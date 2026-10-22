"""API及Agent结构化契约；字段约束在入库前执行。"""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
from .source_catalog import SearchChannel

STAGES = ('new', 'review', 'contacted', 'nurture', 'converted', 'invalid')


class MessageInput(BaseModel):
    """对话提交，client_token用于避免网络重试导致重复任务。"""
    content: str = Field(min_length=1, max_length=20000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    client_token: str = Field(min_length=8, max_length=100)
    query_mode: Literal['auto', 'company_query', 'buyer_discovery', 'company_match'] = 'auto'
    company_id: str | None = Field(default=None, max_length=64)


class Product(BaseModel):
    """用户资料明确提供的产品，缺失规格价格保留为空。"""
    name: str
    model: str | None = None
    specifications: str | None = None
    price: str | None = None
    source: str = '用户提供'


class CompanyResearchInput(BaseModel):
    """企业补查保持任务幂等；空会话建立新研究，空正文采用明确补查范围。"""
    model_config = ConfigDict(extra='forbid')
    client_token: str = Field(min_length=8, max_length=100)
    conversation_id: str | None = Field(default=None, max_length=64)
    content: str = Field(default='', max_length=20000)


class LeadAnalysisInput(BaseModel):
    """显式分析使用指定对话的产品画像，client_token重试不重复任务。"""
    model_config = ConfigDict(extra='forbid')
    conversation_id: str = Field(min_length=1,max_length=64)
    client_token: str = Field(min_length=8,max_length=100)
    content: str = Field(default='',max_length=2000)


class IdentityConfirmationInput(BaseModel):
    """同任务确认主体；原候选版本、同会话和幂等token由服务再次校验。"""
    model_config = ConfigDict(extra='forbid')
    conversation_id: str = Field(min_length=1, max_length=64)
    resolution_revision: int = Field(ge=1)
    client_token: str = Field(min_length=8, max_length=100)
    candidate_id: str | None = Field(default=None, max_length=64)
    name: str = Field(default='', max_length=200)
    context: str = Field(default='', max_length=500)


class ProductProfile(BaseModel):
    """分析后的公司画像与获客条件；questions为空才执行研究。"""
    company_name: str | None = None
    products: list[Product] = Field(default_factory=list)
    region: str = '深圳'
    target_buyers: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    summary: str
    questions: list[str] = Field(default_factory=list)


class Fact(BaseModel):
    """必须能在工具正文找到的字段值和逐字证据。"""
    field: Literal['name', 'legal_name', 'address', 'phone', 'email', 'website', 'wechat', 'contact_name', 'contact_position', 'credit_code', 'registry_status', 'industry', 'categories', 'brands', 'headcount', 'revenue', 'procurement', 'supplier', 'purchase_price', 'frequency', 'buyer_role']
    value: str = Field(min_length=1, max_length=2000)
    source_id: str
    quote: str = Field(min_length=3, max_length=1500)

    scope: str = ''
    effective_date: str = ''


class ProcurementSignal(BaseModel):
    """采购信号必须绑定真实买方、公告阶段和原文截止日期；中标历史不计当前意向。"""
    source_id: str
    buyer: str
    participant_role: Literal['buyer','supplier','agency']
    stage: Literal['open','awarded','closed','historical']
    deadline: str = Field(default='', max_length=30)
    quote: str = Field(min_length=3, max_length=1500)
    buyer_quote: str = Field(default='',max_length=1500)
    deadline_quote: str = Field(default='',max_length=1500)


class Candidate(BaseModel):
    """Agent提议的研究候选，事实逐项校验后才能保存。"""
    display_name: str = Field(min_length=2, max_length=200)
    city: str = Field(max_length=100)
    facts: list[Fact] = Field(min_length=1, max_length=22)
    matched_products: list[str] = Field(default_factory=list, max_length=10)
    match_reason: str = Field(max_length=2000)
    buyer_role: Literal['dealer','retailer','mall','project_buyer','manufacturer','unknown'] = 'unknown'
    procurement_signal: ProcurementSignal | None = None


class LeadInput(BaseModel):
    """CRM人工编辑；不把人工输入伪装成已验证网页事实。"""
    model_config = ConfigDict(extra='forbid')
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=200)
    status: Literal['new', 'review', 'contacted', 'nurture', 'converted', 'invalid'] | None = None
    owner: str | None = Field(default=None, max_length=100)
    next_followup: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=100)
    wechat: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=2000)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_position: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = Field(default=None, max_length=20)
    buyer_role: Literal['dealer','retailer','mall','project_buyer','manufacturer','unknown'] | None = None


class FollowupInput(BaseModel):
    """一次销售跟进，空白或过长内容拒绝。"""
    content: str = Field(min_length=1, max_length=5000)
    kind: Literal['note', 'phone', 'visit', 'email'] = 'note'

    @field_validator('content')
    @classmethod
    def nonblank(cls,value: str) -> str:
        """value是已校验长度的正文；空白拒绝，非空保留原排版，失败返回422。"""
        if not value.strip():raise ValueError('跟进内容不能为空白')
        return value


