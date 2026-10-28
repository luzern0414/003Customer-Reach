"""LuzCrawl 适配层：系统唯一的采集通道。

只通过 CLI 子进程调用（node scripts/luz-crawl.mjs ...），解析 stdout 末尾的 JSON 并读取证据目录中的
raw/content.json。登录或验证码返回 awaiting_user，由用户在 Edge 中处理后调用 resume；限流不重试。
"""
import asyncio
import contextlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import LUZ_CRAWL

SCRIPT = LUZ_CRAWL / 'scripts/luz-crawl.mjs'
TIMEOUT = 600
# 同时运行的 LuzCrawl 进程数；同站排队与节流由 LuzCrawl 自身负责。
_SLOTS = asyncio.Semaphore(int(os.getenv('DEALRADAR_CRAWL_SLOTS', '3')))
# 未指定已连接 Edge 时 LuzCrawl 启动无头 Edge，多个进程共用同一资料目录会互相关闭，只能串行。
_HEADLESS = asyncio.Semaphore(1)
_ERRORS = [('launchPersistentContext', '浏览器启动失败：Edge 未连接 LuzCrawl 扩展或资料目录被占用'),
           ('rate_limited', '网站限制访问频率，已停止访问该站'),
           ('Timeout', '页面加载超时')]


_NULL = contextlib.nullcontext()


class CrawlError(Exception):
    """LuzCrawl 不可用或输出无法解析。"""


@dataclass
class Page:
    """一次页面读取的结果。status: captured/partial/awaiting_user/blocked/failed/skipped。"""
    url: str
    status: str
    title: str = ''
    text: str = ''
    links: list = field(default_factory=list)
    folder: str = ''
    stop_reason: str = ''
    task_id: str = ''
    elapsed_ms: int = 0
    error: str = ''

    @property
    def ok(self) -> bool:
        return self.status in ('captured', 'partial') and bool(self.text.strip())

    @property
    def needs_user(self) -> bool:
        return self.status == 'awaiting_user'


_JSON_START = re.compile(r'^(\{|\[\s*[\[{\]"]|\[$)', re.M)


def parse_output(stdout: str) -> dict:
    """stdout 中混有 “[luz-crawl] …” 进度行；从第一处 JSON 对象或数组的起始行解析到末尾。"""
    text = stdout.strip()
    match = _JSON_START.search(text)
    if not match:
        raise CrawlError('LuzCrawl 没有返回结果：' + text[-300:])
    try:
        return json.loads(text[match.start():])
    except ValueError as exc:
        raise CrawlError('LuzCrawl 输出无法解析') from exc


def reason(error: str) -> str:
    """把 LuzCrawl / Playwright 的原始错误转为可读原因。"""
    return next((text for key, text in _ERRORS if key in error), error.splitlines()[0][:120] if error else '')


