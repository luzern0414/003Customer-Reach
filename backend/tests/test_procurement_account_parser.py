"""标准采购公告走原 Agent 工具与保存门禁；合成资料不冒称真实检索。"""
import asyncio
import uuid
import pytest


def source():
    return {'id':'s','url':'https://www.ggzy.gov.cn/information/synthetic.html',
        'title':'隔离学校教学虚拟仿真软件开发服务竞争性磋商公告',
        'kind':'网页正文','channel':'procurement','captured_at':'2026-10-13 00:00:00',
        'source_meta':{'origin':'bidresearch_mcp','detail_status':'public'},
        'body':'隔离学校教学虚拟仿真软件开发服务竞争性磋商公告\n'
            '项目编号：TEST-001\n项目名称：教学虚拟仿真软件开发服务\n预算金额（元）：1504100\n'
            '采购需求：开发教学虚拟仿真软件。\n提交响应文件截止时间：2099年10月16日 09:30（北京时间）\n'
            '1.采购人信息\n名 称：隔离学校\n地 址：吉林省辽源市东丰县测试街96号\n联系方式：0437-6318701\n'
            '2.采购代理机构信息\n名 称：隔离代理有限公司\n联系方式：0437-9999999\n'
            '3.项目联系方式\n项目联系人：代理联系人\n电话：0437-8888888'}


def test_model_connection_failure_keeps_native_candidates_for_save(client,monkeypatch):
    from app import agent
    from app.gateway import archive_sources
    from app.db import Session,Job,Lead
    from app.service import save_settings
    from app.service import ServiceError
    options=save_settings({'enabled_channels':['procurement'],'max_leads':1})
    with Session.begin() as db:
        job=Job(prompt='寻找全国软件开发采购方',status='running');db.add(job);db.flush();jid=job.id
    rows=archive_sources(jid,[source(),{'url':'https://www.ggzy.gov.cn/other',
        'title':'软件开发采购公告','body':'软件开发采购项目，实际采购人信息需要继续分析。'}],'网页正文','procurement')
    async def unavailable(*args,**kwargs):raise ServiceError('模型连接失败：OpenAIConnectionError',502)
    monkeypatch.setattr(agent,'cached_model',unavailable)
    state={'job_id':jid,'profile':{'region':'全国','products':[{'name':'软件开发服务'}]},
        'prompt':'寻找全国软件开发采购方','options':options,'plan':{'target_roles':['project_buyer']},
        'source_ids':[r['id'] for r in rows],'recent_read_source_ids':[r['id'] for r in rows],
        'saved_ids':[],'cursor':0}
    parsed=asyncio.run(agent.extract_node(state))
    assert len(parsed['candidates'])==1 and 'extract_model_unavailable' in parsed['warnings']
    saved=asyncio.run(agent.save_node({**state,**parsed}))
    with Session() as db:assert db.get(Lead,saved['saved_ids'][0]).display_name=='隔离学校'
    assert parsed['extract_pending_source_ids']==[rows[1]['id']]
    from app.schemas import CandidateBatch
    async def recovered(*args,**kwargs):return CandidateBatch(candidates=[],missing_fields=['buyer_role'])
    monkeypatch.setattr(agent,'cached_model',recovered)
    retried=asyncio.run(agent.extract_node({**state,**parsed,**saved,'recent_read_source_ids':[rows[1]['id']]}))
    assert retried['extract_pending_source_ids']==[]
    assert 'extract_model_unavailable' not in retried['warnings']


