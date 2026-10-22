"""企业标识：从已核验官网或经核对的官网候选中取得站点图标，本地缓存后供头像展示。

取图顺序：apple-touch-icon → 尺寸较大的 icon → 页头 logo 图片 → /favicon.ico。
官网候选必须在首页正文/标题中出现企业完整名或简称才采用；聚合平台、百科与工商查询站不作为官网。
失败结果记录检查时间，7天内不重复访问。
"""
import re
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
import httpx
from sqlalchemy import select
from .config import DATA
from .db import Session, now
from .company_models import Company, CompanyFact
from .observability import logger

LOG = logger('agent')
LOGO_DIR = DATA / 'logos'
MAX_BYTES = 400_000
RETRY_DAYS = 7
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ClientReach/0.3 (+logo)'}
IMAGE_TYPES = {'image/png': '.png', 'image/x-icon': '.ico', 'image/vnd.microsoft.icon': '.ico', 'image/jpeg': '.jpg',
               'image/svg+xml': '.svg', 'image/webp': '.webp', 'image/gif': '.gif'}
NOT_OFFICIAL = re.compile(r'qcc\.com|qichacha|aiqicha|tianyancha|qixin|baike|zhihu|1688\.com|cbi360|zhaobiao|qianlima|yfbzb|jianyu|ebnew|'
                          r'chinabidding|ccgp|ggzy|x315|dlnyzb|b2b|zhipin|liepin|51job|jobs\.|sohu|163\.com|sina|weixin|bilibili|douyin|gov\.cn|edu\.cn')


class IconParser(HTMLParser):
    """收集<link rel=icon>、<meta og:image>与带logo字样的<img>，并记录页面标题。"""

    def __init__(self):
        super().__init__()
        self.links, self.images, self.title, self._in_title = [], [], '', False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'link' and 'icon' in a.get('rel', '').lower() and a.get('href'):
            size = max([int(x) for x in re.findall(r'(\d+)x\d+', a.get('sizes', ''))] or [0])
            self.links.append((a['rel'].lower(), size, a['href']))
        elif tag == 'img' and a.get('src') and re.search('logo', ' '.join([a.get('src', ''), a.get('class', ''), a.get('alt', ''), a.get('id', '')]), re.I):
            self.images.append(a['src'])
        elif tag == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == 'title': self._in_title = False

    def handle_data(self, data):
        if self._in_title: self.title += data


def public_url(url: str) -> bool:
    """url为候选地址；复用研究工具的公网校验，拒绝内网与带凭据地址。"""
    from .research_tools import public_url as check
    return check(url)


def candidates(html: str, base: str) -> list[str]:
    """html为首页源码、base为最终地址；按头像适配度返回图标候选URL（已去重）。"""
    parser = IconParser()
    try: parser.feed(html[:400_000])
    except Exception: pass
    touch = [href for rel, _, href in parser.links if 'apple-touch-icon' in rel]
    icons = [href for rel, size, href in sorted(parser.links, key=lambda x: -x[1]) if 'apple-touch-icon' not in rel]
    sized = {href: size for rel, size, href in parser.links}
    large = [h for h in icons if sized.get(h, 0) >= 64]
    small = [h for h in icons if sized.get(h, 0) < 64]
    # 头像约72px：优先大尺寸图标与页头logo图片，16/32px小图标只作兜底。
    ordered = [*touch, *large[:2], *parser.images[:2], *small[:2], '/favicon.ico']
    result = []
    for href in ordered:
        url = urljoin(base, href.strip())
        if url.startswith(('http://', 'https://')) and url not in result: result.append(url)
    return result


def download(client: httpx.Client, url: str) -> tuple[bytes, str] | None:
    """url为图标候选；返回(内容, 扩展名)，非图片、过大或过小返回None。"""
    if not public_url(url): return None
    response = client.get(url)
    if response.status_code != 200: return None
    kind = response.headers.get('content-type', '').split(';')[0].strip().lower()
    body = response.content
    if not 64 <= len(body) <= MAX_BYTES: return None
    if kind not in IMAGE_TYPES:
        # 部分站点以octet-stream返回favicon，只按魔数识别ICO/PNG。
        if body[:4] == b'\x00\x00\x01\x00': kind = 'image/x-icon'
        elif body[:8] == b'\x89PNG\r\n\x1a\n': kind = 'image/png'
        else: return None
    return body, IMAGE_TYPES[kind]


def homepage(client: httpx.Client, url: str) -> tuple[str, str] | None:
    """url为官网地址；返回(最终地址, HTML)，非公网或非HTML返回None。"""
    if not public_url(url): return None
    response = client.get(url)
    if response.status_code != 200 or 'html' not in response.headers.get('content-type', ''): return None
    response.encoding = response.encoding or response.charset_encoding or 'utf-8'
    text = response.text
    if re.search(r'charset=["\']?gb', text[:2000], re.I):
        text = response.content.decode('gb18030', errors='replace')
    return str(response.url), text


