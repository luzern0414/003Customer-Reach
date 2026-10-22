"""MCP 业务工具的短事务账本；网络在事务之外，暂停/失败不丢预算。"""
import asyncio
import hashlib
import json
import time
from sqlalchemy import select, func, text
from .db import Session, Job, ToolCall, now


def reserved_usage(row, key):
    args=row.arguments or {}
    if '_budgets_total' in args:return args['_budgets_total'].get(key,0)
    return args.get('_budgets',{}).get(key,0)*(row.attempts or 1)


def network_usage(db, job_id):
    """普通网页工具与 MCP 已预留额度共用口径；保守计入已发出而未完成的操作。"""
    calls=list(db.scalars(select(ToolCall).where(ToolCall.job_id==job_id)))
    searches=reads=0
    for row in calls:
        mcp='_budgets' in (row.arguments or {})
        searches+=reserved_usage(row,'searches') if mcp else int(row.tool=='search_accounts')*(row.attempts or 1)
        reads+=reserved_usage(row,'reads') if mcp else int(row.tool in {'fetch_source','fetch_browser'})*(row.attempts or 1)
    return {'searches':searches,'reads':reads}


async def run_bounded(job_id, tool, channel, arguments, ceiling, fn, timeout=120,
                      in_flight='operation_in_progress', exhausted='budget_exhausted', limits=None, reservation=None, strict_limits=()):
    """fn为异步只读操作；同 Job 同入参只发送一次，失败只在明确恢复后重试。"""
    from .research_tools import guard, emit, cancellable, Paused
    from .tool_views import tool_arguments, tool_result
    guard(job_id)
    operation = hashlib.sha256(json.dumps(['mcp-tools-1',job_id,tool,arguments],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with Session.begin() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        job=db.get(Job,job_id)
        old=db.scalar(select(ToolCall).where(ToolCall.operation_id==operation))
        resume=(job.metrics or {}).get('resume_epoch',0)
        retry=bool(old and old.status in {'paused','unavailable','rate_limited','running'} and resume>(old.last_attempt_epoch or 0))
        if old and old.status=='running' and not retry:return {'error':in_flight,'sources':[]}
        if old and not retry:
            return {**(old.result or {}),'reused':True}
        count=db.scalar(select(func.coalesce(func.sum(ToolCall.attempts),0)).where(ToolCall.job_id==job_id,ToolCall.channel==channel)) or 0
        if count>=ceiling:return {'error':exhausted,'sources':[]}
        reserved={}
        if limits is not None:
            calls=list(db.scalars(select(ToolCall).where(ToolCall.job_id==job_id)))
            for key, maximum in limits.items():
                spent=sum(reserved_usage(r,key) for r in calls)
                if key in {'searches','reads'}:
                    names={'search_accounts'} if key=='searches' else {'fetch_source','fetch_browser'}
                    spent+=sum((r.attempts or 1) for r in calls if r.tool in names and '_budgets' not in (r.arguments or {}))
                available=max(0,maximum-spent)
                wanted=(reservation or {}).get(key,0)
                if key in {'searches','requests',*strict_limits} and available<wanted:return {'error':exhausted,'sources':[]}
                reserved[key]=min(wanted,available)
            if reservation is not None:reservation.update(reserved)
        stored={**arguments,**({'_budgets':reserved} if limits is not None else {})}
        if limits is not None:stored['_budgets_total']={key:reserved_usage(old,key)+amount if old else amount for key,amount in reserved.items()}
        if old:
            old.attempts=(old.attempts or 1)+1;old.status='running';old.last_attempt_epoch=time.time()
            old.arguments=stored
            attempt=old.attempts
        else:
            db.add(ToolCall(job_id=job_id,tool=tool,channel=channel,operation_id=operation,arguments=stored,last_attempt_epoch=time.time()))
            attempt=1
    emit(job_id,'tool.started',{'tool':tool,'channel':channel,'operation_id':operation,'arguments':tool_arguments(arguments),'attempts':attempt,'status':'running'},'检索企业资料' if channel=='qcc_mcp' else '检索采购公告')
    started=time.monotonic();status='completed';result={}
    try:
        result=await cancellable(fn(),job_id,timeout)
        if not isinstance(result,dict):result={'error':'bad_tool_output','sources':[]}
        if result.get('error'):status='unavailable'
        return result
    except (Paused,asyncio.CancelledError):
        result={'error':'operation_paused','sources':[]};status='paused'
        raise
    except Exception as exc:
        code=getattr(exc,'code','')
        result={'error':code if isinstance(code,str) and code.startswith('qcc_') else 'mcp_timeout' if isinstance(exc,TimeoutError) else 'mcp_unavailable','sources':[]}
        status='unavailable'
        return result
    finally:
        elapsed=round((time.monotonic()-started)*1000)
        with Session.begin() as db:
            row=db.scalar(select(ToolCall).where(ToolCall.operation_id==operation))
            row.status=status;row.result=result;row.elapsed_ms=(row.elapsed_ms or 0)+elapsed;row.updated_at=now()
        emit(job_id,'tool.finished',{'tool':tool,'channel':channel,'operation_id':operation,'status':status,'attempts':attempt,'elapsed_ms':elapsed,**tool_result(result)},'已取得检索结果' if result.get('sources') else '本次检索未取得证据')