@pytest.mark.parametrize('legacy',[False,True])
def test_terminal_resume_reanalyzes_pending_sources_without_network(client,monkeypatch,tmp_path,legacy):
    """真实持久图恢复已到END的降级任务，优先旧失败正文而非新recent；不重置预算或发网络。"""
    from app import agent
    from app.db import Session,Job
    from app.gateway import archive_sources
    from app.service import save_settings,resume_task
    from app.schemas import CandidateBatch
    from app.research_tools import ToolBroker
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    options=save_settings({'enabled_channels':['procurement'],'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    jid=client.post('/api/conversations/'+conv+'/messages',json={
        'content':'寻找全国软件开发采购方','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:
        job=db.get(Job,jid);job.status='partial';job.elapsed_ms=12000
    rows=archive_sources(jid,[{'url':'https://www.ggzy.gov.cn/pending','title':'待核验页',
        'body':'原失败正文：软件采购公告需要核验主体。'},
        {'url':'https://www.ggzy.gov.cn/later','title':'后读页','body':'另一页已读资料。'}],'网页正文','procurement')
    state={'schema_version':agent.GRAPH_VERSION,'job_id':jid,'conversation_id':conv,'intent':'research',
        'prompt':'寻找全国软件开发采购方','options':options,'profile':{'region':'全国','products':[{'name':'软件开发'}],'questions':[]},
        'plan':{'target_roles':['project_buyer']},'steps':[],'cursor':0,'saved_ids':[],'company_ids':[],
        'source_ids':[r['id'] for r in rows],'recent_read_source_ids':[rows[1]['id']],
        'read_empty':True,'warnings':['extract_model_unavailable'],'attempts':[]}
    if not legacy:state['extract_pending_source_ids']=[rows[0]['id']]
    else:state['recent_read_source_ids']=[rows[0]['id']]
    monkeypatch.setattr(agent,'DATA',tmp_path)
    analyzed=[]
    async def model(state,schema,prompt,label):
        analyzed.append(prompt)
        return CandidateBatch(candidates=[],missing_fields=['buyer_role'])
    async def noop(state):return {}
    async def gap(state):return {'cursor':0,'direct_read_pending':False}
    async def answer(state):return {'answer':'未核验到合格买方。'}
    async def forbidden(*args,**kwargs):raise AssertionError('恢复正文分析不得重新请求外部工具')
    monkeypatch.setattr(agent,'cached_model',model)
    monkeypatch.setattr(agent,'gap_node',gap)
    monkeypatch.setattr(agent,'answer_node',answer)
    monkeypatch.setattr(agent,'learn_node',noop)
    monkeypatch.setattr(ToolBroker,'execute',forbidden)
    config={'configurable':{'thread_id':jid}}
    async def exercise():
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path/'checkpoints.db')) as saver:
            await saver.setup()
            graph=agent.build_graph(saver)
            await graph.aupdate_state(config,state,as_node='learn')
        resume_task(jid)
        await agent.run_job(jid)
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path/'checkpoints.db')) as saver:
            return (await agent.build_graph(saver).aget_state(config)).values
    final=asyncio.run(exercise())
    assert analyzed and '原失败正文' in analyzed[0] and '另一页已读资料' not in analyzed[0]
    assert not final['extract_pending_source_ids'] and 'extract_model_unavailable' not in final['warnings']
    with Session() as db:assert db.get(Job,jid).elapsed_ms>=12000


def test_unrelated_success_does_not_clear_pending_extraction(client,monkeypatch):
    """只有同一失败来源分析成功才消除标记，不以别页成功掩盖未完成资料。"""
    from app import agent
    from app.db import Session,Job
    from app.gateway import archive_sources
    from app.service import save_settings
    from app.schemas import CandidateBatch
    with Session.begin() as db:
        job=Job(prompt='软件采购',status='running');db.add(job);db.flush();jid=job.id
    rows=archive_sources(jid,[{'url':'https://www.ggzy.gov.cn/unrelated','title':'其他页','body':'其他软件采购资料待分析。'}],'网页正文','procurement')
    async def model(*args,**kwargs):return CandidateBatch(candidates=[])
    monkeypatch.setattr(agent,'cached_model',model)
    state={'job_id':jid,'source_ids':[rows[0]['id']],'recent_read_source_ids':[rows[0]['id']],
        'extract_pending_source_ids':['older-source'],'warnings':['extract_model_unavailable'],
        'profile':{'region':'全国','products':[{'name':'软件开发'}]},'prompt':'软件采购',
        'options':save_settings({'enabled_channels':['procurement'],'max_leads':1}),
        'plan':{'target_roles':['project_buyer']},'cursor':0,'saved_ids':[]}
    result=asyncio.run(agent.extract_node(state))
    assert result['extract_pending_source_ids']==['older-source']
    assert 'extract_model_unavailable' in result['warnings']


def test_spaced_buyer_label_preserves_subject_boundary():
    from app.evidence_role import scoped_role
    row=source();quote='采购人信息\n名 称：隔离学校'
    assert scoped_role('隔离学校','采购人',quote,row['title'],True,row['body'])
    for invalid in ['采购人信息\n名 称：隔离学校分校',
        '采购人信息\n名 称：另一个学校\n代理机构名称：隔离学校',
        '采购代理机构信息\n名 称：隔离学校']:
        assert not scoped_role('隔离学校','采购人',invalid,'公告',True,invalid)


