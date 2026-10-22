"""招投标数据投影：按企业汇总采购/中标记录与对手方，供详情页、回答与缺口判断使用。"""
import re
from collections import Counter
from sqlalchemy import select, func
from .company_models import TenderRecord, TenderRelation
from .db import Evidence

CONFIRMED_ROLES = ('buyer', 'winner', 'candidate', 'agency')
RELATION_TYPES = ('customer', 'supplier', 'competitor', 'agency')
BASIS_LABELS = {'records': '招投标公告', 'platform_stats': '招标平台合作统计', 'third_party_list': '第三方供应商名录'}


def tender_source_ids(db, company_id):
    """只返回本企业招投标条目实际绑定、且仍存在的 Evidence；不借同 Job 解锁其他主体。"""
    ids=set(db.scalars(select(TenderRecord.evidence_id).where(TenderRecord.company_id==company_id,TenderRecord.evidence_id.is_not(None))))
    ids.update(db.scalars(select(TenderRelation.evidence_id).where(TenderRelation.company_id==company_id,TenderRelation.evidence_id.is_not(None))))
    for payload in db.scalars(select(TenderRecord.payload).where(TenderRecord.company_id==company_id)):
        ids.update(a['source_id'] for a in ((payload or {}).get('evidence_fields') or {}).get('alternate_sources',[]) if isinstance(a,dict) and a.get('source_id'))
    return set(db.scalars(select(Evidence.id).where(Evidence.id.in_(ids)))) if ids else set()


def record_view(row: TenderRecord) -> dict:
    """row为已保存记录；返回界面所需字段，原文行与证据链接保留，空值不补。"""
    return {'id': row.id, 'role': row.role, 'title': row.title, 'published_at': row.published_at, 'buyer_name': row.buyer_name,
            'winner_names': row.winner_names or [], 'candidate_names': row.candidate_names or [], 'agency_name': row.agency_name,
            'amount': row.amount, 'budget': row.budget, 'region': row.region, 'items': row.items or [], 'platform': row.platform,
            'url': row.url, 'evidence_id': row.evidence_id, 'quote': row.quote, 'confidence': row.confidence,
            'project_number': row.project_number,
            'deadline': ((row.payload or {}).get('evidence_fields') or {}).get('deadline',{}).get('value','')}


def merge_relations(rows: list[TenderRelation]) -> dict:
    """rows为同一企业的对手方；同名同类型跨口径合并，次数取各口径最大值，保留全部口径与证据。"""
    merged: dict[tuple, dict] = {}
    for row in rows:
        if (row.payload or {}).get('unsupported_by_current_records'):continue
        key = (row.relation_type, row.counterparty_name)
        item = merged.setdefault(key, {'name': row.counterparty_name, 'relation_type': row.relation_type, 'count': 0,
                                       'latest_at': '', 'bases': [], 'evidence': [], 'record_ids': []})
        item['count'] = max(item['count'], row.deal_count or 0)
        item['latest_at'] = max(item['latest_at'], row.latest_at or '')
        if row.basis not in item['bases']: item['bases'].append(row.basis)
        item['record_ids'] = list(dict.fromkeys([*item['record_ids'], *(row.record_ids or [])]))
        if row.url: item['evidence'].append({'url': row.url, 'platform': row.platform, 'quote': row.quote, 'basis': BASIS_LABELS.get(row.basis, row.basis),
                                             'evidence_id': row.evidence_id})
    result = {kind: [] for kind in RELATION_TYPES}
    for item in merged.values():
        item['basis_labels'] = [BASIS_LABELS.get(b, b) for b in item['bases']]
        result[item['relation_type']].append(item)
    for kind in result:
        result[kind].sort(key=lambda x: (-x['count'], x['latest_at'] == '', x['name']))
    return result


def top_items(records: list[dict], limit: int = 12) -> list[dict]:
    """records为采购记录；按物资名称统计出现次数，次数相同保持名称顺序，仅反映已读公告清单。"""
    counter, sample = Counter(), {}
    for record in records:
        for item in record['items']:
            name = re.sub(r'\s+', '', item.get('name', ''))
            if not name: continue
            counter[name] += 1
            sample.setdefault(name, item)
    return [{'name': name, 'count': count, 'spec': sample[name].get('spec', ''), 'unit': sample[name].get('unit', '')}
            for name, count in counter.most_common(limit)]


