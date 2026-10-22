"""网页检索兜底：Exa 限流或失败时，经内置 OpenCLI（临时无头 Edge + CDP）执行百度/搜狗检索。

输出经 Pydantic 校验：标题、http(s) 地址、摘要长度与日期格式不合格的行被丢弃，不进入证据。
同一时间只启动一个检索浏览器；被搜索引擎要求验证时返回 verification_required，不尝试绕过。
"""
import asyncio
import json
import re
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ValidationError, field_validator
from .config import ROOT
from .observability import logger

LOG = logger('agent')
RUNNER = ROOT / 'tools/browser/search-edge.cjs'
SEARCH_LOCK = threading.Lock()
BAD_URL = re.compile(r'nourl\.ubs\.baidu\.com|baidu\.com/(?:link|baidu\.php)|sogou\.com/link')


class WebSearchRow(BaseModel):
    """一条自然检索结果；只保留可公开访问的原始地址。"""
    engine: Literal['baidu', 'sogou']
    title: str = Field(min_length=2, max_length=300)
    url: str = Field(min_length=8, max_length=2000)
    snippet: str = Field(default='', max_length=600)
    published_at: str = Field(default='', max_length=10)

    @field_validator('url')
    @classmethod
    def public_url(cls, value: str) -> str:
        """仅接受http(s)原始地址，搜索引擎跳转链接与占位链接拒绝。"""
        if not re.match(r'^https?://', value) or BAD_URL.search(value): raise ValueError('not_original_url')
        return value

    @field_validator('published_at')
    @classmethod
    def date_format(cls, value: str) -> str:
        """日期只接受YYYY-MM-DD，其他格式置空而不是猜测。"""
        return value if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value or '') else ''


class WebSearchResult(BaseModel):
    """单个检索词的结果；error为空表示检索成功（可能0条）。"""
    query: str
    engine: str = ''
    rows: list[WebSearchRow] = Field(default_factory=list)
    error: str = ''
    rejected: int = 0


def available() -> bool:
    """无参数；内置OpenCLI、检索脚本与Node均存在且未被CLIENTREACH_SEARCH_FALLBACK=false关闭时可用。"""
    import os
    if os.getenv('CLIENTREACH_SEARCH_FALLBACK', '').lower() in {'0', 'false', 'off'}: return False
    return RUNNER.is_file() and (ROOT / 'vendor/opencli/dist/src/main.js').is_file() and bool(shutil.which('node'))


def opencli_search(queries: list[str], limit: int = 8, timeout: int = 150) -> list[WebSearchResult]:
    """queries为检索词（最多6个）、limit为每词条数；同步执行，返回逐词校验后的结果，整体失败时每个词带error。"""
    queries = [q.strip()[:200] for q in queries if q and q.strip()][:6]
    if not queries: return []
    if not available(): return [WebSearchResult(query=q, error='search_runtime_unavailable') for q in queries]
    import subprocess
    with SEARCH_LOCK, tempfile.TemporaryDirectory(prefix='cr-search-') as folder:
        try:
            proc = subprocess.run(['node', str(RUNNER), folder, str(limit), *queries], capture_output=True, timeout=timeout, cwd=str(ROOT))
        except subprocess.TimeoutExpired:
            return [WebSearchResult(query=q, error='timeout') for q in queries]
    if proc.returncode != 0:
        LOG.warning('opencli_search_failed', extra={'details': {'stderr': proc.stderr.decode('utf-8', 'replace')[:200]}})
        return [WebSearchResult(query=q, error='search_failed') for q in queries]
    try:
        payload = json.loads(proc.stdout.decode('utf-8', 'replace'))
    except ValueError:
        return [WebSearchResult(query=q, error='bad_output') for q in queries]
    results = []
    for item in payload.get('results', []):
        rows, rejected = [], 0
        for raw in item.get('rows', []):
            try:
                rows.append(WebSearchRow.model_validate({k: raw.get(k, '') for k in ('engine', 'title', 'url', 'snippet', 'published_at')}))
            except ValidationError:
                rejected += 1
        results.append(WebSearchResult(query=item.get('query', ''), engine=item.get('engine', ''), rows=rows, error=item.get('error', ''), rejected=rejected))
    return results


async def opencli_search_async(queries: list[str], limit: int = 8) -> list[WebSearchResult]:
    """异步包装：在线程中执行检索，不阻塞事件循环。"""
    return await asyncio.to_thread(opencli_search, queries, limit)
