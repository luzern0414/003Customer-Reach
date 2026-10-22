"""商场目录保留分店上下文、原文店名和电话归属，不将品牌名改成法律公司。"""
import pytest
from app.public_directory import directory_text,mall_listing,mall_city_quote,directory_links
from app.evidence_context import target_names,evidence_excerpt
from app.source_catalog import reference_urls,requested_channels


def test_visible_directory_preserves_branch_context_and_discards_hidden_content():
    """公开模板保留分店/城市和完整商户块，未知URL、隐藏父级和伪电话不进入证据。"""
    content='<meta charset="utf-8"><div class="subbranch-det"><div class="de-tit">隔离沙井店 入驻品牌</div><div class="banner-exp">深圳隔离商场位于隔离路</div><div class="ctg"><div>灯饰</div><div>星烁灯饰</div><div>Tel: 13169928365</div><div hidden>隐藏号码</div></div></div>'
    url='http://www.leanju.com:8080/subbranch-detail/i-24.html'
    body=directory_text(content.encode(),url)
    assert '深圳隔离商场位于隔离路' in body and '隐藏号码' not in body
    assert mall_listing('星烁灯饰',body)=={'phone':'13169928365'}
    assert not mall_listing('其他灯饰',body)
    assert not directory_text(content.encode(),'https://example.org/subbranch-detail/i-24.html')
    assert not directory_text(('<section hidden>'+content+'</section>').encode(),url)


def test_explicit_storefront_anchor_keeps_long_directory_record():
    """目标必须来自用户指令和原文独立店名交集，不能锚定自家或无关品牌。"""
    body='隔离沙井店 入驻品牌\n深圳分店\n'+('其他门店\nTel: 12345678\n'*100)+'星烁灯饰\nTel: 13169928365\n'
    names=target_names('请查找深圳商场的星烁灯饰门店',[{'title':'目录','body':body}],'深圳')
    assert names==['星烁灯饰']
    assert '星烁灯饰' in evidence_excerpt(body,names,3500)
    assert target_names('我们是星烁灯饰，请查找深圳客户',[{'title':'目录','body':body}],'深圳','星烁灯饰')==[]
    assert reference_urls('读取 http://www.leanju.com:8080/subbranch-detail/i-24.html',['mall_directory'])[0]['channel']=='mall_directory'
    assert requested_channels('请查品牌官方门店目录',['brand_directory'])==['brand_directory']


def test_storefront_role_and_phone_require_same_listed_entry(client):
    """client为隔离库；入驻目录可以证明门店记录，但不能借另一商户电话或替法律名称。"""
    from app.service import checked_candidate,ServiceError
    from app.schemas import Candidate
    body='隔离沙井店 入驻品牌\n作为隔离商场在深圳西部的重要布点。\n了解更多\n灯饰\n星烁灯饰\nTel: 13169928365\n另一灯饰\nTel: 13794469638'
    source={'id':'mall-source','body':body,'url':'http://www.leanju.com:8080/subbranch-detail/i-24.html','title':'商场目录','captured_at':'2026-10-03 15:00:00','kind':'网页正文','channel':'mall_directory'}
    facts=[{'field':'name','value':'星烁灯饰','quote':'星烁灯饰','source_id':'mall-source'},
        {'field':'buyer_role','value':'入驻品牌','quote':'隔离沙井店 入驻品牌','source_id':'mall-source'},
        {'field':'phone','value':'13169928365','quote':'星烁灯饰\nTel: 13169928365','source_id':'mall-source'}]
    candidate=Candidate(display_name='星烁灯饰',city='深圳',buyer_role='retailer',match_reason='隔离目录记录',facts=facts)
    clean,citations=checked_candidate(candidate,{'mall-source':source})
    assert clean['phone']['value']=='13169928365'
    assert next(item['quote'] for item in citations if item['field']=='city')=='作为隔离商场在深圳西部的重要布点。'
    assert not mall_city_quote('星烁灯饰','东莞',body)
    assert not mall_city_quote('其他灯饰','深圳',body)
    wrong=candidate.model_copy(update={'facts':[candidate.facts[0],candidate.facts[1],candidate.facts[2].model_copy(update={'value':'13794469638','quote':'另一灯饰\nTel: 13794469638'})]})
    with pytest.raises(ServiceError,match='商场电话未关联'):checked_candidate(wrong,{'mall-source':source})
    with pytest.raises(ServiceError):checked_candidate(candidate.model_copy(update={'display_name':'深圳星烁灯饰有限公司'}),{'mall-source':source})


