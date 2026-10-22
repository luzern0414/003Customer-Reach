"""真实模型缓存键和修复核心事实保护；合成资料、不发外部请求。"""
import asyncio
import uuid
import pytest


@pytest.mark.parametrize('missing',['name','buyer_role','city'])
def test_same_failed_repair_is_cached_across_cursor_and_preserves_target(client,monkeypatch,missing):
    """client隔离库，monkeypatch仅替structured，missing为被删核心；跨cursor缓存，新原文可重修。"""
    from app import agent
    from app.db import Session,Job
    from app.gateway import archive_sources
    from app.schemas import Candidate
    from app.service import save_settings
    name='隔离修复灯饰经营部'+uuid.uuid4().hex[:6]
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具零售商','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,job).status='running'
    body=name+'位于深圳。\n网页栏目：零售'
    row=archive_sources(job,[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name,'body':body}],'网页正文','official')[0]
    candidate=Candidate(display_name=name,city='深圳',buyer_role='retailer',match_reason='隔离测试',facts=[
        {'field':'name','value':name,'quote':body,'source_id':row['id']},
        {'field':'buyer_role','value':'零售','quote':'网页栏目：零售','source_id':row['id']}])
    calls=[]
    async def structured(schema,prompt):
        """返回故意丢失核心证据的修复；参数为真实schema/prompt，不模拟保存通过。"""
        calls.append(prompt)
        facts=[fact for fact in candidate.facts if fact.field!=missing]
        if missing=='city':facts=[fact.model_copy(update={'quote':name}) if fact.field=='name' else fact for fact in facts]
        return candidate.model_copy(update={'facts':facts})
    monkeypatch.setattr(agent,'structured',structured)
    state={'job_id':job,'prompt':'找深圳灯具零售商','profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'options':save_settings({'enabled_channels':['official'],'max_leads':1}),
        'source_ids':[row['id']],'saved_ids':[],'candidates':[candidate.model_dump()],
        'plan':{'target_roles':['retailer']},'cursor':0}
    first=asyncio.run(agent.save_node(state))
    second=asyncio.run(agent.save_node({**state,**first,'cursor':1}))
    assert first['candidate_targets']==second['candidate_targets']==[name]
    assert second['saved_ids']==[] and len(calls)==1
    extra=archive_sources(job,[{'url':'https://example.net/'+uuid.uuid4().hex,'title':name,'body':body+'\n合成补查新正文。'}],'网页正文','official')[0]
    asyncio.run(agent.save_node({**state,**second,'cursor':2,'source_ids':[row['id'],extra['id']]}))
    assert len(calls)==2
