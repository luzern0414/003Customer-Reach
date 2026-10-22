"""真实LangGraph与持久SQLite运行；只替换外部提供者，用于恢复/预算/知识等业务契约。"""
import asyncio
import json
import uuid
from typing import TypedDict
from datetime import datetime
import pytest
from sqlalchemy import select
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import AIMessage, AIMessageChunk
from app.db import Session, Job, Evidence, ToolCall, Knowledge, JobEvent, serialize
from app.schemas import ProductProfile, Product, ResearchPlan, ResearchStep, CandidateBatch, Candidate
from app.knowledge import WorkspaceStore,store,WORKSPACE,upsert_knowledge,search_knowledge,expires
from app.service import checked_candidate, ServiceError
from app.research_tools import ToolBroker,Paused
from app.config import DATA

def new_job(client, prompt='最多1家深圳灯具经销商'):
    """client为隔离HTTP客户端，prompt非空；创建并领取测试任务，返回实际任务字典。"""
    conv=client.post('/api/conversations').json()['id']
    row=client.post(f'/api/conversations/{conv}/messages',json={'content':prompt,'client_token':uuid.uuid4().hex}).json()
    with Session.begin() as db:db.get(Job,row['id']).status='running'
    return row

def test_memory_store_persistence_and_scope(client):
    store.put((WORKSPACE,'preference'),'test-prefs',{'content':'仅找深圳灯具经销商','source':'用户提供'})
    assert WorkspaceStore().get((WORKSPACE,'preference'),'test-prefs').value['content']=='仅找深圳灯具经销商'
    assert WorkspaceStore().search((WORKSPACE,'preference'),query='深圳灯具')
    with pytest.raises(ServiceError):store.put(('other','preference'),'x',{'content':'不可跨作用域'})
    store.delete((WORKSPACE,'preference'),'test-prefs')
    assert store.get((WORKSPACE,'preference'),'test-prefs') is None

def test_chinese_knowledge_expiry_and_feedback(client):
    fresh=upsert_knowledge('中文产品验证','低压磁吸轨道灯供货目录','product')
    assert any(x['id']==fresh['id'] for x in search_knowledge('磁吸轨道灯'))
    old=upsert_knowledge('过期产品验证','轨道灯昨日资料','product',expiry=expires(-1))
    assert old['id'] not in {x['id'] for x in search_knowledge('轨道灯')}
    lead=client.post('/api/leads',json={'display_name':'隔离反馈灯具客户'}).json()
    known=upsert_knowledge('反馈事实验证','深圳零售门店','public_fact',entity_id=lead['id'])
    assert client.post('/api/leads/'+lead['id']+'/feedback',json={'kind':'nonbuyer','content':'测试排除'}).status_code==201
    assert known['id'] not in {x['id'] for x in search_knowledge('深圳零售门店')}
    assert any(x.value.get('entity_id')==lead['id'] for x in store.search((WORKSPACE,'exclusion'),limit=100))
    client.delete('/api/leads/'+lead['id'])

def test_admin_memory_knowledge_api(client):
    rows=client.post('/api/memories',json={'kind':'preference','content':'产品只使用真实报价'}).json()
    row=next(x for x in rows if x['value'].get('content')=='产品只使用真实报价')
    assert client.delete('/api/memories/'+row['id']).json()['inactive']
    k=client.post('/api/knowledge',json={'title':'补充产品资料','body':'深圳灯具产品说明'}).json()
    assert client.get('/api/knowledge?q=灯具').json()['items']
    assert client.delete('/api/knowledge/'+k['id']).json()['inactive']
    assert client.get('/api/agent/graph').json()['checkpoint']=='AsyncSqliteSaver'
    assert any(x['status']=='authorization_required' for x in client.get('/api/channels').json())

def test_role_is_not_business_registration(client):
    body='深圳测试灯饰商行（个体工商户）'
    source={'s':{'body':body,'url':'https://example.com','title':'注册目录','captured_at':'2026-10-02','kind':'目录'}}
    candidate=Candidate(display_name=body,city='深圳',buyer_role='retailer',match_reason='测试',facts=[
        {'field':'name','value':body,'quote':body,'source_id':'s'},
        {'field':'buyer_role','value':'工商户','quote':body,'source_id':'s'}])
    with pytest.raises(ServiceError):checked_candidate(candidate,source)

