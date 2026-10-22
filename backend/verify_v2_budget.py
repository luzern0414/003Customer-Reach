"""真实6luna预算验收：一次结构化调用成功，第二次被持久预算阻止；不检索或生成客户。"""
import asyncio
from app import model_gateway
from app.db import Session, Conversation, Job, identifier
from app.model_gateway import task_budget, structured, ProbeResult
from app.service import ServiceError


async def main():
    """无参数；调用本机真实provider验证前置预算，失败抛断言，不输出任何凭证。"""
    with Session.begin() as db:
        conv=Conversation(title='模型预算自动验收');db.add(conv);db.flush()
        job=Job(conversation_id=conv.id,client_token=identifier(),prompt='预算探针，不研究客户',status='paused')
        db.add(job);db.flush();job_id=job.id
    with task_budget(job_id,{'max_model_calls':1,'max_model_tokens':12000}):
        result=await structured(ProbeResult,'返回answer=41。')
        assert result.answer==41
        try:await structured(ProbeResult,'返回answer=42。')
        except ServiceError as exc:assert '模型预算' in str(exc)
        else:raise AssertionError('模型调用超预算未被阻止')
    with Session.begin() as db:
        row=db.get(Job,job_id);assert row.metrics['model_budget']['calls']==1
        row.status='completed'
        print({'job_id':job_id,'real_model':'gpt-6-luna','structured':True,'second_call_blocked':True,'budget':row.metrics['model_budget']})
        # 只清理本脚本创建且没有消息/客户的探针行，不污染用户的对话列表。
        db.delete(row);db.delete(db.get(Conversation,row.conversation_id))


if __name__=='__main__':asyncio.run(main())