def test_branch_list_preserves_only_actual_visible_same_site_links():
    """分店入口只保留真实可见href，不从序号猜URL、不将隐藏/外域/查询链接扩成许可。"""
    url='http://www.leanju.com:8080/subbranch/'
    content='<html><a href="/subbranch-detail/i-91.html">隔离分店甲</a><a href="/subbranch-detail/i-91.html">重复入口</a><a href="/subbranch-detail/i-92.html"><img alt="隔离分店乙"></a><div hidden><a href="/subbranch-detail/i-93.html">隐藏分店</a></div><a href="http://example.org/subbranch-detail/i-94.html">外站</a><a href="/subbranch-detail/i-95.html?x=1">查询链接</a><a href="/subbranch-detail/i-96.html"><span hidden>隐藏名</span>隔离分店丙</a><script>nextStore(97)</script></html>'
    body=directory_text(content.encode(),url)
    profile={'region':'深圳','products':[{'name':'吊灯'}]}
    links=directory_links(body,url,profile,'mall_directory')
    assert links==['http://www.leanju.com:8080/subbranch-detail/i-91.html','http://www.leanju.com:8080/subbranch-detail/i-92.html','http://www.leanju.com:8080/subbranch-detail/i-96.html']
    assert '隐藏名' not in body and '隐藏分店' not in body and '外站' not in body
    assert not directory_links(body,url,{**profile,'region':'成都'},'mall_directory')
    assert not directory_links(body,url,{**profile,'products':[{'name':'软件'}]},'mall_directory')
    assert not directory_links(body,url,profile,'qcc_public')
    assert not directory_text(content.encode(),'http://example.org/subbranch/')