async def run(*args: str, timeout: int = TIMEOUT) -> dict:
    if not SCRIPT.exists():
        raise CrawlError(f'未找到 LuzCrawl：{SCRIPT}')
    headless = args[0] not in ('doctor', 'begin', 'cancel', 'pending') and '--profile' not in args
    async with _SLOTS, (_HEADLESS if headless else _NULL):
        process = await asyncio.create_subprocess_exec(
            'node', str(SCRIPT), *args, cwd=str(LUZ_CRAWL),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.wait()
            raise
    output = stdout.decode('utf-8', 'replace')
    if not output.strip():
        raise CrawlError('LuzCrawl 无输出：' + stderr.decode('utf-8', 'replace')[-300:])
    return parse_output(output)


def read_page(result: dict) -> Page:
    """把 capture/continue/batch 单项结果转为 Page，正文以证据目录中的 content.json 为准。"""
    folder = result.get('folder') or ''
    content = {}
    path = Path(folder) / 'raw/content.json' if folder else None
    if path and path.exists():
        content = json.loads(path.read_text(encoding='utf-8'))
    check = content.get('url_check') or result.get('url_check') or {}
    status = result.get('status') or content.get('status') or 'failed'
    text = content.get('text') or ''
    if status in ('captured', 'partial') and check and not check.get('valid_content', True):
        status, text = 'blocked', ''
    return Page(
        url=check.get('resolved') or result.get('resolved_url') or result.get('url') or content.get('requested_url', ''),
        status=status, title=content.get('title') or '', text=text,
        links=[link for link in content.get('links') or [] if link.get('url')], folder=folder,
        stop_reason=result.get('stop_reason') or content.get('stop_reason') or '',
        task_id=result.get('task_id') or '', elapsed_ms=int(result.get('elapsed_ms') or content.get('elapsed_ms') or 0),
        error=reason(str(result.get('error') or '')))


def _profile_args(profile: str) -> list[str]:
    return ['--profile', profile] if profile else []


async def doctor() -> dict:
    try:
        return await run('doctor', timeout=120)
    except (CrawlError, asyncio.TimeoutError) as exc:
        return {'ready': False, 'state': 'unavailable', 'hint': str(exc)}


_default_profile: list[str] = []


async def default_profile() -> str:
    """已连接 Edge 的 context_id，用真实浏览器多标签读取。取不到时返回空串且不缓存，下次重新查询。"""
    if not _default_profile:
        daemon = (await doctor()).get('daemon') or {}
        connected = [p.get('contextId') for p in daemon.get('profiles') or [] if p.get('extensionConnected')]
        profile = daemon.get('context_id') or (connected[0] if connected else '')
        if not profile:
            return ''
        _default_profile.append(profile)
    return _default_profile[0]


async def begin(title: str, root: Path) -> str:
    """为一个任务创建 LuzCrawl 任务目录，返回绝对路径。"""
    result = await run('begin', title[:60] or '研究任务', '--out', str(root), '--new', timeout=60)
    return result['folder']


async def capture(url: str, folder: str, profile: str = '', scrolls: int = 6, timeout: int = TIMEOUT) -> Page:
    try:
        result = await run('capture', url, '--out', folder, '--scrolls', str(scrolls), *_profile_args(profile), timeout=timeout)
    except CrawlError as exc:
        return Page(url=url, status='failed', error=str(exc))
    except asyncio.TimeoutError:
        return Page(url=url, status='failed', error='读取超时')
    page = read_page(result)
    page.url = page.url or url
    return page


async def search(platform: str, query: str, folder: str, profile: str = '') -> Page:
    """在平台站内搜索（--read 0），返回搜索结果页；候选链接放在 links。"""
    try:
        result = await run('search', platform, query, '--read', '0', '--out', folder, *_profile_args(profile))
    except CrawlError as exc:
        return Page(url=platform, status='failed', error=str(exc))
    except asyncio.TimeoutError:
        return Page(url=platform, status='failed', error='检索超时')
    attempts = [a for a in result.get('attempts') or [] if a.get('folder')]
    page = read_page({**(attempts[-1] if attempts else {}), 'status': result.get('status'),
                      'task_id': result.get('task_id', ''), 'stop_reason': result.get('stop_reason', '')})
    page.url = result.get('search_url') or page.url
    candidates = [{'text': c.get('text', ''), 'url': c['url']} for c in result.get('candidates') or [] if c.get('url')]
    if candidates:
        page.links = candidates
    if result.get('requires_user'):
        page.status = 'awaiting_user'
    return page


async def resume(task_id: str, profile: str = '') -> Page:
    try:
        return read_page(await run('continue', task_id, *_profile_args(profile)))
    except (CrawlError, asyncio.TimeoutError) as exc:
        return Page(url='', status='failed', error=str(exc) or '续接超时')


async def cancel(task_id: str) -> None:
    try:
        await run('cancel', task_id, timeout=60)
    except (CrawlError, asyncio.TimeoutError):
        pass
