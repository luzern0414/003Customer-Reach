"""标题伪正文、协议读取限制及非标准企业页访问状态的真实工具边界回归。"""
import asyncio
import uuid
import pytest
import httpx
from app.source_content import has_content


@pytest.mark.parametrize('body,valid',[
    ('# 隔离公司\nURL: https://example.org/company\n隔离公司',False),
    ('Title: 隔离公司\nURL: https://example.org/company\n',False),
    ('# 隔离公司\nURL: https://example.org/company\n联系人：隔离先生',True)])
def test_metadata_is_not_customer_body(body,valid):
    """body为供应商实际响应形状，valid表示有正文；检查不得生成或改写原内容。"""
    item={'title':'隔离公司','url':'https://example.org/company','body':body}
    assert has_content(item)==valid and item['body']==body
    assert has_content({'title':None,'url':item['url'],'body':'公开联系电话：0755-12345678'})


def test_old_title_only_read_is_excluded_from_model_context():
    """历史证据原样保留，但缺正文的读取记录不能重新传给模型冒充企业事实。"""
    from app.evidence_context import evidence_context
    row={'id':'old-id','url':'https://example.org/company','title':'隔离公司','kind':'网页读取',
        'body':'# 隔离公司\nURL: https://example.org/company\n隔离公司'}
    assert evidence_context([row],[],'深圳',['old-id'],['old-id'])==[]
    assert row['body'].endswith('隔离公司')


def broker_for(client,url,channel):
    """client为隔离库、url为验证占位URL、channel为启用渠道；返回真实Broker，禁止真实网络/生产写入。"""
    from app.db import Session,Conversation,Job,identifier
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':[channel],'max_reads':8})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离来源读取边界'))
    job=submit(conversation,{'content':'查找深圳灯具客户，读取 '+url,'attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    return ToolBroker(job['id'],options,{'region':'深圳','products':[{'name':'灯具'}]})


def test_1688_robots_query_denial_stops_before_page_or_fallback(client,monkeypatch):
    """client为隔离库；实际Protego解析通配query规则，目标页及Exa均不得请求，非浏览器UA不冒充Googlebot。"""
    from app import research_tools,source_policy
    url='https://www.1688.com/factory/fixture.html?topOfferIds=fixture'
    broker=broker_for(client,url,'b2b_1688')
    from app.db import Session,Evidence
    from app.knowledge import expires
    with Session.begin() as db:db.add(Evidence(job_id=broker.job_id,url=url,title='隔离工厂',body='隔离旧工厂公开资料。'*30,
        kind='网页读取',channel='b2b_1688',expires_at=expires(30)))
    requests=[];real_client=httpx.AsyncClient
    def handler(request):
        """request为MockTransport捕获请求；只允许robots，任何正文请求立即失败。"""
        requests.append(str(request.url))
        assert request.url.path=='/robots.txt'
        return httpx.Response(200,text='User-agent: *\nDisallow: /*?*\nUser-agent: Googlebot\nAllow: /factory/')
    monkeypatch.setattr(source_policy,'POLICIES',{})
    monkeypatch.setattr(source_policy,'LOCKS',{})
    monkeypatch.setattr(research_tools,'public_url',lambda _:True)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    async def forbidden(*args,**kwargs):raise AssertionError('禁止供应商fallback')
    monkeypatch.setattr(research_tools,'call_exa',forbidden)
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'b2b_1688'}))
    assert result['error']=='site_robots_disallowed' and len(requests)==1


def test_qcc_567_does_not_fallback_to_another_reader(client,monkeypatch):
    """client为隔离库；非标准访问限制有安全错误，不能绕供应商重新抓同一受限企业页。"""
    from app import research_tools
    url='https://m.qcc.com/firm/fixture567.html'
    broker=broker_for(client,url,'qcc_public')
    real_client=httpx.AsyncClient
    monkeypatch.setattr(research_tools,'public_url',lambda _:True)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(lambda _:httpx.Response(567,text='受限')),**kwargs))
    async def forbidden(*args,**kwargs):raise AssertionError('禁止供应商fallback')
    monkeypatch.setattr(research_tools,'call_exa',forbidden)
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'qcc_public'}))
    assert result['error']=='site_access_restricted' and not result['sources']


def test_fallback_title_and_url_do_not_create_evidence(client,monkeypatch):
    """client为隔离库；供应商只返标题/URL时工具unavailable，不保存伪正文。"""
    from app import research_tools
    from app.db import Session,Evidence,ToolCall
    url='https://example.org/title-only-'+uuid.uuid4().hex
    broker=broker_for(client,url,'official')
    real_client=httpx.AsyncClient
    monkeypatch.setattr(research_tools,'public_url',lambda _:True)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(lambda _:httpx.Response(200,text='短页',headers={'Content-Type':'text/plain'})),**kwargs))
    async def title_only(*args,**kwargs):return '# 隔离公司\nURL: '+url+'\n隔离公司'
    monkeypatch.setattr(research_tools,'call_exa',title_only)
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'official'}))
    assert result['error']=='empty_body' and not result['sources']
    with Session() as db:
        assert db.query(Evidence).filter(Evidence.job_id==broker.job_id).count()==0
        assert db.query(ToolCall).filter(ToolCall.job_id==broker.job_id).one().status=='unavailable'


