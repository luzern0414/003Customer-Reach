"""真实目录href和已读完整主体页可以绑定联系导航，不能授予跨商户或派生事实。"""
import asyncio
import uuid
import pytest
from app.industry_navigation import navigation_text,navigation_owner,enrichment_allowed
from app.public_website import website_links


PROFILE={'region':'深圳','products':[{'name':'壁灯'}]}


def chain():
    """无参数；返回纯隔离目录、首页和介绍页及仅引用目录name的客户，不发请求或推断别名。"""
    # 每次独立主体及商户路径，避免共享隔离DB的同名记录/同秒缓存遮蔽本用例。
    name='深圳'+uuid.uuid4().hex[:6]+'隔离照明有限公司';root='https://shop.jc001.cn/410001'+str(int(uuid.uuid4().hex[:8],16))+'/'
    urls=['https://shop.jc001.cn/gc-006001-r1-265/',root,root+'about/']
    bodies=[name+'是一家照明灯具批发企业。'*20+'\n'+navigation_text(
        ('<a href="'+root+'">'+name+'</a>').encode(),urls[0],PROFILE),
        name+'公司业务介绍。'*20+'\n'+navigation_text((
            '<a href="'+root+'about/">公司介绍</a><a href="'+root+'contact.html">联系方式</a>'+
            '<a href="https://shop.jc001.cn/410002/contact.html">联系方式</a>'+
            '<a href="https://shop.jc001.cn/contact.html">联系方式</a>').encode(),root,PROFILE),
        name+'公司业务介绍。'*20+'\n'+navigation_text(('<a href="'+root+'contact.html">联系方式</a>').encode(),urls[2],PROFILE)]
    pages=[{'id':str(index),'url':url,'kind':'网页正文','channel':'industry_directory',
        'title':'深圳灯具企业库' if index==0 else '隔离照明有限公司 '+name,'body':body} for index,(url,body) in enumerate(zip(urls,bodies))]
    lead={'display_name':name,'facts':{},'evidence':[{'field':'name','value':name,'source_id':'0','url':urls[0]}]}
    return lead,pages,root+'contact.html'


def test_real_name_href_chain_binds_home_and_about_without_writing_name_evidence():
    """无参数；原name仍绑定目录，首页和about沿真实链可读联系页，其他商户/平台不借用。"""
    lead,pages,contact=chain()
    assert navigation_owner(lead,pages[1],pages) and navigation_owner(lead,pages[2],pages)
    assert website_links(pages,[lead],['industry_directory'])==[{'url':contact,'channel':'industry_directory'}]
    assert enrichment_allowed(contact,pages[2],[lead],pages)
    assert not enrichment_allowed('https://shop.jc001.cn/410002/contact.html',pages[2],[lead],pages)
    assert lead['evidence'][0]['source_id']=='0' and len(lead['evidence'])==1


@pytest.mark.parametrize('case',['missing_parent','short_label','another_title','no_body_name','disputed','different_namespace','loop'])
def test_missing_or_ambiguous_navigation_chain_does_not_grant_owner(case):
    """case为无来源链/简称/其他主体/无正文名/争议/跨商户/循环；均不能仅凭完整标题或URL授导航。"""
    lead,pages,contact=chain()
    if case=='missing_parent':pages=pages[1:]
    elif case=='short_label':pages[0]['body']=pages[0]['body'].replace('目录入口：'+lead['display_name'],'目录入口：隔离照明')
    elif case=='another_title':pages[1]['title']+=' 其他主体有限公司'
    elif case=='no_body_name':pages[1]['body']=pages[1]['body'].replace(lead['display_name'],'未知公司')
    elif case=='disputed':lead['facts']={'name':{'verification':'disputed'}}
    elif case=='different_namespace':pages[2]['url']='https://shop.jc001.cn/410002/about/'
    elif case=='loop':
        pages[1]['body']=lead['display_name']+'\n'+navigation_text(('<a href="'+pages[2]['url']+'">公司介绍</a>').encode(),pages[1]['url'],PROFILE)
        pages[2]['body']=lead['display_name']+'\n'+navigation_text(('<a href="'+pages[1]['url']+'">关于我们</a>').encode(),pages[2]['url'],PROFILE)
        pages=pages[1:]
    target=pages[-1]
    assert not navigation_owner(lead,target,pages)
    if case!='different_namespace':assert not website_links(pages,[lead],['industry_directory'])


