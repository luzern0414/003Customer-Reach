"""双端关系与对手方独立资料；关系报告不冒充对方的企业介绍。"""
import re
from sqlalchemy import select
from .db import Session, Evidence, serialize
from .company_models import Company, CompanyFact, CompanyRelation
from .service import ServiceError
from .source_service import entry_references

LABELS = {'supplier': '采购供应商', 'customer': '销售客户', 'subsidiary': '子公司', 'service_supplier': '服务供应商'}


def composite_name(name: str) -> bool:
    """name为报告原披露名，可空；返回是否明确含多主体组合，不能将组合统计套给单体。"""
    return bool(re.search(r'(?:及|和|与).{0,3}(?:关联|相关|下属|子公司)|(?:有限公司|股份公司).{0,3}(?:及|和|与).{1,80}(?:有限公司|股份公司)', name or ''))


def relation_projection(row: CompanyRelation, parent: Company) -> dict:
    """row/parent须存在且两者归属一致；返回明确方向、报告依据和独立地址，不推断交易产品。"""
    value = serialize(row)
    value['amount'] = float(row.amount) if row.amount is not None else None
    value['share'] = float(row.share) if row.share is not None else None
    name = parent.short_name or parent.name
    directions = {'supplier': f'{name}向该企业采购', 'customer': f'{name}向该企业销售',
                  'subsidiary': f'该企业是{name}的子公司', 'service_supplier': f'该企业向{name}提供服务'}
    period = row.report_period or ''
    rank = f' · 第{row.rank}位' if row.rank else ''
    value.update(relation_label=LABELS.get(row.relation_type, '公开关系'),
        direction=directions.get(row.relation_type, '公开资料披露双方关系'),
        reason=(period + '年报' if re.fullmatch(r'\d{4}', period) else period or '公开披露') + rank,
        detail_url=f'/companies/{parent.id}/relations/{row.id}',
        identity_status='composite' if composite_name(row.counterparty_name) else 'verified' if row.counterparty_id and row.counterparty_id != row.company_id else 'reported_name')
    value['trade_product'] = None  # 年度关系未含交易产品专属引文时，不从名称或对方主营推断。
    value['amount_label'] = {'supplier':'采购额', 'customer':'销售额', 'service_supplier':'服务采购额'}.get(row.relation_type, '披露金额')
    value['from_name'] = parent.short_name or parent.name if row.relation_type in {'customer', 'subsidiary'} else row.counterparty_name
    value['to_name'] = row.counterparty_name if row.relation_type in {'customer', 'subsidiary'} else parent.short_name or parent.name
    return value


def counterparty_profile(db, relation: CompanyRelation) -> dict | None:
    """db为读取会话、relation须存在；只返回该对手方自己的核验字段，未知/组合主体返回空。"""
    from .company_service import fact_view, source_summary
    if not relation.counterparty_id or relation.counterparty_id == relation.company_id or composite_name(relation.counterparty_name):
        return None
    company = db.get(Company, relation.counterparty_id)
    if not company:
        return None
    facts = list(db.scalars(select(CompanyFact).where(CompanyFact.company_id == company.id,
        CompanyFact.status == 'verified').order_by(CompanyFact.as_of.desc(), CompanyFact.updated_at.desc())))
    fields = {}
    for row in facts:
        if row.field in {'name', 'industry', 'business', 'products', 'address', 'website', 'short_name'} and row.field not in fields:
            fields[row.field] = fact_view(row)
    source_ids = {sid for row in fields.values() for sid in row.get('source_ids') or []}
    sources = [source_summary(row) for row in db.scalars(select(Evidence).where(Evidence.id.in_(source_ids)))] if source_ids else []
    return {'id': company.id, 'name': company.name, 'short_name': company.short_name,
        'research_as_of': company.research_as_of, 'facts': fields, 'sources': sources,
        'profile_url': '/companies/' + company.id}


def relation_detail(company_id: str, relation_id: str) -> dict:
    """两个ID为持久ID且必填；返回当前企业的关系与对方专属资料，跨企业引用或不存在404。"""
    with Session() as db:
        parent = db.get(Company, company_id)
        row = db.get(CompanyRelation, relation_id)
        if not parent or not row or row.company_id != company_id:
            raise ServiceError('企业关系不存在', 404)
        relation = relation_projection(row, parent)
        relation['evidence_refs'] = entry_references(db, {'relation': [row.id]}).get(row.id, [])
        return {'company': {'id': parent.id, 'name': parent.name, 'short_name': parent.short_name},
            'relation': relation, 'counterparty': counterparty_profile(db, row),
            'research_state': (row.payload or {}).get('profile_research', {})}


def research_counterparties(company_id: str, values: dict, relation_id='') -> dict:
    """company_id必存在、values含幂等token/可选会话、relation_id空则补首屏上下游；仅显式提交创建任务。"""
    from .company_service import company_research
    with Session() as db:
        company = db.get(Company, company_id)
        if not company:
            raise ServiceError('企业不存在', 404)
        rows = list(db.scalars(select(CompanyRelation).where(CompanyRelation.company_id == company_id,
            CompanyRelation.relation_type.in_(['supplier', 'customer', 'service_supplier', 'subsidiary']))))
        if relation_id:
            rows = [row for row in rows if row.id == relation_id]
            if not rows: raise ServiceError('企业关系不存在', 404)
        else:
            selected = []
            for kind in ('supplier', 'customer'):
                group = [r for r in rows if r.relation_type == kind]
                period = max((r.report_period or '' for r in group), default='')
                selected.extend(sorted([r for r in group if (r.report_period or '') == period], key=lambda r: r.rank or 999)[:5])
            rows = selected
        ids = [row.id for row in rows]
    if not ids: raise ServiceError('暂无可补齐的上下游企业', 422)
    return company_research(company_id, {**values,
        'content': '补齐该企业已披露上下游公司的独立主营、地区与企业资料来源，不扩展到其他同行。',
        '_operation': {'counterparty_only': True, 'counterparty_relation_ids': ids}})
