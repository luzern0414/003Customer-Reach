"""持久账本驱动的早期目录和公平补查；仅合成数据库，不访问网络。"""
import asyncio
import uuid


def state(client):
    """client为隔离API；返回零客户研究状态，登记渠道和未来计划明确，无网络副作用。"""
    from app.service import save_settings
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具客户','client_token':uuid.uuid4().hex}).json()['id']
    return {'job_id':job,'cursor':1,'steps':[
        {'channel':'b2b_1688','query':'原1688查询'}, {'channel':'qcc_public','query':'原企查查查询'},
        {'channel':'industry_directory','query':'原行业查询'}, {'channel':'official','query':'原官网查询'}],
        'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'prompt':'先查1688和企查查，再寻找深圳灯具买家',
        'options':save_settings({'enabled_channels':['b2b_1688','qcc_public','industry_directory','mall_directory','official'],'max_leads':2,'max_reads':8,'max_searches':8}),
        'saved_ids':[],'source_ids':[],'attempts':[],'warnings':[],'plan':{'target_roles':['dealer','retailer']},'reference_urls':[]}


def record(job,channel,query,attempts=1):
    """job为隔离任务，channel/query为合成真实执行记录，attempts为累计重试次数；不调用搜索。"""
    from app.db import Session,ToolCall
    with Session.begin() as db:db.add(ToolCall(job_id=job,operation_id=uuid.uuid4().hex,tool='search_accounts',channel=channel,
        arguments={'channel':channel,'query':query},status='completed',attempts=attempts,result={'sources':[]}))


def test_late_discovery_reserves_original_searches_for_new_accounts(client):
    """client隔离库；已有联系但未满额时不重复旧主体，余搜索将尽先实际登记目录，不增attempts/预算。"""
    from app.agent import gap_node
    from app.db import Session,Lead,ToolCall,identifier
    current=state(client);name='深圳隔离预算商行';key=identifier()
    with Session.begin() as db:db.add(Lead(id=key,display_name=name,city='深圳',facts={'phone':{'value':'13500001111'}},evidence=[{'field':'name','value':name,'url':'https://example.org/'}],dedupe_key=uuid.uuid4().hex))
    current={**current,'saved_ids':[key],'prompt':'先查1688和企查查，找深圳2家灯具客户，每家至少两个网站','cursor':0,
        'steps':[{'channel':'official','query':'旧轮'}, {'channel':'industry_directory','query':'保留发现查询'}]}
    record(current['job_id'],'b2b_1688','原1688查询')
    record(current['job_id'],'qcc_public','原企查查查询')
    record(current['job_id'],'official',name)
    repeat=asyncio.run(gap_node(current))
    assert not repeat['enrichment_name'] and repeat['steps'][1]['query']=='保留发现查询'
    reserved=asyncio.run(gap_node({**current,'options':{**current['options'],'max_searches':4}}))
    assert reserved['direct_read_pending'] and reserved['remaining_budget']['searches']==1
    assert reserved['direct_read_target']['channel']=='mall_directory'
    assert reserved['steps'][-1]['query']=='保留发现查询'
    with Session() as db:assert db.query(ToolCall).filter(ToolCall.job_id==current['job_id'],ToolCall.tool=='search_accounts').count()==3


