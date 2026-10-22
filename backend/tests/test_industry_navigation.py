"""行业目录导航只授予原href读取许可，不能成为买家事实。"""
import asyncio
import uuid
import pytest
from app.industry_navigation import navigation_text,navigation_links,factual_body,NAVIGATION_MARKER
from app.public_directory import directory_links

PROFILE={'region':'深圳','products':[{'name':'LED吊灯'}]}
URL='https://www.yunfale.com/'


def test_original_queries_visibility_and_exact_site():
    """原查询顺序/重复/空值保留；子域、端口、凭据、隐藏和脚本链接不能授予读取许可。"""
    content='''<meta charset="utf-8"><a href="/search?z=2&amp;a=1&amp;a=3&amp;blank=">深圳照明公司</a>
    <div hidden><a href="/hidden">深圳照明隐藏</a></div>
    <a href="/lighting"><span style="display:none">隐藏名字</span>照明企业</a>
    <template><a href="/template">深圳灯具公司</a></template>
    <a href="https://sub.yunfale.com/">深圳灯具子域</a>
    <a href="https://www.yunfale.com:9443/">深圳灯具端口</a>
    <a href="https://user@www.yunfale.com/x">深圳灯具凭据</a>
    <a href="javascript:go()">深圳照明脚本</a><a href="#part">深圳照明锚点</a>
    <a href="/login">深圳会员登录</a><a href="/lighting">重复灯具</a>'''
    body=navigation_text(content.encode(),URL,PROFILE)
    assert navigation_links(body,URL,PROFILE)==[URL+'search?z=2&a=1&a=3&blank=',URL+'lighting']
    assert '隐藏' not in body and '子域' not in body and '凭据' not in body
    assert directory_links(body,URL,PROFILE,'industry_directory')==navigation_links(body,URL,PROFILE)
    assert not directory_links(body,URL,PROFILE,'qcc_public')
    assert not navigation_text(content.encode(),'https://example.org/',PROFILE)
    assert not navigation_text('<a href="/member/home.php">深圳照明公司主页</a>'.encode(),URL,PROFILE)
    assert not navigation_links('目录入口：深圳灯具\n目录链接：'+URL+'x',URL,PROFILE)
    assert factual_body('实际公司正文\n\n'+body)=='实际公司正文'
    index=navigation_text('<a href="/company/">企业名录</a><a href="/company/detail/1/">深圳贸易公司</a>'.encode(),URL,PROFILE)
    assert navigation_links(index,URL,PROFILE)[0]==URL+'company/'
    assert len(navigation_links(index,URL,PROFILE))==1
    assert not navigation_text('<a href="/company/detail/2/">山东食品有限公司 企业资料可查看</a>'.encode(),URL,PROFILE)


def test_navigation_does_not_invent_paths_and_is_bounded():
    """最多40条DOM记录；候选/已读过滤不能让聚合窗口遮蔽后续真实链接，没有href的页码/脚本不制造。"""
    content='<script>page=99;company=1234</script><span>下一页</span>'
    assert not navigation_text(content.encode(),URL,PROFILE)
    content=''.join(f'<a href="/company/{index}?blank=">深圳灯具公司{index}</a>' for index in range(100))
    body=navigation_text(content.encode(),URL,PROFILE)
    assert body.count('目录链接：')==40 and len(navigation_links(body,URL,PROFILE))==40


def test_new_portal_actual_subdomain_links_do_not_open_other_sites_or_skip_store_home():
    """已核验平台可沿实际分类/商户子域；外域/伪后缀/端口/凭据拒绝，商户根页仍提取客户。"""
    from app.industry_navigation import is_index
    url='https://www.b2b168.com/'
    content='''<a href="https://dengju.b2b168.com/">灯具目录</a>
    <a href="http://isolated.b2b168.com/">深圳灯饰商行</a>
    <a href="https://b2b168.com.evil.example/x">深圳照明外域</a>
    <a href="https://www.jc001.cn/x">深圳灯具其他平台</a>
    <a href="https://dengju.b2b168.com:9443/">深圳灯具外端口</a>
    <a href="https://user@dengju.b2b168.com/">深圳灯具凭据</a>'''
    body=navigation_text(content.encode(),url,PROFILE)
    assert set(navigation_links(body,url,PROFILE))=={'https://dengju.b2b168.com/','http://isolated.b2b168.com/'}
    assert is_index(url) and is_index('https://www.jc001.cn/')
    assert not is_index('http://isolated.b2b168.com/')
    assert not is_index('https://www.jc001.cn/merchant/1')
    assert not navigation_text(content.encode(),'https://b2b168.com.evil.example/',PROFILE)


