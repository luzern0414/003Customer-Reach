import asyncio
from datetime import date
import pytest


def test_history_keeps_old_company_navigation_and_reports_recent_filter(client):
    from app.bidresearch_mcp import archive_result, BidSearch
    row={'source':'ebnew','url':'http://www.ebnew.com/businessShow/111.html','title':'安防维保中标公示',
         'published_at':'2020-01-19','query':'合成电子有限公司',
         'list_evidence':{'url':'https://ss.ebnew.com/tradingSearch/index.htm','sha256':'fixture'},'detail':{'status':'not_requested'}}
    request=BidSearch(keywords=['合成电子有限公司'],company='合成电子有限公司')
    assert request.mode=='history' and request.pages==5 and request.limit==100
    historical=archive_result('history-fixture',{'records':[row]},request.keywords,365,100,request.company,mode='history')
    assert len(historical['records'])==1 and historical['diagnostics']['raw_count']==1
    recent=archive_result('recent-fixture',{'records':[row]},request.keywords,365,100,request.company,mode='recent')
    assert not recent['records'] and recent['diagnostics']['date_rejected']==1


def test_numbered_winner_is_grounded_but_candidate_is_not():
    from app.bidresearch_mcp import grounded_party
    text='第二中标人：成都宏天智电子有限公司'
    assert grounded_party(text,{'role':'winner','label':'第二中标人','name':'成都宏天智电子有限公司','quote':text})
    candidate='第二中标候选人：成都宏天智电子有限公司'
    assert not grounded_party(candidate,{'role':'winner','label':'第二中标候选人','name':'成都宏天智电子有限公司','quote':candidate})


def test_detail_requires_discovered_url_and_spends_one_read_once(client,monkeypatch):
    from app import bidresearch_mcp as module
    from app.research_tools import ToolBroker
    from app.db import Session,Job,ToolCall
    from app.gateway import archive_sources
    from app.mcp_tools import network_usage
    from sqlalchemy import select
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true')
    calls=[]
    async def detail(jid,request,options):
        calls.append(request.url);return {'sources':[],'records':[],'diagnostics':{'raw_count':1}}
    monkeypatch.setattr(module,'detail',detail)
    with Session.begin() as db:
        job=Job(prompt='研究合成电子有限公司',status='running');db.add(job);db.flush();jid=job.id
    opts={'bidresearch_enabled':True,'enabled_channels':['procurement'],'max_reads':1,'bidresearch_max_details':4,
          'bidresearch_max_requests':12,'max_searches':2,'max_bidresearch_calls':2,'max_leads':1}
    broker=ToolBroker(jid,opts,{'products':[]})
    args={'source':'ebnew','url':'http://www.ebnew.com/businessShow/111.html','company':'合成电子有限公司'}
    assert asyncio.run(broker.execute('get_tender_detail',args))['error']=='source_not_allowed'
    sources=archive_sources(jid,[{'url':args['url'],'title':'安防中标公示','body':'安防中标公示',
        'source_meta':{'origin':'bidresearch_mcp','source':'ebnew','query':'合成电子有限公司','navigation_only':True}}],'搜索摘录','procurement')
    broker.allowed_sources.update(s['id'] for s in sources)
    asyncio.run(broker.execute('get_tender_detail',args))
    assert asyncio.run(broker.execute('get_tender_detail',args))['reused']
    assert calls==[args['url']]
    with Session() as db:
        assert network_usage(db,jid)['reads']==1
        assert db.scalar(select(ToolCall).where(ToolCall.job_id==jid)).arguments['_budgets_total']['requests']==8
    second={**args,'url':'http://www.ebnew.com/businessShow/222.html'}
    broker.allowed_sources.update(s['id'] for s in archive_sources(jid,[{'url':second['url'],'title':'第二公告','body':'第二公告',
        'source_meta':{'origin':'bidresearch_mcp','source':'ebnew'}}],'搜索摘录','procurement'))
    assert asyncio.run(broker.execute('get_tender_detail',second))['error']=='budget_exhausted'
    assert calls==[args['url']]


