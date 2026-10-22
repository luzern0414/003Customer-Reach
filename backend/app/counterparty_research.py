"""上下游独立资料的有界补充；与主研究共享预算，不创建隐式新任务。"""
from sqlalchemy import select, func
from .db import Session, Job, ToolCall, now
from .company_models import CompanyRelation, ResearchCompany
from .relation_service import composite_name, counterparty_profile
from .service import ServiceError
from .research_tools import guard


def save_progress(job_id: str, relation_id: str, phase: str, sub: dict) -> None:
    """job_id/关系ID必填，phase为下一子阶段，sub为状态；只存恢复值，片段正文通过Evidence读回。"""
    saved = dict(sub)
    for key in ('company_clean_queue', 'company_failed_chunks'):
        saved[key] = [{k:v for k,v in item.items() if k != 'body'} for item in sub.get(key, [])]
    with Session.begin() as db:
        job = db.get(Job, job_id)
        states = dict((job.metrics or {}).get('counterparty_states', {}))
        states[relation_id] = {'phase': phase, 'state': saved}
        job.metrics = {**(job.metrics or {}), 'counterparty_states': states}


async def company_counterparties(state: dict) -> dict:
    """state为主企业已保存结果；只补其真实上下游身份/主营/官网，暂停传播、额度用完保留待补。"""
    from .company_research import company_collect, company_clean, company_extract, company_save
    from .company_service import stable_key
    with Session() as db:
        job = db.get(Job, state['job_id'])
        only = bool((job.metrics or {}).get('counterparty_only'))
        requested = (job.metrics or {}).get('requested_fields', [])
        roots = list(job.company_ids or [])
        selected = (job.metrics or {}).get('target_company_id')
        if selected and selected not in roots: roots.append(selected)
        if not only and not {'supplier', 'customer'} & set(requested): return {}
        rows = list(db.scalars(select(CompanyRelation).where(CompanyRelation.company_id.in_(roots),
            CompanyRelation.relation_type.in_(['supplier', 'customer', 'service_supplier', 'subsidiary'])).order_by(CompanyRelation.rank, CompanyRelation.id)))
        if only:
            wanted = set((job.metrics or {}).get('counterparty_relation_ids', []))
            rows = [r for r in rows if r.id in wanted]
        else:
            selected_rows = []
            for owner in roots:
                for kind in ('supplier', 'customer'):
                    group = [r for r in rows if r.company_id == owner and r.relation_type == kind]
                    period = max((r.report_period or '' for r in group), default='')
                    distinct = {r.counterparty_name: r for r in group if (r.report_period or '') == period}
                    selected_rows.extend(list(distinct.values())[:5])
            rows = selected_rows
        items = [{'id': r.id, 'name': r.counterparty_name} for r in rows[:10]]
    pending = []; completed = 0; updates = 0
    channel = next((c for c in ('official', 'directory', 'qcc') if c in state['options']['enabled_channels']), None)
    for item in items:
        guard(state['job_id'])
        with Session() as db:
            relation = db.get(CompanyRelation, item['id'])
            profile = counterparty_profile(db, relation)
            counts = {tool: db.scalar(select(func.coalesce(func.sum(ToolCall.attempts), 0)).where(
                ToolCall.job_id == state['job_id'], ToolCall.tool.in_(['fetch_source', 'fetch_browser']) if tool == 'read' else ToolCall.tool == 'search_accounts')) for tool in ('search', 'read')}
            model_calls = ((db.get(Job, state['job_id']).metrics or {}).get('model_budget') or {}).get('calls', 0)
            saved = ((db.get(Job, state['job_id']).metrics or {}).get('counterparty_states') or {}).get(item['id'])
        if profile and profile['facts'].get('business') and profile['sources']:
            completed += 1; continue
        if composite_name(item['name']):
            pending.append(item['name']); continue
        if not saved and (not channel or counts['search'] >= state['options']['max_searches'] or counts['read'] >= state['options']['max_reads'] or model_calls >= state['options'].get('max_model_calls', 32) - 1):
            pending.append(item['name']); continue
        sub = {**state, 'counterparty_relation_id': item['id'], 'company_target_name': '',
            'company_targets': [item['name']], 'company_intent_targets': [item['name']],
            'company_requested_fields': ['name', 'business', 'products', 'industry', 'address', 'website'],
            'company_identities': [], 'company_ids': [], 'source_ids': [], 'company_local_sources': [],
            'company_clean_queue': [], 'company_failed_chunks': [], 'company_extracted_keys': [], 'company_receipts': [],
            'company_batches': [], 'company_direct_urls': [], 'company_read_cursor': 0, 'cursor': 0,
            'company_updates': 0, 'warnings': [], 'attempts': [],
            'steps': [{'entity_name': item['name'], 'query': item['name'] + ' 企业介绍 主营产品 官方网站', 'channel': channel}]}
        phase = 'collect'
        if saved:
            sub = {**sub, **saved['state'], 'options': state['options']}
            phase = saved['phase']
            if phase == 'done' and sub.get('company_failed_chunks'):
                sub['company_clean_queue'] = list({x['key']:x for x in [*sub.get('company_clean_queue', []), *sub['company_failed_chunks']]}.values())
                sub['company_failed_chunks'] = []
                phase = 'extract'
        try:
            # 子阶段在同Job持久化；最后一份读取耗尽预算后，恢复仍优先分析已归档正文。
            while phase != 'done':
                guard(state['job_id'])
                save_progress(state['job_id'], item['id'], phase, sub)
                if phase == 'collect':
                    sub.update(await company_collect(sub)); phase = 'clean'
                elif phase == 'clean':
                    sub.update(await company_clean(sub)); phase = 'extract'
                elif phase == 'extract':
                    sub.update(await company_extract(sub)); phase = 'save'
                else:
                    sub.update(await company_save(sub)); phase = 'extract' if sub.get('company_clean_queue') else 'done'
                save_progress(state['job_id'], item['id'], phase, sub)
            updates += sub.get('company_updates', 0)
        except ServiceError as exc:
            if not any(word in str(exc) for word in ('预算', '额度')): raise
        with Session.begin() as db:
            relation = db.get(CompanyRelation, item['id'])
            profile = counterparty_profile(db, relation)
            ready = bool(profile and profile['facts'].get('business') and profile['sources'])
            relation.payload = {**(relation.payload or {}), 'profile_research': {
                'status': 'verified' if ready else 'partial', 'job_id': state['job_id'], 'updated_at': now()}}
        if ready: completed += 1
        else: pending.append(item['name'])
    with Session.begin() as db:
        job = db.get(Job, state['job_id'])
        progress = {'total': len(items), 'completed': completed, 'pending': pending}
        job.metrics = {**(job.metrics or {}), 'counterparty_progress': progress}
        if only:
            job.company_ids = roots
            for position, owner in enumerate(roots):
                key = stable_key(job.conversation_id, job.id, owner)
                if not db.scalar(select(ResearchCompany.id).where(ResearchCompany.unique_key == key)):
                    db.add(ResearchCompany(unique_key=key, company_id=owner, conversation_id=job.conversation_id,
                        job_id=job.id, position=position, origin='agent'))
    output = {'counterparty_progress': progress}
    if only:
        output.update(company_ids=roots, company_targets=[state.get('company_target_name')] if state.get('company_target_name') else state.get('company_targets', []),
            company_updates=updates or completed, company_questions=[],
            gaps=['企业资料待补：' + name for name in pending],
            company_coverage={'missing_fields': ['counterparty_profiles'] if pending else []})
    return output