def test_tool_validation_idempotency_and_budget(client, monkeypatch):
    from app import research_tools as tools
    row=new_job(client);calls=[]
    async def search(name,args):
        """name/args为外部MCP参数，返回隔离fixture正文，记录调用次数，不冒充真实网络。"""
        calls.append(args)
        return 'Title: 测试目录\nURL: https://example.com/store\n深圳测试灯具店是零售门店。电话0755-12345678。'
    monkeypatch.setattr(tools,'call_exa',search)
    broker=ToolBroker(row['id'],{'max_searches':1,'max_reads':1,'enabled_channels':['official','directory']},{})
    async def run():
        result=await broker.execute('search_accounts',{'query':'深圳灯具测试','channel':'official'})
        repeat=await ToolBroker(row['id'],broker.options,{}).execute('search_accounts',{'query':'深圳灯具测试','channel':'official'})
        assert repeat['reused'] and repeat['sources'][0]['id']==result['sources'][0]['id']
        blocked=await broker.execute('search_accounts',{'query':'深圳灯具另一渠道','channel':'directory'})
        assert blocked['error']=='budget_exhausted'
        with pytest.raises(ServiceError):await broker.execute('shell',{'cmd':'forbidden'})
    asyncio.run(run());assert len(calls)==1

def test_checkpoint_recovers_successful_tool_without_reexecution(client,monkeypatch):
    from app import research_tools as tools
    row=new_job(client);calls=[]
    async def provider(name,args):
        """隔离MCP替身，记录是否重复；返回公开URL形状但不进行实际研究。"""
        calls.append(args);return 'Title: fixture\nURL: https://example.com/cp\n深圳测试资料'
    monkeypatch.setattr(tools,'call_exa',provider)
    failures=[True]
    class CheckpointState(TypedDict,total=False):
        """检查点测试使用与业务相同的逐字段State合并语义。"""
        job_id: str
        sources: list[str]
        done: bool
    async def run():
        def compile_graph(saver):
            graph=StateGraph(CheckpointState)
            async def search(state):
                """state为隔离图输入；使用真实账本和实际checkpoint，不模拟成功节点。"""
                result=await ToolBroker(row['id'],{'max_searches':2,'max_reads':0,'enabled_channels':['official']},{}).execute('search_accounts',{'query':'深圳测试恢复','channel':'official'})
                return {'sources':[x['id'] for x in result['sources']]}
            async def stop(state):
                """state包含来源；第一轮故障、第二轮恢复成功，用于验证pending node。"""
                if failures[0]:failures[0]=False;raise Paused()
                return {'done':True}
            graph.add_node('search',search);graph.add_node('stop',stop);graph.add_edge(START,'search');graph.add_edge('search','stop');graph.add_edge('stop',END)
            return graph.compile(checkpointer=saver)
        config={'configurable':{'thread_id':row['id']}}
        path=str(DATA/'checkpoint-test.db')
        async with AsyncSqliteSaver.from_conn_string(path) as saver:
            await saver.setup();graph=compile_graph(saver)
            with pytest.raises(Paused):await graph.ainvoke({'job_id':row['id']},config)
            checkpoint=await graph.aget_state(config);assert checkpoint.next==('stop',)
        async with AsyncSqliteSaver.from_conn_string(path) as saver:
            await saver.setup();result=await compile_graph(saver).ainvoke(None,config)
            assert result['done'] and result['sources']
    asyncio.run(run());assert len(calls)==1