def test_early_directory_keeps_requested_prefix_future_plan_and_attempted_urls(client,monkeypatch):
    """client隔离库、monkeypatch只断网；真实平台账本完成前不早切，直读后恢复原未执行计划。"""
    from app.agent import gap_node,read_node
    from app.research_tools import ToolBroker
    original=state(client)
    record(original['job_id'],'b2b_1688','原1688查询')
    first=asyncio.run(gap_node(original));assert not first['direct_read_pending']
    record(original['job_id'],'qcc_public','原企查查查询')
    early=asyncio.run(gap_node(original))
    assert early['direct_read_pending'] and early['early_directory_after']==2
    assert early['cursor']==2 and early['steps'][3:]==original['steps'][2:]
    target=early['direct_read_target'];seen=[]
    async def execute(self,name,args):
        """只观察目标调度并返回空来源；不冒充HTTP成功。"""
        seen.append((name,args));return {'sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',execute)
    current={**original,**early,'reference_urls':[{'url':'https://example.org/other','channel':'official'}]}
    result=asyncio.run(read_node(current))
    assert seen==[('fetch_source',target)] and not result['direct_read_target']
    assert target['url'] in result['read_attempted_urls']
    resumed=asyncio.run(gap_node({**original,**early,**result}))
    assert not resumed['direct_read_pending'] and resumed['steps'][resumed['cursor']]['query']=='原行业查询'
    record(original['job_id'],'industry_directory','原行业查询')
    next_early=asyncio.run(gap_node({**original,**early,**result,'cursor':3}))
    assert next_early['direct_read_target']['url']!=target['url']
    assert next_early['steps'][-1]['query']=='原官网查询'


def test_enrichment_uses_least_real_attempts_and_stops_when_all_accounts_exhausted(client):
    """client隔离库；内存假次数无效，新增步骤也选最少实际次数主体，恢复重试计额度且满额不盲搜。"""
    from app.agent import gap_node
    from app.db import Session,Lead,identifier
    current=state(client);keys=[];names=['深圳隔离甲灯饰商行','深圳隔离乙灯饰商行']
    with Session.begin() as db:
        for index,name in enumerate(names):
            key=identifier();keys.append(key)
            facts={'address':{'value':'深圳隔离路','verification':'原文匹配'},'categories':{'value':'灯具','verification':'原文匹配'}}
            if index:facts['phone']={'value':'13428788412','verification':'原文匹配'}
            db.add(Lead(id=key,display_name=name,city='深圳',facts=facts,evidence=[{'field':'name','url':'https://example.org/'+str(index)}],dedupe_key=uuid.uuid4().hex))
    current={**current,'saved_ids':keys,'prompt':'补全深圳两家客户，至少两个网站',
        'steps':[{'channel':'official','query':'上一轮'}, {'channel':'industry_directory','query':'下一轮'}],'cursor':0,
        'attempts':[{'channel':'official','query':names[1]}]*10,'options':{**current['options'],'enabled_channels':['official','industry_directory'],'max_reads':0}}
    record(current['job_id'],'official',names[0],attempts=2)
    next_step=asyncio.run(gap_node(current))
    assert names[1] in next_step['steps'][1]['query'] and names[0] not in next_step['steps'][1]['query']
    # 原计划用尽，新增搜索仍沿同一公平选择，不退回第一主体。
    appended=asyncio.run(gap_node({**current,'steps':[current['steps'][0]]}))
    assert names[1] in appended['steps'][appended['cursor']]['query']
    record(current['job_id'],'official',names[1],attempts=3)
    chosen=asyncio.run(gap_node(current));assert names[0] in chosen['steps'][1]['query']
    record(current['job_id'],'official',names[0])
    stopped=asyncio.run(gap_node(current))
    assert stopped['cursor']==len(stopped['steps']) and not stopped['direct_read_pending']


