"""END处partial恢复必须保留原checkpoint，角色策略升级只重验来源、不重做网络。"""
import asyncio
import json
import uuid
from pathlib import Path
import pytest


@pytest.mark.parametrize('upgrade',[True,False])
def test_terminal_partial_resume_rechecks_role_policy_without_restarting(client,monkeypatch,upgrade):
    """client隔离DB、monkeypatch替无关模型/网络节点、upgrade是否策略变化；实际Saver/图/save/finish保留来源、客户、模型预算。"""
    from app import agent
    from app.db import Session,Job
    from app.service import settings
    from app.evidence_role import ROLE_POLICY
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from test_export_signals import fixture
    lead,candidate,sources,job_id=fixture(client)
    checkpoint_dir=Path(__file__).resolve().parents[2]/'.codex-tmp'/('terminal-resume-'+uuid.uuid4().hex)
    checkpoint_dir.mkdir(parents=True)
    monkeypatch.setattr(agent,'DATA',checkpoint_dir)
    prompt='我们销售吊灯，仅复核这个页面 '+sources[candidate.facts[0].source_id]['url']
    options={**settings(),'enabled_channels':['official'],'max_leads':1,'max_reads':1}
    with Session.begin() as db:
        job=db.get(Job,job_id);job.prompt=prompt;job.status='running';job.lead_ids=[lead]
        job.metrics={'model_budget':{'calls':7,'accounted_tokens':1000}}
        conversation_id=job.conversation_id
    state={'job_id':job_id,'conversation_id':conversation_id,'schema_version':agent.GRAPH_VERSION,'intent':'research',
        'prompt':prompt,'profile':{'region':'深圳','products':[{'name':'吊灯'}],'questions':[]},'options':options,
        'plan':{'target_roles':['retailer']},'source_ids':list(sources),'saved_ids':[lead],'steps':[{'channel':'official','query':'隔离原计划'}],
        'cursor':1,'attempts':[],'warnings':[],'gaps':['phone'],'stage_timings':{},'metrics':{},
        'reference_only':True,'reference_urls':[],'validation_policy':'role-policy-2' if upgrade else ROLE_POLICY}
    seen=[]
    errors=[]
    monkeypatch.setattr(agent.LOG,'error',lambda message,**kwargs:errors.append(kwargs.get('extra',{})))
    async def extract(current):
        """模型替身只记录checkpoint内容；候选走后续实际persist，未冒充真实模型/公网。"""
        assert current['source_ids']==list(sources) and current['cursor']==1
        seen.append('extract');return {'candidates':[candidate.model_dump()]}
    async def forbidden(current):raise AssertionError('不能重做初态或网络')
    async def answer(current):return {'answer':'隔离恢复验证'}
    async def learn(current):return {}
    monkeypatch.setattr(agent,'extract_node',extract)
    for name in ['load_context','profile_node','plan_node','decide_node','search_node','read_node']:monkeypatch.setattr(agent,name,forbidden)
    monkeypatch.setattr(agent,'answer_node',answer);monkeypatch.setattr(agent,'learn_node',learn)
    async def verify():
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_dir/'checkpoints.db')) as saver:
            await saver.setup();graph=agent.build_graph(saver)
            await graph.aupdate_state({'configurable':{'thread_id':job_id}},state,as_node='learn')
            assert not (await graph.aget_state({'configurable':{'thread_id':job_id}})).next
        await agent.run_job(job_id)
        with Session() as db:
            outcome=db.get(Job,job_id)
            assert not outcome.error, json.dumps({'error':outcome.error,'details':errors},ensure_ascii=False)
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_dir/'checkpoints.db')) as saver:
            await saver.setup();current=await agent.build_graph(saver).aget_state({'configurable':{'thread_id':job_id}})
            assert current.values['validation_policy']==ROLE_POLICY
    asyncio.run(verify())
    assert seen==(['extract'] if upgrade else [])
    with Session() as db:
        job=db.get(Job,job_id)
        assert job.status=='partial' and job.lead_ids==[lead]
        assert job.metrics['model_budget']['calls']==7
        assert job.metrics['source_ids']==list(sources)
