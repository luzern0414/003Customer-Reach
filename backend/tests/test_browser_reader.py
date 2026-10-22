"""浏览器工具预算/许可与归档验证；只替实际浏览器运行时，公网验收另有真实OpenCLI记录。"""
import asyncio
import uuid
from sqlalchemy import select
from app.db import Session, Conversation, Job, Evidence, ToolCall


def test_browser_requires_discovered_url_and_shares_read_budget(client,monkeypatch):
    """未发现页面零读取；已许可页面进真实账本/来源，浏览器消耗相同读取总预算。"""
    from app.research_tools import ToolBroker
    from app import browser_reader
    suffix=uuid.uuid4().hex;url='https://browser-'+suffix+'.example.com/profile'
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush()
        job=Job(conversation_id=conv.id,prompt='查询企业画像',query_mode='company_query',client_token=suffix);db.add(job);db.flush();job_id=job.id
        source=Evidence(job_id=job_id,url=url,title='明确标识的测试网页',body='这是搜索阶段返回的验证材料，不冒充真实企业事实。',kind='搜索摘录',channel='official');db.add(source);db.flush();sid=source.id
    calls=[]
    async def read(url,job_id):
        """只返回明确夹具正文，生产工具的许可、共享预算、缓存和SSE仍真实执行。"""
        calls.append(url)
        return {'url':url,'title':'浏览器夹具页面','body':'这是验证浏览器工具的已许可正文。'*20,'backend':'opencli','opencli_version':'1.8.8','truncated':False,'screenshot':'fixture-only'}
    monkeypatch.setattr(browser_reader,'read_edge',read)
    options={'enabled_channels':['official'],'max_searches':1,'max_reads':1,'max_candidate_searches':1}
    broker=ToolBroker(job_id,options,{})
    blocked=asyncio.run(broker.execute('fetch_browser',{'url':url+'/not-discovered','channel':'official'}))
    assert blocked['error']=='url_not_discovered' and calls==[]
    # 被拒绝的未知URL也是实际工具尝试，预算已消耗；另一个新任务验证成功与缓存。
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt='读取'+url,query_mode='company_query',client_token=uuid.uuid4().hex);db.add(job);db.flush();job_id=job.id
        source=Evidence(job_id=job_id,url=url,title='已发现',body='搜索发现的验证页面。',kind='搜索摘录',channel='official');db.add(source);db.flush()
    broker=ToolBroker(job_id,options,{})
    result=asyncio.run(broker.execute('fetch_browser',{'url':url,'channel':'official'}));assert len(result['sources'])==1 and calls==[url]
    again=asyncio.run(broker.execute('fetch_browser',{'url':url,'channel':'official'}));assert again['reused'] and calls==[url]
    exhausted=asyncio.run(broker.execute('fetch_source',{'url':url,'channel':'official'}));assert exhausted['error']=='budget_exhausted'
    with Session() as db:
        evidence=db.get(Evidence,result['sources'][0]['id']);assert evidence.kind=='Edge网页正文' and evidence.source_meta['backend']=='opencli'
        operations=list(db.scalars(select(ToolCall).where(ToolCall.job_id==job_id)));assert len(operations)==1 and operations[0].attempts==1


def test_browser_configuration_rejects_commands_and_separates_validation(client):
    """配置只能选固定后端和边界；状态没有成功读取时不会宣称连接，任意代码字段422。"""
    status=client.get('/api/browser/status');assert status.status_code==200
    assert 'last_read' in status.json() and 'node' not in status.json()
    result=client.patch('/api/browser/settings',json={'enabled':True,'preferred_backend':'auto','max_pages':3,'max_chars':40000,'command_timeout':90,'command':'anything'})
    assert result.status_code==422


def test_browser_page_limit_is_independent_of_shared_read_budget(client,monkeypatch):
    """单任务max_pages=1时第二个许可页不启动读取，即使共享max_reads仍有余额。"""
    from app import browser_reader
    from app.research_tools import ToolBroker
    suffix=uuid.uuid4().hex;urls=['https://example.com/'+suffix+'/a','https://example.com/'+suffix+'/b'];calls=[]
    with Session.begin() as db:
        conv=Conversation();db.add(conv);db.flush();job=Job(conversation_id=conv.id,prompt='读取'+ ' '.join(urls),client_token=suffix,query_mode='company_query');db.add(job);db.flush();jid=job.id
    async def read(url,job_id):
        calls.append(url)
        return {'url':url,'title':'页数边界夹具','body':'明确标注隔离页数上限验证材料，不是实际企业事实。'*20,'backend':'opencli','opencli_version':'1.8.8','truncated':False,'screenshot':'fixture-only'}
    monkeypatch.setattr(browser_reader,'read_edge',read)
    monkeypatch.setattr(browser_reader,'browser_settings',lambda:{'max_pages':1})
    broker=ToolBroker(jid,{'enabled_channels':['official'],'max_reads':5,'max_searches':1,'max_candidate_searches':1},{})
    assert asyncio.run(broker.execute('fetch_browser',{'url':urls[0],'channel':'official'}))['sources']
    result=asyncio.run(broker.execute('fetch_browser',{'url':urls[1],'channel':'official'}))
    assert result['error']=='browser_budget_exhausted' and calls==[urls[0]]
