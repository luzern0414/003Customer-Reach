"""工具失败恢复的真实账本/事务回归；网络故障注入仅用于验证预算与重试语义。"""
import asyncio
import time
import uuid
from sqlalchemy import select
from app.db import Session,Job,ToolCall,JobEvent
from app.research_tools import ToolBroker
from app.service import ServiceError
from app.source_errors import SourceRateLimit,retry_delay,mcp_limit,source_limit
import httpx
from email.utils import formatdate


def make_job(client):
    """client为隔离TestClient；创建任务后返回真实ID，不发外部模型或网络。"""
    conv=client.post('/api/conversations').json()['id']
    return client.post('/api/conversations/'+conv+'/messages',json={'content':'查深圳灯具店','client_token':uuid.uuid4().hex}).json()['id']


def resume(client,job):
    """job为隔离任务ID；模拟图的失败终态后经真实API恢复，返回Response。"""
    with Session.begin() as db:db.get(Job,job).status='failed'
    return client.post('/api/jobs/'+job+'/resume')


def test_failed_search_retries_after_explicit_resume_and_reuses_success(client,monkeypatch):
    job=make_job(client);calls=[]
    async def search(self,args):
        calls.append(args)
        if len(calls)==1:raise TimeoutError('injected timeout')
        return {'sources':[],'fixture':'recovered'}
    monkeypatch.setattr(ToolBroker,'search',search)
    options={'max_searches':2,'max_reads':0,'enabled_channels':['official']}
    args={'query':'深圳 灯具门店','channel':'official'}
    async def scenario():
        broker=ToolBroker(job,options,{})
        assert (await broker.execute('search_accounts',args)).get('error')
        assert (await broker.execute('search_accounts',args))['reused']
        assert len(calls)==1
        assert resume(client,job).status_code==200
        assert (await broker.execute('search_accounts',args))['fixture']=='recovered'
        assert (await broker.execute('search_accounts',args))['reused']
    asyncio.run(scenario())
    assert len(calls)==2
    with Session() as db:
        rows=list(db.scalars(select(ToolCall).where(ToolCall.job_id==job)))
        assert len(rows)==1 and rows[0].attempts==2 and rows[0].status=='completed'
        reused=list(db.scalars(select(JobEvent).where(JobEvent.job_id==job,JobEvent.event_type=='tool.reused')))
        assert reused[0].payload['status']=='unavailable'


def test_failed_attempts_cannot_bypass_budget(client,monkeypatch):
    job=make_job(client);calls=[]
    async def search(self,args):calls.append(args);raise TimeoutError('injected timeout')
    monkeypatch.setattr(ToolBroker,'search',search)
    options={'max_searches':2,'max_reads':0,'enabled_channels':['official']}
    async def scenario():
        broker=ToolBroker(job,options,{})
        args={'query':'深圳 灯具门店','channel':'official'}
        assert (await broker.execute('search_accounts',args)).get('error')
        assert resume(client,job).status_code==200
        assert (await broker.execute('search_accounts',args)).get('error')
        assert resume(client,job).status_code==200
        assert (await broker.execute('search_accounts',args))['error']=='budget_exhausted'
    asyncio.run(scenario());assert len(calls)==2


def test_source_limit_classification_and_server_delay():
    assert retry_delay('300')==300
    assert 299<=retry_delay(formatdate(time.time()+300,usegmt=True))<=300
    assert retry_delay(None)==60 and retry_delay('nan')==60
    limited=mcp_limit('Too many requests. Retry-After: 180 seconds SECRET')
    assert limited.delay==180 and str(limited)=='provider_rate_limited'
    assert mcp_limit('CRAWL_ERROR access restricted') is None
    response=httpx.Response(429,headers={'Retry-After':'240'},request=httpx.Request('GET','https://example.com'))
    error=httpx.HTTPStatusError('sensitive body',request=response.request,response=response)
    assert source_limit(ExceptionGroup('transport',[error])).delay==240