def test_jc_lookup_skips_advertising_mobile_goods_and_prefers_dealer_directory():
    """实际导航不把同城烤箱或新闻/招商/商品/移动副本当买家前沿；目录零模型，商户详情仍需提取。"""
    from app.industry_navigation import is_index
    url='https://www.jc001.cn/'
    content='''<a href="https://supply.jc001.cn/detail/1.html">深圳烤箱</a>
    <a href="http://shop.jc001.cn/st-1/">经销商</a>
    <a href="http://dengju.jc001.cn/shop/">灯具黄页</a>
    <a href="http://shop.jc001.cn/123/">深圳灯具公司</a>
    <a href="http://m.jc001.cn/ushop-123/">深圳灯具手机版</a>
    <a href="http://agent.jc001.cn/detail/2.html">灯具诚招经销商</a>
    <a href="https://news.jc001.cn/3.html">深圳灯具行业新闻</a>
    <a href="http://dengju.jc001.cn/goods/gc-00600103">商业照明商品</a>
    <a href="https://www.jc001.cn/ad_go.php?url=http%3A%2F%2Fexample.org">灯具经销商广告</a>'''
    links=navigation_links(navigation_text(content.encode(),url,PROFILE),url,PROFILE)
    assert set(links)=={'http://shop.jc001.cn/st-1/','http://dengju.jc001.cn/shop/','http://shop.jc001.cn/123/'}
    assert links[0]=='http://shop.jc001.cn/123/'
    assert is_index('http://dengju.jc001.cn/shop/')
    assert is_index('http://shop.jc001.cn/gc-006001-r1-265/')
    assert is_index('http://shop.jc001.cn/st-1/')
    assert not is_index('http://shop.jc001.cn/123/')
    # 旧成功正文缓存的导航仍需按新用途过滤，不能靠缓存把商品页重新放入买家前沿。
    old=NAVIGATION_MARKER+'\n目录入口：商业照明商品\n目录链接：http://dengju.jc001.cn/goods/gc-00600103'
    assert not navigation_links(old,url,PROFILE)


def test_b2b_lighting_frontier_does_not_follow_logistics_or_other_city_directories():
    """目标城市不能盖过产品条件；灯饰目录内可读原深圳公司href，不猜城市或编号。"""
    url='https://www.b2b168.com/'
    content='''<a href="https://isolated.b2b168.com/m980425p1/">深圳DHL国际快递</a>
    <a href="/page-company.html">企业黄页</a><a href="/beijing-dengshi/">北京灯饰黄页</a>
    <a href="/c168-123.html">深圳隔离光电有限公司</a><a href="/c168-124.html">深圳隔离照明有限公司</a>'''
    links=navigation_links(navigation_text(content.encode(),url,PROFILE),url,PROFILE)
    assert url+'page-company.html' in links and url+'c168-124.html' in links
    assert not any('m980425' in link or 'beijing-' in link or 'c168-123' in link for link in links)
    lighting=url+'dengshi/'
    body=navigation_text('<a href="/c168-123.html">深圳隔离光电有限公司</a>'.encode(),lighting,PROFILE)
    assert navigation_links(body,lighting,PROFILE)==[url+'c168-123.html']
    subdomain='https://dengshi.b2b168.com/'
    body=navigation_text('<a href="https://www.b2b168.com/c168-123.html">深圳隔离光电有限公司</a>'.encode(),subdomain,PROFILE)
    assert navigation_links(body,subdomain,PROFILE)==[url+'c168-123.html']


def test_local_category_heading_prioritizes_correct_shenzhen_link_without_creating_fact():
    """多个裸城市href只按紧邻原分类标题排序；不从编号猜灯具，不让隐藏或多个标题授予分类。"""
    url='https://shop.jc001.cn/'
    content='''<main><div><h3>卫浴</h3><a href="/gc-1-r1-265/">深圳</a></div>
    <div><h3>灯具</h3><a href="/gc-2-r1-265/">深圳</a></div>
    <div><h3><span hidden>灯饰</span>家具</h3><a href="/gc-3-r1-265/">深圳</a></div>
    <div><h3>灯具</h3><h3>卫浴</h3><a href="/gc-4-r1-265/">深圳</a></div></main>'''
    body=navigation_text(content.encode(),url,PROFILE)
    assert navigation_links(body,url,PROFILE)[0]==url+'gc-2-r1-265/'
    assert '目录链接：https://shop.jc001.cn/gc-2-r1-265/\n目录分类：灯具' in body
    assert 'gc-3-r1-265/\n目录分类：' not in body
    assert 'gc-4-r1-265/\n目录分类：' not in body
    assert not factual_body(body)
    from app.industry_navigation import navigation_priority
    assert navigation_priority('深圳隔离光电公司','',PROFILE)>navigation_priority('气体放电灯','灯具',PROFILE)


