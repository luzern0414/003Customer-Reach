"""真实网站外链补查必须同主体、可见、已启用；本地夹具不冒充公网多站获客。"""
import asyncio
import uuid
from app.public_website import website_text,website_links
from app.industry_navigation import factual_body,WEBSITE_MARKER,NAVIGATION_MARKER,navigation_text,navigation_links


def test_links_keep_original_query_and_ignore_hidden_footer_and_unsafe_urls():
    """原href查询不重排；隐藏标签/脚本/页尾/凭据/外端口不能成为新读取入口。"""
    content='''<div>公司网址：<a href="https://example.org/?z=2&amp;blank=&amp;a=1">网站地址</a></div>
    <div hidden><a href="https://hidden.example.org/">公司官网</a></div>
    <div><span hidden>公司网站</span><a href="https://hidden-label.example.org/">普通链接</a></div>
    <div><span style="display:none">企业网址</span><a href="https://hidden-style.example.org/">普通链接</a></div>
    <footer><a href="https://footer.example.org/">公司官网</a></footer>
    <a href="https://user@example.org/">企业官网</a><a href="https://example.org:9443/">企业官网</a>
    <script><a href="https://script.example.org/">企业官网</a></script>'''
    appendix=website_text(content.encode(),'https://directory.example.org/company')
    assert 'https://example.org/?z=2&blank=&a=1' in appendix
    assert all(token not in appendix for token in ['hidden','footer','user@','9443','script'])
    assert factual_body('原始事实\n'+appendix)=='原始事实'
    assert not website_text('<a href="https://example.org/">普通推荐链接</a>'.encode(),'https://directory.example.org/')
    assert not website_text('<div>公司网站：<a href="https://example.org/">网址</a><a href="https://other.org/">推广</a></div>'.encode(),'https://directory.example.org/')
    from app.source_content import has_content
    assert not has_content({'body':appendix,'title':'平台标题','url':'https://directory.example.org/'})


def test_only_saved_single_subject_page_and_enabled_channel_grant_links():
    """平台目录、无同源name、其他主体/关闭官网不能取得外链许可；标记本身不证明企业事实。"""
    source={'id':'s1','url':'https://directory.example.org/company','title':'隔离照明有限公司','kind':'网页正文',
            'body':'原文\n'+WEBSITE_MARKER+'\n网站入口：公司网站\n网站链接：https://example.org/'}
    lead={'display_name':'隔离照明有限公司','evidence':[{'field':'name','value':'隔离照明有限公司','source_id':'s1'}]}
    assert website_links([source],[lead],['official'])==[{'url':'https://example.org/','channel':'official'}]
    assert not website_links([source],[],['official'])
    assert not website_links([{**source,'title':'企业目录'}],[lead],['official'])
    assert not website_links([source],[{**lead,'evidence':[]}],['official'])
    assert not website_links([source],[lead],['b2b_1688'])
    platform={**source,'body':source['body'].replace('https://example.org/','https://1688.com/shop/')}
    assert not website_links([platform],[lead],['official'])
    legal={**source,'body':'原文\n'+website_text('<a href="https://other.org/">其他主体有限公司</a><a href="https://example.org/">隔离照明有限公司</a>'.encode(),source['url'],source['title'])}
    assert website_links([legal],[lead],['official'])==[{'url':'https://example.org/','channel':'official'}]
    assert 'other.org' not in legal['body']


def test_target_region_lighting_subcategories_exclude_other_cities():
    """实际Agent曾读外地室外照明灯具目录，分类地域拒绝不能只覆盖灯饰黄页。"""
    profile={'region':'深圳','products':[{'name':'壁灯'}]};url='https://www.b2b168.com/dengshi/'
    content='<a href="/beijing-dengshi/x/">北京室外照明灯具黄页</a><a href="/chongqing-dengshi/x/">重庆室外照明灯具黄页</a><a href="/shenzhen-dengshi/x/">深圳室外照明灯具黄页</a>'
    links=navigation_links(navigation_text(content.encode(),url,profile),url,profile)
    assert links==['https://www.b2b168.com/shenzhen-dengshi/x/']


