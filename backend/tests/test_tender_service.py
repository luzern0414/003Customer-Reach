"""招投标服务层：记录合并、对手方推导、详情投影、覆盖判断与节点跳过规则，全部在隔离库执行且不访问网络。"""
import asyncio
import uuid
import pytest


@pytest.fixture()
def job(client):
    """client为隔离API；创建会话与任务，返回job_id供采集器持久化使用。"""
    from app.db import Session, Conversation, Job
    with Session.begin() as db:
        conversation = Conversation(); db.add(conversation); db.flush()
        row = Job(conversation_id=conversation.id, prompt='招投标测试', client_token='tender-' + uuid.uuid4().hex, status='running')
        db.add(row); db.flush()
        return row.id


def collector(job_id, name='测试航天电子科技有限公司'):
    """返回不触发网络的采集器实例，仅用于合并/推导/持久化。"""
    from app.tender_intel import TenderCollector
    return TenderCollector(job_id, name, {})


def test_record_merge_upgrades_but_never_downgrades(job):
    """同标题记录：详情确认可升级列表记录；未识别角色的详情只补字段，不覆盖已确认角色。"""
    c = collector(job)
    c.add_record('GTX询价单001', 'buyer', 'listing', published_at='2026-10-01', quote='GTX询价单001')
    c.add_record('GTX询价单001', 'mentioned', 'detail', items=[{'name': '继电器', 'quantity': '2', 'unit': '个', 'spec': ''}])
    record = next(iter(c.records.values()))
    assert record['role'] == 'buyer' and record['items'][0]['name'] == '继电器' and record['published_at'] == '2026-10-01'
    c.add_record('某研究院设备采购结果公告', 'related', 'index')
    c.add_record('某研究院设备采购结果公告', 'winner', 'detail', buyer_name='某研究院', amount='12万元')
    upgraded = [r for r in c.records.values() if r['title'].startswith('某研究院')][0]
    assert upgraded['role'] == 'winner' and upgraded['confidence'] == 'detail' and upgraded['amount'] == '12万元'


def test_tender_evidence_is_in_company_source_count_and_document_scope(job,client):
    from app.gateway import archive_sources
    from app.company_service import company_detail
    rows=archive_sources(job,[{'title':'隔离候选公告','url':'https://www.ebnew.com/owned',
        'body':'第二成交候选人为：测试航天电子科技有限公司'},
        {'title':'其他企业公告','url':'https://www.ebnew.com/unrelated','body':'采购人：其他企业有限公司'}],'网页正文','procurement')
    c=collector(job);c.reused=True
    c.add_record('隔离候选公告','candidate','detail',quote=rows[0]['body'],evidence_id=rows[0]['id'],url=rows[0]['url'])
    result=c.persist();cid=result['company_id']
    detail=company_detail(cid)
    assert detail['header']['source_count']==1 and detail['sources'][0]['id']==rows[0]['id']
    assert detail['tenders']['reused'] is True
    document=client.get('/api/companies/'+cid+'/documents/'+rows[0]['id'])
    assert document.status_code==200
    assert document.json()['entries'][0]['scope'].startswith('候选')
    assert document.json()['entries'][0]['evidence_refs'][0]['text']==rows[0]['body']
    assert client.get('/api/companies/'+cid+'/documents/'+rows[1]['id']).status_code==404
    from app.company_research import company_summary
    answer=company_summary({'company_ids':[cid],'warnings':['TimeoutError']})
    assert '候选/备选' in answer and '隔离候选公告' in answer and rows[0]['url'] in answer
    assert '最终中标' in answer and '不代表没有采购需求' in answer


def test_relation_only_source_has_document_entry_and_original_quote(job,client):
    from app.gateway import archive_sources
    from app.company_service import company_detail
    rows=archive_sources(job,[{'title':'平台合作统计','url':'https://example.com/stats',
        'body':'合肥客户研究院 合作次数：3'}],'网页正文','procurement')
    c=collector(job,'关系来源独立测试'+uuid.uuid4().hex+'有限公司')
    c.add_relation('合肥客户研究院','customer','platform_stats',count=3,quote=rows[0]['body'],
        evidence_id=rows[0]['id'],url=rows[0]['url'])
    cid=c.persist()['company_id']
    assert company_detail(cid)['header']['source_count']==1
    document=client.get('/api/companies/'+cid+'/documents/'+rows[0]['id']).json()
    entry=document['entries'][0]
    assert entry['kind']=='relation' and entry['title']=='合肥客户研究院'
    assert entry['evidence_refs'][0]['text']==rows[0]['body']
    assert '平台合作统计' in entry['scope'] and '交易金额' in entry['scope']


