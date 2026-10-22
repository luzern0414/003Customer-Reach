"""知识实际消费、销售反馈与渠道产出回归，使用隔离夹具，不伪造公网验证。"""
import asyncio
import uuid
import pytest
from app.db import Session,Evidence
from app.knowledge import upsert_knowledge,invalidated_procurement,store,WORKSPACE
from app.service import save_candidate,ServiceError
from app.research_tools import recipe
from test_export_signals import fixture


@pytest.mark.parametrize('kind',['incorrect','stale'])
def test_feedback_blocks_independent_procurement(kind,client):
    """kind为纠错或失效反馈；独立公告不能通过新基础来源绕过反馈。"""
    identifier,candidate,rows,job=fixture(client)
    client.post('/api/leads/'+identifier+'/feedback',json={'kind':kind})
    signal=candidate.procurement_signal
    assert invalidated_procurement(candidate.display_name,signal,rows[signal.source_id])
    if kind=='stale':
        from app.gateway import archive_sources
        basic=next(x for x in rows.values() if x['id']!=signal.source_id)
        fresh=archive_sources(job,[{'url':basic['url']+'/fresh','title':basic['title'],'body':basic['body']}],'隔离测试')[0]
        with Session.begin() as db:db.get(Evidence,fresh['id']).captured_at='2099-01-01 00:00:00'
        fresh['captured_at']='2099-01-01 00:00:00'
        rows[fresh['id']]=fresh
        updated=candidate.model_copy(update={'facts':[x.model_copy(update={'source_id':fresh['id']}) for x in candidate.facts]})
        with pytest.raises(ServiceError,match='采购公告已被用户'):save_candidate(updated,rows,job)
        result=client.get('/api/leads/'+identifier).json()
        assert result['qualification']['signal_score']==0 and len(result['procurement_signals'])==1


def test_manual_product_knowledge_enters_real_context(client):
    """client为隔离API；真实FTS/工具/节点消费用户产品知识，但不生成公开证据ID。"""
    from app.agent import load_context
    label='知识产品-'+uuid.uuid4().hex
    upsert_knowledge(label,label+' 吊灯型号QA-KNOW-01，功率18W，价格由用户提供为79元。','product')
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'你好','client_token':uuid.uuid4().hex}).json()['id']
    result=asyncio.run(load_context({'job_id':job,'conversation_id':conv,'prompt':label,'source_ids':[],
        'options':{'enabled_channels':['knowledge']}}))
    assert 'QA-KNOW-01' in result['context'] and '用户资料，非公开客户证据' in result['context']
    assert not result['source_ids'] and result['metrics']['knowledge_hits']>=1


def test_learned_leads_change_next_plan_only_for_same_product(client,monkeypatch):
    """client为隔离API，monkeypatch只替规划模型；真实learn/Store/排序验证同产品产出优先。"""
    from app import agent
    from app.schemas import ResearchPlan,ResearchStep
    identifier,candidate,rows,job=fixture(client)
    region='隔离地区-'+uuid.uuid4().hex
    profile={'products':[{'name':'吊灯'}],'region':region}
    with Session.begin() as db:
        for source in rows.values():db.get(Evidence,source['id']).channel='directory'
    recipe('directory',True,10,profile)
    for _ in range(5):recipe('procurement',True,10,profile)
    learn_state={'profile':profile,'conversation_id':client.post('/api/conversations').json()['id'],
        'attempts':[{'channel':'directory'}],'saved_ids':[identifier]}
    asyncio.run(agent.learn_node(learn_state))
    asyncio.run(agent.learn_node(learn_state))
    assert any(x.value.get('valid_leads')==1 for x in store.search((WORKSPACE,'recipes'),limit=200) if x.value.get('region')==region)
    recipe('procurement',True,10,{'products':[{'name':'沙发'}],'region':region},valid_leads=100)
    async def planner(state,schema,prompt,label):
        """参数为真实计划节点；固定模型计划以验证后续实际排序，不冒充真实模型调用。"""
        return ResearchPlan(target_roles=['retailer'],steps=[ResearchStep(channel=x,query='隔离查询'+x,purpose='隔离计划') for x in ['official','procurement','directory']])
    monkeypatch.setattr(agent,'cached_model',planner)
    result=asyncio.run(agent.plan_node({'prompt':'寻找灯具零售门店','profile':profile,
        'options':{'enabled_channels':['official','procurement','directory']}}))
    assert [x['channel'] for x in result['steps']]==['official','directory','procurement']
    client.post('/api/leads/'+identifier+'/feedback',json={'kind':'relevant'})
    actual=[x.value for x in store.search((WORKSPACE,'recipes'),limit=200) if x.value.get('region')==region]
    assert next(x for x in actual if x['channel']=='directory')['positive_feedback']==1
    assert all(x.get('positive_feedback',0)==0 for x in actual if x['category']=='沙发')
