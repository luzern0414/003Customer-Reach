"""角色肯定/否定、连续单主体介绍与竞争主体的真实校验回归。"""
import uuid
import pytest


def test_every_name_fact_must_match_full_candidate_identity(client):
    """client为隔离库；完整name已存在也不能混入另一个简称作为第二name，未知别名不自动合并。"""
    from app.schemas import Candidate
    from app.service import checked_candidate,ServiceError
    name='深圳隔离照明有限公司';body=name+'在深圳零售灯具。简称：隔离照明。'
    source={'body':body,'title':name,'url':'https://example.org/identity','kind':'网页正文','channel':'official','captured_at':'2026-10-04 00:00:00'}
    candidate=Candidate(display_name=name,city='深圳',buyer_role='retailer',match_reason='合成名称一致性',facts=[
        {'field':field,'value':value,'quote':body,'source_id':'s'} for field,value in [('name',name),('buyer_role','零售'),('name','隔离照明')]])
    with pytest.raises(ServiceError,match='客户名称必须'):checked_candidate(candidate,{'s':source})


@pytest.mark.parametrize('name,tail,role,value,accepted',[
    ('隔离零售有限公司','位于深圳。','retailer','零售',False),
    ('隔离灯饰市场','位于深圳。','mall','灯饰市场',False),
    ('隔离照明经营部','位于深圳灯饰市场。','mall','灯饰市场',False),
    ('隔离照明经营部','位于深圳零售市场。','retailer','零售',False),
    ('隔离照明经营部','是一家位于深圳的灯饰市场。','mall','灯饰市场',True),
    ('隔离零售有限公司','位于深圳，专业从事零售。','retailer','零售',True)])
def test_name_or_location_cannot_supply_business_role(client,name,tail,role,value,accepted):
    """client隔离库，其余为合成原文与预期；名称内角色词、所在地不证明经营身份，明确谓词仍保留。"""
    from app.schemas import Candidate
    from app.service import checked_candidate,ServiceError
    body=name+tail
    source={'title':name,'body':body,'url':'https://example.org/synthetic','kind':'网页正文',
        'captured_at':'2026-10-04 00:00:00','channel':'official'}
    candidate=Candidate(display_name=name,city='深圳',buyer_role=role,match_reason='合成角色边界',facts=[
        {'field':field,'value':item,'quote':body,'source_id':'s'} for field,item in [('name',name),('buyer_role',value)]])
    if accepted:assert checked_candidate(candidate,{'s':source})[0]['buyer_role']['value']==value
    else:
        with pytest.raises(ServiceError,match='主体建立关联'):checked_candidate(candidate,{'s':source})


@pytest.mark.parametrize('tail,accepted',[
    ('，是深圳市品种齐全的家居建材综合类商场。',True),
    (',是深圳市品种齐全的家居建材综合类商场之一。',True),
    ('，不是家居建材综合类商场。',False),
    ('，是位于家居建材综合类商场的灯具经销商。',False),
    ('，是位于家居建材综合类商场。',False),
    ('，是服务家居建材综合类商场。',False),
    ('，是另一照明有限公司的家居建材综合类商场。',False),
])
def test_direct_identity_sentence_survives_comma_and_generic_site_title(client,tail,accepted):
    """client隔离库，tail为明确身份/否定/所在地/竞争主体；实际服务不因通用标题丢直接主谓关联。"""
    from app.schemas import Candidate,Fact
    from app.service import checked_candidate,ServiceError
    name='深圳隔离身份场所';quote=name+tail
    source={'id':'s','title':'官方网站','url':'https://example.org/identity','body':quote,'kind':'网页正文','captured_at':'2026-10-04 00:00:00'}
    candidate=Candidate(display_name=name,city='深圳',buyer_role='mall',match_reason='隔离身份句校验',facts=[
        Fact(field='name',value=name,quote=name,source_id='s'),
        Fact(field='buyer_role',value='家居建材综合类商场',quote=quote,source_id='s')])
    if accepted:
        assert checked_candidate(candidate,{'s':source})[0]['buyer_role']['value']=='家居建材综合类商场'
        with pytest.raises(ServiceError):checked_candidate(candidate,{'s':{**source,'body':quote+'\n'+quote}})
    else:
        with pytest.raises(ServiceError):checked_candidate(candidate,{'s':source})


