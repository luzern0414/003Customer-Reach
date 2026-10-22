"""当前消息平台顺序与禁用约束；仅本地模型/网络替身，不作真实平台获客证明。"""
import asyncio
import uuid
import pytest
from app.source_catalog import active_channels,requested_channels,preferred_channels,public_entries,blocked_source,reference_urls

ENABLED=['official','b2b_1688','qcc_public','industry_directory','mall_directory','directory','knowledge']


@pytest.mark.parametrize('prompt,first,excluded',[
    ('先查企查查，再查1688',['qcc_public','b2b_1688'],[]),
    ('先用1688，然后查企查查',['b2b_1688','qcc_public'],[]),
    ('不使用企查查，改查行业黄页',['industry_directory'],['qcc_public']),
    ('不要查企查查或1688，查行业黄页',['industry_directory'],['qcc_public','b2b_1688']),
    ('只查官网，不要查企查查或1688',['official'],['qcc_public','b2b_1688','industry_directory','mall_directory','directory']),
    ('只使用1688和企查查公开索引',['b2b_1688','qcc_public'],['official','industry_directory','mall_directory','directory']),
])
def test_platform_order_and_current_scope(prompt,first,excluded):
    """prompt/first/excluded为当前明确指令与预期，不修改原启用列表或把未启用来源打开。"""
    scope=active_channels(prompt,ENABLED)
    assert requested_channels(prompt,ENABLED)==first
    assert preferred_channels(prompt,ENABLED)[:len(first)]==first
    assert not set(excluded).intersection(scope) and 'knowledge' in scope
    assert active_channels(prompt,[])==[]


def test_access_cautions_are_not_whole_platform_denials():
    """禁止捏造、绕登录和无API权限均不是禁用公开索引；先只查是阶段安排，不变永久仅查名单。"""
    for prompt in ['不要捏造企查查的联系人，不绕过1688登录','不用企查查API，也没有1688权限','先只查企查查，没结果再查1688']:
        assert active_channels(prompt,ENABLED)==ENABLED
    assert requested_channels('不用企查查API，也没有1688权限',ENABLED)==[]


def test_denied_directory_does_not_borrow_parent_or_official_route():
    """明确禁用的已知平台/登记目录不通过其他通道读；品牌公司主页不粗暴封为门店目录。"""
    prompt='不需要商场目录，不查企查查和1688，查行业黄页'
    entries=public_entries({'region':'深圳','products':[{'name':'壁灯'}]},ENABLED,'',[],prompt)
    assert not any('leanju.com' in entry['url'] for entry in entries)
    assert blocked_source('https://www.qcc.com/firm/example.html',prompt)
    assert blocked_source('https://www.1688.com/shop/example',prompt)
    assert blocked_source('http://www.leanju.com:8080/subbranch/',prompt)
    assert not reference_urls('不查企查查，读取https://www.qcc.com/firm/example.html',ENABLED)
    assert blocked_source('http://w2.siemens.com.cn/wa/Retailing_Map/map_Guangdong.html','不查品牌门店目录')
    assert not blocked_source('https://www.siemens.com.cn/company','不查品牌门店目录')
    assert blocked_source('https://www.qcc.com/firm/example.html','只查官网')


@pytest.mark.parametrize('prompt,expected',[
    ('先查企查查，再查1688',['qcc_public','b2b_1688']),
    ('只查官网，不要查企查查或1688',['official']),
])
def test_planner_cannot_reverse_or_reintroduce_denied_channels(client,monkeypatch,prompt,expected):
    """client隔离库、monkeypatch故意返回错误模型计划；prompt/expected为用户契约，实际plan节点确定性纠正。"""
    from app import agent
    from app.schemas import ResearchPlan,ResearchStep
    async def planner(*args,**kwargs):
        return ResearchPlan(target_roles=['dealer'],steps=[ResearchStep(channel=key,query='隔离查询',purpose='隔离计划') for key in ['b2b_1688','industry_directory','qcc_public','official']])
    monkeypatch.setattr(agent,'cached_model',planner)
    options={'enabled_channels':ENABLED.copy()}
    result=asyncio.run(agent.plan_node({'prompt':prompt,'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'options':options}))
    assert [step['channel'] for step in result['steps']][:len(expected)]==expected
    if len(expected)==1:assert [step['channel'] for step in result['steps']]==expected
    assert options['enabled_channels']==ENABLED
    assert result['options']['enabled_channels']==active_channels(prompt,ENABLED)


def test_broker_denies_before_network_budget_and_old_success_reuse(client,monkeypatch):
    """client隔离API、monkeypatch记录查询，禁用不发请求/不记尝试，旧成功也不绕当前范围。"""
    from app.db import Session,Job,ToolCall
    from app.research_tools import ToolBroker
    conv=client.post('/api/conversations').json()['id']
    key=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具经销商','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,key).status='running'
    options={'enabled_channels':['official','qcc_public'],'max_searches':1,'max_reads':1}
    calls=[]
    async def search(self,args):calls.append(args);return {'sources':[],'error':''}
    monkeypatch.setattr(ToolBroker,'search',search)
    args={'channel':'qcc_public','query':'隔离查询'+key}
    first=ToolBroker(key,options,{})
    assert asyncio.run(first.execute('search_accounts',args))['error']==''
    closed=ToolBroker(key,{**options,'enabled_channels':['official']},{})
    assert asyncio.run(closed.execute('search_accounts',args))['error']=='channel_disabled'
    assert len(calls)==1
    with Session() as db:assert db.query(ToolCall).filter(ToolCall.job_id==key).one().attempts==1
    # 新消息文字禁用，在全局仍启用时也不能通过公开网页路由读取该平台。
    other=client.post('/api/conversations').json()['id']
    denied=client.post('/api/conversations/'+other+'/messages',json={'content':'找深圳经销商，不查企查查，读https://www.qcc.com/firm/example.html','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,denied).status='running'
    broker=ToolBroker(denied,options,{})
    assert asyncio.run(broker.execute('fetch_source',{'url':'https://www.qcc.com/firm/example.html','channel':'official'}))['error']=='channel_disabled'
    with Session() as db:assert db.query(ToolCall).filter(ToolCall.job_id==denied).count()==0


def test_redirect_cannot_reach_a_denied_platform(client,monkeypatch):
    """client隔离API、monkeypatch本地302；已有链接也不能通过允许站点跳转到明确禁用的平台，不发目标/备用请求。"""
    import httpx
    from app import research_tools
    from app.db import Session,Job
    from app.research_tools import ToolBroker
    url='https://example.org/redirect-'+uuid.uuid4().hex
    conv=client.post('/api/conversations').json()['id']
    key=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳客户，不查企查查，读取'+url,'client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,key).status='running'
    broker=ToolBroker(key,{'enabled_channels':ENABLED,'max_reads':1,'max_searches':0},{})
    real_client=httpx.AsyncClient;requests=[]
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(302,headers={'Location':'https://www.qcc.com/firm/example.html'})
    monkeypatch.setattr(research_tools,'public_url',lambda _:True)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    async def forbidden(*args,**kwargs):raise AssertionError('不能借备用读取访问禁用平台')
    monkeypatch.setattr(research_tools,'call_exa',forbidden)
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'official'}))
    assert result['error']=='channel_disabled' and requests==[url] and not result['sources']


