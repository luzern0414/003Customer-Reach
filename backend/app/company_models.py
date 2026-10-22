"""企业研究持久模型：身份、原文事实、需求项目与年度关系分开存储。"""
from sqlalchemy import Column, String, Text, JSON, Integer, Boolean, ForeignKey, Numeric
from .db import Base, identifier, now


class Company(Base):
    """研究主体；报告集团/品牌/未知主体不冒充已工商消歧法人。"""
    __tablename__ = 'companies'
    id = Column(String, primary_key=True, default=identifier)
    identity_key = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False, index=True)
    short_name = Column(String, default='')
    entity_kind = Column(String, default='legal')
    view_scope = Column(String, default='entity')
    visibility = Column(String, default='primary', index=True)
    credit_code = Column(String, nullable=True)
    origin = Column(String, default='agent')
    research_as_of = Column(String, default='')
    metadata_json = Column(JSON, default=dict)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class CompanyFact(Base):
    """逐项事实保留原值、单位、报告期与证据，不用最新值覆盖不同统计期。"""
    __tablename__ = 'company_facts'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    company_id = Column(String, ForeignKey('companies.id'), nullable=False, index=True)
    category = Column(String, default='')
    field = Column(String, nullable=False, index=True)
    label = Column(String, nullable=False)
    raw_value = Column(JSON, nullable=True)
    numeric_value = Column(Numeric(24, 4), nullable=True)
    unit = Column(String, default='')
    raw_unit = Column(String, default='')
    report_period = Column(String, default='')
    as_of = Column(String, default='')
    scope = Column(String, default='')
    status = Column(String, default='verified')
    source_ids = Column(JSON, default=list)
    quote = Column(Text, default='')
    note = Column(Text, default='')
    provenance = Column(JSON, default=dict)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class ProcurementProject(Base):
    """同一真实买方的采购需求；计划、品牌应用和已成交分类型保留。"""
    __tablename__ = 'procurement_projects'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    buyer_id = Column(String, ForeignKey('companies.id'), nullable=False, index=True)
    title = Column(String, nullable=False)
    project_number = Column(String, default='')
    record_kind = Column(String, default='procurement', index=True)
    stage = Column(String, default='unknown')
    published_at = Column(String, default='')
    deadline = Column(String, default='')
    payload = Column(JSON, default=dict)
    source_ids = Column(JSON, default=list)
    quote = Column(Text, default='')
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class ProcurementNotice(Base):
    """项目下的独立公告事件；附件和转载只是事件来源，不增加采购次数。"""
    __tablename__ = 'procurement_notices'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    project_id = Column(String, ForeignKey('procurement_projects.id'), nullable=False, index=True)
    title = Column(String, nullable=False)
    notice_type = Column(String, default='')
    published_at = Column(String, default='')
    platform_published_at = Column(String, default='')
    deadline = Column(String, default='')
    source_ids = Column(JSON, default=list)
    payload = Column(JSON, default=dict)
    created_at = Column(String, default=now)


class CompanyRelation(Base):
    """报告明确的双端关系；年度金额和占比不推断具体产品或采购频率。"""
    __tablename__ = 'company_relations'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    company_id = Column(String, ForeignKey('companies.id'), nullable=False, index=True)
    counterparty_id = Column(String, ForeignKey('companies.id'), nullable=True)
    counterparty_name = Column(String, nullable=False)
    relation_type = Column(String, nullable=False, index=True)
    rank = Column(Integer, nullable=True)
    report_period = Column(String, default='')
    amount = Column(Numeric(24, 4), nullable=True)
    currency = Column(String, nullable=True)
    unit = Column(String, default='')
    share = Column(Numeric(12, 4), nullable=True)
    scope = Column(String, default='')
    source_ids = Column(JSON, default=list)
    quote = Column(Text, default='')
    note = Column(Text, default='')
    payload = Column(JSON, default=dict)
    created_at = Column(String, default=now)


class ResearchCompany(Base):
    """真实会话/任务成员；历史导入仅关联标记清楚的历史会话，不伪造任务。"""
    __tablename__ = 'research_companies'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    company_id = Column(String, ForeignKey('companies.id'), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey('conversations.id'), nullable=False, index=True)
    job_id = Column(String, ForeignKey('jobs.id'), nullable=True, index=True)
    position = Column(Integer, default=0)
    origin = Column(String, default='agent')
    created_at = Column(String, default=now)


class ResearchDataset(Base):
    """每轮清洗、提取、核验与最终快照；未核验提议与企业事实分开存储。"""
    __tablename__ = 'research_datasets'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    job_id = Column(String, ForeignKey('jobs.id'), nullable=False, index=True)
    conversation_id = Column(String, ForeignKey('conversations.id'), nullable=False, index=True)
    company_id = Column(String, ForeignKey('companies.id'), nullable=True)
    phase = Column(String, nullable=False)
    status = Column(String, default='pending')
    source_ids = Column(JSON, default=list)
    payload = Column(JSON, default=dict)
    cleaning_version = Column(String, default='research-clean-1')
    model_version = Column(String, default='gpt-6-luna')
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class TenderRecord(Base):
    """招投标平台的逐条公告；角色按原文标签判定，关系由记录汇总而非年度披露。"""
    __tablename__ = 'tender_records'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    company_id = Column(String, ForeignKey('companies.id'), nullable=False, index=True)
    job_id = Column(String, ForeignKey('jobs.id'), nullable=True, index=True)
    role = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    notice_type = Column(String, default='')
    project_number = Column(String, default='')
    published_at = Column(String, default='', index=True)
    buyer_name = Column(String, default='')
    winner_names = Column(JSON, default=list)
    candidate_names = Column(JSON, default=list)
    agency_name = Column(String, default='')
    amount = Column(String, default='')
    budget = Column(String, default='')
    region = Column(String, default='')
    items = Column(JSON, default=list)
    platform = Column(String, default='')
    url = Column(String, default='')
    evidence_id = Column(String, ForeignKey('evidence.id'), nullable=True)
    quote = Column(Text, default='')
    confidence = Column(String, default='index')
    payload = Column(JSON, default=dict)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)


class TenderRelation(Base):
    """由招投标记录或平台合作统计汇总的对手方；次数与金额只代表公开招投标口径。"""
    __tablename__ = 'tender_relations'
    id = Column(String, primary_key=True, default=identifier)
    unique_key = Column(String, nullable=False, unique=True)
    company_id = Column(String, ForeignKey('companies.id'), nullable=False, index=True)
    counterparty_name = Column(String, nullable=False)
    relation_type = Column(String, nullable=False, index=True)
    deal_count = Column(Integer, default=0)
    amount_total = Column(String, default='')
    latest_at = Column(String, default='')
    record_ids = Column(JSON, default=list)
    platform = Column(String, default='')
    url = Column(String, default='')
    evidence_id = Column(String, ForeignKey('evidence.id'), nullable=True)
    quote = Column(Text, default='')
    basis = Column(String, default='records')
    payload = Column(JSON, default=dict)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now)
