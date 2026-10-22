"""招投标情报采集：聚合招标平台、千里马系企业主页与全网检索，按原文判定角色并沉淀记录与对手方。

数据流：平台检索与全网检索并行 → 发现企业招投标主页并读取公告/中标/合作单位栏目 → 读取重点公告详情 →
逐条保存TenderRecord（含证据ID与原文行）→ 由记录与平台合作统计汇总TenderRelation。
每次外部调用都写ToolCall账本并推送工具事件；同一任务重复执行复用已完成结果，不重复访问站点。
"""
import asyncio
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
from urllib.parse import urlparse
from langsmith import traceable
from sqlalchemy import select
from .config import ROOT, exa_mcp_url
from .db import Session, Job, ToolCall, now
from .company_models import Company, TenderRecord, TenderRelation, ResearchCompany
from .gateway import archive_sources
from .observability import logger, safe_error
from .site_guides import retry_policy
from .tender_models import PlatformSearchOutput, WebSearchOutput, PageReadOutput, TenderRecordProposal, TenderRelationProposal
from .tender_parse import (parse_detail, parse_listing, parse_partners, parse_supplier_table, parse_win_table, parse_owner_page, parse_info_pairs, parse_shuidi,
                           title_buyer, clean_name, compact, normalize_date, AGENCY_RE, title_key)

LOG = logger('agent')
POLICY = 'tender-intel-1'
PLATFORM_SOURCES = ['qianlima', 'chinabidding', 'ebnew', 'yfbzb_public']
SOURCE_NAMES = {'qianlima': '千里马', 'chinabidding': '中国采购与招标网', 'ebnew': '必联网', 'yfbzb_public': '乙方宝',
                'exa': '全网检索', 'hub': '招投标企业主页', 'detail': '公告详情'}
HUB_RE = re.compile(r'^(https?://(?:www\.)?[a-z0-9\-]+\.(?:com|cn|net)/qiye/[a-z0-9]+/)')
WIN_SUMMARY_RE = re.compile(r'cbi360\.net/hhb/sg_\d+/zb/?')
OWNER_RE = re.compile(r'cbi360\.net/hhb/proprietor/\d+')
SHUIDI_RE = re.compile(r'biaoxun\.shuidi\.cn/company-detail/')
CONFIDENCE_RANK = {'index': 0, 'listing': 1, 'detail': 2}
EXA_GATE = threading.BoundedSemaphore(2)
RETRY_DELAYS = (2, 5)
REGISTRATION_KEYS = {'法人': '法定代表人', '注册资本金': '注册资本', '成立时间': '成立日期', '统一社会信用代码': '统一信用代码', '详细地址': '注册地址',
                     '企业地址': '注册地址', '经营期限': '营业期限', '企业官网': '官网', '联系方式': '电话'}
ROLE_LABELS = {'buyer': '采购', 'winner': '中标', 'candidate': '候选', 'agency': '代理', 'related': '待核实', 'mentioned': '提及'}


def acq_modules():
    """无参数；把项目内acq查询工具加入导入路径并返回其模块，复用平台适配与归一化逻辑。"""
    path = str(ROOT / 'src/tools')
    if path not in sys.path: sys.path.insert(0, path)
    from acq_query import sources, config, exa
    return sources, config, exa


def stable_key(*parts) -> str:
    """parts为可序列化身份片段；返回确定性SHA-256，用于幂等去重。"""
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


class Ledger:
    """单个任务的招投标工具账本。

    - 同任务同参数已完成：直接复用；其他任务近期（reuse_days）完成的同参数检索：跨任务复用并标记来源任务；
    - 失败按网站指引的重试策略处理：只重试临时性错误，验证码/登录/限流/404不重试；
    - 工具输出经Pydantic模型校验，不合格记为bad_tool_output，不进入后续解析。
    """

    def __init__(self, job_id: str):
        self.job_id = job_id

    def recent(self, tool: str, arguments: dict, reuse_days: float) -> dict | None:
        """返回其他任务在reuse_days内以相同参数完成且有结果的调用（job_id与result），没有返回None。"""
        if reuse_days <= 0: return None
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=reuse_days)).strftime('%Y-%m-%d %H:%M:%S')
        with Session() as db:
            for row in db.scalars(select(ToolCall).where(ToolCall.tool == tool, ToolCall.status == 'completed', ToolCall.job_id != self.job_id,
                                                        ToolCall.updated_at >= cutoff).order_by(ToolCall.updated_at.desc()).limit(300)):
                result = row.result or {}
                if row.arguments == arguments and (result.get('notices') or result.get('rows') or result.get('text')):
                    return {'job_id': row.job_id, 'result': result}
        return None

    @traceable(name='工具·招投标', run_type='tool', process_inputs=lambda x: {k: x.get(k) for k in ('tool', 'label', 'arguments')},
               process_outputs=lambda r: {k: (len(v) if isinstance(v, (list, str)) else v) for k, v in (r or {}).items()
                                          if k in ('notices', 'rows', 'text', 'error', 'status', 'reused', 'provider', 'attempts')})
    async def run(self, tool: str, label: str, arguments: dict, fn, timeout: float, model=None, policy=None, reuse_days: float = 0) -> dict:
        """tool/label/arguments为工具名、显示名与可见参数；fn为同步采集函数；model为输出Pydantic模型；policy为重试策略；
        reuse_days>0时允许复用其他任务近期同参数结果。返回校验后的结果字典，失败时带error。"""
        from .research_tools import emit, guard
        from .tool_views import tool_result
        from .site_guides import RetryPolicy, retryable
        policy = policy or RetryPolicy(max_attempts=1, backoff_seconds=[])
        guard(self.job_id)
        from langsmith.run_helpers import get_current_run_tree
        tree = get_current_run_tree()
        if tree:
            tree.name = '工具·' + label
            tree.add_metadata({'tool_name': tool, 'channel': 'tender', 'job_id': self.job_id, **{k: str(v)[:200] for k, v in arguments.items()}})
        operation = stable_key(POLICY, self.job_id, tool, arguments)
        with Session.begin() as db:
            old = db.scalar(select(ToolCall).where(ToolCall.operation_id == operation))
            if old and old.status == 'completed':
                emit(self.job_id, 'tool.reused', {'tool': tool, 'operation_id': operation, 'channel': 'tender', 'arguments': arguments,
                     'status': 'completed', 'attempts': old.attempts or 1, **tool_result(old.result)}, '复用已取得结果')
                return {**(old.result or {}), 'reused': True}
            has_old = old is not None
        shared = None if has_old else self.recent(tool, arguments, reuse_days)
        if shared:
            # 跨任务复用：保存为本任务的完成记录（标明来源任务），使恢复与经验统计一致。
            result = {**shared['result'], 'reused_from_job': shared['job_id']}
            with Session.begin() as db:
                db.add(ToolCall(job_id=self.job_id, operation_id=operation, tool=tool, channel='tender', arguments=arguments,
                                result=result, status='completed', last_attempt_epoch=time.time()))
            emit(self.job_id, 'tool.reused', {'tool': tool, 'operation_id': operation, 'channel': 'tender', 'arguments': arguments,
                 'status': 'completed', 'attempts': 1, **tool_result(result), 'reused': True}, '复用近期已保存结果')
            return {**result, 'reused': True}
        with Session.begin() as db:
            old = db.scalar(select(ToolCall).where(ToolCall.operation_id == operation))
            if old:
                old.attempts = (old.attempts or 1) + 1; old.status = 'running'; old.last_attempt_epoch = time.time(); attempt = old.attempts
            else:
                db.add(ToolCall(job_id=self.job_id, operation_id=operation, tool=tool, channel='tender', arguments=arguments, last_attempt_epoch=time.time()))
                attempt = 1
        emit(self.job_id, 'tool.started', {'tool': tool, 'channel': 'tender', 'operation_id': operation, 'arguments': arguments,
             'status': 'running', 'attempts': attempt}, label)
        start, tries, state, result = time.monotonic(), 0, 'completed', {}
        for index in range(policy.max_attempts):
            tries += 1
            state = 'completed'
            try:
                result = await asyncio.wait_for(asyncio.to_thread(fn), max(timeout, policy.timeout_seconds))
            except asyncio.TimeoutError:
                result, state = {'error': 'timeout', 'sources': []}, 'unavailable'
            except ProviderLimited:
                result, state = {'error': 'provider_rate_limited', 'sources': []}, 'rate_limited'
            except Exception as exc:  # 单个来源失败不影响其他来源
                result, state = {'error': safe_error(exc), 'sources': []}, 'unavailable'
                LOG.warning('tender_tool_error', extra={'details': {'job_id': self.job_id, 'tool': tool, 'error_type': safe_error(exc), 'try': tries}})
            if model is not None and state == 'completed':
                try:
                    result = model.model_validate(result).model_dump()
                except Exception:
                    result, state = {'error': 'bad_tool_output', 'sources': []}, 'rejected'
            produced = bool(result.get('notices') or result.get('rows') or result.get('text'))
            if result.get('error') and state == 'completed' and not produced: state = 'unavailable'
            if state == 'completed' or not retryable(result.get('error', '')) or index + 1 >= policy.max_attempts: break
            guard(self.job_id)
            delays = policy.backoff_seconds or [1.0]
            await asyncio.sleep(delays[min(index, len(delays) - 1)])
        result = {**result, 'attempts': tries}
        elapsed = round((time.monotonic() - start) * 1000)
        with Session.begin() as db:
            row = db.scalar(select(ToolCall).where(ToolCall.operation_id == operation))
            row.result, row.status, row.elapsed_ms, row.updated_at = result, state, (row.elapsed_ms or 0) + elapsed, now()
            row.attempts = (row.attempts or 1) + tries - 1
        emit(self.job_id, 'tool.finished', {'tool': tool, 'channel': 'tender', 'operation_id': operation, 'elapsed_ms': elapsed,
             'status': state, 'attempts': attempt + tries - 1, **tool_result(result)}, '完成' if state == 'completed' else '该渠道未取得结果')
        return result


