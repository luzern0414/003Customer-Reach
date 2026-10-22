import asyncio
import json
import uuid


def test_reposted_mcp_details_keep_both_sources_but_one_event(client):
    from app.db import Session,Job,Conversation
    from app.gateway import archive_sources
    from app.tender_intel import TenderCollector
    from app.company_service import company_detail
    with Session.begin() as db:
        conversation=Conversation();db.add(conversation);db.flush()
        job=Job(prompt='查询合成电子有限公司',conversation_id=conversation.id,status='running');db.add(job);db.flush();jid=job.id
    body='维保服务中标结果公告\n采购人：合成学校\n第二中标人：合成电子有限公司\n成交金额：***元。'
    collector=TenderCollector(jid,'合成电子有限公司',{})
    for index,text in enumerate([body+'\n来源：中国邮政网',body.replace('采购人：','采购人：\n')]):
        source=archive_sources(jid,[{'url':f'http://www.ebnew.com/businessShow/{index}.html','title':'维保服务中标结果公告','body':text}],'网页正文','procurement')[0]
        result=collector.consume_mcp({'records':[{'source_id':source['id'],'has_full_text':True,'title':'维保服务中标结果公告','published_at':'2020-01-19','source':'ebnew',
            'parties':[{'role':'winner','label':'第二中标人','name':'合成电子有限公司','quote':'第二中标人：合成电子有限公司'},
                       {'role':'buyer','label':'采购人','name':'合成学校','quote':'采购人：合成学校' if index==0 else '采购人：\n合成学校'}]}]})
    detail=company_detail(result['company_id'])
    assert detail['tenders']['summary']['wins']==1
    assert len(detail['sources'])==2
    assert detail['tenders']['relations']['customer'][0]['count']==1


def test_legacy_mcp_key_is_reused_on_same_visible_notice(client):
    from app.db import Session,Job,Conversation
    from app.company_models import TenderRecord
    from app.gateway import archive_sources
    from app.tender_intel import TenderCollector,stable_key
    from app.company_service import company_detail
    from sqlalchemy import select
    import hashlib,re
    with Session.begin() as db:
        conversation=Conversation();db.add(conversation);db.flush()
        job=Job(prompt='查询合成旧键电子有限公司',conversation_id=conversation.id,status='running');db.add(job);db.flush();jid=job.id
    body='维保服务中标结果公告\n采购人：合成学校\n第二中标人：合成旧键电子有限公司\n来源：中国邮政网'
    source=archive_sources(jid,[{'url':'http://www.ebnew.com/businessShow/555.html','title':'维保服务中标结果公告','body':body}],'网页正文','procurement')[0]
    result={'records':[{'source_id':source['id'],'has_full_text':True,'title':'维保服务中标结果公告','published_at':'2020-01-19','source':'ebnew',
        'parties':[{'role':'winner','label':'第二中标人','name':'合成旧键电子有限公司','quote':'第二中标人：合成旧键电子有限公司'}]}]}
    saved=TenderCollector(jid,'合成旧键电子有限公司',{}).consume_mcp(result)
    with Session.begin() as db:
        row=db.scalar(select(TenderRecord).where(TenderRecord.company_id==saved['company_id']))
        old=stable_key('mcp-notice-2',re.sub(r'\s+','','维保服务中标结果公告'),'','2020-01-19',hashlib.sha256(re.sub(r'\s+','',body).encode()).hexdigest())
        row.payload={**row.payload,'mcp_record_key':old};row.unique_key=stable_key('tender-record',saved['company_id'],old)
    TenderCollector(jid,'合成旧键电子有限公司',{}).consume_mcp(result)
    with Session() as db:
        rows=[(r.title,r.url,r.published_at,r.payload) for r in db.scalars(select(TenderRecord).where(TenderRecord.company_id==saved['company_id']))]
    assert company_detail(saved['company_id'])['tenders']['summary']['wins']==1,rows


