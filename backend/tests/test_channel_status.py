"""渠道设置展示真实最近工具结果；准备好不代表已取得客户或平台持续可访问。"""
import uuid
import pytest


@pytest.fixture
def ledger(client):
    """client确保隔离库；仅清理本用例合成账本，避免未来冷却污染后续回归。"""
    from app.db import Session,ToolCall
    key='channel-status-'+uuid.uuid4().hex
    yield key
    with Session.begin() as db:db.query(ToolCall).filter(ToolCall.job_id==key).delete(synchronize_session=False)


def test_read_success_does_not_clear_search_limit_or_expose_content(client,monkeypatch,ledger):
    """client为隔离API、monkeypatch固定时钟；同渠道读成功不得清除检索受限，结果不得泄漏正文/Key。"""
    from app.db import Session,ToolCall
    import app.channel_status as module
    clock=10_000_000_000.0
    monkeypatch.setattr(module.time,'time',lambda:clock)
    with Session.begin() as db:
        db.add(ToolCall(job_id=ledger,operation_id=uuid.uuid4().hex,tool='search_accounts',channel='mall_directory',
            attempts=1,last_attempt_epoch=clock,status='rate_limited',retry_after_epoch=clock+60,
            result={'error':'provider_rate_limited','body':'PRIVATE_SOURCE','key':'PRIVATE_KEY'}))
        db.add(ToolCall(job_id=ledger,operation_id=uuid.uuid4().hex,tool='fetch_source',channel='mall_directory',
            attempts=1,last_attempt_epoch=clock,status='completed',elapsed_ms=1234,result={'sources':[{'body':'PRIVATE_SOURCE','url':'https://example.org'}]}))
    response=client.get('/api/channels');assert response.status_code==200
    assert 'PRIVATE_SOURCE' not in response.text and 'PRIVATE_KEY' not in response.text
    channels={row['id']:row for row in response.json()}
    assert channels['mall_directory']['status']=='ready'
    assert channels['mall_directory']['runtime']['search']['cooling_down']
    assert channels['mall_directory']['runtime']['read']['label']=='最近成功'
    assert channels['mall_directory']['runtime']['read']['source_count']==1
    assert channels['qcc_public']['runtime']['search']['cooling_down']
    assert channels['company_api']['status']=='authorization_required'
    assert not channels['company_api']['runtime']['search']['cooling_down']
    monkeypatch.setattr(module.time,'time',lambda:clock+61)
    expired={row['id']:row for row in module.channel_status([])}
    assert not expired['mall_directory']['runtime']['search']['cooling_down']
    assert expired['mall_directory']['runtime']['search']['label']=='最近受限'


def test_empty_response_and_site_failure_are_not_platform_success(client,monkeypatch,ledger):
    """隔离模拟站点失败与空来源；不把成功HTTP空正文当取得资料，也不把单站失败扩散其他渠道。"""
    from app.db import Session,ToolCall
    import app.channel_status as module
    clock=20_000_000_000.0
    monkeypatch.setattr(module.time,'time',lambda:clock)
    with Session.begin() as db:
        for tool,status,result in [('search_accounts','completed',{'sources':[]}),('fetch_source','unavailable',{'error':'site_access_restricted'})]:
            db.add(ToolCall(job_id=ledger,operation_id=uuid.uuid4().hex,tool=tool,channel='ccgp',
                attempts=1,last_attempt_epoch=clock,status=status,result=result))
    channels={row['id']:row for row in module.channel_status(['ccgp'])}
    assert channels['ccgp']['runtime']['search']['label']=='最近无结果'
    assert channels['ccgp']['runtime']['read']['label']=='最近读取失败'
    assert not channels['ccgp']['runtime']['search']['cooling_down']
    assert channels['brand_directory']['runtime']['read']['label']!='最近读取失败'
