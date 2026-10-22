"""企业链路退化与多源预算回归；隔离数据库，外部服务故障使用明确替身。"""
import asyncio
import json
import uuid
import httpx
import pytest


def job(client, prompt):
    from app.db import Session, Job, Conversation
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush()
        row=Job(conversation_id=conv.id,prompt=prompt,status='running');db.add(row);db.flush()
        return row.id


@pytest.mark.parametrize('error',['connection','timeout'])
def test_plan_service_failure_continues_authorized_queries(client,monkeypatch,error):
    from app import agent
    from app.company_research import company_plan
    from openai import APIConnectionError, APITimeoutError
    name='链路验证电子有限公司';jid=job(client,name)
    async def failed(*args):
        request=httpx.Request('POST','https://model.example.invalid')
        raise (APIConnectionError(request=request) if error=='connection' else APITimeoutError(request=request))
    monkeypatch.setattr(agent,'cached_model',failed)
    state={'job_id':jid,'prompt':name,'context':name,'company_intent_targets':[name],
        'company_requested_fields':['name','business','products','procurement','customer','supplier'],
        'options':{'enabled_channels':['official','procurement'],'max_searches':8}}
    result=asyncio.run(company_plan(state))
    assert result['company_targets']==[name] and result['steps'] and result['warnings']
    assert all(step['entity_name']==name and step['channel'] in state['options']['enabled_channels'] for step in result['steps'])
    assert any('公共资源交易' in step['query'] for step in result['steps'])
    assert 'https://' not in json.dumps(result['steps'])


def test_plan_budget_failure_does_not_fallback(client,monkeypatch):
    from app import agent
    from app.company_research import company_plan
    from app.service import ServiceError
    async def failed(*args):raise ServiceError('任务模型预算已耗尽')
    monkeypatch.setattr(agent,'cached_model',failed)
    with pytest.raises(ServiceError):asyncio.run(company_plan({'job_id':job(client,'合成有限公司'),
        'prompt':'合成有限公司','context':'合成有限公司','company_intent_targets':['合成有限公司'],
        'options':{'enabled_channels':['official'],'max_searches':8}}))


def test_procurement_plan_queries_original_web_after_platform_listing(client,monkeypatch):
    from app.research_tools import ToolBroker
    from app.db import Session,ToolCall
    name='跨源验证有限公司';jid=job(client,name)
    with Session.begin() as db:
        db.add(ToolCall(job_id=jid,tool='search_tenders',channel='bidresearch',operation_id=uuid.uuid4().hex,status='completed',
            arguments={'company':name},result={'records':[{'url':'http://www.ebnew.com/businessShow/123.html'}]}))
    broker=ToolBroker(jid,{'bidresearch_enabled':True,'enabled_channels':['procurement'],'research_targets':[name]}, {})
    async def forbidden(*args):raise AssertionError('已取得平台列表，不再次劫持公共资源补查')
    async def web(name,args):return {'sources':[],'query':args['query'],'provider':'exa'}
    monkeypatch.setattr(broker,'search_tenders',forbidden);monkeypatch.setattr(broker,'_execute',web)
    result=asyncio.run(broker.execute('search_accounts',{'channel':'procurement','query':name+' 公共资源交易 评标 投标报价'}))
    assert result['provider']=='exa'


def test_qcc_registration_is_not_discarded_before_ui(client,monkeypatch):
    from app import company_research
    from app.company_mcp import enrich_company
    from app.qcc_mcp import archive_qcc_result,QccCallResult
    from app.company_service import company_detail
    from app.company_validation import save_snapshot
    from app.company_research_schemas import CompanySnapshot
    name='工商完整验证有限公司';jid=job(client,name)
    source=archive_qcc_result(jid,QccCallResult('company','get_company_registration_info',{
        '企业名称':name,'法定代表人':'合成法人','注册资本':'1110万元','实缴资本':'1110万元','成立日期':'2007-03-15','核准日期':'2007-03-15',
        '工商注册号':'510107000000000','登记状态':'存续','企业类型':'有限责任公司',
        '经营范围':'软件开发；信息系统集成。'},'fixture','2026-10-14'),name)
    class Broker:
        async def execute(self,tool,args):
            if tool=='qcc_company_lookup':return {'sources':[source]}
            return save_snapshot(jid,CompanySnapshot.model_validate(args['snapshot']),{source['id']},args['targets'])
    monkeypatch.setenv('CLIENTREACH_QCC_ENABLED','true');monkeypatch.setattr(company_research,'broker_for',lambda state:Broker())
    result=asyncio.run(enrich_company({'job_id':jid,'company_intent_targets':[name],
        'options':{'qcc_enabled':True,'max_qcc_calls':1}}))
    detail=company_detail(result['company_ids'][0])
    values={f['label']:f['value'] for f in detail['registration']['fields']}
    assert values['注册资本']=='1110万元' and values['法定代表人']=='合成法人' and values['成立日期']=='2007-03-15'
    assert values['实缴资本']=='1110万元' and values['核准日期']=='2007-03-15' and values['工商注册号']=='510107000000000'
    assert any(f['label']=='工商注册号' and f['evidence_refs'] for f in detail['facts'])


def test_competitor_intent_field_survives_to_coverage(client,monkeypatch):
    from app import intent
    from app.company_research_schemas import IntentDecision
    name='竞争验证有限公司';jid=job(client,name+'竞争对手')
    async def recognize(state):return IntentDecision(intent='company_query',targets=[name],requested_fields=['name','competitor'])
    monkeypatch.setattr(intent,'recognize_intent',recognize)
    result=asyncio.run(intent.intent_node({'job_id':jid,'prompt':name+'竞争对手','options':{'enabled_channels':['official','procurement']}}))
    assert 'competitor' in result['company_requested_fields']


def test_tender_coverage_is_per_target_not_global():
    from app.company_research import apply_tender_coverage
    coverage={'missing_fields':['customer'],'companies':[{'target':'A','missing_fields':['customer']},{'target':'B','missing_fields':['customer']}]}
    result=apply_tender_coverage(coverage,{'company_tender_summary':{'A':{'relations':{'customer':1}}}})
    assert result['companies'][0]['missing_fields']==[]
    assert result['companies'][1]['missing_fields']==['customer'] and result['missing_fields']==['customer']
