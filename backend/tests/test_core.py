import json

from fastapi.testclient import TestClient

from app import crawl, services
from app.main import app
from app.research import store
from app.research.schemas import CompanyExtract, NoticeExtract, Party, ProfileField
from app.research.verify import company_name, grounded, grounded_value, plausible_company
from app.sites import SITES, enabled, site_of

URL = 'https://www.ccgp.gov.cn/cggg/zygg/cjgg/202610/t20261027_27568291.htm'


def test_grounding_ignores_whitespace_and_width(ccgp_text):
    assert grounded('供应商名称：天津市金泰志达科技发展有限公司', ccgp_text)
    assert grounded('中标（成交）金额：3.8000000（万元）', ccgp_text)
    assert not grounded('供应商名称：北京某某科技有限公司', ccgp_text)
    assert not grounded_value('中国船级社天津分社', '名 称：中国船级社', ccgp_text)


def test_company_name_rules():
    assert company_name(' 华为技术(深圳)有限公司 ') == '华为技术（深圳）有限公司'
    assert not plausible_company('广东南×××')
    assert not plausible_company('详见公告')
    assert plausible_company('中国船级社')


def test_parse_output_skips_progress_lines():
    assert crawl.parse_output('[luz-crawl] Opening x\n[LuzCrawl] y\n{\n  "status": "captured"\n}') == {'status': 'captured'}
    assert crawl.parse_output('[luz-crawl] a\n[\n  {"id": 1}\n]') == [{'id': 1}]


def test_read_page_rejects_invalid_content(tmp_path):
    (tmp_path / 'raw').mkdir()
    (tmp_path / 'raw/content.json').write_text(json.dumps({'text': '请登录', 'url_check': {'valid_content': False}}),
                                               encoding='utf-8')
    page = crawl.read_page({'status': 'captured', 'folder': str(tmp_path)})
    assert page.status == 'blocked' and not page.ok


def test_sites_rules():
    assert SITES['ggzy'].detail_url('https://www.ggzy.gov.cn/information/deal/html/a/1/2.html').endswith('/html/b/1/2.html')
    assert site_of(URL).id == 'ccgp'
    assert 'kw=%E9%98%B2' in SITES['ccgp'].search_url('防火墙', 30)
    assert 'searchtype=2' in SITES['ccgp'].search_url('某公司', 30, fulltext=True)
    ids = [s.id for s in enabled('procurement', {'sources': {'ggzy': False}})]
    assert 'ggzy' not in ids and 'bidcenter' not in ids and 'ccgp' in ids


def _extract() -> NoticeExtract:
    return NoticeExtract(
        is_notice=True, title='中国船级社天津分社政府采购防火墙2台成交公告', kind='award',
        project_code='HT26092484782420', published_on='2026年10月27日', amount=38000,
        amount_quote='中标（成交）金额：3.8000000（万元）', items='防火墙 华为 USG6525F 2台',
        items_quote='防火墙  	   华为  	   USG6525F  	   2',
        buyer=Party(name='中国船级社', quote='名 称：中国船级社'),
        winners=[Party(name='天津市金泰志达科技发展有限公司', quote='供应商名称：天津市金泰志达科技发展有限公司', amount=38000),
                 Party(name='编造的科技有限公司', quote='供应商名称：编造的科技有限公司')])


def test_save_notice_keeps_only_grounded_values(ccgp_text):
    page = crawl.Page(url=URL, status='captured', title='成交公告', text=ccgp_text)
    source_id = store.save_source(page, 'ccgp', 'notice', 'job')
    saved = store.save_notice(_extract(), source_id, page, {})
    assert saved['buyer_id'] and len(saved['winner_ids']) == 1
    detail = services.company_detail(saved['buyer_id'])
    notice = detail['purchases'][0]
    assert notice['published_on'] == '2026-10-27' and notice['amount'] == 38000
    assert notice['project_code'] == 'HT26092484782420'
    assert detail['relations']['suppliers'][0]['name'] == '天津市金泰志达科技发展有限公司'
    winner = services.company_detail(saved['winner_ids'][0])
    assert winner['relations']['customers'][0]['name'] == '中国船级社'
    # 重复保存同一公告不产生重复参与方
    store.save_notice(_extract(), source_id, page, {})
    assert services.company_detail(saved['buyer_id'])['stats']['purchases'] == 1


