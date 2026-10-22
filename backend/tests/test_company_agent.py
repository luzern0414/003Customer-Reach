"""真实LangGraph/HTTP解析/工具账本/企业持久链；外部模型和HTTP仅此处使用明确夹具。"""
import asyncio
import json
import re
import uuid
import httpx
import pytest
from types import SimpleNamespace
from sqlalchemy import select


def test_company_mode_preserves_seller_and_question_routes():
    """企业研究进入新模式，产品获客和解释不被公司关键词抢走。"""
    from app.conversation import company_intent
    assert company_intent('查询海能技术的完整企业画像、采购信息和上下游关系')
    assert company_intent('研究比亚迪股份有限公司的公开资料')
    assert not company_intent('我们销售灯具，寻找深圳经销商客户')
    assert not company_intent('解释上下游关系是什么意思')


@pytest.mark.parametrize('followup',[False,True])
def test_company_graph_without_products_uses_real_broker_and_sse(client, monkeypatch, followup):
    """仅替外部响应，保留实际图、Trafilatura、来源作用域、保存和SSE，验证不学习卖方产品画像。"""
    from app import agent, research_tools, company_research
    from app.db import Session, Job, Conversation, ToolCall, JobEvent, Message
    from app.company_models import Company, CompanyFact, ResearchCompany
    from app.company_research_schemas import CompanyPlan, CompanyBatch, CompanySnapshot, ResearchFact
    suffix=uuid.uuid4().hex
    name='企业研究验证'+suffix+'有限公司'
    url='https://company-'+suffix+'.example.com/profile'
    paragraph=f'企业名称：{name}。公司行业分类：仪器仪表制造业。公司主营业务：研发、生产分析仪器。'
    html='<html><head><title>'+name+'</title></head><body><main><h1>'+name+'</h1><p>'+paragraph+'</p><p>'+('这是明确标识为自动验证的数据，公开研究不能把需求量作成交量，不能将候选报价或建设投资预算当最终成交金额。'*6)+'</p></main></body></html>'
    original_client=httpx.AsyncClient
    def transport_client(*args,**kwargs):
        """只拦本用例的HTTP，返回真实HTML由生产解析器处理；不请求公网。"""
        kwargs['transport']=httpx.MockTransport(lambda request:httpx.Response(200,text=html,headers={'content-type':'text/html; charset=utf-8'},request=request))
        kwargs['trust_env']=False
        return original_client(*args,**kwargs)
    monkeypatch.setattr(research_tools.httpx,'AsyncClient',transport_client)
    monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    from app import browser_reader
    monkeypatch.setattr(browser_reader,'browser_settings',lambda:{'enabled':False})
    async def structured(schema,prompt):
        """模型夹具只提出给定正文中的字段，生产缓存、验证与数据库调用保持真实。"""
        if schema is CompanyPlan:return CompanyPlan(targets=[name],steps=[])
        assert schema is CompanyBatch
        source_id=re.findall(r'"id":\s*"([a-f0-9]{32,64})"',prompt)[0]
        return CompanyBatch(companies=[CompanySnapshot(name=name,source_id=source_id,identity_quote='企业名称：'+name+'。',facts=[
            ResearchFact(field='industry',label='行业分类',value='仪器仪表制造业',source_id=source_id,quote='公司行业分类：仪器仪表制造业。'),
            ResearchFact(field='business',label='主营业务',value='研发、生产分析仪器',source_id=source_id,quote='公司主营业务：研发、生产分析仪器。')])])
    monkeypatch.setattr(agent,'structured',structured)
    class Model:
        """只替外部回答模型；异步块用于核验实际SSE写入，不冒充真实模型验收。"""
        async def astream(self,messages):
            yield SimpleNamespace(content='已保存验证企业的')
            yield SimpleNamespace(content='行业与主营，采购和上下游未知。')
    monkeypatch.setattr(company_research,'model',lambda:Model())
    monkeypatch.setattr(agent,'settings',lambda:{'enabled_channels':['official'],'max_searches':1,'max_reads':1,
        'max_leads':2,'max_seconds':60,'max_model_calls':10,'max_model_tokens':50000,'max_candidate_searches':2,'default_region':'深圳'})
    conv=client.post('/api/conversations').json()
    request=f'查询{name}的信息，仅读取以下网页，不读取其他网页：{url}'
    if followup:
        # 真实提交路由保留用户短确认，并把获授权的原主体/限页约束传入图节点。
        prior=client.post('/api/conversations/'+conv['id']+'/messages',json={'content':request,'client_token':suffix+'-prior'}).json()
        with Session.begin() as db:db.get(Job,prior['id']).status='completed'
    response=client.post('/api/conversations/'+conv['id']+'/messages',json={'content':'都要' if followup else request, 'client_token':suffix})
    job_id=response.json()['id']
    with Session.begin() as db:db.get(Job,job_id).status='running'
    asyncio.run(agent.run_job(job_id))
    with Session() as db:
        job=db.get(Job,job_id)
        assert job.status=='completed',job.error
        assert len(job.company_ids)==1 and job.lead_ids==[]
        company=db.get(Company,job.company_ids[0]);assert company.name==name
        assert db.scalar(select(CompanyFact).where(CompanyFact.company_id==company.id,CompanyFact.field=='industry')).raw_value=='仪器仪表制造业'
        member=db.scalar(select(ResearchCompany).where(ResearchCompany.job_id==job_id));assert member.company_id==company.id
        assert db.get(Conversation,conv['id']).profile=={}
        calls=list(db.scalars(select(ToolCall).where(ToolCall.job_id==job_id)))
        assert any(c.tool=='fetch_source' and c.status=='completed' for c in calls)
        assert any(c.tool=='persist_company' and c.status=='completed' for c in calls)
        assert not any(c.tool=='product_profile' for c in calls)
        events=list(db.scalars(select(JobEvent).where(JobEvent.job_id==job_id,JobEvent.event_type=='message.delta').order_by(JobEvent.id)))
        assert job.metrics['first_answer_ms']>0 and any('首批资料已保存' in event.payload['delta'] for event in events)
        # 首批答复与最终答复是不同generation；reset后只能重放最终一代，不能拼接旧草稿。
        deltas=[e.payload['delta'] for e in events if e.payload['generation_id']==job.generation_id]
        assert ''.join(deltas)==db.get(Message,job.reply_message_id).content
    rows=client.get('/api/companies',params={'conversation_id':conv['id']}).json()
    assert rows['total']==1 and rows['items'][0]['id']==company.id


