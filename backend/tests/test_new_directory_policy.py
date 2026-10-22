"""新公共目录沿既有robots边界读取，缓存不能绕过同源规则。"""
import asyncio
import uuid
import httpx
import pytest
from app import source_policy
from app.service import ServiceError


@pytest.mark.parametrize('domain',['b2b168.com','jc001.cn'])
def test_platform_subdomain_policy_reuses_original_path_and_crawl_delay(monkeypatch,domain):
    """domain为注册平台；原查询通配拒绝、缓存规则及crawl-delay用真实Protego解析，假后缀不匹配。"""
    host=uuid.uuid4().hex+'.'+domain;seen=[];original=httpx.AsyncClient
    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(200,text='User-agent: *\nDisallow: /private?*\nCrawl-delay: 3\n')
    def client(*args,**kwargs):
        """保留真实HTTP客户端，仅本fixture传输替换为无网络响应。"""
        return original(*args,**kwargs,transport=httpx.MockTransport(handle))
    monkeypatch.setattr(source_policy.httpx,'AsyncClient',client)
    with pytest.raises(ServiceError,match='site_robots_disallowed'):
        asyncio.run(source_policy.reading_delay('https://'+host+'/private?z=2&a=1'))
    assert asyncio.run(source_policy.reading_delay('https://'+host+'/public'))==3
    assert seen==['https://'+host+'/robots.txt']
    assert not source_policy.requires_policy('https://'+domain+'.evil.example/private')


@pytest.mark.parametrize('domain',['b2b168.com','jc001.cn'])
def test_cached_directory_body_cannot_bypass_forbidden_robots(client,monkeypatch,domain):
    """注册平台已有有效正文缓存时，真实Broker仍先检查同源拒绝规则，不读取正文/备用供应商。"""
    from app.db import Session,Conversation,Job,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':['industry_directory']})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离缓存政策'))
    job=submit(conv,{'content':'找深圳灯具经销商','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    url='https://'+uuid.uuid4().hex+'.'+domain+'/private'
    source=archive_sources(job['id'],[{'url':url,'title':'隔离缓存','body':'缓存正文仅验证规则。'*40}],'网页正文','industry_directory')[0]
    original=httpx.AsyncClient;seen=[]
    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(200,text='User-agent: *\nDisallow: /private\n')
    def transport(*args,**kwargs):
        """只替换本用例网络，使用真实客户端与Protego，不请求外网。"""
        return original(*args,**kwargs,transport=httpx.MockTransport(handle))
    monkeypatch.setattr(source_policy.httpx,'AsyncClient',transport)
    from app import research_tools
    monkeypatch.setattr(research_tools,'public_url',lambda value:True)
    broker=ToolBroker(job['id'],options,{'region':'深圳','products':[{'name':'吊灯'}]});broker.allowed_sources={source['id']}
    with pytest.raises(ServiceError,match='site_robots_disallowed'):
        asyncio.run(broker.fetch({'url':url,'channel':'industry_directory'}))
    assert seen==[url.rsplit('/',1)[0]+'/robots.txt']