def test_save_profile_requires_value_in_quote(ccgp_text):
    page = crawl.Page(url='https://example.com/profile', status='captured', text=ccgp_text)
    source_id = store.save_source(page, 'baidu', 'business', 'job')
    from app.db import Session
    with Session.begin() as db:
        company_id = store.upsert_company(db, '中国船级社').id
    extract = CompanyExtract(matched=True, name='中国船级社',
                             address=ProfileField(value='天津市滨海新区开发区南海路11号明珠园A座',
                                                  quote='地址：天津市滨海新区开发区南海路11号明珠园A座'),
                             legal_person=ProfileField(value='张三', quote='联系方式：孟超'))
    assert store.save_profile(company_id, extract, source_id, ccgp_text) == 1
    profile = {item['field']: item for item in services.company_detail(company_id)['profile']}
    assert 'legal_person' not in profile and profile['address']['evidence']['url'] == 'https://example.com/profile'


def test_score_prefers_active_recent():
    assert store.score_lead('tender', '2026-10-20', '') > store.score_lead('award', '2026-10-20', '')
    assert store.score_lead('tender', '2020-01-01', '') == 10


def test_api_conversation_lead_flow(monkeypatch, ccgp_text):
    started = []
    monkeypatch.setattr('app.runner.start', started.append)
    client = signed_in()
    conversation = client.post('/api/conversations').json()
    sent = client.post(f'/api/conversations/{conversation["id"]}/messages', json={'content': '找防火墙买家'})
    assert sent.status_code == 202 and started == [sent.json()['job']['id']]
    busy = client.post(f'/api/conversations/{conversation["id"]}/messages', json={'content': '再来'})
    assert busy.status_code == 400
    company = client.get('/api/companies', params={'q': '船级社'}).json()['items'][0]
    lead = client.post(f'/api/companies/{company["id"]}/lead', json={}).json()
    patched = client.patch(f'/api/leads/{lead["id"]}', json={'status': 'contacted', 'owner': '王五'}).json()
    assert patched['status'] == 'contacted' and patched['contacts'] == []
    listing = client.get('/api/leads', params={'status': 'contacted'}).json()
    assert listing['total'] == 1 and listing['counts']['contacted'] == 1 and listing['owners'] == ['王五']
    assert client.post(f'/api/leads/{lead["id"]}/followups', json={'content': '电话沟通'}).json()['followups']
    assert client.get('/api/leads/export').status_code == 200
    assert client.get(f'/api/companies/{company["id"]}/export').status_code == 200
    assert client.patch('/api/settings', json={'sources': {'ggzy': False, 'nope': True}}).json()['sources'] == {'ggzy': False}


def test_new_lead_gets_score_and_keeps_best_notice(ccgp_text):
    page = crawl.Page(url=URL + '?lead', status='captured', text=ccgp_text)
    source_id = store.save_source(page, 'ccgp', 'notice', 'job')
    saved = store.save_notice(_extract().model_copy(update={'project_code': ''}), source_id, page, {})
    lead_id = store.upsert_lead(saved['buyer_id'], saved['notice_id'], 'c1', 60, '中标结果')
    assert store.upsert_lead(saved['buyer_id'], saved['notice_id'], 'c1', 30, '旧公告') == lead_id
    assert services.lead_detail(lead_id)['score'] == 60


