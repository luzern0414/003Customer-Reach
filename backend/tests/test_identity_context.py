"""真实提取入口的历史身份上下文回归；模型替身不作真实获客成果。"""
import asyncio
import json
import uuid


def test_repeated_enrichment_only_keeps_cited_identity_and_fresh_pages(client,monkeypatch):
    """client为隔离库，monkeypatch记录提示；两轮新页均进入，未引用历史和上一补查页不重复。"""
    from app import agent
    from app.db import Session,Lead,identifier
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    job=uuid.uuid4().hex;name='深圳合成身份灯饰有限公司';key=identifier()
    intro=name+'位于深圳。专业从事灯具零售业务。'
    rows=archive_sources(job,[{'url':f'https://example.org/{job}/{index}','title':name,
        'body':intro+f'\n隔离正文标记{index}。'+('合成资料。'*25)} for index in range(4)],'网页正文','official')
    with Session.begin() as db:
        db.add(Lead(id=key,display_name=name,city='深圳',dedupe_key=job,evidence=[
            {'field':field,'source_id':rows[0]['id'],'quote':intro} for field in ['name','buyer_role','city']]))
    prompts=[]
    async def model(state,schema,prompt,label):
        """参数为真实提取调用；仅记录上下文并返回空批次，不提供任何客户事实。"""
        prompts.append(prompt);return CandidateBatch(candidates=[],missing_fields=[])
    monkeypatch.setattr(agent,'cached_model',model)
    for index in [2,3]:
        asyncio.run(agent.extract_node({'job_id':job,'saved_ids':[key],'source_ids':[row['id'] for row in rows[:index+1]],
            'recent_read_source_ids':[rows[index]['id']],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
            'prompt':'自主查找深圳灯具零售买家','options':{'max_leads':1,'enabled_channels':['official']},
            'cursor':index,'plan':{'target_roles':['retailer']}}))
    for index,prompt in zip([2,3],prompts):
        context=json.loads(prompt.split('\n来源：',1)[1].split('\n明确指定主体：',1)[0])
        assert {row['url'] for row in context}=={rows[0]['url'],rows[index]['url']}
        assert all(intro in row['body'] for row in context)


def test_full_batch_new_page_does_not_regenerate_unmentioned_saved_subject(client,monkeypatch):
    """client隔离库、monkeypatch记录真实提示；满额新页只提甲时，不带乙旧网页也不要求重生成乙。"""
    from app import agent
    from app.db import Session,Lead,identifier
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    job=uuid.uuid4().hex;names=['深圳隔离满额甲商行','深圳隔离满额乙商行'];keys=[]
    rows=archive_sources(job,[{'url':'https://example.org/'+uuid.uuid4().hex,'title':name,
        'body':name+'位于深圳，经销灯具。'+('合成旧资料。'*30)} for name in names],'网页正文','official')
    with Session.begin() as db:
        for name,row in zip(names,rows):
            key=identifier();keys.append(key)
            db.add(Lead(id=key,display_name=name,city='深圳',dedupe_key=uuid.uuid4().hex,
                evidence=[{'field':'name','source_id':row['id'],'url':row['url']}]))
    fresh=archive_sources(job,[{'url':'https://example.net/'+uuid.uuid4().hex,'title':names[0],
        'body':names[0]+'位于深圳，经销灯具。'+('合成新资料。'*30)}],'网页正文','official')[0]
    prompts=[]
    async def model(state,schema,prompt,label):
        """只记录本轮模型输入；不生成候选或模拟外部请求。"""
        prompts.append(prompt);return CandidateBatch(candidates=[],missing_fields=[])
    monkeypatch.setattr(agent,'cached_model',model)
    asyncio.run(agent.extract_node({'job_id':job,'saved_ids':keys,'source_ids':[row['id'] for row in rows]+[fresh['id']],
        'recent_read_source_ids':[fresh['id']],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'prompt':'找深圳灯具经销商','options':{'max_leads':2,'enabled_channels':['official']},
        'cursor':0,'plan':{'target_roles':['dealer']}}))
    context=json.loads(prompts[0].split('\n来源：',1)[1].split('\n明确指定主体：',1)[0])
    assert {row['url'] for row in context}=={rows[0]['url'],fresh['url']}
    assert '\n明确指定主体：'+json.dumps([names[0]],ensure_ascii=False) in prompts[0]
    assert names[1] not in prompts[0]


def test_contact_enrichment_receives_exact_active_identity_citations_with_current_aliases(client,monkeypatch):
    """client隔离库、monkeypatch只记录模型输入；原身份引文可复用，争议地址/未入范围来源不进入卡片。"""
    from app import agent
    from app.db import Session,Lead,identifier
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    job=uuid.uuid4().hex;name='深圳隔离联系身份照明有限公司';key=identifier()
    role_quote=name+'经销灯具。'
    old=archive_sources(job,[{'url':'https://example.org/'+job,'title':name,'body':role_quote+'\n地址：深圳隔离路'}],'网页正文','official')[0]
    fresh=archive_sources(job,[{'url':'https://example.net/'+job,'title':name,'body':name+'\n联系人：李先生'}],'网页正文','official')[0]
    with Session.begin() as db:db.add(Lead(id=key,display_name=name,city='深圳',buyer_role='dealer',dedupe_key=job,
        facts={'name':{'value':name,'verification':'原文匹配'},'buyer_role':{'value':'经销','verification':'原文匹配'},
            'address':{'value':'深圳隔离路','verification':'disputed'}},
        evidence=[{'field':field,'value':value,'source_id':old['id'],'quote':quote,'url':old['url']} for field,value,quote in [
            ('name',name,name),('buyer_role','经销',role_quote),('address','深圳隔离路','地址：深圳隔离路')]]))
    async def model(state,schema,prompt,label):
        """参数为实际候选生成请求；验证原文卡片精确绑定当前Source短别名，不生成新事实。"""
        sources=json.loads(prompt.split('\n来源：',1)[1].split('\n明确指定主体：',1)[0])
        cards=json.JSONDecoder().raw_decode(prompt.split('\n本轮已存主体的有效身份引用：',1)[1])[0]
        assert {card['field'] for card in cards}=={'name','buyer_role'}
        role=next(card for card in cards if card['field']=='buyer_role')
        assert role['quote']==role_quote and role['value']=='经销'
        assert any(source['id']==role['source_id'] and source['url']==old['url'] for source in sources)
        return CandidateBatch(candidates=[],missing_fields=['phone'])
    monkeypatch.setattr(agent,'cached_model',model)
    result=asyncio.run(agent.extract_node({'job_id':job,'saved_ids':[key],'source_ids':[old['id'],fresh['id']],
        'recent_read_source_ids':[fresh['id']],'profile':{'region':'深圳','products':[{'name':'吊灯'}]},
        'prompt':'补查'+name+'的联系人','options':{'max_leads':1,'enabled_channels':['official']},'cursor':0,'plan':{'target_roles':['dealer']}}))
    assert result['gaps']==['phone']
