"""结构化匹配门禁：原文引用、主体范围与缓存时效。"""
import copy


def context():
    return {'lead_id':'test-lead','name':'隔离买方','products':[{'name':'知识库软件','specifications':'私有部署'}],
        'evidence':[{'ref':'p0.requirements','value':'知识库开发服务','quote':'采购需求：知识库开发服务','source_id':'s1','status':'verified','url':'https://example.org/notice'}],
        'projects':[{'status':'公开采购','source_id':'s1'}],'limitations':[],'feedback':[]}


def proposed(**overrides):
    item={'product_index':0,'requirement_ref':'p0.requirements','quote':'采购需求：知识库开发服务','fit':'related',
        'reason':'产品与知识库需求方向相关，部署方式尚需核验','next_step':'获取采购文件核验部署方式'}
    return {**item,**overrides}


def test_rejects_fabricated_source_quote_product_and_inactive_evidence():
    from app.lead_analysis import validate_matches
    c=context()
    assert len(validate_matches([proposed()],c)[0])==1
    for invalid in [proposed(requirement_ref='other-lead.fact'),proposed(quote='不存在的引文'),proposed(product_index=5)]:
        accepted,rejected=validate_matches([invalid],c)
        assert not accepted and rejected==1
    c['evidence'][0]['status']='disputed'
    assert validate_matches([proposed()],c)[1]==1


def test_input_fingerprint_changes_with_product_fact_and_feedback():
    from app.lead_analysis import input_fingerprint
    c=context();old=input_fingerprint(c)
    for field,value in [('products',[{'name':'硬件'}]),('feedback',[{'kind':'nonbuyer','content':'不是买家'}]),('projects',[{'status':'已过期','source_id':'s1'}])]:
        altered=copy.deepcopy(c);altered[field]=value
        assert input_fingerprint(altered)!=old


def test_analysis_input_is_valid_bounded_json_and_reports_omissions():
    import json
    from app.lead_analysis import bounded_context
    c=context();c['evidence']=[{**c['evidence'][0],'ref':f'f{i}','quote':'连续原文'*1500} for i in range(30)]
    payload=bounded_context(c,limit=6000)
    assert len(json.dumps(payload,ensure_ascii=False))<=6000
    assert payload['coverage']['omitted_evidence']>0 and payload['limitations']


def test_analysis_endpoint_needs_product_and_is_idempotent(client):
    from test_acquisition_workspace import seed
    import uuid
    lead_id,conv,other,_=seed(client)
    token=uuid.uuid4().hex
    body={'conversation_id':conv,'client_token':token}
    a=client.post('/api/leads/'+lead_id+'/analysis',json=body)
    assert a.status_code==202
    b=client.post('/api/leads/'+lead_id+'/analysis',json=body)
    assert a.json()['id']==b.json()['id']
    assert a.json()['metrics']['target_lead_id']==lead_id
    no_product=client.post('/api/leads/'+lead_id+'/analysis',json={'conversation_id':other,'client_token':uuid.uuid4().hex})
    assert no_product.status_code==409


def test_model_budget_exhaustion_propagates(client,monkeypatch):
    import asyncio,uuid,pytest
    from test_acquisition_workspace import seed
    from app import agent
    from app.db import Session,Job
    from app.lead_analysis import analyze_leads
    from app.service import ServiceError,settings
    lead_id,conv,*_=seed(client)
    task=client.post('/api/leads/'+lead_id+'/analysis',json={'conversation_id':conv,'client_token':uuid.uuid4().hex}).json()
    with Session.begin() as db:db.get(Job,task['id']).status='running'
    async def exhausted(*args,**kwargs):raise ServiceError('任务模型预算已耗尽')
    monkeypatch.setattr(agent,'cached_model',exhausted)
    with pytest.raises(ServiceError,match='预算'):
        asyncio.run(analyze_leads({'job_id':task['id'],'conversation_id':conv,'prompt':'分析','options':settings()},[lead_id],{'products':[{'name':'知识库'}]}))


def test_analysis_answer_preserves_required_site_gap():
    from app.lead_analysis import analysis_markdown
    row={'id':'x','display_name':'隔离买方','evidence':[{'url':'https://example.org/'}],'facts':{}}
    assert '至少2个网站' in analysis_markdown([row],[],site_target=2)


