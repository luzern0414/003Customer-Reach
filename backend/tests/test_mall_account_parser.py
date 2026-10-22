"""Agent原生目录工具的确定性商户提取；合成记录不是实际客户名单。"""
import asyncio
import uuid
import pytest
from app.public_accounts import parse_accounts,supports_template


def source():
    """无参数；返回已验证目录形状，包含灯饰与后续其他分类，号码仅用于隔离测试。"""
    return {'id':'s','url':'http://www.leanju.com:8080/subbranch-detail/i-91.html','title':'合成目录',
        'kind':'网页正文','channel':'mall_directory','captured_at':'2026-10-04 00:00:00',
        'body':'隔离南山店 入驻品牌\n作为隔离商场在深圳西部的重要布点。\n了解更多\n灯饰\n隔离甲灯饰\nTel: 13169928365\n隔离乙照明\nTel: 0755-23004025\n隔离短号灯饰\nTel: 81762065\n家具\n隔离家具\nTel: 13794469638'}


def test_parser_preserves_each_merchant_phone_and_omits_inherited_address(client):
    """client隔离库；复用真实checked_candidate逐字/角色/城市/电话验证，不继承商场总地址或补法律名。"""
    from app.service import checked_candidate
    row=source();candidates=parse_accounts(row,'深圳',[{'name':'吊灯'}])
    assert [candidate.display_name for candidate in candidates]==['隔离甲灯饰','隔离乙照明']
    assert [checked_candidate(candidate,{'s':row})[0]['phone']['value'] for candidate in candidates]==['13169928365','0755-23004025']
    for candidate in candidates:
        assert candidate.matched_products==[]
        assert {fact.field for fact in candidate.facts}=={'name','buyer_role','phone','categories'}
        assert all(fact.quote in row['body'] and fact.value in fact.quote for fact in candidate.facts)
    assert not parse_accounts(row,'广州',[{'name':'吊灯'}])
    assert not parse_accounts(row,'深圳',[{'name':'沙发'}])
    assert not supports_template({**row,'kind':'搜索摘录'})
    assert not supports_template({**row,'url':'https://example.org/subbranch-detail/i-91.html'})
    conflict={**row,'body':row['body'].replace('\n家具\n','\n隔离甲灯饰\nTel: 13794469638\n家具\n')}
    assert [candidate.display_name for candidate in parse_accounts(conflict,'深圳',[{'name':'吊灯'}])]==['隔离乙照明']
    assert not parse_accounts({**row,'body':row['body']+'\n隔离宝安店 入驻品牌'},'深圳',[{'name':'吊灯'}])


