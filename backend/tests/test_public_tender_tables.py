"""公开公告表格的角色与金额保存；实际HTML/存档/数据库链，外部响应不联网。"""
import uuid
import asyncio


def test_dom_table_keeps_bidder_rows_when_article_extractor_omits_them():
    from app.public_tender_tables import table_text
    html='''<html><body><table><tr><td>投标人名称</td><td>投标报价（元）</td></tr>
    <tr><td>合成电子有限公司</td><td>6280000</td></tr></table>
    <div style="display:none"><table><tr><td>隐形有限公司</td></tr></table></div></body></html>'''
    result=table_text(html.encode(), 'https://ggzyjy.sc.gov.cn/notice')
    assert '| 合成电子有限公司 | 6280000 |' in result and '隐形有限公司' not in result
    assert not table_text(html.encode(),'https://unknown.example/notice')


def test_award_source_is_saved_as_supplier_winner_not_buyer_project(client):
    from app.public_tender_tables import save_public_notices
    from app.db import Session,Job,Conversation
    from app.gateway import archive_sources
    from app.company_service import company_detail
    name='合成公告电子有限公司'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt=name,status='running');db.add(job);db.flush();jid=job.id
    body='发布时间：2024-10-17\n| 供应商名称 | 供应商地址 | 中标（成交）金额 |\n|---|---|---|\n| '+name+' | 合成地址 | 3,559,478.00元 |\n采购人：合成农业农村局\n'
    source=archive_sources(jid,[{'url':'https://ggzyjy.sc.gov.cn/'+uuid.uuid4().hex,'title':'保护工程中标（成交）结果公告','body':body}],'网页正文','procurement')[0]
    result=save_public_notices(jid,[source['id']],[name],{})
    detail=company_detail(result[name]['company_id'])
    assert detail['tenders']['summary']['wins']==1 and detail['tenders']['summary']['customers']==1
    record=detail['tenders']['wins'][0]
    assert record['amount']=='3,559,478.00元' and record['buyer_name']=='合成农业农村局'
    assert detail['procurement_summary']['projects']==0


def test_explicit_government_reference_marked_official_still_saves_tender_table(client):
    from app.public_tender_tables import save_public_notices
    from app.db import Session,Job,Conversation
    from app.gateway import archive_sources
    name='合成官网引用电子有限公司'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt=name,status='running');db.add(job);db.flush();jid=job.id
    body='| 供应商名称 | 中标（成交）金额 |\n|---|---|\n| '+name+' | 3559478元 |\n采购人：合成采购局'
    source=archive_sources(jid,[{'url':'https://ggzyjy.sc.gov.cn/'+uuid.uuid4().hex,'title':'项目中标结果公告','body':body}],'网页正文','official')[0]
    result=save_public_notices(jid,[source['id']],[name],{})
    assert result[name]['records']=={'winner':1}


def test_other_bidder_price_is_not_award_or_candidate(client):
    from app.public_tender_tables import save_public_notices
    from app.db import Session,Job,Conversation
    from app.gateway import archive_sources
    from app.company_service import company_detail
    name='合成开标电子有限公司'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt=name,status='running');db.add(job);db.flush();jid=job.id
    body='其他投标人（除中标候选人之外的）评审情况\n| 投标人名称 | 投标报价（元） | 经评审的投标价（元） | 综合评估得分 |\n|---|---|---|---|\n| '+name+' | 6280000 | 6280000 | 88.19 |\n'
    source=archive_sources(jid,[{'url':'https://www.msggzy.org.cn/'+uuid.uuid4().hex,'title':'交通检测评标结果公示','body':body}],'网页正文','procurement')[0]
    result=save_public_notices(jid,[source['id']],[name],{})
    detail=company_detail(result[name]['company_id'])
    assert detail['tenders']['summary']['wins']==0 and detail['tenders']['summary']['candidates']==0
    record=detail['tenders']['pending'][0]
    assert record['candidate_bid']['price']=='6280000' and record['candidate_bid']['unit']=='元'
    assert record['candidate_bid']['score']=='88.19' and not record['amount']


def test_plain_project_title_and_historical_owner_header_are_not_buyer(client):
    from app.public_tender_tables import save_public_notices
    from app.db import Session,Job,Conversation
    from app.gateway import archive_sources
    from app.company_service import company_detail
    name='合成水务电子有限公司'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt=name,status='running');db.add(job);db.flush();jid=job.id
    body='水务工程评标结果公示\n| 项目业主 | 项目名称 | 合同价格（元） |\n\n其他投标人\n| 投标人名称 | 投标报价（元） |\n| '+name+' | 14525626.00元(/) |\n'
    source=archive_sources(jid,[{'url':'https://ggzyjy.sc.gov.cn/'+uuid.uuid4().hex,'title':'水务工程二标段（智慧化部分）','body':body}],'网页正文','procurement')[0]
    result=save_public_notices(jid,[source['id']],[name],{})
    record=company_detail(result[name]['company_id'])['tenders']['pending'][0]
    assert record['buyer_name']=='' and record['candidate_bid']['price']=='14525626.00'


