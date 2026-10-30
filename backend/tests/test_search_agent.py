from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def signed_in() -> TestClient:
    client = TestClient(app)
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin'}).status_code == 200
    return client


def test_search_plan_and_new_status_fields():
    from app.research.schemas import Plan

    plan = Plan(mode='search', title='AI research', query='latest AI safety papers',
                language='en', needs_clarification=False, result_columns=['标题', '来源'])
    assert plan.mode == 'search'
    assert plan.language == 'en'
    assert plan.result_columns == ['标题', '来源']


def test_init_db_adds_request_id_columns(tmp_path, monkeypatch):
    from app import db

    engine = db.create_engine('sqlite:///' + (Path(tmp_path) / 'test.db').as_posix())
    monkeypatch.setattr(db, 'engine', engine)
    db.init_db()
    message_names = {column['name'] for column in db.inspect(db.engine).get_columns('messages')}
    job_names = {column['name'] for column in db.inspect(db.engine).get_columns('jobs')}
    assert 'request_id' in message_names
    assert 'request_id' in job_names


def test_sse_treats_awaiting_input_as_terminal():
    from app.events import TERMINAL

    assert 'awaiting_input' in TERMINAL


def test_active_message_becomes_supplement_and_does_not_consume_again(monkeypatch):
    from app import runner

    started = []
    monkeypatch.setattr(runner, 'start', started.append)
    client = signed_in()
    conversation = client.post('/api/conversations').json()
    first = client.post(f'/api/conversations/{conversation["id"]}/messages',
                        json={'content': 'search AI safety', 'request_id': 'r-first'})
    second = client.post(f'/api/conversations/{conversation["id"]}/messages',
                         json={'content': 'only English sources', 'request_id': 'r-second'})
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()['supplemented'] is True
    assert second.json()['job']['id'] == first.json()['job']['id']
    assert started == [first.json()['job']['id'], first.json()['job']['id']]


def test_duplicate_request_id_returns_same_message(monkeypatch):
    from app import runner

    monkeypatch.setattr(runner, 'start', lambda job_id: None)
    client = signed_in()
    conversation = client.post('/api/conversations').json()
    body = {'content': 'find papers about retrieval', 'request_id': 'same-request'}
    first = client.post(f'/api/conversations/{conversation["id"]}/messages', json=body).json()
    second = client.post(f'/api/conversations/{conversation["id"]}/messages', json=body).json()
    assert second['message_id'] == first['message_id']
    assert second['job']['id'] == first['job']['id']