def test_home_lighting_does_not_follow_same_city_other_category_or_vehicle_lamps():
    """地区命中不能抵消明文品类冲突；用户明确混合产品或未知企业名称保持可核验。"""
    from app.industry_navigation import relevant_detail
    profile={'region':'深圳','products':[{'name':'壁灯'}]};parent='https://shop.jc001.cn/'
    link='https://shop.jc001.cn/gc-001001002-r1-265/'
    for label in ['深圳地板企业','深圳洁具企业','深圳吊顶企业','深圳管材企业','车灯设计公司黄页']:
        assert not relevant_detail(label,link,parent,profile)
    assert relevant_detail('深圳灯具企业',link,parent,profile)
    assert relevant_detail('深圳未知名称有限公司',link,parent,profile)
    assert relevant_detail('深圳地板企业',link,parent,{**profile,'products':[{'name':'壁灯'},{'name':'地板'}]})
    assert relevant_detail('车灯设计公司黄页',link,parent,{**profile,'products':[{'name':'车灯'}]})


def test_city_only_category_links_require_actual_visible_product_context():
    """真实Agent日志显示同城分类标签都只写深圳；保留唯一可见标题，旧附录无分类不从编号猜。"""
    profile={'region':'深圳','products':[{'name':'壁灯'}]};parent='https://shop.jc001.cn/'
    content='<section><h3>灯具</h3><a href="/gc-111-r1-265/">深圳</a></section><section><h3>地板</h3><a href="/gc-222-r1-265/">深圳</a></section><section><a href="/gc-333-r1-265/">深圳</a></section>'
    result=navigation_text(content.encode(),parent,profile)
    assert navigation_links(result,parent,profile)==[parent+'gc-111-r1-265/']
    legacy=NAVIGATION_MARKER+'\n目录入口：深圳\n目录链接：'+parent+'gc-111-r1-265/\n目录分类：灯具\n\n目录入口：深圳\n目录链接：'+parent+'gc-222-r1-265/'
    assert navigation_links(legacy,parent,profile)==[parent+'gc-111-r1-265/']
    # 明确混合产品可进入其真实分类，未知链接仍不自动扩为目标产品。
    mixed={**profile,'products':[{'name':'壁灯'},{'name':'地板'}]}
    result=navigation_text(content.encode(),parent,mixed)
    assert navigation_links(result,parent,mixed)==[parent+'gc-111-r1-265/',parent+'gc-222-r1-265/']


def test_generated_link_annotation_cannot_be_saved_as_website_fact():
    """即使修复模型能看到工具原始结果，派生导航标记也不能通过自动事实校验。"""
    from app.service import checked_candidate,ServiceError
    from app.schemas import Candidate,Fact
    import pytest
    body='隔离照明有限公司经销灯具。\n'+WEBSITE_MARKER+'\n网站入口：公司网站\n网站链接：https://example.org/'
    source={'s1':{'body':body,'url':'https://directory.example.org/','title':'隔离照明有限公司','captured_at':'2026-10-04 08:00:00','kind':'网页正文'}}
    candidate=Candidate(display_name='隔离照明有限公司',city='',match_reason='隔离派生链接校验',buyer_role='unknown',facts=[
        Fact(field='name',value='隔离照明有限公司',quote='隔离照明有限公司经销灯具。',source_id='s1'),
        Fact(field='website',value='https://example.org/',quote='网站链接：https://example.org/',source_id='s1')])
    with pytest.raises(ServiceError,match='website的引文未能在原始资料中找到'):checked_candidate(candidate,source)


