"""普通对话不进入获客图、不污染画像；首响应与研究全程分别验收。"""
import asyncio
import uuid
import pytest
from sqlalchemy import select
from app.db import Session,Conversation,Job,Memory,JobEvent
from app.conversation import mode
from app.knowledge import store,WORKSPACE


@pytest.mark.parametrize('text,expected',[
 ('你好，你是谁','quick'),('你好','quick'),('你是谁？帮我找深圳灯具客户','research'),
 ('如何获取B端客户','chat'),('刚才找到哪些客户','chat'),('最多1家深圳灯具店','research'),
 ('销售吊灯，最多1家深圳零售门店','research'),('我们卖餐桌','research'),('帮我找上海经销商','research')])
def test_current_message_route(text,expected):
    assert mode(text)==expected


def test_identity_does_not_wait_for_research_or_change_profile(client):
    conv=client.post('/api/conversations').json()['id']
    profile={'products':[{'name':'吊灯'}],'region':'深圳','questions':[],'summary':'稳定产品资料'}
    with Session.begin() as db:db.get(Conversation,conv).profile=profile
    store.put((WORKSPACE,'company'),'latency-sentinel',{'profile':profile,'source':'用户资料'})
    response=client.post('/api/conversations/'+conv+'/messages',json={'content':'你好，你是谁','client_token':uuid.uuid4().hex})
    assert response.status_code==202
    job=response.json();assert job['status']=='queued' and job['metrics']['intent_pending']
    from app import agent
    asyncio.run(agent.run_job(job['id']))
    detail=client.get('/api/conversations/'+conv).json()
    assert detail['profile']==profile and '我是 Reach' in detail['messages'][-1]['content']
    assert store.get((WORKSPACE,'company'),'latency-sentinel').value['profile']==profile
    assert 'message.completed' in client.get('/api/jobs/'+job['id']+'/events').text


def test_chat_graph_skips_profile_knowledge_and_learning(client,monkeypatch):
    from app import agent
    from langchain_core.messages import AIMessageChunk
    conv=client.post('/api/conversations').json()['id']
    response=client.post('/api/conversations/'+conv+'/messages',json={'content':'怎么评估公开资料可靠性？','client_token':uuid.uuid4().hex}).json()
    async def forbidden(*args,**kwargs):
        """args/kwargs为研究节点参数；普通问答调用这些节点即失败。"""
        raise AssertionError('普通问答进入研究节点')
    class Chat:
        """只替换外部生成，真实图与消息事件仍执行生产代码。"""
        async def astream(self,messages):
            """messages必须包含当前问题，输出两块；不触发工具。"""
            assert '怎么评估公开资料可靠性' in messages[-1].content
            yield AIMessageChunk(content='优先官网和原始公告，')
            yield AIMessageChunk(content='核对主体、日期和来源。')
    monkeypatch.setattr(agent,'model',lambda:Chat())
    for name in ['load_context','profile_node','plan_node','learn_node']:monkeypatch.setattr(agent,name,forbidden)
    with Session.begin() as db:db.get(Job,response['id']).status='running'
    asyncio.run(agent.run_job(response['id']))
    job=client.get('/api/jobs/'+response['id']).json()
    assert job['status']=='completed' and set(job['metrics']['stage_timings'])=={'intent','answer'}
    with Session() as db:
        events=list(db.scalars(select(JobEvent).where(JobEvent.job_id==job['id']).order_by(JobEvent.id)))
    assert any(event.event_type=='message.delta' for event in events)


def test_plain_followup_reuses_profile(client,monkeypatch):
    from app.agent import profile_node
    from app.schemas import ProductProfile,Product
    from app import agent
    conv=client.post('/api/conversations').json()['id']
    original=ProductProfile(products=[Product(name='吊灯')],region='深圳',target_buyers=['经销商'],summary='以前资料').model_dump()
    async def forbidden(*args,**kwargs):
        """args/kwargs为画像模型参数；产品未变时不得重复调用。"""
        raise AssertionError('重复提取未变产品')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    result=asyncio.run(profile_node({'conversation_id':conv,'profile':original,'prompt':'继续补查','metrics':{}}))
    assert result['metrics']['profile_reused'] and result['profile']['region']=='深圳'
    assert result['profile']['target_buyers']==['经销商']
    assert client.get('/api/conversations/'+conv).json()['profile']['products']==original['products']


