"""停止首token/流停顿、原生LangSmith配置与文档问答路由的本地回归。"""
import asyncio
import time
import uuid
import pytest
from app.conversation import mode
from app.db import Session,Job,Conversation
from app.research_tools import cancellable_stream, cancellable, Paused, PENDING_CLEANUP


@pytest.mark.parametrize('first_chunk',[False,True])
def test_stop_waiting_model_stream(client,first_chunk):
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'解释Markdown','client_token':uuid.uuid4().hex}).json()
    closed=[]
    async def scenario():
        async def output():
            try:
                if first_chunk:yield '第一块'
                await asyncio.sleep(30)
                yield '不应收到'
            finally:closed.append(True)
        iterator=cancellable_stream(output(),job['id'])
        if first_chunk:assert await anext(iterator)=='第一块'
        waiting=asyncio.create_task(anext(iterator))
        await asyncio.sleep(.05)
        with Session.begin() as db:
            row=db.get(Job,job['id']);row.cancel_requested=True
        started=time.perf_counter()
        with pytest.raises(Paused):await waiting
        assert time.perf_counter()-started<2
    asyncio.run(scenario())
    assert closed


def test_stop_with_provider_suppressing_cancel_releases_business_wait(client):
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'解释停止回答','client_token':uuid.uuid4().hex}).json()['id']
    async def scenario():
        release=asyncio.Event();closed=[]
        async def output():
            try:
                try:await asyncio.sleep(30)
                except asyncio.CancelledError:await release.wait()
                yield '已取消请求的迟到文本'
            finally:closed.append(True)
        iterator=cancellable_stream(output(),job)
        waiting=asyncio.create_task(anext(iterator));await asyncio.sleep(.05)
        with Session.begin() as db:db.get(Job,job).cancel_requested=True
        started=time.monotonic()
        try:
            with pytest.raises(Paused):await asyncio.wait_for(waiting,2)
            assert time.monotonic()-started<1.5
            assert job in PENDING_CLEANUP.values()
        finally:
            release.set()
            await asyncio.sleep(.1)
        assert not [x for x in PENDING_CLEANUP.values() if x==job] and closed
    asyncio.run(scenario())


def test_timeout_with_provider_suppressing_cancel_is_bounded(client):
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'解释超时','client_token':uuid.uuid4().hex}).json()['id']
    async def scenario():
        release=asyncio.Event()
        async def external():
            try:await asyncio.sleep(30)
            except asyncio.CancelledError:await release.wait()
        started=time.monotonic()
        try:
            with pytest.raises(TimeoutError):await asyncio.wait_for(cancellable(external(),job,.1),2)
            assert time.monotonic()-started<1.5
        finally:
            release.set();await asyncio.sleep(.1)
    asyncio.run(scenario())


def test_model_tls_uses_standard_verified_ca_not_native_windows_chain(monkeypatch):
    import ssl,certifi
    from app.config import configure_tls
    from openai import DefaultAsyncHttpxClient
    monkeypatch.delenv('SSL_CERT_FILE',raising=False);monkeypatch.delenv('SSL_CERT_DIR',raising=False)
    configure_tls()
    async def scenario():
        async with DefaultAsyncHttpxClient() as client:
            context=client._transport._pool._ssl_context
            assert type(context).__module__=='ssl'
            assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
            assert len(context.get_ca_certs())>0
    asyncio.run(scenario())
    assert __import__('os').environ['SSL_CERT_FILE']==certifi.where()


def test_explicit_ca_configuration_is_preserved(monkeypatch):
    import os
    from app.config import configure_tls
    monkeypatch.setenv('SSL_CERT_FILE','user-configured-ca.pem');configure_tls()
    assert os.environ['SSL_CERT_FILE']=='user-configured-ca.pem'
    monkeypatch.delenv('SSL_CERT_FILE');monkeypatch.setenv('SSL_CERT_DIR','user-configured-ca-directory');configure_tls()
    assert os.environ.get('SSL_CERT_FILE') is None and os.environ['SSL_CERT_DIR']=='user-configured-ca-directory'