def test_relations_derived_from_records_and_self_excluded(job):
    """自身采购的中标方为供应商，自身中标的采购方为客户，同场候选为竞争对手；目标自身与代理机构不进入客户。"""
    c = collector(job)
    c.add_record('电缆采购结果公告', 'buyer', 'detail', winner_names=['北京电缆供应有限公司'], published_at='2026-09-01')
    c.add_record('某大学雷达系统采购结果公告', 'winner', 'detail', buyer_name='某某大学', candidate_names=['测试航天电子科技有限公司', '竞争科技有限公司'])
    c.add_record('某中心维保项目', 'winner', 'detail', buyer_name='某招标代理有限公司')
    c.derive_relations()
    kinds = {(r['name'], r['kind']) for r in c.relations.values()}
    assert ('北京电缆供应有限公司', 'supplier') in kinds and ('某某大学', 'customer') in kinds and ('竞争科技有限公司', 'competitor') in kinds
    assert not any(name == '测试航天电子科技有限公司' for name, _ in kinds)
    assert not any(kind == 'customer' and '代理' in name for name, kind in kinds)


def test_persist_and_detail_projection(job):
    """持久化后详情页返回招投标汇总、记录、对手方（跨口径合并）与工商摘要；重复持久化幂等。"""
    from app.company_service import company_detail, list_companies
    c = collector(job)
    c.add_record('GTX询价单002', 'buyer', 'listing', published_at='2026-10-02', items=[{'name': '电容', 'quantity': '5', 'unit': '个', 'spec': ''}])
    c.add_relation('合肥客户研究院', 'customer', 'platform_stats', count=3, quote='| 合肥客户研究院 | 3 |', url='https://example.com/qiye/x/4/')
    c.add_relation('合肥客户研究院', 'customer', 'records', record_key='k', latest_at='2026-08-01')
    c.registration = {'法定代表人': '张三', '注册资本': '100万人民币', 'source_url': 'https://example.com/qiye/x/6/'}
    summary = c.persist()
    c.persist()
    detail = company_detail(summary['company_id'])
    tenders = detail['tenders']
    assert tenders['summary']['purchases'] == 1 and tenders['top_items'][0]['name'] == '电容'
    customer = tenders['relations']['customer'][0]
    assert customer['name'] == '合肥客户研究院' and customer['count'] == 3 and set(customer['bases']) == {'platform_stats', 'records'}
    assert detail['registration']['fields'][0] == {'label': '法定代表人', 'value': '张三'}
    card = next(x for x in list_companies(q='测试航天电子')['items'])
    assert card['tender_purchases'] == 1 and card['tender_customers'] == 1


def test_tender_coverage_marks_fields_covered():
    """平台已确认的采购/供应商/客户视为字段已覆盖，其余缺口保留。"""
    from app.company_research import apply_tender_coverage
    coverage = {'missing_fields': ['procurement', 'supplier', 'customer', 'website'], 'companies': [{'target': 'A', 'missing_fields': ['procurement', 'website']}]}
    state = {'company_tender_summary': {'A': {'records': {'buyer': 3}, 'relations': {'supplier': 1, 'customer': 2}}}}
    result = apply_tender_coverage(coverage, state)
    assert result['missing_fields'] == ['website'] and result['companies'][0]['missing_fields'] == ['website']


def test_node_skips_without_procurement_fields_or_when_offline(monkeypatch):
    """未请求采购/上下游字段或离线开关时不发起采集。"""
    from app import tender_intel
    called = []
    class Fake:
        def __init__(self, *args): called.append(args)
        async def collect(self): return {'company_id': 'x', 'records': {'buyer': 1}, 'relations': {}}
    monkeypatch.setattr(tender_intel, 'TenderCollector', Fake)
    state = {'job_id': 'j', 'options': {'tender_enabled': True}, 'company_intent_targets': ['测试企业有限公司'], 'company_requested_fields': ['name', 'business']}
    assert asyncio.run(tender_intel.company_tenders(state)) == {'company_tender_summary': {}}
    monkeypatch.setenv('CLIENTREACH_TENDER_ENABLED', 'true')
    result = asyncio.run(tender_intel.company_tenders({**state, 'company_requested_fields': ['procurement']}))
    assert called and result['company_ids'] == ['x']


