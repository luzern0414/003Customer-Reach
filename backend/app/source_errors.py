"""公开来源的安全错误分类；只携带类别与冷却信息，不保存供应商原始错误正文。"""
import re
import math
import time
from email.utils import parsedate_to_datetime

class QccError(Exception):
    def __init__(self, code, retry_after=None):
        self.code=code; self.retry_after=retry_after
        super().__init__(code)

def qcc_error(value, headers=None):
    if isinstance(value, QccError):
        return value
    while isinstance(value,BaseExceptionGroup) and value.exceptions:value=value.exceptions[0]
    response = getattr(value, 'response', None)
    status = getattr(value, 'status_code', None) or getattr(response, 'status_code', None)
    if isinstance(value, int):
        status = value
    chain=[];current=value;seen=set()
    while isinstance(current,BaseException) and id(current) not in seen and len(chain)<6:
        seen.add(id(current));chain.append(current)
        current=current.__cause__ or current.__context__
    text = ' '.join([str(value),*[type(item).__name__ for item in chain]]).lower()
    if status in (401, 403) or 'invalid_token' in text or 'unauthorized' in text:
        code = 'qcc_invalid_token'
    elif status == 429 or re.search(r'\b429\b|rate.?limit|too many requests', text):
        code = 'qcc_rate_limited'
    elif 'quota' in text or 'points exhausted' in text or '积分不足' in text:
        code = 'qcc_quota_exhausted'
    elif 'pagination' in text or '翻页' in text:
        code = 'qcc_pagination_unavailable'
    elif 'timeout' in text or 'timed out' in text:
        code = 'qcc_timeout'
    elif any(term in text for term in ('brokenresourceerror','closedresourceerror','connecterror','networkerror')):
        code = 'qcc_unavailable'
    elif 'invalid json' in text or 'protocol' in text or 'parse error' in text:
        code = 'qcc_invalid_response'
    elif re.fullmatch(r'qcc_[a-z_]+', text):
        code = text
    elif 'tool' in text and ('unknown' in text or 'not allowed' in text or 'unmapped' in text):
        code = 'qcc_tool_not_allowed'
    else:
        code = 'qcc_invalid_response'
    retry = (headers or {}).get('retry-after') if headers else None
    if retry is None and response is not None:
        retry = getattr(response, 'headers', {}).get('retry-after')
    return QccError(code, retry_delay(retry) if retry is not None else None)


def retry_delay(value: str | None) -> float:
    """value为Retry-After秒数或HTTP日期，空/无效时60秒；返回至少60秒，不缩短服务端冷却。"""
    try:
        seconds=float(value)
    except (TypeError, ValueError):
        try:
            seconds=parsedate_to_datetime(value).timestamp()-time.time()
        except (TypeError, ValueError, OverflowError):
            seconds=60
    return max(60,seconds) if math.isfinite(seconds) else 60


class SourceRateLimit(Exception):
    """限流类别；scope仅provider/site，host只用于站点冷却，不携带请求正文。"""
    def __init__(self, scope: str='provider', delay: float=60, host: str=''):
        """scope指定限制范围，delay为非负秒数，host为空表示供应商；异常文字固定且不含密钥。"""
        self.scope,self.delay,self.host=scope,max(60,delay),host
        super().__init__(scope+'_rate_limited')


def source_limit(exc: Exception) -> SourceRateLimit | None:
    """exc为工具异常或嵌套异常组；仅429/已分类限流返回安全对象，其余返回None。"""
    if isinstance(exc,SourceRateLimit):return exc
    for child in getattr(exc,'exceptions',[]):
        found=source_limit(child)
        if found:return found
    response=getattr(exc,'response',None)
    if getattr(exc,'status_code',None)==429 or getattr(response,'status_code',None)==429:
        return SourceRateLimit(delay=retry_delay(getattr(response,'headers',{}).get('retry-after')))
    # 免费MCP额度也可能在initialize阶段用JSON-RPC -32000抛出，而不是工具is_error或HTTP429。
    message=getattr(getattr(exc,'error',None),'message','')
    if isinstance(message,str) and (limited:=mcp_limit(message)):return limited
    return None


def mcp_limit(text: str) -> SourceRateLimit | None:
    """text只在MCP错误响应时分类；返回限流和明确秒数，不回传原始正文，无匹配返回None。"""
    if not re.search(r'\b429\b|rate.?limit|too many requests',text,re.I):return None
    match=re.search(r'(?:retry[ -]?after|retry in)\s*[:=]?\s*(\d+)\s*(?:s|seconds)?',text,re.I)
    return SourceRateLimit(delay=retry_delay(match.group(1) if match else None))