def platform_search(source: str, company: str, days: int, limit: int) -> dict:
    """source为平台键、company为完整企业名；调用OpenCLI平台适配器，返回归一化公告与状态。"""
    sources, config, _ = acq_modules()
    settings = config.load_settings()
    quiet = lambda *_: None
    out = sources.Collected()
    if source == 'qianlima': sources.collect_qianlima(settings, company, days, limit, out, quiet)
    elif source == 'chinabidding': sources.collect_chinabidding(settings, company, limit, out, quiet)
    elif source == 'ebnew': sources.collect_ebnew(settings, company, limit, out, quiet)
    elif source == 'yfbzb_public': sources.collect_yfbzb_public(settings, company, limit, out, quiet)
    status = out.statuses[-1] if out.statuses else None
    # 归一化函数会把推断角色写回buyer/winner字段；这里改用适配器原始字段，推断交给index_role重新判定。
    raw = {row.get('url', ''): row for row in out.raw.get(source, []) if isinstance(row, dict)}
    notices = [{**{k: n.get(k, '') for k in ('source', 'source_label', 'notice_type', 'title', 'published_at', 'agency', 'amount',
               'budget', 'role', 'region', 'summary', 'url')}, 'buyer': raw.get(n.get('url', ''), {}).get('buyer', ''),
               'winner': raw.get(n.get('url', ''), {}).get('winner', '')} for n in out.notices]
    return {'notices': notices, 'status': status.status if status else 'empty',
            'error': '' if not status or status.status in {'ok', 'empty'} else status.status,
            'message': '' if not status else re.sub(r'\s+', ' ', status.message)[:200],
            'sources': [{'title': n['title'], 'url': n['url']} for n in notices[:5]]}


class ProviderLimited(RuntimeError):
    """Exa限流或额度不足；调用方记录为provider_rate_limited，不再重试。"""


def exa_call(fn):
    """fn为单次Exa请求；全进程最多两路并发，429/5xx/网络错误按固定退避重试两次，其余错误原样抛出。"""
    for attempt, delay in enumerate((0, *RETRY_DELAYS)):
        time.sleep(delay)
        try:
            with EXA_GATE: return fn()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == len(RETRY_DELAYS): raise ProviderLimited('provider_rate_limited') from exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == len(RETRY_DELAYS): raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == len(RETRY_DELAYS): raise


def exa_search(queries: list[str], per_query: int) -> dict:
    """queries为检索词列表；顺序调用Exa避免匿名额度被并发打满，返回去重后的标题/链接/摘要。"""
    _, _, exa = acq_modules()
    client = exa.ExaMcp(exa_mcp_url())
    exa_call(client.connect)
    rows, seen = [], set()
    for query in queries:
        for row in exa_call(lambda: client.search(query, per_query)):
            url = row.get('url', '')
            if url and url not in seen:
                seen.add(url)
                rows.append({'title': row.get('title', ''), 'url': url, 'published_at': row.get('published_at', '') if re.match(r'\d{4}-', row.get('published_at', '')) else '',
                             'text': (row.get('text') or '')[:1500], 'query': query})
    return {'rows': rows, 'error': '' if rows else 'empty_results', 'sources': [{'title': r['title'], 'url': r['url']} for r in rows[:5]]}


def web_search(queries: list[str], per_query: int) -> dict:
    """queries为检索词；先用Exa，限流/失败/无结果时改用内置OpenCLI百度/搜狗检索，返回统一行格式并注明实际检索方式。"""
    exa_error = ''
    try:
        result = exa_search(queries, per_query)
        if result.get('rows'): return {**result, 'provider': 'exa'}
        exa_error = result.get('error', 'empty_results')
    except ProviderLimited:
        exa_error = 'provider_rate_limited'
    except Exception as exc:
        exa_error = safe_error(exc)
    from .web_search import opencli_search
    rows, seen, errors = [], set(), []
    # 兜底检索逐词启动浏览器较慢，只执行前3个最有价值的检索词。
    for item in opencli_search(queries[:3], per_query):
        if item.error: errors.append(item.error)
        for row in item.rows:
            if row.url in seen: continue
            seen.add(row.url)
            rows.append({'title': row.title, 'url': row.url, 'published_at': row.published_at, 'text': row.snippet, 'query': item.query, 'engine': row.engine})
    return {'rows': rows, 'provider': 'opencli', 'exa_error': exa_error,
            'error': '' if rows else (errors[0] if errors else 'empty_results'), 'sources': [{'title': r['title'], 'url': r['url']} for r in rows[:5]]}


HTTP_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 ClientReach/0.3'}
HOST_CLOCK: dict[str, float] = {}
HOST_LOCK = threading.Lock()


def http_read(url: str, max_chars: int = 30000) -> dict:
    """url为公开页面；直接HTTP读取并转为文本（含表格行、公告链接与工商标签），同站至少间隔1秒；验证页/空壳页返回error。"""
    import httpx
    from .research_tools import public_url
    from .tender_html import html_text, html_title, html_articles, html_info
    if not public_url(url): return {'text': '', 'error': 'site_policy_unavailable', 'sources': []}
    host = urlparse(url).hostname or ''
    with HOST_LOCK:
        wait = HOST_CLOCK.get(host, 0) + 1.0 - time.time()
        HOST_CLOCK[host] = max(time.time(), HOST_CLOCK.get(host, 0) + 1.0)
    if wait > 0: time.sleep(wait)
    with httpx.Client(headers=HTTP_HEADERS, timeout=15, follow_redirects=True, max_redirects=3) as client:
        response = client.get(url)
    if response.status_code != 200 or 'html' not in response.headers.get('content-type', ''):
        return {'text': '', 'error': f'http_{response.status_code}', 'sources': []}
    html = response.text
    if re.search(r'charset=.{0,2}gb', html[:3000], re.I): html = response.content.decode('gb18030', errors='replace')
    text = html_text(html)
    if re.search('Access Verification|人机验证|请输入正确的验证码|滑动验证', text[:600]):
        return {'text': '', 'error': 'site_verification_required', 'sources': []}
    if len(text) < 200: return {'text': '', 'error': 'empty_body', 'sources': []}
    title = html_title(html)
    return {'text': text[:max_chars], 'title': title, 'articles': html_articles(html, str(response.url)), 'info': html_info(html),
            'published_at': '', 'error': '', 'sources': [{'title': title, 'url': url}]}