def test_partial_batch_alternates_cross_site_enrichment_and_open_discovery(client,monkeypatch):
    """client隔离库、monkeypatch记录提示；未满额也跨站补查，下一轮仍可发现新主体且旧身份页不泛滥。"""
    import json
    from app import agent
    from app.db import Session,Lead,identifier
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    current=state(client);names=['深圳隔离跨站甲商行','深圳隔离跨站乙商行'];keys=[]
    sources=archive_sources(current['job_id'],[{'url':'https://example.org/old/'+uuid.uuid4().hex,
        'title':name,'body':name+'位于深圳，经销灯具。'+('隔离旧资料。'*30)} for name in names],'网页正文','official')
    with Session.begin() as db:
        for name,row in zip(names,sources):
            key=identifier();keys.append(key)
            db.add(Lead(id=key,display_name=name,city='深圳',dedupe_key=uuid.uuid4().hex,
                facts={'phone':{'value':'13428788412','verification':'原文匹配'},'address':{'value':'深圳隔离路','verification':'原文匹配'},'categories':{'value':'灯具','verification':'原文匹配'}},
                evidence=[{'field':'name','value':name,'source_id':row['id'],'url':row['url']}]))
    current={**current,'cursor':0,'saved_ids':keys,'source_ids':[row['id'] for row in sources],
        'options':{**current['options'],'max_leads':4},'prompt':'找深圳灯具买家，每家至少两个网站交叉核验',
        'steps':[{'channel':'industry_directory','query':'上一发现轮'}, {'channel':'official','query':'原官网发现'},
            {'channel':'industry_directory','query':'原行业发现'}]}
    record(current['job_id'],'industry_directory','深圳灯具公开联系')
    focused=asyncio.run(agent.gap_node(current))
    assert focused['enrichment_name']==names[0] and names[0] in focused['steps'][1]['query']
    fresh=archive_sources(current['job_id'],[{'url':'https://example.net/new/'+uuid.uuid4().hex,'title':names[0],
        'body':names[0]+'位于深圳，经销灯具。'+('隔离新资料。'*30)}],'网页正文','official')[0]
    prompts=[]
    async def model(state,schema,prompt,label):
        """只检查真实提取协议，不发模型请求或生成任何候选事实。"""
        prompts.append(prompt);return CandidateBatch(candidates=[],missing_fields=[])
    monkeypatch.setattr(agent,'cached_model',model)
    asyncio.run(agent.extract_node({**current,**focused,'source_ids':[row['id'] for row in sources]+[fresh['id']],
        'recent_read_source_ids':[fresh['id']]}))
    assert '\n明确指定主体：'+json.dumps([names[0]],ensure_ascii=False) in prompts[0]
    context=json.loads(prompts[0].split('\n来源：',1)[1].split('\n明确指定主体：',1)[0])
    assert {row['url'] for row in context}=={sources[0]['url'],fresh['url']}
    record(current['job_id'],'official',focused['steps'][1]['query'])
    opened=asyncio.run(agent.gap_node({**current,**focused}))
    assert not opened['enrichment_name'] and opened['steps'][opened['cursor']]['query']=='原行业发现'
    new='深圳隔离新发现商行'
    newer=archive_sources(current['job_id'],[{'url':'https://example.net/newer/'+uuid.uuid4().hex,
        'title':new,'body':new+'位于深圳，经销灯具。'+('隔离新主体资料。'*30)}],'网页正文','industry_directory')[0]
    asyncio.run(agent.extract_node({**current,**opened,'source_ids':[row['id'] for row in sources]+[newer['id']],
        'recent_read_source_ids':[newer['id']]}))
    assert '\n明确指定主体：' not in prompts[-1] and newer['url'] in prompts[-1] and sources[0]['url'] not in prompts[-1]


def test_uncontactable_index_candidate_does_not_block_early_directory(client):
    """client隔离库；已有无联系候选仍允许目录降级，完整电话出现后不抢占后续搜索计划。"""
    from app import agent
    from app.db import Session,Lead,identifier
    current=state(client);key=identifier()
    with Session.begin() as db:db.add(Lead(id=key,display_name='深圳隔离摘录企业',city='深圳',facts={},evidence=[],dedupe_key=uuid.uuid4().hex))
    record(current['job_id'],'b2b_1688','原1688查询');record(current['job_id'],'qcc_public','原企查查查询')
    current={**current,'saved_ids':[key]}
    result=asyncio.run(agent.gap_node(current))
    assert result['direct_read_pending'] and result['direct_read_target']['channel']=='mall_directory'
    with Session.begin() as db:db.get(Lead,key).facts={'phone':{'value':'13428788412','verification':'原文匹配'}}
    assert not asyncio.run(agent.gap_node(current))['direct_read_pending']


