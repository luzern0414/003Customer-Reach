"""研究经验沉淀：任务结束后按工具账本统计来源产出，并保存企业研究档案，供下一次规划与采集复用。

- search_experience：按来源（招投标平台、检索渠道、站点域名）累计尝试、成功与“产出被采用”的次数；
- company_memory：按企业保存最近一次研究的有效入口、招投标主页、产出统计与仍缺字段；
- learned_jobs：已学习任务标记，保证同一任务重复结束不重复计数。
只记录来源与统计，不复制网页正文或联系方式。
"""
import hashlib
import re
from urllib.parse import urlparse
from sqlalchemy import select
from .db import Session, Job, ToolCall, Evidence, now
from .company_models import Company, CompanyFact, ProcurementProject, CompanyRelation, TenderRecord, TenderRelation
from .knowledge import store, WORKSPACE

NS_SOURCES = (WORKSPACE, 'search_experience')
NS_COMPANY = (WORKSPACE, 'company_memory')
NS_LEARNED = (WORKSPACE, 'learned_jobs')
SOURCE_LABELS = {'qianlima': '千里马', 'chinabidding': '中国采购与招标网', 'ebnew': '必联网', 'yfbzb_public': '乙方宝', 'exa': '全网检索', 'exa_original': '原始公告追溯'}
HUB_RE = re.compile(r'^(https?://(?:www\.)?[a-z0-9\-]+\.(?:com|cn|net)/qiye/[a-z0-9]+/)')


def company_key(name: str) -> str:
    """name为企业完整名；返回稳定短键，去空白后计算。"""
    return hashlib.sha256(re.sub(r'\s+', '', name).encode()).hexdigest()[:24]


def source_keys(call: ToolCall) -> list[tuple[str, str]]:
    """call为一次工具调用；返回(经验键, 显示名)列表：工具来源一项，读取类再按域名一项。"""
    args = call.arguments or {}
    keys = []
    if call.tool == 'search_tenders':
        source = args.get('source', 'exa')
        keys.append(('tender:' + source, '招投标检索·' + SOURCE_LABELS.get(source, source)))
    elif call.tool == 'search_accounts':
        from .source_catalog import CHANNELS
        keys.append(('search:' + (call.channel or ''), '公开检索·' + CHANNELS.get(call.channel or '', {}).get('name', call.channel or '')))
    host = (urlparse(args.get('url', '')).hostname or '').removeprefix('www.')
    if host and call.tool in {'fetch_source', 'fetch_browser', 'read_tender'}: keys.append(('domain:' + host, '站点·' + host))
    return keys


def used_evidence(db, company_ids: list[str], job_id: str) -> set[str]:
    """db为读取会话；返回被已核验事实、项目、关系或招投标记录引用的证据ID，用于判断来源是否“被采用”。"""
    used = set()
    if company_ids:
        for model in (CompanyFact, ProcurementProject, CompanyRelation):
            for ids in db.scalars(select(model.source_ids).where((model.company_id if hasattr(model, 'company_id') else model.buyer_id).in_(company_ids))):
                used.update(ids or [])
        used.update(x for x in db.scalars(select(TenderRelation.evidence_id).where(TenderRelation.company_id.in_(company_ids))) if x)
    used.update(x for x in db.scalars(select(TenderRecord.evidence_id).where(TenderRecord.job_id == job_id)) if x)
    return used