def test_learning_is_idempotent_per_job(job):
    """任务结束学习只累计一次，经验摘要包含来源采用统计。"""
    from app.db import Session, Job, ToolCall
    from app.search_memory import learn_from_job, store, NS_SOURCES
    with Session.begin() as db:
        row = db.get(Job, job); row.status = 'completed'
        db.add(ToolCall(job_id=job, operation_id=uuid.uuid4().hex, tool='search_tenders', channel='tender', arguments={'source': 'qianlima', 'query': 'x'},
                        result={'notices': [{'title': 't'}]}, status='completed'))
    first = learn_from_job(job)
    assert first['sources'] == 1 and learn_from_job(job) == {}
    assert store.get(NS_SOURCES, 'tender:qianlima').value['attempts'] >= 1


def test_logo_candidates_prefer_large_icons_and_logo_images():
    """头像图标顺序：apple-touch-icon、大尺寸icon、页头logo图片，小favicon兜底。"""
    from app.logo_service import candidates
    html = ('<link rel="icon" href="/favicon-16.png" sizes="16x16"><link rel="icon" href="/icon-192.png" sizes="192x192">'
            '<link rel="apple-touch-icon" href="/touch.png"><img class="site-logo" src="/img/logo.png">')
    assert candidates(html, 'https://example.com/') == ['https://example.com/touch.png', 'https://example.com/icon-192.png',
        'https://example.com/img/logo.png', 'https://example.com/favicon-16.png', 'https://example.com/favicon.ico']


def test_candidate_brief_has_role_bid_history_and_competitor_source(job):
    from pathlib import Path
    from app.db import Session, Evidence
    from app.tender_service import tender_brief
    name = '成都宏天智电子有限公司'
    body = (Path(__file__).parent / 'fixtures/tender/hongtianzhi_candidates.md').read_text(encoding='utf-8')
    url = 'https://www.cqggzy.com/trade/test-candidate'
    with Session.begin() as db:
        evidence = Evidence(job_id=job, title='视频监控系统的中标候选人公示', body=body, url=url, kind='网页读取')
        db.add(evidence); db.flush(); eid = evidence.id
    c = collector(job, name)
    c.add_record('视频监控系统的中标候选人公示', 'candidate', 'detail', buyer_name='重庆市映天辉氯碱化工有限公司',
                 candidate_names=[name, '杭州海康威视数字技术股份有限公司'], url=url, evidence_id=eid, quote=name)
    c.derive_relations(); result = c.persist()
    with Session() as db:
        brief = tender_brief(db, result['company_id'])
    assert brief['summary']['wins'] == 0 and brief['summary']['candidates'] == 1
    record = brief['recent_wins'][0]
    assert record['role'] == 'candidate' and record['candidate_bid']['price'] == '1149600.00'
    assert len(record['disclosed_performance']) == 6
    assert brief['customers'] == [] and brief['suppliers'] == []
    assert brief['competitors'][0]['evidence'][0]['url'] == url
    assert brief['competitors'][0]['record_ids']


def test_competitor_only_brief_does_not_disappear(job):
    from app.db import Session
    from app.tender_service import tender_brief
    c = collector(job, '仅有竞争线索测试有限公司')
    c.add_relation('竞争科技有限公司', 'competitor', 'platform_stats', count=1, url='https://example.com/competition', quote='竞争科技有限公司')
    result = c.persist()
    with Session() as db:
        assert tender_brief(db, result['company_id'])['competitors'][0]['name'] == '竞争科技有限公司'


def test_platform_cache_is_not_reported_as_all_fresh(job, monkeypatch):
    c = collector(job)
    async def cached(*args, **kwargs):
        return {'notices': [], 'reused': True, 'reused_from_job': 'previous-job'}
    monkeypatch.setattr(c.ledger, 'run', cached)
    asyncio.run(c.search_platforms())
    assert c.persist()['reused'] is True