def test_same_project_from_two_sites_is_one_notice(ccgp_text):
    first = crawl.Page(url='https://www.ccgp.gov.cn/a.htm', status='captured', text=ccgp_text)
    second = crawl.Page(url='https://www.ggzy.gov.cn/information/deal/html/b/x.html', status='captured', text=ccgp_text)
    a = store.save_notice(_extract(), store.save_source(first, 'ccgp', 'notice', 'job'), first, {})
    b = store.save_notice(_extract(), store.save_source(second, 'ggzy', 'notice', 'job'), second, {})
    assert a['notice_id'] == b['notice_id']


def test_title_key_strips_codes_and_site_suffix():
    from app.research.pipeline import _title_key
    assert _title_key('Z1303252600932401秦皇岛市公安局防火墙结果公告') == _title_key('秦皇岛市公安局防火墙结果公告')
    assert _title_key('防火墙项目中标结果公告-交易公开-全国公共资源交易平台') == _title_key('防火墙项目中标结果公告')


def test_every_stage_is_a_method():
    from app.research.pipeline import STAGES, Run
    for stages in STAGES.values():
        for stage in stages:
            assert callable(getattr(Run, stage)), stage
    assert not any(isinstance(getattr(Run, name, None), str) for stage in STAGES.values() for name in stage)


def test_company_search_windows_respect_site_span():
    from app.research.pipeline import Run
    assert Run._windows(SITES['ccgp'], 730) == [(365, 0), (365, 365)]
    assert Run._windows(SITES['bidcenter'], 730) == [(730, 0)]
    assert 'start_time=' in SITES['ccgp'].search_url('某公司', 365, True, 365)
    assert not SITES['ggzy'].by_company and SITES['ccgp'].by_company


def test_crawl_errors_are_readable():
    assert crawl.reason('browserType.launchPersistentContext: Target page closed\nlogs') .startswith('浏览器启动失败')
    assert crawl.reason('') == ''


def test_overview_counts_and_shares():
    client = signed_in()
    data = client.get('/api/overview', params={'days': 30}).json()
    assert data['kpis']['new_leads'] >= 1 and data['kpis']['notices'] >= 1
    assert data['trend'] and {'date', 'leads', 'notices'} <= set(data['trend'][0])
    assert sum(item['count'] for item in data['lead_status']) == data['kpis']['new_leads']
    assert client.get('/api/overview', params={'days': 0}).json()['kpis']['companies'] >= data['kpis']['companies']


def test_overview_previous_period():
    client = signed_in()
    assert client.get('/api/overview', params={'days': 30}).json()['previous']['new_leads'] == 0
    assert client.get('/api/overview', params={'days': 0}).json()['previous'] == {}


def test_custom_sites_are_validated_and_merged():
    client = signed_in()
    bad = client.post('/api/sources/sites', json={'name': '某站', 'mode': 'template', 'template': 'https://x.com/s'})
    assert bad.status_code == 400 and '{q}' in bad.json()['detail']
    assert client.post('/api/sources/sites', json={'name': '某站', 'mode': 'site_search', 'domain': 'not a domain'}).status_code == 400
    assert client.post('/api/sources/sites', json={'name': '某站', 'template': 'https://x.com/s?k={q}', 'detail': '('}).status_code == 400
    site_id = client.post('/api/sources/sites', json={'name': '省采购网', 'template': 'https://x.com/s?k={q}&d={start_date}',
                                                      'detail': r'x\.com/notice/'}).json()['id']
    listed = {s['id']: s for s in client.get('/api/sources').json()['sites']}
    assert listed[site_id]['custom'] and listed[site_id]['enabled'] and listed['ccgp']['custom'] is False
    from app.sites import enabled, get_site
    assert get_site(site_id).search_url('监控', 30).startswith('https://x.com/s?k=%E7%9B%91%E6%8E%A7&d=20')
    assert site_id in [s.id for s in enabled('procurement', {})]
    assert client.patch('/api/settings', json={'sources': {site_id: False}}).json()['sources'][site_id] is False
    assert site_id not in [s.id for s in enabled('procurement', {'sources': {site_id: False}})]
    assert client.delete(f'/api/sources/sites/{site_id}').status_code == 200
    assert client.delete('/api/sources/sites/ccgp').status_code == 404