def test_company_validator_rejects_fabricated_quote_and_statistics(client):
    """真实保存门禁拒绝虚构值/统计日期，不因已知公司身份放宽逐字段证据。"""
    from app.db import Session, Conversation, Job, Evidence
    from app.company_research_schemas import CompanySnapshot,ResearchFact
    from app.company_validation import save_snapshot
    from app.company_models import CompanyFact
    suffix=uuid.uuid4().hex;name='原文核验'+suffix+'有限公司'
    body=f'企业名称：{name}。在职员工总计123人。公司成立日期2020年1月1日。行业分类：仪器仪表制造业。'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt='研究'+name,query_mode='company_query',client_token=suffix);db.add(job)
        source=Evidence(job_id=job.id,title=name,url='https://validation.example.com/'+suffix,body=body,kind='网页正文',channel='official');db.add(source);db.flush();job_id=job.id;sid=source.id
    snap=CompanySnapshot(name=name,source_id=sid,identity_quote='企业名称：'+name+'。',facts=[
        ResearchFact(field='industry',label='行业',value='不存在的行业',source_id=sid,quote='行业分类：仪器仪表制造业。'),
        ResearchFact(field='headcount',label='员工人数',value='123',unit='人',scope='在职员工',report_period='2020-01-01',source_id=sid,quote='在职员工总计123人。',metadata_quote='公司成立日期2020年1月1日。')])
    result=save_snapshot(job_id,snap,{sid},[name]);assert result['accepted_fields']==0 and len(result['rejected'])==2
    with Session() as db:
        assert not list(db.scalars(select(CompanyFact).where(CompanyFact.company_id==result['company_id'],CompanyFact.field.in_(['industry','headcount']))))