def test_application_read_of_discovered_procurement_page_uses_same_native_parser():
    from app.public_accounts import parse_accounts
    row={**source(),'source_meta':{}}
    assert len(parse_accounts(row,'全国',[{'name':'软件开发服务'}],['project_buyer']))==1
    assert not parse_accounts({**row,'kind':'搜索摘录'},'全国',[{'name':'软件开发服务'}],['project_buyer'])
    assert not parse_accounts({**row,'url':'https://unregistered.example.com/p'},'全国',[{'name':'软件开发服务'}],['project_buyer'])


def test_native_procurement_candidate_keeps_exact_fields_and_buyer_contact(client):
    from app.public_accounts import parse_accounts,supports_template
    from app.service import checked_candidate
    row=source()
    assert supports_template(row)
    candidates=parse_accounts(row,'全国',[{'name':'软件开发服务'}],['project_buyer'])
    assert len(candidates)==1
    candidate=candidates[0];clean,_=checked_candidate(candidate,{'s':row})
    assert candidate.display_name=='隔离学校' and candidate.city==''
    assert clean['phone']['value']=='0437-6318701'
    assert clean['address']['value']=='吉林省辽源市东丰县测试街96号'
    assert 'contact_name' not in clean
    assert candidate.procurement_signal.deadline=='2099-10-16 09:30:00'
    assert all(fact.quote in row['body'] and fact.value in fact.quote for fact in candidate.facts)
    assert '预算金额（元）：1504100' in clean['procurement']['value']
    assert not supports_template({**row,'kind':'搜索摘录'})
    assert not parse_accounts(row,'深圳',[{'name':'软件开发服务'}],['project_buyer'])
    assert not parse_accounts(row,'全国',[{'name':'灯具'}],['project_buyer'])
    assert not parse_accounts(row,'全国',[{'name':'软件开发服务'}],['dealer'])


def test_agent_procurement_native_parse_and_signal_pass_original_persist(client,monkeypatch):
    from app import agent
    from app.db import Session,Job,ToolCall,Lead
    from app.gateway import archive_sources
    from app.service import save_settings
    options=save_settings({'enabled_channels':['procurement'],'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    jid=client.post('/api/conversations/'+conv+'/messages',json={
        'content':'寻找全国软件开发采购方','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,jid).status='running'
    row=archive_sources(jid,[source()],'网页正文','procurement')[0]
    async def forbidden(*args,**kwargs):raise AssertionError('标准已读采购公告无需模型重写')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    state={'job_id':jid,'profile':{'region':'全国','products':[{'name':'软件开发服务'}]},
        'prompt':'寻找全国软件开发采购方','options':options,'plan':{'target_roles':['project_buyer']},
        'source_ids':[row['id']],'recent_read_source_ids':[row['id']],'saved_ids':[],'cursor':0}
    parsed=asyncio.run(agent.extract_node(state))
    saved=asyncio.run(agent.save_node({**state,**parsed}))
    assert len(saved['saved_ids'])==1
    with Session() as db:
        lead=db.get(Lead,saved['saved_ids'][0])
        assert lead.qualification['signal_score']==10
        assert lead.facts['phone']['value']=='0437-6318701'
        assert db.query(ToolCall).filter_by(job_id=jid,tool='parse_account').one().status=='completed'
    # Re-analysis/re-save uses the same ledger operations and never adds a duplicate customer.
    again=asyncio.run(agent.save_node({**state,**parsed}))
    assert again['saved_ids']==saved['saved_ids']


def test_verified_fallback_answer_keeps_procurement_details(client):
    from app.answer_summary import saved_summary
    from app.db import serialize,Session,Lead,Job,Conversation
    from app.public_accounts import parse_accounts
    from app.service import save_candidate
    row=source();candidate=parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0]
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='查软件开发',client_token=uuid.uuid4().hex)
        db.add(j);db.flush();jid=j.id
    receipt=save_candidate(candidate,{'s':row},jid)
    with Session() as db:lead=serialize(db.get(Lead,receipt['id']))
    answer=saved_summary([lead])
    for value in ('教学虚拟仿真软件开发服务','TEST-001','1504100','2099-10-16 09:30:00',row['url']):
        assert value in answer


@pytest.mark.parametrize('irrelevant',[
    '投标保证金递交截止时间：2099年10月10日 17:00',
    '获取采购文件截止时间：2099年10月10日 17:00',
    '投标报名截止时间：2099年10月10日 17:00'])
