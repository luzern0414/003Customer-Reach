"""公司研究工具契约：每项数据绑定独立连续原文，未知值保持空。"""
from typing import Literal
from pydantic import BaseModel, Field
from .schemas import ResearchStep


class CompanyStep(ResearchStep):
    """单个公司和单渠道的有界搜索步骤。"""
    entity_name: str = Field(min_length=1, max_length=200)


class CompanyPlan(BaseModel):
    """只研究用户指定主体；信息不足返回问题，不把卖方产品作为必填项。"""
    targets: list[str] = Field(default_factory=list, max_length=8)
    steps: list[CompanyStep] = Field(default_factory=list, max_length=6)
    questions: list[str] = Field(default_factory=list, max_length=2)


class ResearchFact(BaseModel):
    """值与统计口径分别引用实际正文，禁止把发布时间当统计时间。"""
    field: Literal['name','short_name','credit_code','stock_code','industry','business','products','address','phone','email','website','headcount','revenue','procurement_rule','detail']
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=2000)
    unit: str = Field(default='', max_length=30)
    report_period: str = Field(default='', max_length=30)
    scope: str = Field(default='', max_length=100)
    source_id: str = Field(min_length=1, max_length=64)
    quote: str = Field(min_length=3, max_length=1800)
    metadata_quote: str = Field(default='', max_length=1800)
    note: str = Field(default='', max_length=400)


class ResearchRelation(BaseModel):
    """年度双端关系，与具体逐笔采购分开；金额、币种、占比必须有原文。"""
    counterparty_name: str = Field(min_length=2, max_length=200)
    relation_type: Literal['supplier','customer','subsidiary','service_supplier']
    report_period: str = Field(default='', max_length=30)
    amount: str | None = Field(default=None, max_length=50)
    unit: str = Field(default='', max_length=30)
    currency: Literal['CNY','USD','EUR'] | None = None
    share: float | None = Field(default=None, ge=0, le=100)
    source_id: str = Field(min_length=1, max_length=64)
    quote: str = Field(min_length=3, max_length=1800)
    metadata_quote: str = Field(default='', max_length=1800)
    note: str = Field(default='', max_length=400)


class ResearchProject(BaseModel):
    """原始公告的需求项目；实际买方、预算和候选/最终结果必须分别绑定来源。"""
    buyer_name: str = Field(min_length=2, max_length=200)
    title: str = Field(min_length=2, max_length=300)
    project_number: str = Field(default='', max_length=200)
    project_number_quote: str = Field(default='', max_length=1000, description='项目编号/采购号标签与原编号的同源连续引文，可与标题分开')
    stage: Literal['open','candidate','awarded','closed','unknown'] = 'unknown'
    publication_date: str = Field(default='', max_length=30)
    deadline: str = Field(default='', max_length=30)
    publication_quote: str = Field(default='', max_length=1000)
    deadline_quote: str = Field(default='', max_length=1000)
    product: str = Field(default='', max_length=200)
    quantity: float | None = Field(default=None, ge=0)
    unit: str = Field(default='', max_length=30)
    budget_value: str | None = Field(default=None, max_length=50)
    budget_unit: str = Field(default='', max_length=30)
    budget_quote: str = Field(default='', max_length=1000)
    buyer_quote: str = Field(default='', max_length=1000, description='同源连续原文，含采购人/招标人标签与完整买方名称；与标题引文分开')
    quantity_quote: str = Field(default='', max_length=1000, description='同源需求数量与单位原文；数量未知时留空')
    specifications: str = Field(default='', max_length=2000)
    source_id: str = Field(min_length=1, max_length=64)
    quote: str = Field(min_length=3, max_length=3000)
    metadata_quote: str = Field(default='', max_length=1800)


class CompanySnapshot(BaseModel):
    """当前主体的结构化提议；姓名、字段、项目和关系均由后端核验后持久。"""
    name: str = Field(min_length=2, max_length=200)
    source_id: str = Field(min_length=1, max_length=64)
    identity_quote: str = Field(min_length=3, max_length=1500)
    facts: list[ResearchFact] = Field(default_factory=list, max_length=24)
    projects: list[ResearchProject] = Field(default_factory=list, max_length=8)
    relations: list[ResearchRelation] = Field(default_factory=list, max_length=15)
    gaps: list[str] = Field(default_factory=list, max_length=8)


class CompanyBatch(BaseModel):
    """一次有界正文提取，仅提出实际出现的主体，不用搜索标题补造事实。"""
    companies: list[CompanySnapshot] = Field(default_factory=list, max_length=2)
    warnings: list[str] = Field(default_factory=list, max_length=8)


class IntentDecision(BaseModel):
    """每条新消息的模型意图；历史仅补指代，来源权限仍由工具执行门禁确认。"""
    intent: Literal['quick','chat','document','research','company_query']
    research_prompt: str = Field(default='',max_length=20000)
    targets: list[str] = Field(default_factory=list,max_length=8)
    requested_fields: list[str] = Field(default_factory=list,max_length=24)
    time_scope: str = Field(default='',max_length=200)
    is_continuation: bool = False
    title: str = Field(default='',max_length=10)
    questions: list[str] = Field(default_factory=list,max_length=2)


class GapDecision(BaseModel):
    """根据真实覆盖和核验拒因提出后续查询，不用模型声明替代字段证据。"""
    steps: list[CompanyStep] = Field(default_factory=list,max_length=6)
    gaps: list[str] = Field(default_factory=list,max_length=24)
    unavailable: list[str] = Field(default_factory=list,max_length=12)
    questions: list[str] = Field(default_factory=list,max_length=2)
    continue_research: bool = False


class IdentityCandidate(BaseModel):
    """名称候选只是提议；连续身份与区分信息核验通过后才可供确认。"""
    name: str = Field(min_length=2, max_length=200)
    source_id: str = Field(min_length=1, max_length=64)
    identity_quote: str = Field(min_length=2, max_length=1500)
    alias_quote: str = Field(default='', max_length=1500)
    address: str = Field(default='', max_length=200)
    address_quote: str = Field(default='', max_length=1500)
    industry: str = Field(default='', max_length=120)
    industry_quote: str = Field(default='', max_length=1500)


class IdentityBatch(BaseModel):
    """名称查证输出；没有可靠身份原文时返回空候选，不从模型常识补全。"""
    candidates: list[IdentityCandidate] = Field(default_factory=list, max_length=8)
