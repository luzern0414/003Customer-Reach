"""公开公告目录按真实href发现，不能凭URL形状授予读取许可或放宽ICP。"""
from app.public_directory import procurement_directory_text, announcement_links,procurement_links

URL='https://www.ccgp.gov.cn/cggg/dfgg/gkzb/'
DETAIL=URL+'202610/t20261003_27439999.htm'
PROFILE={'region':'深圳','products':[{'name':'LED灯具'}]}


def test_encoded_list_keeps_title_record_and_actual_href():
    """GB2312列表必须可读；外域链接、未知模板和隐藏记录不产生入口。"""
    content=f'<html><meta charset="gb2312"><ul class="c_list_bid"><li><a title="深圳灯具采购公告" href="{DETAIL}">深圳灯具采购公告</a><em>区域：深圳</em><em>采购人：隔离验证单位</em></li><li hidden><a href="{DETAIL}">深圳照明采购</a></li><li><a href="https://example.org/other">深圳照明采购</a></li></ul></html>'.encode('gb2312')
    body=procurement_directory_text(content,URL)
    assert '深圳灯具采购公告' in body and '隔离验证单位' in body
    assert announcement_links(body,URL,PROFILE)==[DETAIL]
    assert 'example.org' not in body
    assert not procurement_directory_text(content,'https://example.org/')
    assert not announcement_links(body,URL,{**PROFILE,'region':'成都'})
    assert not announcement_links(body,URL,{**PROFILE,'products':[{'name':'软件'}]})
    assert not announcement_links(body.replace('灯具','手术灯具'),URL,PROFILE)


def test_next_page_requires_visible_forward_href_and_matching_icp():
    """真实href仅决定发现；脚本声明、隐藏/外域/回退链接均不能生成翻页许可。"""
    listing=f'<ul class="c_list_bid"><li><a href="{DETAIL}">隔离家具公告</a><em>北京</em></li></ul>'
    next_url=URL+'index_1.htm'
    body=procurement_directory_text((listing+'<a href="index_1.htm">下一页</a>').encode(),URL)
    assert procurement_links(body,URL,PROFILE)==[next_url]
    assert not procurement_links(body,URL,{**PROFILE,'products':[{'name':'软件'}]})
    assert not procurement_links(body,next_url,PROFILE)
    for navigation in ['<div hidden><a href="index_1.htm">下一页</a></div>',
                       '<a href="https://example.org/index_1.htm">下一页</a>',
                       '<script>createPageHTML(100,0,"index","htm");</script>',
                       '<a href="javascript:next()">下一页</a>']:
        text=procurement_directory_text((listing+navigation).encode(),URL)
        assert not procurement_links(text,URL,PROFILE)
    assert not procurement_directory_text(b'<a href="index_1.htm">next</a>',URL)
    matching=f'公告标题：深圳灯具采购\n列表记录：深圳 灯具采购\n公告链接：{DETAIL}\n\n下一页链接：{next_url}'
    assert procurement_links(matching,URL,PROFILE)==[DETAIL,next_url]


def test_list_extraction_skips_model_but_detail_still_uses_model(client,monkeypatch):
    """Agent列表不冒充采购人，省去模型调用；详情正文仍进入结构化提取。"""
    import asyncio,uuid
    from app import agent
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    job=uuid.uuid4().hex
    listing=archive_sources(job,[{'url':URL,'title':'公开招标列表','body':'公告标题：深圳灯具采购\n列表记录：深圳采购公告\n公告链接：'+DETAIL+'\n'+('隔离列表资料。'*30)}],'网页正文','ccgp')[0]
    calls=[]
    async def model(state,schema,prompt,label):
        """仅记录调用，不生成事实，不能作真实模型验收。"""
        calls.append(label);return CandidateBatch(candidates=[],missing_fields=[])
    monkeypatch.setattr(agent,'cached_model',model)
    state={'job_id':job,'profile':PROFILE,'saved_ids':[],'source_ids':[listing['id']],
        'recent_read_source_ids':[listing['id']],'prompt':'自主查深圳灯具采购单位',
        'options':{'max_leads':1,'enabled_channels':['ccgp']},'plan':{'target_roles':['project_buyer']},'cursor':0}
    result=asyncio.run(agent.extract_node(state))
    assert result['candidates']==[] and 'procurement' in result['gaps'] and not calls
    detail=archive_sources(job,[{'url':DETAIL,'title':'深圳灯具采购公告','body':'深圳灯具采购公告\n'+('隔离公告详情资料。'*50)}],'网页正文','ccgp')[0]
    asyncio.run(agent.extract_node({**state,'source_ids':[detail['id']],'recent_read_source_ids':[detail['id']]}))
    assert calls==['extract:0']