EXA_FIRST_HOSTS = {'www.qianlima.com', 'qianlima.com'}


def page_read(url: str, max_chars: int = 12000) -> dict:
    """url为公开页面；先直接HTTP读取，失败或为空壳时经Exa读取已索引版本，两者都失败返回最后的错误。

    正文由脚本加载的站点（直接读取只得到导航）先走Exa。
    """
    if (urlparse(url).hostname or '') in EXA_FIRST_HOSTS:
        result = exa_read(url, max_chars)
        if result.get('text'): return {**result, 'via': 'exa'}
    try:
        result = http_read(url, max(max_chars, 30000))
    except Exception as exc:
        result = {'text': '', 'error': safe_error(exc), 'sources': []}
    if result.get('text'): return {**result, 'via': 'http'}
    try:
        fallback = exa_read(url, max_chars)
    except ProviderLimited:
        return {'text': '', 'error': result.get('error') or 'provider_rate_limited', 'sources': []}
    return {**fallback, 'via': 'exa', 'http_error': result.get('error', '')} if fallback.get('text') else {**fallback, 'http_error': result.get('error', '')}


def portal_read(portal) -> dict:
    """portal为集团采购平台；按目录登记的方式直接读取或用浏览器渲染，返回正文，失败返回error。"""
    if portal.access == 'http':
        return http_read(portal.url)
    from .browser_reader import read_edge
    try:
        page = asyncio.run(read_edge(portal.url))
    except Exception as exc:
        from .service import ServiceError
        return {'text': '', 'error': str(exc)[:60] if isinstance(exc, ServiceError) else safe_error(exc), 'sources': []}
    body = page.get('body') or ''
    if len(body) < 200: return {'text': '', 'error': 'empty_body', 'sources': []}
    return {'text': body[:40000], 'title': page.get('title', ''), 'via': 'browser', 'error': '', 'sources': [{'title': page.get('title', ''), 'url': portal.url}]}


def exa_read(url: str, max_chars: int = 12000) -> dict:
    """url为公开页面；经Exa读取正文，遇登录/验证页返回error，不尝试绕过。"""
    _, _, exa = acq_modules()
    client = exa.ExaMcp(exa_mcp_url())
    exa_call(client.connect)
    text = exa_call(lambda: client.fetch(url, max_chars)) or ''
    title = (re.search(r'^#\s*(.+)$', text, re.M) or [None, ''])[1].strip()
    if not text.strip() or re.search('Access Verification|人机验证|请输入正确的验证码', text[:400]):
        return {'text': '', 'title': title, 'error': 'site_verification_required', 'sources': []}
    published = (re.search(r'^Published:\s*(\S+)', text, re.M) or [None, ''])[1]
    return {'text': text, 'title': title or url, 'published_at': normalize_date(published), 'error': '', 'sources': [{'title': title, 'url': url}]}


def ensure_member(db, job_id: str, name: str) -> Company:
    """db为当前事务、name为完整企业名；按原名幂等取得主体并关联当前会话，不做相似名合并。"""
    from .company_service import ensure_company
    company = ensure_company(db, name, visibility='primary', origin='agent', research_as_of=now()[:10])
    job = db.get(Job, job_id)
    from .company_service import stable_key as company_key
    member_key = company_key(job.conversation_id, job_id, company.id)
    if not db.scalar(select(ResearchCompany.id).where(ResearchCompany.unique_key == member_key)):
        db.add(ResearchCompany(unique_key=member_key, company_id=company.id, conversation_id=job.conversation_id, job_id=job_id,
                               position=len(job.company_ids or []), origin='agent'))
    job.company_ids = list(dict.fromkeys([*(job.company_ids or []), company.id]))
    return company


