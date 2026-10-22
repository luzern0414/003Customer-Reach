"""Focused QCC evidence and citation regression tests."""
import json
import asyncio
import uuid
import pytest
from app.qcc_mcp import QccCallResult, archive_qcc_result

@pytest.fixture(autouse=True)
def enable_qcc(monkeypatch):
    monkeypatch.setenv('CLIENTREACH_QCC_ENABLED','true')


def test_archive_projection_is_stable(monkeypatch):
    # Contract smoke test: projection is deterministic and excludes credentials.
    result = QccCallResult('company', 'lookup', {'name': '示例'}, 'hash-1', '2026-01-01T00:00:00Z')
    assert result.authorized is True
    assert json.dumps(result.response, ensure_ascii=False, sort_keys=True, separators=(',', ':')) == '{"name":"示例"}'


def test_archive_qcc_result_is_authorized_and_idempotent(client):
    from app.db import Session
    result = QccCallResult('company', 'get_basic_info', {'name': '合成企业'}, 'response-hash', '2026-01-01T00:00:00Z')
    jid = _job()
    first = archive_qcc_result(jid, result, '合成企业基本信息')
    second = archive_qcc_result(jid, result, '合成企业基本信息')
    assert first['id'] == second['id']
    assert first['channel'] == 'qcc_mcp' and first['kind'] == '授权数据' and first['url'] == ''
    assert first['source_meta']['origin'] == 'qcc_mcp' and first['source_meta']['authorized'] is True


def test_public_qcc_source_cannot_satisfy_authorized_citation(client):
    from app.company_validation import cited_source
    from app.db import Evidence, Session
    jid = _job()
    with Session.begin() as db:
        row = Evidence(job_id=jid, channel='qcc_public', kind='网页正文', title='公开页面',
                       url='https://www.qcc.com/firm/example', body='公开页面正文。')
        db.add(row); db.flush(); sid = row.id
    with Session() as db, pytest.raises(Exception):
        cited_source(db, sid, '$.name: 公开页面正文。', {sid})


def test_authorized_qcc_citation_requires_structured_path(client):
    from app.company_validation import cited_source
    from app.db import Evidence, Session
    jid = _job()
    with Session.begin() as db:
        row = Evidence(job_id=jid, channel='qcc_mcp', kind='授权数据', title='授权企业信息', url='',
                       body='{"name":"合成企业"}',
                       source_meta={'origin':'qcc_mcp','authorized':True,'server':'company','tool':'get_basic_info','response_hash':'h'})
        db.add(row); db.flush(); sid = row.id
    with Session() as db:
        assert cited_source(db, sid, '$.name: 合成企业', {sid}).id == sid
        with pytest.raises(Exception, match='结构化字段路径'):
            cited_source(db, sid, '合成企业', {sid})


def test_archive_large_qcc_payload_remains_valid_json(client):
    from app.db import Session, Evidence
    jid = _job()
    result = QccCallResult('company', 'get_basic_info', {'name': '合成企业', 'detail': 'x' * 300000}, 'large-hash', '2026-01-01T00:00:00Z')
    archived = archive_qcc_result(jid, result, '大型响应')
    payload = json.loads(archived['body'])
    assert payload['name'] == '合成企业'
    assert len(archived['body']) <= 200000


def _job():
    from app.db import Conversation, Session, Job
    key = 'qcc-' + uuid.uuid4().hex
    with Session.begin() as db:
        conversation = Conversation(title='企查查测试会话')
        db.add(conversation)
        db.flush()
        db.add(Job(id=key, conversation_id=conversation.id, prompt='查询合成企业', status='queued', metrics={}))
    return key


def test_qcc_broker_rejects_model_tool_injection(client):
    from app.research_tools import ToolBroker
    broker = ToolBroker(_job(), {'enabled_channels': ['official'], 'max_qcc_calls': 1}, {})
    result = asyncio.run(broker.execute('qcc_company_lookup', {'name': '合成企业', 'tool': 'delete_company'}))
    assert result['error'] == 'qcc_tool_not_allowed'


