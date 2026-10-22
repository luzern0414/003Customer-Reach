"""网站指引：每个数据源能提供什么、如何访问、访问间隔、重试策略与质量约束。

用途：
- 工具执行：`retry_policy()` 决定失败后是否重试、重试几次、退避多久；
- 模型规划：`planner_brief()` 把来源能力与约束写进提示，避免让模型去检索不提供该信息的网站；
- 质量门禁：`quality_rules` 与解析器、`tender_models` 的校验一致；
- 设置页“网站指引”展示同一份数据（GET /api/site-guides）。
"""
import re
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, Field

RETRYABLE = {'timeout', 'error', 'search_failed', 'bad_output', 'HTTPError', 'URLError', 'ConnectError', 'ReadTimeout', 'http_500', 'http_502',
             'http_503', 'http_504', 'empty_body', 'unavailable'}
NEVER_RETRY = {'site_verification_required', 'verification_required', 'auth_required', 'site_login_required', 'site_policy_unavailable',
               'channel_disabled', 'budget_exhausted', 'http_404', 'http_403', 'provider_rate_limited', 'bad_tool_output'}


class RetryPolicy(BaseModel):
    """失败重试策略：只对临时性错误重试；验证码、登录、限流、404不重试。"""
    max_attempts: int = Field(default=2, ge=1, le=4)
    backoff_seconds: list[float] = Field(default_factory=lambda: [2.0, 5.0])
    timeout_seconds: int = Field(default=60, ge=5, le=300)


class SiteGuide(BaseModel):
    """单个数据源的能力与约束。"""
    key: str
    name: str
    domains: list[str] = Field(default_factory=list)
    kind: Literal['aggregator', 'company_hub', 'original', 'search', 'registry']
    provides: list[str]
    access: Literal['opencli_http', 'opencli_browser', 'http', 'exa', 'http_then_exa', 'exa_then_http', 'mcp_http', 'mcp_stdio']
    login: Literal['none', 'member', 'verification_possible'] = 'none'
    min_interval_seconds: float = 1.0
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    trust: Literal['original', 'aggregated', 'third_party'] = 'aggregated'
    quality_rules: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


