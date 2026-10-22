"""已登记Exa MCP搜索/读取适配器；不使用浏览器搜索或绕过站点访问限制。"""
import asyncio
import json
import re
import hashlib
from datetime import timedelta
from urllib.parse import urlparse
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from .db import Session, Evidence, serialize
from .source_errors import mcp_limit

from .config import exa_mcp_url


async def call_exa(tool: str, arguments: dict) -> str:
    """调用固定tool及非空arguments；返回工具文本，限流/传输失败抛异常，不回显密钥。"""
    async with streamable_http_client(exa_mcp_url()) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=45) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            text = '\n'.join(item.text for item in result.content if hasattr(item, 'text'))
            if result.is_error and (limited:=mcp_limit(text)):
                raise limited
            if result.is_error or re.search(r'UNSUPPORTED_URL|CRAWL_ERROR|FETCH_ERROR', text):
                raise RuntimeError('Exa返回受限地址或读取错误')
            return text


def split_sources(text: str) -> list[dict]:
    """将实际搜索text拆为URL来源；空文本返回空列表，缺URL的段落不伪造来源。"""
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and isinstance(payload.get('results'), list):
            return [{'url': x['url'], 'title': x.get('title', x['url']), 'body': x.get('text', x.get('content', ''))}
                    for x in payload['results'] if x.get('url') and x.get('text', x.get('content'))]
    except (ValueError, TypeError):
        pass
    sources = []
    for block in re.split(r'(?m)(?=^(?:Title:|# )[^\n]+\n)', text):
        match = re.search(r'(?m)^URL:\s*(https?://\S+)', block)
        if match:
            title = block.splitlines()[0].removeprefix('Title:').lstrip('# ').strip()
            sources.append({'url': match.group(1).rstrip('.,'), 'title': title, 'body': block})
    return sources


def archive_sources(job_id: str, items: list[dict], kind: str, channel: str='official') -> list[dict]:
    """保存实际工具items为证据；job_id、kind非空，返回可引用ID及限长正文，缺项跳过。"""
    records = []
    with Session.begin() as db:
        for item in items:
            uri = urlparse(item['url'])
            if uri.scheme not in {'http', 'https'} or uri.username or uri.hostname in {'localhost', '127.0.0.1'}:
                continue
            if not item.get('body'):
                continue
            from sqlalchemy import select
            from .knowledge import expires
            digest=hashlib.sha256(item['body'].encode()).hexdigest()
            row=db.scalar(select(Evidence).where(Evidence.job_id==job_id,Evidence.url==item['url'],Evidence.content_hash==digest))
            if row:
                records.append(serialize(row));continue
            row = Evidence(job_id=job_id, url=item['url'], title=item['title'], body=item['body'], kind=kind,
                           channel=channel,content_hash=digest,published_at=item.get('published_at'),expires_at=expires(30),source_meta=item.get('source_meta') or {'origin':'agent'})
            db.add(row)
            db.flush()
            records.append(serialize(row))
    return records