def test_table_quotes_remain_contiguous_with_indented_rows():
    from app.public_tender_tables import bid_context
    body='    | 投标人名称 | 投标报价（元） |\n    |---|---|\n    | 合成电子有限公司 | 6280000 |\n'
    result=bid_context(body,'合成电子有限公司')
    assert result['quote'] in body and '6280000' in result['quote']


def test_fetch_preserves_omitted_dom_table_without_name_error(client,monkeypatch):
    from app import research_tools,browser_reader
    from app.db import Session,Job,Conversation
    from app.research_tools import ToolBroker
    import httpx
    name='HTML链路电子有限公司';url='https://ggzyjy.sc.gov.cn/'+uuid.uuid4().hex
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt=url,status='running');db.add(job);db.flush();jid=job.id
    html='<html><head><meta charset="utf-8"><title>中标结果公告</title></head><body><main><p>'+('公告的其他说明。'*100)+'</p></main><table><tr><td>供应商名称</td><td>中标（成交）金额</td></tr><tr><td>'+name+'</td><td>3559478元</td></tr></table></body></html>'
    original=httpx.AsyncClient
    def local(*args,**kwargs):
        kwargs.update(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=html,headers={'content-type':'text/html;charset=utf-8'},request=request)),trust_env=False)
        return original(*args,**kwargs)
    monkeypatch.setattr(research_tools.httpx,'AsyncClient',local);monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    monkeypatch.setattr(browser_reader,'browser_settings',lambda:{'enabled':False})
    broker=ToolBroker(jid,{'enabled_channels':['procurement'],'max_reads':1,'max_searches':1,'max_leads':1},{})
    broker.reference_urls.add(url)
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'procurement'}))
    assert not result.get('error'),result
    assert name in result['sources'][0]['body'] and '3559478元' in result['sources'][0]['body']


def test_official_reference_fetch_keeps_visible_government_tender_table(client,monkeypatch):
    from app import research_tools,browser_reader
    from app.db import Session,Job,Conversation
    from app.research_tools import ToolBroker
    import httpx
    name='HTML官方引用电子有限公司';url='https://ggzyjy.sc.gov.cn/'+uuid.uuid4().hex
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt=url,status='running');db.add(job);db.flush();jid=job.id
    html='<html><head><meta charset="utf-8"><title>中标结果公告</title></head><body><main><p>'+('公告的其他说明。'*100)+'</p></main><table><tr><td>供应商名称</td><td>中标（成交）金额</td></tr><tr><td>'+name+'</td><td>3559478元</td></tr></table></body></html>'
    original=httpx.AsyncClient
    def local(*args,**kwargs):
        kwargs.update(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=html,headers={'content-type':'text/html;charset=utf-8'},request=request)),trust_env=False)
        return original(*args,**kwargs)
    monkeypatch.setattr(research_tools.httpx,'AsyncClient',local);monkeypatch.setattr(research_tools,'public_url',lambda url:True)
    monkeypatch.setattr(browser_reader,'browser_settings',lambda:{'enabled':False})
    broker=ToolBroker(jid,{'enabled_channels':['official'],'max_reads':1,'max_searches':1,'max_leads':1},{})
    broker.reference_urls.add(url)
    result=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'official'}))
    assert not result.get('error'),result
    assert name in result['sources'][0]['body'] and '3559478元' in result['sources'][0]['body']


def test_late_company_row_in_long_bid_table_remains_visible(client):
    from app.public_tender_tables import save_public_notices
    from app.db import Session,Job,Conversation
    from app.gateway import archive_sources
    from app.company_service import company_detail
    name='长表末位投标电子有限公司'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt=name,status='running');db.add(job);db.flush();jid=job.id
    bidders='\n'.join(f'| 其他投标企业{i:02d} | {i+1}000000 | {i+1}000000 | 80.00 |' for i in range(40))
    body=('其他投标人\n| 投标人名称 | 投标报价（元） | 经评审的投标价（元） | 综合评估得分 |\n|---|---|---|---|\n'+
        bidders+'\n| '+name+' | 6280000 | 6280000 | 88.19 |\n')
    source=archive_sources(jid,[{'url':'https://www.msggzy.org.cn/'+uuid.uuid4().hex,'title':'项目中标候选人公示','body':body}],'网页正文','official')[0]
    result=save_public_notices(jid,[source['id']],[name],{})
    detail=company_detail(result[name]['company_id'])
    assert detail['tenders']['summary']['pending']==1
    assert detail['tenders']['pending'][0]['candidate_bid']['price']=='6280000'
