import asyncio


def test_resumed_company_search_reads_discovered_detail_and_projects_diagnostics(client,monkeypatch):
    import uuid,time
    from app.agent import recover_tools
    from app.research_tools import ToolBroker
    from app import bidresearch_mcp
    from app.db import Session,Conversation,Job,ToolCall
    from app.company_models import Company,TenderRecord
    from app.mcp_tools import network_usage
    from sqlalchemy import select
    name='合成检索恢复软件有限公司';url='http://www.ebnew.com/businessShow/778.html';calls=[]
    row={'source':'ebnew','url':url,'title':name+'软件维保中标公告','published_at':'2024-05-06'}
    async def search(jid,request,options,channel='procurement'):
        calls.append('search')
        if calls.count('search')==1:return {'error':'mcp_timeout','sources':[]}
        return bidresearch_mcp.archive_result(jid,{'records':[row]},request.keywords,365,100,name,mode='history')
    async def detail(jid,request,options):
        calls.append('detail')
        visible={**row,'detail':{'status':'public','text':row['title']+'\n采购人：合成采购学校\n中标人：'+name,
            'parties':[{'role':'winner','name':name,'quote':'中标人：'+name}]}}
        return bidresearch_mcp.archive_result(jid,{'records':[visible]},[name],365,1,name,mode='history')
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true')
    monkeypatch.setattr(bidresearch_mcp,'search',search);monkeypatch.setattr(bidresearch_mcp,'detail',detail)
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='查询'+name,client_token=uuid.uuid4().hex,status='running')
        db.add(j);db.flush();jid=j.id
    options={'bidresearch_enabled':True,'max_bidresearch_calls':2,'bidresearch_max_requests':40,
        'bidresearch_max_details':3,'max_reads':3,'max_searches':3,'enabled_channels':['procurement']}
    asyncio.run(ToolBroker(jid,options,{}).execute('search_tenders',{'keywords':[name],'company':name}))
    with Session.begin() as db:db.get(Job,jid).metrics={'resume_epoch':time.time()}
    result=asyncio.run(recover_tools({'job_id':jid,'options':options,'profile':{},'source_ids':[],
        'intent':'company_query','company_ids':[]}))
    assert calls==['search','search','detail']
    summary=result['company_tender_summary'][name];diagnostics=summary['diagnostics']
    assert summary['records']=={'winner':1}
    assert diagnostics['raw_count']==1 and diagnostics['full_text_count']==1 and diagnostics['confirmed_count']==1
    assert diagnostics['details_attempted']==1 and diagnostics['details_failed']==0 and diagnostics['unique_record_count']==1
    assert result['company_mcp_sources'] and set(result['company_mcp_sources'])<=set(result['source_ids'])
    with Session() as db:
        assert db.get(Company,summary['company_id']).metadata_json['tender_diagnostics']==diagnostics
        assert db.scalar(select(TenderRecord).where(TenderRecord.job_id==jid)).role=='winner'
        assert network_usage(db,jid)=={'searches':2,'reads':1}
        assert len(list(db.scalars(select(ToolCall).where(ToolCall.job_id==jid))))==2