def test_absolute_launcher_and_detail_whitelist_work_from_caller_directory(monkeypatch,tmp_path):
    import mcp
    import mcp.client.stdio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from app import bidresearch_mcp as module
    launcher=tmp_path/'scripts/run_mcp.py';launcher.parent.mkdir();launcher.write_text('# fixture',encoding='utf8')
    monkeypatch.setattr(module,'runtime_status',lambda:{'installed':True,'python':tmp_path/'python.exe','home':tmp_path,'launcher':launcher})
    captured=[]
    @asynccontextmanager
    async def stdio(params):
        captured.append(params);yield (None,None)
    class FakeSession:
        def __init__(self,*a,**k):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def initialize(self):pass
        async def list_tools(self):return SimpleNamespace(tools=[SimpleNamespace(name='get_tender_detail')])
        async def call_tool(self,*a,**k):return SimpleNamespace(is_error=False,structured_content={'detail':{'status':'masked'}})
    monkeypatch.setattr(mcp.client.stdio,'stdio_client',stdio)
    monkeypatch.setattr(mcp,'ClientSession',FakeSession)
    assert asyncio.run(module.BidResearchClient().call('get_tender_detail',{}))['detail']['status']=='masked'
    assert captured[0].args==['-X','utf8',str(launcher)]
    with pytest.raises(ValueError):asyncio.run(module.BidResearchClient().call('run_command',{}))


def test_detail_adapter_uses_actual_archived_evidence_columns(client,monkeypatch):
    from app import bidresearch_mcp as module
    from app.gateway import archive_sources
    url='http://www.ebnew.com/businessShow/333.html'
    archive_sources('adapter-detail',[{'url':url,'title':'维保中标结果','body':'维保中标结果','published_at':'2020-01-19',
        'source_meta':{'origin':'bidresearch_mcp','source':'ebnew','query':'合成电子有限公司'}}],'搜索摘录','procurement')
    async def call(self,tool,args,timeout):
        assert tool=='get_tender_detail' and args['url']==url
        return {'detail':{'status':'masked','text':'维保中标结果\n采购人：中国邮政集团有限公司\n第二中标人：合成电子有限公司\n成交金额：***元。',
            'parties':[{'role':'winner','label':'第二中标人','name':'合成电子有限公司','quote':'第二中标人：合成电子有限公司'}]},'report':{'request_count':1}}
    monkeypatch.setattr(module.BidResearchClient,'call',call)
    result=asyncio.run(module.detail('adapter-detail',module.BidDetail(source='ebnew',url=url,company='合成电子有限公司'),{}))
    assert result['diagnostics']['confirmed_count']==1 and result['records'][0]['published_at']=='2020-01-19'
    assert result['sources'][0]['kind']=='网页正文' and not result['records'][0]['amounts']


@pytest.mark.parametrize('status',['blocked','login_required','captcha_required','robots_denied','rate_limited'])
def test_detail_access_refusal_blocks_other_readers_even_without_evidence(client,monkeypatch,status):
    from app.db import Session,Job,ToolCall
    from app.research_tools import ToolBroker
    with Session.begin() as db:
        job=Job(prompt='查询合成电子有限公司',status='running');db.add(job);db.flush();jid=job.id
        db.add(ToolCall(job_id=jid,tool='get_tender_detail',channel='bidresearch_detail',operation_id=uuid_hex(),
            arguments={'url':'http://www.ebnew.com/businessShow/444.html'},status='unavailable',result={'error':status,'sources':[]}))
    opts={'bidresearch_enabled':True,'enabled_channels':['procurement'],'max_reads':10,'max_searches':5,'max_leads':1}
    broker=ToolBroker(jid,opts,{'products':[]})
    for tool in ['fetch_source','fetch_browser']:
        assert asyncio.run(broker.execute(tool,{'url':'http://www.ebnew.com/businessShow/444.html','channel':'procurement'}))['error']==('site_rate_limited' if status=='rate_limited' else 'site_access_restricted')


def uuid_hex():
    import uuid
    return uuid.uuid4().hex


@pytest.mark.parametrize('prompt,days',[('查询近30天的采购',30),('查询近一个月的公告',30),('查询最近7天中标',7)])
def test_explicit_recent_window_is_not_default_365(prompt,days):
    from app.bidresearch_mcp import company_time_window
    assert company_time_window(prompt,365)==('recent',days)


