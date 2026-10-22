"""企业查询路由、短确认、主体补充与真实API保存联动的本地隔离回归。"""
import uuid
import asyncio
import pytest
from app.conversation import company_intent, company_request, short_title


@pytest.mark.parametrize('content',[
    '查询福州船厂的信息','查一下福州船厂','帮我查询海能技术的资料',
    '查询比亚迪的信息','研究福州船厂的完整画像和采购信息',
])
def test_enterprise_query_without_company_suffix(content):
    """企业简称/非公司后缀同样授权结构化研究。"""
    assert company_intent(content)


@pytest.mark.parametrize('content',[
    '解释福州船厂的采购信息','如何查询公司的信息','查询今天的天气信息',
    '查询上一轮的结果信息','不要查询福州船厂的信息','翻译查询福州船厂的信息',
    '我们销售灯具，寻找深圳经销商客户','你好','今天几号',
])
def test_plain_question_cannot_authorize_company_research(content):
    """解释、禁止检索与普通问答不应意外产生公网任务。"""
    assert not company_intent(content)


def test_confirmation_stays_with_immediate_company_request():
    """历史仅在明确短确认时提供主体；普通问答隔断历史，附件不承接企业路线。"""
    previous=[{'prompt':'查询福州船厂的信息','query_mode':'auto','status':'completed'}]
    assert '福州船厂' in company_request('都要',previous=previous)
    assert not company_request('谢谢',previous=previous)
    assert not company_request('今天几号',previous=previous)
    assert not company_request('都要',previous=[{'prompt':'今天几号'},*previous])
    assert not company_request('都要',attachment_ids=['attachment'],previous=previous)
    assert not company_request('都要')
    assert '福州船厂' in company_request('继续',previous=[{'prompt':'都要'},*previous])
    missing=[{'prompt':'查询一家企业的完整画像','query_mode':'company_query','status':'needs_input'}]
    assert '福州船厂' in company_request('福州船厂',previous=missing)
    assert not company_request('福州船厂',previous=previous)


def test_submit_persists_routing_and_original_confirmation(client):
    """实际API保留用户“都要”原文、幂等与同会话研究上下文，不改写历史消息。"""
    from app.db import Session, Job
    conv=client.post('/api/conversations').json()['id']
    first=client.post(f'/api/conversations/{conv}/messages',json={'content':'查询福州船厂的信息','client_token':uuid.uuid4().hex}).json()
    assert first['status']=='queued' and first['metrics']['intent_pending']
    from app.intent import intent_node
    from app.service import settings
    asyncio.run(intent_node({'job_id':first['id'],'prompt':first['prompt'],'options':settings()}))
    first=client.get('/api/jobs/'+first['id']).json()
    assert first['query_mode']=='company_query' and first['metrics']['intent']=='company_query'
    with Session.begin() as db:db.get(Job,first['id']).status='completed'
    token=uuid.uuid4().hex
    confirmation=client.post(f'/api/conversations/{conv}/messages',json={'content':'都要','client_token':token}).json()
    assert confirmation['prompt']=='都要' and confirmation['metrics']['intent_pending']
    asyncio.run(intent_node({'job_id':confirmation['id'],'prompt':confirmation['prompt'],'options':settings()}))
    confirmation=client.get('/api/jobs/'+confirmation['id']).json()
    assert confirmation['metrics']['research_prompt']=='查询福州船厂的信息\n本轮补充：都要'
    assert client.post(f'/api/conversations/{conv}/messages',json={'content':'都要','client_token':token}).json()['id']==confirmation['id']
    detail=client.get(f'/api/conversations/{conv}').json()
    assert detail['title']=='福州船厂研究' and detail['messages'][-1]['content']=='都要'
    assert next(row for row in client.get('/api/conversations').json() if row['id']==conv)['title']==detail['title']


def test_short_title_is_bounded_and_stable():
    """多次投影不重复追加标题后缀，长问题只影响短标题而不裁剪原需求。"""
    assert short_title('查询福州船厂的信息')=='福州船厂研究'
    title=short_title('研究比亚迪股份有限公司的完整企业画像、采购信息与上下游关系')
    assert len(title)<=10 and short_title(title)==title
    assert short_title('查询海能未来技术集团股份有限公司的信息')!='多企业研究'
    assert short_title('查询海能未来技术集团股份有限公司和比亚迪股份有限公司的信息')=='多企业研究'