def test_failed_attempt_updates_diagnostics_without_erasing_saved_notices(client):
    from app.db import Session
    from app.company_service import ensure_company,company_detail
    from app.tender_intel import TenderCollector
    with Session.begin() as db:
        company=ensure_company(db,'合成诊断有限公司',visibility='primary',origin='agent');cid=company.id
        company.metadata_json={'tender_diagnostics':{'mode':'history','full_text_count':4,'confirmed_count':4}}
    collector=TenderCollector('failure-diagnostics','合成诊断有限公司',{})
    collector.diagnostics={'mode':'history','raw_count':50,'details_failed':4,'full_text_count':0,'confirmed_count':0}
    collector.consume_mcp({'records':[],'error':'mcp_timeout'})
    assert company_detail(cid)['tenders']['diagnostics']['details_failed']==4
    assert company_detail(cid)['tenders']['diagnostics']['confirmed_count']==0


def test_cross_job_reread_preserves_sources_and_corrects_old_customer(client):
    from app.db import Session,Job,Conversation
    from app.company_models import TenderRecord,TenderRelation
    from app.gateway import archive_sources
    from app.tender_intel import TenderCollector,stable_key
    from app.company_service import company_detail
    from sqlalchemy import select
    from pathlib import Path
    # Derived offline fixture isolates this company from other tests; live source is unchanged.
    name='跨任务复核电子有限公司'
    body=(Path(__file__).parent/'fixtures/tender/ebnew-705768958-visible.txt').read_text(encoding='utf8').replace('成都宏天智电子有限公司',name)
    for turn in range(2):
        with Session.begin() as db:
            conversation=Conversation();db.add(conversation);db.flush()
            job=Job(prompt='查询'+name,conversation_id=conversation.id,status='running');db.add(job);db.flush();jid=job.id
        source=archive_sources(jid,[{'url':'http://www.ebnew.com/businessShow/705768958.html','title':'四川邮政技防服务项目中标结果公告','body':body}],'网页正文','procurement')[0]
        result=TenderCollector(jid,name,{}).consume_mcp({'records':[{'source_id':source['id'],'has_full_text':True,'title':'四川邮政技防服务项目中标结果公告','published_at':'2025-12-10','source':'ebnew',
            'parties':[{'role':'winner','label':'中标人','name':name,'quote':'中标人：'+name},
                       {'role':'buyer','label':'招标人','name':'中国邮政集团有限公司四川省分公司','quote':'招标人：中国邮政集团有限公司四川省分公司'}]}]})
        if turn==0:
            with Session.begin() as db:
                row=db.scalar(select(TenderRecord).where(TenderRecord.company_id==result['company_id']));row.role='winner'
                db.add(TenderRelation(company_id=result['company_id'],unique_key=stable_key('old-customer',jid),relation_type='customer',
                    counterparty_name='中国邮政集团有限公司四川省分公司',basis='records',deal_count=1,record_ids=[row.id]))
    detail=company_detail(result['company_id'])
    assert len(detail['sources'])==2
    assert detail['tenders']['summary']['candidates']==1 and detail['tenders']['summary']['customers']==0


def test_company_mcp_navigation_is_scheduled_but_not_saved(client,monkeypatch):
    from app import company_research
    from app.tender_intel import company_tenders
    from app.gateway import archive_sources
    from app.db import Session,Job
    monkeypatch.setenv('CLIENTREACH_TENDER_ENABLED','true')
    with Session.begin() as db:
        job=Job(prompt='查询合成电子有限公司采购',status='running');db.add(job);db.flush();jid=job.id
    source=archive_sources(jid,[{'title':'维保服务候选人公示','url':'http://www.ebnew.com/businessShow/123.html',
        'body':'维保服务候选人公示','source_meta':{'origin':'bidresearch_mcp','navigation_only':True}}],'搜索摘录','procurement')[0]
    class Broker:
        allowed_sources=set()
        async def execute(self,*args,**kwargs):
            return {'sources':[source],'records':[{'source_id':source['id'],'has_full_text':False}],'coverage':[]}
    monkeypatch.setattr(company_research,'broker_for',lambda state:Broker())
    state={'job_id':jid,'company_intent_targets':['合成电子有限公司'],
        'company_direct_urls':[{'url':'https://example.com/known','channel':'official'}],
        'options':{'bidresearch_enabled':True,'enabled_channels':['procurement'],'tender_enabled':True}}
    result=asyncio.run(company_tenders(state))
    assert {'url':source['url'],'channel':'procurement'} in result['company_direct_urls']
    assert len(result['company_direct_urls'])==2 and not result['company_ids']


