"""模型结构化输出。所有事实字段都带 quote（资料原文片段），入库前逐条核验。"""
from typing import Literal

from pydantic import BaseModel, Field

NoticeKind = Literal['intent', 'tender', 'change', 'candidate', 'award', 'contract', 'other']


class Plan(BaseModel):
    """理解用户需求后的研究计划。"""
    mode: Literal['find_buyers', 'company', 'chat'] = Field(
        description='find_buyers=描述产品找正在采购的买家；company=查询指定企业的采购、中标、上下游；chat=问答或追问已有结果，不需要检索')
    title: str = Field(description='12 字以内的任务标题，如“防火墙买家研究”“航天广通研究”')
    product: str = Field('', description='find_buyers：用户销售的产品与能力摘要')
    keywords: list[str] = Field(default_factory=list,
                                description='find_buyers：招标公告里采购方会使用的品目/产品词，2-6 个，短词优先')
    company: str = Field('', description='company：目标企业名称，尽量为全称')
    regions: list[str] = Field(default_factory=list, description='限定地区（省或市），无则空')
    days: int = Field(0, description='时间范围（天），用户未说明则 0')
    exclusions: list[str] = Field(default_factory=list, description='用户明确排除的对象或类型')


class Keywords(BaseModel):
    keywords: list[str] = Field(default_factory=list, description='招标公告中采购方使用的品目或设备名称，短词')


class ListRow(BaseModel):
    link: int = Field(description='资料中链接列表的编号')
    buyer: str = Field('', description='列表中写明的采购人/招标人名称，没有写明则空')
    kind: NoticeKind = 'other'
    published_on: str = Field('', description='YYYY-MM-DD')
    region: str = ''
    relevant: bool = Field(description='是否与研究目标相关')


class ListResult(BaseModel):
    rows: list[ListRow] = Field(default_factory=list)


class Party(BaseModel):
    name: str = Field(description='单位全称，与原文一致')
    quote: str = Field(description='包含该名称与其角色的原文片段')
    amount: float | None = Field(None, description='该单位中标/报价金额，单位元')


class Contact(BaseModel):
    person: str = ''
    phone: str = ''
    address: str = ''
    quote: str = Field('', description='包含联系人/电话的原文片段')


class NoticeExtract(BaseModel):
    """一篇招投标公告的结构化内容。"""
    is_notice: bool = Field(description='正文是否为一篇招投标/采购公告')
    title: str = ''
    kind: NoticeKind = 'other'
    project_code: str = ''
    published_on: str = Field('', description='YYYY-MM-DD')
    deadline: str = Field('', description='投标/响应截止时间，原文格式')
    region: str = ''
    budget: float | None = Field(None, description='预算或最高限价，单位元')
    budget_quote: str = ''
    amount: float | None = Field(None, description='中标/成交总金额，单位元')
    amount_quote: str = ''
    items: str = Field('', description='采购标的：品名、品牌型号、数量，100 字以内')
    items_quote: str = ''
    buyer: Party | None = None
    buyer_contact: Contact | None = None
    agent: Party | None = None
    winners: list[Party] = Field(default_factory=list)
    candidates: list[Party] = Field(default_factory=list, description='中标候选人（未定标）')


class ProfileField(BaseModel):
    value: str
    quote: str


class CompanyExtract(BaseModel):
    """工商与企业介绍页面的结构化内容；页面不是目标企业时 matched=false。"""
    matched: bool = Field(description='资料是否在描述目标企业本身')
    name: str = ''
    credit_code: ProfileField | None = None
    legal_person: ProfileField | None = None
    registered_capital: ProfileField | None = None
    founded_on: ProfileField | None = None
    business_status: ProfileField | None = None
    industry: ProfileField | None = None
    address: ProfileField | None = None
    website: ProfileField | None = None
    phone: ProfileField | None = None
    email: ProfileField | None = None
    scope: ProfileField | None = Field(None, description='经营范围或主营业务')


class Identity(BaseModel):
    """从工商检索结果中确认目标企业。"""
    names: list[str] = Field(default_factory=list, description='检索结果中与目标相符的企业全称，按匹配度排序')
    exact: bool = Field(description='是否有且仅有一家与目标完全对应')


class MatchItem(BaseModel):
    product: str
    fit: Literal['相关', '能力缺口', '待核验']
    evidence: str = Field(description='采购需求原文')
    judgement: str


class MatchAnalysis(BaseModel):
    items: list[MatchItem] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list, description='需要向客户确认的问题')