def learn_from_job(job_id: str) -> dict:
    """job_id为已结束任务；累计来源经验与企业档案并返回本次写入摘要，已学习过的任务直接返回空。"""
    if store.get(NS_LEARNED, job_id): return {}
    with Session() as db:
        job = db.get(Job, job_id)
        if not job or job.status in {'queued', 'running', 'paused'}: return {}
        calls = list(db.scalars(select(ToolCall).where(ToolCall.job_id == job_id, ToolCall.channel != 'model')))
        company_ids = list(job.company_ids or [])
        used = used_evidence(db, company_ids, job_id)
        evidence_by_url = {}
        for row in db.scalars(select(Evidence).where(Evidence.job_id == job_id)):
            evidence_by_url.setdefault(row.url, set()).add(row.id)
        companies = [{'id': c.id, 'name': c.name, 'gaps': list((c.metadata_json or {}).get('gaps', []))[:8]}
                     for cid in company_ids if (c := db.get(Company, cid))]
        tender_counts = {cid: _role_counts(db, cid) for cid in company_ids}
        status = job.status
    stats = {}
    for call in calls:
        result = call.result or {}
        url = (call.arguments or {}).get('url', '')
        produced = bool(result.get('sources') or result.get('notices') or result.get('rows') or result.get('text'))
        adopted = bool(evidence_by_url.get(url, set()) & used) if url else bool(result.get('notices')) and call.status == 'completed'
        for key, label in source_keys(call):
            item = stats.setdefault(key, {'label': label, 'attempts': 0, 'successes': 0, 'adopted': 0, 'elapsed_ms': 0})
            item['attempts'] += call.attempts or 1
            item['successes'] += int(call.status == 'completed' and produced)
            item['adopted'] += int(adopted)
            item['elapsed_ms'] += call.elapsed_ms or 0
    for key, item in stats.items():
        previous = store.get(NS_SOURCES, key)
        data = previous.value if previous else {'label': item['label'], 'attempts': 0, 'successes': 0, 'adopted': 0, 'elapsed_ms': 0}
        store.put(NS_SOURCES, key, {'label': item['label'], 'attempts': data['attempts'] + item['attempts'], 'successes': data['successes'] + item['successes'],
                                    'adopted': data['adopted'] + item['adopted'], 'elapsed_ms': data['elapsed_ms'] + item['elapsed_ms'],
                                    'last_job_id': job_id, 'updated_at': now(), 'source': '实际工具调用统计'})
    for company in companies:
        hubs = sorted({m.group(1) for call in calls if call.tool == 'read_tender' and call.status == 'completed'
                       and (m := HUB_RE.match((call.arguments or {}).get('url', '')))})
        useful = [url for url, ids in evidence_by_url.items() if ids & used][:12]
        failed = sorted({key for call in calls if call.status != 'completed' for key, _ in source_keys(call)})[:12]
        previous = store.get(NS_COMPANY, company_key(company['name']))
        old = previous.value if previous else {}
        store.put(NS_COMPANY, company_key(company['name']), {
            'name': company['name'], 'company_id': company['id'], 'last_job_id': job_id, 'last_status': status,
            'researched_at': now(), 'tender_hubs': sorted(set(old.get('tender_hubs', [])) | set(hubs)),
            'useful_urls': list(dict.fromkeys([*useful, *old.get('useful_urls', [])]))[:20], 'failed_sources': failed,
            'tender_records': tender_counts.get(company['id'], {}), 'gaps': company['gaps'], 'source': '实际研究结果'})
    store.put(NS_LEARNED, job_id, {'learned_at': now(), 'sources': len(stats), 'companies': len(companies)})
    return {'sources': len(stats), 'companies': len(companies)}


def _role_counts(db, company_id: str) -> dict:
    """db为读取会话；返回企业招投标记录各角色数量。"""
    from sqlalchemy import func
    return {role: n for role, n in db.execute(select(TenderRecord.role, func.count()).where(TenderRecord.company_id == company_id).group_by(TenderRecord.role))}


def company_memory(name: str) -> dict:
    """name为企业完整名；返回该企业的研究档案，没有时返回空字典。"""
    item = store.get(NS_COMPANY, company_key(name))
    return item.value if item else {}


def experience_hint(names: list[str], limit: int = 8) -> str:
    """names为本轮目标；返回给规划模型的经验摘要：被采用率高的来源、近期失败来源与企业档案，没有经验时返回空串。"""
    rows = [item.value | {'key': item.key} for item in store.search(NS_SOURCES, limit=200)]
    ranked = sorted([r for r in rows if r.get('attempts', 0) >= 2], key=lambda r: (r['adopted'] / max(1, r['attempts']), r['attempts']), reverse=True)
    good = [f"{r['label']}（采用{r['adopted']}/{r['attempts']}）" for r in ranked if r['adopted']][:limit]
    weak = [r['label'] for r in ranked if r['attempts'] >= 3 and r['successes'] == 0][:5]
    parts = []
    if good: parts.append('过往有效来源：' + '、'.join(good))
    if weak: parts.append('多次无结果的来源（少用）：' + '、'.join(weak))
    for name in names:
        memory = company_memory(name)
        if memory:
            parts.append(f"{name}上次研究于{memory.get('researched_at', '')[:10]}，有效入口：" + '、'.join(memory.get('useful_urls', [])[:5]))
    return ('\n研究经验（来自历史任务统计，仅作检索优先级参考，不是企业事实）：' + '；'.join(parts)) if parts else ''
