"""独立关系资料、主体消歧与真实LangGraph恢复的本地隔离回归；外部模型明确使用替身。"""
import asyncio
import uuid
import pytest
from sqlalchemy import select, func
from test_company_workspace import workspace


def seed_company(session, name, alias=''):
    """session为隔离事务工厂，name为夹具全称、alias可空；返回独立公司及正文ID，不代表真实企业。"""
    from app.db import Evidence
    from app.company_models import Company, CompanyFact
    from app.company_service import stable_key, ensure_company
    with session.begin() as db:
        company = ensure_company(db, name, visibility='counterparty')
        db.flush()
        quote = name + ('（以下简称“'+alias+'”）' if alias else '')
        source = Evidence(title=name, url='https://qa-'+uuid.uuid4().hex+'.example.com/about', body=quote+'。本地夹具企业资料，仅用于自动化核验。'*12, kind='网页正文')
        db.add(source); db.flush()
        db.add(CompanyFact(company_id=company.id, unique_key=stable_key(company.id,'name'), field='name', label='企业名称', raw_value=name, source_ids=[source.id], quote=quote))
        if alias:
            company.short_name=alias
            db.add(CompanyFact(company_id=company.id, unique_key=stable_key(company.id,'alias'), field='short_name', label='企业简称', raw_value=alias, source_ids=[source.id], quote=quote))
        return company.id, source.id


def new_job(client, prompt):
    """client为隔离API、prompt非空；返回真实submit创建的原任务。"""
    cid=client.post('/api/conversations').json()['id']
    return client.post('/api/conversations/'+cid+'/messages',json={'content':prompt,'client_token':uuid.uuid4().hex}).json()


def test_each_relation_has_direction_reason_and_own_url(workspace):
    client, session, imported=workspace
    cid=imported['company_ids'][0]
    rows=[r for r in client.get('/api/companies/'+cid).json()['relations'] if r['relation_type'] in {'supplier','customer'}]
    assert len(rows)==10 and len({r['detail_url'] for r in rows})==10
    for row in rows:
        data=client.get('/api'+row['detail_url']).json()
        assert data['relation']['counterparty_name']==row['counterparty_name']
        assert ('采购' if row['relation_type']=='supplier' else '销售') in row['direction']
        assert '2025' in row['reason'] and data['relation']['evidence_refs']
        assert data['counterparty'] is None
        assert client.get('/api/companies/'+imported['company_ids'][1]+'/relations/'+row['id']).status_code==404


@pytest.mark.parametrize('name',['甲有限公司及乙有限公司','甲集团及下属公司','华测检测认证集团股份有限公司及其关联企业'])
def test_composite_is_not_single_entity(name):
    from app.relation_service import composite_name
    assert composite_name(name)


def test_identity_candidate_requires_original_full_body(workspace):
    from app.company_identity import _candidate
    from app.db import Evidence
    name='原样核验有限公司'
    for kind,body,quote in [('搜索摘要',name+'。主营测试。'*30,name),('网页正文',name,name),('网页正文',name+'，本地测试。'*30,name+',本地测试。')]:
        source=Evidence(id=uuid.uuid4().hex,title=name,url='https://qa.example.com',kind=kind,body=body)
        assert _candidate(name,'原样核验',source,quote) is None


def test_alias_can_resolve_but_substring_needs_confirmation(workspace):
    from app.company_identity import local_candidates
    _, session, _=workspace
    name='简称核验'+uuid.uuid4().hex+'有限公司';alias='简称'+uuid.uuid4().hex
    seed_company(session,name,alias)
    assert local_candidates(alias)[0]['automatic'] is True
    assert local_candidates(name[:-4])[0]['automatic'] is False


