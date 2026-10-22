"""发现阶段单平台不能耗完全部预算；先给未试的独立公开目录机会。"""
import asyncio
import uuid
from app.industry_navigation import frontier_allowed,NAVIGATION_MARKER,subject_link,same_site


def test_platform_budget_groups_subdomains_and_does_not_block_selected_buyer():
    """子域/失败尝试计同平台，已选主体及没有其他未试平台时解除发现限额，不改变总预算。"""
    entries=[{'channel':'industry_directory','url':'https://www.b2b168.com/'},
        {'channel':'industry_directory','url':'https://www.jc001.cn/'}]
    history=[{'url':'https://www.b2b168.com/','attempts':2},{'url':'https://isolated.b2b168.com/','attempts':2}]
    assert not frontier_allowed('https://www.b2b168.com/dengshi/',history,entries,False)
    assert frontier_allowed('https://www.jc001.cn/',history,entries,False)
    assert frontier_allowed('https://www.b2b168.com/dengshi/',history,entries,True)
    assert frontier_allowed('https://www.b2b168.com/dengshi/',history+[{'url':'https://www.jc001.cn/','attempts':1}],entries,False)


def test_gap_and_read_really_select_untried_portal_after_four_platform_reads(client,monkeypatch):
    """真实图查询隔离合成账本，忽略仍有链接的旧平台，转向新注册目录；不冒充网络成功。"""
    from app import agent
    from app.db import Session,Conversation,Job,ToolCall,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':['industry_directory'],'max_reads':10,'max_leads':1})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离目录切换'))
    job=submit(conv,{'content':'找深圳灯具经销商','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:
        db.get(Job,job['id']).status='running'
        for index in range(4):
            url='https://www.b2b168.com/' if not index else 'https://www.b2b168.com/isolated/'+str(index)
            db.add(ToolCall(job_id=job['id'],operation_id=uuid.uuid4().hex,tool='fetch_source',channel='industry_directory',
                arguments={'url':url,'channel':'industry_directory'},status='completed',attempts=1,result={'sources':[]}))
    source=archive_sources(job['id'],[{'url':'https://www.b2b168.com/page-company.html','title':'隔离导航',
        'body':NAVIGATION_MARKER+'\n目录入口：深圳隔离灯具公司\n目录链接：https://www.b2b168.com/c168-987.html'}],'网页正文','industry_directory')[0]
    state={'job_id':job['id'],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'options':options,
        'saved_ids':[],'source_ids':[source['id']],'steps':[{'channel':'industry_directory','query':'隔离查询'}],'cursor':0,
        'reference_urls':[],'read_attempted_urls':[],'warnings':['provider_rate_limited'],'prompt':'找深圳灯具经销商'}
    update=asyncio.run(agent.gap_node(state))
    assert update['direct_read_pending']
    seen=[]
    async def execute(self,name,args):
        """name/args为实际图委托，只记录选页、返回无结果，不联网或捏造客户。"""
        seen.append(args);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    result=asyncio.run(agent.read_node({**state,**update}))
    assert seen==[{'url':'https://www.jc001.cn/','channel':'industry_directory'}]
    assert result['read_attempted_urls']==['https://www.jc001.cn/']
    # 有已存客户不应为所有无关链接解锁同平台配额。
    from app.db import Lead
    key=identifier()
    with Session.begin() as db:db.add(Lead(id=key,display_name='隔离已选灯饰门店',buyer_role='retailer',facts={},evidence=[]))
    state={**state,'saved_ids':[key]}
    update=asyncio.run(agent.gap_node(state))
    seen.clear()
    asyncio.run(agent.read_node({**state,**update}))
    assert seen==[{'url':'https://www.jc001.cn/','channel':'industry_directory'}]


def test_only_matching_visible_label_gets_subject_exemption():
    """标题含具体主体的真实原href可补查；正文提名/URL字符串/其他商户不授予豁免，文章不入企业前沿。"""
    link='https://isolated.b2b168.com/'
    body=NAVIGATION_MARKER+'\n目录入口：隔离已选灯饰门店\n目录链接：'+link
    assert subject_link(link,body,['隔离已选灯饰门店'])
    assert not subject_link(link,body,['另一个灯饰门店'])
    assert not subject_link(link,'隔离已选灯饰门店 '+link,['隔离已选灯饰门店'])
    assert not same_site('https://isolated.b2b168.com/s323383886.html','https://led.b2b168.com/')
    assert same_site('https://isolated.b2b168.com/','https://led.b2b168.com/')


def test_full_enrichment_rejects_unrelated_known_company_details_but_keeps_directory():
    """只验证已保存主体补查的选页，未知模板不猜实体；标签匹配及本商户介绍保留，不赋予事实身份。"""
    from app.industry_navigation import enrichment_allowed
    name='隔离已选灯饰门店'
    targets=['https://www.yunfale.com/company/detail/123/','https://shop.jc001.cn/9166/','https://isolated.b2b168.com/']
    source={'id':'s','url':'https://shop.jc001.cn/gc-006001-r1-265/','title':'目录','body':''}
    lead={'display_name':name,'evidence':[]}
    for link in targets:
        unrelated={**source,'body':NAVIGATION_MARKER+'\n目录入口：深圳另一家照明有限公司\n目录链接：'+link}
        assert not enrichment_allowed(link,unrelated,[lead])
        assert enrichment_allowed(link,unrelated,[])
        matching={**unrelated,'body':unrelated['body'].replace('深圳另一家照明有限公司',name)}
        assert enrichment_allowed(link,matching,[lead])
    assert enrichment_allowed('https://shop.jc001.cn/gc-006001-r1-265/',source,[lead])
    assert enrichment_allowed('https://unknown.example.org/company',source,[lead])
    owner={**source,'url':'https://shop.jc001.cn/9166/','title':name,'body':name+'经销灯具。'}
    own={**lead,'evidence':[{'field':'name','value':name,'source_id':'s','url':owner['url']}]}
    assert enrichment_allowed(owner['url']+'about/',owner,[own])
    assert not enrichment_allowed('https://shop.jc001.cn/9167/about/',owner,[own])


def test_full_gap_read_skip_unrelated_company_and_follow_actual_classification(client,monkeypatch):
    """client隔离库、monkeypatch记录真实图选页不联网；保存满额后既有目录中的别家公司不可继续消耗读取预算。"""
    from app import agent
    from app.db import Session,Job,Lead,identifier
    from app.gateway import archive_sources
    from app.service import save_settings
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':['industry_directory'],'max_reads':3,'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯饰门店','client_token':uuid.uuid4().hex}).json()['id']
    category='https://shop.jc001.cn/gc-006001007-r1-265/'
    body=NAVIGATION_MARKER+'\n目录入口：深圳另一照明有限公司\n目录链接：https://shop.jc001.cn/9167/\n目录入口：深圳灯具企业\n目录链接：'+category
    source=archive_sources(job,[{'url':'https://shop.jc001.cn/gc-006001-r1-265/','title':'深圳灯具企业','body':body}],'网页正文','industry_directory')[0]
    key=identifier()
    with Session.begin() as db:
        row=db.get(Job,job);row.status='running';row.lead_ids=[key]
        db.add(Lead(id=key,display_name='隔离已选灯饰门店',buyer_role='retailer',facts={},evidence=[]))
    state={'job_id':job,'profile':{'region':'深圳','products':[{'name':'壁灯'}]},'options':options,'saved_ids':[key],
        'source_ids':[source['id']],'steps':[{'channel':'industry_directory','query':'旧查询'}],'cursor':0,
        'reference_urls':[],'warnings':['provider_rate_limited'],'prompt':'找深圳灯饰门店'}
    update=asyncio.run(agent.gap_node(state))
    assert update['direct_read_target']['url']==category
    seen=[]
    async def execute(self,name,args):
        """name/args为图实际请求，仅记录URL并返回空来源，不声称外部读取成功。"""
        seen.append(args['url']);return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    asyncio.run(agent.read_node({**state,**update}))
    assert seen==[category]