def test_target_identity_mapping_is_local_and_exact():
    """完整名与简称只可由对应连续身份声明授权，同报告其他主体和子串均拒绝。"""
    from app.company_validation import target_matches
    name='甲方未来技术集团股份有限公司'
    assert target_matches(name,name,'企业名称：'+name)
    assert target_matches(name,'甲方技术',name+'（以下简称“甲方技术”）。')
    assert not target_matches('乙方有限公司','甲方技术',name+'（以下简称“甲方技术”）。乙方有限公司是供应商。')
    assert not target_matches('甲方未来技术集团股份有限公司子公司','甲方未来技术集团股份有限公司','企业名称：甲方未来技术集团股份有限公司子公司')


def test_selected_company_reference_only_does_not_add_old_urls(client):
    """已有官网及报告不能扩大当前限页读取入口，历史身份只用于校验不作为新HTTP授权。"""
    from app.db import Session, Conversation, Job, Evidence
    from app.company_service import ensure_company, stable_key
    from app.company_models import CompanyFact
    from app.company_research import company_context
    suffix=uuid.uuid4().hex;name='限页验证'+suffix+'有限公司';url='https://www.example.com/contact'
    with Session.begin() as db:
        company=ensure_company(db,name);conv=Conversation();db.add(conv);db.flush()
        source=Evidence(title=name,body=f'公司名称：{name}。公司网址：https://www.example.com。'+('已保存历史资料，仅验证读取范围。'*20),url='https://www.example.com/old-report',kind='历史归档正文')
        db.add(source);db.flush()
        db.add(CompanyFact(unique_key=stable_key(suffix),company_id=company.id,field='website',label='公司网址',raw_value='https://www.example.com',quote='公司网址：https://www.example.com。',source_ids=[source.id]))
        job=Job(conversation_id=conv.id,client_token=suffix,prompt='仅复核以下页面，不读取其他网页：'+url,query_mode='company_query',metrics={'target_company_id':company.id});db.add(job);db.flush();jid=job.id;prompt=job.prompt
    state=asyncio.run(company_context({'job_id':jid,'prompt':prompt,'options':{'enabled_channels':['official']}}))
    assert state['reference_only'] is True
    assert state['company_direct_urls']==[{'url':url,'channel':'official'}]


def test_procurement_dates_and_events_merge_across_jobs(client):
    """历史项目与新公告精确归并，跨任务重读不增公告，旧事件不回退成交阶段，伪日期不保存。"""
    from app.db import Session, Conversation, Job, Evidence
    from app.company_service import ensure_company, stable_key
    from app.company_models import ProcurementProject, ProcurementNotice
    from app.company_research_schemas import CompanySnapshot, ResearchProject
    from app.company_validation import save_snapshot
    suffix=uuid.uuid4().hex;name='公告验证'+suffix+'有限公司';title='分析仪采购项目';number='TEST-'+suffix
    with Session.begin() as db:
        company=ensure_company(db,name);cid=company.id
        db.add(ProcurementProject(unique_key=stable_key('historical',suffix),buyer_id=cid,title=title,project_number=number,stage='公开招标',published_at='2026-09-01'))
    for idx,day,stage in [(0,'2026-09-08','awarded'),(1,'2026-09-08','awarded'),(2,'2026-09-01','open')]:
        phase='成交公告' if stage=='awarded' else '招标公告'
        quote=f'采购人：{name}。项目名称：{title}。项目编号：{number}。{phase}。需求数量：2台。'
        pub='发布日期：'+day+'。';deadline='投标截止时间：2026年9月7日15:30。'
        with Session.begin() as db:
            conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt='研究'+name,query_mode='company_query',client_token=suffix+str(idx));db.add(job);db.flush()
            source=Evidence(job_id=job.id,url='https://example.com/notice/'+str(idx),title=title,kind='网页正文',body=quote+pub+deadline+('明确标注自动验证夹具，不属于生产企业公告。'*20));db.add(source);db.flush();jid=job.id;sid=source.id
        snapshot=CompanySnapshot(name=name,source_id=sid,identity_quote='采购人：'+name+'。',projects=[ResearchProject(buyer_name=name,title=title,project_number=number,stage=stage,publication_date=day,publication_quote=pub,deadline='2026-09-07 15:30:00',deadline_quote=deadline,quantity=2,unit='台',source_id=sid,quote=quote)])
        result=save_snapshot(jid,snapshot,{sid},[name]);assert result['rejected']==[],result
    with Session() as db:
        projects=list(db.scalars(select(ProcurementProject).where(ProcurementProject.buyer_id==cid)))
        assert len(projects)==1
        project=projects[0];assert project.stage=='已成交' and project.deadline=='2026-09-07 15:30:00'
        notices=list(db.scalars(select(ProcurementNotice).where(ProcurementNotice.project_id==project.id)))
        assert len(notices)==2 and len(next(n for n in notices if n.notice_type=='已成交').source_ids)==2
        assert len(project.source_ids)==3
    snapshot.projects[0].publication_date='2026-02-30'
    result=save_snapshot(jid,snapshot,{sid},[name]);assert any('日期' in r for r in result['rejected'])


