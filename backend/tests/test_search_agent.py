from pathlib import Path


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