def test_actual_backup_winner_label_does_not_prove_completed_customer_relationship():
    from pathlib import Path
    from app.bidresearch_mcp import grounded_party
    text=(Path(__file__).parent/'fixtures/tender/ebnew-705768958-visible.txt').read_text(encoding='utf8')
    party={'role':'winner','label':'中标人','name':'成都宏天智电子有限公司','quote':'中标人：成都宏天智电子有限公司'}
    value=grounded_party(text,party)
    assert value['role']=='candidate' and value['quote']=='备选供应商中标人：成都宏天智电子有限公司'
    assert grounded_party(text,value)==value


def test_broker_company_followup_respects_original_recent_request(client,monkeypatch):
    from app import bidresearch_mcp as module
    from app.db import Session,Job
    from app.research_tools import ToolBroker
    received=[]
    async def search(jid,request,options,channel='procurement'):
        received.append(request);return {'sources':[{'id':'synthetic-source'}]}
    monkeypatch.setattr(module,'search',search)
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true')
    with Session.begin() as db:
        job=Job(prompt='查询合成电子有限公司近30天的采购',status='running');db.add(job);db.flush();jid=job.id
    broker=ToolBroker(jid,{'bidresearch_enabled':True,'enabled_channels':['procurement'],'research_targets':['合成电子有限公司'],
        'tender_days':365,'max_reads':10,'max_searches':5,'max_bidresearch_calls':2,'bidresearch_max_requests':80,'max_leads':1},{'products':[]})
    asyncio.run(broker.execute('search_accounts',{'query':'合成电子有限公司采购项目','channel':'procurement'}))
    assert received[0].mode=='recent' and received[0].days==30


def test_company_network_failure_can_recover_valid_cache_within_reserved_requests(client,monkeypatch):
    from app import bidresearch_mcp as module
    calls=[]
    async def call(self,tool,args,timeout):
        calls.append(args)
        if len(calls)==1:return {'records':[],'report':{'request_count':1,'sources':[{'source':'ebnew','status':'network_error'}]}}
        assert args['cache_search_ttl']==3600 and args['max_requests']<=5
        return {'records':[{'source':'ebnew','url':'http://www.ebnew.com/businessShow/666.html','title':'维保中标公示','published_at':'2020-01-19','query':'合成恢复电子有限公司',
            'list_evidence':{'url':'https://ss.ebnew.com/tradingSearch/index.htm','sha256':'fixture'},'detail':{'status':'not_requested'}}],
            'report':{'request_count':0,'sources':[{'source':'ebnew','status':'ok','cache_hits':1}]}}
    monkeypatch.setattr(module.BidResearchClient,'call',call)
    result=asyncio.run(module.search('recover-valid-cache',module.BidSearch(keywords=['合成恢复电子有限公司'],company='合成恢复电子有限公司'),
        {'bidresearch_max_requests':6,'bidresearch_timeout':90,'company_force_refresh':True}))
    assert len(calls)==2 and result['reused'] and result['request_count']==1
    assert result['status']=='partial' and result['recovery']=='retry_after_network_failure'
    assert len(result['records'])==1 and result['coverage'][0]['status']=='network_error'


def test_rate_limit_blocks_same_host_next_url_but_not_another_site(client):
    import time
    from app.bidresearch_mcp import refused_detail
    from app.db import Session,Job,ToolCall
    with Session.begin() as db:
        job=Job(prompt='检索企业',status='running');db.add(job);db.flush();jid=job.id
        db.add(ToolCall(job_id=jid,tool='get_tender_detail',channel='bidresearch_detail',operation_id=uuid_hex(),
            arguments={'url':'http://www.ebnew.com/businessShow/1.html'},status='unavailable',last_attempt_epoch=time.time(),result={'error':'rate_limited'}))
    with Session() as db:
        assert refused_detail(db,jid,'http://www.ebnew.com/businessShow/2.html')=='site_rate_limited'
        assert not refused_detail(db,jid,'https://www.ggzy.gov.cn/notice/2.html')


def test_model_cannot_select_output_command_or_unbounded_budgets():
    from app.bidresearch_mcp import BidSearch
    for extra in [{'output':'D:/other'},{'command':'cmd'},{'max_requests':999},{'sources':['unknown']}]:
        with pytest.raises(ValueError):BidSearch.model_validate({'keywords':['软件'],**extra})