def test_independent_profile_and_duplicate_binding(workspace):
    from app.company_models import CompanyRelation, CompanyFact
    from app.company_research_schemas import CompanySnapshot, ResearchFact
    from app.company_validation import save_snapshot
    from app.db import Job,Evidence
    client,session,imported=workspace;root=imported['company_ids'][0]
    name='独立对手'+uuid.uuid4().hex+'有限公司'
    job=new_job(client,'补齐上下游资料')
    with session.begin() as db:
        original=CompanyRelation(company_id=root,counterparty_name=name,relation_type='supplier',report_period='2025',amount=12,unit='元',currency='CNY',unique_key=uuid.uuid4().hex)
        duplicate=CompanyRelation(company_id=root,counterparty_name=name,relation_type='supplier',report_period='2025',amount=12,unit='元',currency='CNY',unique_key=uuid.uuid4().hex)
        db.add_all([original,duplicate]);db.flush();rid=original.id;duplicate_id=duplicate.id
        row=db.get(Job,job['id']);row.company_ids=[root];row.metrics={**row.metrics,'requested_fields':['supplier']}
        quote=name+'主营精密阀门。'
        source=Evidence(job_id=job['id'],title=name,url='https://own.example.com/about',body=quote+'这是独立资料归属的本地自动化核验夹具。'*15,kind='网页正文')
        db.add(source);db.flush();sid=source.id
    result=save_snapshot(job['id'],CompanySnapshot(name=name,source_id=sid,identity_quote=name,facts=[ResearchFact(field='business',label='主营',value='精密阀门',quote=quote,source_id=sid)]),{sid},[name],rid)
    data=client.get('/api/companies/'+root+'/relations/'+duplicate_id).json()
    assert data['counterparty']['facts']['business']['raw_value']=='精密阀门'
    assert {s['id'] for s in data['counterparty']['sources']}=={sid}
    with session() as db:
        assert db.get(CompanyRelation,duplicate_id).counterparty_id==result['company_id']
        assert db.get(Job,job['id']).company_ids==[root]


def test_counterparty_cannot_borrow_parent_fields_or_conflicting_identity(workspace):
    from app.company_models import CompanyRelation, CompanyFact, Company
    from app.company_research_schemas import CompanySnapshot, ResearchFact
    from app.company_validation import save_snapshot
    from app.db import Job,Evidence
    from app.service import ServiceError
    client,session,imported=workspace;root=imported['company_ids'][0]
    name='归属核验'+uuid.uuid4().hex+'有限公司';company,sid=seed_company(session,name)
    job=new_job(client,'补齐上下游资料')
    with session.begin() as db:
        relation=CompanyRelation(company_id=root,counterparty_name=name,relation_type='supplier',unique_key=uuid.uuid4().hex)
        db.add(relation);db.flush();rid=relation.id
        j=db.get(Job,job['id']);j.company_ids=[root];j.metrics={**j.metrics,'requested_fields':['supplier']}
        source=db.get(Evidence,sid);source.title='母企业年度报告';source.body=name+'作为供应商。母企业主营造船。'+'本地自动化核验报告不能套用主营。'*15
        db.get(Company,company).credit_code='OLD_CODE'
    receipt=save_snapshot(job['id'],CompanySnapshot(name=name,source_id=sid,identity_quote=name,facts=[ResearchFact(field='business',label='主营',value='造船',quote='母企业主营造船。',source_id=sid)]),{sid},[name],rid)
    assert receipt['accepted_fields']==0 and receipt['rejected']
    with session.begin() as db:
        source=db.get(Evidence,sid);source.title=name;source.body=name+'信用代码：NEW_CODE。'+'本地自动化核验身份冲突。'*15
    with pytest.raises(ServiceError,match='信用代码冲突'):
        save_snapshot(job['id'],CompanySnapshot(name=name,source_id=sid,identity_quote=name,facts=[ResearchFact(field='credit_code',label='信用代码',value='NEW_CODE',quote=name+'信用代码：NEW_CODE。',source_id=sid)]),{sid},[name],rid)
    with session() as db:assert db.get(Company,company).credit_code=='OLD_CODE'