def test_site_limit_does_not_block_other_host_and_respects_cooldown(client,monkeypatch):
    job=make_job(client);calls=[]
    async def fetch(self,args):
        calls.append(args['url'])
        if 'example.com' in args['url']:raise SourceRateLimit('site',180,'example.com')
        return {'sources':[],'fixture':'other-host'}
    monkeypatch.setattr(ToolBroker,'fetch',fetch)
    async def scenario():
        broker=ToolBroker(job,{'max_reads':3,'max_searches':0,'enabled_channels':['official']},{})
        assert (await broker.execute('fetch_source',{'url':'https://example.com/a','channel':'official'}))['error']=='site_rate_limited'
        assert resume(client,job).status_code==200
        assert (await broker.execute('fetch_source',{'url':'https://example.com/b','channel':'official'}))['error']=='site_rate_limited'
        assert (await broker.execute('fetch_source',{'url':'https://example.org/a','channel':'official'}))['fixture']=='other-host'
        with Session() as db:
            rows=list(db.scalars(select(ToolCall).where(ToolCall.job_id==job)))
            assert len(rows)==2 and sum(x.attempts for x in rows)==2
            limited=next(x for x in rows if x.status=='rate_limited')
            assert limited.retry_after_epoch-time.time()>175
    try:asyncio.run(scenario())
    finally:
        with Session.begin() as db:
            for row in db.scalars(select(ToolCall).where(ToolCall.job_id==job)):row.retry_after_epoch=0


def test_provider_cooldown_blocks_new_operations_without_spending_budget(client,monkeypatch):
    job=make_job(client);calls=[]
    async def search(self,args):calls.append(args);raise SourceRateLimit(delay=300)
    monkeypatch.setattr(ToolBroker,'search',search)
    async def scenario():
        broker=ToolBroker(job,{'max_searches':4,'max_reads':0,'enabled_channels':['official']},{})
        assert (await broker.execute('search_accounts',{'query':'深圳 灯具门店','channel':'official'}))['error']=='provider_rate_limited'
        assert (await broker.execute('search_accounts',{'query':'深圳 家居门店','channel':'official'}))['error']=='provider_rate_limited'
        response=resume(client,job)
        assert response.status_code==409 and '秒后' in response.json()['error']
        with Session() as db:
            rows=list(db.scalars(select(ToolCall).where(ToolCall.job_id==job)))
            assert len(rows)==1 and rows[0].attempts==1 and rows[0].retry_after_epoch-time.time()>295
    try:asyncio.run(scenario());assert len(calls)==1
    finally:
        with Session.begin() as db:
            for row in db.scalars(select(ToolCall).where(ToolCall.job_id==job)):row.retry_after_epoch=0


def test_actual_graph_resume_retries_search_already_passed_before_answer(client,monkeypatch):
    from app import agent
    from app.research_tools import Paused
    from app.gateway import archive_sources
    job=make_job(client);calls=[];extractions=[];answers=[]
    with Session.begin() as db:db.get(Job,job).prompt='我们销售吊灯，请寻找深圳灯具经销商'
    profile={'products':[{'name':'吊灯'}],'region':'深圳','questions':[]}
    async def context(state):return {}
    async def product(state):return {'profile':profile}
    async def plan(state):return {'plan':{'target_roles':['retailer']},'steps':[{'channel':'official','query':'深圳 灯具门店'}],'cursor':0}
    async def decide(state):return {'pending_call':{'name':'search_accounts','args':{'query':'深圳 灯具门店','channel':'official'},'tool_call_id':'fixture-call'}}
    async def search(self,args):
        calls.append(args)
        if len(calls)==1:raise TimeoutError('fixture transient timeout')
        sources=archive_sources(job,[{'url':'https://example.org/recovery-fixture','title':'隔离恢复资料','body':'仅用于恢复测试，不是客户事实'}],'搜索摘录')
        return {'sources':sources}
    async def fetch(self,args):return {'sources':[]}
    async def extract(state):extractions.append(list(state.get('source_ids',[])));return {'candidates':[]}
    async def save(state):return {}
    async def gap(state):return {'cursor':len(state['steps'])}
    async def answer(state):
        answers.append(True)
        if len(answers)==1:raise Paused()
        return {'answer':'恢复测试完成'}
    async def learn(state):return {}
    for name,fn in [('load_context',context),('profile_node',product),('plan_node',plan),('decide_node',decide),
        ('extract_node',extract),('save_node',save),('gap_node',gap),('answer_node',answer),('learn_node',learn)]:monkeypatch.setattr(agent,name,fn)
    monkeypatch.setattr(ToolBroker,'search',search);monkeypatch.setattr(ToolBroker,'fetch',fetch)
    client.patch('/api/settings',json={'max_searches':3,'max_reads':3})
    asyncio.run(agent.run_job(job))
    assert client.get('/api/jobs/'+job).json()['status']=='paused' and calls and extractions==[[]]
    assert client.post('/api/jobs/'+job+'/resume').status_code==200
    asyncio.run(agent.run_job(job))
    final=client.get('/api/jobs/'+job).json()
    assert len(calls)==2 and len(extractions)==2 and extractions[-1]
    assert final['status']=='partial' and final['metrics']['source_ids']
    with Session() as db:
        row=db.scalar(select(ToolCall).where(ToolCall.job_id==job,ToolCall.tool=='search_accounts'))
        assert row.status=='completed' and row.attempts==2


