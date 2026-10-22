"""已知商户模板的确定性解析及模型超时熔断；不使用模拟响应冒充真实网页验收。"""
import asyncio
import uuid
import pytest
from app.public_accounts import parse_account
from app.service import checked_candidate


def source():
    """返回隔离模板形状；字段原文校验仍由实际service执行。"""
    name='深圳隔离解析商行'
    return {'id':'fixture','url':'https://www.yunfale.com/company/detail/123/', 'title':name,'kind':'网页正文','channel':'industry_directory',
        'captured_at':'2026-10-03 00:00:00',
        'body':'平台客服电话4000000000\n主营：吊灯,LED灯具\n'+name+'位置在深圳某市场，专业从事灯具经营，经销批发灯具。\n联系人\n()\n电话86 0755 23493726 传真86 0755 23493726 地址深圳某市场\n公司规模5-10人'}


def test_parser_uses_exact_owned_contact_and_omits_unknown_facts(client):
    """未知统计时间/联系人/采购不补造，平台电话不借给主体；城市及模板不匹配返回None。"""
    row=source();candidate=parse_account(row,'深圳');assert candidate
    clean,_=checked_candidate(candidate,{row['id']:row})
    assert clean['phone']['value']=='86 0755 23493726'
    assert set(clean)=={'name','buyer_role','phone','address','categories'}
    assert not parse_account({**row,'kind':'搜索摘录'},'深圳')
    assert not parse_account({**row,'url':'https://example.org/company/detail/123/'},'深圳')
    assert not parse_account(row,'广州')
    assert not parse_account({**row,'body':row['body'].replace('经销批发','生产制造')},'深圳')
    assert not parse_account({**row,'body':row['body'].replace('联系人','网站服务联系人')},'深圳')


@pytest.mark.parametrize('event_type',['run.failed','extract.partial'])
def test_graph_template_tool_and_timeout_circuit_do_not_call_model(client,monkeypatch,event_type):
    """client隔离DB、monkeypatch禁模型、event_type为运行/提取SDK失败；三次账本错误触发真实确定性SSE。"""
    from app import agent
    from app.db import Session,Job,JobEvent,Conversation,identifier
    from app.service import submit,save_settings
    from app.gateway import archive_sources
    options=save_settings({'enabled_channels':['industry_directory'],'max_leads':1})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离解析与降级'))
    job=submit(conversation,{'content':'找深圳灯具经销商','attachment_ids':[],'client_token':uuid.uuid4().hex})
    row=source();sources=archive_sources(job['id'],[row],'网页正文','industry_directory')
    with Session.begin() as db:
        db.get(Job,job['id']).status='running'
        for _ in range(3):db.add(JobEvent(job_id=job['id'],event_type=event_type,payload={'error':'OpenAITimeoutError'}))
    async def forbidden(*args,**kwargs):
        """禁止网络模型替身：本用例只核验确定性路径，不能发生隐式模型调用。"""
        raise AssertionError('模型不应被调用')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    monkeypatch.setattr(agent,'model',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('模型不应被调用')))
    state={'job_id':job['id'],'conversation_id':conversation,'intent':'research','profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'prompt':'请核验深圳隔离解析商行','options':options,'plan':{'target_roles':['dealer']},'cursor':0,
        'source_ids':[sources[0]['id']],'saved_ids':[],'warnings':['extract_model_timeout'] if event_type=='extract.partial' else []}
    parsed=asyncio.run(agent.extract_node(state));assert len(parsed['candidates'])==1
    own=asyncio.run(agent.extract_node({**state,'profile':{**state['profile'],'company_name':'深圳隔离解析商行'}}))
    assert not own['candidates']
    saved=asyncio.run(agent.save_node({**state,**parsed}))
    answer=asyncio.run(agent.answer_node({**state,**parsed,**saved}))
    assert '深圳隔离解析商行' in answer['answer'] and answer['metrics']['model_circuit_open']
    assert answer['metrics']['model_timeout_count']==3
    if event_type=='extract.partial':assert '部分网页的资料分析超时' not in answer['answer']
    with Session() as db:assert db.query(JobEvent).filter(JobEvent.job_id==job['id'],JobEvent.event_type=='message.completed').count()==1
    from app.agent import finish
    finish(job['id'],'partial',answer['answer'],'OpenAITimeoutError')
    with Session() as db:
        events=db.query(JobEvent).filter(JobEvent.job_id==job['id']).order_by(JobEvent.id).all()
        assert [event.event_type for event in events[-4:]]==['message.reset','message.delta','message.completed','run.partial']
        assert db.get(Job,job['id']).error=='OpenAITimeoutError'