def test_qcc_enrichment_saves_only_exact_company_and_path_facts(client, monkeypatch):
    monkeypatch.setenv('CLIENTREACH_QCC_ENABLED','true')
    from app.company_mcp import enrich_company
    from app import company_research
    from app.qcc_mcp import archive_qcc_result,QccCallResult
    from app.db import Session,Conversation,Job
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush()
        j=Job(conversation_id=c.id,client_token=uuid.uuid4().hex,prompt='查合成软件有限公司主营');db.add(j);db.flush();jid=j.id
    response={'企业名称':'合成软件有限公司','统一社会信用代码':'911101000000000000','经营范围':'软件开发；人工智能应用软件开发。','注册地址':'合成地址'}
    source=archive_qcc_result(jid,QccCallResult('company','get_company_registration_info',response,'synthetic-hash','2026-10-13'),'企查查合成软件有限公司')
    class Broker:
        allowed_sources={source['id']}
        async def execute(self,name,args):
            if name=='qcc_company_lookup':return {'sources':[source],'error':''}
            from app.company_validation import save_snapshot
            from app.company_research_schemas import CompanySnapshot
            return save_snapshot(jid,CompanySnapshot.model_validate(args['snapshot']),self.allowed_sources,args['targets'])
    monkeypatch.setattr(company_research,'broker_for',lambda s:Broker())
    state={'job_id':jid,'options':{'qcc_enabled':True,'max_qcc_calls':1},'company_intent_targets':['合成软件有限公司'],
        'company_requested_fields':['business'],'source_ids':[]}
    result=asyncio.run(enrich_company(state))
    assert result['company_ids'] and result['company_receipts'][0]['accepted_fields']>=2
    assert result['source_ids']==[source['id']]


def test_zero_budget_or_explicit_only_skips_enrichment(monkeypatch):
    from app.company_mcp import enrich_company
    from app import company_research
    monkeypatch.setattr(company_research,'broker_for',lambda s:(_ for _ in ()).throw(AssertionError('must not create broker')))
    assert asyncio.run(enrich_company({'options':{'qcc_enabled':True,'max_qcc_calls':0}}))=={}
    assert asyncio.run(enrich_company({'options':{'qcc_enabled':True,'max_qcc_calls':4},'reference_only':True}))=={}


def test_authorized_company_cannot_borrow_shareholder_fields(client):
    from app.company_validation import save_snapshot
    from app.company_research_schemas import CompanySnapshot
    from app.qcc_mcp import archive_qcc_result,QccCallResult
    from app.db import Session,Conversation,Job
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush()
        j=Job(conversation_id=c.id,prompt='合成软件有限公司',client_token=uuid.uuid4().hex);db.add(j);db.flush();jid=j.id
    body={'企业名称':'合成软件有限公司','注册地址':'本企业地址','股东':[{'企业名称':'合成股东有限公司','注册地址':'股东地址'}]}
    s=archive_qcc_result(jid,QccCallResult('company','basic',body,uuid.uuid4().hex,''),'合成软件有限公司工商')
    result=save_snapshot(jid,CompanySnapshot(name='合成软件有限公司',source_id=s['id'],identity_quote='$.企业名称: 合成软件有限公司',
        facts=[{'field':'address','label':'地址','value':'股东地址','source_id':s['id'],'quote':'$.股东[0].注册地址: 股东地址'}]),{s['id']},['合成软件有限公司'])
    assert result['accepted_fields']==0 and result['rejected']


