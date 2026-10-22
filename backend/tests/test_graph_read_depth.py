"""允许的24次读取预算必须能经过真实LangGraph完整回路到达答复，不能撞固定100步。"""
import asyncio
import uuid
from pathlib import Path


def test_supported_twenty_four_reads_reach_answer_without_recursion_error(client,monkeypatch):
    """保留run_job/图/SQLite checkpoint/计时；替换外部业务节点为确定性无网络样例，验证图步预算而非获客。"""
    from app import agent
    from app.db import Session,Conversation,Job,identifier
    from app.service import submit,save_settings
    folder=Path(__file__).resolve().parents[2]/'.codex-tmp'/('graph-depth-'+uuid.uuid4().hex)
    folder.mkdir(parents=True)
    monkeypatch.setattr(agent,'DATA',folder)
    save_settings({'enabled_channels':['industry_directory'],'max_reads':24,'max_leads':1})
    conv=identifier()
    with Session.begin() as db:db.add(Conversation(id=conv,title='隔离图步预算'))
    job=submit(conv,{'content':'找深圳灯具经销客户最多1家','attachment_ids':[],'client_token':uuid.uuid4().hex})
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    calls=[]
    async def noop(state):
        """state为真实图状态；无网络节点保留已有业务值，不造客户。"""
        return {}
    async def profile(state):
        """state为初始状态；固定产品仅用于图控制路径，不代表真实用户解析验证。"""
        return {'profile':{'region':'深圳','products':[{'name':'吊灯'}],'questions':[],'summary':'隔离图预算输入'}}
    async def plan(state):
        """state为输入；单一读渠道用于触发原read→extract→save→gap真实条件回路。"""
        return {'steps':[{'channel':'industry_directory','query':'隔离样例'}],'cursor':0}
    async def read(state):
        """state为累计状态；模拟一次读动作但不返回来源，不作为外部读取证据。"""
        calls.append('read');return {'metrics':{'reads':len(calls)}}
    async def gap(state):
        """state含模拟次数；24次后进入answer，之前走原直接读取条件边。"""
        return {'cursor':0 if len(calls)<24 else 1,'direct_read_pending':len(calls)<24}
    async def answer(state):
        """state为已完成循环；只记录真实到达，不模拟客户或模型结果。"""
        return {'answer':'隔离图回路完成，无客户数据。','metrics':{**state.get('metrics',{}),'depth_answer_reached':True}}
    for name in ['load_context','decide_node','search_node','extract_node','save_node','learn_node']:monkeypatch.setattr(agent,name,noop)
    for name,fn in [('profile_node',profile),('plan_node',plan),('read_node',read),('gap_node',gap),('answer_node',answer)]:monkeypatch.setattr(agent,name,fn)
    asyncio.run(agent.run_job(job['id']))
    with Session() as db:
        row=db.get(Job,job['id'])
        assert row.status=='partial' and not row.error
        assert row.metrics['depth_answer_reached'] and len(calls)==24
