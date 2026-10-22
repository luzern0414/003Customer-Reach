"""获客证据覆盖与CRM跨字段一致性回归；所有企业/公告都是隔离测试夹具。"""
import asyncio
import uuid
from sqlalchemy import select
from app.db import Session,Lead,Job
from app.gateway import archive_sources
from app.evidence_context import evidence_context,evidence_excerpt
from app.research_tools import ToolBroker
from app.schemas import Candidate


def test_recent_source_and_full_body_enter_context():
    rows=[{'id':str(i),'url':'https://example.com/'+str(i),'title':'旧来源','kind':'网页正文','body':'深圳授权经销商旧资料'} for i in range(6)]
    rows.extend([{'id':'new','url':'https://example.org/new','title':'新来源','kind':'搜索摘录','body':'深圳授权经销商摘要'},
        {'id':'full','url':'https://example.org/new','title':'新正文','kind':'网页正文','body':'完整正文：原始业务联系方式'}])
    context=evidence_context(rows,[],'深圳',[row['id'] for row in rows],['new'])
    assert len(context)<=6 and context[0]['id']=='full'
    assert sum(x['url']=='https://example.org/new' for x in context)==1


def test_middle_buyer_record_is_not_lost_in_long_directory():
    record='隔离门店甲为授权经销商，业务电话0755-12345678。'
    text='目录介绍。'*1200+record+'目录说明。'*1200
    excerpt=evidence_excerpt(text,[])
    assert record in excerpt and len(excerpt)<=3500 and '省略' in excerpt


def test_badly_decoded_body_cannot_replace_valid_excerpt():
    base={'url':'https://example.org/gb2312','title':'隔离编码样例'}
    rows=[{**base,'id':'snippet','kind':'搜索摘录','body':'深圳隔离门店为授权销售点，地址深圳。'},
        {**base,'id':'bad','kind':'网页正文','body':'\ufffd'*200}]
    context=evidence_context(rows,[],'深圳',['snippet','bad'],['snippet'])
    assert len(context)==1 and context[0]['id']=='snippet'


def test_html_charset_and_corrupt_cache_use_real_decoder(client,monkeypatch):
    import httpx
    from app import research_tools
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'寻找深圳经销商','client_token':uuid.uuid4().hex}).json()['id']
    url='https://encoding.example/store'
    archive_sources(job,[{'url':url,'title':'隔离乱码缓存','body':'\ufffd'*300}],'网页正文')
    text='深圳隔离照明店是灯具授权销售点，地址深圳市南山区，主营轨道灯和筒灯，仅用于编码解析测试。'
    html=('<html><head><meta charset="gb2312"><title>隔离编码目录</title></head><body><article>'+''.join('<p>'+text+'</p>' for _ in range(6))+'</article></body></html>').encode('gb2312')
    calls=[]
    async def response(request):calls.append(str(request.url));return httpx.Response(200,content=html,headers={'Content-Type':'text/html'})
    original=httpx.AsyncClient
    monkeypatch.setattr(research_tools.httpx,'AsyncClient',lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(response)))
    monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    async def no_fallback(*args):raise AssertionError('正确解码后不应调用供应商fallback')
    monkeypatch.setattr(research_tools,'call_exa',no_fallback)
    broker=ToolBroker(job,{'max_reads':1,'max_searches':0,'enabled_channels':['official']},{})
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'official'}))
    assert len(calls)==1 and not result.get('error')
    assert result['sources'][0]['body'].count('\ufffd')==0 and '授权销售点' in result['sources'][0]['body']


def test_error_diagnostics_never_include_exception_body():
    import json
    from app.observability import error_details
    try:raise OSError(22,'PRIVATE_API_KEY_AND_DOCUMENT')
    except OSError as exc:data=error_details(exc)
    encoded=json.dumps(data)
    assert 'PRIVATE' not in encoded and data['errors'][0]['errno']==22 and data['errors'][0]['frames']