def test_agent_directory_tool_batch_still_passes_broker_before_save(client,monkeypatch):
    """真实extract→parse_account→persist，禁止模型替身；候选批次与保存配额分开、不发网络请求。"""
    from app import agent
    from app.db import Session,Job,ToolCall
    from app.service import save_settings
    from app.gateway import archive_sources
    options=save_settings({'enabled_channels':['mall_directory'],'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具零售商','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,job).status='running'
    row=archive_sources(job,[source()],'网页正文','mall_directory')[0]
    async def forbidden(*args,**kwargs):raise AssertionError('已验证目录不应耗模型提取')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    state={'job_id':job,'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'prompt':'自主找深圳灯具零售买家',
        'options':options,'plan':{'target_roles':['retailer']},'source_ids':[row['id']],
        'recent_read_source_ids':[row['id']],'saved_ids':[],'cursor':0}
    parsed=asyncio.run(agent.extract_node(state));assert len(parsed['candidates'])==2
    saved=asyncio.run(agent.save_node({**state,**parsed}));assert len(saved['saved_ids'])==1
    with Session() as db:
        assert db.query(ToolCall).filter(ToolCall.job_id==job,ToolCall.tool=='parse_account',ToolCall.status=='completed').count()==1
        assert db.query(ToolCall).filter(ToolCall.job_id==job,ToolCall.tool=='persist_lead',ToolCall.status=='completed').count()==1


@pytest.mark.parametrize('timeout',[False,True])
def test_empty_second_template_does_not_regenerate_successful_page(client,monkeypatch,timeout):
    """client隔离库；成功页保持原生结果，第二页只有短号时模型只见第二页原文。"""
    from app import agent
    from app.db import Session,Job
    from app.service import save_settings
    from app.gateway import archive_sources
    from app.schemas import CandidateBatch
    options=save_settings({'enabled_channels':['mall_directory'],'max_leads':8})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳灯具零售商','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,job).status='running'
    first=source()
    second={**source(),'url':'http://www.leanju.com:8080/subbranch-detail/i-92.html',
        'body':'隔离宝安店 入驻品牌\n作为隔离商场在深圳西部的重要布点。\n灯饰\n隔离丙灯饰\nTel: 81762065'}
    rows=archive_sources(job,[first,second],'网页正文','mall_directory')
    calls=[]
    async def extract(state,schema,text,key):
        """参数为真实候选模型接口；只替换外部生成，验证短编号映射不混成功页。"""
        calls.append(text)
        assert '隔离丙灯饰' in text and '隔离甲灯饰' not in text and rows[0]['url'] not in text
        if timeout:raise TimeoutError('隔离模型超时')
        return CandidateBatch(candidates=[],missing_fields=['phone'])
    monkeypatch.setattr(agent,'cached_model',extract)
    state={'job_id':job,'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'prompt':'自主找深圳灯具零售买家',
        'options':options,'plan':{'target_roles':['retailer']},'source_ids':[row['id'] for row in rows],
        'recent_read_source_ids':[row['id'] for row in rows],'saved_ids':[],'cursor':0}
    result=asyncio.run(agent.extract_node(state))
    assert len(calls)==1 and len(result['candidates'])==2
    assert result['gaps']==(['buyer_role','phone'] if timeout else ['phone'])
    if timeout:
        assert result['warnings']==['extract_model_timeout'] and 'extraction_hashes' not in result
        saved=asyncio.run(agent.save_node({**state,**result}))
        assert len(saved['saved_ids'])==2
    assert all(fact['source_id']==rows[0]['id'] for item in result['candidates'] for fact in item['facts'])


def market_source():
    """无入参；已验证分店结构的合成直接身份简介，租户号码不能给场所。"""
    return {**source(),'body':'乐安居隔离南山店，是深圳市品种齐全的家居建材综合类商场。\n了解更多\n隔离南山店 入驻品牌\n灯饰\n隔离甲灯饰\nTel: 13169928365'}


@pytest.mark.parametrize('header_first',[False,True])
def test_market_parser_preserves_explicit_identity_and_never_borrows_tenant_phone(client,header_first):
    """client隔离库；真实Pydantic及服务校验，目标角色明确，城市/角色直接原文，联系方式未知。"""
    from app.service import checked_candidate
    row=market_source()
    if header_first:row['body']='隔离南山店 入驻品牌\n'+row['body'].replace('隔离南山店 入驻品牌\n','')
    candidates=parse_accounts(row,'深圳',[{'name':'吊灯'}],['mall'])
    assert len(candidates)==1 and candidates[0].display_name=='乐安居隔离南山店'
    clean,cites=checked_candidate(candidates[0],{'s':row})
    assert set(clean)=={'name','buyer_role','categories'} and clean['categories']['value']=='灯饰'
    assert 'Tel:' not in next(fact.quote for fact in candidates[0].facts if fact.field=='categories')
    assert candidates[0].matched_products==[] and all(item['quote'] in row['body'] for item in cites)
    for body in [row['body'].replace('是深圳市','是广州市'),row['body'].replace('，是','，不是'),
        row['body'].replace('是深圳市品种齐全的','是深圳另一照明有限公司的'),
        row['body'].replace('乐安居隔离南山店','乐安居另一个店'),
        row['body'].replace('是深圳市品种齐全的','是服务深圳市品种齐全的')]:
        assert not parse_accounts({**row,'body':body},'深圳',[{'name':'吊灯'}],['mall'])
    assert not parse_accounts(row,'深圳',[{'name':'吊灯'}],['manufacturer'])
    assert [candidate.buyer_role for candidate in parse_accounts(row,'深圳',[{'name':'吊灯'}],['retailer'])]==['retailer']


def test_agent_market_parse_tool_avoids_model_and_keeps_full_persist_guard(client,monkeypatch):
    """client隔离库，monkeypatch禁止模型；实际Agent→parse_account→persist，不以原生解析替代核验。"""
    from app import agent
    from app.db import Session,Job,ToolCall,Lead
    from app.gateway import archive_sources
    from app.service import save_settings
    options=save_settings({'enabled_channels':['mall_directory'],'max_leads':1})
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'找深圳家居市场','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:db.get(Job,job).status='running'
    row=archive_sources(job,[market_source()],'网页正文','mall_directory')[0]
    async def forbidden(*args,**kwargs):raise AssertionError('成功目录场所提取不应调用模型')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    state={'job_id':job,'profile':{'region':'深圳','products':[{'name':'吊灯'}]},'prompt':'自主寻找深圳家居市场',
        'options':options,'plan':{'target_roles':['mall']},'source_ids':[row['id']],'recent_read_source_ids':[row['id']],
        'saved_ids':[],'cursor':0}
    parsed=asyncio.run(agent.extract_node(state));assert len(parsed['candidates'])==1
    saved=asyncio.run(agent.save_node({**state,**parsed}));assert len(saved['saved_ids'])==1
    with Session() as db:
        tool=db.query(ToolCall).filter(ToolCall.job_id==job,ToolCall.tool=='parse_account').one()
        assert tool.arguments['target_roles']==['mall'] and tool.status=='completed'
        assert 'phone' not in db.get(Lead,saved['saved_ids'][0]).facts
