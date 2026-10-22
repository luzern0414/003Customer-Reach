"""检索限额不能阻止已给定公开链接的余下读取；关闭渠道和读取预算仍有效。"""
import asyncio
import uuid


def test_gap_reads_remaining_reference_after_search_limit(client,monkeypatch):
    """隔离真实gap/read与账本；网络替身仅记录未读链接，不能作为真实获客验收。"""
    from app.agent import gap_node,read_node
    from app.db import Session,ToolCall,Job,Conversation,identifier
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':['official'],'max_reads':3,'max_leads':3})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离多链接读取'))
    job=submit(conversation,{'content':'找深圳灯具零售商','attachment_ids':[],'client_token':uuid.uuid4().hex})
    refs=[{'url':f'https://example.org/{index}','channel':'official'} for index in range(3)]
    with Session.begin() as db:
        db.get(Job,job['id']).status='running'
        for item in refs[:2]:db.add(ToolCall(job_id=job['id'],operation_id=uuid.uuid4().hex,tool='fetch_source',
            channel='official',status='completed',attempts=1,arguments=item,result={'sources':[]}))
    state={'job_id':job['id'],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'options':options,
        'steps':[{'channel':'official','query':'深圳灯具门店'}],'cursor':0,'saved_ids':[],'source_ids':[],
        'reference_urls':refs,'warnings':['provider_rate_limited'],'plan':{'target_roles':['retailer']}}
    update=asyncio.run(gap_node(state))
    assert update['direct_read_pending'] and update['cursor']==0
    seen=[]
    async def fetch(self,args):
        """self为实际Broker、args为本轮选择链接；模拟预检查失败无账本，验证仍不会重复空转。"""
        seen.append(args);return {'sources':[],'error':'site_access_restricted'}
    monkeypatch.setattr(ToolBroker,'execute',lambda self,name,args:fetch(self,args))
    read=asyncio.run(read_node({**state,**update}))
    assert seen==[refs[2]]
    assert refs[2]['url'] in read['read_attempted_urls']
    final=asyncio.run(gap_node({**state,**update,**read}))
    assert not final['direct_read_pending'] and final['cursor']==1
    budget=asyncio.run(gap_node({**state,'options':{**options,'max_reads':2}}))
    assert not budget['direct_read_pending']
    disabled=asyncio.run(gap_node({**state,'reference_urls':[{**refs[2],'channel':'qcc_public'}]}))
    assert not disabled['direct_read_pending']


def test_explicit_list_keeps_later_customer_after_multiple_urls():
    """多URL名单第三项仍属于请求，但下一句明确排除主体不能由名单作用域纳入。"""
    from app.evidence_context import target_names,evidence_context
    names=['深圳验证甲商行','深圳验证乙商行','深圳验证丙商行']
    prompt='请核验以下三个经销主体：'+ '；'.join(name+' https://example.org/'+('x'*100)+str(index) for index,name in enumerate(names))+'。不要找深圳排除商行。'
    rows=[{'id':str(index),'url':f'https://example.org/{index}','title':name,'body':name+'。经销批发灯具。','kind':'搜索摘录'} for index,name in enumerate([*names,'深圳排除商行'])]
    assert set(target_names(prompt,rows,'深圳'))==set(names)
    # 最近HTTP补读必须可独立进入上下文，不因旧已选主体过滤掉新页面。
    contexts=evidence_context(rows[:3],names[:2],'深圳',['0','1','2'],['2'])
    assert any(row['id']=='2' for row in contexts)


def test_failed_direct_read_does_not_reextract_old_evidence(client,monkeypatch):
    """实际read→extract失败补读链保留旧证据，不回退旧摘要重发模型；恢复由独立recover契约允许。"""
    from app import agent
    from app.db import Session,Conversation,Job,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings
    from app.research_tools import ToolBroker
    options=save_settings({'enabled_channels':['official'],'max_reads':3,'max_leads':1})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离失败补读'))
    job=submit(conv,{'content':'找深圳灯具门店','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    old=archive_sources(job['id'],[{'url':'https://example.org/old','title':'隔离旧资料',
        'body':'旧资料只用于验证失败补读不得重新调用模型。'*20}],'网页正文','official')[0]
    state={'job_id':job['id'],'profile':{'region':'深圳','products':[{'name':'壁灯'}]},'options':options,
        'source_ids':[old['id']],'saved_ids':[],'attempts':[], 'prompt':'找深圳灯具门店',
        'steps':[{'channel':'official','query':'隔离查询'}],'cursor':0,'direct_read_pending':True,
        'reference_urls':[{'url':'https://example.org/new','channel':'official'}]}
    async def fail(self,name,args):return {'error':'site_access_restricted','sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',fail)
    def forbidden():raise AssertionError('不应对旧页再次调用模型')
    monkeypatch.setattr(agent,'model',forbidden)
    update=asyncio.run(agent.read_node(state))
    assert update['source_ids']==[old['id']] and update['recent_read_source_ids']==[]
    assert asyncio.run(agent.extract_node({**state,**update}))['candidates']==[]


