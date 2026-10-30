"""研究管线：理解需求 → 确认企业 → 检索列表 → 筛选公告 → 读取详情 → 工商资料 → 回答。

每个阶段完成后把进度写入 job.plan，阶段可重复执行：暂停、重启或用户登录后从中断处继续。
需要用户登录、验证或选择企业时抛出 Handover，任务进入 awaiting_user。
"""
import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

from datetime import date

from sqlalchemy import func, select

from .. import crawl, llm
from ..config import CRAWL_OUT
from ..db import (Attachment, Company, Conversation, Job, JobCompany, Knowledge, Lead, Message, Notice,
                  NoticeParty, Session, SiteStat, Source, get_settings, now)
from ..events import emit
from ..sites import SITES, Site, domain_of, enabled, get_site, known_domain, regional_sites, site_of, source_tier
from . import quality, store
from .schemas import CompanyExtract, Identity, Keywords, ListResult, ListRow, NoticeExtract, Plan, WebExtract, WebQuery, WebQueryPlan
from .verify import company_name, grounded, norm

log = logging.getLogger('dealradar.pipeline')

STAGES = {
    'find_buyers': ['understand', 'search', 'screen', 'read', 'expand', 'enrich', 'answer'],
    'company': ['understand', 'identify', 'search', 'screen', 'read', 'profile', 'answer'],
    'chat': ['understand', 'answer'],
    'search': ['understand', 'web_plan', 'web_discover', 'web_search', 'web_read', 'web_verify', 'answer'],
}
STAGE_LABELS = {'understand': '理解需求', 'identify': '确认企业', 'search': '检索公告', 'screen': '筛选公告',
                'read': '阅读原文', 'expand': '扩大检索', 'enrich': '补充工商信息', 'profile': '核对工商信息',
                'web_plan': '生成查询计划', 'web_discover': '发现来源', 'web_search': '通用检索',
                'web_read': '读取原文', 'web_verify': '引用核验', 'answer': '整理结论'}
KIND_LABELS = {'intent': '采购意向', 'tender': '招标公告', 'change': '更正公告', 'candidate': '中标候选',
               'award': '中标结果', 'contract': '合同公告', 'other': '公告'}


def _title_key(title: str) -> str:
    """同一公告在不同平台的标题常带编号前缀或站点后缀，去掉后比较。"""
    return re.sub(r'^[A-Z0-9\-]{8,}|[-_|].{0,20}(平台|网)$', '', norm(title))


_NON_MAINLAND = re.compile(r'台湾|台灣|臺灣|香港|澳门|澳門')
# 大陆公告不会出现的繁体字；采购单位或标题中出现两个以上视为港澳台公告
_TRADITIONAL = set('醫療業總處採購電氣會議與為國際東灣區縣廠構體備標產務資團機關費設計劃辦')


SCREEN_BATCH = 20


def _excerpt(flat: str, title: str, width: int = 120) -> str:
    """链接标题在列表页正文（已去空白）中的那一段，含日期、采购人等；找不到时为空。"""
    probe = re.sub(r'\s+', '', title)[:14]
    at = flat.find(probe) if len(probe) >= 6 else -1
    return flat[max(0, at - 20):at + width] if at >= 0 else ''


def _outside_mainland(title: str, buyer: str, region: str) -> bool:
    return bool(_NON_MAINLAND.search(f'{buyer} {region}')) or sum(ch in _TRADITIONAL for ch in f'{title}{buyer}') >= 2


def _web_url(url: str) -> str:
    """用于去重的网页地址：忽略大小写主机、片段与多余结尾斜杠。"""
    parts = urlsplit(url or '')
    if parts.scheme.lower() not in ('http', 'https') or not parts.netloc:
        return ''
    host = parts.hostname.lower() if parts.hostname else ''
    path = parts.path or '/'
    if path != '/':
        path = path.rstrip('/') or '/'
    return urlunsplit((parts.scheme.lower(), host + (f':{parts.port}' if parts.port else ''), path, parts.query, ''))


def dedupe_web_candidates(rows: list[dict]) -> list[dict]:
    result, seen = [], set()
    for row in rows:
        key = _web_url(row.get('url', ''))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append({**row, 'url': key})
    return result


class Handover(Exception):
    """需要用户处理：login/verify（在 Edge 中登录或验证）或 identity（选择企业）。"""

    def __init__(self, kind: str, message: str, **data):
        super().__init__(message)
        self.data = {'kind': kind, 'message': message, **data}


class OutOfTime(Exception):
    pass