def test_interrupted_clock_marks_unknown_tail_without_counting_downtime(client):
    from datetime import datetime,timedelta,timezone
    from app.db import JobEvent
    from app.service import settle_interrupted_clock
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'解释计时','client_token':uuid.uuid4().hex}).json()['id']
    epoch=time.time()-500
    def stamp(value):return datetime.fromtimestamp(value,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    with Session.begin() as db:
        row=db.get(Job,job);row.status='running';row.clock_at=epoch;row.updated_at=stamp(epoch)
        db.add(JobEvent(job_id=job,created_at=stamp(epoch+2),message='隔离最后活动'))
        db.flush();settle_interrupted_clock(row,db);row.status='paused'
        assert row.clock_at is None and 1000<=row.elapsed_ms<=3000
        assert row.metrics['clock_is_partial'] is True
    response=client.get('/api/jobs/'+job).json()
    assert response['elapsed_ms']<5000 and response['metrics']['clock_is_partial']


@pytest.mark.parametrize('text,files,expected',[
    ('只解析附件，不要找客户',['file'],'document'),
    ('读取文件里的型号和价格，不要联网搜索',['file'],'document'),
    ('这份文件有哪些型号？',[],'document'),
    ('列出附件产品对照表',['file'],'document'),
    ('根据目录寻找深圳经销商',['file'],'research'),
    ('你好，你是谁',[],'quick'),
    ('把“模型先搜索再核验客户”改写成一句简单中文',[],'chat'),
    ('计算58乘20是多少，只给结果',[],'chat'),
    ('请写一个B端获客策略说明',[],'chat'),
    ('用Markdown二级标题、粗体和表格解释如何核验客户资料，不要联网搜索',[],'chat'),
    ('附件里的价格是多少',[],'document'),
    ('根据附件寻找深圳经销商，列出联系方式',['file'],'research'),
])
def test_document_intent(text,files,expected):
    assert mode(text,files)==expected


def test_document_graph_does_not_search_buyers(client,monkeypatch):
    from app import agent
    from langchain_core.messages import AIMessageChunk
    file=client.post('/api/attachments',files={'file':('sample.txt','型号CR-T20，功率20W，单价58元'.encode())}).json()
    conv=client.post('/api/conversations').json()['id']
    job=client.post('/api/conversations/'+conv+'/messages',json={'content':'列出附件的型号、功率、单价，不要联网搜索',
        'attachment_ids':[file['id']],'client_token':uuid.uuid4().hex}).json()
    async def forbidden(*args,**kwargs):raise AssertionError('文件问答执行了买家研究')
    class Chat:
        async def astream(self,messages):
            assert '型号CR-T20' in messages[-1].content and '不搜索客户' in messages[-1].content
            yield AIMessageChunk(content='**CR-T20** · 20W · 58元')
    monkeypatch.setattr(agent,'model',lambda:Chat())
    for name in ['profile_node','plan_node','search_node','read_node','extract_node','learn_node']:
        monkeypatch.setattr(agent,name,forbidden)
    with Session.begin() as db:db.get(Job,job['id']).status='running'
    asyncio.run(agent.run_job(job['id']))
    value=client.get('/api/jobs/'+job['id']).json()
    assert value['status']=='completed' and set(value['metrics']['stage_timings'])=={'intent','context','answer'}
    assert all(x['tool']=='search_knowledge' for x in value['tools'])


def test_tracing_never_exposes_key(client,monkeypatch,tmp_path):
    from app import tracing
    from langsmith.run_helpers import get_tracing_context
    monkeypatch.setattr(tracing,'ROOT',tmp_path)
    monkeypatch.delenv('LANGSMITH_API_KEY',raising=False)
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    assert not tracing.tracing_status()['enabled']
    with tracing.trace_scope('job','conversation'):
        assert get_tracing_context()['enabled'] is False
    monkeypatch.setenv('LANGSMITH_API_KEY','test-local-key-not-for-cloud')
    sentinel=object()
    monkeypatch.setattr(tracing,'_client',lambda *args:sentinel)
    with tracing.trace_scope('job','conversation'):
        context=get_tracing_context()
        assert context['enabled'] and context['metadata']=={'job_id':'job','conversation_id':'conversation'}
        assert context['client'] is sentinel
    value=client.get('/api/tracing').json()
    assert value['configured'] and value['enabled'] and value['hide_inputs'] and value['hide_outputs']
    assert 'test-local-key' not in str(value)


def test_langsmith_sdk_to_local_collector(monkeypatch):
    """使用官方SDK向本机HTTP收集器发送嵌套trace，核实隐私配置；不是云端验收。"""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from langsmith import Client,traceable
    from app import tracing
    from app.tool_views import trace_tool_inputs,tool_result
    records=[]
    class Collector(BaseHTTPRequestHandler):
        """仅测试用本机LangSmith协议收集器，不连接远程服务。"""
        def do_POST(self):
            """读取SDK提交体并返回200，不回显正文。"""
            records.append(json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')))))
            self.send_response(200);self.end_headers();self.wfile.write(b'{}')
        do_PATCH=do_POST
        def log_message(self,*args):
            """忽略测试HTTP默认日志，避免把测试路径重复输出。"""
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Collector)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    sdk=Client(api_key='local-fixture',api_url=f'http://127.0.0.1:{server.server_port}',
               auto_batch_tracing=False,hide_inputs=True,hide_outputs=True,info={})
    monkeypatch.setenv('LANGSMITH_API_KEY','local-fixture')
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.setattr(tracing,'_client',lambda *args:sdk)
    @traceable(name='tool-fixture',run_type='tool',process_inputs=trace_tool_inputs,process_outputs=tool_result)
    def tool(name,arguments):
        return {'sources':[{'title':'测试来源','url':'https://example.com','body':'PRIVATE-BODY'}]}
    @traceable(name='graph-fixture')
    def graph(prompt):
        return tool('search_accounts',{'query':prompt,'api_key':'PRIVATE-KEY'})
    try:
        with tracing.trace_scope('fixture-job','fixture-conversation'):
            graph('PRIVATE-PRODUCT-PHONE')
        deadline=time.monotonic()+3
        while len(records)<4 and time.monotonic()<deadline:time.sleep(.05)
        serialized=json.dumps(records)
        assert len(records)>=4
        assert 'tool-fixture' in serialized and 'graph-fixture' in serialized
        assert 'fixture-job' in serialized and 'fixture-conversation' in serialized
        assert 'PRIVATE-' not in serialized and 'local-fixture' not in serialized
        assert any(x.get('parent_run_id') for x in records)
    finally:
        sdk.close();server.shutdown();server.server_close();thread.join(2)


def test_tracing_init_error_does_not_break_agent(monkeypatch):
    from app import tracing
    from langsmith.run_helpers import get_tracing_context
    monkeypatch.setenv('LANGSMITH_API_KEY','fixture-only')
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    def unavailable(*args):raise ValueError('fixture SDK initialization error')
    monkeypatch.setattr(tracing,'_client',unavailable)
    with tracing.trace_scope('job','conversation'):
        assert get_tracing_context()['enabled'] is False