def test_job_report_summarises_saved_results(ccgp_text):
    from app.db import Job, Session
    client = signed_in()
    conversation = client.post('/api/conversations').json()
    with Session.begin() as db:
        job = Job(conversation_id=conversation['id'], message_id='m', mode='find_buyers', status='completed',
                  metrics={'elapsed_ms': 90000, 'verify': {'checked': 10, 'kept': 8}},
                  plan={'lists': {'ccgp|防火墙|0': {'site': 'ccgp', 'query': '防火墙', 'status': 'captured', 'links': [{}, {}]}},
                        'read': {'u1': 'saved', 'u2': 'failed'}, 'problems': ['全国公共资源交易平台：读取超时']})
        db.add(job)
        db.flush()
        job_id = job.id
    page = crawl.Page(url=URL + '?report', status='captured', text=ccgp_text)
    saved = store.save_notice(_extract().model_copy(update={'project_code': ''}), store.save_source(page, 'ccgp', 'notice', job_id), page, {})
    store.link_job(job_id, saved['buyer_id'], 'buyer')
    report = client.get(f'/api/jobs/{job_id}/report').json()
    assert report['quality']['rate'] == 0.8 and report['counts']['read_failed'] == 1
    assert report['counts']['notices'] == 1 and report['quality']['complete']['budget'] == 1
    assert report['sites'][0]['name'] == '中国政府采购网' and report['sites'][0]['links'] == 2
    assert report['top'][0]['name'] == '中国船级社' and report['problems'] == ['全国公共资源交易平台：读取超时']


def test_anonymous_buyers_are_rejected():
    assert not plausible_company('某单位1') and not plausible_company('某某公司') and not plausible_company('匿名采购人')
    assert not plausible_company('SPD-08') and plausible_company('华为技术有限公司')


def test_search_rounds_page_then_expand():
    from app.db import Job, Session
    from app.research.pipeline import Run
    client = signed_in()
    conversation = client.post('/api/conversations').json()
    with Session.begin() as db:
        job = Job(conversation_id=conversation['id'], message_id='m', mode='find_buyers',
                  plan={'plan': {'mode': 'find_buyers', 'title': 't', 'keywords': ['服务器', '存储'], 'days': 30}})
        db.add(job)
        db.flush()
        job_id = job.id
    run = Run(job_id)
    sites = [SITES['ccgp'], SITES['ggzy']]
    jobs = run._pending_searches(sites)
    # 第一页：两个关键词 × 两个站点；之后 ccgp 翻页（ggzy 为站内搜索不翻页）
    assert [(j[0].id, j[1], j[4]) for j in jobs[:4]] == [('ccgp', '服务器', 1), ('ggzy', '服务器', 1), ('ccgp', '存储', 1), ('ggzy', '存储', 1)]
    assert [(j[0].id, j[4]) for j in jobs[4:]] == [('ccgp', 2), ('ccgp', 2), ('ccgp', 3), ('ccgp', 3)]
    run.state['lists'] = {Run._search_key(j[0], j[1], 0, j[4]): {} for j in jobs[:4]}
    assert len(run._pending_searches(sites)) == 4


def test_discovered_sites_offer_ready_config():
    store.discover('www.zsjypt.cn', '中山市公共资源交易平台', 'https://www.zsjypt.cn/artical/53/1')
    store.discover('www.zsjypt.cn', '中山市公共资源交易平台', 'https://www.zsjypt.cn/artical/53/1', adopted=1)
    store.discover('www.ccgp.gov.cn', '政府采购网', 'https://www.ccgp.gov.cn/cggg/zygg/a.htm')
    client = signed_in()
    found = client.get('/api/discovered-sources').json()
    assert [f['domain'] for f in found] == ['www.zsjypt.cn']
    assert found[0]['hits'] == 1 and found[0]['adopted'] == 1
    site_id = client.post('/api/sources/sites', json=found[0]['config']).json()['id']
    assert client.get('/api/discovered-sources').json() == []
    client.delete(f'/api/sources/sites/{site_id}')