def test_company_procurement_search_reuses_same_window_and_preserves_read_budget(client,monkeypatch):
    from app import bidresearch_mcp
    from app.research_tools import ToolBroker
    from app.db import Session,Job
    received=[]
    async def search(jid,request,options,channel='procurement'):
        received.append((request,options));return {'error':'empty_results','sources':[]}
    async def fallback(self,name,args):return {'sources':[]}
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true')
    monkeypatch.setattr(bidresearch_mcp,'search',search)
    monkeypatch.setattr(ToolBroker,'_execute',fallback)
    with Session.begin() as db:
        job=Job(prompt='查询合成电子有限公司的采购',status='running');db.add(job);db.flush();jid=job.id
    options={'bidresearch_enabled':True,'max_bidresearch_calls':2,'bidresearch_max_requests':24,
        'bidresearch_max_details':4,'max_reads':8,'max_searches':5,'max_leads':1,
        'tender_days':365,'enabled_channels':['procurement'],'research_targets':['合成电子有限公司']}
    broker=ToolBroker(jid,options,{'products':[]})
    asyncio.run(broker.execute('search_tenders',{'keywords':['合成电子有限公司'],'company':'合成电子有限公司','days':365}))
    asyncio.run(broker.execute('search_accounts',{'query':'合成电子有限公司采购项目','channel':'procurement'}))
    assert len(received)==1
    assert received[0][1]['bidresearch_max_details']<=2
    assert received[0][0].sources==['ebnew']


@pytest.mark.parametrize('quote', ['第二成交候选人为：成都宏天智电子有限公司', '第一中标候选人 成都宏天智电子有限公司'])
def test_explicit_candidate_formats_are_grounded_without_promoting_to_winner(quote):
    from app.bidresearch_mcp import grounded_party
    party={'role':'candidate','name':'成都宏天智电子有限公司','label':'成交候选人' if '成交' in quote else '中标候选人','quote':quote}
    assert grounded_party(quote,party)['name']==party['name']
    assert grounded_party(quote,{**party,'role':'winner'}) is None


def test_backup_award_candidate_requires_its_own_section_and_column():
    from app.bidresearch_mcp import grounded_party
    body='成交：\n序号 | 寻源单名称 | 供应商名称\n* | 监控项目 | 成都慧翼科技有限公司\n备选成交：\n序号 | 寻源单名称 | 供应商名称\n* | 监控项目 | 成都宏天智电子有限公司'
    quote=body[body.index('备选成交：'):]
    party={'role':'candidate','name':'成都宏天智电子有限公司','label':'备选成交供应商','quote':quote}
    assert grounded_party(body,party)['quote']==quote
    assert grounded_party(body,{**party,'role':'winner'}) is None
    assert grounded_party(body,{**party,'name':'成都慧翼科技有限公司'}) is None
    assert grounded_party(body,{**party,'role':'winner','label':'供应商名称','quote':quote.splitlines()[-1]}) is None


def test_upstream_cache_hits_are_visible_in_result_provenance(client):
    from app.bidresearch_mcp import archive_result
    report={'request_count':0,'sources':[{'source':'ebnew','status':'ok','cache_hits':3}]}
    result=archive_result('cache-provenance',{'records':[],'report':report},['软件'],30,5)
    assert result['reused'] is True and result['network_attempted'] is False


def test_current_opportunity_constraint_survives_intent_rephrasing():
    from app.bidresearch_mcp import active_procurement_requested
    assert active_procurement_requested('近30天仍在采购人工智能服务的买方')


def test_upstream_search_has_inner_deadline_before_stdio_timeout(monkeypatch,client):
    from app import bidresearch_mcp as module
    received=[]
    async def call(self,tool,args,timeout):
        received.append((args,timeout));return {'records':[],'report':{}}
    monkeypatch.setattr(module.BidResearchClient,'call',call)
    asyncio.run(module.search('deadline-job',module.BidSearch(keywords=['软件开发']),
        {'bidresearch_max_requests':12,'bidresearch_max_details':4,'bidresearch_timeout':90}))
    assert 1<=received[0][0]['max_seconds']<=received[0][1]-10