def test_bounded_intro_links_contiguous_role_but_not_directory_or_competitor():
    """连续引文完整主体锚点可跨介绍句；目录/重复片段/新主体/标题分区仍拒绝。"""
    from app.evidence_role import scoped_role
    name='隔离灯饰经营部'
    quote=name+'成立于2011年，位于深圳。\n主营灯具产品，聚焦深圳开展灯具零售及配套服务。'
    assert scoped_role(name,'灯具零售',quote,name,True,quote)
    assert not scoped_role(name,'灯具零售',quote,name+'企业目录',True,quote)
    assert not scoped_role(name,'灯具零售',quote,name,True,quote+'\n'+quote)
    assert not scoped_role(name,'灯具零售',quote.replace('主营','其他灯饰有限公司主营'),name,True,quote)
    assert not scoped_role(name,'灯具零售',quote.replace('主营','# 其他商户\n主营'),name,True,quote)
    assert not scoped_role(name,'灯具零售','聚焦深圳开展灯具零售及配套服务。',name,True,quote)


@pytest.mark.parametrize('text,expected',[
    ('公司不是零售企业。',True),('公司不从事灯具零售。',True),
    ('零售业务不是本公司主营。',True),('公司并非生产厂家，但经营灯具零售。',False),
    ('公司不从事生产而是开展零售业务。',False),('公司零售灯具。',False)])
def test_role_negation_is_specific_to_same_assertion(text,expected):
    """text/expected为合成角色语句；其他角色否定及转折不抹去真实肯定角色。"""
    from app.evidence_role import role_denied
    assert role_denied('零售',text)==expected


@pytest.mark.parametrize('tail,accepted',[
    ('不是零售企业。',False),('不从事灯具零售。',False),
    ('与其他灯饰有限公司合作零售灯具。',False),('在深圳零售灯具。',True),
    ('成立于2011年，位于深圳。\n主营灯具，聚焦深圳开展灯具零售服务。',True)])
def test_service_enforces_role_ownership_across_all_paths(client,tail,accepted):
    """client隔离持久库，tail角色原文、accepted期望；直接主谓与scoped兜底均走真实checked_candidate。"""
    from app.gateway import archive_sources
    from app.schemas import Candidate
    from app.service import checked_candidate,ServiceError
    name='隔离灯饰经营部'+uuid.uuid4().hex[:6]
    body=name+tail
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'你好','client_token':uuid.uuid4().hex}).json()['id']
    row=archive_sources(job,[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name,'body':body}],'网页正文','official')[0]
    candidate=Candidate(display_name=name,city='',buyer_role='retailer',match_reason='隔离角色验证',
        facts=[{'field':field,'value':value,'quote':body,'source_id':row['id']} for field,value in [('name',name),('buyer_role','零售')]])
    if accepted:assert checked_candidate(candidate,{row['id']:row})[0]['buyer_role']['value']=='零售'
    else:
        with pytest.raises(ServiceError,match='主体建立关联'):checked_candidate(candidate,{row['id']:row})


def test_rejected_role_target_survives_next_empty_candidate_batch(client,monkeypatch):
    """实际save/gap：角色未确认的完整主体保留补查方向，不当客户保存，空批次不抹去目标。"""
    import asyncio
    from app import agent
    from app.db import Session,Job
    from app.gateway import archive_sources
    from app.schemas import Candidate
    from app.service import save_settings
    options=save_settings({'enabled_channels':['official','industry_directory'],'max_leads':1,'max_reads':0})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具零售商','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,job).status='running'
    name='隔离待核灯饰经营部'+uuid.uuid4().hex[:6]
    body=name+'位于深圳。\n网页栏目：零售'
    row=archive_sources(job,[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name,'body':body}],'网页正文','official')[0]
    candidate=Candidate(display_name=name,city='深圳',buyer_role='retailer',match_reason='隔离待核',facts=[
        {'field':'name','value':name,'quote':body,'source_id':row['id']},
        {'field':'buyer_role','value':'零售','quote':'网页栏目：零售','source_id':row['id']}])
    async def unchanged(*args,**kwargs):return candidate
    monkeypatch.setattr(agent,'cached_model',unchanged)
    state={'job_id':job,'prompt':'找深圳灯具零售商','profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'options':options,'source_ids':[row['id']],'saved_ids':[],'candidates':[candidate.model_dump()],
        'plan':{'target_roles':['retailer']},'steps':[{'channel':'official','query':'深圳灯具'},{'channel':'industry_directory','query':'深圳行业灯具'}],'cursor':0}
    saved=asyncio.run(agent.save_node(state))
    assert saved['saved_ids']==[] and saved['candidate_targets']==[name]
    next_state=asyncio.run(agent.gap_node({**state,**saved,'candidates':[]}))
    assert name in next_state['steps'][1]['query']
    assert '核验待确认' in next_state['steps'][1]['purpose']