def tender_view(db, company_id: str, record_limit: int = 200) -> dict:
    """db为读取会话、company_id为主体ID；返回招投标汇总、记录与对手方，无数据时各列表为空。"""
    rows = list(db.scalars(select(TenderRecord).where(TenderRecord.company_id == company_id)
                           .order_by(TenderRecord.published_at.desc(), TenderRecord.updated_at.desc()).limit(record_limit)))
    from .company_models import Company
    from .tender_parse import title_key
    company = db.get(Company, company_id)
    rank = {'detail': 2, 'listing': 1, 'index': 0}
    best: dict[str, TenderRecord] = {}
    def display_key(row):
        # MCP confirmed events keep dates/project IDs; an annual recurring title is not one event.
        if (row.payload or {}).get('mcp_record_key'):return row.payload['mcp_record_key']
        return title_key(row.title, company.name if company else '') or row.id
    # 历史版本的记录键较粗，展示时按“去企业名的标题”再合并一次，保留置信度最高、字段最全的一条。
    for row in rows:
        key = display_key(row)
        current = best.get(key)
        if not current or (rank.get(row.confidence, 0), len(row.items or []), row.role != 'related') > (rank.get(current.confidence, 0), len(current.items or []), current.role != 'related'):
            best[key] = row
    records = [record_view(r) for r in rows if best.get(display_key(r)) is r]
    # 从记录自身归档版本补投标报价/业绩，读取有界且无写入，不把业绩计入成交数。
    from .tender_parse import candidate_context
    evidence_ids = {r['evidence_id'] for r in records if r['evidence_id']}
    evidence = {e.id: e for e in db.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids)))} if evidence_ids else {}
    for record in records:
        source = evidence.get(record['evidence_id'])
        if source and company:
            context = candidate_context(source.body or '', company.name)
            record['candidate_bid'] = context['bid']
            if not context['bid']:
                from .public_tender_tables import bid_context
                record['candidate_bid']=bid_context(source.body or '',company.name)
            record['disclosed_performance'] = context['disclosed_performance']
    relations = merge_relations(list(db.scalars(select(TenderRelation).where(TenderRelation.company_id == company_id))))
    # 历史派生关系只存record_ids时，引用回到对应公告，不能只给模型一个名字。
    by_id = {r['id']: r for r in records}
    for items in relations.values():
        for item in items:
            if item['evidence']: continue
            for rid in item['record_ids']:
                record = by_id.get(rid)
                if record and record['url']:
                    item['evidence'].append({'url': record['url'], 'platform': record['platform'], 'quote': record['quote'],
                        'basis': BASIS_LABELS['records'], 'evidence_id': record['evidence_id']})
    by_role = Counter(r['role'] for r in records)
    purchases = [r for r in records if r['role'] == 'buyer']
    wins = [r for r in records if r['role'] in {'winner', 'candidate'}]
    months = Counter(r['published_at'][:7] for r in purchases if r['published_at'])
    platforms = sorted({r['platform'] for r in records if r['platform']})
    # 待核实只展示标题/引文出现企业全称的记录；全文检索的无关命中不展示。
    name = re.sub(r'\s+', '', company.name) if company else ''
    pending = [r for r in records if r['role'] in {'related', 'mentioned'} and name and name in re.sub(
        r'\s+', '', r['title'] + r['quote'] + ((r.get('candidate_bid') or {}).get('quote', '')))]
    return {'summary': {'purchases': by_role.get('buyer', 0), 'wins': by_role.get('winner', 0), 'candidates': by_role.get('candidate', 0),
                        'pending': len(pending),
                        'detail_confirmed': sum(r['confidence'] == 'detail' for r in records),
                        'latest_purchase': purchases[0]['published_at'] if purchases else '',
                        'latest_win': next((r['published_at'] for r in wins if r['published_at']), ''),
                        'customers': len(relations['customer']), 'suppliers': len(relations['supplier']),
                        'competitors': len(relations['competitor']), 'platforms': platforms,
                        'purchases_by_month': sorted(months.items())[-12:]},
            'purchases': purchases, 'wins': wins,
            'pending': pending[:40],
            'relations': relations, 'top_items': top_items(purchases)}