def test_gap_read_and_broker_follow_saved_owner_link_before_generic_directory(client):
    """真实gap/read/Broker缓存路径核验网址许可，检索受限仍补原主体；不调用外部网络/模型，不称真实多站获客。"""
    from app import agent
    from app.db import Session,Conversation,Job,Lead,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':['official','industry_directory'],'max_reads':3,'max_leads':1})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离企业外链'))
    job=submit(conv,{'content':'找深圳经销商并至少2个网站核验','attachment_ids':[],'client_token':uuid.uuid4().hex})
    body='隔离照明有限公司经销灯具。'*20+'\n'+website_text('<div>企业网址：<a href="https://example.org/company">网站</a></div>'.encode(),'https://www.yunfale.com/company/detail/12/')
    source=archive_sources(job['id'],[{'url':'https://www.yunfale.com/company/detail/12/','title':'隔离照明有限公司','body':body}],'网页正文','industry_directory')[0]
    cached=archive_sources(uuid.uuid4().hex,[{'url':'https://example.org/company','title':'隔离照明有限公司','body':'隔离照明有限公司公开介绍及联系原文。'*20}],'网页正文','official')[0]
    key=identifier()
    with Session.begin() as db:
        row=db.get(Job,job['id']);row.status='running';row.lead_ids=[key]
        db.add(Lead(id=key,display_name='隔离照明有限公司',buyer_role='dealer',facts={},
                    evidence=[{'field':'name','value':'隔离照明有限公司','source_id':source['id'],'url':source['url']}]))
    state={'job_id':job['id'],'profile':{'region':'深圳','products':[{'name':'壁灯'}]},'options':options,
        'source_ids':[source['id']],'saved_ids':[key],'attempts':[], 'prompt':'找深圳经销商并至少2个网站核验',
        'steps':[{'channel':'industry_directory','query':'隔离查询'}],'cursor':0,'warnings':['provider_rate_limited'],'reference_urls':[]}
    update=asyncio.run(agent.gap_node(state))
    assert update['steps'][update['cursor']]['channel']=='official' and update['direct_read_pending']
    result=asyncio.run(agent.read_node({**state,**update}))
    assert cached['id'] in result['recent_read_source_ids'] and not result['read_empty']
    broker=ToolBroker(job['id'],options,state['profile'])
    from app.service import ServiceError
    import pytest
    with pytest.raises(ServiceError,match='url_not_discovered'):
        asyncio.run(broker.fetch({'url':'https://example.org/not-listed','channel':'official'}))


def test_owner_contact_navigation_prioritizes_same_shop_and_excludes_platform_or_other_shop():
    """实际目录附录只授发现；已存单主体的同公司联系页优先，不借跨商户/平台/外端口入口。"""
    name='隔离联系照明有限公司';parent='http://shop.jc001.cn/9136/'
    source={'id':'s','url':parent,'title':name,'kind':'网页正文','channel':'industry_directory','body':name+'经销灯具。\n'+NAVIGATION_MARKER+'\n'+
        '\n'.join('目录入口：联系方式\n目录链接：'+link for link in [
            parent+'contact.html?original=&z=2', 'http://shop.jc001.cn/9137/contact.html',
            'http://shop.jc001.cn/contact.html','http://shop.jc001.cn:9443/9136/contact.html',
            'http://user@shop.jc001.cn/9136/contact.html'])+'\n'+WEBSITE_MARKER+'\n网站入口：公司网站\n网站链接：https://example.org/'}
    lead={'display_name':name,'evidence':[{'field':'name','value':name,'source_id':'s','url':parent}]}
    result=website_links([source],[lead],['official','industry_directory'])
    assert result[0]=={'url':parent+'contact.html?original=&z=2','channel':'industry_directory'}
    assert len(result)==2 and result[1]['url']=='https://example.org/'
    assert not website_links([{**source,'title':'企业目录'}],[lead],['industry_directory'])
    assert not website_links([source],[{**lead,'evidence':[]}],['industry_directory'])
    assert not website_links([{**source,'body':source['body'].split(WEBSITE_MARKER,1)[0]}],[lead],['mall_directory'])