def test_qcc_broker_reuses_success_and_spends_one_call(monkeypatch, client):
    from app import research_tools
    from app.research_tools import ToolBroker
    calls = []
    async def fake_lookup(job_id, request):
        calls.append((job_id, request.name))
        return {'error': '', 'company': {'name': request.name}, 'sources': [], 'authorized': True}
    monkeypatch.setattr(research_tools, 'qcc_company_lookup', fake_lookup)
    jid = _job()
    options = {'enabled_channels': ['official'], 'max_qcc_calls': 1}
    first = asyncio.run(ToolBroker(jid, options, {}).execute('qcc_company_lookup', {'name': '合成企业'}))
    second = asyncio.run(ToolBroker(jid, options, {}).execute('qcc_company_lookup', {'name': '合成企业'}))
    assert first['authorized'] is True and second['reused'] is True and len(calls) == 1


def test_qcc_followup_requires_resolved_company_identifier(client):
    from app.research_tools import ToolBroker
    broker = ToolBroker(_job(), {'enabled_channels': ['official'], 'max_qcc_calls': 1}, {})
    result = asyncio.run(broker.execute('qcc_operation_lookup', {}))
    assert result['error'] == 'qcc_invalid_arguments'


def test_qcc_followup_rejects_blank_identifier(client):
    from app.research_tools import ToolBroker
    broker = ToolBroker(_job(), {'enabled_channels': ['official'], 'max_qcc_calls': 1}, {})
    result = asyncio.run(broker.execute('qcc_operation_lookup', {'company_id': '   '}))
    assert result['error'] == 'qcc_invalid_arguments'


def test_qcc_same_job_concurrent_duplicate_is_not_sent_twice(monkeypatch, client):
    from app import research_tools
    from app.research_tools import ToolBroker
    calls = []
    async def slow_lookup(job_id, request):
        calls.append(1)
        await asyncio.sleep(0.05)
        return {'error': '', 'company': {'name': request.name}, 'sources': [], 'authorized': True}
    monkeypatch.setattr(research_tools, 'qcc_company_lookup', slow_lookup)
    jid = _job(); options = {'enabled_channels': ['official'], 'max_qcc_calls': 2}
    async def run():
        return await asyncio.gather(ToolBroker(jid, options, {}).execute('qcc_company_lookup', {'name': '合成企业'}),
                                    ToolBroker(jid, options, {}).execute('qcc_company_lookup', {'name': '合成企业'}))
    results = asyncio.run(run())
    assert len(calls) == 1
    assert sum(item.get('error') == 'qcc_in_flight' for item in results) == 1


def test_qcc_operation_id_is_scoped_to_job(monkeypatch, client):
    from app import research_tools
    from app.research_tools import ToolBroker
    calls = []
    async def lookup(job_id, request):
        calls.append(job_id)
        return {'error': '', 'company': {'name': request.name}, 'sources': [], 'authorized': True}
    monkeypatch.setattr(research_tools, 'qcc_company_lookup', lookup)
    options = {'enabled_channels': ['official'], 'max_qcc_calls': 1}
    first_job, second_job = _job(), _job()
    asyncio.run(ToolBroker(first_job, options, {}).execute('qcc_company_lookup', {'name': '合成企业'}))
    asyncio.run(ToolBroker(second_job, options, {}).execute('qcc_company_lookup', {'name': '合成企业'}))
    assert calls == [first_job, second_job]


def test_company_identity_can_use_exact_qcc_candidate(monkeypatch, client):
    from app import company_identity
    from app.db import Evidence, Session, serialize
    jid = _job()
    with Session.begin() as db:
        row = Evidence(job_id=jid, channel='qcc_mcp', kind='授权数据', title='企查查授权企业信息', url='',
                       body='{"name":"合成企业"}',
                       source_meta={'origin':'qcc_mcp','authorized':True,'server':'company','tool':'get_basic_info','response_hash':'identity-hash'})
        db.add(row); db.flush(); source = serialize(row)
    class Broker:
        async def execute(self, name, arguments):
            assert name == 'qcc_company_lookup' and arguments == {'name':'合成企业'}
            return {'error':'', 'company':{'name':'合成企业'}, 'sources':[source], 'authorized':True}
    monkeypatch.setattr(company_identity, 'local_candidates', lambda requested: [])
    monkeypatch.setattr('app.company_research.broker_for', lambda state: Broker())
    monkeypatch.setattr(company_identity, 'qcc_mcp_configured', lambda: True, raising=False)
    state={'job_id':jid,'company_intent_targets':['合成企业'],'prompt':'查询合成企业',
           'context':'','options':{'enabled_channels':['official']},'source_ids':[], 'attempts':[]}
    resolved = asyncio.run(company_identity.company_resolve(state))
    assert resolved['company_target_name'] == '合成企业'
    assert resolved['company_identities'][0]['source_id'] == source['id']