def test_empty_primary_and_limited_fallback_are_persisted_and_projected(client,monkeypatch):
    """client隔离库、monkeypatch注入HTML框架及429；实际解析/Broker/事件保留两阶段失败，原协议正文不出UI。"""
    from app import research_tools
    from app.db import Session,ToolCall,JobEvent,Evidence
    from app.tool_views import tool_view,read_summary
    from app.answer_summary import empty_summary
    url='https://example.org/empty-'+uuid.uuid4().hex
    broker=broker_for(client,url,'official');real_client=httpx.AsyncClient
    monkeypatch.setattr(research_tools,'public_url',lambda _:True)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(lambda _:httpx.Response(
        200,text='<html><body><div id="app"></div></body></html>',headers={'Content-Type':'text/html'})),**kwargs))
    async def limited(*args,**kwargs):
        """模拟供应商429，携带敏感占位正文验证不会被误存或展示；不调用真实供应商。"""
        response=httpx.Response(429,text='private-fixture-protocol',request=httpx.Request('GET','https://provider.example.org/'))
        raise httpx.HTTPStatusError('private-fixture-protocol',request=response.request,response=response)
    monkeypatch.setattr(research_tools,'call_exa',limited)
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'official'}))
    assert result['error']=='provider_rate_limited' and result['read_outcome']=={
        'primary_status':'empty_body','fallback_status':'provider_rate_limited','http_status':200,'body_chars':0}
    with Session() as db:
        row=db.query(ToolCall).filter(ToolCall.job_id==broker.job_id).one()
        projection=tool_view(row)
        assert row.result['read_outcome']==result['read_outcome']
        assert projection['read_summary']=='网页无可用正文，备用读取服务受限'
        event=db.query(JobEvent).filter(JobEvent.job_id==broker.job_id,JobEvent.event_type=='tool.finished').one()
        assert event.payload['read_summary']==projection['read_summary']
        assert db.query(Evidence).filter(Evidence.job_id==broker.job_id).count()==0
        assert 'private-fixture-protocol' not in str(projection) and 'read_outcome' not in projection
    summary=empty_summary([{'tool':'fetch_source','url':url,'read_summary':projection['read_summary'],'status':'rate_limited'}])
    assert projection['read_summary'] in summary and '已读取' not in summary
    assert not read_summary({'primary_status':['旧数据坏值'],'fallback_status':'provider_rate_limited'})
    # 只让本夹具的冷却到期，避免污染后续真实Broker测试；原错误记录仍保留。
    with Session.begin() as db:db.query(ToolCall).filter(ToolCall.job_id==broker.job_id).one().retry_after_epoch=0


def test_transport_failure_then_fallback_success_keeps_both_outcomes(client,monkeypatch):
    """网络故障注入只验证降级协议，不作真实网站/买家成功；成功复用保留原阶段且不再发HTTP。"""
    from app import research_tools
    from app.db import Session,ToolCall
    url='https://example.org/transport-'+uuid.uuid4().hex
    broker=broker_for(client,url,'official');real_client=httpx.AsyncClient;calls=[]
    def handler(request):
        """request为真实MockTransport请求；仅模拟传输中断，不返回伪HTTP成功。"""
        calls.append(request);raise httpx.ConnectError('private-fixture-transport',request=request)
    monkeypatch.setattr(research_tools,'public_url',lambda _:True)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    async def fallback(*args,**kwargs):
        """返回隔离供应商响应形状；解析/存Evidence由实际工具完成，无客户保存。"""
        return 'Title: 隔离降级页面\nURL: '+url+'\n'+'隔离正文，不用于真实客户交付。'*20
    monkeypatch.setattr(research_tools,'call_exa',fallback)
    async def scenario():
        result=await broker.execute('fetch_source',{'url':url,'channel':'official'})
        assert result['sources'] and result['read_outcome']=={'primary_status':'failed','fallback_status':'completed'}
        again=await broker.execute('fetch_source',{'url':url,'channel':'official'})
        assert again['reused'] and again['read_outcome']==result['read_outcome']
    asyncio.run(scenario())
    assert len(calls)==1
    with Session() as db:
        row=db.query(ToolCall).filter(ToolCall.job_id==broker.job_id).one()
        assert row.attempts==1 and row.status=='completed'


def test_concurrent_pages_do_not_share_read_outcomes(client,monkeypatch):
    """client隔离库、monkeypatch本地故障注入；同Broker两个用户引用的故障与成功按URL隔离，不联网。"""
    from app import research_tools
    first='https://example.org/concurrent-empty-'+uuid.uuid4().hex
    second='https://example.org/concurrent-valid-'+uuid.uuid4().hex
    broker=broker_for(client,first+' '+second,'official');real_client=httpx.AsyncClient
    def handler(request):
        """request由MockTransport捕获；一个空框架、一个有段落的隔离正文，不生成客户事实。"""
        text='<html><body><div id="app"></div></body></html>' if str(request.url)==first else '<html><body><p>'+'隔离并发测试的独立正文段落。'*30+'</p></body></html>'
        return httpx.Response(200,text=text,headers={'Content-Type':'text/html'})
    monkeypatch.setattr(research_tools,'public_url',lambda _:True)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    async def empty(*args,**kwargs):return '# 无正文\nURL: '+first
    monkeypatch.setattr(research_tools,'call_exa',empty)
    async def scenario():
        left,right=await asyncio.gather(broker.execute('fetch_source',{'url':first,'channel':'official'}),broker.execute('fetch_source',{'url':second,'channel':'official'}))
        assert left['read_outcome']['primary_status']=='empty_body' and left['read_outcome']['fallback_status']=='empty_body'
        assert right['read_outcome']['primary_status']=='completed' and right['read_outcome']['fallback_status']=='not_attempted'
        assert not left['sources'] and len(right['sources'])==1
    asyncio.run(scenario())