def signed_in(username: str = 'admin', password: str = 'admin') -> TestClient:
    client = TestClient(app)
    assert client.post('/api/auth/login', json={'username': username, 'password': password}).status_code == 200
    return client


def test_auth_quota_and_isolation(monkeypatch):
    from app import runner
    monkeypatch.setattr(runner, 'start', lambda job_id: None)
    anonymous = TestClient(app)
    assert anonymous.get('/api/conversations').status_code == 401
    assert anonymous.post('/api/auth/login', json={'username': 'admin', 'password': 'wrong'}).json()['detail'] == '账号或密码错误'
    assert anonymous.post('/api/auth/register', json={'username': 'ab', 'password': '123456'}).status_code == 400
    user = TestClient(app)
    me = user.post('/api/auth/register', json={'username': 'trial_user', 'password': 'secret1'}).json()
    assert me['remaining'] == 5 and not me['is_admin']
    assert user.post('/api/auth/register', json={'username': 'trial_user', 'password': 'secret1'}).status_code == 409
    assert user.get('/api/settings').status_code == 403 and user.get('/api/sources').status_code == 403
    for i in range(5):
        conversation = user.post('/api/conversations').json()
        assert user.post(f'/api/conversations/{conversation["id"]}/messages', json={'content': f'找买家{i}'}).status_code == 202
    blocked = user.post(f'/api/conversations/{user.post("/api/conversations").json()["id"]}/messages', json={'content': '再找'})
    assert blocked.status_code == 403 and blocked.json()['detail'] == '使用次数已用完'
    assert user.get('/api/auth/me').json()['remaining'] == 0
    # 其他用户看不到这些对话；管理员不限次数
    admin = signed_in()
    assert admin.get('/api/auth/me').json()['unlimited'] is True
    other = TestClient(app)
    other.post('/api/auth/register', json={'username': 'other_user', 'password': 'secret2'})
    assert other.get('/api/conversations').json() == []
    assert other.get(f'/api/conversations/{conversation["id"]}').status_code == 404
    user.post('/api/auth/logout')
    assert user.get('/api/conversations').status_code == 401



def test_auth_hardening(monkeypatch):
    from app import auth
    monkeypatch.setattr(auth, '_REGISTRATIONS', {})
    monkeypatch.setattr(auth, '_FAILURES', {})
    owner, stranger = TestClient(app), TestClient(app)
    owner.post('/api/auth/register', json={'username': 'owner_user', 'password': 'secret3'})
    stranger.post('/api/auth/register', json={'username': 'stranger_user', 'password': 'secret4'})
    # 附件只对上传者可见
    uploaded = owner.post('/api/attachments', files={'file': ('需求.txt', '采购 UPS 电源'.encode(), 'text/plain')})
    assert uploaded.status_code == 200
    assert owner.get(f'/api/attachments/{uploaded.json()["id"]}').status_code == 200
    assert stranger.get(f'/api/attachments/{uploaded.json()["id"]}').status_code == 404
    # 安全响应头
    response = owner.get('/api/health')
    assert response.headers['X-Frame-Options'] == 'DENY' and response.headers['X-Content-Type-Options'] == 'nosniff'
    # 连续失败 5 次后锁定，并提示剩余时间
    for _ in range(5):
        assert stranger.post('/api/auth/login', json={'username': 'owner_user', 'password': 'bad'}).status_code == 401
    locked = stranger.post('/api/auth/login', json={'username': 'owner_user', 'password': 'secret3'})
    assert locked.status_code == 429 and '分钟后再试' in locked.json()['detail']
    # 同一来源注册频率受限
    for i in range(3):
        TestClient(app).post('/api/auth/register', json={'username': f'bulk_user{i}', 'password': 'secret5'})
    assert TestClient(app).post('/api/auth/register', json={'username': 'bulk_user9', 'password': 'secret5'}).status_code == 429