@pytest.mark.parametrize('region',['杭州','成都','武汉','苏州'])
def test_new_target_uses_structured_profile_without_city_allowlist(client,monkeypatch,region):
    """region为明确新城市；检查真实节点进入结构化模型而非静默复用旧地区，不模拟公网成功。"""
    from app import agent
    from app.schemas import ProductProfile,Product
    conv=client.post('/api/conversations').json()['id']
    original=ProductProfile(products=[Product(name='吊灯')],region='深圳',target_buyers=['经销商'],summary='已有产品').model_dump()
    prompt=f'继续核验{region}的零售门店'
    async def extract(state,schema,text,key):
        """参数为真实画像请求；必须带当前要求与旧产品背景，返回结构化城市更新。"""
        assert schema is ProductProfile and prompt in text and '吊灯' in text
        return ProductProfile(products=[Product(name='吊灯')],region=region,target_buyers=['零售门店'],summary='更新目标')
    monkeypatch.setattr(agent,'cached_model',extract)
    result=asyncio.run(agent.profile_node({'conversation_id':conv,'profile':original,'prompt':prompt,'context':prompt+'\n已有画像：'+str(original),'options':{'default_region':'深圳'},'metrics':{}}))
    assert result['profile']['region']==region
    assert client.get('/api/conversations/'+conv).json()['profile']['target_buyers']==['零售门店']


@pytest.mark.parametrize('has_products',[True,False])
def test_profile_questions_only_block_missing_products(client,monkeypatch,has_products):
    """has_products表示用户产品是否已提取；限制性说明不得阻断，缺产品仍保留询问。"""
    from app import agent
    from app.schemas import ProductProfile,Product
    conv=client.post('/api/conversations').json()['id']
    question='仅复核指定目录，不读取其他网页。' if has_products else '请说明销售什么产品？'
    async def extract(state,schema,text,key):
        """参数为真实画像模型接口；只替换外部生成，执行实际节点与持久化。"""
        return ProductProfile(products=[Product(name='吊灯')] if has_products else [],region='深圳',questions=[question],summary='隔离画像校验')
    monkeypatch.setattr(agent,'cached_model',extract)
    result=asyncio.run(agent.profile_node({'conversation_id':conv,'prompt':'复核深圳目录商户','context':'用户资料','options':{'default_region':'深圳'}}))
    expected=[] if has_products else [question]
    assert result['profile']['questions']==expected
    assert client.get('/api/conversations/'+conv).json()['profile']['questions']==expected


def test_worker_chat_lane_not_blocked_by_research(client,monkeypatch):
    from app import worker
    # 只整理隔离库遗留队列，避免其他测试的排队任务被此调度专项领取。
    with Session.begin() as db:
        for row in db.scalars(select(Job).where(Job.status.in_(['queued','running','cancelling']))):row.status='paused'
    ids=[]
    for content in ['寻找深圳灯具经销商','解释获客流程']:
        conv=client.post('/api/conversations').json()['id']
        ids.append(client.post('/api/conversations/'+conv+'/messages',json={'content':content,'client_token':uuid.uuid4().hex}).json()['id'])
    async def exercise():
        research_started=asyncio.Event();chat_completed=asyncio.Event();release=asyncio.Event()
        async def fake(job_id):
            """job_id为真实领取的隔离任务；研究保持阻塞，普通对话必须并发完成。"""
            if job_id==ids[0]:research_started.set();await release.wait()
            else:
                await research_started.wait()
                with Session.begin() as db:db.get(Job,job_id).status='completed'
                chat_completed.set()
        monkeypatch.setattr(worker,'run_job',fake)
        task=asyncio.create_task(worker.loop())
        try:
            await asyncio.wait_for(chat_completed.wait(),5)
            with Session() as db:assert db.get(Job,ids[0]).status=='running'
        finally:task.cancel();await asyncio.gather(task,return_exceptions=True)
    asyncio.run(exercise())


def test_named_account_reuses_bounded_plan(client,monkeypatch):
    from app import agent
    lead=client.post('/api/leads',json={'display_name':'深圳固定渠道审查照明有限公司','buyer_role':'dealer'}).json()
    async def forbidden(*args,**kwargs):
        """args/kwargs为开放式规划模型调用；固定主体复用计划时不能调用。"""
        raise AssertionError('指定公司仍重新生成渠道计划')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    result=asyncio.run(agent.plan_node({'prompt':'核验'+lead['display_name']+'的经销身份','profile':{'region':'深圳','products':[{'name':'吊灯'}]},'options':{'enabled_channels':['official','directory']},'metrics':{}}))
    assert result['metrics']['plan_reused'] and result['plan']['target_roles']==['dealer']
    assert [x['channel'] for x in result['steps']]==['official','directory']


def test_mcp_body_cache_avoids_another_network_read(client,monkeypatch):
    from app.db import Evidence
    from app.knowledge import expires
    from app.research_tools import ToolBroker
    from app import research_tools
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'查找深圳灯具客户','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:
        row=Evidence(job_id=job,url='https://example.com/cached-mcp-body',title='隔离缓存',body='深圳灯具客户的完整公开经营资料。'*20,kind='网页读取',channel='official',expires_at=expires(30))
        db.add(row);db.flush();source_id=row.id
    def forbidden(url):
        """url为已读取的测试页面；有效MCP正文缓存命中不得重复发网络。"""
        raise AssertionError('重复读取已有MCP正文')
    monkeypatch.setattr(research_tools,'public_url',forbidden)
    result=asyncio.run(ToolBroker(job,{},{}).fetch({'url':'https://example.com/cached-mcp-body','channel':'official'}))
    assert result['cached'] and result['sources'][0]['id']==source_id