def test_gap_and_read_prioritize_owner_contact_link_over_news_after_directory_quota(client,monkeypatch):
    """client隔离库、monkeypatch只禁止网络；真实gap/read/Broker缓存证明联系页优先且仍检查robots调用。"""
    from app import agent,research_tools,source_policy
    from app.db import Session,Job,Lead,identifier
    from app.gateway import archive_sources
    from app.service import save_settings
    options=save_settings({'enabled_channels':['industry_directory'],'max_reads':6,'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具经销商','client_token':uuid.uuid4().hex}).json()['id']
    name='隔离联系补查照明有限公司';parent='http://shop.jc001.cn/9146/';contact=parent+'contact.html'
    body=name+'经销灯具。\n'+NAVIGATION_MARKER+'\n目录入口：'+name+'新闻\n目录链接：'+parent+'news/1.html\n目录入口：联系方式\n目录链接：'+contact
    source=archive_sources(job,[{'url':parent,'title':name,'body':body}],'网页正文','industry_directory')[0]
    cached=archive_sources(uuid.uuid4().hex,[{'url':contact,'title':name,'body':name+'实际联系正文。'*30}],'网页正文','industry_directory')[0]
    key=identifier()
    with Session.begin() as db:
        row=db.get(Job,job);row.status='running';row.lead_ids=[key]
        db.add(Lead(id=key,display_name=name,city='深圳',buyer_role='dealer',dedupe_key=uuid.uuid4().hex,
            evidence=[{'field':'name','value':name,'source_id':source['id'],'url':parent}]))
    checked=[]
    async def policy(url):checked.append(url);return 1
    monkeypatch.setattr(source_policy,'reading_delay',policy)
    monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    state={'job_id':job,'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'options':options,
        'source_ids':[source['id']],'saved_ids':[key],'attempts':[],'prompt':'補查深圳灯具经销商',
        'steps':[{'channel':'industry_directory','query':'旧查询'}],'cursor':0,'warnings':['provider_rate_limited'],'reference_urls':[]}
    update=asyncio.run(agent.gap_node(state))
    assert update['direct_read_target']=={'url':contact,'channel':'industry_directory'}
    result=asyncio.run(agent.read_node({**state,**update}))
    assert cached['id'] in result['recent_read_source_ids'] and checked==[contact]


def test_complete_contact_prefers_fifth_cross_site_link_and_broker_allows_it(client):
    """client隔离库；前四同站联系页不能挡住第五独立站，gap/read/Broker真实缓存路径无需网络。"""
    from app import agent
    from app.public_website import prioritize_websites
    from app.db import Session,Job,Lead,identifier
    from app.gateway import archive_sources
    from app.service import save_settings
    options=save_settings({'enabled_channels':['official','industry_directory'],'max_reads':1,'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳经销商并至少2个网站核验','client_token':uuid.uuid4().hex}).json()['id']
    name='隔离跨站照明有限公司';parent='http://shop.jc001.cn/9156/';external='https://example.org/cross-site'
    body=name+'经销灯具。'*20+'\n'+NAVIGATION_MARKER+'\n'+'\n'.join(
        '目录入口：联系方式\n目录链接：'+parent+'contact.html?original='+str(i) for i in range(4))+'\n'+WEBSITE_MARKER+'\n网站入口：公司网站\n网站链接：'+external
    source=archive_sources(job,[{'url':parent,'title':name,'body':body}],'网页正文','industry_directory')[0]
    cached=archive_sources(uuid.uuid4().hex,[{'url':external,'title':name,'body':name+'独立网站公开正文。'*25}],'网页正文','official')[0]
    key=identifier();facts={field:{'value':value} for field,value in [('phone','13500001111'),('address','隔离地址'),('categories','灯具')]}
    evidence=[{'field':'name','value':name,'source_id':source['id'],'url':parent}]
    with Session.begin() as db:
        row=db.get(Job,job);row.status='running';row.lead_ids=[key]
        db.add(Lead(id=key,display_name=name,city='深圳',buyer_role='dealer',facts=facts,evidence=evidence))
    stored={'display_name':name,'facts':facts,'evidence':evidence}
    links=website_links([source],[stored],options['enabled_channels'])
    assert len(links)==5 and links[4]['url']==external
    assert prioritize_websites(links,[stored],2)[0]['url']==external
    assert prioritize_websites(links,[{**stored,'facts':{}}],2)[0]['url']!=external
    state={'job_id':job,'profile':{'region':'深圳','products':[{'name':'壁灯'}]},'options':options,
        'source_ids':[source['id']],'saved_ids':[key],'attempts':[],'prompt':'找深圳经销商并至少2个网站核验',
        'steps':[{'channel':'industry_directory','query':'旧查询'}],'cursor':0,'warnings':['provider_rate_limited'],'reference_urls':[]}
    update=asyncio.run(agent.gap_node(state))
    assert update['direct_read_target']=={'url':external,'channel':'official'}
    result=asyncio.run(agent.read_node({**state,**update}))
    assert result['recent_read_source_ids']==[cached['id']]
