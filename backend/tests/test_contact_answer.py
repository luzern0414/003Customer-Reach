"""最终联系人交付校验；模型替身仅核验SSE替换协议，真实模型另用隔离任务复核。"""
import asyncio
import uuid
import pytest
from types import SimpleNamespace
from app.answer_summary import contact_answer_missing,saved_summary


def lead():
    """返回虚构隔离联系人，不作公开客户或真实网页证据。"""
    return {'display_name':'隔离测试商户','facts':{'phone':{'value':'13500001111'},'contact_name':{'value':'隔离联系人'}},'evidence':[]}


def test_required_contacts_and_narrow_questions():
    row=lead()
    assert contact_answer_missing([row],'只找到邮箱信息','补查公开联系方式')
    assert not contact_answer_missing([row],saved_summary([row]),'补查公开联系方式')
    for prompt in ['为什么没找到邮箱','复核原文联系方式','比较候选','查询采集时间','你好']:
        assert not contact_answer_missing([row],'回答当前问题',prompt)
    for status in ['disputed','inactive']:
        row['facts']['phone']['verification']=status
        assert not contact_answer_missing([row],'电话待核','补查公开联系方式')
        assert '13500001111' not in saved_summary([row])
    row['facts']['phone']={'value':'23493726'}
    assert not contact_answer_missing([row],'电话待核','补查公开联系方式')
    assert '23493726' not in saved_summary([row])


@pytest.mark.parametrize('mixed,sites',[(False,1),(False,2),(True,2)])
def test_answer_replaces_incomplete_stream_and_persists_final(client,monkeypatch,mixed,sites):
    """真实保存和SSE账本验证漏电话草稿被新generation替换；参数client隔离库、monkeypatch模型替身不联网。"""
    from app import agent
    from app.db import Session,Job,JobEvent,Message,Conversation,ToolCall,identifier
    from app.gateway import archive_sources
    from app.service import submit,save_settings
    from test_public_account_parser import source
    options=save_settings({'enabled_channels':['industry_directory'],'max_leads':1})
    conversation=identifier()
    with Session.begin() as db:db.add(Conversation(id=conversation,title='隔离回答完整性'))
    job=submit(conversation,{'content':'补查公开联系方式','attachment_ids':[],'client_token':uuid.uuid4().hex})
    rows=archive_sources(job['id'],[source()],'网页正文','industry_directory')
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    state={'job_id':job['id'],'conversation_id':conversation,'intent':'research','profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'prompt':'补查深圳隔离解析商行的公开联系方式'+('，至少两家不同网站核验' if sites==2 else ''),'options':options,'plan':{'target_roles':['dealer']},'cursor':0,
        'source_ids':[rows[0]['id']],'saved_ids':[],'warnings':[]}
    parsed=asyncio.run(agent.extract_node(state));saved=asyncio.run(agent.save_node({**state,**parsed}))
    if mixed:
        with Session.begin() as db:
            db.add(ToolCall(job_id=job['id'],operation_id=uuid.uuid4().hex,tool='fetch_source',channel='industry_directory',status='unavailable',arguments={},result={'error':'empty_body'}))
            db.add(ToolCall(job_id=job['id'],operation_id=uuid.uuid4().hex,tool='fetch_source',channel='industry_directory',status='completed',arguments={},result={'sources':rows}))
    calls=[]
    class Model:
        """只模拟遗漏回答；不模拟外部客户获取成功。"""
        async def astream(self,messages):
            """messages为真实节点提示；记录一次流请求并返回漏电话草稿，无异常。"""
            calls.append(messages)
            yield SimpleNamespace(content='未取得正文，邮箱待核。')
    monkeypatch.setattr(agent,'model',lambda:Model())
    output=asyncio.run(agent.answer_node({**state,**saved}))
    assert output['metrics']['answer_mode']==('verified_process_summary' if mixed else 'verified_corroboration_summary' if sites==2 else 'verified_contact_summary') and len(calls)==(0 if sites==2 else 1)
    if mixed:assert '已取得正文，部分页面读取未成功' in output['answer']
    assert '86 0755 23493726' in output['answer'] and '未取得正文' not in output['answer']
    if sites==2:
        assert '仍有1条线索未达到每条至少2个网站的核验要求' in output['answer']
        assert '1个网站' in output['answer']
    with Session() as db:
        events=list(db.query(JobEvent).filter(JobEvent.job_id==job['id']).order_by(JobEvent.id))
        assert [e.event_type for e in events[-3:]]==['message.reset','message.delta','message.completed']
        generation=events[-3].payload['generation_id']
        assert all(e.payload['generation_id']==generation for e in events[-3:])
        stored=db.get(Job,job['id'])
        assert stored.generation_id==generation and db.get(Message,stored.reply_message_id).content==output['answer']


def test_each_account_site_count_is_preserved_in_summary():
    """无参数；跨站与单站混合名单分别计数，不把一个客户的缺口套给全部客户。"""
    a=lead();a['evidence']=[{'url':'https://example.org/'},{'url':'https://example.net/'},{'url':'https://example.com/'}]
    b={**lead(),'display_name':'隔离另一商户','evidence':[{'url':'https://example.org/branch'}]}
    result=saved_summary([a,b],2)
    assert '3个网站' in result and '1个网站' in result
    assert '仍有1条线索未达到' in result