def test_graph_and_broker_read_real_contact_before_about_with_original_directory_name(client,monkeypatch):
    """client为隔离API、monkeypatch禁公网/robots请求；真实gap/read/Broker取原联系页且保留预算与name证据。"""
    from app import agent,research_tools,source_policy
    from app.db import Session,Job,Lead,identifier
    from app.gateway import archive_sources
    from app.service import save_settings
    lead,pages,contact=chain()
    options=save_settings({'enabled_channels':['industry_directory'],'max_reads':1,'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'查找深圳灯具经销商','client_token':uuid.uuid4().hex}).json()['id']
    rows=archive_sources(job,pages,'网页正文','industry_directory')
    evidence=[{**lead['evidence'][0],'source_id':rows[0]['id']}]
    key=identifier()
    with Session.begin() as db:
        row=db.get(Job,job);row.status='running';row.lead_ids=[key]
        db.add(Lead(id=key,display_name=lead['display_name'],city='深圳',buyer_role='dealer',evidence=evidence))
    cached=archive_sources(uuid.uuid4().hex,[{'url':contact,'title':lead['display_name'],
        'body':lead['display_name']+'实际联系正文。'*30}],'网页正文','industry_directory')[0]
    checked=[]
    async def policy(url):
        """url为实际被选联系页；仅记录robots检查位置，真实网络禁止，不声称站点允许。"""
        checked.append(url);return 1
    monkeypatch.setattr(source_policy,'reading_delay',policy)
    monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    state={'job_id':job,'profile':PROFILE,'options':options,'source_ids':[row['id'] for row in rows],
        'saved_ids':[key],'attempts':[],'prompt':'补查已保存客户的公开联系方式',
        'steps':[{'channel':'industry_directory','query':'旧查询'}],'cursor':0,'warnings':[],'reference_urls':[]}
    update=asyncio.run(agent.gap_node(state))
    assert update['direct_read_target']=={'url':contact,'channel':'industry_directory'}
    result=asyncio.run(agent.read_node({**state,**update}))
    assert result['recent_read_source_ids']==[cached['id']] and checked==[contact]
    with Session() as db:assert db.get(Lead,key).evidence==evidence


@pytest.mark.parametrize('completed',[True,False])
def test_named_followup_loads_only_proven_completed_bridge_from_origin_conversation(client,completed):
    """client隔离API、completed为原首页实际读取账本状态；只有同原会话成功读取链可桥接，不加载其他会话或失败缓存。"""
    from app import agent
    from app.db import Session,Job,Lead,ToolCall,identifier
    from app.gateway import archive_sources
    from app.service import save_settings
    lead,pages,contact=chain()
    options=save_settings({'enabled_channels':['industry_directory'],'max_reads':2,'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    old=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具经销商','client_token':uuid.uuid4().hex}).json()['id']
    rows=archive_sources(old,pages,'网页正文','industry_directory')
    key=identifier();evidence=[{**lead['evidence'][0],'source_id':rows[0]['id']}]
    with Session.begin() as db:
        job=db.get(Job,old);job.status='partial';job.lead_ids=[key]
        db.add(Lead(id=key,display_name=lead['display_name'],city='深圳',buyer_role='dealer',evidence=evidence))
        db.add(ToolCall(job_id=old,operation_id=uuid.uuid4().hex,tool='fetch_source',channel='industry_directory',
            status='completed' if completed else 'failed',arguments={'url':rows[1]['url']},result={'sources':[rows[1]]}))
    other_conv=client.post('/api/conversations').json()['id']
    other=client.post('/api/conversations/'+other_conv+'/messages',json={'content':'其他会话隔离测试','client_token':uuid.uuid4().hex}).json()['id']
    foreign=archive_sources(other,[pages[1]],'网页正文','industry_directory')[0]
    with Session.begin() as db:
        db.add(ToolCall(job_id=other,operation_id=uuid.uuid4().hex,tool='fetch_source',status='completed',arguments={'url':foreign['url']},result={'sources':[foreign]}))
    prompt='补查已保存客户'+lead['display_name']+'的公开联系方式'
    current=client.post('/api/conversations/'+conv+'/messages',json={'content':prompt,'client_token':uuid.uuid4().hex}).json()['id']
    state={'job_id':current,'conversation_id':conv,'intent':'research','prompt':prompt,'options':options}
    loaded=asyncio.run(agent.load_context(state))
    assert rows[0]['id'] in loaded['source_ids'] and foreign['id'] not in loaded['source_ids']
    assert (rows[1]['id'] in loaded['source_ids'])==completed
    if completed:
        plan=asyncio.run(agent.plan_node({**state,**loaded,'profile':PROFILE}))
        assert plan['direct_read_pending']
    with Session() as db:assert db.get(Lead,key).evidence==evidence