def test_stdio_timeout_retains_atomic_partial_records_from_this_call(client,monkeypatch,tmp_path):
    import json
    from pathlib import Path
    from app import bidresearch_mcp as module
    monkeypatch.setattr(module,'runtime_status',lambda:{'installed':True,'home':tmp_path})
    async def interrupted(self,tool,args,timeout):
        output=Path(args['output']);output.mkdir(parents=True)
        row={'source':'ggzy','url':'https://www.ggzy.gov.cn/partial','title':'软件开发采购公告',
            'published_at':date.today().isoformat(),'detail':{'status':'public',
            'text':'项目名称：软件开发服务\n采购人：合成学校\n采购需求：开发企业知识库。\n预算金额：80万元。'}}
        (output/'partial.json').write_text(json.dumps({'records':[row],'report':{'request_count':2,
            'sources':[{'source':'ggzy','status':'partial','cache_hits':1}]}}),encoding='utf8')
        raise TimeoutError()
    monkeypatch.setattr(module.BidResearchClient,'call',interrupted)
    result=asyncio.run(module.search('partial-node',module.BidSearch(keywords=['软件开发']),
        {'bidresearch_max_requests':12,'bidresearch_max_details':2,'bidresearch_timeout':90}))
    assert result['sources'][0]['kind']=='网页正文'
    assert result['partial_recovery'] is True and result['status']=='partial'
    assert result['reused'] is True and result['network_attempted'] is True


def test_projection_retains_detail_and_deduplicates_same_notice(client):
    from app.bidresearch_mcp import archive_result
    from app.db import Session,Evidence
    from sqlalchemy import select
    row={'source':'ggzy','url':'https://www.ggzy.gov.cn/information/a.html','title':'软件开发采购公告','published_at':date.today().isoformat(),
         'detail':{'status':'public','text':'软件开发采购公告\n采购人：合成单位\n采购需求：开发知识库软件。\n预算金额：80万元。',
                   'parties':[{'role':'buyer','name':'合成单位','quote':'采购人：合成单位'}]},'parties':[],'amounts':[]}
    result=archive_result('synthetic-job',{'records':[row,row],'report':{'sources':[]}},['软件'],30,5)
    assert len(result['records'])==1 and len(result['sources'])==1
    assert result['sources'][0]['kind']=='网页正文'
    assert result['records'][0]['detail_status']=='public'
    assert result['records'][0]['parties'][0]['name']=='合成单位'
    repeated=archive_result('synthetic-job',{'records':[row],'report':{'sources':[]}},['软件'],30,5)
    assert repeated['sources'][0]['id']==result['sources'][0]['id']


def test_company_listing_is_navigation_only_until_subject_is_read(client):
    from app.bidresearch_mcp import archive_result
    row={'source':'ebnew','url':'http://www.ebnew.com/businessShow/123.html','title':'车载安防设备维保服务候选人公示',
        'published_at':date.today().isoformat(),'query':'合成电子有限公司',
        'list_evidence':{'url':'https://ss.ebnew.com/tradingSearch/index.htm?key=company','sha256':'fixture'},
        'detail':{'status':'not_requested'}}
    result=archive_result('company-navigation',{'records':[row]},['合成电子有限公司'],365,8,'合成电子有限公司')
    assert len(result['sources'])==1 and result['sources'][0]['kind']=='搜索摘录'
    assert result['sources'][0]['source_meta']['navigation_only'] is True
    assert not result['records'][0]['parties'] and not result['records'][0]['has_full_text']
    assert not archive_result('wrong-query',{'records':[{**row,'query':'另一公司'}]},['合成电子有限公司'],365,8,'合成电子有限公司')['sources']
    unrelated={**row,'detail':{'status':'public','text':'采购人：另一公司\n公告明确中标人是其他供应商。'}}
    assert not archive_result('unrelated-read',{'records':[unrelated]},['合成电子有限公司'],365,8,'合成电子有限公司')['sources']