def test_complete_graph_waterfall_stream_and_flywheel(client,monkeypatch):
    from app import agent as module
    from app import research_tools as tools
    profile=ProductProfile(products=[Product(name='吊灯')],summary='隔离画像',region='深圳',target_buyers=['零售门店'])
    row=new_job(client,'销售吊灯，最多1家深圳零售门店')
    body='深圳测试灯具店是灯具零售门店。地址深圳市南山区。电话0755-12345678。主营吊灯。'
    actual_calls=[]
    async def provider(name,args):
        """外部提供者替身；官网无结果，目录有证据，验证真实图的换渠道决策。"""
        actual_calls.append(args)
        if '官网' in args['query']:return '没有可用来源'
        return 'Title: 隔离目录\nURL: https://example.com/retail\n'+body
    async def fetch(self,args):
        """只复用隔离已归档来源，防止测试发真实HTTP。"""
        with Session() as db:return {'sources':[serialize(x) for x in db.scalars(select(Evidence).where(Evidence.job_id==self.job_id))]}
    async def structured(state,schema,prompt,label):
        """替换外部LLM结构化结果；图、数据库、校验、SSE事件和知识仍执行真实代码。"""
        if schema is ProductProfile:return profile
        if schema is ResearchPlan:return ResearchPlan(target_roles=['retailer'],steps=[ResearchStep(channel='official',query='深圳官网 '+row['id'],purpose='官网核验'),ResearchStep(channel='directory',query='深圳门店目录 '+row['id'],purpose='换渠道')])
        # 该模型替身只认识本用例正文；真实知识命中可来自其他测试，不能将本用例引文配给外来source_id。
        with Session() as db:sources=list(db.scalars(select(Evidence).where(Evidence.id.in_(state.get('source_ids',[])),Evidence.job_id==row['id'])))
        if not sources:return CandidateBatch(missing_fields=['buyer_role','phone'])
        source=sources[0].id
        return CandidateBatch(candidates=[Candidate(display_name='深圳测试灯具店',city='深圳',buyer_role='retailer',matched_products=['吊灯'],match_reason='隔离测试公开零售门店',facts=[
            {'field':'name','value':'深圳测试灯具店','quote':body,'source_id':source},
            {'field':'buyer_role','value':'零售门店','quote':body,'source_id':source},
            {'field':'phone','value':'0755-12345678','quote':body,'source_id':source},
            {'field':'address','value':'深圳市南山区','quote':body,'source_id':source},
            {'field':'categories','value':'吊灯','quote':body,'source_id':source}])])
    class LLM:
        """外部模型替身，只检查真实工具协议与Markdown增量是否被图保留。"""
        def bind_tools(self,*args,**kwargs):
            """args/kwargs为schema与tool_choice，返回工具探针自身，不调网络。"""
            return self
        async def ainvoke(self,messages):
            """messages为搜索节点指令，返回对应确定渠道的真实AIMessage tool_calls形状。"""
            step=json.loads(messages[-1].content.split('\n')[-1])
            return AIMessage(content='',tool_calls=[{'name':'SearchAccounts','args':{'query':step['query'],'channel':step['channel']},'id':uuid.uuid4().hex}])
        async def astream(self,messages):
            """messages为回答上下文，逐步输出带粗体的fixture，验证增量早于完成事件。"""
            for value in ['### 深圳测试灯具店\n','**零售门店**',' · 深圳\n','公开电话：0755-12345678']:
                await asyncio.sleep(.09);yield AIMessageChunk(content=value)
    monkeypatch.setattr(tools,'call_exa',provider);monkeypatch.setattr(ToolBroker,'fetch',fetch)
    monkeypatch.setattr(module,'cached_model',structured);monkeypatch.setattr(module,'model',lambda:LLM())
    client.patch('/api/settings',json={'max_leads':2,'max_searches':3,'max_reads':3})
    asyncio.run(module.run_job(row['id']))
    final=client.get('/api/jobs/'+row['id']).json()
    assert final['status']=='completed' and len(final['lead_ids'])==1 and final['elapsed_ms']>0, {'error':final.get('error'),'tools':[(x['tool'],x['error']) for x in final.get('tools',[])]}
    assert final['metrics']['channels']==['official','directory'] and final['metrics']['llm_chunks']==4
    with Session() as db:
        events=list(db.scalars(select(JobEvent).where(JobEvent.job_id==row['id']).order_by(JobEvent.id)))
    deltas=[x for x in events if x.event_type=='message.delta']
    completed=[x for x in events if x.event_type=='message.completed']
    assert len(deltas)>=3 and deltas[0].id<completed[0].id
    assert ''.join(x.payload['delta'] for x in deltas)==completed[0].payload['content']
    streamed=client.get('/api/jobs/'+row['id']+'/events?after='+str(deltas[0].id)).text
    assert 'event: message.delta' in streamed and 'event: message.completed' in streamed
    assert store.get((WORKSPACE,'company'),'profile').value['profile']['products'][0]['name']=='吊灯'
    assert any(x['entity_id']==final['lead_ids'][0] for x in search_knowledge('深圳零售门店'))
    client.delete('/api/leads/'+final['lead_ids'][0])