def test_agent_follows_branch_list_and_skips_list_extraction(client,monkeypatch):
    """本任务原入口派生许可；真实Broker/gap/read不越过预算，列表零模型不制造买家。"""
    import asyncio,uuid
    from app import agent
    from app.db import Session,Conversation,Job,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings,ServiceError
    from app.research_tools import ToolBroker
    url='http://www.leanju.com:8080/subbranch/';detail='http://www.leanju.com:8080/subbranch-detail/i-91.html'
    profile={'region':'深圳','products':[{'name':'LED吊灯'}]}
    options=save_settings({'enabled_channels':['mall_directory'],'max_reads':2})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离分店入口'))
    job=submit(conversation,{'content':'自主找深圳灯饰店','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    body='分店入口：隔离分店甲\n分店链接：'+detail
    source=archive_sources(job['id'],[{'url':url,'title':'分店列表','body':body}],'网页正文','mall_directory')[0]
    archive_sources(job['id'],[{'url':detail,'title':'隔离详情','body':'隔离缓存测试资料。'*50}],'网页正文','mall_directory')
    broker=ToolBroker(job['id'],options,profile);broker.allowed_sources={source['id']}
    assert asyncio.run(broker.fetch({'url':detail,'channel':'mall_directory'}))['cached']
    with pytest.raises(ServiceError,match='url_not_discovered'):
        asyncio.run(broker.fetch({'url':detail.replace('91','99'),'channel':'mall_directory'}))
    state={'job_id':job['id'],'profile':profile,'options':options,'cursor':0,'steps':[{'channel':'mall_directory'}],
        'saved_ids':[],'source_ids':[source['id']],'recent_read_source_ids':[source['id']],
        'read_attempted_urls':[url],'reference_urls':[],'warnings':['provider_rate_limited'],'prompt':'自主找深圳灯饰店'}
    async def model(*args,**kwargs):
        """列表不得调用客户提取；调用即测试失败。"""
        raise AssertionError('入口列表不应生成客户')
    monkeypatch.setattr(agent,'cached_model',model)
    extracted=asyncio.run(agent.extract_node(state))
    assert extracted['candidates']==[] and 'procurement' not in extracted['gaps']
    update=asyncio.run(agent.gap_node(state));assert update['direct_read_pending']
    seen=[]
    async def execute(self,name,args):
        """仅记录实际图选链，返回无正文不冒称外部成功。"""
        seen.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    read=asyncio.run(agent.read_node({**state,**update}))
    assert seen==[{'url':detail,'channel':'mall_directory'}]
    assert detail in read['read_attempted_urls']
    assert not asyncio.run(agent.gap_node({**state,'options':{**options,'max_reads':0}}))['direct_read_pending']


def test_full_target_does_not_reextract_same_brand_from_other_branch(client,monkeypatch):
    """相同店名在不同分店不代表同一客户；同分店新证据仍保留正常补全模型流程。"""
    import asyncio,uuid
    from app import agent
    from app.db import Session,Lead,identifier
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    name='隔离同名灯饰';key=identifier();job=uuid.uuid4().hex
    old_url='http://www.leanju.com:8080/subbranch-detail/i-91.html'
    with Session.begin() as db:db.add(Lead(id=key,display_name=name,city='深圳',dedupe_key=uuid.uuid4().hex,
        evidence=[{'field':'name','value':name,'url':old_url}]))
    other=archive_sources(job,[{'url':old_url.replace('91','92'),'title':'其他分店',
        'body':'隔离另一分店 入驻品牌\n'+name+'\nTel: 13900000000\n'+('隔离资料。'*30)}],'网页正文','mall_directory')[0]
    calls=[]
    async def model(state,schema,prompt,label):
        """只记录模型入口，无真实网络或客户产出。"""
        calls.append(label);return CandidateBatch(candidates=[],missing_fields=[])
    monkeypatch.setattr(agent,'cached_model',model)
    state={'job_id':job,'saved_ids':[key],'source_ids':[other['id']],'recent_read_source_ids':[other['id']],
        'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'prompt':'自主找深圳灯饰店',
        'options':{'max_leads':1,'enabled_channels':['mall_directory']},'cursor':1,'plan':{'target_roles':['retailer']}}
    assert asyncio.run(agent.extract_node(state))=={'candidates':[]}
    assert not calls
    same=archive_sources(job,[{'url':old_url,'title':'原分店',
        'body':'隔离原分店 入驻品牌\n'+name+'\nTel: 13900000000\n'+('隔离资料。'*30)}],'网页正文','mall_directory')[0]
    asyncio.run(agent.extract_node({**state,'source_ids':[same['id']],'recent_read_source_ids':[same['id']]}))
    assert calls==['extract:1']


def test_full_branch_target_skips_other_branch_before_http_and_changes_channel(client,monkeypatch):
    """满额且name证据分店明确时，gap/read先排除其他分店，把预算留给另一网站；未满额不限制新发现。"""
    import asyncio,uuid
    from app import agent,source_catalog
    from app.db import Session,Lead,Conversation,Job,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    from app.public_directory import matches_branches
    old='http://www.leanju.com:8080/subbranch-detail/i-91.html';other=old.replace('91','92')
    assert not matches_branches(other,[{'/subbranch-detail/i-91.html'}])
    assert matches_branches(other,[]) and matches_branches(other,[set()])
    assert matches_branches(old,[{'/subbranch-detail/i-91.html'}])
    assert matches_branches('https://www.yunfale.com/',[{'/subbranch-detail/i-91.html'}])
    options=save_settings({'enabled_channels':['mall_directory','industry_directory'],'max_leads':1,'max_reads':4})
    conv=identifier();key=identifier()
    with Session.begin() as db:
        db.add(Conversation(id=conv,title='隔离跨渠道补全'))
        db.add(Lead(id=key,display_name='隔离灯饰',city='深圳',dedupe_key=uuid.uuid4().hex,
            evidence=[{'field':'name','value':'隔离灯饰','url':old}]))
    job=submit(conv,{'content':'找深圳灯饰门店并从2个不同网站核验','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    source=archive_sources(job['id'],[{'url':'http://www.leanju.com:8080/subbranch/','title':'隔离列表',
        'body':'分店入口：隔离其他分店\n分店链接：'+other}],'网页正文','mall_directory')[0]
    monkeypatch.setattr(source_catalog,'public_entries',lambda *args:[{'url':other,'channel':'mall_directory'},
        {'url':'https://www.yunfale.com/','channel':'industry_directory'}])
    state={'job_id':job['id'],'saved_ids':[key],'source_ids':[source['id']],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'prompt':'找深圳灯饰门店并从2个不同网站核验','options':options,'cursor':0,'steps':[{'channel':'mall_directory','query':'隔离查询'}],
        'read_attempted_urls':['http://www.leanju.com:8080/subbranch/'],'reference_urls':[],'warnings':['provider_rate_limited']}
    update=asyncio.run(agent.gap_node(state))
    assert update['direct_read_pending'] and update['steps'][update['cursor']]['channel']=='industry_directory'
    seen=[]
    async def execute(self,name,args):
        """name/args为实际图选页调用，仅记录、不宣称网络成功。"""
        seen.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    asyncio.run(agent.read_node({**state,**update}))
    assert seen==[{'url':'https://www.yunfale.com/','channel':'industry_directory'}]
    discovery=asyncio.run(agent.gap_node({**state,'options':{**options,'max_leads':2}}))
    assert discovery['steps'][discovery['cursor']]['channel']=='mall_directory'
def test_mall_header_and_telephone_are_not_tenant_listing():
    """实际Agent曾把商场名判作入驻租户；公共标题/电话必须从子商户列表排除。"""
    from app.public_directory import mall_listing
    from app.evidence_role import scoped_role
    body='坪山中心店\nTel:0755-11111111\n商场介绍。\n坪山中心店  入驻品牌\n隔离灯饰商户\nTel:13900000000\n'
    assert not mall_listing('坪山中心店',body)
    assert mall_listing('隔离灯饰商户',body)['phone']=='13900000000'
    assert not scoped_role('坪山中心店','入驻品牌','坪山中心店  入驻品牌','乐安居官网',True,body)