def test_retail_enrichment_preserves_explicit_procurement_step(client):
    """client隔离库；保留明确采购平台首次查询，但不借其补零售客户电话或第二网站。"""
    from app.agent import gap_node
    from app.db import Session,Lead,identifier
    current=state(client);key=identifier();name='深圳隔离零售灯饰'
    with Session.begin() as db:db.add(Lead(id=key,display_name=name,city='深圳',facts={
        'phone':{'value':'13428788412','verification':'原文匹配'}},evidence=[],dedupe_key=uuid.uuid4().hex))
    steps=[{'channel':'official','query':'原发现'}, {'channel':'ccgp','query':'深圳灯具采购公告'}, {'channel':'official','query':'原官网'}]
    current={**current,'cursor':0,'steps':steps,'saved_ids':[key],'prompt':'找深圳零售客户，每家至少两个网站，并查中国政府采购',
        'options':{**current['options'],'max_reads':0,'enabled_channels':['official','ccgp']}}
    result=asyncio.run(gap_node(current))
    assert result['steps'][1]==steps[1] and not result['enrichment_name']
    record(current['job_id'],'ccgp',steps[1]['query'])
    following=asyncio.run(gap_node({**current,**result}))
    assert following['enrichment_name']==name and name in following['steps'][2]['query']


def test_unverified_candidate_procurement_gap_does_not_select_purchase_channel(client):
    """client隔离库；来源产生procurement缺口不能让未核身份候选到采购平台补电话。"""
    from app.agent import gap_node
    current=state(client);name='深圳隔离未核灯饰'
    current={**current,'cursor':0,'steps':[{'channel':'official','query':'旧查询'}],
        'candidate_targets':[name],'gaps':['buyer_role','procurement'],
        'options':{**current['options'],'max_reads':0,'enabled_channels':['ccgp','official']}}
    result=asyncio.run(gap_node(current));step=result['steps'][result['cursor']]
    assert step['channel']=='official' and name in step['query'] and '采购公告' not in step['query']
    project=asyncio.run(gap_node({**current,'plan':{'target_roles':['project_buyer']}}))
    step=project['steps'][project['cursor']]
    assert step['channel']=='ccgp' and '采购公告' in step['query'] and name not in step['query']
    assert '公开业务电话' not in step['query']


def test_directory_enrichment_first_query_anchors_original_phone(client):
    """client隔离库；短店名首次补查带原完整电话，后续不锁死号码，短号无联系资格不作查询锚点。"""
    from app.agent import gap_node
    from app.db import Session,Lead,identifier
    current=state(client);key=identifier();name='隔离品牌灯饰';phone='13428788412'
    with Session.begin() as db:db.add(Lead(id=key,display_name=name,city='深圳',facts={
        'phone':{'value':phone,'verification':'原文匹配'}},
        evidence=[{'field':'name','url':'http://www.leanju.com:8080/subbranch-detail/i-91.html'}],dedupe_key=uuid.uuid4().hex))
    current={**current,'cursor':0,'steps':[{'channel':'official','query':'旧查询'}],'saved_ids':[key],
        'options':{**current['options'],'max_reads':0,'max_leads':1,'enabled_channels':['official']}}
    result=asyncio.run(gap_node(current));query=result['steps'][result['cursor']]['query']
    assert name in query and phone in query
    record(current['job_id'],'official',query)
    later=asyncio.run(gap_node(current));assert phone not in later['steps'][later['cursor']]['query']
    with Session.begin() as db:db.get(Lead,key).facts={'phone':{'value':'81762065','verification':'原文匹配'}}
    short=asyncio.run(gap_node(current));assert '81762065' not in short['steps'][short['cursor']]['query']
