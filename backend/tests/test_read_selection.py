"""读取预算去噪；全部来源合成，未请求搜索供应商或客户网站。"""
import asyncio
import uuid
import pytest
from app.read_selection import read_selection


@pytest.mark.parametrize('url,title,roles,allowed,reason',[
    ('https://exa.ai/library/places?q=fixture','深圳经销目录',['dealer'],False,'provider_library'),
    ('https://exa.ai.example.org/library/places','深圳经销目录',['dealer'],True,'target_signal'),
    ('https://example.org/factory','深圳灯饰厂生产加工',['dealer','retailer'],False,'manufacturer_only'),
    ('https://example.org/factory','深圳灯饰厂生产加工',['manufacturer'],True,'target_signal'),
    ('https://example.org/mixed','深圳灯饰厂经销批发',['dealer'],True,'target_signal'),
    ('https://example.org/unknown','深圳灯具企业',['dealer'],True,'unknown_role')])
def test_read_signal_is_not_qualification(url,title,roles,allowed,reason):
    """参数为合成来源/目标及预期；精确供应商主机匹配，未知和混合主体不硬拒绝。"""
    result=read_selection({'url':url,'title':title,'body':''},roles,'深圳')
    assert result['allowed']==allowed and result['reason']==reason


@pytest.mark.parametrize('explicit',[False,True])
@pytest.mark.parametrize('selected',[False,True])
def test_read_node_skips_irrelevant_results_but_keeps_explicit_url(client,monkeypatch,explicit,selected):
    """client隔离库，monkeypatch替网络，explicit是否用户指定；跳过不占fetch账本并抑制旧摘要提取。"""
    from app import agent
    from app.gateway import archive_sources
    from app.research_tools import ToolBroker
    job=client.post('/api/conversations/'+client.post('/api/conversations').json()['id']+'/messages',
        json={'content':'找深圳灯具经销商','client_token':uuid.uuid4().hex}).json()['id']
    rows=archive_sources(job,[{'url':'https://example.org/factory','title':'深圳合成灯饰厂生产加工','body':'合成制造商'},
        {'url':'https://exa.ai/library/places?q=fixture','title':'深圳经销商目录','body':'合成供应商聚合资料'}],'搜索摘录','official')
    seen=[]
    async def execute(self,name,args):
        """只记录真实read_node调度，不发网络请求或提供正文。"""
        seen.append((name,args));return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    state={'job_id':job,'profile':{'region':'深圳','products':[{'name':'灯具'}]},
        'options':{'enabled_channels':['official'],'max_reads':1},'plan':{'target_roles':['dealer']},
        'source_ids':[row['id'] for row in rows],'attempts':[{'source_ids':[row['id'] for row in rows]}],
        'steps':[{'channel':'official'}],'cursor':0,'saved_ids':[]}
    if selected:
        from app.db import Session,Lead,identifier
        key=identifier()
        with Session.begin() as db:db.add(Lead(id=key,display_name='合成灯饰',city='深圳',dedupe_key=uuid.uuid4().hex,
            facts={'phone':{'value':'13428788412','verification':'原文匹配'},'address':{'value':'深圳隔离路','verification':'原文匹配'}},
            evidence=[{'field':'name','url':'https://example.net/original-store'}]))
        state['saved_ids']=[key]
    if explicit:state['reference_urls']=[{'url':rows[0]['url'],'channel':'official'}]
    result=asyncio.run(agent.read_node(state))
    if explicit:assert seen==[('fetch_source',state['reference_urls'][0])]
    else:
        assert seen==[] and result['read_empty']
        assert {item['reason'] for item in result['read_skipped']}=={'manufacturer_only','provider_library'}
        assert asyncio.run(agent.extract_node({**state,**result}))=={'candidates':[]}