def test_online_amount_unit_and_currency_cannot_be_invented(client):
    """实际保存拒绝金额倍率/币种/数字子串错误，正确原单位可入库；全部为隔离夹具。"""
    from app.db import Session, Conversation, Job, Evidence
    from app.company_research_schemas import CompanySnapshot, ResearchRelation, ResearchFact
    from app.company_validation import save_snapshot
    from app.company_models import CompanyFact, CompanyRelation
    suffix=uuid.uuid4().hex;name='单位验证'+suffix+'有限公司';counterparty='供应商'+suffix+'有限公司'
    finance=f'2025年{name}公司及控股子公司营业收入100万元人民币。'
    relation=f'2025年采购供应商{counterparty}100万元人民币，占比4.83%。'
    body=f'企业名称：{name}。'+finance+relation+('明确标识自动校验材料，不是真实企业数据。'*20)
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,client_token=suffix,prompt='查询'+name,query_mode='company_query');db.add(job);db.flush()
        source=Evidence(url='https://example.com/'+suffix,title=name,kind='网页正文',body=body,job_id=job.id);db.add(source);db.flush();jid=job.id;sid=source.id
    for unit,currency,amount,share in [('元','CNY','100',4.83),('万元','USD','100',4.83),('万元','CNY','10',4.83),('万元','CNY','100',4.8)]:
        snapshot=CompanySnapshot(name=name,source_id=sid,identity_quote='企业名称：'+name+'。',relations=[ResearchRelation(counterparty_name=counterparty,relation_type='supplier',report_period='2025',amount=amount,unit=unit,currency=currency,share=share,source_id=sid,quote=relation)])
        result=save_snapshot(jid,snapshot,{sid},[name]);assert result['accepted_fields']==0 and result['rejected'],result
    fact=ResearchFact(field='revenue',label='营业收入',value='100',unit='元',report_period='2025',scope='公司及控股子公司',source_id=sid,quote=finance,metadata_quote=finance)
    snapshot=CompanySnapshot(name=name,source_id=sid,identity_quote='企业名称：'+name+'。',facts=[fact])
    assert save_snapshot(jid,snapshot,{sid},[name])['accepted_fields']==0
    fact.unit='万元';snapshot.facts=[fact]
    snapshot.relations=[ResearchRelation(counterparty_name=counterparty,relation_type='supplier',report_period='2025',amount='100',unit='万元',currency='CNY',share=4.83,source_id=sid,quote=relation)]
    result=save_snapshot(jid,snapshot,{sid},[name]);assert result['accepted_fields']==2,result
    with Session() as db:
        assert db.scalar(select(CompanyFact).where(CompanyFact.company_id==result['company_id'],CompanyFact.field=='revenue')).raw_unit=='万元'
        row=db.scalar(select(CompanyRelation).where(CompanyRelation.company_id==result['company_id']));assert row.currency=='CNY' and row.unit=='万元'