def test_submission_deadline_is_not_replaced_by_other_deadlines(irrelevant):
    from app.public_accounts import parse_accounts
    row=source();row['body']=row['body'].replace('提交响应文件截止时间：',irrelevant+'\n提交响应文件截止时间：')
    candidate=parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0]
    assert candidate.procurement_signal.deadline=='2099-10-16 09:30:00'
    row['body']=row['body'].replace('提交响应文件截止时间：2099年10月16日 09:30（北京时间）\n','')
    assert parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0].procurement_signal.deadline==''


def test_ambiguous_submission_times_remain_unknown_and_section_label_is_supported():
    from app.public_accounts import parse_accounts
    row=source();row['body']=row['body'].replace('提交响应文件截止时间：','四、响应文件提交\n截止时间：')
    assert parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0].procurement_signal.deadline=='2099-10-16 09:30:00'
    row['body']=row['body'].replace('1.采购人信息','投标截止时间：2099年10月20日 09:30\n1.采购人信息')
    assert parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0].procurement_signal.deadline==''


def test_paused_procurement_cannot_gain_open_signal_score(client):
    from app.public_accounts import parse_accounts
    from app.service import save_candidate
    from app.db import Session,Lead,Job,Conversation
    row=source();row['title']='软件开发采购暂停公告'
    row['body']=row['body'].replace('项目编号：TEST-001','本项目暂停采购，恢复时间另行通知。\n项目编号：TEST-001')
    candidate=parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0]
    assert candidate.procurement_signal.stage=='closed'
    candidate.procurement_signal.stage='open'  # Even a mistaken model proposal cannot bypass the service check.
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='查软件开发',client_token=uuid.uuid4().hex)
        db.add(j);db.flush();jid=j.id
    receipt=save_candidate(candidate,{'s':row},jid)
    with Session() as db:assert db.get(Lead,receipt['id']).qualification['signal_score']==0


@pytest.mark.parametrize('empty_name',['名 称：\n',''])
def test_missing_buyer_name_never_saves_section_word_as_customer(empty_name):
    from app.public_accounts import parse_accounts
    from app.evidence_role import buyer_identity
    row=source();row['body']=row['body'].replace('名 称：隔离学校\n',empty_name)
    assert not parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])
    assert not buyer_identity('信息','采购人信息')


def test_delivery_address_cannot_authorize_buyers_city():
    from app.public_accounts import parse_accounts
    row=source();row['body']=row['body'].replace('地 址：吉林省辽源市东丰县测试街96号',
        '送货地址：深圳市南山区测试街96号\n地 址：北京市海淀区测试街1号')
    assert not parse_accounts(row,'深圳',[{'name':'软件开发'}],['project_buyer'])
    candidate=parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0]
    assert next(f.value for f in candidate.facts if f.field=='address')=='北京市海淀区测试街1号'


@pytest.mark.parametrize('boilerplate',['代理服务费由中标人支付。','本项目若出现废标，采购人将重新组织采购。',
    '若本项目终止，已缴纳投标保证金将予退还。','如本项目取消，采购人将通知所有投标人。'])
def test_open_notice_stays_open_when_it_mentions_future_award_or_failure(boilerplate):
    from app.public_accounts import parse_accounts
    row=source();row['body']=row['body'].replace('1.采购人信息',boilerplate+'\n1.采购人信息')
    assert parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0].procurement_signal.stage=='open'


def test_explicit_active_request_does_not_save_unknown_or_awarded_opportunities(client):
    from app.research_tools import ToolBroker
    from app.public_accounts import parse_accounts
    from app.gateway import archive_sources
    from app.service import save_settings
    from app.db import Session,Job,Conversation
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='找正在采购的软件开发买方',client_token=uuid.uuid4().hex)
        db.add(j);db.flush();jid=j.id
    row=archive_sources(jid,[source()],'网页正文','procurement')[0]
    candidate=parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0]
    broker=ToolBroker(jid,save_settings({'enabled_channels':['procurement'],'max_leads':1}),{'products':[{'name':'软件开发'}]})
    for signal in [None,candidate.procurement_signal.model_copy(update={'stage':'awarded'})]:
        rejected=candidate.model_copy(update={'procurement_signal':signal})
        result=asyncio.run(broker.execute('persist_lead',{'candidate':rejected.model_dump()}))
        assert result['error']=='尚未核验到正在开放的软件或服务采购机会'
    assert not asyncio.run(broker.execute('persist_lead',{'candidate':candidate.model_dump()})).get('error')