def test_company_collect_consumes_archived_mcp_detail_without_refetch(client,monkeypatch):
    from app import company_research as module
    source={'id':'synthetic-full','kind':'网页正文','url':'https://www.ggzy.gov.cn/test','title':'合成企业软件采购','body':'采购需求：软件开发',
            'source_meta':{'origin':'bidresearch_mcp'}}
    class Broker:
        async def execute(self,name,args):
            assert name=='search_accounts','MCP detail must not be fetched again'
            return {'sources':[source]}
    monkeypatch.setattr(module,'broker_for',lambda state:Broker())
    result=asyncio.run(module.company_collect({'job_id':'unused','options':{'research_read_concurrency':2},'company_targets':['合成企业'],
        'steps':[{'entity_name':'合成企业','channel':'procurement','query':'合成企业采购'}],'source_ids':[]}))
    assert result['company_new_source_ids']==[source['id']]


def test_tender_mcp_keeps_exact_roles_and_separate_notice_dates(client,monkeypatch):
    from app.tender_intel import TenderCollector
    from app.gateway import archive_sources
    from app.db import Session,Conversation,Job
    from app.company_service import company_detail
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush()
        j=Job(conversation_id=c.id,prompt='合成软件有限公司采购',client_token=uuid.uuid4().hex);db.add(j);db.flush();jid=j.id
    body='软件开发采购公告\n采购人：合成软件有限公司\n预算金额：80万元。\n供应商：另一个公司\n采购需求：知识库软件开发。'
    rows=[]
    for day in ('2026-10-01','2026-10-02'):
        s=archive_sources(jid,[{'title':'软件开发采购公告','body':body,'url':'https://www.ggzy.gov.cn/'+day}],'网页正文','procurement')[0]
        rows.append({'source_id':s['id'],'title':'软件开发采购公告','url':s['url'],'published_at':day,'has_full_text':True,'source':'ggzy',
            'parties':[{'role':'buyer','name':'合成软件有限公司','quote':'采购人：合成软件有限公司'}],'amounts':[]})
    c=TenderCollector(jid,'合成软件有限公司',{})
    result=c.consume_mcp({'records':rows,'coverage':[]})
    assert result['records']=={'buyer':2}
    assert len(company_detail(result['company_id'])['tenders']['purchases'])==2


def test_tender_record_details_reach_both_company_answer_paths(client,monkeypatch):
    from datetime import date
    from types import SimpleNamespace
    from app import company_research
    from app.bidresearch_mcp import archive_result
    from app.tender_intel import TenderCollector
    from app.db import Session,Conversation,Job
    captured=[]
    class Model:
        async def astream(self,messages):
            captured.append(messages[-1].content)
            yield SimpleNamespace(content='合成企业回答')
    monkeypatch.setattr(company_research,'model',lambda:Model())
    for direct in (True,False):
        prompt='合成学校' if direct else '查看合成学校软件开发项目预算和投标截止时间'
        with Session.begin() as db:
            c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt=prompt,client_token=uuid.uuid4().hex,status='running')
            db.add(j);db.flush();jid=j.id
        body='项目编号：TEST-BUDGET\n项目名称：教学软件开发采购\n预算金额（元）：1504100\n提交响应文件截止时间：2099年10月16日 09:30\n采购人：合成学校'
        row={'source':'ggzy','url':'https://www.ggzy.gov.cn/company-budget-'+jid,'title':'合成学校教学软件开发采购公告',
            'published_at':date.today().isoformat(),'detail':{'status':'public','text':body,
                'parties':[{'role':'buyer','name':'合成学校','quote':'采购人：合成学校'}],
                'amounts':[{'kind':'budget','label':'预算金额（元）','original':'1504100','quote':'预算金额（元）：1504100'}]}}
        result=archive_result(jid,{'records':[row]},['合成学校'],30,5,company='合成学校')
        summary=TenderCollector(jid,'合成学校',{}).consume_mcp(result)
        state={'job_id':jid,'conversation_id':c.id,'prompt':prompt,'company_ids':[summary['company_id']],
            'company_targets':['合成学校'],'company_tender_summary':{'合成学校':summary},'source_ids':[s['id'] for s in result['sources']]}
        answer=asyncio.run(company_research.company_answer(state))['answer']
        value=answer if direct else captured[-1]
        for expected in ('1504100','TEST-BUDGET',row['url'],'2099-10-16 09:30:00'):
            assert expected in value