def test_search_cache_and_new_results_filter_denied_source_without_rewriting_history(client,monkeypatch):
    """client隔离API、monkeypatch仅返回占位搜索响应；新响应与跨任务/同任务缓存都筛真实URL，原证据/账本保留。"""
    from app import research_tools
    from app.db import Session,Job,ToolCall,Evidence
    from app.research_tools import ToolBroker
    allowed='https://example.org/allowed-'+uuid.uuid4().hex
    denied='https://www.qcc.com/firm/fixture.html'
    conv=client.post('/api/conversations').json()['id']
    key=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳客户，不查企查查','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,key).status='running'
    calls=[]
    async def search(*args,**kwargs):
        calls.append(args)
        return f'Title: 占位企查查\nURL: {denied}\n占位原文\n\nTitle: 占位企业\nURL: {allowed}\n占位原文'
    monkeypatch.setattr(research_tools,'call_exa',search)
    options={'enabled_channels':ENABLED,'max_searches':2,'max_reads':0}
    broker=ToolBroker(key,options,{})
    args={'channel':'official','query':'隔离来源范围'+key}
    result=asyncio.run(broker.execute('search_accounts',args))
    assert [source['url'] for source in result['sources']]==[allowed]
    with Session.begin() as db:
        row=db.query(ToolCall).filter(ToolCall.job_id==key).one()
        row.result={**row.result,'sources':[{'id':'legacy','url':denied,'kind':'搜索摘录'}]}
    again=asyncio.run(broker.execute('search_accounts',args))
    assert again['reused'] and not again['sources'] and again['error']=='empty_results'
    # 新任务命中同查询缓存，仍不恢复被禁止平台；不改旧成功响应来伪造历史。
    other=client.post('/api/conversations').json()['id']
    next_key=client.post('/api/conversations/'+other+'/messages',json={'content':'找深圳客户，不查企查查','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,next_key).status='running'
    third=asyncio.run(ToolBroker(next_key,options,{}).execute('search_accounts',args))
    assert third['cached'] and not third['sources'] and len(calls)==1
    with Session() as db:
        original=db.query(ToolCall).filter(ToolCall.job_id==key).one()
        assert original.result['sources'][0]['url']==denied
        assert db.query(Evidence).filter(Evidence.job_id==key,Evidence.url==denied).count()==0


def test_old_scope_violating_evidence_cannot_create_new_customer(client):
    """client为隔离API；旧误标公开网页的被禁平台证据不授予新保存权限，原Evidence保留可审计。"""
    from app.db import Session,Job,Lead
    from app.gateway import archive_sources
    from app.research_tools import ToolBroker
    from app.schemas import Candidate,Fact
    conv=client.post('/api/conversations').json()['id']
    key=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具经销商，不查企查查','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,key).status='running'
    name='深圳隔离范围'+uuid.uuid4().hex+'有限公司';quote=name+'经销灯具。'
    source=archive_sources(key,[{'url':'https://www.qcc.com/firm/fixture.html','title':name,'body':quote}],'网页正文','official')[0]
    candidate=Candidate(display_name=name,city='深圳',buyer_role='dealer',match_reason='隔离范围验证',facts=[
        Fact(field='name',value=name,quote=quote,source_id=source['id']),
        Fact(field='buyer_role',value='经销',quote=quote,source_id=source['id'])])
    broker=ToolBroker(key,{'enabled_channels':ENABLED,'max_leads':1},{'products':[{'name':'吊灯'}]})
    result=asyncio.run(broker.execute('persist_lead',{'candidate':candidate.model_dump()}))
    assert result['error']=='channel_disabled'
    with Session() as db:assert db.query(Lead).filter(Lead.display_name==name).count()==0