def test_gap_and_broker_follow_next_page_with_original_budget(client,monkeypatch):
    """已读列表派生下一页许可，图限流后继续读；未知页/预算耗尽拒绝且不模拟外部成功。"""
    import asyncio,uuid
    import pytest
    from app.db import Session,Conversation,Job,identifier
    from app.service import submit,save_settings,ServiceError
    from app.gateway import archive_sources
    from app.research_tools import ToolBroker
    from app.agent import gap_node,read_node
    options=save_settings({'enabled_channels':['ccgp'],'max_reads':2})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离采购下一页'))
    job=submit(conversation,{'content':'自主找深圳照明采购单位','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    next_url=URL+'index_1.htm'
    source=archive_sources(job['id'],[{'url':URL,'title':'隔离列表',
        'body':'隔离公告资料。'*25+'\n下一页链接：'+next_url}],'网页正文','ccgp')[0]
    archive_sources(job['id'],[{'url':next_url,'title':'隔离第二页','body':'隔离缓存资料。'*50}],'网页正文','ccgp')
    broker=ToolBroker(job['id'],options,PROFILE);broker.allowed_sources={source['id']}
    assert asyncio.run(broker.fetch({'url':next_url,'channel':'ccgp'}))['cached']
    with pytest.raises(ServiceError,match='url_not_discovered'):
        asyncio.run(broker.fetch({'url':URL+'index_9.htm','channel':'ccgp'}))
    state={'job_id':job['id'],'options':options,'profile':PROFILE,'steps':[{'channel':'ccgp'}],
        'cursor':0,'source_ids':[source['id']],'saved_ids':[],'reference_urls':[],
        'read_attempted_urls':[URL],'warnings':['provider_rate_limited'],'prompt':'自主找深圳照明采购单位'}
    update=asyncio.run(gap_node(state));assert update['direct_read_pending']
    seen=[]
    async def execute(self,name,args):
        """只记录真实图选链，不生成虚构网页或客户。"""
        seen.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    read=asyncio.run(read_node({**state,**update}))
    assert seen==[{'url':next_url,'channel':'ccgp'}]
    assert not asyncio.run(gap_node({**state,**update,**read}))['direct_read_pending']
    assert not asyncio.run(gap_node({**state,'options':{**options,'max_reads':0}}))['direct_read_pending']


def test_broker_follows_only_in_scope_actual_directory_link(client,monkeypatch):
    """真实Broker的读取许可与图选链路运行；网络替身不代表外部验收。"""
    import asyncio,uuid
    import pytest
    from app.db import Session,Evidence,Job,Conversation,identifier
    from app.service import submit,save_settings,ServiceError
    from app.agent import read_node
    from app.research_tools import ToolBroker
    from app.gateway import archive_sources
    options=save_settings({'enabled_channels':['ccgp'],'max_reads':2})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离目录验证'))
    job=submit(conversation,{'content':'查找深圳灯具采购公告','attachment_ids':[],'client_token':uuid.uuid4().hex})
    body=f'公告标题：深圳灯具采购公告\n列表记录：深圳灯具采购公告 区域：深圳 采购人：隔离验证单位\n公告链接：{DETAIL}'
    sources=archive_sources(job['id'],[{'url':URL,'title':'公开公告列表','body':body}], '网页正文','ccgp')
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    broker=ToolBroker(job['id'],options,PROFILE);broker.allowed_sources.update(row['id'] for row in sources)
    real_fetch=ToolBroker.fetch
    # 缓存模拟已读详情，fetch真实许可校验必须先运行，不执行任何公网请求。
    archive_sources(job['id'],[{'url':DETAIL,'title':'深圳灯具采购公告','body':'深圳灯具采购公告\n'+('隔离测试正文，仅验证工具缓存，不是真实买家资料。'*20)}],'网页正文','ccgp')
    assert asyncio.run(real_fetch(broker,{'url':DETAIL,'channel':'ccgp'}))['cached']
    with pytest.raises(ServiceError,match='url_not_discovered'):
        asyncio.run(real_fetch(broker,{'url':DETAIL.replace('27439999','27438888'),'channel':'ccgp'}))
    seen=[]
    async def fetch(self,args):
        """self为Broker、args为图选择真实目录href；只记录，不伪造已获取正文。"""
        seen.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'fetch',fetch)
    state={'job_id':job['id'],'options':options,'profile':PROFILE,'steps':[{'channel':'ccgp'}],
        'cursor':0,'source_ids':[sources[0]['id']],'reference_urls':[],'saved_ids':[],'plan':{'target_roles':['end_user']}}
    asyncio.run(read_node(state))
    assert seen==[{'url':DETAIL,'channel':'ccgp'}]