def test_listing_is_not_full_text_and_old_notice_is_excluded(client):
    from app.bidresearch_mcp import archive_result
    rows=[{'source':'ggzy','url':'https://www.ggzy.gov.cn/a','title':'软件采购公告','published_at':'2001-01-01','detail':{'status':'public','text':'旧正文'}},
          {'source':'ggzy','url':'https://www.ggzy.gov.cn/b','title':'软件采购公告','published_at':'','detail':{'status':'not_requested'}}]
    result=archive_result('listing-job',{'records':rows,'report':{'sources':[]}},['软件'],30,5)
    assert len(result['records'])==1 and result['records'][0]['date_filter']=='unconfirmed'
    assert result['sources'][0]['kind']=='搜索摘录'


def test_software_submission_instructions_are_not_demand(client):
    from app.bidresearch_mcp import archive_result
    row={'source':'ggzy','url':'https://www.ggzy.gov.cn/a','title':'设备采购公告',
         'detail':{'status':'public','text':'设备采购公告\n投标人须下载软件制作投标文件。'}}
    assert archive_result('instruction-job',{'records':[row],'report':{}},['软件'],30,5)['records']==[]


def test_disposed_software_assets_are_not_software_procurement(client):
    from app.bidresearch_mcp import archive_result
    row={'source':'ggzy','url':'https://www.ggzy.gov.cn/a','title':'某学校报废软件、黑板等资产残值处置项目',
         'detail':{'status':'public','text':'项目名称：某学校报废软件、黑板等资产残值处置项目。'}}
    assert archive_result('asset-job',{'records':[row],'report':{}},['软件'],30,5)['records']==[]


def test_installed_stdio_health_and_tools_without_network():
    from app.bidresearch_mcp import BidResearchClient, runtime_status
    if not runtime_status()['installed']:pytest.skip('local optional BidResearch not installed')
    health=asyncio.run(BidResearchClient().call('health_check',{},timeout=15))
    assert health['ok'] is True and health['sources']==7


def test_details_are_prioritized_and_duplicate_reposts_are_one_record(client):
    from app.bidresearch_mcp import archive_result
    listing={'source':'ggzy','url':'https://www.ggzy.gov.cn/a','title':'软件采购公告','published_at':date.today().isoformat()}
    detail={'source':'ebnew','url':'https://www.ebnew.com/b','title':'AI软件开发采购公告','published_at':date.today().isoformat(),
            'detail':{'status':'public','text':'AI软件开发采购公告\n采购需求：人工智能知识库软件开发。\n采购人：合成研究院\n预算金额：80万元。',
            'parties':[{'role':'buyer','name':'合成研究院','quote':'采购人：合成研究院'}]}}
    repost={**detail,'source':'ggzy','url':'https://www.ggzy.gov.cn/c'}
    result=archive_result('rank-job',{'records':[listing,detail,repost],'report':{}},['软件'],30,2)
    assert result['records'][0]['has_full_text']
    assert len([r for r in result['records'] if r['title']==detail['title']])==1


def test_upstream_per_keyword_details_cannot_exceed_shared_reads(monkeypatch,client):
    from app import bidresearch_mcp as module
    received=[]
    async def call(self,tool,args,timeout):
        received.append(args);return {'records':[],'report':{}}
    monkeypatch.setattr(module.BidResearchClient,'call',call)
    asyncio.run(module.search('budget-job',module.BidSearch(keywords=['软件','人工智能']),
        {'bidresearch_max_requests':16,'bidresearch_max_details':4}))
    args=received[0]
    assert args['details']*len(args['sources'])*len(args['keywords'])<=4


def test_same_day_same_title_with_different_project_bodies_is_not_merged(client):
    from app.bidresearch_mcp import archive_result
    rows=[]
    for number in ('P001','P002'):
        rows.append({'source':'ggzy','url':'https://www.ggzy.gov.cn/'+number,'title':'软件开发采购公告','published_at':date.today().isoformat(),
            'detail':{'status':'public','text':f'软件开发采购公告\n项目编号：{number}\n采购人：合成研究院\n采购需求：软件开发。',
                'parties':[{'role':'buyer','name':'合成研究院','quote':'采购人：合成研究院'}]}})
    assert len(archive_result('projects-job',{'records':rows},['软件'],30,5)['records'])==2