def test_parallel_same_site_rechecks_cooldown_before_http(client,monkeypatch):
    from app import research_tools
    from app.gateway import archive_sources
    job=make_job(client);calls=[]
    async def response(request):
        calls.append(str(request.url))
        return httpx.Response(429,headers={'Retry-After':'180'})
    original=httpx.AsyncClient
    monkeypatch.setattr(research_tools.httpx,'AsyncClient',lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(response)))
    monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    archive_sources(job,[{'url':'https://cooldown.example/a','title':'a','body':'隔离来源a'},
        {'url':'https://cooldown.example/b','title':'b','body':'隔离来源b'}],'搜索摘录')
    async def scenario():
        broker=ToolBroker(job,{'max_reads':2,'max_searches':0,'enabled_channels':['official']},{})
        rows=await asyncio.gather(*[broker.execute('fetch_source',{'url':'https://cooldown.example/'+part,'channel':'official'}) for part in ['a','b']])
        assert all(x['error']=='site_rate_limited' for x in rows)
    try:asyncio.run(scenario());assert len(calls)==1
    finally:
        with Session.begin() as db:
            for row in db.scalars(select(ToolCall).where(ToolCall.job_id==job)):row.retry_after_epoch=0


def test_concurrent_same_operation_is_not_sent_twice(client,monkeypatch):
    job=make_job(client);calls=[]
    async def fetch(self,args):calls.append(args);await asyncio.sleep(.05);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'fetch',fetch)
    async def scenario():
        broker=ToolBroker(job,{'max_reads':2,'max_searches':0,'enabled_channels':['official']},{})
        args={'url':'https://example.com/fixture','channel':'official'}
        result=await asyncio.gather(broker.execute('fetch_source',args),broker.execute('fetch_source',args))
        assert sum(x.get('error')=='operation_in_progress' for x in result)==1
    asyncio.run(scenario());assert len(calls)==1


def test_paused_tool_persists_duration_and_actual_state(client,monkeypatch):
    import pytest
    from app.research_tools import cancellable,Paused
    job=make_job(client)
    async def search(self,args):
        await cancellable(asyncio.sleep(30),job)
        return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'search',search)
    async def scenario():
        broker=ToolBroker(job,{'max_searches':2,'max_reads':0,'enabled_channels':['official']},{})
        running=asyncio.create_task(broker.execute('search_accounts',{'query':'深圳隔离计时','channel':'official'}))
        await asyncio.sleep(.05)
        with Session.begin() as db:db.get(Job,job).cancel_requested=True
        with pytest.raises(Paused):await running
    asyncio.run(scenario())
    with Session() as db:
        row=db.scalar(select(ToolCall).where(ToolCall.job_id==job))
        event=db.scalar(select(JobEvent).where(JobEvent.job_id==job,JobEvent.event_type=='tool.finished'))
        assert row.status=='paused' and row.elapsed_ms>0 and row.attempts==1
        assert row.result['error']=='operation_paused'
        assert event.payload['status']=='paused' and event.payload['elapsed_ms']==row.elapsed_ms


def test_rate_limit_cooldown_and_next_resume(client,monkeypatch):
    job=make_job(client);calls=[]
    async def search(self,args):
        calls.append(args)
        if len(calls)==1:raise ServiceError('provider_rate_limited')
        return {'sources':[],'fixture':'after-cooldown'}
    monkeypatch.setattr(ToolBroker,'search',search)
    async def scenario():
        broker=ToolBroker(job,{'max_searches':2,'max_reads':0,'enabled_channels':['official']},{})
        args={'query':'深圳 灯具门店','channel':'official'}
        assert (await broker.execute('search_accounts',args))['error']=='provider_rate_limited'
        response=resume(client,job)
        assert response.status_code==409 and '秒后' in response.json()['error']
        assert len(calls)==1
        # 只把隔离账本时间前移，验证冷却结束语义；不实际绕过任何provider限流。
        with Session.begin() as db:
            row=db.scalar(select(ToolCall).where(ToolCall.job_id==job));row.retry_after_epoch=time.time()-1
        assert resume(client,job).status_code==200
        assert (await broker.execute('search_accounts',args))['fixture']=='after-cooldown'
    asyncio.run(scenario());assert len(calls)==2