def test_confirm_candidate_and_full_graph_resume_keep_same_job(workspace,monkeypatch,intent_decision):
    """真实图先needs_input，再确认后跑到研究完成；外部仅模型/网络替身，checkpoint与原账本不清零。"""
    from app import agent,company_research,company_identity
    from app.db import Job,ToolCall,Message
    from app.company_research_schemas import CompanyPlan,CompanyBatch,GapDecision
    client,session,_=workspace
    short='歧义'+uuid.uuid4().hex
    first,sid=seed_company(session,short+'江苏有限公司')
    second,_=seed_company(session,short+'山东有限公司')
    intent_decision.update(intent='company_query',targets=[short],requested_fields=['name'],research_prompt='查询'+short,title='企业确认')
    job=new_job(client,'查询'+short)
    async def no_external(schema,prompt):
        if schema is CompanyPlan:
            assert short+'江苏有限公司' in prompt
            return CompanyPlan(targets=[short+'江苏有限公司'],steps=[])
        if schema is GapDecision:return GapDecision(continue_research=False)
        if schema is CompanyBatch:return CompanyBatch(companies=[])
        raise AssertionError('非预期外部模型')
    monkeypatch.setattr(agent,'structured',no_external)
    # 保留真实图的resolver/plan/answer，只禁止深度网络；主体未选时它不应调用collect。
    async def collect(state):
        from app.company_validation import save_snapshot
        from app.company_research_schemas import CompanySnapshot
        receipt=save_snapshot(state['job_id'],CompanySnapshot(name=short+'江苏有限公司',source_id=sid,identity_quote=short+'江苏有限公司'),{sid},[short+'江苏有限公司'])
        return {'company_updates':1,'company_ids':[first],'company_receipts':[receipt]}
    monkeypatch.setattr(company_research,'company_collect',collect)
    with session.begin() as db:
        row=db.get(Job,job['id']);row.status='running';row.metrics={**row.metrics,'model_budget':{'calls':3,'accounted_tokens':900}}
    asyncio.run(agent.run_job(job['id']))
    waiting=client.get('/api/jobs/'+job['id']).json()
    assert waiting['status']=='needs_input',waiting
    resolution=waiting['metrics']['company_resolution'];assert len(resolution['candidates'])==2
    candidate=next(x for x in resolution['candidates'] if x['company_id']==first)
    payload={'conversation_id':job['conversation_id'],'resolution_revision':resolution['revision'],'candidate_id':candidate['id'],'client_token':uuid.uuid4().hex}
    wrong={**payload,'resolution_revision':resolution['revision']+1}
    assert client.post('/api/jobs/'+job['id']+'/identity-confirmation',json=wrong).status_code==409
    assert client.post('/api/jobs/'+job['id']+'/identity-confirmation',json={**payload,'candidate_id':'unknown'}).status_code==422
    assert client.post('/api/jobs/'+job['id']+'/identity-confirmation',json={**payload,'conversation_id':'wrong'}).status_code==404
    confirmed=client.post('/api/jobs/'+job['id']+'/identity-confirmation',json=payload)
    assert confirmed.status_code==202,confirmed.text
    assert client.post('/api/jobs/'+job['id']+'/identity-confirmation',json=payload).json()['id']==job['id']
    before=confirmed.json()['metrics']['model_budget']
    with session.begin() as db:db.get(Job,job['id']).status='running'
    asyncio.run(agent.run_job(job['id']))
    final=client.get('/api/jobs/'+job['id']).json()
    assert final['status']=='completed',final.get('error')
    assert final['metrics']['target_company_id']==first and second not in final['company_ids']
    assert final['metrics']['model_budget']['calls']>=before['calls'] and final['elapsed_ms']>=waiting['elapsed_ms']
    with session() as db:
        assert db.get(Job,job['id']).prompt=='查询'+short
        assert db.scalar(select(func.count()).select_from(Job).where(Job.conversation_id==job['conversation_id']))==1


