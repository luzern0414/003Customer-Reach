"""模型预算触顶不应只给通用重试文案；实际图终止仍输出账本事实，不请求更多模型。"""
import asyncio
import uuid


def test_budget_stop_generates_truthful_empty_answer_and_sse(client,monkeypatch):
    """真实StateGraph/checkpoint/finish链，在本地注入确定预算异常；不把夹具当外部模型或客户验收。"""
    from app import agent
    from app.db import Session,Conversation,Job,Message,ToolCall,JobEvent,identifier
    from app.service import submit,save_settings,ServiceError
    from sqlalchemy import select
    save_settings({'enabled_channels':['official'],'max_leads':1,'max_seconds':120})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离预算答复'))
    job=submit(conv,{'content':'找深圳灯具经销商 '+uuid.uuid4().hex,'attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:
        db.get(Job,job['id']).status='running'
        db.add(ToolCall(job_id=job['id'],operation_id=uuid.uuid4().hex,tool='fetch_source',channel='official',status='completed',
            arguments={'url':'https://example.org/'},result={'sources':[{'id':'fixture','title':'未核验公司','url':'https://example.org/','kind':'网页正文','body':'隔离预算测试的真实形状网页内容，尚未通过主体校验。'}]}))
    async def stop(state):raise ServiceError('任务模型预算已耗尽')
    def forbidden():raise AssertionError('预算触顶后不得请求回答模型')
    monkeypatch.setattr(agent,'profile_node',stop);monkeypatch.setattr(agent,'model',forbidden)
    asyncio.run(agent.run_job(job['id']))
    with Session() as db:
        row=db.get(Job,job['id']);message=db.get(Message,row.reply_message_id)
        events=list(db.scalars(select(JobEvent).where(JobEvent.job_id==job['id']).order_by(JobEvent.id)))
        assert row.status=='failed' and row.error=='ServiceError' and not row.lead_ids
        assert row.metrics['answer_mode']=='budget_summary' and row.metrics['budget_exhausted']
        assert '预算上限' in message.content and '尚无通过完整校验' in message.content
        assert '未核验公司' not in message.content
        assert '已读取：example.org' in message.content
        assert [item.event_type for item in events][-4:]==['message.reset','message.delta','message.completed','run.failed']