def test_explicit_analysis_graph_does_not_search_and_timeout_can_resume(client,monkeypatch):
    import asyncio,uuid
    from test_acquisition_workspace import seed
    from app import agent,intent
    from app.db import Session,Job
    from app.company_research_schemas import IntentDecision
    from app.lead_analysis import AnalysisBatch,AnalysisItem,Match
    from app.service import resume_task
    lead_id,conv,*_=seed(client)
    task=client.post('/api/leads/'+lead_id+'/analysis',json={'conversation_id':conv,'client_token':uuid.uuid4().hex}).json()
    calls=[]
    async def wrong_intent(state):return IntentDecision(intent='company_query',title='隔离匹配')
    monkeypatch.setattr(intent,'recognize_intent',wrong_intent)
    async def analysis(state,schema,prompt,label):
        calls.append(label)
        if len(calls)==1:raise TimeoutError('isolated model timeout')
        return AnalysisBatch(items=[AnalysisItem(lead_id=lead_id,matches=[Match(product_index=0,requirement_ref='p0.requirements',quote='提供知识库开发与部署服务',fit='related',reason='方向相关，详细规格待核验',next_step='获取采购文件核验部署要求')])])
    monkeypatch.setattr(agent,'cached_model',analysis)
    async def forbidden(*args,**kwargs):raise AssertionError('仅读分析错误进入公网或事实保存')
    for name in ['profile_node','plan_node','search_node','read_node','extract_node','save_node','learn_node']:
        monkeypatch.setattr(agent,name,forbidden)
    asyncio.run(agent.run_job(task['id']))
    first=client.get('/api/jobs/'+task['id']).json()
    assert first['status']=='partial' and first['metrics']['lead_analysis_partial']
    resume_task(task['id']);asyncio.run(agent.run_job(task['id']))
    final=client.get('/api/jobs/'+task['id']).json()
    assert final['status']=='completed' and len(calls)==2
    assert set(final['metrics']['stage_timings'])=={'intent','context','answer'}
    detail=client.get('/api/leads/'+lead_id).json()
    assert detail['analysis']['matches'][0]['quote']=='提供知识库开发与部署服务'
    assert not detail['analysis']['stale']


def test_unchanged_evidence_and_product_reuses_successful_analysis(client,monkeypatch):
    import asyncio,uuid
    from test_acquisition_workspace import seed
    from app import agent
    from app.db import Session,Job
    from app.lead_analysis import analyze_leads,AnalysisBatch,AnalysisItem,Match
    from app.service import settings
    lead_id,conv,*_=seed(client);calls=[];ids=[]
    with Session.begin() as db:
        for _ in range(2):
            job=Job(conversation_id=conv,client_token=uuid.uuid4().hex,prompt='分析',status='running');db.add(job);db.flush();ids.append(job.id)
    async def analyze(state,schema,prompt,label):
        calls.append(label)
        return AnalysisBatch(items=[AnalysisItem(lead_id=lead_id,matches=[Match(product_index=0,requirement_ref='p0.requirements',quote='提供知识库开发与部署服务',fit='related',reason='方向相关，部署条件待核验',next_step='获取采购文件')])])
    monkeypatch.setattr(agent,'cached_model',analyze)
    profile={'products':[{'name':'知识库软件'}]};outputs=[]
    for jid in ids:
        outputs.append(asyncio.run(analyze_leads({'job_id':jid,'conversation_id':conv,'prompt':'分析','options':settings()},[lead_id],profile)))
    assert len(calls)==1 and outputs[1][0]['reused']


def test_company_match_context_keeps_project_specs_deadline_and_quote(client):
    from app.db import Session
    from app.company_models import Company,ProcurementProject
    from app.company_service import company_match_context
    import uuid,json
    with Session.begin() as db:
        company=Company(id=uuid.uuid4().hex,identity_key=uuid.uuid4().hex,name='隔离产品匹配企业',entity_kind='legal');db.add(company);db.flush()
        db.add(ProcurementProject(unique_key=uuid.uuid4().hex,buyer_id=company.id,title='知识库采购',stage='open',deadline='2099-10-16 09:30:00',project_number='QA-SPEC',quote='采购需求：必须本地部署',payload={'specifications':'必须本地部署','budget':1504100,'unit':'元'},source_ids=[]))
    payload=json.loads(company_match_context(company.id))
    assert payload['projects'][0]['specifications']=='必须本地部署'
    assert payload['projects'][0]['deadline']=='2099-10-16 09:30:00'
    assert payload['projects'][0]['quote']=='采购需求：必须本地部署'


def test_company_match_sources_follow_selected_project(monkeypatch):
    import json
    from app import company_service
    project={'title':'本地软件采购','buyer_name':'隔离买方','record_kind':'procurement',
        'project_number':'QA-SOURCE','published_at':'2026-10-12','deadline':'2099-10-16',
        'temporal_status':'公开采购','payload':{'specifications':'本地部署'},'quote':'采购本地软件',
        'source_ids':['s13'],'evidence_refs':[{'source_id':'s13','quote':'采购本地软件'}],'notices':[]}
    detail={'header':{'name':'隔离买方','origin':'研究','research_as_of':'2026-10-13'},
        'facts':[],'projects':[project],
        'sources':[{'id':f's{i}','title':f'来源{i}','url':f'https://example.org/{i}'} for i in range(1,14)]}
    monkeypatch.setattr(company_service,'company_detail',lambda _:detail)
    payload=json.loads(company_service.company_match_context('isolated'))
    assert {s['id'] for s in payload['sources']}=={'s13'}
    assert payload['coverage']['selected_projects']==1