def test_table_roles_and_units_require_correct_header_column(client):
    from app.bidresearch_mcp import archive_result
    text='软件开发采购公告\n采购人 | 中标人 | 预算金额（万元）\n合成研究院 | 合成软件有限公司 | 80'
    row={'source':'ggzy','url':'https://www.ggzy.gov.cn/table','title':'软件开发采购公告','published_at':date.today().isoformat(),
        'detail':{'status':'public','text':text,'parties':[{'role':'buyer','name':'合成研究院','label':'采购人','quote':'合成研究院 | 合成软件有限公司 | 80'},
            {'role':'winner','name':'合成研究院','label':'中标人','quote':'合成研究院 | 合成软件有限公司 | 80'}],
        'amounts':[{'kind':'budget','label':'预算金额（万元）','original':'80','quote':'合成研究院 | 合成软件有限公司 | 80'}]}}
    result=archive_result('table-job',{'records':[row]},['软件'],30,5)['records'][0]
    assert len(result['parties'])==1 and '采购人 | 中标人' in result['parties'][0]['quote']
    assert result['amounts'][0]['display_value']=='80万元'
    assert result['amounts'][0]['quote'] in text


def test_access_rejection_is_preserved_before_another_reader(client,monkeypatch):
    from app.research_tools import ToolBroker
    from app.db import Session,Conversation,Job
    from app.gateway import archive_sources
    import uuid
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='软件采购',client_token=uuid.uuid4().hex);db.add(j);db.flush();jid=j.id
    s=archive_sources(jid,[{'url':'https://www.chinabidding.cn/rejected','title':'软件采购公告','body':'软件采购公告','source_meta':{'origin':'bidresearch_mcp','detail_status':'blocked'}}],'搜索摘录','procurement')[0]
    async def fetch(*args):raise AssertionError('rejected source must not be sent to another reader')
    monkeypatch.setattr(ToolBroker,'fetch',fetch)
    result=asyncio.run(ToolBroker(jid,{'enabled_channels':['procurement'],'max_reads':4},{}).execute('fetch_source',{'url':s['url'],'channel':'procurement'}))
    assert result['error']=='site_access_restricted'


@pytest.mark.parametrize('title,body',[
    ('润泽人工智能应用中心园区周边基础设施建设项目设计采购公告','采购需求：市政道路基础设施工程设计。'),
    ('江西水利职业学院人工智能创新实训室采购公告','采购需求：教学仪器、机柜等设备。'),
    ('人工智能与自动化学院搬迁货物采购成交公告','采购内容：电脑、话筒、机柜。')])
def test_software_service_scope_rejects_ai_names_and_physical_projects(client,title,body):
    from app.bidresearch_mcp import archive_result
    row={'source':'ggzy','url':'https://www.ggzy.gov.cn/irrelevant','title':title,'published_at':date.today().isoformat(),
        'detail':{'status':'public','text':title+'\n'+body+'\n采购人：合成学校'}}
    result=archive_result('service-scope-job',{'records':[row]},['人工智能'],30,5,category='software_services')
    assert result['records']==[] and result['sources']==[]


def test_service_scope_keeps_specific_software_demand_and_short_queries(client):
    from app.bidresearch_mcp import archive_result,procurement_keywords
    row={'source':'ggzy','url':'https://www.ggzy.gov.cn/software-service','title':'教学虚拟仿真软件开发服务采购公告',
        'published_at':date.today().isoformat(),'detail':{'status':'public','text':'项目名称：教学虚拟仿真软件开发服务\n采购需求：开发教学软件。\n采购人：合成学校'}}
    assert archive_result('service-positive-job',{'records':[row]},['软件开发'],30,5,category='software_services')['records']
    assert procurement_keywords('人工智能或软件开发服务采购',[{'name':'软件开发服务'}])==['软件开发','人工智能']
    assert procurement_keywords('人工智能采购',[{'name':'软件开发服务'},{'name':'人工智能应用开发'}])==['软件开发','人工智能']


