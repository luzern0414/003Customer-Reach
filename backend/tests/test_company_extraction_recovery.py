"""企业正文主体筛选与SDK超时降级回归，不请求外部网页或模型。"""
import asyncio
import uuid
import httpx
import pytest


def test_unrelated_body_is_not_sent_for_company_extraction(client,monkeypatch):
    """搜索发现的其他公司原文不会因相关性被送作目标身份；Evidence原始归档保留。"""
    from app import agent
    from app.db import Session, Evidence
    from app.company_research import company_extract
    async def forbidden(*args,**kwargs):raise AssertionError('无目标主体的正文不应调用提取模型')
    monkeypatch.setattr(agent,'cached_model',forbidden)
    with Session.begin() as db:
        source=Evidence(body='公司名称：福建船政重工股份有限公司。'+('此处仅为隔离验证其他主体的原文。'*20),title='福建船政重工股份有限公司',url='https://example.com/'+uuid.uuid4().hex,kind='网页正文');db.add(source);db.flush();sid=source.id
    result=asyncio.run(company_extract({'company_new_source_ids':[sid],'company_targets':['福州船厂']}))
    assert result['company_batches']==[]
    with Session() as db:assert db.get(Evidence,sid)


def test_finished_research_requests_identity_when_only_other_subjects_read(client):
    """真正已读页仍无法确认主体时请求全称，无正文或预算未结束不提前询问。"""
    from app.db import Session, Evidence
    from app.company_research import company_gap
    with Session.begin() as db:
        source=Evidence(body='公司名称：其他企业。'+('这是主体消歧的隔离测试正文。'*20),title='其他企业',url='https://example.com/'+uuid.uuid4().hex,kind='网页正文');db.add(source);db.flush();sid=source.id
    state={'job_id':uuid.uuid4().hex,'options':{'max_searches':3,'max_reads':6},'steps':[],
        'source_ids':[sid],'company_targets':['福州船厂'],'company_ids':[]}
    result=asyncio.run(company_gap(state));assert '企业全称' in result['company_questions'][0]
    assert asyncio.run(company_gap({**state,'source_ids':[]}))['company_questions']==[]
    assert asyncio.run(company_gap({**state,'steps':[{'query':'下一查询'}]}))['company_questions']==[]


@pytest.mark.parametrize('budget_error',[False,True])
def test_sdk_timeout_preserves_gap_but_budget_still_raises(client,monkeypatch,budget_error):
    """只替模型异常，保留实际来源、节点和事件；预算不得被当作SDK超时继续。"""
    from app import agent
    from app.db import Session, Job, Conversation, Evidence, JobEvent
    from app.company_research import company_extract
    from app.service import ServiceError
    from sqlalchemy import select
    from openai import APITimeoutError
    async def fail(*args,**kwargs):
        if budget_error:raise ServiceError('任务模型预算已耗尽')
        raise APITimeoutError(request=httpx.Request('POST','https://example.com/model'))
    monkeypatch.setattr(agent,'cached_model',fail)
    name='超时验证'+uuid.uuid4().hex+'有限公司'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt='查询'+name,client_token=uuid.uuid4().hex);db.add(job);db.flush()
        source=Evidence(job_id=job.id,body='公司名称：'+name+'。'+('这是隔离验证的企业原文。'*20),title=name,url='https://example.com/'+uuid.uuid4().hex,kind='网页正文');db.add(source);db.flush();sid=source.id;jid=job.id
    state={'job_id':jid,'company_new_source_ids':[sid],'company_targets':[name],'prompt':'查询'+name,'warnings':[]}
    if budget_error:
        with pytest.raises(ServiceError,match='预算'):asyncio.run(company_extract(state))
    else:
        result=asyncio.run(company_extract(state));assert result['company_batches']==[] and '超时' in result['warnings'][0]
        with Session() as db:
            assert db.scalar(select(JobEvent).where(JobEvent.job_id==jid,JobEvent.event_type=='extract.partial'))
            assert db.get(Job,jid).company_ids==[]