GUIDES: list[SiteGuide] = [
    SiteGuide(key='bidresearch',name='公开采购检索',kind='search',access='mcp_stdio',
              provides=['软件/AI 等关键词采购公告','已读公告正文与日期','原文标注的买方、供应商与不同用途金额'],
              retry=RetryPolicy(max_attempts=1,timeout_seconds=90),
              quality_rules=['全文优先，列表不当正文','已核验日期按时间范围过滤，日期未知标待核实','重复转载保留来源但仅展示一条公告'],
              cautions=['默认公共资源与必联网；七站能力不表示七站均取得正文','REA 浏览器来源需单独启用','失败在同任务复用，明确恢复才重试']),
    SiteGuide(key='qcc_mcp',name='企查查授权企业资料',domains=['agent.qcc.com'],kind='registry',access='mcp_http',
              provides=['企业基本工商资料','企业精确名称与信用代码','经营范围和国标行业'],
              retry=RetryPolicy(max_attempts=1,timeout_seconds=55),
              quality_rules=['字段以真实 JSON 路径引用','股东等其他主体字段不作为本公司资料','人员和营收缺报告期不保存'],
              cautions=['凭据仅从服务端读取','模糊查询先确认主体，不能按简称合并法人']),
    SiteGuide(key='qianlima', name='千里马', domains=['qianlima.com'], kind='aggregator', access='opencli_http',
              provides=['招标/采购公告标题', '发布时间', '地区', '预算'], retry=RetryPolicy(max_attempts=3, timeout_seconds=120),
              quality_rules=['列表无采购人/中标人时角色记为待核实', '详情页正文由脚本加载，读取走Exa已索引版本'],
              cautions=['直接访问详情页频繁会出现人机验证，不绕过', '会员遮挡字段（****、点击查看）不取']),
    SiteGuide(key='chinabidding', name='中国采购与招标网', domains=['chinabidding.com.cn'], kind='aggregator', access='opencli_http',
              provides=['公告标题', '公告类型', '发布时间'], retry=RetryPolicy(max_attempts=3, timeout_seconds=120),
              quality_rules=['无买方/中标方字段，只能作为待核实线索或按标题开头机构判定采购方']),
    SiteGuide(key='ebnew', name='必联网', domains=['ebnew.com', 'ss.ebnew.com'], kind='aggregator', access='opencli_http',
              provides=['公告标题', '采购方式', '产品', '地区', '企业库（性质/行业/注册资本/主营）'], retry=RetryPolicy(max_attempts=3, timeout_seconds=120)),
    SiteGuide(key='yfbzb_public', name='乙方宝公开页', domains=['yfbzb.com'], kind='aggregator', access='opencli_http',
              provides=['招标公告标题', '采购人', '发布时间'], retry=RetryPolicy(max_attempts=3, timeout_seconds=120),
              cautions=['会员控制台详情消耗每日额度，必须用户同意后才可读取']),
    SiteGuide(key='qianlima_hub', name='千里马系企业招投标主页', domains=['anfangzhaobiao.com', 'tujianzhaobiao.com', 'dianlizhaobiao.com', 'dlnyzb.com'],
              kind='company_hub', access='http_then_exa', min_interval_seconds=1.0,
              provides=['企业发布的招标公告列表（/1/）', '中标公告列表（/2/）', '合作单位：合作乙方=供应商、合作甲方=客户（/4/）',
                        '竞争对手：共同竞标公司（/5/）', '工商信息（/6/）'],
              quality_rules=['页面标题必须含目标企业全称才采用', '“潜在竞争对手”是行业排行，不作为竞争对手', '次数为招投标统计，不是交易金额'],
              cautions=['企业主页slug无法由企业名构造，只能经检索或记忆发现']),
    SiteGuide(key='cbi360', name='建设通', domains=['cbi360.net'], kind='company_hub', access='http_then_exa',
              provides=['企业中标业绩（项目/地区/金额范围）', '业主页：常合作供应商（次数/累计金额/最近时间）、历史发包', '工商信息（官网/电话/邮箱）'],
              quality_rules=['金额范围（1000万以下）不是精确金额', '匿名化采购方（某大学）不作为客户名称']),
    SiteGuide(key='shuidi', name='水滴标讯', domains=['biaoxun.shuidi.cn'], kind='company_hub', access='http_then_exa',
              provides=['逐条招投标记录，页面标注“招采单位/中标单位”角色', '预算金额', '工商摘要'],
              quality_rules=['只采用页面明确标注的角色']),
    SiteGuide(key='bidcenter', name='采招网', domains=['bidcenter.com.cn'], kind='company_hub', access='http_then_exa',
              provides=['企业招标/中标信息页'], cautions=['部分字段需登录，遮挡值不取']),
    SiteGuide(key='ccgp', name='中国政府采购网', domains=['ccgp.gov.cn'], kind='original', access='http_then_exa', trust='original',
              provides=['政府采购原始公告：采购人、代理机构、中标/成交供应商、金额'], login='verification_possible', min_interval_seconds=3.0,
              quality_rules=['原始公告优先于聚合站', '采购人/代理/中标供应商分开记录'], cautions=['频繁访问出现“访问过于频繁”，命中后停止该站检索']),
    SiteGuide(key='ggzy', name='全国公共资源交易平台', domains=['ggzy.gov.cn'], kind='original', access='opencli_browser', trust='original',
              provides=['工程/政府采购交易公告'], login='verification_possible', cautions=['出现验证码需用户在Edge中输入，Agent不自动识别']),
    SiteGuide(key='group_portal', name='集团自建采购平台（国家电网、中国能建、江苏交控）', domains=['ecp.sgcc.com.cn', 'ec.ceec.net.cn', 'zbcg.jchc.cn'],
              kind='original', access='http_then_exa', trust='original', min_interval_seconds=2.0,
              provides=['集团及下属单位自行发布的采购公告（标题、日期，标题开头即采购单位）'],
              retry=RetryPolicy(max_attempts=2, backoff_seconds=[5.0], timeout_seconds=150),
              quality_rules=['只在目标企业属于该集团时读取', '标题含企业全称或去掉“有限公司”后的名称才计入'],
              cautions=['目录共26个平台（清单来自开源项目BidMonitor-AI），其余需登录、滑动验证、robots禁止或无公开列表，不访问']),
    SiteGuide(key='x315', name='格兰德信用', domains=['x315.cn'], kind='registry', access='http_then_exa', trust='third_party',
              provides=['第三方整理的供应商名录（带页面日期）'], quality_rules=['名录日期可能较旧，必须展示页面日期']),
    SiteGuide(key='exa', name='Exa 全网检索', domains=['mcp.exa.ai'], kind='search', access='exa',
              provides=['全网检索摘要与已索引网页正文'], retry=RetryPolicy(max_attempts=3, backoff_seconds=[2.0, 5.0], timeout_seconds=60),
              cautions=['匿名访问额度有限，返回429时改用OpenCLI百度/搜狗检索；配置EXA_API_KEY可提高额度']),
    SiteGuide(key='opencli_search', name='百度/搜狗检索（OpenCLI）', domains=['baidu.com', 'sogou.com'], kind='search', access='opencli_browser',
              provides=['中文网页自然结果（剔除推广）'], login='verification_possible', min_interval_seconds=0.8,
              retry=RetryPolicy(max_attempts=2, backoff_seconds=[3.0], timeout_seconds=150),
              quality_rules=['只保留原始地址，搜索引擎跳转与推广链接丢弃'], cautions=['出现安全验证页即返回verification_required，不绕过']),
]
BY_KEY = {guide.key: guide for guide in GUIDES}


def guide_for_url(url: str) -> SiteGuide | None:
    """url为任意页面地址；按域名后缀匹配网站指引，没有匹配返回None。"""
    host = (urlparse(url or '').hostname or '').lower()
    for guide in GUIDES:
        if any(host == d or host.endswith('.' + d) for d in guide.domains): return guide
    return None


def retry_policy(source: str = '', url: str = '') -> RetryPolicy:
    """source为来源键或url为页面地址；返回对应重试策略，未登记的来源用默认（2次、退避2秒）。"""
    guide = BY_KEY.get(source) or guide_for_url(url)
    return guide.retry if guide else RetryPolicy()


def retryable(error: str) -> bool:
    """error为工具错误码；只有临时性错误可重试，验证码/登录/限流/404/输出不合格永不重试。"""
    if not error or error in NEVER_RETRY: return False
    return error in RETRYABLE or bool(re.match(r'http_5\d\d', error))


def planner_brief() -> str:
    """返回给规划/补查模型的来源能力说明：哪些信息已由招投标模块覆盖，哪些需要模型检索官网/报告。"""
    covered = '；'.join(f"{g.name}：{'、'.join(g.provides[:3])}" for g in GUIDES if g.kind in {'aggregator', 'company_hub'})
    return ('\n网站能力指引（是否已调用及取得信息以本轮实际结果为准）：' + covered + '。'
            '模型规划应聚焦：企业官网（主营、产品、联系方式）、年报/招股书（年度供应商与客户金额）、政府采购原始公告（ccgp.gov.cn）。'
            '聚合站遮挡字段不可作为事实；“次数”不是金额；未取得的信息写“未取得”，不推测。')