def test_profile_scope_is_applied_to_actual_mcp_request_and_persist(client,monkeypatch):
    import uuid
    from app import bidresearch_mcp
    from app.research_tools import ToolBroker
    from app.db import Session,Conversation,Job
    from app.gateway import archive_sources
    from app.schemas import Candidate,Fact
    received=[]
    async def search(jid,request,options,channel='procurement'):
        received.append(request);return {'error':'','sources':[]}
    monkeypatch.setenv('CLIENTREACH_BIDRESEARCH_ENABLED','true');monkeypatch.setattr(bidresearch_mcp,'search',search)
    with Session.begin() as db:
        c=Conversation();db.add(c);db.flush();j=Job(conversation_id=c.id,prompt='寻找软件开发买方',client_token=uuid.uuid4().hex)
        db.add(j);db.flush();jid=j.id
    options={'bidresearch_enabled':True,'max_bidresearch_calls':1,'bidresearch_max_requests':8,
        'bidresearch_max_details':1,'max_reads':3,'max_searches':3,'max_leads':1,'enabled_channels':['procurement']}
    broker=ToolBroker(jid,options,{'products':[{'name':'软件开发服务'}]})
    asyncio.run(broker.execute('search_tenders',{'keywords':['人工智能']}))
    assert received[0].category=='software_services'
    source=archive_sources(jid,[{'title':'人工智能园区道路设计采购公告','body':'采购人：合成学校\n采购需求：市政道路设计。',
        'url':'https://www.ggzy.gov.cn/design'}],'网页正文','procurement')[0]
    broker.allowed_sources.add(source['id'])
    candidate=Candidate(display_name='合成学校',city='',buyer_role='project_buyer',match_reason='人工智能园区',facts=[
        Fact(field='name',value='合成学校',quote='采购人：合成学校',source_id=source['id']),
        Fact(field='buyer_role',value='采购人',quote='采购人：合成学校',source_id=source['id'])])
    result=asyncio.run(broker.execute('persist_lead',{'candidate':candidate.model_dump()}))
    assert result['error']=='采购原文未证明软件或AI服务需求'


def test_table_winner_label_cannot_be_relabelled_as_buyer():
    from app.bidresearch_mcp import grounded_party
    body='采购人 | 中标人 | 预算金额（万元）\n合成研究院 | 合成软件有限公司 | 80'
    party={'role':'buyer','label':'中标人','name':'合成软件有限公司','quote':body.splitlines()[-1]}
    assert grounded_party(body,party) is None
    assert grounded_party(body,{**party,'role':'winner'})['name']=='合成软件有限公司'


def test_amount_quote_with_header_still_requires_correct_data_column():
    from app.bidresearch_mcp import grounded_amount
    body='预算金额（万元） | 成交金额（万元）\n80 | 500'
    amount={'kind':'budget','label':'预算金额（万元）','original':'500','quote':body}
    assert grounded_amount(body,amount) is None
    assert grounded_amount(body,{**amount,'original':'80'})['display_value']=='80万元'


def test_amount_label_cannot_borrow_an_adjacent_other_amount():
    from app.bidresearch_mcp import grounded_amount
    body='预算金额：80万元；成交金额：500万元'
    amount={'kind':'budget','label':'预算金额','original':'500万元','quote':body}
    assert grounded_amount(body,amount) is None
    assert grounded_amount(body,{**amount,'original':'80万元'})['display_value']=='80万元'


@pytest.mark.parametrize('title',['人工智能平台建设服务器采购公告','人工智能计算平台建设项目采购公告'])
def test_generic_ai_platform_title_is_not_evidence_of_software_service(title):
    from app.bidresearch_mcp import software_service_match
    assert not software_service_match(title,'采购需求：GPU服务器10台、机柜、交换机；本次只采购硬件设备，不采购软件开发或服务。')


def test_candidate_quote_cannot_be_treated_as_final_award_amount():
    from app.bidresearch_mcp import grounded_amount
    body='中标候选人报价：80万元'
    assert grounded_amount(body,{'kind':'award','label':'中标候选人报价','original':'80万元','quote':body}) is None
    body='中标（成交）金额：80万元'
    assert grounded_amount(body,{'kind':'award','label':'中标（成交）金额','original':'80万元','quote':body})['display_value']=='80万元'


def test_active_scope_excludes_award_notices_before_archiving(client):
    from app.bidresearch_mcp import archive_result
    row={'source':'ggzy','url':'https://www.ggzy.gov.cn/awarded','title':'软件开发服务中标结果公告',
        'published_at':date.today().isoformat(),'detail':{'status':'public','text':'项目名称：软件开发服务\n采购人：合成学校\n成交金额：80万元。'}}
    assert archive_result('active-job',{'records':[row]},['软件开发'],30,5,active_only=True)['records']==[]