def test_broker_gap_and_read_follow_only_archived_navigation(client,monkeypatch):
    """真实Broker/图从本任务导航读实际链接；未知路径拒绝，已尝试和预算耗尽终止。"""
    from app import agent
    from app import source_catalog
    from app.db import Session,Conversation,Job,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings,ServiceError
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':['industry_directory'],'max_reads':2})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离行业导航'))
    job=submit(conversation,{'content':'查找深圳灯具经销商','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    detail=URL+'lighting?z=2&a=1&blank='
    body='目录首页实际文字。'*20+'\n\n'+NAVIGATION_MARKER+'\n目录入口：深圳灯具公司\n目录链接：'+detail
    source=archive_sources(job['id'],[{'url':URL,'title':'隔离目录','body':body}],'网页正文','industry_directory')[0]
    archive_sources(job['id'],[{'url':detail,'title':'隔离详情','body':'隔离缓存资料正文。'*40}],'网页正文','industry_directory')
    broker=ToolBroker(job['id'],options,PROFILE);broker.allowed_sources={source['id']}
    assert asyncio.run(broker.fetch({'url':detail,'channel':'industry_directory'}))['cached']
    with pytest.raises(ServiceError,match='url_not_discovered'):
        asyncio.run(broker.fetch({'url':URL+'invented','channel':'industry_directory'}))
    state={'job_id':job['id'],'profile':PROFILE,'options':options,'cursor':0,'steps':[{'channel':'industry_directory'}],
        'saved_ids':[],'source_ids':[source['id']],'recent_read_source_ids':[source['id']],
        'read_attempted_urls':[URL],'reference_urls':[],'warnings':['provider_rate_limited'],'prompt':'查找深圳灯具经销商'}
    # 此用例只检验单一已归档导航的耗尽；新增平台注册入口由public_entries单独验证。
    monkeypatch.setattr(source_catalog,'public_entries',lambda *args:[])
    update=asyncio.run(agent.gap_node(state));assert update['direct_read_pending']
    async def forbidden_model(*args,**kwargs):
        """主页入口不得花模型生成客户；调用即失败。"""
        raise AssertionError('目录首页不能产客户')
    monkeypatch.setattr(agent,'cached_model',forbidden_model)
    extracted=asyncio.run(agent.extract_node(state))
    assert not extracted['candidates']
    seen=[]
    async def execute(self,name,args):
        """name/args为图调用；仅记录选页不伪造网络成功，返回空来源。"""
        seen.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    read=asyncio.run(agent.read_node({**state,**update}))
    assert seen==[{'url':detail,'channel':'industry_directory'}]
    assert detail in read['read_attempted_urls']
    ended=asyncio.run(agent.gap_node({**state,**update,**read}))
    assert not ended.get('direct_read_pending')
    ended=asyncio.run(agent.gap_node({**state,'options':{**options,'max_reads':0}}))
    assert not ended.get('direct_read_pending')


def test_new_index_is_not_reextracted_with_old_unselected_company_page(client,monkeypatch):
    """尚无已存客户的自主发现也只看新正文；旧公司页不能迫使新入口再次模型提取。"""
    from app import agent
    from app.gateway import archive_sources
    job=uuid.uuid4().hex
    old=archive_sources(job,[{'url':'https://example.org/'+uuid.uuid4().hex,'title':'隔离旧公司',
        'body':'隔离旧公司旧页。'*30}],'网页正文','industry_directory')[0]
    latest=archive_sources(job,[{'url':'https://www.jc001.cn/','title':'九正建材网',
        'body':'本轮实际入口文字。'*30}],'网页正文','industry_directory')[0]
    async def forbidden(*args,**kwargs):
        """纯入口不得因旧正文调用模型。"""
        raise AssertionError('旧正文不能令新入口反复提取')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    result=asyncio.run(agent.extract_node({'job_id':job,'profile':PROFILE,'options':{'max_leads':1},
        'source_ids':[old['id'],latest['id']],'recent_read_source_ids':[latest['id']],
        'saved_ids':[],'prompt':'自主找深圳灯具经销商','cursor':0,'plan':{'target_roles':['dealer']}}))
    assert result['candidates']==[]