def test_resumed_company_detail_rebuilds_statistics_without_repeating_completed_pages(client,monkeypatch):
    import uuid,time
    from app.agent import recover_tools
    from app.research_tools import ToolBroker
    from app import bidresearch_mcp
    from app.db import Session,Conversation,Job
    from app.company_models import Company
    from app.tender_intel import TenderCollector
    from app.mcp_tools import network_usage
    name='合成详情恢复软件有限公司';calls=[]
    rows=[{'source':'ebnew','url':f'http://www.ebnew.com/businessShow/{n}.html',
        'title':name+f'软件项目{n}中标公告','published_at':'2024-05-06'} for n in (779,780)]
    async def search(jid,request,options,channel='procurement'):
        return bidresearch_mcp.archive_result(jid,{'records':rows},[name],365,100,name,mode='history')
    async def detail(jid,request,options):
        calls.append(request.url)
        if request.url==rows[1]['url'] and calls.count(request.url)==1:return {'error':'mcp_timeout','sources':[]}
        row=next(r for r in rows if r['url']==request.url)
        visible={**row,'detail':{'status':'public','text':row['title']+'\n中标人：'+name,
            'parties':[{'role':'winner','name':name,'quote':'中标人：'+name}]}}
        return bidresearch_mcp.archive_result(jid,{'records':[visible]},[name],365,1,name,mode='history')
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true')
    monkeypatch.setattr(bidresearch_mcp,'search',search);monkeypatch.setattr(bidresearch_mcp,'detail',detail)
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='查询'+name,client_token=uuid.uuid4().hex,status='running')
        db.add(j);db.flush();jid=j.id
    options={'bidresearch_enabled':True,'max_bidresearch_calls':2,'bidresearch_max_requests':40,
        'bidresearch_max_details':4,'max_reads':4,'max_searches':3,'enabled_channels':['procurement']}
    broker=ToolBroker(jid,options,{})
    search_result=asyncio.run(broker.execute('search_tenders',{'keywords':[name],'company':name}))
    collector=TenderCollector(jid,name,options)
    collector.diagnostics={**search_result['diagnostics'],'full_text_count':1,'confirmed_count':1,'details_attempted':2,'details_failed':1}
    first=asyncio.run(broker.execute('get_tender_detail',{'source':'ebnew','url':rows[0]['url'],'company':name}))
    old_summary=collector.consume_mcp(first)
    asyncio.run(broker.execute('get_tender_detail',{'source':'ebnew','url':rows[1]['url'],'company':name}))
    with Session.begin() as db:db.get(Job,jid).metrics={'resume_epoch':time.time()}
    result=asyncio.run(recover_tools({'job_id':jid,'options':options,'profile':{},'source_ids':[s['id'] for s in search_result['sources']],
        'intent':'company_query','company_ids':[],'company_tender_summary':{name:old_summary}}))
    diagnostics=result['company_tender_summary'][name]['diagnostics']
    assert diagnostics['full_text_count']==2 and diagnostics['confirmed_count']==2 and diagnostics['details_failed']==0
    assert diagnostics['details_attempted']==3 and diagnostics['unique_record_count']==2
    assert result['company_tender_summary'][name]['records']=={'winner':2}
    assert calls==[rows[0]['url'],rows[1]['url'],rows[1]['url']]
    with Session() as db:
        assert network_usage(db,jid)=={'searches':1,'reads':3}
        assert db.get(Company,result['company_tender_summary'][name]['company_id']).metadata_json['tender_diagnostics']==diagnostics


def test_failed_detail_is_replayed_on_explicit_resume_without_resetting_read_budget(client,monkeypatch):
    import uuid,time
    from app.agent import recover_tools
    from app.research_tools import ToolBroker
    from app import bidresearch_mcp
    from app.db import Session,Conversation,Job,ToolCall
    from app.gateway import archive_sources
    from app.mcp_tools import network_usage
    from sqlalchemy import select
    calls=[]
    async def detail(jid,request,options):
        calls.append(request.url)
        return {'error':'mcp_timeout','sources':[]} if len(calls)==1 else {'records':[],'sources':[],'recovered':True}
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true');monkeypatch.setattr(bidresearch_mcp,'detail',detail)
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='查询合成恢复有限公司',client_token=uuid.uuid4().hex,status='running');db.add(j);db.flush();jid=j.id
    url='http://www.ebnew.com/businessShow/777.html'
    archive_sources(jid,[{'url':url,'title':'维保服务中标公示','body':'维保服务中标公示','source_meta':{'origin':'bidresearch_mcp','source':'ebnew'}}],'搜索摘录','procurement')
    options={'bidresearch_enabled':True,'bidresearch_max_requests':24,'bidresearch_max_details':3,'max_reads':3,'max_searches':3,'max_leads':1,'enabled_channels':['procurement']}
    asyncio.run(ToolBroker(jid,options,{}).execute('get_tender_detail',{'source':'ebnew','url':url,'company':'合成恢复有限公司'}))
    with Session.begin() as db:db.get(Job,jid).metrics={'resume_epoch':time.time()+1}
    asyncio.run(recover_tools({'job_id':jid,'options':options,'profile':{},'source_ids':[],'intent':'company_query'}))
    assert len(calls)==2
    with Session() as db:
        row=db.scalar(select(ToolCall).where(ToolCall.job_id==jid));assert row.attempts==2
        assert network_usage(db,jid)['reads']==2 and row.arguments['_budgets_total']['requests']==16


def test_fixed_search_step_does_not_spend_another_model_call(monkeypatch):
    from app import agent
    monkeypatch.setattr(agent,'model',lambda:(_ for _ in ()).throw(AssertionError('step already chosen by planner')))
    state={'job_id':'unused','cursor':0,'steps':[{'channel':'procurement','query':'人工智能采购','purpose':'需求'}]}
    value=asyncio.run(agent.decide_node(state))
    assert value['pending_call']['args']=={'channel':'procurement','query':'人工智能采购'}
    assert value['messages'][0].tool_calls[0]['id']==value['pending_call']['tool_call_id']


