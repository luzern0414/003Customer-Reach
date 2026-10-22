"""招投标工具的结构化契约：工具输出、待保存记录与研究摘要均用 Pydantic 校验。

- 工具输出（PlatformSearchOutput / WebSearchOutput / PageReadOutput）：Ledger 执行后校验，不合格记为 bad_tool_output 且不进入后续流程；
- 记录提议（TenderRecordProposal / TenderRelationProposal）：保存前逐条校验，遮挡名称、非法日期、非 http 地址被拒绝并计数；
- 研究摘要（CompanyResearchSummary）：由数据库确定性生成，供回答模型、后续任务与界面复用。
"""
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator

MASK = re.compile(r'\*{3,}|点击查看|登录查看|立即查看|开通会员')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _date(value: str) -> str:
    """value为日期字符串；只接受YYYY-MM-DD，其他置空。"""
    return value if DATE.match(value or '') else ''


class PlatformNotice(BaseModel):
    """平台检索返回的一条公告（未经详情确认）。"""
    source: str = ''
    source_label: str = ''
    notice_type: str = ''
    title: str = Field(min_length=2, max_length=500)
    published_at: str = ''
    buyer: str = ''
    winner: str = ''
    agency: str = ''
    amount: str = ''
    budget: str = ''
    role: str = ''
    region: str = ''
    summary: str = ''
    url: str = ''

    _clean_date = field_validator('published_at')(classmethod(lambda cls, v: _date(v)))


class PlatformSearchOutput(BaseModel):
    """平台检索工具输出。"""
    notices: list[PlatformNotice] = Field(default_factory=list)
    status: str = ''
    error: str = ''
    message: str = ''
    sources: list[dict] = Field(default_factory=list)


class WebRow(BaseModel):
    """全网检索一行（Exa 或 OpenCLI 百度/搜狗）。"""
    title: str = Field(default='', max_length=500)
    url: str = Field(pattern=r'^https?://', max_length=2000)
    published_at: str = ''
    text: str = Field(default='', max_length=4000)
    query: str = ''
    engine: str = ''

    _clean_date = field_validator('published_at')(classmethod(lambda cls, v: _date(v)))


class WebSearchOutput(BaseModel):
    """全网检索工具输出；provider 标明实际使用 exa 还是 opencli。"""
    rows: list[WebRow] = Field(default_factory=list)
    provider: str = 'exa'
    exa_error: str = ''
    error: str = ''
    sources: list[dict] = Field(default_factory=list)


class Article(BaseModel):
    """企业主页公告列表中的一条。"""
    title: str = Field(min_length=1, max_length=500)
    url: str = ''
    published_at: str = ''


class PageReadOutput(BaseModel):
    """页面读取工具输出；text 为空时必须带 error。"""
    text: str = ''
    title: str = ''
    articles: list[Article] = Field(default_factory=list)
    info: dict[str, str] = Field(default_factory=dict)
    published_at: str = ''
    via: str = ''
    error: str = ''
    http_error: str = ''
    sources: list[dict] = Field(default_factory=list)


class TenderItem(BaseModel):
    """公告物资清单行。"""
    name: str = Field(min_length=1, max_length=80)
    spec: str = Field(default='', max_length=160)
    quantity: str = Field(default='', max_length=20)
    unit: str = Field(default='', max_length=10)


class TenderRecordProposal(BaseModel):
    """待保存的招投标记录；角色、置信度为枚举，名称与引文不得含遮挡值。"""
    title: str = Field(min_length=2, max_length=300)
    role: Literal['buyer', 'winner', 'candidate', 'agency', 'related', 'mentioned']
    confidence: Literal['detail', 'listing', 'index']
    published_at: str = ''
    buyer_name: str = Field(default='', max_length=200)
    winner_names: list[str] = Field(default_factory=list, max_length=20)
    candidate_names: list[str] = Field(default_factory=list, max_length=30)
    agency_name: str = Field(default='', max_length=200)
    amount: str = Field(default='', max_length=60)
    budget: str = Field(default='', max_length=60)
    region: str = Field(default='', max_length=60)
    items: list[TenderItem] = Field(default_factory=list, max_length=40)
    url: str = Field(default='', max_length=2000)
    quote: str = Field(default='', max_length=1200)

    _clean_date = field_validator('published_at')(classmethod(lambda cls, v: _date(v)))

    @field_validator('buyer_name', 'agency_name')
    @classmethod
    def no_mask(cls, value: str) -> str:
        """遮挡或非机构值拒绝。"""
        if value and MASK.search(value): raise ValueError('masked_name')
        return value

    @field_validator('winner_names', 'candidate_names')
    @classmethod
    def no_mask_list(cls, value: list[str]) -> list[str]:
        """名单中的遮挡值剔除。"""
        return [v for v in value if v and not MASK.search(v)]

    @field_validator('url')
    @classmethod
    def http_url(cls, value: str) -> str:
        """地址只接受http(s)，其他置空。"""
        return value if re.match(r'^https?://', value or '') else ''


class TenderRelationProposal(BaseModel):
    """待保存的对手方汇总。"""
    name: str = Field(min_length=2, max_length=200)
    kind: Literal['customer', 'supplier', 'competitor', 'agency']
    basis: Literal['records', 'platform_stats', 'third_party_list']
    count: int = Field(ge=0, le=100000)

    @field_validator('name')
    @classmethod
    def no_mask(cls, value: str) -> str:
        """遮挡名称拒绝。"""
        if MASK.search(value): raise ValueError('masked_name')
        return value


class Counterparty(BaseModel):
    """摘要中的对手方。"""
    name: str
    count: int
    basis: list[str] = Field(default_factory=list)


class CompanyResearchSummary(BaseModel):
    """单家企业的结构化研究摘要（数据库确定性生成）。"""
    company_id: str
    name: str
    data_as_of: str = ''
    reused: bool = False
    registration: dict[str, str] = Field(default_factory=dict)
    facts: dict[str, str] = Field(default_factory=dict)
    purchases: int = 0
    latest_purchase: str = ''
    recent_purchases: list[str] = Field(default_factory=list, max_length=8)
    top_items: list[str] = Field(default_factory=list, max_length=8)
    wins: int = 0
    candidates: int = 0
    customers: list[Counterparty] = Field(default_factory=list, max_length=10)
    suppliers: list[Counterparty] = Field(default_factory=list, max_length=10)
    competitors: list[Counterparty] = Field(default_factory=list, max_length=8)
    annual_suppliers: int = 0
    annual_customers: int = 0
    sources: int = 0
    gaps: list[str] = Field(default_factory=list, max_length=12)
