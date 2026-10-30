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
    replanned = []
    monkeypatch.setattr(runner, 'start', started.append)
    monkeypatch.setattr(runner, 'replan', replanned.append)
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
    assert started == [first.json()['job']['id']]
    duplicate = client.post(f'/api/conversations/{conversation["id"]}/messages',
                            json={'content': 'only English sources', 'request_id': 'r-second'})
    assert duplicate.status_code == 202
    assert duplicate.json()['duplicate'] is True
    assert replanned == [first.json()['job']['id']]


def test_replan_clears_completed_stages_and_restarts(monkeypatch):
    from app import runner
    from app.db import Conversation, Job, Message, Session

    with Session.begin() as db:
        conversation = Conversation(title='重规划测试')
        db.add(conversation)
        db.flush()
        message = Message(conversation_id=conversation.id, role='user', content='search AI safety')
        db.add(message)
        db.flush()
        job = Job(conversation_id=conversation.id, message_id=message.id, mode='search', status='running', plan={
            'plan': {'mode': 'search', 'title': 'AI safety', 'query': 'AI safety'},
            'done': ['understand', 'web_plan', 'web_discover'],
            'search_candidates': [{'url': 'https://example.com'}],
        })
        db.add(job)
        db.flush()
        job_id = job.id

    class FakeTask:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    task = FakeTask()
    started = []
    monkeypatch.setattr(runner, '_tasks', {job_id: task})
    monkeypatch.setattr(runner, '_replanning', set())
    monkeypatch.setattr(runner, 'start', started.append)
    runner.replan(job_id)

    assert task.cancelled is True
    assert started == [job_id]
    with Session() as db:
        refreshed = db.get(Job, job_id)
        assert refreshed.status == 'replanning'
        assert refreshed.stage == 'understand'
        assert refreshed.plan['done'] == []


def test_pause_cancels_without_marking_replan(monkeypatch):
    from app import runner

    class FakeTask:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    task = FakeTask()
    monkeypatch.setattr(runner, '_tasks', {'job-1': task})
    monkeypatch.setattr(runner, '_replanning', set())

    assert runner.pause('job-1') is True
    assert task.cancelled is True
    assert 'job-1' in runner._tasks
    assert 'job-1' not in runner._replanning


def test_duplicate_request_id_returns_same_message(monkeypatch):
    from app import runner

    started, replanned = [], []
    monkeypatch.setattr(runner, 'start', started.append)
    monkeypatch.setattr(runner, 'replan', replanned.append)
    client = signed_in()
    conversation = client.post('/api/conversations').json()
    body = {'content': 'find papers about retrieval', 'request_id': 'same-request'}
    first = client.post(f'/api/conversations/{conversation["id"]}/messages', json=body).json()
    second = client.post(f'/api/conversations/{conversation["id"]}/messages', json=body).json()
    assert second['message_id'] == first['message_id']
    assert second['job']['id'] == first['job']['id']
    assert second['duplicate'] is True
    assert started == [first['job']['id']]
    assert replanned == []


def test_search_report_has_rows_and_no_paragraph_reply():
    from app.db import Conversation, Job, Message, Session

    with Session.begin() as db:
        conversation = Conversation(title='AI research')
        db.add(conversation)
        db.flush()
        message = Message(conversation_id=conversation.id, role='user', content='search AI safety')
        db.add(message)
        db.flush()
        job = Job(conversation_id=conversation.id, message_id=message.id, mode='search', status='completed', plan={
            'search_queries': [{'query': 'AI safety', 'language': 'en'}],
            'search_candidates': [{'url': 'https://example.com/paper'}],
            'search_results': [{'status': 'verified', 'title': 'AI Safety', 'url': 'https://example.com/paper',
                                'language': 'en', 'published_on': '2026-10-29', 'points': ['Robustness'],
                                'summary': 'Safety research', 'quote': 'Robustness is evaluated', 'source_id': 's1'}],
            'stage_history': [{'stage': 'web_verify', 'status': 'completed'}],
        })
        db.add(job)
        db.flush()
        message.job_id = job.id
        conversation_id, job_id = conversation.id, job.id

    client = signed_in()
    report = client.get(f'/api/jobs/{job_id}/report').json()
    assert report['mode'] == 'search'
    assert report['columns'] == ['标题', '来源', '语言', '日期', '要点', '原文']
    assert report['rows'][0]['status'] == 'verified'
    detail = client.get(f'/api/conversations/{conversation_id}').json()
    assert not any(message['role'] == 'assistant' and message['content'].strip() for message in detail['messages'])
