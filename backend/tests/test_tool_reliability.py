"""工具可靠性：网站指引重试、Pydantic输出校验、跨任务复用、招投标数据复用判断与检索结果校验，全部离线执行。"""
import asyncio
import uuid
import pytest


@pytest.fixture()
def job(client):
    """client为隔离API；返回新建运行中任务ID。"""
    from app.db import Session, Conversation, Job
    with Session.begin() as db:
        conversation = Conversation(); db.add(conversation); db.flush()
        row = Job(conversation_id=conversation.id, prompt='可靠性测试', client_token='rel-' + uuid.uuid4().hex, status='running')
        db.add(row); db.flush()
        return row.id


def test_retry_only_transient_errors():
    """临时错误可重试；验证码、登录、限流、404与输出不合格永不重试。"""
    from app.site_guides import retryable, retry_policy
    assert retryable('timeout') and retryable('http_503') and retryable('search_failed')
    for code in ('site_verification_required', 'auth_required', 'provider_rate_limited', 'http_404', 'bad_tool_output', ''):
        assert not retryable(code)
    assert retry_policy('qianlima').max_attempts == 3 and retry_policy(url='https://www.anfangzhaobiao.com/qiye/x/').max_attempts == 2


def test_ledger_retries_then_succeeds_and_validates(job):
    """首次超时类错误按策略重试，第二次成功；输出经模型校验，记录真实尝试次数。"""
    from app.tender_intel import Ledger
    from app.tender_models import PlatformSearchOutput
    from app.site_guides import RetryPolicy
    calls = []
    def fn():
        calls.append(1)
        if len(calls) == 1: return {'notices': [], 'error': 'timeout'}
        return {'notices': [{'title': '测试采购公告', 'published_at': '2026-10-01'}], 'status': 'ok'}
    result = asyncio.run(Ledger(job).run('search_tenders', '测试', {'query': 'x', 'source': 'qianlima'}, fn, 30, model=PlatformSearchOutput,
                                         policy=RetryPolicy(max_attempts=3, backoff_seconds=[0.01])))
    assert len(calls) == 2 and result['attempts'] == 2 and result['notices'][0]['title'] == '测试采购公告'


def test_ledger_never_retries_verification_and_rejects_bad_output(job):
    """验证页错误只尝试一次；不符合模型的输出记为bad_tool_output。"""
    from app.tender_intel import Ledger
    from app.tender_models import PageReadOutput
    from app.site_guides import RetryPolicy
    calls = []
    def blocked():
        calls.append(1); return {'text': '', 'error': 'site_verification_required'}
    result = asyncio.run(Ledger(job).run('read_tender', '测试', {'url': 'https://a.example/1'}, blocked, 30, model=PageReadOutput,
                                         policy=RetryPolicy(max_attempts=3, backoff_seconds=[0.01])))
    assert len(calls) == 1 and result['error'] == 'site_verification_required'
    bad = asyncio.run(Ledger(job).run('read_tender', '测试', {'url': 'https://a.example/2'}, lambda: {'text': 'x', 'articles': [{'title': ''}]}, 30,
                                      model=PageReadOutput))
    assert bad['error'] == 'bad_tool_output'


def test_ledger_reuses_recent_result_from_other_job(client, job):
    """其他任务近期同参数检索已完成时直接复用，不再调用站点，并标明来源任务。"""
    from app.db import Session, Conversation, Job
    from app.tender_intel import Ledger
    with Session.begin() as db:
        conversation = Conversation(); db.add(conversation); db.flush()
        other = Job(conversation_id=conversation.id, prompt='另一任务', client_token='rel-' + uuid.uuid4().hex, status='running'); db.add(other); db.flush()
        other_id = other.id
    args = {'query': '复用测试企业', 'source': 'qianlima'}
    asyncio.run(Ledger(other_id).run('search_tenders', '测试', args, lambda: {'notices': [{'title': '已保存公告'}]}, 30))
    called = []
    result = asyncio.run(Ledger(job).run('search_tenders', '测试', args, lambda: called.append(1) or {'notices': []}, 30, reuse_days=1))
    assert not called and result['reused'] and result['reused_from_job'] == other_id and result['notices'][0]['title'] == '已保存公告'


def test_reuse_decision_respects_window_and_refresh_words(job):
    """24小时内采集过的企业复用已保存记录；超过时限或用户要求最新时重新采集。"""
    from app.db import Session, now
    from app.company_service import ensure_company
    from app.company_models import TenderRecord
    from app.tender_intel import reusable_summary, REFRESH_RE
    with Session.begin() as db:
        company = ensure_company(db, '复用判断测试有限公司')
        company.metadata_json = {'tender_collected_at': now()}
        db.add(TenderRecord(unique_key=uuid.uuid4().hex, company_id=company.id, role='buyer', title='已存采购', confidence='listing'))
    reused = reusable_summary(job, '复用判断测试有限公司', 24)
    assert reused['reused'] and reused['records'] == {'buyer': 1}
    assert reusable_summary(job, '复用判断测试有限公司', 0) is None
    assert REFRESH_RE.search('帮我查一下最新的采购') and not REFRESH_RE.search('查一下采购与上下游')


def test_web_search_rows_reject_redirects_and_bad_dates():
    """检索结果只保留原始地址，搜索引擎跳转/推广链接拒绝，非法日期置空。"""
    from pydantic import ValidationError
    from app.web_search import WebSearchRow
    row = WebSearchRow(engine='baidu', title='某公司招标公告', url='https://www.ccgp.gov.cn/a.htm', published_at='昨天')
    assert row.published_at == ''
    for url in ('https://www.baidu.com/link?url=abc', 'http://nourl.ubs.baidu.com/1', 'https://www.sogou.com/link?url=x'):
        with pytest.raises(ValidationError):
            WebSearchRow(engine='baidu', title='标题标题', url=url)


def test_structured_summary_matches_database(job):
    """研究摘要由数据库生成：采购数、对手方与工商字段与详情一致。"""
    from app.tender_intel import TenderCollector
    from app.tender_service import research_summary
    collector = TenderCollector(job, '摘要测试科技有限公司', {})
    collector.add_record('设备采购', 'buyer', 'listing', published_at='2026-09-01', items=[{'name': '示波器', 'quantity': '2', 'unit': '台', 'spec': ''}])
    collector.add_relation('客户研究院', 'customer', 'platform_stats', count=4)
    collector.registration = {'法定代表人': '李四'}
    summary = collector.persist()
    result = research_summary(summary['company_id'])
    assert result.purchases == 1 and result.customers[0].name == '客户研究院' and result.customers[0].count == 4
    assert result.registration['法定代表人'] == '李四' and result.top_items == ['示波器']


def test_reversed_subsidiary_direction_detected():
    """原文写明“本企业是对方的子公司”时判定为方向相反；“本企业持有对方股权、对方为其子公司”不误判。"""
    from app.company_validation import reversed_subsidiary
    own = '北京航天广通科技有限公司'
    assert reversed_subsidiary(own, '中国航天科工二院二十三所', '北京航天广通科技有限公司是中国航天科工二院二十三所下属全资子公司')
    assert reversed_subsidiary(own, '中国航天科工集团第二研究院二十三所',
        '北京航天广通科技有限公司（以下简称“广通公司”）成立于 1998 年，是中国航天科工集团第二研究院二十三所的全资子公司')
    assert not reversed_subsidiary('甲科技有限公司', '乙电子有限公司', '甲科技有限公司持有乙电子有限公司100%股权，乙电子有限公司为其全资子公司')
