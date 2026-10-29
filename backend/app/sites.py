"""数据来源注册表。每个站点给出检索方式（自拼 URL 交给 capture，或 LuzCrawl 平台站内搜索）、
公告详情链接规则与必要的详情地址改写。新增站点前先用 LuzCrawl 实测列表与详情正文。"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import quote, urlencode

from .config import LUZ_CRAWL

log = logging.getLogger('dealradar.sites')


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    kind: str                       # procurement / business / web
    detail: str                     # 详情链接正则
    template: str = ''              # 列表 URL 模板，{q} 关键词，{start}/{end} 日期
    platform: str = ''              # 无模板时使用 LuzCrawl 平台站内搜索
    rewrite: tuple = ()             # 详情地址改写 (pattern, repl)
    login: bool = False             # 可能需要用户登录
    default_on: bool = True         # 未在设置中开关时是否启用
    by_company: bool = False        # 支持按企业名全文检索（企业名多出现在正文而非标题）
    max_days: int = 0               # 单次检索的最长时间跨度，0 为不限
    note: str = ''
    custom: bool = False            # 用户在数据源页面新增的站点
    pages: int = 1                  # 模板含 {page}/{offset} 时可翻的页数
    page_size: int = 10             # {offset} 每页步长（必应 first=1、11、21…）
    web: bool = False               # 搜索引擎：结果指向其他网站，用于发现新来源
    region: str = ''                # 省级、城市平台所在地区；需求含该地区时自动加入
    origin: str = 'builtin'         # builtin / luzcrawl / custom
    domains: tuple = ()             # 站点域名；非空时详情链接须属于这些域名
    aggregator: bool = False        # 招标聚合站：转载各平台公告，正文常有删减

    def search_url(self, query: str, days: int, fulltext: bool = False, end_offset: int = 0, page: int = 1) -> str:
        """检索 [今天-end_offset-days, 今天-end_offset] 区间；fulltext 用于按企业名检索。"""
        if not self.template:
            return ''
        end = date.today() - timedelta(days=end_offset)
        start = end - timedelta(days=max(days, 1))
        values = {'q': quote(query), 'start': start.strftime('%Y:%m:%d'), 'end': end.strftime('%Y:%m:%d'),
                  'start_date': start.isoformat(), 'end_date': end.isoformat(), 'st': '2' if fulltext else '1',
                  'page': str(page), 'offset': str((page - 1) * self.page_size + 1)}
        return re.sub(r'\{(\w+)\}', lambda m: values.get(m[1], m[0]), self.template)

    def is_detail(self, url: str) -> bool:
        if self.domains:
            host = domain_of(url)
            if not any(host == d or host.endswith('.' + d) for d in self.domains):
                return False
        return bool(re.search(self.detail, url))

    def detail_url(self, url: str) -> str:
        return re.sub(self.rewrite[0], self.rewrite[1], url) if self.rewrite else url


_CCGP = 'https://search.ccgp.gov.cn/bxsearch?' + urlencode({
    'bidSort': '0', 'pinMu': '0', 'bidType': '0', 'dbselect': 'bidx',
    'timeType': '6', 'pppStatus': '0'}) + '&page_index={page}&searchtype={st}&kw={q}&start_time={start}&end_time={end}'

# 2026-10-28 实测：ccgp、ggzy 列表与详情免登录可读；采招网详情对非会员打码；百度结果页含爱企查企业卡
# （法定代表人、注册资本、成立时间、经营状态、地址、经营范围）与百科摘要，免登录。
# 千里马（URL 参数在 SPA 中不生效）、中国招标投标公共服务平台与中国采购与招标网（忽略关键词）、
# 必联网（结果无链接）、剑鱼（列表未渲染）暂不接入。
# 必应全网检索返回各招采站的公告直链（政府采购网、各地公共资源交易平台、央企采购平台等），百度结果为跳转链接且夹杂文库，未采用；
# 中国招标网触发验证、中国招标投标网无可用站内搜索；360 搜索结果为跳转链接、搜狗结果以公众号为主，均未采用。
# 必应 site: 限定可按网站类型检索（gov.cn、央企采购平台、edu.cn），并可翻页（first=11、21）。
# ccgp 自定义时间跨度最长一年（3 年返回 0 条），按企业检索时分年查询；ggzy 只检索标题，不用于按企业检索。
SITES: dict[str, Site] = {site.id: site for site in [
    Site('ccgp', '中国政府采购网', 'procurement', r'ccgp\.gov\.cn/cggg/', template=_CCGP, by_company=True, max_days=365, pages=3,
         note='全国政府采购公告，列表含采购人与公告类型'),
    Site('ggzy', '全国公共资源交易平台', 'procurement', r'ggzy\.gov\.cn/information/deal/html/a/', platform='ggzy',
         rewrite=(r'/html/a/', '/html/b/'), note='汇集各省公共资源交易公告'),
    Site('bing', '全网招标检索', 'procurement', r'^https?://(?!([\w-]+\.)*(bing|microsoft|msn|live)\.com)',
         template='https://cn.bing.com/search?q={q}+%E6%8B%9B%E6%A0%87%E5%85%AC%E5%91%8A&first={offset}', by_company=True,
         pages=3, web=True,
         note='必应检索各地政府采购网、公共资源交易平台、央企采购平台的公告'),
    Site('bing_gov', '政府网站招标检索', 'procurement', r'^https?://([\w-]+\.)*gov\.cn/',
         template='https://cn.bing.com/search?q={q}+%E6%8B%9B%E6%A0%87%E5%85%AC%E5%91%8A+site%3Agov.cn&first={offset}',
         by_company=True, pages=3, web=True, note='各省市政府采购网与公共资源交易平台（gov.cn）'),
    Site('bing_soe', '央企采购平台检索', 'procurement', r'^https?://(?!([\w-]+\.)*(bing|microsoft)\.com)',
         template='https://cn.bing.com/search?q={q}+%E9%87%87%E8%B4%AD%E5%85%AC%E5%91%8A+(site%3Aecp.sgcc.com.cn+OR+site%3Abidding.csg.cn+OR+site%3Ab2b.10086.cn+OR+site%3Acaigou.chinatelecom.com.cn+OR+site%3Awww.chinaunicombidding.cn+OR+site%3Abuy.cnooc.com.cn+OR+site%3Abid.powerchina.cn+OR+site%3Aec.chng.com.cn)&first={offset}',
         by_company=True, pages=2, web=True, note='国家电网、南方电网、三大运营商、中海油、中国电建、华能等采购平台'),
    Site('bing_edu', '高校科研采购检索', 'procurement', r'^https?://([\w-]+\.)*(edu\.cn|cas\.cn)/',
         template='https://cn.bing.com/search?q={q}+%E9%87%87%E8%B4%AD%E5%85%AC%E5%91%8A+(site%3Aedu.cn+OR+site%3Acas.cn)&first={offset}',
         pages=2, web=True, note='高校与中科院各院所的采购公告'),
    Site('bidcenter', '采招网', 'procurement', r'bidcenter\.com\.cn/news-\d+',
         template='https://search.bidcenter.com.cn/search?keywords={q}&mod=0', login=True, default_on=False, by_company=True,
         note='覆盖国企与企业采购；采购人等字段需会员登录后可见'),
    Site('baidu', '百度企业信息', 'business', r'^$', template='https://www.baidu.com/s?wd={q}',
         note='企业信息卡（爱企查数据）与百科摘要'),
    Site('aiqicha', '爱企查', 'business', r'aiqicha\.baidu\.com/company_detail_',
         template='https://aiqicha.baidu.com/s?q={q}', login=True, default_on=False,
         note='完整工商信息，需在 Edge 中登录百度账号'),
]}


# LuzCrawl 目录中实测通过的采购入口（2026-10-29：198 个候选实测，“空调”“电梯”两词复验）。
# 检索交给 LuzCrawl 站内搜索：地址模板、站内表单或逐条点击结果行，候选已按关键词过滤。
_PLACES = ('北京', '天津', '上海', '重庆', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江', '江苏', '浙江', '安徽', '福建',
           '江西', '山东', '河南', '湖北', '湖南', '广东', '广西', '海南', '四川', '贵州', '云南', '西藏', '陕西', '甘肃',
           '青海', '宁夏', '新疆', '广州', '深圳', '宁波', '厦门', '大连', '青岛', '烟台', '中山', '佛山')
# 城市平台同时属于所在省份
_PROVINCE = {'广州': '广东', '深圳': '广东', '中山': '广东', '宁波': '浙江', '厦门': '福建', '大连': '辽宁', '青岛': '山东', '烟台': '山东', '佛山': '广东'}
_catalog_cache: dict = {'mtime': None, 'sites': {}}


def _region(name: str) -> str:
    return next((place for place in _PLACES if place in name), '')


def _library() -> dict[str, dict] | None:
    """LuzCrawl 网站库（id → 条目）；不可读时返回 None（不按实测结论过滤）。"""
    try:
        library = json.loads((LUZ_CRAWL / 'references' / 'site-library.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return {str(s.get('id')): s for s in library.get('sites') or []}


_AGGREGATOR_KIND = re.compile(r'aggregator|聚合|招标目录|b2b', re.I)


def luzcrawl_sites() -> dict[str, Site]:
    """读取 LuzCrawl 目录中站内搜索实测通过的采购入口；文件缺失或损坏时返回空，研究只用其余站点。"""
    path = LUZ_CRAWL / 'opencli' / 'catalog.json'
    library = LUZ_CRAWL / 'references' / 'site-library.json'
    try:
        mtime = (path.stat().st_mtime, library.stat().st_mtime if library.exists() else 0)
        if _catalog_cache['mtime'] == mtime:
            return _catalog_cache['sites']
        entries = json.loads(path.read_text(encoding='utf-8')).get('sites') or []
    except (OSError, ValueError) as exc:
        log.warning('LuzCrawl 目录不可用：%s', exc)
        return {}
    library = _library()
    sites = {}
    for entry in entries:
        sid, name = str(entry.get('id', '')), str(entry.get('name', ''))
        if entry.get('category') != 'procurement' or sid in SITES or not re.fullmatch(r'[A-Za-z0-9-]{2,48}', sid) or not name:
            continue
        info = (library or {}).get(sid) or {}
        if library is not None and (info.get('verification') or {}).get('search') != 'verified':
            continue
        region = _region(name)
        domains = tuple(str(d).lower().removeprefix('www.') for d in entry.get('domains') or [] if re.fullmatch(r'[\w.-]+', str(d)))
        if not domains:
            continue
        sites[sid] = Site(sid, name[:100], 'procurement', str(entry.get('detail') or r'^https?://'), platform=sid,
                          default_on=not region, region=region, origin='luzcrawl', domains=domains,
                          aggregator=bool(_AGGREGATOR_KIND.search(str(info.get('kind', '')))))
    _catalog_cache.update(mtime=mtime, sites=sites)
    return sites


_OFFICIAL = re.compile(r'\.(gov|edu|mil|ac)\.cn$|(^|\.)cas\.cn$')


def source_tier(url: str, site: Site | None) -> int:
    """来源层级：3 官方原文（政府、高校、科研院所、军队域名与采购单位自己的平台），1 聚合转载，2 其余。"""
    if _OFFICIAL.search(domain_of(url)):
        return 3
    if site is None or site.web:
        return 2
    if site.aggregator:
        return 1
    return 3 if site.origin == 'luzcrawl' or site.id in ('ccgp', 'ggzy') else 2


def regional_sites(regions: list[str], switches: dict) -> list[Site]:
    """需求所含地区对应的省级、城市平台；用户在数据源页面关闭的不加入。"""
    wanted = {_PROVINCE.get(r, r) for r in (_region(region) for region in regions) if r} | {r for r in map(_region, regions) if r}
    return [site for site in all_sites().values()
            if site.region and switches.get(site.id) is not False
            and (site.region in wanted or _PROVINCE.get(site.region) in wanted)]


def from_custom(row) -> Site:
    return Site(row.id, row.name, row.kind, row.detail or r'^https?://', template=row.template if row.mode == 'template' else '',
                platform=row.domain if row.mode == 'site_search' else '', login=bool(row.login), by_company=bool(row.by_company),
                note=row.note, custom=True, origin='custom')


def all_sites() -> dict[str, Site]:
    """内置站点 + LuzCrawl 采购入口 + 用户新增站点（数据库）；ID 重复时以前者为准。"""
    from sqlalchemy import select

    from .db import CustomSite, Session
    with Session() as db:
        custom = {row.id: from_custom(row) for row in db.scalars(select(CustomSite).order_by(CustomSite.created_at))}
    merged = {**SITES, **{k: v for k, v in luzcrawl_sites().items() if k not in SITES}}
    return {**merged, **{k: v for k, v in custom.items() if k not in merged}}


def get_site(site_id: str) -> Site | None:
    return all_sites().get(site_id)


def enabled(kind: str, settings: dict) -> list[Site]:
    switches = settings.get('sources') or {}
    return [site for site in all_sites().values() if site.kind == kind and switches.get(site.id, site.default_on)]


def domain_of(url: str) -> str:
    match = re.match(r'^https?://([^/:?#]+)', url or '')
    return match[1].lower() if match else ''


def known_domain(url: str) -> bool:
    """该链接所在网站已登记为数据源（内置站点的详情规则或自定义站点的域名）。"""
    domain = domain_of(url)
    for site in all_sites().values():
        if site.web:
            continue
        if site.is_detail(url) or (site.custom and site.platform and domain.endswith(site.platform.removeprefix('www.'))):
            return True
    return False


def site_of(url: str) -> Site | None:
    # 具体站点优先，搜索引擎类（结果指向各网站）最后
    sites = sorted((s for s in all_sites().values() if s.kind == 'procurement'), key=lambda s: s.web)
    return next((site for site in sites if site.is_detail(url)), None)