def test_region_supplement_keeps_original_name(workspace):
    from app.company_identity import confirm_identity
    from app.db import Job
    client,session,_=workspace;job=new_job(client,'查询海能')
    with session.begin() as db:
        row=db.get(Job,job['id']);row.status='needs_input';row.metrics={**row.metrics,'company_resolution':{'revision':2,'requested_name':'海能','status':'insufficient','candidates':[]}}
    values={'conversation_id':job['conversation_id'],'resolution_revision':2,'client_token':uuid.uuid4().hex,'context':'江苏'}
    result=confirm_identity(job['id'],values)
    assert result['metrics']['identity_resume']=={'name':'海能','context':'江苏'}


def test_counterparty_resume_analyzes_archived_queue_even_if_read_budget_exhausted(workspace,monkeypatch):
    """真实子节点阶段恢复：已完成最后一次读取后暂停，恢复处理三块资料，不再网络调用、不创建子Job。"""
    from app import counterparty_research,company_research
    from app.db import Job,ToolCall
    from app.company_models import CompanyRelation
    from app.research_tools import Paused
    client,session,imported=workspace;root=imported['company_ids'][0];job=new_job(client,'补齐上下游资料')
    with session.begin() as db:
        relation=CompanyRelation(company_id=root,counterparty_name='恢复核验有限公司',relation_type='supplier',unique_key=uuid.uuid4().hex)
        db.add(relation);db.flush();rid=relation.id
        row=db.get(Job,job['id']);row.status='running';row.company_ids=[root];row.metrics={**row.metrics,'counterparty_only':True,'counterparty_relation_ids':[rid]}
    calls=[];pause=[True]
    async def collect(state):
        calls.append('collect')
        with session.begin() as db:
            db.add(ToolCall(job_id=job['id'],operation_id=uuid.uuid4().hex,tool='fetch_source',attempts=1,status='completed'))
        return {'source_ids':['archived'], 'company_new_source_ids':['archived']}
    async def clean(state):
        assert state['source_ids']==['archived']
        if pause[0]:pause[0]=False;raise Paused()
        return {'company_clean_queue':[{'key':str(i),'source_id':'archived'} for i in range(3)]}
    async def extract(state):
        calls.append('extract');return {'company_clean_queue':state['company_clean_queue'][2:], 'company_batches':[]}
    async def save(state):return {'company_updates':0}
    for name,func_ in [('company_collect',collect),('company_clean',clean),('company_extract',extract),('company_save',save)]:monkeypatch.setattr(company_research,name,func_)
    state={'job_id':job['id'],'options':{'enabled_channels':['official'],'max_searches':1,'max_reads':1,'max_model_calls':10}}
    with pytest.raises(Paused):asyncio.run(counterparty_research.company_counterparties(state))
    result=asyncio.run(counterparty_research.company_counterparties(state))
    assert calls==['collect','extract','extract'] and result['company_ids']==[root]
    with session() as db:
        assert db.get(Job,job['id']).metrics['counterparty_states'][rid]['phase']=='done'
        assert db.scalar(select(func.count()).select_from(Job).where(Job.conversation_id==job['conversation_id']))==1


def test_candidate_address_belongs_to_candidate(workspace,monkeypatch):
    from app import company_identity,agent
    from app.db import Evidence,Job
    from app.company_research_schemas import IdentityBatch,IdentityCandidate
    client,session,_=workspace;job=new_job(client,'查询地址归属')
    name='地址归属有限公司';quote=name+'主营检验。';other='乙企业有限公司地址：江苏。'
    with session.begin() as db:
        row=db.get(Job,job['id']);row.status='running'
        source=Evidence(title='公开企业名录',url='https://fixture.example.com',body=quote+other+'本地自动化核验夹具。'*20,kind='网页正文');db.add(source);db.flush();sid=source.id
    async def model(state,schema,prompt,label):return IdentityBatch(candidates=[IdentityCandidate(name=name,source_id=sid,identity_quote=quote,address='江苏',address_quote=other)])
    monkeypatch.setattr(agent,'cached_model',model)
    result=asyncio.run(company_identity.company_resolve({'job_id':job['id'],'prompt':'查询地址归属','company_intent_targets':['地址归属'],'source_ids':[sid],'reference_only':True,'options':{'enabled_channels':['official']}}))
    assert result['company_resolution']['candidates'][0]['address']==''