class Run:
    def __init__(self, job_id: str):
        self.job_id = job_id
        with Session() as db:
            job = db.get(Job, job_id)
            self.conversation_id, self.message_id = job.conversation_id, job.message_id
            self.state = dict(job.plan or {})
            self.metrics = dict(job.metrics or {})
        self.settings = get_settings()
        self.browser = self.settings.get('crawl_profile') or ''
        self.started = time.monotonic()
        self.deadline = self.started + self.settings['max_minutes'] * 60 - self.metrics.get('elapsed_ms', 0) / 1000
        # 剩余次数可能为 0 或负数（预算已用完），只有设置为 0 才表示不限
        self.usage = llm.Usage(self.settings['max_model_calls'] - self.metrics.get('model_calls', 0),
                               unlimited=self.settings['max_model_calls'] <= 0)
        self.tool_seq = self.metrics.get('tools', 0)
        self.problems: list[str] = list(self.state.get('problems', []))
        self.pending_cancel: list[str] = []

    # ---------- 基础 ----------

    @property
    def plan(self) -> Plan:
        return Plan.model_validate(self.state['plan'])

    def save(self, **job_fields) -> None:
        self.metrics.update(elapsed_ms=self.metrics.get('elapsed_ms', 0) + round((time.monotonic() - self.started) * 1000),
                            model_calls=self.metrics.get('model_calls', 0) + self.usage.calls,
                            tokens=self.metrics.get('tokens', 0) + self.usage.tokens, tools=self.tool_seq)
        self.started = time.monotonic()
        # 已计入 metrics 的调用从剩余额度中扣除，再清零本段计数
        self.usage.limit -= self.usage.calls
        self.usage.calls = self.usage.tokens = 0
        self.state['problems'] = self.problems
        with Session.begin() as db:
            job = db.get(Job, self.job_id)
            job.plan, job.metrics = dict(self.state), dict(self.metrics)
            for key, value in job_fields.items():
                setattr(job, key, value)

    def check_time(self) -> None:
        if time.monotonic() > self.deadline:
            raise OutOfTime()

    @asynccontextmanager
    async def tool(self, name: str, label: str, site: str = '', url: str = ''):
        """记录一次工具调用：发出 tool.started / tool.finished 事件。调用方在 info 中写入结果。"""
        self.tool_seq += 1
        tool_id, started, info = f'{self.job_id}:{self.tool_seq}', time.monotonic(), {'status': 'completed'}
        emit(self.job_id, 'tool.started', {'id': tool_id, 'tool': name, 'label': label, 'site': site, 'url': url})
        try:
            yield info
        except Exception as exc:
            info.update(status='failed', error=str(exc)[:200])
            raise
        finally:
            emit(self.job_id, 'tool.finished', {'id': tool_id, 'tool': name, 'label': label, 'site': site, 'url': url,
                                                'elapsed_ms': round((time.monotonic() - started) * 1000), **info})

    async def folder(self) -> str:
        if not self.state.get('folder'):
            self.state['folder'] = await crawl.begin(self.state.get('plan', {}).get('title') or '研究任务', CRAWL_OUT)
            self.save(crawl_folder=self.state['folder'])
        return self.state['folder']

    def gate(self, page: crawl.Page, site: Site) -> None:
        """登录/验证页交给用户；限流与失败只记录问题，不重试。"""
        if page.needs_user and (site.web or site.origin == 'luzcrawl'):
            # 搜索引擎与 LuzCrawl 批量入口出现登录或验证时不让整个研究停下：跳过该来源，记为未完成项。
            self.problems.append(f'{site.name}：要求{"完成验证" if "verif" in page.stop_reason else "登录"}，本次跳过')
            self.pending_cancel.append(page.task_id)
            return
        if page.needs_user:
            raise Handover('verify' if 'verif' in page.stop_reason else 'login',
                           f'{site.name}需要{"完成验证" if "verif" in page.stop_reason else "登录"}，请在 Edge 中处理后点“继续”',
                           site=site.id, site_name=site.name, url=page.url, task_id=page.task_id)
        if not page.ok:
            reason = '访问受限' if page.stop_reason == 'rate_limited' else (page.error or page.stop_reason or '未读取到正文')
            self.problems.append(f'{site.name}：{reason}')

    # ---------- 执行 ----------

    async def execute(self) -> str:
        """返回终态 completed / partial；Handover 与取消向上抛出。"""
        token = llm.USAGE.set(self.usage)
        self.browser = self.browser or await crawl.default_profile()
        terminal_override = ''
        try:
            while True:
                stages = STAGES[self.state['plan']['mode']] if 'plan' in self.state else ['understand']
                pending = [stage for stage in stages if stage not in self.state.get('done', [])]
                if not pending:
                    break
                stage = pending[0]
                emit(self.job_id, 'stage', {'stage': stage, 'label': STAGE_LABELS[stage]})
                emit(self.job_id, 'stage.started', {'stage': stage, 'label': STAGE_LABELS[stage]})
                stage_started = time.monotonic()
                self.save(stage=stage)
                try:
                    if stage != 'answer':
                        self.check_time()
                    redo = await getattr(self, stage)()
                except (OutOfTime, llm.BudgetExceeded) as exc:
                    self.problems.append('已达到本次任务的时间上限' if isinstance(exc, OutOfTime) else str(exc))
                    self.state['done'] = [s for s in stages if s != 'answer']
                    continue
                if redo:
                    # 再跑一轮：把这些阶段移出已完成列表，从第一个开始重跑。
                    self.state['done'] = [s for s in self.state.get('done', []) if s not in redo]
                else:
                    self.state.setdefault('done', []).append(stage)
                    history = self.state.setdefault('stage_history', [])
                    entry = {'stage': stage, 'label': STAGE_LABELS[stage], 'status': 'completed',
                             'elapsed_ms': round((time.monotonic() - stage_started) * 1000),
                             'count': self._stage_count(stage), 'error': ''}
                    history[:] = [item for item in history if item.get('stage') != stage]
                    history.append(entry)
                    emit(self.job_id, 'stage.completed', entry)
                self.save()
                if stage == 'understand' and self.plan.needs_clarification:
                    await self._clarify()
                    terminal_override = 'awaiting_input'
                    break
        finally:
            llm.USAGE.reset(token)
            for task_id in filter(None, self.pending_cancel):
                await crawl.cancel(task_id)
        quality.rescore_leads()
        return terminal_override or self.final_status()

    def final_status(self) -> str:
        """有结果、没有读取以外的问题、未读到的不超过已读篇数的四分之一时记为完成，否则为部分完成；问题照常列在报告里。"""
        if self.plan.mode == 'search':
            verified = sum(1 for row in self.state.get('search_results', []) if row.get('status') == 'verified')
            return 'completed' if verified and not self.problems else ('partial' if verified else 'partial')
        read = list(self.state.get('read', {}).values())
        failed = read.count('failed')
        ok = sum(1 for state in read if state in ('saved', 'reused'))
        others = [p for p in self.problems if '公告未读取' not in p]
        with Session() as db:
            found = db.scalar(select(func.count()).select_from(JobCompany).where(
                JobCompany.job_id == self.job_id, JobCompany.role.in_(('buyer', 'target'))))
        return 'completed' if found and not others and failed * 4 <= ok else 'partial'

    def _stage_count(self, stage: str) -> int:
        if stage == 'web_read':
            return sum(1 for row in self.state.get('search_results', []) if row.get('source_id'))
        if stage == 'web_verify':
            return sum(1 for row in self.state.get('search_results', []) if row.get('status') == 'verified')
        if stage in ('web_discover', 'web_search'):
            return len(self.state.get('search_candidates', []))
        if stage == 'web_plan':
            return len(self.state.get('search_queries', []))
        return 0

    # ---------- 阶段 ----------

    async def understand(self) -> None:
        with Session() as db:
            message = db.get(Message, self.message_id)
            task_messages = list(db.scalars(select(Message).where(Message.job_id == self.job_id,
                                                                  Message.role == 'user').order_by(Message.created_at)))
            history = list(db.scalars(select(Message).where(Message.conversation_id == self.conversation_id,
                                                            Message.id != self.message_id)
                                      .order_by(Message.created_at.desc()).limit(6)))
            files = [db.get(Attachment, aid) for item in task_messages for aid in item.attachment_ids or []]
            notes = list(db.scalars(select(Knowledge).where(Knowledge.active == 1).limit(30)))
        attachments = '\n\n'.join(f'【附件：{f.filename}】\n{f.text[:6000]}' for f in files if f)
        request_text = '\n'.join(
            f'{"原始任务" if index == 0 else "执行中补充"}：{item.content}'
            for index, item in enumerate(task_messages or [message])
        )
        prompt = '\n\n'.join(filter(None, [
            f'我方公司：{self.settings["company_name"]}\n{self.settings["company_profile"]}' if self.settings['company_name'] else '',
            '长期偏好与排除：\n' + '\n'.join(f'- [{n.kind}] {n.body[:200]}' for n in notes) if notes else '',
            '最近对话：\n' + '\n'.join(f'{m.role}: {m.content[:300]}' for m in reversed(history)) if history else '',
            attachments,
            f'今天是 {date.today().isoformat()}。\n{request_text}',
            '请判断研究模式并给出研究计划。追问已有结果、问候、解释类问题用 chat。']))
        async with self.tool('understand', '理解需求') as info:
            plan = await llm.structured(Plan, prompt)
            if self.state.get('mode_hint') in STAGES:
                plan.mode = self.state['mode_hint']
            if self.state.get('company_hint'):
                plan.mode, plan.company = 'company', self.state['company_hint']
            plan.days = plan.days or self.settings['default_days']
            plan.regions = plan.regions or self.settings['target_regions']
            plan.exclusions = list(dict.fromkeys(plan.exclusions + self.settings['exclusions']))
            plan.keywords = plan.keywords[:6]
            if plan.mode == 'search':
                plan.query = plan.query or message.content
                plan.questions = plan.questions[:3]
            info['summary'] = plan.title
        self.state['plan'] = plan.model_dump()
        with Session.begin() as db:
            conversation = db.get(Conversation, self.conversation_id)
            if conversation.title == '新研究' and plan.mode != 'chat':
                conversation.title = plan.title
                emit(self.job_id, 'title', {'title': plan.title})
            db.get(Job, self.job_id).mode = plan.mode

    async def _clarify(self) -> None:
        """澄清阶段只发送问题，搜索阶段的结果仍由报告表格承载。"""
        questions = [question.strip() for question in self.plan.questions[:3] if question.strip()]
        if not questions:
            return
        content = '\n'.join(questions)
        with Session.begin() as db:
            reply = Message(conversation_id=self.conversation_id, role='assistant', content=content, job_id=self.job_id)
            db.add(reply)
            db.flush()
            db.get(Conversation, self.conversation_id).updated_at = now()
        self.save(reply_message_id=reply.id)
        emit(self.job_id, 'message.completed', {'message_id': reply.id, 'content': content})

    async def identify(self) -> None:
        """在百度企业信息中确认企业全称；多家相近时请用户选择。该页面同时作为工商资料来源。"""
        plan = self.plan
        site = SITES['baidu']
        if self.state.get('identity_choice') or site not in enabled('business', self.settings):
            self._set_target(self.state.get('identity_choice') or plan.company)
            return
        async with self.tool('search_company', f'确认企业“{plan.company}”', site.id) as info:
            page = await crawl.capture(site.search_url(plan.company, 0), await self.folder(), self.browser, scrolls=2)
            store.record_site(site.id, page.status)
            info['status'] = page.status
            self.gate(page, site)
            if not page.ok:
                self._set_target(plan.company)
                return
            source_id = store.save_source(page, site.id, 'business', self.job_id)
            identity = await llm.structured(Identity, f'目标企业：{plan.company}\n\n搜索结果页：\n{page.text[:8000]}')
            names = list(dict.fromkeys(company_name(n) for n in identity.names if company_name(n) in page.text))
            info['summary'] = '、'.join(names[:3]) or '未找到匹配企业'
        if len(names) > 1 and not identity.exact:
            raise Handover('identity', f'找到多家与“{plan.company}”相近的企业，请选择要研究的一家',
                           candidates=names[:6], site=site.id, site_name=site.name)
        self.state['business_sources'] = [source_id]
        self._set_target(names[0] if names else plan.company)

    def _set_target(self, name: str) -> None:
        name = company_name(name)
        self.state['plan'] = {**self.state['plan'], 'company': name}
        with Session.begin() as db:
            company = store.upsert_company(db, name)
            self.state['target_id'] = company.id
        store.link_job(self.job_id, self.state['target_id'], 'target')
        emit(self.job_id, 'result', {'company_id': self.state['target_id']})

    async def web_plan(self) -> None:
        """生成不超过六条的中英文查询，并把查询意图保存在可恢复状态中。"""
        plan = self.plan
        raw = (plan.query or plan.title or '').strip()
        async with self.tool('web_plan', '生成中英文查询计划') as info:
            if raw:
                prompt = (f'用户原始问题：{raw}\n用户语言：{plan.language}\n'
                          '把同一个问题扩展成最多 3 条中文和最多 3 条英文网页检索词。可以翻译，不能添加原问题没有的新主题；'
                          '每条写明 purpose，语言只用 zh/en/mixed。只返回结构化查询列表。')
                result = await llm.structured(WebQueryPlan, prompt)
                queries = result.queries[:6]
            else:
                queries = []
            if not queries:
                language = 'en' if plan.language == 'en' else 'zh' if plan.language == 'zh' else 'mixed'
                queries = [WebQuery(query=raw or plan.title, language=language, purpose='原始问题')]
            seen, normalized = set(), []
            language_counts = {'zh': 0, 'en': 0, 'mixed': 0}
            for query in queries:
                value = query.query.strip()
                if not value or value.lower() in seen:
                    continue
                if query.language in ('zh', 'en') and language_counts[query.language] >= 3:
                    continue
                seen.add(value.lower())
                language_counts[query.language] = language_counts.get(query.language, 0) + 1
                normalized.append({'query': value, 'language': query.language, 'purpose': query.purpose, 'status': 'queued'})
            self.state['search_queries'] = normalized[:6]
            info['count'] = len(normalized)
        self.save()

    async def web_discover(self) -> None:
        """通过 LuzCrawl 读取搜索引擎结果页，允许结果指向任意 HTTP(S) 域名。"""
        site = SITES['web']
        candidates: list[dict] = []
        source_ids = list(self.state.get('source_ids') or [])
        folder = await self.folder()
        engine_hosts = ('bing.com', 'microsoft.com', 'msn.com', 'live.com')
        for item in self.state.get('search_queries', []):
            query = item.get('query', '')
            if not query:
                continue
            async with self.tool('web_discover', f'发现“{query[:50]}”的来源', site.id, site.search_url(query, 0)) as info:
                page = await crawl.capture(site.search_url(query, 0), folder, self.browser, scrolls=3)
                info['status'] = page.status
                self.gate(page, site)
                links = []
                if page.ok:
                    source_id = store.save_source(page, site.id, 'web-search', self.job_id)
                    source_ids.append(source_id)
                    page_host = domain_of(page.url)
                    for link in page.links:
                        url = _web_url(link.get('url', ''))
                        host = domain_of(url)
                        if not url or not host or any(host == h or host.endswith('.' + h) for h in engine_hosts):
                            continue
                        if page_host and (host == page_host or host.endswith('.' + page_host)):
                            continue
                        links.append({'title': (link.get('text') or link.get('title') or '').strip()[:500],
                                      'url': url, 'domain': host, 'snippet': (link.get('snippet') or '').strip()[:500],
                                      'language': item.get('language', 'mixed'), 'source_id': source_id})
                candidates.extend(links)
                info['count'] = len(links)
                emit(self.job_id, 'search.route', {'stage': 'web_discover', 'query': query, 'language': item.get('language', 'mixed'),
                                                   'status': page.status, 'count': len(links), 'url': page.url or site.search_url(query, 0)})
                item['status'] = 'completed' if page.ok else page.status
        self.state['source_ids'] = list(dict.fromkeys(source_ids))
        self.state['search_candidates'] = dedupe_web_candidates(candidates)
        self.save()

    async def web_search(self) -> None:
        """对发现到的任意来源去重排序，形成有限的读取队列。"""
        candidates = dedupe_web_candidates(self.state.get('search_candidates') or [])
        max_reads = max(int(self.settings.get('max_reads', 20)), 1)
        self.state['search_candidates'] = candidates
        self.state['search_to_read'] = candidates[:max_reads]
        for item in self.state.get('search_queries', []):
            if item.get('status') == 'queued':
                item['status'] = 'completed'
        async with self.tool('web_search', '整理通用搜索结果') as info:
            info['count'] = len(candidates)
        emit(self.job_id, 'search.route', {'stage': 'web_search', 'status': 'completed', 'count': len(candidates),
                                           'queries': len(self.state.get('search_queries', []))})
        self.save()

    async def web_read(self) -> None:
        """用 LuzCrawl 读取候选正文，并要求模型给出可连续核验的引用。"""
        folder = await self.folder()
        results = list(self.state.get('search_results') or [])
        done = {row.get('url') for row in results}
        async with self.tool('web_read', f'读取 {len(self.state.get("search_to_read", []))} 个来源') as info:
            for candidate in self.state.get('search_to_read', []):
                url = candidate.get('url', '')
                if not url or url in done:
                    continue
                page = await crawl.capture(url, folder, self.browser, scrolls=4, timeout=150)
                if page.needs_user:
                    self.gate(page, SITES['web'])
                if not page.ok:
                    self.problems.append(f'{candidate.get("domain", "来源")}：{page.error or page.stop_reason or page.status}')
                    results.append({**candidate, 'status': 'failed', 'error': page.error or page.stop_reason or page.status})
                    done.add(url)
                    continue
                page.url = url
                source_id = store.save_source(page, candidate.get('domain', 'web')[:64] or 'web', 'web', self.job_id)
                async with self.tool('web_extract', f'抽取《{page.title[:40]}》', candidate.get('domain', 'web'), url) as extract_info:
                    extract = await llm.structured(WebExtract,
                                                   '只依据下面网页正文抽取与用户问题相关的信息。title、summary、points、published_on 必须来自正文；'
                                                   'quote 必须是正文中的连续原文片段，不能拼接或改写；要点最多三条。\n\n'
                                                   f'用户问题：{self.plan.query or self.plan.title}\n网页正文：\n{page.text[:16000]}')
                    extract_info['status'] = 'captured'
                row = {**candidate, 'relevant': extract.relevant,
                       'title': extract.title or candidate.get('title') or page.title,
                       'language': extract.language or candidate.get('language', 'mixed'),
                       'published_on': extract.published_on, 'summary': extract.summary,
                       'points': extract.points[:3], 'quote': extract.quote, 'source_id': source_id,
                       'status': 'pending'}
                results.append(row)
                done.add(url)
                emit(self.job_id, 'result.row', {**row, 'status': 'pending'})
            info['count'] = sum(1 for row in results if row.get('source_id'))
        self.state['search_results'] = results
        self.save()

    async def web_verify(self) -> None:
        """只保留引用出现在 LuzCrawl 原文中的结果行。"""
        with Session() as db:
            texts = {row.get('source_id'): (db.get(Source, row.get('source_id')).text
                                             if row.get('source_id') and db.get(Source, row.get('source_id')) else '')
                     for row in self.state.get('search_results', [])}
        verified_rows, problems = [], []
        for row in dedupe_web_candidates(self.state.get('search_results') or []):
            text = texts.get(row.get('source_id'), '')
            if not row.get('relevant', True) or not row.get('title') or not row.get('url') or not grounded(row.get('quote', ''), text):
                problems.append(f'引用核验失败：{row.get("title") or row.get("url") or "未命名来源"}')
                continue
            row = {**row, 'published_on': store._date(row.get('published_on', '')), 'points': (row.get('points') or [])[:3],
                   'status': 'verified'}
            verified_rows.append(row)
            emit(self.job_id, 'result.row', row)
        self.state['search_results'] = verified_rows
        self.problems.extend(problems)
        self.state['source_ids'] = list(dict.fromkeys(self.state.get('source_ids', []) + [r['source_id'] for r in verified_rows if r.get('source_id')]))
        self.save()

    COMPANY_YEARS = 2

    async def search(self) -> None:
        plan = self.plan
        company_mode = plan.mode == 'company'
        sites = [s for s in self._procurement_sites() if s.by_company or not company_mode]
        if company_mode:
            # 企业研究看历史：最近若干年，超出站点单次跨度时分段检索。
            jobs = [(site, plan.company, *window) for site in sites
                    for window in self._windows(site, 365 * self.COMPANY_YEARS)]
        else:
            # 每轮检索有上限，先跑历史表现好的站点，尽早进入阅读；其余在后续轮次补搜
            jobs = self._pending_searches(sites)[:max(self.settings['max_queries'] * 3, 12)]
        lists = self.state.setdefault('lists', {})
        folder = await self.folder()

        async def one(site: Site, query: str, days: int, offset: int, page_no: int = 1) -> None:
            key = self._search_key(site, query, offset, page_no)
            if key in lists:
                return
            label = f'在{site.name}检索“{query}”' + (f'（{offset // 365} 年前）' if offset else '') + (f'（第 {page_no} 页）' if page_no > 1 else '')
            async with self.tool('search_notices', label, site.id) as info:
                if site.template:
                    page = await crawl.capture(site.search_url(query, days, company_mode, offset, page_no), folder, self.browser, 3)
                else:
                    page = await crawl.search(site.platform, query, folder, self.browser)
                store.record_site(site.id, page.status)
                links = [l for l in page.links if site.is_detail(l['url'])]
                info.update(status=page.status, count=len(links))
                self.gate(page, site)
            lists[key] = {'site': site.id, 'query': query, 'status': page.status,
                          'source_id': store.save_source(page, site.id, 'list', self.job_id) if page.ok else None,
                          'links': [{'text': l.get('text', '')[:200], 'url': l['url']} for l in links[:80]]}
            self.save()

        results = await asyncio.gather(*(one(*job) for job in jobs), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result

    def _procurement_sites(self) -> list[Site]:
        """默认启用的站点 + 需求所含地区的省级、城市平台，去掉本次已跳过的站点；按历史表现排序。"""
        sites = enabled('procurement', self.settings)
        sites += [s for s in regional_sites(self.plan.regions, self.settings.get('sources') or {}) if s not in sites]
        sites = [s for s in sites if s.id not in self.state.get('skip_sites', [])]
        with Session() as db:
            stats = {row.site: row for row in db.scalars(select(SiteStat))}

        def score(site: Site) -> float:
            # 被采用的公告数优先，其次检索成功率；没有记录的站点居中，地区平台略微提前
            row = stats.get(site.id)
            rate = row.successes / row.attempts if row and row.attempts else 0.5
            return (min(row.adopted, 20) if row else 0) * 2 + rate * 3 + (1 if site.region else 0)
        return sorted(sites, key=score, reverse=True)

    @staticmethod
    def _search_key(site: Site, query: str, offset: int, page_no: int) -> str:
        return f'{site.id}|{query}|{offset}' + (f'|p{page_no}' if page_no > 1 else '')

    def _pending_searches(self, sites: list[Site]) -> list[tuple]:
        """尚未执行的检索，按“页 → 关键词 → 站点”排序：先把每个关键词的第一页搜完，再翻页。"""
        plan, lists = self.plan, self.state.get('lists', {})
        queries = list(dict.fromkeys((plan.keywords or [plan.product[:20]]) + self.state.get('extra_keywords', [])))
        # 站点按表现每 12 个一组：先让前一组跑完各关键词，再轮到下一组
        jobs = [(site, query, plan.days, 0, page_no) for page_no in range(1, 4)
                for group in range(0, len(sites), 12) for query in queries for site in sites[group:group + 12]
                if page_no <= (site.pages if site.template else 1)]
        return [job for job in jobs if self._search_key(job[0], job[1], 0, job[4]) not in lists]

    @staticmethod
    def _windows(site: Site, days: int) -> list[tuple[int, int]]:
        """把 days 天拆成站点允许的时间段，返回 [(跨度, 距今偏移)]。"""
        if not site.template or not site.max_days or days <= site.max_days:
            return [(days, 0)]
        return [(site.max_days, offset) for offset in range(0, days, site.max_days)]

    async def screen(self) -> None:
        """模型逐页判断列表中哪些公告与目标相关，合并去重后排序，选出需要阅读的公告。"""
        plan = self.plan
        goal = (f'找出企业“{plan.company}”作为采购人、中标人或投标人出现的公告' if plan.mode == 'company' else
                f'找出正在或近期采购以下产品/服务的公告：{plan.product}；关键词：{"、".join(plan.keywords)}')
        if plan.exclusions:
            goal += f'。排除：{"、".join(plan.exclusions)}'
        if plan.regions:
            goal += f'。只要这些地区：{"、".join(plan.regions)}'
        # 未指定港澳台时只要中国大陆的采购单位
        mainland_only = not any(_NON_MAINLAND.search(region) for region in plan.regions)
        if mainland_only:
            goal += '。只要中国大陆的采购单位，不要台湾、香港、澳门的单位'
        candidates = self.state.setdefault('candidates', {})
        by_title = {_title_key(c['title']): url for url, c in candidates.items()}
        screened = self.state.setdefault('screened', [])
        pending = []
        for key, item in self.state.get('lists', {}).items():
            if key in screened or not item.get('source_id') or not item['links']:
                continue
            list_site = get_site(item['site'])
            if not list_site:
                screened.append(key)
                continue
            pending.append((key, item, list_site))
        # 多份列表合批判断：同名公告只判断一次，每批最多 20 条链接，同时最多 4 批；
        # 每条链接带上它在列表页正文里的那一段，供模型读出采购人、公告类型、日期与地区。
        texts, groups, order = {}, {}, []
        for key, item, _ in pending:
            if item['source_id'] not in texts:
                with Session() as db:
                    texts[item['source_id']] = re.sub(r'\s+', '', db.get(Source, item['source_id']).text or '')
            for index, link in enumerate(item['links']):
                title_key = _title_key(link['text']) or link['url']
                if title_key not in groups:
                    groups[title_key] = []
                    order.append((title_key, link['text'], _excerpt(texts[item['source_id']], link['text'])))
                groups[title_key].append((key, index))
        verdicts: dict[tuple, ListRow] = {}
        slots = asyncio.Semaphore(4)

        async def judge(number: int, batch: list, part: str = '') -> None:
            lines = '\n'.join(f'[{i}] {title}' + (f'\n    列表摘录：{excerpt}' if excerpt else '') for i, (_, title, excerpt) in enumerate(batch))
            failure = None
            async with slots, self.tool('screen', f'筛选第 {number} 批检索结果{part}（{len(batch)} 条）') as info:
                try:
                    result = await llm.structured(ListResult, f'研究目标：{goal}\n\n公告链接：\n{lines}\n\n'
                                                  '逐条判断链接是否与研究目标相关，并从标题与列表摘录读出采购人、公告类型、日期、地区。')
                except ValueError as exc:
                    failure = exc
                    info['status'] = 'failed'
                else:
                    for row in result.rows:
                        if 0 <= row.link < len(batch):
                            for member in groups[batch[row.link][0]]:
                                verdicts[member] = row
                    info['count'] = sum(1 for row in result.rows if row.relevant)
            if failure is None:
                return
            # 输出超长：把这一批对半拆开各判断一次（在释放并发名额之后再拆，避免互相等待）
            if not part and len(batch) > 1:
                half = len(batch) // 2
                await asyncio.gather(judge(number, batch[:half], '（拆分 1/2）'), judge(number, batch[half:], '（拆分 2/2）'))
            else:
                self.problems.append(f'第 {number} 批检索结果{part}未能筛选（{failure}）')

        batches = [order[i:i + SCREEN_BATCH] for i in range(0, len(order), SCREEN_BATCH)]
        results = await asyncio.gather(*(judge(n + 1, batch) for n, batch in enumerate(batches)), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        results = [[verdicts[(key, i)].model_copy(update={'link': i}) for i in range(len(item['links'])) if (key, i) in verdicts]
                   for key, item, _ in pending]
        for (key, item, list_site), rows in zip(pending, results):
            for row in rows:
                if not row.relevant or not 0 <= row.link < len(item['links']):
                    continue
                link = item['links'][row.link]
                if mainland_only and _outside_mainland(link['text'], row.buyer, row.region):
                    continue
                url = list_site.detail_url(link['url'])
                title_key = _title_key(link['text'])
                if list_site.web and not known_domain(url):
                    store.discover(domain_of(url), link['text'], url)
                read = self.state.get('read', {})
                if url in candidates or url in read:
                    continue
                tier = source_tier(url, site_of(url) or list_site)
                existing = by_title.get(title_key)
                if existing:
                    # 同一公告：官方平台原文替换聚合站转载（已读过的不再替换）
                    old = candidates.get(existing)
                    if not old or existing in read or old.get('tier', 2) >= tier:
                        continue
                    del candidates[existing]
                by_title[title_key] = url
                candidates[url] = {'url': url, 'title': link['text'], 'site': list_site.id, 'buyer': row.buyer,
                                   'kind': row.kind, 'published_on': row.published_on, 'region': row.region, 'tier': tier}
            screened.append(key)
            self.save()
        unread = [c for c in candidates.values() if c['url'] not in self.state.get('read', {})]
        ranked = sorted(unread, key=self._rank, reverse=True)
        self.state['to_read'] = [c['url'] for c in ranked[:self.settings['max_reads']]]
        emit(self.job_id, 'progress', {'candidates': len(candidates), 'to_read': len(self.state['to_read'])})

    def _rank(self, candidate: dict) -> tuple:
        """待读顺序：公告类型 → 来源层级（官方原文优先）→ 站点历史采用率 → 公告时间。"""
        active = {'intent': 3, 'tender': 3, 'change': 2, 'candidate': 1, 'award': 1, 'contract': 1}.get(candidate['kind'], 0)
        if self.plan.mode == 'company':
            active = 1
        if not hasattr(self, '_adoption'):
            with Session() as db:
                self._adoption = {row.site: row.adopted / row.attempts for row in db.scalars(select(SiteStat)) if row.attempts}
        return active, candidate.get('tier', 2), round(self._adoption.get(candidate['site'], 0.0), 2), candidate.get('published_on') or ''

    async def read(self) -> None:
        plan = self.plan
        done = self.state.setdefault('read', {})
        todo = [url for url in self.state.get('to_read', []) if url not in done]
        for url in list(todo):
            if self._reuse(url):
                done[url] = 'reused'
                todo.remove(url)
        folder = await self.folder()
        extract_slots = asyncio.Semaphore(4)
        for start in range(0, len(todo), 6):
            self.check_time()
            chunk = todo[start:start + 6]
            async with self.tool('read_notices', f'阅读 {len(chunk)} 篇公告原文') as info:
                # 逐页并发读取，单页最多等 150 秒：一页卡住不拖住整批。
                pages = await asyncio.gather(*(crawl.capture(url, folder, self.browser, scrolls=4, timeout=150) for url in chunk))
                info['count'] = sum(page.ok for page in pages)

            async def handle(url: str, page: crawl.Page) -> None:
                site = get_site(self.state.get('candidates', {}).get(url, {}).get('site', '')) or site_of(url) or SITES['ccgp']
                store.record_site(site.id, page.status)
                if page.needs_user:
                    self.gate(page, site)
                if not page.ok:
                    done[url] = 'failed'
                    self.problems.append(f'{site.name}公告未读取：{page.error or page.stop_reason or page.status}')
                    return
                page.url = url
                source_id = store.save_source(page, site.id, 'notice', self.job_id)
                async with extract_slots, self.tool('extract_notice', f'核验《{page.title[:40]}》', site.id, url) as info:
                    extract = await llm.structured(NoticeExtract, self._notice_prompt(page.text))
                    if not extract.is_notice:
                        done[url], info['status'] = 'not_notice', 'skipped'
                        return
                    saved = store.save_notice(extract, source_id, page, self.state['candidates'].get(url, {}))
                    info['summary'] = KIND_LABELS.get(extract.kind, '公告')
                self._adopt(saved, extract, plan, site)
                if site.web and not known_domain(url):
                    store.discover(domain_of(url), page.title, url, adopted=1)
                done[url] = 'saved'

            results = await asyncio.gather(*(handle(u, p) for u, p in zip(chunk, pages)), return_exceptions=True)
            self.save()
            for result in results:
                if isinstance(result, (Handover, OutOfTime, llm.BudgetExceeded)):
                    raise result
                if isinstance(result, BaseException):
                    log.error('notice handling failed', exc_info=result)
                    self.problems.append(f'公告解析失败：{str(result)[:80]}')

    def _reuse(self, url: str) -> bool:
        """这篇公告以前读过并核验入库：直接复用，不再抓取和调用模型。"""
        with Session() as db:
            notice = db.scalar(select(Notice).where(Notice.url == url))
            if not notice:
                return False
            parties = list(db.execute(select(NoticeParty.company_id, NoticeParty.role).where(NoticeParty.notice_id == notice.id)).all())
            info = (notice.id, notice.kind, notice.title, notice.published_on, notice.deadline)
        buyer = next((cid for cid, role in parties if role == 'buyer'), None)
        for company_id, _ in parties:
            store.link_job(self.job_id, company_id, 'related')
        if self.plan.mode == 'find_buyers' and buyer:
            store.link_job(self.job_id, buyer, 'buyer')
            store.upsert_lead(buyer, info[0], self.conversation_id, f'{KIND_LABELS.get(info[1], "公告")}：{info[2][:60]}')
        emit(self.job_id, 'result', {'company_id': buyer, 'notice_id': info[0]})
        return True

    async def expand(self) -> list[str] | None:
        """线索不够就再来一轮：翻页、补充关键词，直到达到目标、没有新结果、轮数或时间用完。"""
        plan = self.plan
        with Session() as db:
            buyers = db.scalar(select(func.count()).select_from(JobCompany).where(
                JobCompany.job_id == self.job_id, JobCompany.role == 'buyer')) or 0
        target, round_no = self.settings.get('target_leads', 10), self.state.get('round', 1)
        if buyers >= target or round_no >= self.settings.get('max_rounds', 3) or time.monotonic() > self.deadline - 180:
            return None
        sites = self._procurement_sites()
        if not self._pending_searches(sites) and not self.state.get('extra_keywords'):
            async with self.tool('expand', '补充检索关键词') as info:
                more = await llm.structured(Keywords, f'产品：{plan.product}\n已用关键词：{"、".join(plan.keywords)}\n'
                                            '再给出 3-5 个招标公告中采购方可能使用的不同说法（品目名、设备名、服务名），不要重复已用关键词。')
                self.state['extra_keywords'] = [k for k in more.keywords if k not in plan.keywords][:5]
                info['summary'] = '、'.join(self.state['extra_keywords']) or '没有新关键词'
        if not self._pending_searches(sites):
            return None
        self.state['round'] = round_no + 1
        emit(self.job_id, 'progress', {'round': round_no + 1, 'buyers': buyers, 'target': target})
        return ['search', 'screen', 'read', 'expand']

    def _notice_prompt(self, text: str) -> str:
        return ('从下面的公告正文中抽取结构化信息。每个 quote 必须逐字复制正文里的连续片段；正文没有写明的字段留空。'
                '金额统一换算为元（如 3.8 万元 = 38000）。\n\n公告正文：\n' + text[:14000])

    def verified(self, checked: int, kept: int) -> None:
        stats = self.metrics.setdefault('verify', {'checked': 0, 'kept': 0})
        stats['checked'] += checked
        stats['kept'] += kept

    def _adopt(self, saved: dict, extract: NoticeExtract, plan: Plan, site: Site) -> None:
        store.record_site(site.id, 'captured', adopted=1)
        self.verified(saved['checked'], saved['kept'])
        for company_id in saved['company_ids']:
            store.link_job(self.job_id, company_id, 'related')
        buyer = saved['buyer_id']
        if plan.mode == 'find_buyers' and buyer:
            store.link_job(self.job_id, buyer, 'buyer')
            reason = f'{KIND_LABELS.get(extract.kind, "公告")}：{extract.title[:60]}'
            store.upsert_lead(buyer, saved['notice_id'], self.conversation_id, reason)
        if 'first_result_ms' not in self.metrics:
            self.metrics['first_result_ms'] = self.metrics.get('elapsed_ms', 0) + round((time.monotonic() - self.started) * 1000)
        emit(self.job_id, 'result', {'company_id': buyer or self.state.get('target_id'), 'notice_id': saved['notice_id']})

    async def enrich(self) -> None:
        """为本次找到的采购方补充工商信息（百度企业信息卡），已研究过的企业跳过。"""
        site = SITES['baidu']
        limit = self.settings.get('max_enrich', 5)
        if not limit or site not in enabled('business', self.settings):
            return
        with Session() as db:
            buyers = list(db.execute(select(Company.id, Company.name).join(JobCompany, JobCompany.company_id == Company.id)
                                     .where(JobCompany.job_id == self.job_id, JobCompany.role == 'buyer',
                                            Company.researched_at.is_(None))).all())[:limit]
        done = self.state.setdefault('enriched', [])
        folder = await self.folder()
        slots = asyncio.Semaphore(2)

        async def one(company_id: str, name: str) -> None:
            if company_id in done:
                return
            async with slots:
                self.check_time()
                async with self.tool('read_profile', f'补充“{name}”的工商信息', site.id) as info:
                    page = await crawl.capture(site.search_url(name, 0), folder, self.browser, scrolls=2)
                    store.record_site(site.id, page.status)
                    info['status'] = page.status
                    if page.ok:
                        source_id = store.save_source(page, site.id, 'business', self.job_id)
                        extract = await llm.structured(CompanyExtract, f'目标企业：{name}\n只抽取描述目标企业本身的信息，'
                                                       '每个 quote 必须逐字复制资料中的连续片段。\n\n'
                                                       f'资料：\n{page.text[:12000]}')
                        info['count'] = store.save_profile(company_id, extract, source_id, page.text) if extract.matched else 0
                        if extract.matched:
                            self.verified(store.provided_fields(extract), info['count'])
                with Session.begin() as db:
                    db.get(Company, company_id).researched_at = now()
                done.append(company_id)

        results = await asyncio.gather(*(one(cid, name) for cid, name in buyers), return_exceptions=True)
        self.save()
        for result in results:
            if isinstance(result, (OutOfTime, llm.BudgetExceeded)):
                raise result
            if isinstance(result, BaseException):
                log.error('enrich failed', exc_info=result)

    async def profile(self) -> None:
        """从工商来源（百度企业信息卡；启用时加爱企查详情页）抽取字段，逐条核验后写入。"""
        sources = self.state.setdefault('business_sources', [])
        aiqicha = SITES['aiqicha']
        skipped = aiqicha.id in self.state.get('skip_sites', []) or self.state.get('aiqicha_done')
        if aiqicha in enabled('business', self.settings) and not skipped:
            folder = await self.folder()
            async with self.tool('read_profile', f'在{aiqicha.name}读取工商信息', aiqicha.id) as info:
                page = await crawl.capture(aiqicha.search_url(self.plan.company, 0), folder, self.browser, scrolls=2)
                store.record_site(aiqicha.id, page.status)
                self.gate(page, aiqicha)
                link = next((l['url'] for l in page.links if aiqicha.is_detail(l['url'])
                             and self.plan.company in (l.get('text') or '')), '')
                if link:
                    page = await crawl.capture(link, folder, self.browser, scrolls=4)
                    self.gate(page, aiqicha)
                    if page.ok:
                        sources.append(store.save_source(page, aiqicha.id, 'business', self.job_id))
                info['status'] = page.status if link else 'not_found'
            self.state['aiqicha_done'] = True
            self.save()
        for source_id in sources:
            with Session() as db:
                text = db.get(Source, source_id).text
            async with self.tool('extract_profile', '核验工商信息') as info:
                extract = await llm.structured(CompanyExtract, f'目标企业：{self.plan.company}\n'
                                               '只抽取描述目标企业本身的信息，每个 quote 必须逐字复制资料中的连续片段。\n\n'
                                               f'资料：\n{text[:14000]}')
                info['count'] = store.save_profile(self.state['target_id'], extract, source_id, text) if extract.matched else 0
                if extract.matched:
                    self.verified(store.provided_fields(extract), info['count'])
        with Session.begin() as db:
            db.get(Company, self.state['target_id']).researched_at = now()

    async def answer(self) -> None:
        if self.plan.mode != 'chat':
            return
        context = self._answer_context()
        with Session.begin() as db:
            reply = Message(conversation_id=self.conversation_id, role='assistant', content='', job_id=self.job_id)
            db.add(reply)
            db.flush()
            reply_id = reply.id
        self.save(reply_message_id=reply_id)
        with Session() as db:
            question = db.get(Message, self.message_id).content
        prompt = (f'今天是 {date.today().isoformat()}。用户问题：{question}\n\n本次研究结果（JSON，均已核验原文）：\n{json.dumps(context, ensure_ascii=False)[:24000]}\n\n'
                  '用中文 Markdown 回答：先给结论，再按企业或公告列出要点（采购内容、金额、时间、角色），注明未取得的信息。'
                  '不要编造结果中没有的事实，不输出 JSON，不提及工具或模型。')
        parts: list[str] = []
        async for piece in llm.stream(prompt):
            parts.append(piece)
            emit(self.job_id, 'message.delta', {'message_id': reply_id, 'text': piece})
        content = ''.join(parts)
        if not content.strip():
            content = '没有生成回答，请重试。'
            self.problems.append('模型没有返回回答')
        with Session.begin() as db:
            db.get(Message, reply_id).content = content
            db.get(Conversation, self.conversation_id).updated_at = now()
        emit(self.job_id, 'message.completed', {'message_id': reply_id, 'content': content})

    async def _result_answer(self) -> None:
        """研究类任务不让模型写长文：用已核验的数据生成一句结论，完整结果表由研究报告卡展示。"""
        with Session() as db:
            rows = db.execute(select(JobCompany.role, func.count()).where(JobCompany.job_id == self.job_id)
                              .group_by(JobCompany.role)).all()
        roles = dict(rows)
        if self.plan.mode == 'company':
            content = (f'已整理 {self.plan.company} 的工商信息、采购与中标记录，涉及 {sum(roles.values()) - roles.get("target", 0)} 家相关单位，结果见下表。'
                       if roles.get('target') else f'没有找到与 {self.plan.company} 对应的企业。')
        else:
            buyers = roles.get('buyer', 0)
            content = (f'找到 {buyers} 家正在或近期采购的单位，结果见下表。' if buyers else
                       '这次没有找到与需求相符的采购公告，可以换个说法或放宽时间范围再试。')
        if self.problems:
            content += f' 有 {len(self.problems)} 项未完成，详见下方。'
        with Session.begin() as db:
            reply = Message(conversation_id=self.conversation_id, role='assistant', content=content, job_id=self.job_id)
            db.add(reply)
            db.flush()
            reply_id = reply.id
            db.get(Conversation, self.conversation_id).updated_at = now()
        self.save(reply_message_id=reply_id)
        emit(self.job_id, 'message.completed', {'message_id': reply_id, 'content': content})

    def _answer_context(self) -> dict:
        plan = self.plan
        with Session() as db:
            if plan.mode == 'chat':
                ids = select(JobCompany.company_id).join(Job, Job.id == JobCompany.job_id).where(
                    Job.conversation_id == self.conversation_id)
            else:
                ids = select(JobCompany.company_id).where(JobCompany.job_id == self.job_id)
            companies = list(db.scalars(select(Company).where(Company.id.in_(ids)).limit(40)))
            result = {'mode': plan.mode, 'problems': self.problems[:10],
                      'candidates_found': len(self.state.get('candidates', {})), 'companies': []}
            for company in companies:
                rows = db.execute(select(Notice, NoticeParty.role).join(NoticeParty, NoticeParty.notice_id == Notice.id)
                                  .where(NoticeParty.company_id == company.id)
                                  .order_by(Notice.published_on.desc()).limit(8)).all()
                lead = db.scalar(select(Lead).where(Lead.company_id == company.id))
                result['companies'].append({
                    'name': company.name, 'legal_person': company.legal_person, 'registered_capital': company.registered_capital,
                    'business_status': company.business_status, 'address': company.address, 'scope': company.scope[:200],
                    'lead_score': lead.score if lead else None,
                    'notices': [{'role': role, 'title': n.title, 'kind': KIND_LABELS.get(n.kind), 'date': n.published_on,
                                 'budget': n.budget, 'amount': n.amount, 'items': n.items, 'deadline': n.deadline,
                                 'contact': (n.quotes or {}).get('contact')} for n, role in rows]})
        return result