def test_award_notice_date_enrichment_does_not_create_another_event(client):
    """同URL成交公告首次日期缺失、后续日期有证据时补日期/来源而不新增公告。"""
    from app.db import Session, Conversation, Job, Evidence
    from app.company_research_schemas import CompanySnapshot, ResearchProject
    from app.company_validation import save_snapshot
    from app.company_models import ProcurementNotice
    suffix=uuid.uuid4().hex;name='公告日期补全'+suffix+'有限公司';url='https://example.com/'+suffix
    quote=f'分析仪采购成交公告。采购人：{name}。项目编号：{suffix}。发布日期：2026年10月1日。'
    for index in range(2):
        with Session.begin() as db:
            conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,client_token=uuid.uuid4().hex,prompt='研究'+name,query_mode='company_query');db.add(job);db.flush()
            source=Evidence(url=url,title='分析仪采购成交公告',body=quote+('隔离公告事件测试材料。'*20),kind='网页正文',job_id=job.id);db.add(source);db.flush();jid=job.id;sid=source.id
        project=ResearchProject(buyer_name=name,title='分析仪采购成交公告',project_number=suffix,stage='awarded',source_id=sid,quote=quote,publication_date='2026-10-01' if index else '',publication_quote='发布日期：2026年10月1日。')
        snapshot=CompanySnapshot(name=name,source_id=sid,identity_quote='采购人：'+name+'。',projects=[project])
        result=save_snapshot(jid,snapshot,{sid},[name]);assert result['rejected']==[]
    with Session() as db:
        notices=list(db.scalars(select(ProcurementNotice).where(ProcurementNotice.title=='分析仪采购成交公告')))
        # 本用例的项目按UUID区分，避免其他同标题夹具影响统计。
        from app.company_models import ProcurementProject
        pid=db.scalar(select(ProcurementProject.id).where(ProcurementProject.project_number==suffix))
        notices=[n for n in notices if n.project_id==pid];assert len(notices)==1
        assert notices[0].published_at=='2026-10-01' and len(notices[0].source_ids)==2


def test_company_recovery_time_counts_against_graph_budget(client,monkeypatch):
    """保留run_job计时与异常终态，模拟慢恢复及后续节点，恢复不能获得第二份时间预算。"""
    from app import agent
    from app.db import Session, Job
    options={'enabled_channels':['official'],'max_leads':2,'max_reads':2,'max_searches':1,'max_seconds':0.8,'max_model_calls':8,'max_model_tokens':10000}
    conv=client.post('/api/conversations').json()
    job=client.post('/api/conversations/'+conv['id']+'/messages',json={'content':'研究时间验证有限公司','client_token':uuid.uuid4().hex,'query_mode':'company_query'}).json()
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    class Graph:
        """仅替节点耗时，不请求模型或网页；验证生产run_job恢复时间预算。"""
        async def aget_state(self,config):
            return SimpleNamespace(values={'job_id':job['id'],'schema_version':agent.GRAPH_VERSION,'intent':'company_query','options':options,'warnings':[]},next=('company_answer',))
        async def aupdate_state(self,*args,**kwargs): pass
        async def ainvoke(self,*args,**kwargs):
            await asyncio.sleep(0.4)
            return {'intent':'company_query','answer':'预算夹具','company_ids':[]}
    async def recover(state):
        await asyncio.sleep(0.6)
        return {}
    monkeypatch.setattr(agent,'settings',lambda:options)
    monkeypatch.setattr(agent,'build_graph',lambda saver:Graph())
    monkeypatch.setattr(agent,'recover_tools',recover)
    asyncio.run(agent.run_job(job['id']))
    with Session() as db:
        row=db.get(Job,job['id']);assert row.status=='failed' and row.error=='TimeoutError'
