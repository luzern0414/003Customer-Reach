"""交替回到同一证据不应重复模型提取；画像、规则或实际原文变更仍须分析。"""
import asyncio
import uuid


def test_alternating_sources_are_processed_once_but_changes_reopen(client,monkeypatch):
    """实际extract上下文选择/签名，替身只计模型次数；不调用外部服务或保存测试客户。"""
    from app import agent
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    key=uuid.uuid4().hex
    sources=[archive_sources(key,[{'url':f'https://example.org/{key}/{label}','title':'隔离照明资料'+label,
        'body':('原始照明资料'+label+'，没有完整买家身份。')*30}],'网页正文','official')[0] for label in ['A','B']]
    calls=[]
    async def count(state,schema,prompt,name):
        calls.append(name);return CandidateBatch(candidates=[],missing_fields=['buyer_role'])
    monkeypatch.setattr(agent,'cached_model',count)
    state={'job_id':key,'profile':{'region':'深圳','products':[{'name':'壁灯'}]},'prompt':'寻找深圳灯具经销商 '+key,
        'options':{'enabled_channels':['official'],'max_leads':1},'plan':{'target_roles':['dealer']},'saved_ids':[],
        'source_ids':[sources[0]['id']],'recent_read_source_ids':[sources[0]['id']],'cursor':0}
    state={**state,**asyncio.run(agent.extract_node(state))}
    state={**state,'source_ids':[item['id'] for item in sources],'recent_read_source_ids':[sources[1]['id']],'cursor':1}
    state={**state,**asyncio.run(agent.extract_node(state))}
    state={**state,'recent_read_source_ids':[sources[0]['id']],'cursor':2}
    assert asyncio.run(agent.extract_node(state))['candidates']==[] and len(calls)==2
    updated={**state,'profile':{**state['profile'],'products':[{'name':'吊灯'}]}}
    assert asyncio.run(agent.extract_node(updated))['extraction_hash'] not in state['extraction_hashes']
    assert len(calls)==3
    monkeypatch.setattr(agent,'source_rules',lambda enabled:'明确更新后的规则')
    assert asyncio.run(agent.extract_node(state))['extraction_hash'] not in state['extraction_hashes']
    assert len(calls)==4
    changed=archive_sources(key,[{'url':sources[0]['url'],'title':sources[0]['title'],
        'body':'新增公开资料，需重新分析。'*40}],'网页正文','official')[0]
    state={**state,'source_ids':[changed['id']],'recent_read_source_ids':[changed['id']]}
    assert asyncio.run(agent.extract_node(state))['extraction_hash'] not in state['extraction_hashes']
    assert len(calls)==5
