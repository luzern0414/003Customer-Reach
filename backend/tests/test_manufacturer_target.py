"""尊重明确制造企业客群，不把成品灯经销场景改成厂家或把制造能力写成采购。"""
import asyncio
import uuid
from app.role_policy import manufacturer_target


def test_only_positive_factory_target_counts_not_seller_or_exclusion():
    """明确目标启用；卖方自述、厂家的经销商、排除制造及网页关键词都不启用。"""
    assert manufacturer_target('我卖电源，买家画像是深圳生产灯具的企业，只找生产企业')
    assert manufacturer_target('请找深圳生产LED灯具的公司')
    assert manufacturer_target('找灯具工厂')
    assert not manufacturer_target('我是灯具生产厂家，找经销商')
    assert not manufacturer_target('找灯具经销商，排除生产厂家')
    assert not manufacturer_target('找灯具厂家的经销商')
    assert not manufacturer_target('生产厂家可以组装电源')
    assert not manufacturer_target('我不想找灯具生产企业')
    assert not manufacturer_target('找灯具门店，厂家除外')
    assert manufacturer_target('目标客户是灯具工厂，不要把工厂当已采购客户')


def test_plan_corrects_model_ignoring_explicit_factory_and_does_not_enable_default(client,monkeypatch):
    """模型漏用户明确厂家目标时确定性补齐；普通经销要求下制造目标不能靠模型自行开放。"""
    from app import agent
    from app.schemas import ResearchPlan,ResearchStep
    async def planner(state,schema,prompt,label):
        """state/schema/prompt/label为实际规划入口，仅替模型输出、不联网。"""
        return ResearchPlan(target_roles=['manufacturer'],steps=[ResearchStep(channel='industry_directory',query='深圳灯具公司',purpose='隔离规划')])
    monkeypatch.setattr(agent,'cached_model',planner)
    base={'profile':{'region':'深圳','products':[{'name':'LED电源'}]},'options':{'enabled_channels':['industry_directory']}}
    result=asyncio.run(agent.plan_node({**base,'prompt':'只找深圳生产灯具的企业'}))
    assert 'manufacturer' in result['plan']['target_roles'] and 'manufacturer' not in result['plan']['excluded_roles']
    result=asyncio.run(agent.plan_node({**base,'prompt':'找深圳灯具经销商，排除生产厂家'}))
    assert 'manufacturer' not in result['plan']['target_roles']


def test_real_persistence_qualifies_factory_only_for_explicit_job_and_keeps_manual_contact_eligibility(client):
    """真实原文校验/持久保存按本任务目标；无实际采购不加意向，修改联系字段不丢原目标匹配。"""
    from app.db import Session,Conversation,Job,identifier,Lead
    from app.gateway import archive_sources
    from app.service import submit,save_candidate,edit_lead
    from app.schemas import Candidate,LeadInput
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离制造画像'))
    job=submit(conv,{'content':'找深圳生产灯具的企业','attachment_ids':[],'client_token':uuid.uuid4().hex})
    name='隔离制造目标'+uuid.uuid4().hex[:6]
    body=name+'在深圳隔离路1号生产灯具，电话13900000003。'
    source=archive_sources(job['id'],[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name,'body':body}],'网页正文','official')[0]
    candidate=Candidate(display_name=name,city='深圳',buyer_role='manufacturer',matched_products=[],match_reason='潜在配套用途，采购待核',
        facts=[{'field':field,'value':value,'quote':body,'source_id':source['id']} for field,value in
            [('name',name),('buyer_role','生产灯具'),('address','深圳隔离路1号'),('phone','13900000003'),('categories','灯具')]])
    result=save_candidate(candidate,{source['id']:source},job['id'])
    assert result['eligible']
    with Session() as db:assert db.get(Lead,result['id']).qualification['signal_score']==0
    updated=edit_lead(result['id'],LeadInput(phone='13900000004'))
    assert updated['qualification']['eligible'] and updated['qualification']['manufacturer_target']
    with Session.begin() as db:db.get(Job,job['id']).status='completed'
    other=submit(conv,{'content':'找深圳灯具经销商，排除生产厂家','attachment_ids':[],'client_token':uuid.uuid4().hex})
    second_name=name+'另'
    second_body=second_name+'在深圳隔离路2号生产灯具。'
    second=archive_sources(other['id'],[{'url':'https://example.org/'+uuid.uuid4().hex,'title':second_name,'body':second_body}],'网页正文','official')[0]
    c=Candidate(display_name=second_name,city='深圳',buyer_role='manufacturer',match_reason='隔离默认排除',
        facts=[{'field':field,'value':value,'quote':second_body,'source_id':second['id']} for field,value in [('name',second_name),('buyer_role','生产灯具')]])
    assert not save_candidate(c,{second['id']:second},other['id'])['eligible']


def test_save_omits_invalid_legal_representative_after_failed_repair_and_revalidates_rest(client,monkeypatch):
    """联系身份省略不降低姓名/角色/电话校验；原文真实企业电话可存，法人不被写成联系人。"""
    from app import agent
    from app.db import Session,Conversation,Job,Lead,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings
    from app.schemas import Candidate
    options=save_settings({'enabled_channels':['industry_directory'],'max_leads':1})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离字段级恢复'))
    job=submit(conv,{'content':'找深圳生产灯具的企业','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    name='隔离生产公司'+uuid.uuid4().hex[:6]
    body=name+'在深圳隔离路1号生产灯具，业务电话13900000003。法定代表人：隔离张先生。员工人数10人。'
    source=archive_sources(job['id'],[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name,'body':body}],'网页正文','industry_directory')[0]
    candidate=Candidate(display_name=name,city='深圳',buyer_role='manufacturer',match_reason='潜在配套用途，采购待核',
        facts=[{'field':field,'value':value,'quote':body,'source_id':source['id']} for field,value in
            [('name',name),('buyer_role','生产灯具'),('phone','13900000003'),('contact_name','隔离张先生'),('headcount','10人')]])
    async def repair(*args,**kwargs):
        """故意重复原错误，验证自动省略后的完整真实持久校验而非模型模拟成功。"""
        return candidate
    monkeypatch.setattr(agent,'cached_model',repair)
    state={'job_id':job['id'],'profile':{'region':'深圳','products':[{'name':'LED电源'}]},'options':options,
        'source_ids':[source['id']],'saved_ids':[],'candidates':[candidate.model_dump()],
        'plan':{'target_roles':['manufacturer']},'prompt':'找深圳生产灯具的企业','cursor':0}
    result=asyncio.run(agent.save_node(state))
    assert len(result['saved_ids'])==1 and 'contact_name' in result['gaps']
    with Session() as db:
        row=db.get(Lead,result['saved_ids'][0])
        assert row.facts['phone']['value']=='13900000003' and 'contact_name' not in row.facts and 'contact_position' not in row.facts
        assert 'headcount' not in row.facts
        assert row.qualification['eligible'] and row.qualification['signal_score']==0
