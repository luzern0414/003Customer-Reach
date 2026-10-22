import asyncio
import uuid
from sqlalchemy import select


def job():
    from app.db import Session, Conversation, Job
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush()
        row=Job(conversation_id=c.id,client_token=uuid.uuid4().hex,prompt='研究软件采购');db.add(row);db.flush()
        return row.id


def test_failed_call_reuses_until_explicit_resume(client):
    from app.mcp_tools import run_bounded
    from app.db import Session,ToolCall
    jid=job();calls=[]
    async def fn():
        calls.append(1)
        return {'error':'qcc_timeout','sources':[]}
    async def run():
        return [await run_bounded(jid,'lookup','qcc_mcp',{},2,fn),await run_bounded(jid,'lookup','qcc_mcp',{},2,fn)]
    results=asyncio.run(run())
    assert len(calls)==1 and results[1]['reused']
    with Session() as db:
        row=db.scalar(select(ToolCall).where(ToolCall.job_id==jid))
        assert row.status=='unavailable' and row.elapsed_ms>=0


def test_concurrent_calls_reserve_once_and_budget_is_job_scoped(client):
    from app.mcp_tools import run_bounded
    calls=[];jid=job()
    async def fn():
        calls.append(1);await asyncio.sleep(.04)
        return {'error':'','sources':[]}
    async def run():
        a=await asyncio.gather(*[run_bounded(jid,'search_tenders','bidresearch',{'keywords':['软件']},1,fn) for _ in range(2)])
        b=await run_bounded(jid,'search_tenders','bidresearch',{'keywords':['AI']},1,fn)
        return a,b
    a,b=asyncio.run(run())
    assert len(calls)==1 and any(r.get('error')=='operation_in_progress' for r in a)
    assert b['error']=='budget_exhausted'


def test_cancelled_call_is_settled_paused(client):
    from app.mcp_tools import run_bounded
    from app.db import Session,ToolCall
    jid=job()
    async def fn():raise asyncio.CancelledError()
    async def run():
        try:await run_bounded(jid,'lookup','qcc_mcp',{},1,fn)
        except asyncio.CancelledError:pass
    asyncio.run(run())
    with Session() as db:
        assert db.scalar(select(ToolCall).where(ToolCall.job_id==jid)).status=='paused'


def test_resume_accumulates_actual_reserved_pools_even_if_later_read_grant_shrinks(client):
    import time
    from app.mcp_tools import run_bounded,network_usage
    from app.db import Session,Job
    jid=job()
    async def fn():return {'error':'mcp_timeout','sources':[]}
    async def run():
        limits={'searches':3,'reads':5,'requests':30}
        await run_bounded(jid,'search_tenders','bidresearch',{},3,fn,limits=limits,reservation={'searches':1,'reads':4,'requests':10})
        with Session.begin() as db:db.get(Job,jid).metrics={'resume_epoch':time.time()+1}
        await run_bounded(jid,'search_tenders','bidresearch',{},3,fn,limits=limits,reservation={'searches':1,'reads':4,'requests':10})
    asyncio.run(run())
    with Session() as db:assert network_usage(db,jid)=={'searches':2,'reads':5}


def test_normal_reads_and_mcp_share_atomic_pool(client):
    from app.mcp_tools import run_bounded,network_usage
    from app.db import Session,ToolCall
    jid=job()
    with Session.begin() as db:
        db.add(ToolCall(job_id=jid,tool='fetch_source',channel='official',operation_id=uuid.uuid4().hex,arguments={},status='completed',attempts=2))
    grant={'searches':1,'reads':4,'requests':12}
    async def fn():return {'sources':[]}
    asyncio.run(run_bounded(jid,'search_tenders','bidresearch',{},2,fn,limits={'searches':3,'reads':3,'requests':24},reservation=grant))
    assert grant['reads']==1
    with Session() as db:assert network_usage(db,jid)=={'searches':1,'reads':3}