def find_website(name: str, short_name: str = '') -> str:
    """name为企业全称；经全网检索找官网候选，首页出现全称或简称才返回，否则空串。"""
    from .tender_intel import web_search
    rows = web_search([f'{name} 官网', f'{name} 官方网站 首页'], 6).get('rows', [])
    hosts = []
    for row in rows:
        host = urlparse(row['url']).hostname or ''
        if host and not NOT_OFFICIAL.search(host) and host not in hosts: hosts.append(host)
    keys = [k for k in {name, short_name, re.sub(r'(股份)?有限(责任)?公司$', '', name)} if len(k) >= 4]
    with httpx.Client(headers=HEADERS, timeout=10, follow_redirects=True, max_redirects=3) as client:
        for host in hosts[:4]:
            try:
                page = homepage(client, f'https://{host}/') or homepage(client, f'http://{host}/')
            except httpx.HTTPError:
                continue
            if page and any(k in re.sub(r'\s+', '', page[1]) for k in keys):
                return page[0]
    return ''


def verified_website(db, company: Company) -> str:
    """db为读取会话；返回已核验事实中的官网地址，没有时返回空串。"""
    from .contact_view import website_link
    for fact in db.scalars(select(CompanyFact).where(CompanyFact.company_id == company.id, CompanyFact.field == 'website',
                                                   CompanyFact.status.not_in(['disputed', 'inactive', 'masked']))):
        link = website_link(str(fact.raw_value or ''))
        if link: return link
    return ''


def refresh_logo(company_id: str, force: bool = False) -> dict:
    """company_id为主体ID；取得并缓存站点图标，写入metadata_json.logo，返回最新logo状态。"""
    with Session() as db:
        company = db.get(Company, company_id)
        if not company: return {}
        meta = dict((company.metadata_json or {}).get('logo') or {})
        name, short = company.name, company.short_name or ''
        from .contact_view import website_link
        registered = website_link(((company.metadata_json or {}).get('registration') or {}).get('官网', ''))
        verified = verified_website(db, company)
        website, basis = (verified, 'verified_fact') if verified else (registered, 'registration') if registered else ('', 'homepage_name_match')
    # 检索/网络错误不代表没有标识，下次任务可再试；只有确认未找到或已取得时才按周期跳过。
    if not force and meta.get('checked_at') and meta.get('status') in {'ok', 'not_found'}:
        checked = datetime.strptime(meta['checked_at'], '%Y-%m-%d %H:%M:%S')
        if meta.get('file') or checked > datetime.now() - timedelta(days=RETRY_DAYS): return meta
    result = {'checked_at': now(), 'status': 'not_found'}
    try:
        site = website or find_website(name, short)
        if site:
            with httpx.Client(headers=HEADERS, timeout=10, follow_redirects=True, max_redirects=3) as client:
                page = homepage(client, site)
                base, html = page if page else (site, '')
                for url in candidates(html, base):
                    try: found = download(client, url)
                    except httpx.HTTPError: found = None
                    if found:
                        LOGO_DIR.mkdir(parents=True, exist_ok=True)
                        file = company_id + found[1]
                        (LOGO_DIR / file).write_bytes(found[0])
                        result = {'checked_at': now(), 'status': 'ok', 'file': file, 'source_url': url, 'website': base,
                                  'website_basis': basis, 'version': str(int(time.time()))}
                        break
            if result['status'] != 'ok': result['website'] = site
    except Exception as exc:
        result['status'], result['error'] = 'error', type(exc).__name__
        LOG.warning('logo_failed', extra={'details': {'company_id': company_id, 'error_type': type(exc).__name__}})
    with Session.begin() as db:
        company = db.get(Company, company_id)
        if company: company.metadata_json = {**(company.metadata_json or {}), 'logo': result}
    return result


def logo_url(company: Company) -> str:
    """company为主体；有缓存图标时返回带版本号的接口地址，否则空串。"""
    logo = (company.metadata_json or {}).get('logo') or {}
    return f"/api/companies/{company.id}/logo?v={logo.get('version', '')}" if logo.get('file') else ''


def logo_file(company_id: str) -> Path | None:
    """company_id为主体ID；返回缓存文件路径，不存在返回None。"""
    with Session() as db:
        company = db.get(Company, company_id)
        file = ((company.metadata_json or {}).get('logo') or {}).get('file') if company else ''
    path = LOGO_DIR / file if file else None
    return path if path and path.is_file() and path.parent == LOGO_DIR else None
