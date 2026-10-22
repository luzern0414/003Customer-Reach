"""已出现明确robots限制的平台读取检查；复用Protego，不模拟搜索引擎或改写URL绕限制。"""
import asyncio
import time
from urllib.parse import urlsplit
import httpx
from protego import Protego
from .service import ServiceError
from .source_errors import SourceRateLimit,retry_delay

USER_AGENT='ClientReach/0.2 PublicResearch'
POLICIES={}
LOCKS={}


def requires_policy(url: str) -> bool:
    """url为实际待读地址；1688及新接入平台/子域读取与缓存均检查同源robots，其他来源沿原规则。"""
    host=(urlsplit(url).hostname or '').lower()
    return any(host==domain or host.endswith('.'+domain) for domain in ['1688.com','b2b168.com','jc001.cn'])


async def reading_delay(url: str) -> float:
    """url为已校验公网URL；注册平台读取前核验同源robots，返回至少1秒间隔；拒绝/未知规则抛安全业务错误。

    普通来源保持既有1秒策略；robots缓存1小时，失败不缓存，3xx/5xx/大文件不自动追随或绕过。
    """
    parsed=urlsplit(url)
    host=(parsed.hostname or '').lower()
    if not requires_policy(url):return 1
    origin=f'{parsed.scheme}://{parsed.netloc}'
    lock=LOCKS.setdefault(origin,asyncio.Lock())
    async with lock:
        cached=POLICIES.get(origin)
        if not cached or cached[0]<=time.monotonic():
            async with httpx.AsyncClient(timeout=10,follow_redirects=False,headers={'User-Agent':USER_AGENT}) as client:
                try:response=await client.get(origin+'/robots.txt')
                except httpx.HTTPError:raise ServiceError('site_policy_unavailable') from None
            if response.status_code==429:raise SourceRateLimit('site',retry_delay(response.headers.get('retry-after')),host)
            if response.status_code in {404,410}:policy=Protego.parse('')
            elif response.status_code==200 and len(response.content)<=512_000:policy=Protego.parse(response.text)
            else:raise ServiceError('site_policy_unavailable')
            POLICIES[origin]=(time.monotonic()+3600,policy)
        else:policy=cached[1]
    if not policy.can_fetch(url,USER_AGENT):raise ServiceError('site_robots_disallowed')
    return max(1,policy.crawl_delay(USER_AGENT) or 1)