def test_explicit_resume_replays_failed_mcp_using_public_arguments(client,monkeypatch):
    import uuid,time
    from app.agent import recover_tools
    from app.research_tools import ToolBroker
    from app import bidresearch_mcp
    from app.db import Session,Conversation,Job,ToolCall
    from sqlalchemy import select
    calls=[]
    async def search(jid,request,options,channel='procurement'):
        calls.append(request.keywords)
        if len(calls)==1:return {'error':'mcp_timeout','sources':[]}
        return {'error':'','sources':[],'records':[],'recovered':True}
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true');monkeypatch.setattr(bidresearch_mcp,'search',search)
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='软件采购',client_token=uuid.uuid4().hex);db.add(j);db.flush();jid=j.id
    options={'bidresearch_enabled':True,'max_bidresearch_calls':2,'bidresearch_max_requests':24,'bidresearch_max_details':2,'max_reads':4,'max_searches':3,'enabled_channels':['procurement']}
    asyncio.run(ToolBroker(jid,options,{}).execute('search_tenders',{'keywords':['软件']}))
    with Session.begin() as db:db.get(Job,jid).metrics={'resume_epoch':time.time()+1}
    asyncio.run(recover_tools({'job_id':jid,'options':options,'profile':{},'source_ids':[],'intent':'research'}))
    assert len(calls)==2
    with Session() as db:
        row=db.scalar(select(ToolCall).where(ToolCall.job_id==jid))
        assert row.attempts==2 and row.result['recovered']


def test_resumed_tender_preserves_new_company_in_checkpoint(client,monkeypatch):
    import uuid,time
    from datetime import date
    from app.agent import recover_tools
    from app.research_tools import ToolBroker
    from app import bidresearch_mcp
    from app.db import Session,Conversation,Job
    calls=[]
    async def search(jid,request,options,channel='procurement'):
        calls.append(request)
        if len(calls)==1:return {'error':'mcp_timeout','sources':[]}
        row={'source':'ggzy','url':'https://www.ggzy.gov.cn/resumed-company',
            'title':'合成学校软件开发采购公告','published_at':date.today().isoformat(),
            'detail':{'status':'public','text':'合成学校软件开发采购公告\n项目编号：T-01\n采购人：合成学校\n采购需求：软件开发。',
                'parties':[{'role':'buyer','name':'合成学校','quote':'采购人：合成学校'}]}}
        return bidresearch_mcp.archive_result(jid,{'records':[row]},request.keywords,30,5,request.company,channel)
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true')
    monkeypatch.setattr(bidresearch_mcp,'search',search)
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='查合成学校采购',client_token=uuid.uuid4().hex)
        db.add(j);db.flush();jid=j.id
    options={'bidresearch_enabled':True,'max_bidresearch_calls':2,'bidresearch_max_requests':24,
        'bidresearch_max_details':2,'max_reads':4,'max_searches':3,'enabled_channels':['procurement']}
    asyncio.run(ToolBroker(jid,options,{}).execute('search_tenders',{'keywords':['合成学校'],'company':'合成学校'}))
    with Session.begin() as db:db.get(Job,jid).metrics={'resume_epoch':time.time()+1}
    result=asyncio.run(recover_tools({'job_id':jid,'options':options,'profile':{},'source_ids':[],
        'intent':'company_query','company_ids':[]}))
    company_id=result['company_tender_summary']['合成学校']['company_id']
    assert company_id and company_id in result['company_ids']
    with Session() as db:assert company_id in db.get(Job,jid).company_ids


def test_tender_consumer_rechecks_amount_column_from_cached_mcp_result(client,monkeypatch):
    import uuid
    from app.db import Session,Conversation,Job
    from app.gateway import archive_sources
    from app.tender_intel import TenderCollector
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt='合成学校',client_token=uuid.uuid4().hex)
        db.add(job);db.flush();jid=job.id
    table='预算金额（万元） | 成交金额（万元）\n80 | 500'
    row=archive_sources(jid,[{'title':'合成学校软件开发采购公告','body':'采购人：合成学校\n'+table,
        'url':'https://www.ggzy.gov.cn/amount-check'}],'网页正文','procurement')[0]
    result={'records':[{'title':row['title'],'source':'ggzy','source_id':row['id'],'has_full_text':True,'published_at':'2026-10-13',
        'parties':[{'role':'buyer','name':'合成学校','quote':'采购人：合成学校'}],
        'amounts':[{'kind':'budget','label':'预算金额（万元）','original':'500','display_value':'500万元','quote':table}]}]}
    monkeypatch.setattr(TenderCollector,'persist',lambda self:self.records)
    records=TenderCollector(jid,'合成学校',{}).consume_mcp(result)
    assert len(records)==1 and next(iter(records.values()))['budget']==''