def test_resume_keeps_recent_read_source_without_new_sources(client,monkeypatch):
    """恢复没有新来源时仍保留待提取正文优先ID，不因恢复清空而绕过模板解析。"""
    from app.agent import recover_tools
    from app.db import Session,Job,ToolCall
    from app.research_tools import ToolBroker
    key=uuid.uuid4().hex
    with Session.begin() as db:
        db.add(Job(id=key,prompt='隔离恢复',metrics={'resume_epoch':100.0}))
        db.add(ToolCall(job_id=key,operation_id=uuid.uuid4().hex,tool='search_accounts',status='rate_limited',last_attempt_epoch=1,
            arguments={'query':'隔离恢复','channel':'industry_directory'},result={'error':'provider_rate_limited'}))
    async def retry(self,name,args):
        """模拟失败重放没有新来源，仅核验恢复状态，不请求供应商。"""
        return {'error':'provider_rate_limited','sources':[]}
    monkeypatch.setattr(ToolBroker,'execute',retry)
    state={'job_id':key,'source_ids':['real-read-id'],'recent_read_source_ids':['real-read-id'],
        'warnings':[],'options':{'enabled_channels':['industry_directory']},'profile':{'region':'深圳'}}
    result=asyncio.run(recover_tools(state))
    assert result['recent_read_source_ids']==['real-read-id']


def test_budget_timeout_does_not_open_model_circuit(client,monkeypatch):
    """仅任务预算超时没有证据证明模型失败，不应该自动触发模型熔断。"""
    from app import agent
    from app.db import Session,Job,JobEvent
    key=uuid.uuid4().hex
    with Session.begin() as db:
        db.add(Job(id=key,conversation_id=uuid.uuid4().hex))
        for _ in range(3):db.add(JobEvent(job_id=key,event_type='run.partial',payload={'error':'TimeoutError'}))
    def normal_model():
        """零结果使用账本摘要，无需模型；误发请求直接令测试失败。"""
        raise AssertionError('empty-answer-must-not-call-model')
    monkeypatch.setattr(agent,'model',normal_model)
    result=asyncio.run(agent.answer_node({'job_id':key,'intent':'research','saved_ids':[],'profile':{'products':[]},'prompt':'隔离预算用例'}))
    assert result['metrics']['model_circuit_open'] is False
    assert result['metrics']['model_timeout_count']==0
    assert result['metrics']['answer_mode']=='verified_empty'


def test_parser_policy_change_rechecks_cached_template(client,monkeypatch):
    """解析政策升级不能被旧提取hash/工具缓存挡住；不重新发网络或重置任务预算。"""
    from app import agent,public_accounts
    from app.db import Session,Job,ToolCall
    from app.gateway import archive_sources
    key=uuid.uuid4().hex
    with Session.begin() as db:db.add(Job(id=key,prompt='隔离模板政策'))
    rows=archive_sources(key,[source()],'网页正文','industry_directory')
    state={'job_id':key,'saved_ids':[],'source_ids':[rows[0]['id']],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'prompt':'核验深圳隔离解析商行','options':{'max_leads':1,'enabled_channels':['industry_directory']},
        'cursor':0,'plan':{'target_roles':['dealer']}}
    first=asyncio.run(agent.extract_node(state));assert first['candidates']
    monkeypatch.setattr(public_accounts,'PARSER_POLICY',public_accounts.PARSER_POLICY+'-test')
    second=asyncio.run(agent.extract_node({**state,**first}));assert second['candidates']
    with Session() as db:assert db.query(ToolCall).filter(ToolCall.job_id==key,ToolCall.tool=='parse_account').count()==2