class TenderCollector:
    """单个企业的招投标采集过程；所有记录写入同一主体，记录键按企业+标题去重。"""

    def __init__(self, job_id: str, company: str, options: dict):
        self.job_id, self.company, self.options = job_id, company, options
        self.ledger = Ledger(job_id)
        self.records: dict[str, dict] = {}
        self.relations: dict[tuple, dict] = {}
        self.read_urls: set[str] = set()
        self.status: dict[str, str] = {}
        self.registration: dict = {}
        # 跨任务复用近期同参数检索/读取结果的天数（0表示每次都重新访问站点）。
        self.reuse_days = float(options.get('tender_reuse_days', 1))
        self.rejected = 0
        # Exa限流后，正文只能经Exa读取的站点（千里马详情）在本次采集中跳过，避免逐条等待。
        self.exa_down = False
        self.reused = False

    # ---------------------------------------------------------------- 记录合并
    def add_record(self, title: str, role: str, confidence: str, **fields) -> None:
        """title为公告标题、role/confidence为判定结果；同标题记录合并，高置信度覆盖角色，空字段补齐。"""
        key = title_key(title, self.company)
        if not key: return
        current = self.records.get(key)
        for field in ('buyer_name', 'agency_name'):
            # 平台字段常把机构名按词断开（“国网 江苏省 电力 有限公司”），中文之间的空格去掉。
            if fields.get(field): fields[field] = re.sub(r'(?<=[一-鿿])\s+(?=[一-鿿])', '', fields[field]).strip()
        value = {'title': title.strip()[:300], 'role': role, 'confidence': confidence, **{k: v for k, v in fields.items() if v not in (None, '', [])}}
        if not current:
            self.records[key] = value; return
        stronger = CONFIDENCE_RANK.get(confidence, 0) > CONFIDENCE_RANK.get(current['confidence'], 0)
        confirmed_over_unknown = current['role'] in {'related', 'mentioned'} and role not in {'related', 'mentioned'}
        downgrade = role in {'related', 'mentioned'} and current['role'] not in {'related', 'mentioned'}
        if (stronger and not downgrade) or confirmed_over_unknown:
            merged = {**current, **value}
            for field in ('published_at', 'region', 'budget', 'amount', 'project_number'):
                if not merged.get(field) and current.get(field): merged[field] = current[field]
            self.records[key] = merged
        else:
            for field, item in value.items():
                if field not in current or current[field] in ('', None, []): current[field] = item

    def add_relation(self, name: str, kind: str, basis: str, **fields) -> None:
        """name为对手方原名、kind为supplier/customer/competitor/agency、basis为来源口径；同名同口径合并次数与记录。"""
        name = clean_name(name)
        if not name or compact(self.company) in compact(name) or compact(name) in compact(self.company): return
        key = (name, kind, basis)
        current = self.relations.setdefault(key, {'name': name, 'kind': kind, 'basis': basis, 'count': 0, 'record_keys': [], 'latest_at': ''})
        current['count'] = max(current['count'], fields.pop('count', 0)) if basis == 'platform_stats' else current['count'] + fields.pop('count', 1)
        if fields.get('record_key'): current['record_keys'].append(fields.pop('record_key'))
        if fields.get('latest_at', '') > current['latest_at']: current['latest_at'] = fields.pop('latest_at')
        for field, item in fields.items():
            if item and not current.get(field): current[field] = item

    # ---------------------------------------------------------------- 采集阶段
    def consume_mcp(self, result: dict) -> dict:
        """只消费本任务归档正文；完整名称与原文角色相等才确认，不追加联网请求。"""
        from .db import Evidence
        self.reused |= bool(result.get('reused'))
        incoming={r['source']:r.get('status','unknown') for r in result.get('coverage',[]) if r.get('source')}
        for key,value in incoming.items():
            if self.status.get(key) not in {None,'ok','empty','public','masked'} and value in {'ok','empty','public','masked'}:continue
            self.status[key]=value
        if result.get('error'):self.status['mcp']=result['error']
        with Session() as db:
            for record in result.get('records',[]):
                source=db.get(Evidence,record.get('source_id'))
                if not source or source.job_id!=self.job_id or not record.get('has_full_text') or source.kind not in {'网页正文','网页读取'}:continue
                from .bidresearch_mcp import grounded_party,grounded_amount
                parties=[p for item in record.get('parties',[]) if (p:=grounded_party(source.body,item))]
                own=next((p for p in parties if p['name']==self.company),None)
                if not own:continue
                parsed=parse_detail(source.body,self.company,record['title'])
                number=parsed.get('project_number','')
                if number and number not in source.body:number=''
                date=record.get('published_at','')
                from .procurement_accounts import submission_deadline
                deadline,deadline_quote=submission_deadline(source.body)
                # Ignore only a trailing attribution footer; every substantive visible word must match.
                visible=re.sub(r'\n来源[：:][^\n]{0,200}\s*$','',source.body)
                key=stable_key('mcp-notice-2',re.sub(r'\s+','',record['title']),number,date,hashlib.sha256(re.sub(r'\s+','',visible).encode()).hexdigest()) if date else stable_key('mcp-notice-2',source.url)
                previous=self.records.get(key)
                alternates=list(record.get('alternate_sources',[]))
                if previous:
                    alternates.extend(previous.get('evidence_fields',{}).get('alternate_sources',[]))
                    if previous.get('evidence_id')!=source.id:alternates.append({'source_id':previous['evidence_id'],'url':previous['url'],'source':previous.get('platform','')})
                amounts=[a for item in record.get('amounts',[]) if (a:=grounded_amount(source.body,item))]
                amount=lambda kind:next((a.get('display_value',a['original']) for a in amounts if a.get('kind')==kind and '元' in a.get('display_value',a['original']) and len(a.get('display_value',a['original']))<=60 and
                    re.search('预算' if kind=='budget' else '中标|成交',a.get('label',''))),'')
                self.records[key]={'title':record['title'][:300],'role':own['role'],'confidence':'detail','quote':own['quote'][:1200],
                    'published_at':date,'project_number':number,'platform':record.get('source',''),'url':source.url,'evidence_id':source.id,
                    'buyer_name':next((p['name'] for p in parties if p['role']=='buyer'),''),'winner_names':[p['name'] for p in parties if p['role']=='winner'],
                    'candidate_names':[p['name'] for p in parties if p['role']=='candidate'],'agency_name':next((p['name'] for p in parties if p['role']=='agency'),''),
                    'budget':amount('budget'),'amount':amount('award'),'items':parsed.get('items',[]),'region':record.get('region','')[:60],
                    'evidence_fields':{'parties':parties,'amounts':amounts,'alternate_sources':list({a['source_id']:a for a in alternates if a.get('source_id') and a['source_id']!=source.id}.values()),
                        'deadline':{'value':deadline,'quote':deadline_quote} if deadline else {}},'record_key':key}
        if not self.records:
            # Update this attempt only for an existing exact company, without creating an identity from search navigation.
            with Session.begin() as db:
                company=db.scalar(select(Company).where(Company.name==self.company))
                if company and hasattr(self,'diagnostics'):
                    company.metadata_json={**(company.metadata_json or {}),'tender_diagnostics':self.diagnostics,'tender_status':self.status,'tender_reused':self.reused,'tender_collected_at':now()}
            return {'company':self.company,'company_id':None,'records':{},'relations':{},'status':self.status,'reused':self.reused,'diagnostics':getattr(self,'diagnostics',{})}
        self.relations={}
        self.derive_relations()
        return self.persist()

    @traceable(name='招投标·平台检索', run_type='chain')
    async def search_platforms(self) -> list[dict]:
        """并行调用免登录平台适配器；返回全部归一化公告，单个平台失败只记录状态。"""
        days, limit = self.options.get('tender_days', 365), self.options.get('tender_limit', 40)
        tasks = [self.ledger.run('search_tenders', f'{SOURCE_NAMES[src]}检索', {'query': self.company, 'source': src},
                                 lambda src=src: platform_search(src, self.company, days, limit), 120, model=PlatformSearchOutput,
                                 policy=retry_policy(src), reuse_days=self.reuse_days) for src in PLATFORM_SOURCES]
        notices = []
        for src, result in zip(PLATFORM_SOURCES, await asyncio.gather(*tasks)):
            self.reused |= bool(result.get('reused'))
            self.status[src] = result.get('error') or ('ok' if result.get('notices') else 'empty')
            notices.extend(result.get('notices') or [])
        return notices

    @traceable(name='招投标·全网检索', run_type='chain')
    async def search_web(self) -> list[dict]:
        """以企业名组合招标/中标/合作关系检索词，发现原始公告与企业招投标主页。"""
        name = self.company
        queries = [f'{name}招标中标信息', f'{name}招标公告', f'{name} 中标', f'{name} 中标候选人 成交结果', f'{name} 合作单位 供应商']
        result = await self.ledger.run('search_tenders', '全网招投标检索', {'query': ' | '.join(queries), 'source': 'exa'},
                                       lambda: web_search(queries, 8), 210, model=WebSearchOutput, policy=retry_policy('exa'),
                                       reuse_days=self.reuse_days)
        self.status['web'] = result.get('error') or ('ok · ' + result.get('provider', 'exa'))
        self.reused |= bool(result.get('reused'))
        return result.get('rows') or []

    async def read(self, url: str, label: str, max_chars: int = 12000) -> dict:
        """url为公开页面；读取并归档为证据，返回正文与证据ID，失败返回空正文。"""
        if url in self.read_urls: return {}
        self.read_urls.add(url)
        result = await self.ledger.run('read_tender', label, {'url': url}, lambda: page_read(url, max_chars), 75, model=PageReadOutput,
                                       policy=retry_policy(url=url), reuse_days=self.reuse_days * 3)
        self.reused |= bool(result.get('reused'))
        if result.get('error') == 'provider_rate_limited': self.exa_down = True
        if not result.get('text'): return {}
        records = await asyncio.to_thread(archive_sources, self.job_id, [{'url': url, 'title': result.get('title') or url, 'body': result['text'],
            'published_at': result.get('published_at') or None, 'source_meta': {'origin': 'tender_platform', 'policy': POLICY}}], '网页读取', 'tender')
        return {**result, 'evidence_id': records[0]['id'] if records else None}

    @traceable(name='招投标·企业主页', run_type='chain')
    async def read_hub(self, base: str) -> None:
        """base为千里马系企业主页根地址；读取招标、中标、合作单位、竞争对手与工商栏目，形成记录、对手方与工商摘要。"""
        pages = [(base + '1/', 'tenders'), (base + '1/2', 'tenders'), (base + '2/', 'wins'), (base + '4/', 'partners'),
                 (base + '5/', 'partners'), (base + '6/', 'registration')]
        results = await asyncio.gather(*[self.read(url, '读取招投标企业主页') for url, _ in pages])
        platform = urlparse(base).hostname or ''
        for (url, kind), page in zip(pages, results):
            if not page: continue
            heading = page.get('title', '')
            if kind in {'tenders', 'wins'}:
                if compact(self.company) not in compact(heading): continue
                # 直接读取时有逐条原文链接；经索引读取只有标题，链接退回为列表页。
                rows = page.get('articles') or [{**row, 'url': ''} for row in parse_listing(page['text'])]
                for row in rows:
                    role = 'buyer' if kind == 'tenders' else 'candidate' if re.search('候选人', row['title']) else 'winner'
                    self.add_record(row['title'], role, 'listing', published_at=row['published_at'], platform=platform,
                                    buyer_name=title_buyer(row['title']) if kind == 'wins' else '', url=row.get('url') or url,
                                    evidence_id=page['evidence_id'], quote=row['title'], heading=heading)
            elif kind == 'partners':
                for kind_key, rows in parse_partners(page['text']).items():
                    for row in rows:
                        self.add_relation(row['name'], kind_key, 'platform_stats', count=row['count'], platform=platform, url=url,
                                          evidence_id=page['evidence_id'], quote=row['line'])
            elif kind == 'registration' and page.get('info'):
                self.merge_registration(page['info'], url, page['evidence_id'])

    async def read_win_summary(self, url: str) -> None:
        """url为建设通企业中标业绩页；表格中“目标企业中标……”的行作为中标记录。"""
        page = await self.read(url, '读取企业中标业绩')
        if not page: return
        for row in parse_win_table(page['text'], self.company):
            self.add_record(row['title'], 'winner', 'listing', region=row['region'], amount=row['amount'], buyer_name=row['buyer'],
                            platform=urlparse(url).hostname or '', url=url, evidence_id=page['evidence_id'], quote=row['line'])

    def merge_registration(self, info: dict, url: str, evidence_id: str | None) -> None:
        """info为工商标签值对；首个来源优先，其余来源只补空字段，并记录全部来源链接。"""
        if not info: return
        sources = list(dict.fromkeys([*self.registration.get('sources', []), url]))
        for key, value in info.items(): self.registration.setdefault(REGISTRATION_KEYS.get(key, key), value)
        self.registration.setdefault('source_url', url); self.registration.setdefault('evidence_id', evidence_id)
        self.registration['sources'] = sources; self.registration['as_of'] = now()[:10]

    async def read_owner_page(self, url: str) -> None:
        """url为建设通业主页；常合作供应商形成供应商关系，历史发包形成采购记录（含中标企业），工商表补企业信息。"""
        page = await self.read(url, '读取业主发包与常合作供应商')
        if not page or compact(self.company) not in compact(page.get('title', '') + page['text'][:600]): return
        parsed = parse_owner_page(page['text'], self.company)
        platform = urlparse(url).hostname or ''
        for row in parsed['suppliers']:
            self.add_relation(row['name'], 'supplier', 'platform_stats', count=row['count'], latest_at=row['latest_at'], platform=platform,
                              url=url, evidence_id=page['evidence_id'], quote=row['line'], amount_total=row['amount'])
        for row in parsed['projects']:
            self.add_record(row['title'], 'buyer', 'listing', published_at=row['published_at'], region=row['region'], buyer_name=self.company,
                            winner_names=[row['winner']] if row['winner'] else [], platform=platform, url=url,
                            evidence_id=page['evidence_id'], quote=row['line'])
        self.merge_registration(parse_info_pairs(page['text']), url, page['evidence_id'])

    async def read_shuidi(self, url: str) -> None:
        """url为水滴标讯企业页；按页面标注的“招采单位/中标单位”角色形成采购与中标记录，工商摘要补企业信息。"""
        page = await self.read(url, '读取企业招投标档案')
        if not page or compact(self.company) not in compact(page.get('title', '') + page['text'][:400]): return
        platform = urlparse(url).hostname or ''
        for row in parse_shuidi(page['text'], self.company):
            self.add_record(row['title'], row['role'], 'listing', published_at=row['published_at'], budget=row['budget'],
                            buyer_name=row['buyer'], notice_type=row['notice_type'], platform=platform, url=url,
                            evidence_id=page['evidence_id'], quote=row['line'])
        self.merge_registration(parse_info_pairs(page['text']), url, page['evidence_id'])

    async def read_group_portal(self, portal) -> None:
        """portal为目标企业所属集团的自建采购平台；读取首页公告列表，标题含企业名称的记为其采购记录。"""
        from .procurement_portals import parse_portal_notices, name_variants
        result = await self.ledger.run('read_tender', '读取集团采购平台·' + portal.name, {'url': portal.url, 'portal': portal.key},
                                       lambda: portal_read(portal), 150, model=PageReadOutput, policy=retry_policy(url=portal.url),
                                       reuse_days=self.reuse_days)
        self.reused |= bool(result.get('reused'))
        if not result.get('text'): return
        records = await asyncio.to_thread(archive_sources, self.job_id, [{'url': portal.url, 'title': result.get('title') or portal.name, 'body': result['text'],
            'source_meta': {'origin': 'group_portal', 'portal': portal.key, 'policy': POLICY}}], '网页读取', 'tender')
        evidence_id = records[0]['id'] if records else None
        variants = [compact(v) for v in name_variants(self.company)]
        for row in parse_portal_notices(result['text']):
            if any(v in compact(row['title']) for v in variants):
                self.add_record(row['title'], 'buyer', 'listing', published_at=row['published_at'], buyer_name=self.company,
                                platform=portal.name, url=portal.url, evidence_id=evidence_id, quote=row['title'])

    async def read_supplier_list(self, url: str) -> None:
        """url为第三方供应商列表页；仅当页面标题含目标企业时登记供应商，保留页面发布日期。"""
        page = await self.read(url, '读取企业供应商列表')
        if not page or compact(self.company) not in compact(page.get('title', '')): return
        for row in parse_supplier_table(page['text']):
            self.add_relation(row['name'], 'supplier', 'third_party_list', platform=urlparse(url).hostname or '', url=url,
                              evidence_id=page['evidence_id'], quote=row['line'], latest_at=page.get('published_at', ''))

    async def read_detail(self, item: dict) -> None:
        """item含公告url/title；读取详情并按原文标签确认角色、对手方、金额与清单。"""
        if self.exa_down and (urlparse(item['url']).hostname or '') in EXA_FIRST_HOSTS: return
        page = await self.read(item['url'], '读取公告详情')
        if not page: return
        title = item.get('title') or page.get('title', '')
        parsed = parse_detail(page['text'], self.company, title)
        if parsed['role'] == 'mentioned' and compact(self.company) not in compact(page['text']): return
        self.add_record(title, parsed['role'], 'detail', published_at=parsed['published_at'] or item.get('published_at', ''),
                        buyer_name=parsed['buyer'], winner_names=parsed['winners'], candidate_names=parsed['candidates'],
                        agency_name=parsed['agency'], amount=parsed['amount'], budget=parsed['budget'], items=parsed['items'],
                        project_number=parsed['project_number'], platform=urlparse(item['url']).hostname or '', url=item['url'],
                        evidence_id=page['evidence_id'], quote=parsed['quote'] or title)

    # ---------------------------------------------------------------- 主流程
    async def collect(self) -> dict:
        """执行完整采集；返回各角色记录数、对手方数与渠道状态，供回答与缺口规划使用。"""
        notices, web_rows = await asyncio.gather(self.search_platforms(), self.search_web())
        hubs = {}
        for row in web_rows:
            found = HUB_RE.match(row['url'])
            if found and compact(self.company) in compact(row['title']): hubs[found.group(1)] = hubs.get(found.group(1), 0) + 1
        if not hubs:
            # 检索漏掉或受限时，复用已保存记录与研究档案中的企业主页地址。
            from .search_memory import company_memory
            hubs = {base: 1 for base in [*self.known_hubs(), *company_memory(self.company).get('tender_hubs', [])]}
        jobs = [self.read_hub(base) for base, _ in sorted(hubs.items(), key=lambda x: -x[1])[:1]]
        jobs += [self.read_win_summary(row['url']) for row in web_rows if WIN_SUMMARY_RE.search(row['url']) and compact(self.company) in compact(row['title'])][:1]
        jobs += [self.read_supplier_list(row['url']) for row in web_rows if re.search('供应商有哪些|供应商列表', row['title']) and compact(self.company) in compact(row['title'])][:1]
        jobs += [self.read_owner_page(row['url']) for row in web_rows if OWNER_RE.search(row['url']) and compact(self.company) in compact(row['title'])][:1]
        jobs += [self.read_shuidi(row['url']) for row in web_rows if SHUIDI_RE.search(row['url']) and compact(self.company) in compact(row['title'])][:1]
        from .procurement_portals import portals_for
        jobs += [self.read_group_portal(portal) for portal in portals_for(self.company)]
        await asyncio.gather(*jobs)
        # 平台列表只有标题时先作待核实；与企业主页同标题的公告补发布日期与地区。
        for notice in notices:
            role = self.index_role(notice)
            # 质量约束：全文检索命中但标题/摘要都未出现企业全称的待核实公告是噪声，不保存。
            if role == 'related' and compact(self.company) not in compact(notice.get('title', '') + notice.get('summary', '')): continue
            self.add_record(notice['title'], role, 'index', published_at=notice.get('published_at', ''), region=notice.get('region', ''),
                            buyer_name=notice.get('buyer', ''), winner_names=[notice['winner']] if notice.get('winner') else [],
                            agency_name=notice.get('agency', ''), amount=notice.get('amount', ''), budget=notice.get('budget', ''),
                            platform=notice.get('source_label', ''), url=notice.get('url', ''), quote=notice.get('summary', '')[:300])
        await self.find_originals()
        details = self.detail_candidates(web_rows)
        semaphore = asyncio.Semaphore(3)
        async def bounded(item):
            async with semaphore: await self.read_detail(item)
        await asyncio.gather(*[bounded(item) for item in details])
        self.derive_relations()
        return await asyncio.to_thread(self.persist)

    def known_hubs(self) -> list[str]:
        """从数据库中该企业已保存的招投标记录与对手方来源中取企业主页根地址。"""
        from .company_service import stable_key as company_key
        with Session() as db:
            company = db.scalar(select(Company).where(Company.identity_key == company_key('name', self.company)))
            if not company: return []
            urls = [*db.scalars(select(TenderRelation.url).where(TenderRelation.company_id == company.id)),
                    *db.scalars(select(TenderRecord.url).where(TenderRecord.company_id == company.id).limit(300))]
        return list(dict.fromkeys(m.group(1) for url in urls if url and (m := HUB_RE.match(url))))

    def index_role(self, notice: dict) -> str:
        """notice为平台检索结果；只按买方/中标字段或标题开头的采购机构判定角色，“结果”字样不再推断为中标方。"""
        target, title = compact(self.company), notice.get('title', '')
        if target in compact(notice.get('buyer', '')): return 'buyer'
        if target in compact(notice.get('winner', '')): return 'candidate' if '候选' in notice.get('notice_type', '') + title else 'winner'
        # 标题以本企业开头只说明发布者；还须含采购类词语才算采购公告（排除规划公示、招租等）。
        procurement = re.search('采购|招标|询价|询比|比选|竞价|竞争性|磋商|谈判|遴选|单一来源', title)
        if procurement and (compact(title_buyer(title)) == target or compact(title).startswith(target)) and not re.match(re.escape(self.company) + r'\s*中标', title):
            return 'buyer'
        if re.match(re.escape(self.company) + r'\s*中标', title): return 'winner'
        return 'related'

    @traceable(name='招投标·追溯原始公告', run_type='chain')
    async def find_originals(self) -> None:
        """企业主页只有中标/候选标题时，按标题检索原始公告并读取，取得候选人名单（竞争对手）与金额。"""
        limit = self.options.get('tender_original_reads', 3)
        # 候选人公示列出全部投标人，最能反映竞争对手，优先追溯；其次是最近的结果公告。
        # 自身中标/候选的公告给出竞争对手；自身采购的结果公告给出中标方（供应商）。
        pending = [r for r in sorted(self.records.values(), key=lambda r: ('候选' in r['title'], r['role'] != 'buyer', r.get('published_at', '')), reverse=True)
                   if r['role'] in {'winner', 'candidate', 'buyer'} and r['confidence'] in {'listing', 'index'} and not r.get('winner_names')
                   and re.search('候选|结果|成交|中标', r['title'])][:limit]
        if not pending: return
        result = await self.ledger.run('search_tenders', '检索原始中标公告', {'query': ' | '.join(r['title'] for r in pending), 'source': 'exa_original'},
                                       lambda: web_search([r['title'] for r in pending], 4), 180, model=WebSearchOutput,
                                       policy=retry_policy('exa'), reuse_days=self.reuse_days * 3)
        self.reused |= bool(result.get('reused'))
        reads = []
        for record in pending:
            key = title_key(record['title'], self.company)
            match = next((row for row in result.get('rows', []) if row['query'] == record['title'] and not HUB_RE.match(row['url'])
                          and (key[:16] in title_key(row['title'], self.company) or title_key(row['title'], self.company)[:16] in key)), None)
            if match: reads.append({'url': match['url'], 'title': record['title'], 'published_at': record.get('published_at', '')})
        await asyncio.gather(*[self.read_detail(item) for item in reads])

    def detail_candidates(self, web_rows: list[dict]) -> list[dict]:
        """web_rows为全网检索结果；优先读取正文提到企业的原始公告，其次补读待核实的平台公告。"""
        limit = self.options.get('tender_detail_reads', 6)
        chosen, seen = [], set()
        def push(url, title, published_at=''):
            if url and url not in seen and url not in self.read_urls and not HUB_RE.match(url) and not WIN_SUMMARY_RE.search(url)                     and not OWNER_RE.search(url) and not SHUIDI_RE.search(url):
                seen.add(url); chosen.append({'url': url, 'title': title, 'published_at': published_at})
        for row in web_rows:
            text = compact(row['title'] + row['text'])
            if len(chosen) < (limit + 1) // 2 and compact(self.company) in text and re.search('中标|成交|候选|采购|招标|询价|比选|结果', row['title'] + row['text'][:300]):
                push(row['url'], row['title'], row['published_at'])
        recent = sorted(self.records.values(), key=lambda r: r.get('published_at', ''), reverse=True)
        # 自身采购的结果公告给出中标方（供应商），其次是最近的询价单（物资清单）；只读有逐条原文链接的记录。
        own = [r for r in recent if r['role'] == 'buyer' and r.get('url') and not HUB_RE.match(r['url']) and not r.get('items')]
        for record in sorted(own, key=lambda r: bool(re.search('结果|中标|成交', r['title'])), reverse=True)[:2]:
            push(record['url'], record['title'], record.get('published_at', ''))
        for record in recent:
            if record['role'] == 'related' and record.get('url'): push(record['url'], record['title'], record.get('published_at', ''))
        return chosen[:limit]

    def derive_relations(self) -> None:
        """由已确认角色的记录汇总对手方：自身采购的中标方为供应商，自身中标的采购方为客户，同项目其他候选为竞争对手。"""
        for key, record in self.records.items():
            date = record.get('published_at', '')
            if record['role'] == 'buyer':
                for name in record.get('winner_names', []):
                    self.add_relation(name, 'supplier', 'records', record_key=key, latest_at=date)
            elif record['role'] in {'winner', 'candidate'}:
                buyer = record.get('buyer_name', '')
                if buyer and not AGENCY_RE.search(buyer) and record['role'] == 'winner':
                    self.add_relation(buyer, 'customer', 'records', record_key=key, latest_at=date)
                for name in [*record.get('candidate_names', []), *([] if record['role'] == 'winner' else record.get('winner_names', []))]:
                    self.add_relation(name, 'competitor', 'records', record_key=key, latest_at=date)
            if record.get('agency_name') and record['role'] in {'buyer', 'winner'}:
                self.add_relation(record['agency_name'], 'agency', 'records', record_key=key, latest_at=date)

    def persist(self) -> dict:
        """在一个事务内写入主体、记录与对手方；同键幂等更新，返回摘要。"""
        with Session.begin() as db:
            company = ensure_member(db, self.job_id, self.company)
            ids = {}
            for key, record in list(self.records.items()):
                # 质量门禁：角色/置信度枚举、日期格式、遮挡名称与地址协议不合格的记录不保存，计入rejected。
                try:
                    checked = TenderRecordProposal.model_validate({**record, 'items': record.get('items', [])}).model_dump()
                except Exception:
                    self.rejected += 1; self.records.pop(key, None); continue
                record = {**record, **{k: checked[k] for k in ('published_at', 'winner_names', 'candidate_names', 'url', 'items')}}
                unique = stable_key('tender-record', company.id, key)
                row = db.scalar(select(TenderRecord).where(TenderRecord.unique_key == unique))
                if not row and record.get('record_key') and record.get('published_at'):
                    from .db import Evidence
                    canonical=lambda body:re.sub(r'\s+','',re.sub(r'\n来源[：:][^\n]{0,200}\s*$','',body or ''))
                    current_source=db.get(Evidence,record.get('evidence_id'))
                    for prior in db.scalars(select(TenderRecord).where(TenderRecord.company_id==company.id,TenderRecord.url==record.get('url',''),
                        TenderRecord.title==record['title'],TenderRecord.published_at==record['published_at'])):
                        old_source=db.get(Evidence,prior.evidence_id)
                        if current_source and old_source and canonical(current_source.body)==canonical(old_source.body):
                            row=prior
                            fields=record.setdefault('evidence_fields',{})
                            alternates=[*fields.get('alternate_sources',[]),*((prior.payload or {}).get('evidence_fields') or {}).get('alternate_sources',[])]
                            if old_source.id!=current_source.id:alternates.append({'source_id':old_source.id,'url':old_source.url,'source':prior.platform})
                            fields['alternate_sources']=list({a['source_id']:a for a in alternates if a.get('source_id') and a['source_id']!=current_source.id}.values())
                            break
                values = {'role': record['role'], 'title': record['title'], 'notice_type': record.get('notice_type', ''),
                          'project_number': record.get('project_number', ''), 'published_at': record.get('published_at', ''),
                          'buyer_name': record.get('buyer_name', ''), 'winner_names': record.get('winner_names', []),
                          'candidate_names': record.get('candidate_names', []), 'agency_name': record.get('agency_name', ''),
                          'amount': record.get('amount', ''), 'budget': record.get('budget', ''), 'region': record.get('region', ''),
                          'items': record.get('items', []), 'platform': record.get('platform', ''), 'url': record.get('url', ''),
                          'evidence_id': record.get('evidence_id'), 'quote': record.get('quote', ''), 'confidence': record['confidence'],
                          'payload': {'heading': record.get('heading', ''), 'policy': POLICY,
                                      **({'mcp_record_key':record['record_key'],'evidence_fields':record.get('evidence_fields',{})} if record.get('record_key') else {})}}
                if row and record.get('record_key'):
                    fields=values['payload']['evidence_fields']
                    alternates=[*fields.get('alternate_sources',[]),*((row.payload or {}).get('evidence_fields') or {}).get('alternate_sources',[])]
                    if row.evidence_id and row.evidence_id!=values['evidence_id']:alternates.append({'source_id':row.evidence_id,'url':row.url,'source':row.platform})
                    fields['alternate_sources']=list({a['source_id']:a for a in alternates if a.get('source_id') and a['source_id']!=values['evidence_id']}.values())
                if row and CONFIDENCE_RANK.get(row.confidence, 0) > CONFIDENCE_RANK.get(values['confidence'], 0):
                    # 已有更高置信度的详情记录时，只补空字段，不用列表信息降级。
                    for field, item in values.items():
                        if item and not getattr(row, field): setattr(row, field, item)
                elif row:
                    for field, item in values.items():
                        if item or field in {'role', 'confidence'}: setattr(row, field, item)
                    row.job_id = self.job_id; row.updated_at = now()
                else:
                    row = TenderRecord(unique_key=unique, company_id=company.id, job_id=self.job_id, **values)
                    db.add(row); db.flush()
                ids[key] = row.id
            if any(r.get('record_key') for r in self.records.values()):
                # Record relations reflect all saved notices, including corrections to old roles.
                db.flush()
                saved_records=list(db.scalars(select(TenderRecord).where(TenderRecord.company_id==company.id)))
                current_records=self.records
                self.records={r.id:{field:getattr(r,field) for field in ('role','title','published_at','buyer_name','winner_names','candidate_names','agency_name','platform','url','evidence_id','quote')} for r in saved_records}
                self.relations={key:value for key,value in self.relations.items() if key[2]!='records'}
                self.derive_relations()
                self.records=current_records
                ids.update({r.id:r.id for r in saved_records})
                supported={(name,kind) for name,kind,basis in self.relations if basis=='records'}
                for old_relation in db.scalars(select(TenderRelation).where(TenderRelation.company_id==company.id,TenderRelation.basis=='records')):
                    if (old_relation.counterparty_name,old_relation.relation_type) not in supported:
                        old_relation.payload={**(old_relation.payload or {}),'unsupported_by_current_records':True}
            for (name, kind, basis), relation in list(self.relations.items()):
                try:
                    TenderRelationProposal.model_validate({'name': name, 'kind': kind, 'basis': basis, 'count': relation['count']})
                except Exception:
                    self.rejected += 1; self.relations.pop((name, kind, basis), None); continue
                unique = stable_key('tender-relation', company.id, name, kind, basis)
                row = db.scalar(select(TenderRelation).where(TenderRelation.unique_key == unique))
                values = {'counterparty_name': name, 'relation_type': kind, 'basis': basis, 'deal_count': relation['count'],
                          'amount_total': relation.get('amount_total', ''),
                          'latest_at': relation.get('latest_at', ''), 'record_ids': list(dict.fromkeys(ids[k] for k in relation['record_keys'] if k in ids)),
                          'platform': relation.get('platform', ''), 'url': relation.get('url', ''), 'evidence_id': relation.get('evidence_id'),
                          'quote': relation.get('quote', ''), 'payload': {'policy': POLICY}}
                if row:
                    for field, item in values.items(): setattr(row, field, item)
                    row.updated_at = now()
                else: db.add(TenderRelation(unique_key=unique, company_id=company.id, **values))
            company.updated_at = now()
            if hasattr(self,'diagnostics'):self.diagnostics['unique_record_count']=len(self.records)
            company.metadata_json = {**(company.metadata_json or {}), 'tender_as_of': now()[:10], 'tender_collected_at': now(), 'tender_status': self.status,'tender_reused':bool(self.reused),
                                     **({'tender_diagnostics':self.diagnostics} if hasattr(self,'diagnostics') else {}),
                                     **({'registration': self.registration} if self.registration else {})}
            company_id = company.id
        roles = {}
        for record in self.records.values(): roles[record['role']] = roles.get(record['role'], 0) + 1
        kinds = {}
        for relation in self.relations.values(): kinds[relation['kind']] = kinds.get(relation['kind'], 0) + 1
        return {'company': self.company, 'company_id': company_id, 'records': roles, 'relations': kinds, 'status': self.status,
                'rejected': self.rejected, 'reused': self.reused,'diagnostics':getattr(self,'diagnostics',{})}