def test_single_subject_mall_pronoun_keeps_role_ownership():
    """单主体标题+同源完整name可回指本商场；别的主体、目录标题或无name证据仍拒绝。"""
    from app.evidence_role import scoped_role
    name='深圳隔离灯饰店'
    quote='本商场现销售经营面积较大，并是甲牌、乙牌等品牌在深圳的一级经销商。'
    assert scoped_role(name,'一级经销商',quote,name,True)
    assert not scoped_role(name,'一级经销商',quote,'商户名录',True)
    assert not scoped_role(name,'一级经销商',quote,name,False)
    assert not scoped_role(name,'一级经销商','其他深圳公司有限公司是一级经销商，本商场仅展示。',name,True)
    intro=name+'位置在深圳某市场，主营灯具，本店经销批发灯具。'
    assert scoped_role(name,'经销批发',intro,name,True)
    assert not scoped_role(name,'经销批发',intro,'行业企业目录',True)
    assert not scoped_role(name,'经销批发',name+'位于深圳，隔离其他主体有限公司经销批发灯具。',name,True)


def test_same_subject_address_fragments_do_not_create_duplicate(client):
    """明确单主体页重复地址片段合并主体但保留争议；跨分店目录仍不当同一店。"""
    from app.schemas import Candidate
    from app.service import save_candidate,lead_detail
    from app.evidence_role import same_subject_page
    name='深圳隔离地址验证商行'
    source={'s':{'id':'s','url':'https://example.org/subject','title':name,'body':name+'，地址：深圳某路市场一楼。',
        'captured_at':'2026-10-03 00:00:00','kind':'测试','channel':'official'}}
    def make(address):
        """address为原文地址片段；不补字段，创建隔离候选用于真实保存测试。"""
        return Candidate(display_name=name,city='深圳',facts=[{'field':'name','value':name,'quote':name,'source_id':'s'},
            {'field':'address','value':address,'quote':'地址：深圳某路市场一楼','source_id':'s'}],matched_products=[],match_reason='隔离验证')
    first=save_candidate(make('深圳某路市场一楼'),source,'isolated')
    second=save_candidate(make('深圳某路市场'),source,'isolated')
    assert second['id']==first['id'] and lead_detail(second['id'])['facts']['address']['verification']=='disputed'
    evidence=[{'field':'name','value':name,'source_id':'s','url':source['s']['url']}]
    assert not same_subject_page(name,evidence,{'s':{**source['s'],'title':name+'门店列表'}})
    assert not same_subject_page(name,evidence,{'new':{**source['s'],'url':'https://example.org/other'}})


def test_new_explicit_subject_does_not_regenerate_saved_subjects(client,monkeypatch):
    """真实extract上下文聚焦新补读主体，模型替身只记录提示，不冒充网络模型成功。"""
    import json
    from app import agent
    from app.db import Session,Lead,identifier
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    names=['深圳隔离聚焦甲商行','深圳隔离聚焦乙商行','深圳隔离聚焦丙商行']
    saved=[]
    with Session.begin() as db:
        for name in names[:2]:
            key=identifier();saved.append(key)
            db.add(Lead(id=key,display_name=name,city='深圳',dedupe_key=uuid.uuid4().hex))
    job=uuid.uuid4().hex
    sources=archive_sources(job,[{'url':f'https://example.org/{job}/{index}','title':name,
        'body':name+'位置在深圳，经销批发灯具。'+('隔离验证资料。'*30)} for index,name in enumerate(names)],'网页正文','official')
    prompts=[]
    async def model(state,schema,prompt,label):
        """记录真实上下文裁剪结果；不生成虚构候选，不计作真实模型验收。"""
        prompts.append(prompt);return CandidateBatch(candidates=[],missing_fields=[])
    monkeypatch.setattr(agent,'cached_model',model)
    asyncio.run(agent.extract_node({'job_id':job,'saved_ids':saved,'source_ids':[row['id'] for row in sources],
        'recent_read_source_ids':[sources[2]['id']],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'prompt':'请核验以下三家：'+'；'.join(names)+'。','options':{'max_leads':3,'enabled_channels':['official']},
        'cursor':0,'plan':{'target_roles':['dealer']}}))
    context=json.loads(prompts[0].split('\n来源：',1)[1].split('\n明确指定主体：',1)[0])
    assert len(context)==1 and context[0]['url']==sources[2]['url']