@pytest.mark.parametrize('mistake',['deposit','paused','wrong_role'])
def test_active_persist_checks_original_submission_deadline_and_status(client,mistake):
    from app.research_tools import ToolBroker
    from app.public_accounts import parse_accounts
    from app.gateway import archive_sources
    from app.service import save_settings
    from app.db import Session,Job,Conversation
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush()
        job=Job(conversation_id=conv.id,prompt='寻找正在采购的软件开发买方',client_token=uuid.uuid4().hex)
        db.add(job);db.flush();jid=job.id
    original=source()
    if mistake=='deposit':original['body']=original['body'].replace('提交响应文件截止时间：','投标保证金递交截止时间：')
    if mistake=='paused':original['body']=original['body'].replace('项目编号：','本项目已暂停采购。\n项目编号：')
    row=archive_sources(jid,[original],'网页正文','procurement')[0]
    candidate=parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0]
    candidate.procurement_signal.stage='open'
    candidate.procurement_signal.deadline='2099-10-16 09:30:00'
    candidate.procurement_signal.deadline_quote=next(line for line in row['body'].splitlines() if '截止时间' in line)
    if mistake=='wrong_role':candidate.procurement_signal.participant_role='supplier'
    broker=ToolBroker(jid,save_settings({'enabled_channels':['procurement'],'max_leads':1}),{'products':[{'name':'软件开发'}]})
    result=asyncio.run(broker.execute('persist_lead',{'candidate':candidate.model_dump()}))
    assert result.get('error')=='尚未核验到正在开放的软件或服务采购机会'
    with Session() as db:assert not db.get(Job,jid).lead_ids


def test_model_deposit_deadline_cannot_gain_open_score_in_historical_research(client):
    from app.public_accounts import parse_accounts
    from app.service import save_candidate
    from app.db import Session,Lead,Job,Conversation
    row=source();row['body']=row['body'].replace('提交响应文件截止时间：','投标保证金递交截止时间：')
    candidate=parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0]
    candidate.procurement_signal.stage='open';candidate.procurement_signal.deadline='2099-10-16 09:30:00'
    candidate.procurement_signal.deadline_quote=next(line for line in row['body'].splitlines() if '截止时间' in line)
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt='研究软件开发买方历史',client_token=uuid.uuid4().hex)
        db.add(job);db.flush();jid=job.id
    receipt=save_candidate(candidate,{'s':row},jid)
    with Session() as db:assert db.get(Lead,receipt['id']).qualification['signal_score']==0


@pytest.mark.parametrize('quote',['采购人：隔离学校。软件采购，提交截止：2099-10-16 09:30:00。',
    '投标截止：2099年10月16日09：30'])
def test_submission_deadline_accepts_explicit_inline_submission(quote):
    from app.procurement_accounts import submission_deadline
    assert submission_deadline(quote)[0]=='2099-10-16 09:30:00'


def test_distinct_procurement_projects_of_one_buyer_coexist_without_false_conflict(client):
    from app.public_accounts import parse_accounts
    from app.gateway import archive_sources
    from app.service import save_candidate
    from app.db import Session,Lead,Job,Conversation
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt='查软件开发采购',client_token=uuid.uuid4().hex)
        db.add(job);db.flush();jid=job.id
    receipts=[];buyer='并存学校'+uuid.uuid4().hex[:8]
    from app.knowledge import upsert_knowledge
    from app.db import Knowledge
    from sqlalchemy import select
    for number in ['P001','P002']:
        original=source();original['url']=original['url']+'?project='+number
        original['body']=original['body'].replace('TEST-001',number).replace('隔离学校',buyer)
        row=archive_sources(jid,[original],'网页正文','procurement')[0]
        candidate=parse_accounts(row,'全国',[{'name':'软件开发'}],['project_buyer'])[0]
        receipts.append(save_candidate(candidate,{row['id']:row},jid))
        upsert_knowledge(buyer,candidate.procurement_signal.quote,'public_fact',row['id'],row['url'],receipts[-1]['id'])
    assert receipts[0]['id']==receipts[1]['id']
    with Session() as db:
        lead=db.get(Lead,receipts[0]['id'])
        assert lead.facts['procurement']['verification']!='disputed'
        assert lead.qualification['signal_score']==10
        assert len(lead.qualification['procurement_signals'])==2
        assert {q['source_id'] for q in lead.qualification['procurement_signals']}=={e['source_id'] for e in lead.evidence if e['field']=='procurement'}
        assert {row.status for row in db.scalars(select(Knowledge).where(Knowledge.entity_id==lead.id))}=={'active'}