REFRESH_RE = re.compile('最新|重新|刷新|更新一下|再查|重查|实时')


def reusable_summary(job_id: str, name: str, hours: float) -> dict | None:
    """name为企业全称；该企业在hours小时内完成过招投标采集时，返回数据库中的角色与对手方计数（标记reused），否则None。"""
    if hours <= 0: return None
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from .company_service import stable_key as company_key
    with Session() as db:
        company = db.scalar(select(Company).where(Company.identity_key == company_key('name', name)))
        collected = ((company.metadata_json or {}).get('tender_collected_at') or '') if company else ''
        if not collected or collected < (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S'): return None
        roles = dict(db.execute(select(TenderRecord.role, func.count()).where(TenderRecord.company_id == company.id).group_by(TenderRecord.role)).all())
        kinds = dict(db.execute(select(TenderRelation.relation_type, func.count()).where(TenderRelation.company_id == company.id).group_by(TenderRelation.relation_type)).all())
        company_id = company.id
    # 只有待核实/提及记录时没有可复用的结论，重新采集。
    if not any(n for role, n in roles.items() if role not in {'related', 'mentioned'}) and not kinds: return None
    with Session.begin() as db: ensure_member(db, job_id, name)
    return {'company': name, 'company_id': company_id, 'records': roles, 'relations': kinds, 'status': {}, 'rejected': 0,
            'reused': True, 'collected_at': collected}


def company_mcp_calls(job_id: str, name: str) -> list[dict]:
    """读取同任务企业 MCP 账本的最新结果和累计尝试；不重发已经成功的操作。"""
    with Session() as db:
        return [{'tool':row.tool,'arguments':row.arguments or {},'result':row.result or {},'attempts':row.attempts or 1}
                for row in db.scalars(select(ToolCall).where(ToolCall.job_id==job_id,
                    ToolCall.tool.in_(['search_tenders','get_tender_detail']),
                    ToolCall.arguments['company'].as_string()==name).order_by(ToolCall.created_at,ToolCall.id))]


def company_mcp_diagnostics(calls: list[dict], name: str) -> dict:
    """线索取检索结果，正文按证据去重；尝试累计，失败计仍未恢复的详情操作。"""
    diagnostics={}
    bodies={}
    for call in calls:
        payload=call['result']
        for key,value in payload.get('diagnostics',{}).items():
            if call['tool']=='get_tender_detail' and key in {'raw_count','navigation_count','missing_body_count'}:continue
            if isinstance(value,int) and key not in {'full_text_count','confirmed_count'}:
                diagnostics[key]=diagnostics.get(key,0)+value
            elif isinstance(value,str):diagnostics[key]=value
        for row in payload.get('records',[]):
            if row.get('has_full_text'):
                bodies[row.get('source_id') or row.get('url')]=row
    details=[call for call in calls if call['tool']=='get_tender_detail']
    return {**diagnostics,'full_text_count':len(bodies),
        'confirmed_count':sum(any(p.get('name')==name for p in row.get('parties',[])) for row in bodies.values()),
        'details_attempted':sum(call['attempts'] for call in details),
        'details_failed':sum(bool(call['result'].get('error')) for call in details),'unique_record_count':0}


async def collect_company_mcp(state, broker, name: str, fallback: dict | None = None) -> dict:
    """初次采集与显式恢复共用：消费已存结果，补读未尝试公告，逐页保存并更新诊断。"""
    calls=company_mcp_calls(state['job_id'],name)
    if not calls and fallback:calls=[{'tool':'search_tenders','arguments':{},'result':fallback,'attempts':0}]
    collector=TenderCollector(state['job_id'],name,state['options'])
    collector.reused=bool(fallback and fallback.get('reused'))
    collector.diagnostics=company_mcp_diagnostics(calls,name)
    sources={s['id']:s for call in calls for s in call['result'].get('sources',[])}
    broker.allowed_sources.update(sources)
    for call in calls:
        await asyncio.to_thread(collector.consume_mcp,call['result'])
    # A failed detail is retried only by recover_tools at the explicit resume boundary.
    # The queue contains actual returned links, and skips every already attempted page.
    attempted={call['arguments'].get('url') for call in calls if call['tool']=='get_tender_detail'}
    full_urls={row.get('url') for call in calls for row in call['result'].get('records',[]) if row.get('has_full_text')}
    queue={}
    for call in calls:
        if call['tool']!='search_tenders':continue
        args=call['arguments']
        for row in call['result'].get('records',[]):
            if row.get('url') and row.get('source') and row['url'] not in attempted|full_urls:
                queue[row['url']]={'source':row['source'],'url':row['url'],'company':name,
                    'mode':args.get('mode','history'),'days':args.get('days',365)}
    errors=[]
    for request in list(queue.values())[:state['options'].get('bidresearch_max_details',0)]:
        page=await broker.execute('get_tender_detail',request)
        if page.get('error')=='budget_exhausted':break
        if page.get('error'):errors.append(page['error'])
        sources.update({s['id']:s for s in page.get('sources',[])})
        collector.diagnostics=company_mcp_diagnostics(company_mcp_calls(state['job_id'],name),name)
        await asyncio.to_thread(collector.consume_mcp,page)
    summary=await asyncio.to_thread(collector.consume_mcp,{'records':[]})
    pending=[s['id'] for s in sources.values() if s.get('kind') in {'搜索摘录','网页正文','网页读取'}]
    direct=[{'url':s['url'],'channel':'procurement'} for s in sources.values()
            if s.get('kind')=='搜索摘录' and (s.get('source_meta') or {}).get('navigation_only')]
    return {'summary':summary,'sources':list(sources.values()),'pending':pending,'direct':direct,'errors':errors}


async def company_tenders(state):
    """图节点：对本轮目标企业（最多3家）执行招投标采集；未请求采购/上下游字段时跳过，不消耗外部额度。

    复用判断：企业在“招投标数据复用时长”内已采集且用户未要求最新/刷新时，直接使用已保存记录，不访问站点。
    """
    from .research_tools import emit
    fields = set(state.get('company_requested_fields') or [])
    wanted = not fields or bool(fields & {'procurement', 'procurement_rule', 'supplier', 'customer', 'competitor', 'relations', 'tender'})
    offline = os.getenv('CLIENTREACH_TENDER_ENABLED', '').lower() in {'0', 'false', 'off'}
    if offline or not wanted or not state['options'].get('tender_enabled', True) or state.get('reference_only'):
        return {'company_tender_summary': {}}
    if 'enabled_channels' in state['options'] and 'procurement' not in state['options']['enabled_channels']:
        return {'company_tender_summary': {}}
    from .bidresearch_mcp import runtime_status
    if state['options'].get('bidresearch_enabled',False) and runtime_status()['installed']:
        from .company_research import broker_for
        broker=broker_for(state);summary=dict(state.get('company_tender_summary') or {})
        sources=list(state.get('source_ids',[]));pending=list(state.get('company_mcp_sources',[]));direct=list(state.get('company_direct_urls',[]))
        for name in (state.get('company_intent_targets') or [])[:2]:
            if name in summary:continue
            from .bidresearch_mcp import company_time_window
            mode,days=company_time_window(state.get('prompt',''),min(365,state['options'].get('tender_days',365)))
            request={'keywords':[name],'company':name,'mode':mode,'days':days}
            if mode=='history':request['sources']=['ebnew']
            result=await broker.execute('search_tenders',request)
            collected=await collect_company_mcp(state,broker,name,result)
            sources.extend(s['id'] for s in collected['sources']);pending.extend(collected['pending']);direct.extend(collected['direct'])
            summary[name]=collected['summary']
        found=[item['company_id'] for item in summary.values() if item.get('company_id')]
        return {'company_tender_summary':summary,'source_ids':list(dict.fromkeys(sources)),'company_mcp_sources':list(dict.fromkeys(pending)),
                'company_ids':list(dict.fromkeys([*state.get('company_ids',[]),*found])),
                'company_direct_urls':list({item['url']:item for item in direct}.values())}
    targets = [name for name in (state.get('company_intent_targets') or []) if len(name) >= 4][:3]
    summary = dict(state.get('company_tender_summary') or {})
    hours = 0 if REFRESH_RE.search(state.get('prompt', '')) else float(state['options'].get('tender_reuse_hours', 24))
    for name in targets:
        if name in summary: continue
        reused = reusable_summary(state['job_id'], name, hours)
        if reused:
            emit(state['job_id'], 'tool.reused', {'tool': 'reuse_tenders', 'operation_id': stable_key('reuse', state['job_id'], name), 'channel': 'tender',
                 'arguments': {'query': name}, 'status': 'completed', 'attempts': 1, 'source_count': sum(reused['records'].values()),
                 'sources': [], 'error': '', 'reused': True}, '复用已保存的招投标数据（采集于 ' + reused['collected_at'][:16] + '）')
            summary[name] = reused
            continue
        options = {**state['options'], 'tender_reuse_days': hours / 24}
        summary[name] = await TenderCollector(state['job_id'], name, options).collect()
    found = [item['company_id'] for item in summary.values() if item.get('records') or item.get('relations')]
    return {'company_tender_summary': summary, 'company_ids': list(dict.fromkeys([*state.get('company_ids', []), *found]))}