def test_policy_upgrade_revalidates_without_reusing_stale_rejection(client):
    """client隔离库；旧规则同参数拒绝记录保留，新规则通过真实Broker重新核验，不清旧账本。"""
    import asyncio
    import hashlib
    import json
    from app.db import Session,ToolCall
    from app.research_tools import ToolBroker
    from sqlalchemy import select
    from test_export_signals import fixture
    lead,candidate,sources,job=fixture(client)
    args={'candidate':candidate.model_dump()}
    operation=hashlib.sha256(json.dumps(['role-policy-2',job,'persist_lead',args],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with Session.begin() as db:db.add(ToolCall(job_id=job,operation_id=operation,tool='persist_lead',channel='knowledge',
        status='rejected',arguments=args,result={'error':'角色原文没有与该客户主体建立关联'},elapsed_ms=11))
    broker=ToolBroker(job,{'enabled_channels':['official'],'max_leads':1},{'region':'深圳','products':[{'name':'吊灯'}]})
    broker.allowed_sources.update(sources)
    result=asyncio.run(broker.execute('persist_lead',args))
    assert result['id']==lead and not result.get('error')
    with Session() as db:assert db.scalar(select(ToolCall).where(ToolCall.operation_id==operation)).status=='rejected'


@pytest.mark.parametrize('value,label,suffix,accepted',[
    ('灯具市场','市场类型：灯具市场','',True),
    ('灯饰专业市场','市场类别：灯饰专业市场','',True),
    ('灯具市场','市场类型：灯具市场','企业目录',False),
    ('灯具市场','市场类型：不是灯具市场','',False)])
def test_market_role_field_needs_single_subject_and_positive_classification(client,value,label,suffix,accepted):
    """client隔离库，value/label为合成原字段、suffix标题、accepted期望；单主体市场字段通过，目录/否定拒绝。"""
    from app.gateway import archive_sources
    from app.schemas import Candidate
    from app.service import checked_candidate,ServiceError
    name='隔离灯饰市场'+uuid.uuid4().hex[:6]
    body=name+'\n地区：深圳\n'+label
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'你好','client_token':uuid.uuid4().hex}).json()['id']
    source=archive_sources(job,[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name+suffix,'body':body}],'网页正文','official')[0]
    candidate=Candidate(display_name=name,city='深圳',buyer_role='mall',match_reason='隔离市场字段',facts=[
        {'field':'name','value':name,'quote':body,'source_id':source['id']},
        {'field':'buyer_role','value':value,'quote':label,'source_id':source['id']}])
    if accepted:assert checked_candidate(candidate,{source['id']:source})[0]['buyer_role']['value']==value
    else:
        with pytest.raises(ServiceError,match='主体建立关联'):checked_candidate(candidate,{source['id']:source})


def test_market_type_does_not_corrupt_product_category(client):
    """client隔离库；实际字段校验拒绝把场所类别当主营，真实LED/家用照明原文仍通过。"""
    from app.gateway import archive_sources
    from app.schemas import Candidate,Fact
    from app.service import checked_candidate,ServiceError
    name='隔离品类市场'+uuid.uuid4().hex[:6]
    body=name+'位于深圳。市场类型：灯具市场。主要经营LED光源、家用照明灯具。'
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'你好','client_token':uuid.uuid4().hex}).json()['id']
    source=archive_sources(job,[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name,'body':body}],'网页正文','official')[0]
    base=Candidate(display_name=name,city='深圳',buyer_role='mall',match_reason='隔离语义验证',facts=[
        Fact(field='name',value=name,quote=body,source_id=source['id']),
        Fact(field='buyer_role',value='灯具市场',quote='市场类型：灯具市场',source_id=source['id'])])
    wrong=base.model_copy(update={'facts':[*base.facts,Fact(field='categories',value='灯具市场',quote='市场类型：灯具市场',source_id=source['id'])]})
    with pytest.raises(ServiceError,match='市场类型不能替代主营'):checked_candidate(wrong,{source['id']:source})
    correct=base.model_copy(update={'facts':[*base.facts,Fact(field='categories',value='LED光源、家用照明灯具',quote='主要经营LED光源、家用照明灯具',source_id=source['id'])]})
    assert checked_candidate(correct,{source['id']:source})[0]['categories']['value']=='LED光源、家用照明灯具'