class SettingsInput(BaseModel):
    """允许修改的非敏感运行设置；不接受密钥和任意模型名称。"""
    model_config = ConfigDict(extra='forbid')
    company_name: str = Field(default='', max_length=200)
    default_region: str = Field(default='深圳', min_length=1, max_length=100)
    max_leads: int = Field(default=8, ge=1, le=20)
    max_searches: int = Field(default=8, ge=1, le=16)
    max_reads: int = Field(default=10, ge=0, le=24)
    model: Literal['gpt-6-luna'] = 'gpt-6-luna'
    enabled_channels: list[SearchChannel | Literal['knowledge']] = Field(default_factory=lambda:['knowledge','official','directory','procurement'])
    max_seconds: int = Field(default=600, ge=60, le=1800)
    max_model_calls: int = Field(default=32, ge=1, le=100)
    max_model_tokens: int = Field(default=180000, ge=4000, le=1000000)
    max_candidate_searches: int = Field(default=3, ge=1, le=8)
    research_max_rounds: int = Field(default=3, ge=1, le=8)
    research_pages_per_query: int = Field(default=4, ge=1, le=8)
    research_read_concurrency: int = Field(default=2, ge=1, le=4)
    research_chunks_per_source: int = Field(default=6, ge=1, le=16)
    research_no_gain_rounds: int = Field(default=2, ge=1, le=4)
    tender_enabled: bool = True
    tender_detail_reads: int = Field(default=6, ge=0, le=16)
    tender_reuse_hours: int = Field(default=24, ge=0, le=720)
    qcc_enabled: bool = True
    max_qcc_calls: int = Field(default=4, ge=0, le=12)
    bidresearch_enabled: bool = True
    max_bidresearch_calls: int = Field(default=2, ge=0, le=6)
    bidresearch_max_requests: int = Field(default=80, ge=0, le=80)
    bidresearch_max_details: int = Field(default=4, ge=0, le=12)
    bidresearch_timeout: int = Field(default=90, ge=15, le=180)
    bidresearch_browser: bool = False


class BrowserSettingsInput(BaseModel):
    """固定公开浏览器读取配置，不允许自定义脚本、命令或日常浏览器profile路径。"""
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    preferred_backend: Literal['auto','opencli','playwright'] = 'auto'
    max_pages: int = Field(default=3, ge=1, le=8)
    max_chars: int = Field(default=40000, ge=2000, le=100000)
    command_timeout: int = Field(default=90, ge=15, le=120)


class BrowserReadInput(BaseModel):
    """用户明确输入的公开页面诊断；不包含任意代码、凭据或执行路径。"""
    url: str = Field(min_length=8, max_length=2000)
    backend: Literal['auto','opencli','playwright'] = 'auto'


class ResearchStep(BaseModel):
    """每个模型决策只请求一个明确的数据渠道，工具schema禁止任意执行代码。"""
    channel: SearchChannel
    query: str = Field(min_length=3, max_length=500)
    purpose: str = Field(min_length=2, max_length=200)


class ResearchPlan(BaseModel):
    """ICP导出的有界计划；搜索步骤由图按顺序执行、缺字段时拓展新渠道。"""
    target_roles: list[Literal['dealer','retailer','mall','project_buyer','manufacturer']] = Field(min_length=1, max_length=5)
    excluded_roles: list[str] = Field(default_factory=lambda:['manufacturer'])
    steps: list[ResearchStep] = Field(min_length=1, max_length=6)


class CandidateBatch(BaseModel):
    """来源内候选及缺口；失败不制造电话或采购数据。"""
    candidates: list[Candidate] = Field(default_factory=list, max_length=8)
    missing_fields: list[Literal['buyer_role','phone','email','website','wechat','contact_name','address','categories','procurement']] = Field(default_factory=list)


class RoleCorrection(BaseModel):
    """角色协议错误的一次纠正；只允许枚举变化，不能修改已经取得的原文事实。"""
    buyer_role: Literal['dealer','retailer','mall','project_buyer','manufacturer','unknown']


class FeedbackInput(BaseModel):
    """用户反馈更新知识有效性/角色，正文不等同来源。"""
    kind: Literal['relevant','nonbuyer','incorrect','stale']
    content: str = Field(default='', max_length=2000)


class MemoryInput(BaseModel):
    """用户明确提供的长期记忆；不接受任意命名空间。"""
    kind: Literal['company','preference','exclusion']
    content: str = Field(min_length=1, max_length=4000)


class KnowledgeInput(BaseModel):
    """用户第一方知识手工补充，始终标为用户提供。"""
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)


class ResearchResult(BaseModel):
    """最终业务结果与Markdown分开校验；只允许实际CRM ID，不把回答当事实。"""
    saved_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    answer: str = ''
    warnings: list[str] = Field(default_factory=list)


class MemoryCandidate(BaseModel):
    """画像沉淀只来自用户资料，不允许模型回答或网页指令成为公司产品。"""
    profile: ProductProfile
    source: Literal['用户对话与产品文件'] = '用户对话与产品文件'
    conversation_id: str
    updated_at: str