def tender_counts(db, company_ids: list[str]) -> dict:
    """db为读取会话、company_ids为主体ID列表；返回每家企业的采购/中标/客户/供应商数，用于列表卡片。"""
    if not company_ids: return {}
    result = {cid: {'tender_purchases': 0, 'tender_wins': 0, 'tender_customers': 0, 'tender_suppliers': 0} for cid in company_ids}
    for cid, role, count in db.execute(select(TenderRecord.company_id, TenderRecord.role, func.count())
                                       .where(TenderRecord.company_id.in_(company_ids)).group_by(TenderRecord.company_id, TenderRecord.role)):
        if role == 'buyer': result[cid]['tender_purchases'] = count
        elif role == 'winner': result[cid]['tender_wins'] = count
    for cid, kind, count in db.execute(select(TenderRelation.company_id, TenderRelation.relation_type, func.count(func.distinct(TenderRelation.counterparty_name)))
                                       .where(TenderRelation.company_id.in_(company_ids),func.coalesce(TenderRelation.payload['unsupported_by_current_records'].as_boolean(),False)==False).group_by(TenderRelation.company_id, TenderRelation.relation_type)):
        if kind == 'customer': result[cid]['tender_customers'] = count
        elif kind == 'supplier': result[cid]['tender_suppliers'] = count
    return result


def tender_brief(db, company_id: str) -> dict:
    """db为读取会话、company_id为主体ID；返回给模型回答用的紧凑摘要，条目数有界避免超出上下文。"""
    view = tender_view(db, company_id)
    if not any(view['summary'][k] for k in ('purchases', 'wins', 'candidates', 'customers', 'suppliers', 'competitors', 'pending')): return {}
    brief = lambda r: {k: r[k] for k in ('role', 'title', 'published_at', 'buyer_name', 'amount', 'budget', 'platform','project_number','deadline','url','quote',
                                      'candidate_bid', 'disclosed_performance') if r.get(k)} | (
        {'items': [i['name'] + (f"×{i['quantity']}{i['unit']}" if i.get('quantity') else '') for i in r['items'][:5]]} if r['items'] else {})
    rel = lambda kind, n: [{'name': x['name'], 'count': x['count'], 'basis': x['basis_labels'],
                          'record_ids': x['record_ids'], 'evidence': x['evidence'][:2]} for x in view['relations'][kind][:n]]
    return {'summary': {k: v for k, v in view['summary'].items() if k != 'purchases_by_month'},
            'recent_purchases': [brief(r) for r in view['purchases'][:8]], 'recent_wins': [brief(r) for r in view['wins'][:8]],
            'top_items': view['top_items'][:8], 'customers': rel('customer', 10), 'suppliers': rel('supplier', 10),
            'competitors': rel('competitor', 6),
            'pending': [brief(r) for r in view['pending'][:4]],
            'note': '招投标口径：次数为公开招投标/平台合作统计次数，不是年度交易额；候选不等于成交，投标报价不等于成交金额；业绩披露不计入本轮中标/客户数；待核实记录未计入。'}


def evidence_url(db, evidence_id: str | None) -> str:
    """db为读取会话、evidence_id可空；返回证据原始URL，不存在返回空串。"""
    row = db.get(Evidence, evidence_id) if evidence_id else None
    return row.url if row else ''


def research_summary(company_id: str, reused: bool = False):
    """company_id为主体ID；由数据库确定性生成CompanyResearchSummary（Pydantic），供回答、后续任务与界面复用。"""
    from .company_service import company_detail
    from .tender_models import CompanyResearchSummary, Counterparty
    detail = company_detail(company_id)
    header, tenders = detail['header'], detail['tenders']
    rel = lambda kind, n: [Counterparty(name=x['name'], count=x['count'], basis=x['basis_labels']) for x in tenders['relations'][kind][:n]]
    facts = {field: str(value['raw_value'])[:200] for field, value in header['facts'].items() if value}
    registration = {f['label']: f['value'][:200] for f in (detail.get('registration') or {}).get('fields', [])}
    purchases = tenders['purchases']
    return CompanyResearchSummary(
        company_id=company_id, name=header['name'], data_as_of=header.get('research_as_of') or '', reused=reused,
        registration=registration, facts=facts, purchases=tenders['summary']['purchases'], latest_purchase=tenders['summary']['latest_purchase'],
        recent_purchases=[(r['published_at'] + ' ' if r['published_at'] else '') + r['title'][:80] for r in purchases[:8]],
        top_items=[i['name'] + (f"（{i['count']}次）" if i['count'] > 1 else '') for i in tenders['top_items'][:8]],
        wins=tenders['summary']['wins'], candidates=tenders['summary']['candidates'],
        customers=rel('customer', 10), suppliers=rel('supplier', 10), competitors=rel('competitor', 8),
        annual_suppliers=header.get('supplier_count', 0), annual_customers=header.get('customer_count', 0),
        sources=header.get('source_count', 0), gaps=list(detail.get('gaps') or [])[:12])