def test_followup_reads_only_current_conversation_crm_results(client,monkeypatch):
    from app import agent
    from langchain_core.messages import AIMessageChunk
    own=client.post('/api/conversations').json()['id'];other=client.post('/api/conversations').json()['id']
    lead=client.post('/api/leads',json={'display_name':'隔离当前对话客户'}).json()
    foreign=client.post('/api/leads',json={'display_name':'隔离其他对话客户'}).json()
    own_job=client.post('/api/conversations/'+own+'/messages',json={'content':'你好','client_token':uuid.uuid4().hex}).json()['id']
    foreign_job=client.post('/api/conversations/'+other+'/messages',json={'content':'你好','client_token':uuid.uuid4().hex}).json()['id']
    with Session.begin() as db:
        db.get(Job,own_job).lead_ids=[lead['id']];db.get(Job,foreign_job).lead_ids=[foreign['id']]
        db.get(Job,own_job).status='completed';db.get(Job,foreign_job).status='completed'
    prompt='刚才结果有哪些客户？'
    chat=client.post('/api/conversations/'+own+'/messages',json={'content':prompt,'client_token':uuid.uuid4().hex}).json()['id']
    captured=[]
    class Model:
        """仅捕获模型输入，客户读取/消息/SSE执行真实实现，不发网络。"""
        async def astream(self,messages):
            """messages为真实模型消息；返回隔离固定回答用于检查上下文作用域。"""
            captured.append(messages[-1].content);yield AIMessageChunk(content='隔离上下文验证')
    monkeypatch.setattr(agent,'model',lambda:Model())
    asyncio.run(agent.answer_node({'job_id':chat,'conversation_id':own,'intent':'chat','prompt':prompt}))
    assert '隔离当前对话客户' in captured[0] and '隔离其他对话客户' not in captured[0]
    assert '优先于旧助手总结' in captured[0]
    client.delete('/api/leads/'+lead['id']);client.delete('/api/leads/'+foreign['id'])


def test_role_edit_recalculates_qualification_and_respects_nonbuyer_feedback(client):
    row=client.post('/api/leads',json={'display_name':'隔离资格回归客户','buyer_role':'dealer','phone':'0755-12345678'}).json()
    with Session.begin() as db:
        lead=db.get(Lead,row['id']);lead.matched_products=['吊灯'];lead.score=90
        lead.qualification={'eligible':True,'role':'dealer','role_score':40,'product_score':20,'evidence_score':30,'signal_score':0}
    changed=client.patch('/api/leads/'+row['id'],json={'buyer_role':'manufacturer'}).json()
    assert changed['score']<=35 and changed['qualification']['eligible'] is False
    assert changed['qualification']['role']=='manufacturer' and changed['qualification']['role_score']==0
    dealer=client.patch('/api/leads/'+row['id'],json={'buyer_role':'dealer'}).json()
    assert dealer['qualification']['eligible'] and dealer['score']==70
    assert client.post('/api/leads/'+row['id']+'/feedback',json={'kind':'nonbuyer'}).status_code==201
    changed=client.patch('/api/leads/'+row['id'],json={'phone':'0755-87654321','buyer_role':'dealer'}).json()
    assert changed['score']==0 and changed['qualification']['eligible'] is False
    assert '非买家' in changed['tags']
    client.delete('/api/leads/'+row['id'])


def test_blank_followup_rejected_without_writing_record(client):
    lead=client.post('/api/leads',json={'display_name':'隔离跟进回归客户'}).json()
    assert client.post('/api/leads/'+lead['id']+'/followups',json={'content':' \n\t '}).status_code==422
    assert client.get('/api/leads/'+lead['id']).json()['followups']==[]
    client.delete('/api/leads/'+lead['id'])


def test_procurement_signal_can_cite_separate_in_scope_announcement(client):
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'寻找深圳经销商','client_token':uuid.uuid4().hex}).json()['id']
    body='隔离测试门店是深圳灯具零售门店，主营吊灯。'
    quote='采购人：隔离测试门店。吊灯采购，提交截止：2099-12-31 18:00:00。'
    basic=archive_sources(job,[{'url':'https://example.org/basic-fixture','title':'隔离门店资料','body':body}],'网页正文')[0]
    purchase=archive_sources(job,[{'url':'https://example.org/purchase-fixture','title':'隔离采购公告','body':quote}],'网页正文','procurement')[0]
    candidate=Candidate(display_name='隔离测试门店',city='深圳',buyer_role='retailer',matched_products=['吊灯'],match_reason='隔离测试',facts=[
        {'field':'name','value':'隔离测试门店','source_id':basic['id'],'quote':body},
        {'field':'buyer_role','value':'零售门店','source_id':basic['id'],'quote':body}],
        procurement_signal={'source_id':purchase['id'],'buyer':'隔离测试门店','participant_role':'buyer','stage':'open',
            'deadline':'2099-12-31 18:00:00','quote':quote})
    broker=ToolBroker(job,{'max_leads':1},{'products':[{'name':'吊灯'}]})
    result=asyncio.run(broker.execute('persist_lead',{'candidate':candidate.model_dump()}))
    assert not result.get('error') and result['eligible']
    lead=client.get('/api/leads/'+result['id']).json()
    assert lead['qualification']['signal_score']==10
    assert any(x['source_id']==purchase['id'] and x['quote']==quote for x in lead['evidence'])
    with Session.begin() as db:db.get(Job,job).lead_ids=[]
    client.delete('/api/leads/'+result['id'])