def test_graph_api_keeps_conditional_loop_edges(client):
    """编排接口必须展示实际回路，不能只因lambda无返回注解漏掉gap/read。"""
    response=client.get('/api/agent/graph');assert response.status_code==200
    edges={(item['source'],item['target']) for item in response.json()['edges']}
    assert {('gap','read'),('gap','decide'),('gap','answer'),('context','profile'),('context','answer')}<=edges


def test_autonomous_discovery_keeps_new_customer_after_saved_one(client,monkeypatch):
    """已存主体不是用户指定名单；下一来源的新主体仍进入真实提取协议。"""
    import json
    from app import agent
    from app.db import Session,Lead,identifier
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch,Candidate
    old='深圳隔离已存灯饰商行';new='深圳隔离新发现灯饰商行'
    key=identifier();job=uuid.uuid4().hex
    with Session.begin() as db:db.add(Lead(id=key,display_name=old,city='深圳',dedupe_key=uuid.uuid4().hex))
    source=archive_sources(job,[{'url':'https://example.org/'+job,'title':new,
        'body':new+'位于深圳，经营灯具经销批发。'+('隔离测试资料。'*30)}],'网页正文','official')[0]
    previous=archive_sources(job,[{'url':'https://example.org/previous/'+job,'title':old,
        'body':old+'位于深圳，经营灯具经销批发。'+('隔离旧资料。'*30)}],'网页正文','official')[0]
    prompts=[]
    async def model(state,schema,prompt,label):
        """只模拟结构化输出，核验新主体不被过滤；不计真实模型或网络验收。"""
        prompts.append(prompt)
        return CandidateBatch(candidates=[Candidate(display_name=new,city='深圳',buyer_role='dealer',
            facts=[{'field':'name','value':new,'quote':new,'source_id':'S1'}],match_reason='隔离协议验证')],missing_fields=[])
    monkeypatch.setattr(agent,'cached_model',model)
    result=asyncio.run(agent.extract_node({'job_id':job,'saved_ids':[key],'source_ids':[previous['id'],source['id']],
        'recent_read_source_ids':[source['id']],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'prompt':'自主找深圳灯具经销商','options':{'max_leads':2,'enabled_channels':['official']},
        'cursor':1,'plan':{'target_roles':['dealer']}}))
    assert result['candidates'][0]['display_name']==new
    assert '\n明确指定主体：' not in prompts[0]
    context=json.loads(prompts[0].split('\n来源：',1)[1])
    assert len(context)==1 and context[0]['url']==source['url']


def test_full_target_skips_unrelated_new_page_without_reextracting_old_facts(client,monkeypatch):
    """满额补查只有完整目标名关联才分析；无关新页不能反复重生成旧事实。"""
    from app import agent
    from app.db import Session,Lead,identifier
    from app.gateway import archive_sources
    key=identifier();job=uuid.uuid4().hex;name='深圳隔离目标经销商'
    with Session.begin() as db:db.add(Lead(id=key,display_name=name,city='深圳',dedupe_key=uuid.uuid4().hex))
    old=archive_sources(job,[{'url':'https://example.org/old/'+job,'title':name,'body':name+'位于深圳，经销灯具。'+('隔离旧资料。'*40)}],'网页正文','official')[0]
    fresh=archive_sources(job,[{'url':'https://example.org/new/'+job,'title':'隔离其他品牌目录','body':'隔离其他品牌目录。'*50}],'网页正文','brand_directory')[0]
    async def model(*args,**kwargs):
        """无完整主体的新页应零模型调用；调用即测试失败。"""
        raise AssertionError('不应重新分析无关页面或旧事实')
    monkeypatch.setattr(agent,'cached_model',model)
    result=asyncio.run(agent.extract_node({'job_id':job,'saved_ids':[key],
        'source_ids':[old['id'],fresh['id']],'recent_read_source_ids':[fresh['id']],
        'profile':{'region':'深圳','products':[{'name':'灯具'}]},'prompt':'自主找深圳灯具经销商',
        'options':{'max_leads':1,'enabled_channels':['official','brand_directory']},'cursor':2,
        'plan':{'target_roles':['dealer']}}))
    assert result=={'candidates':[]}
