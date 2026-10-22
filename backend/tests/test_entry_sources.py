"""条目证据、强外键与原站归属回归；使用隔离库和真实历史存档，不调用网络。"""
import uuid
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError


def test_history_distinct_relation_fragments_and_document_scope(client):
    """client为隔离API；同报告的每家关系有自己的原文，片段位置可读回核对。"""
    from app.db import Session, Evidence
    from app.source_models import SourceDocument, SourceFragment, EntrySourceBinding
    cid = client.post('/api/companies/import-history').json()['company_ids'][0]
    detail = client.get('/api/companies/' + cid).json()
    rows = [r for r in detail['relations'] if r['relation_type'] in {'supplier', 'customer'}]
    assert len(rows) == 10
    assert all(r['evidence_refs'] for r in rows)
    texts = [r['evidence_refs'][0]['text'] for r in rows]
    assert len(set(texts)) == 10
    assert all(r['counterparty_name'] in text for r, text in zip(rows, texts))
    assert all(len(text) < 800 for text in texts)
    source_id = rows[0]['source_ids'][0]
    with Session() as db:
        before = [db.scalar(select(func.count()).select_from(model)) for model in (SourceDocument, SourceFragment, EntrySourceBinding)]
        for row in rows:
            ref = row['evidence_refs'][0]
            fragment = db.get(SourceFragment, ref['id'])
            evidence = db.get(Evidence, ref['source_id'])
            assert fragment.location_status == 'located'
            assert evidence.body[fragment.char_start:fragment.char_end] == fragment.text
            assert ref['url'] == evidence.url
            assert ref['page_start'] is None and ref['page_url'] == ''
    assert client.post('/api/companies/import-history').status_code == 200
    with Session() as db:
        assert before == [db.scalar(select(func.count()).select_from(model)) for model in (SourceDocument, SourceFragment, EntrySourceBinding)]
    response = client.get(f'/api/companies/{cid}/documents/{source_id}')
    assert response.status_code == 200
    document = response.json()
    assert len([r for r in document['entries'] if r['kind'] == 'relation']) >= 10
    assert 'body' not in document['source'] and 'original_path' not in response.text
    assert client.get(f'/api/companies/{cid}/documents/unrelated').status_code == 404
    assert client.get('/api/source-fragments/missing').status_code == 404
    assert client.get('/api/source-fragments/' + rows[0]['evidence_refs'][0]['id']).json()['text'] == texts[0]


def test_explicit_multisource_spans_and_transaction_rollback(client):
    """client保证隔离迁移已完成；每份来源只取得自身片段，同事务回滚不留下孤立证据。"""
    from app.db import Session, Evidence
    from app.company_models import Company, CompanyFact
    from app.source_models import SourceDocument, SourceFragment, EntrySourceBinding
    from app.source_service import bind_company_sources, entry_references
    token = uuid.uuid4().hex
    with Session() as db:
        company = Company(identity_key=token, name='隔离来源事务企业')
        db.add(company); db.flush()
        a = Evidence(id=token + 'a', body='===== PDF PAGE 2 =====\n本企业采购结构件。', url='https://example.org/first.pdf', source_meta={})
        b = Evidence(id=token + 'b', body='本企业采购电子元器件。', url='https://example.org/second', source_meta={})
        db.add_all([a, b]); db.flush()
        fact = CompanyFact(unique_key=token, company_id=company.id, field='procurement_rule', label='采购品类',
            quote='本企业采购结构件。\n本企业采购电子元器件。', source_ids=[a.id, b.id],
            provenance={'source_citations': [{'source_id': a.id, 'quote': '本企业采购结构件。'}, {'source_id': b.id, 'quote': '本企业采购电子元器件。'}]})
        db.add(fact); db.flush()
        count = bind_company_sources(db, company.id)
        assert count == {'documents': 2, 'fragments': 2, 'bindings': 2}
        assert bind_company_sources(db, company.id) == {'documents': 0, 'fragments': 0, 'bindings': 0}
        refs = entry_references(db, {'fact': [fact.id]})[fact.id]
        assert {r['text'] for r in refs} == {'本企业采购结构件。', '本企业采购电子元器件。'}
        assert next(r for r in refs if r['source_id'] == a.id)['page_url'] == a.url + '#page=2'
        assert all('\n' not in r['text'] for r in refs)
        db.rollback()
    with Session() as db:
        assert not db.get(Evidence, a.id)
        assert not db.scalar(select(SourceDocument).where(SourceDocument.evidence_id == a.id))


def test_ambiguous_historical_excerpt_does_not_invent_locator(client):
    """client保证隔离库；重复原句和整理摘录不盲取首处，不用人工页码制造PDF跳转。"""
    from app.db import Session, Evidence
    from app.company_models import Company, CompanyFact
    from app.source_models import SourceFragment, EntrySourceBinding
    from app.source_service import bind_company_sources, entry_references
    token = uuid.uuid4().hex
    with Session() as db:
        company = Company(identity_key=token, name='隔离未知定位企业')
        db.add(company); db.flush()
        source = Evidence(id=token, body='重复原句。重复原句。', url='https://example.org/report.pdf', source_meta={'origin': 'historical_snapshot'})
        db.add(source); db.flush()
        fact = CompanyFact(unique_key=token, company_id=company.id, field='detail', label='历史摘录', quote='PDF物理第23页：重复原句。', source_ids=[source.id], provenance={})
        db.add(fact); db.flush()
        bind_company_sources(db, company.id)
        ref = entry_references(db, {'fact': [fact.id]})[fact.id][0]
        assert ref['quote_kind'] == 'historical_excerpt' and ref['page_url'] == '' and ref['page_start'] is None
        fragment = db.get(SourceFragment, ref['id'])
        assert fragment.char_start is None and fragment.char_end is None
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(EntrySourceBinding(company_id=company.id, fragment_id=fragment.id, fact_id=fact.id, relation_id='unrelated', role='value', ordinal=0))
            db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(EntrySourceBinding(company_id=company.id, fragment_id=fragment.id, role='value', ordinal=0))
            db.flush()
        db.rollback()


def test_upgrade_from_v3_preserves_business_rows_and_backfills_once(client, tmp_path):
    """client初始化模型，tmp_path为pytest隔离目录；旧版本升级不改原文/事实，重复升级不增片段。"""
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.db import Base, Evidence
    from app.config import ROOT
    from app.company_models import Company, CompanyFact
    from app.source_models import SourceFragment
    engine = create_engine('sqlite:///' + str(tmp_path / 'migration.db'))
    versioned = {'companies', 'company_facts', 'procurement_projects', 'procurement_notices', 'company_relations', 'research_companies', 'research_datasets', 'source_documents', 'source_fragments', 'entry_source_bindings', 'tender_records', 'tender_relations'}
    Base.metadata.create_all(engine, tables=[table for name, table in Base.metadata.tables.items() if name not in versioned])
    config = Config(); config.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '20261009_03')
    with Session(engine) as db:
        company = Company(identity_key='migration-isolated', name='迁移隔离企业有限公司')
        db.add(company); db.flush()
        source = Evidence(id='migration-source', body='迁移隔离企业有限公司主营仪器。', url='https://example.org/migration')
        db.add(source); db.flush()
        fact = CompanyFact(unique_key='migration-fact', company_id=company.id, field='business', label='主营', raw_value='仪器', quote=source.body, source_ids=[source.id])
        db.add(fact); db.commit(); fact_id = fact.id
    for _ in range(2):
        with engine.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
        with Session(engine) as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '20261010_05'
            assert db.get(Evidence, 'migration-source').body == '迁移隔离企业有限公司主营仪器。'
            assert db.get(CompanyFact, fact_id).raw_value == '仪器'
            assert db.scalar(select(func.count()).select_from(SourceFragment)) == 1
    engine.dispose()


def test_history_source_backfill_preserves_latest_research_metadata(client):
    """client为隔离API；重复导入仅补历史来源，不能覆盖后来研究日期/缺口或已存在引用。"""
    from app.db import Session
    from app.company_models import Company, CompanyFact
    cid = client.post('/api/companies/import-history').json()['company_ids'][0]
    with Session.begin() as db:
        company = db.get(Company, cid)
        original_metadata, original_date = company.metadata_json, company.research_as_of
        company.metadata_json = {**original_metadata, 'last_research_job_id': 'isolated-preserved-job', 'gaps': ['后续研究真实缺口']}
        company.research_as_of = '2026-10-09'
        fact = db.scalar(select(CompanyFact).where(CompanyFact.company_id == cid))
        original_provenance = fact.provenance
        fact.provenance = {**fact.provenance, 'manual_review': '保留人工审核元信息'}
        fact_id = fact.id
    try:
        assert client.post('/api/companies/import-history').status_code == 200
        with Session() as db:
            company = db.get(Company, cid)
            assert company.metadata_json['last_research_job_id'] == 'isolated-preserved-job'
            assert company.metadata_json['gaps'] == ['后续研究真实缺口']
            assert company.research_as_of == '2026-10-09'
            assert db.get(CompanyFact, fact_id).provenance['manual_review'] == '保留人工审核元信息'
    finally:
        with Session.begin() as db:
            company = db.get(Company, cid); company.metadata_json = original_metadata; company.research_as_of = original_date
            db.get(CompanyFact, fact_id).provenance = original_provenance


def test_explicit_new_source_does_not_inherit_missing_metadata(client):
    """client为隔离API；新来源未提供metadata即不绑定，即使旧表头碰巧出现在新文档。"""
    from app.db import Session, Evidence
    from app.company_models import Company, CompanyFact
    from app.source_service import bind_company_sources, entry_references
    token = uuid.uuid4().hex
    with Session() as db:
        company = Company(identity_key=token, name='来源角色隔离企业')
        db.add(company); db.flush()
        a = Evidence(id=token + 'a', body='旧值。旧统计表头。', source_meta={})
        b = Evidence(id=token + 'b', body='新值。旧统计表头。', source_meta={})
        c = Evidence(id=token + 'c', body='无关段落。', source_meta={})
        db.add_all([a, b, c]); db.flush()
        fact = CompanyFact(unique_key=token, company_id=company.id, field='detail', label='来源角色', quote='旧值。', source_ids=[a.id, b.id],
            provenance={'metadata_quote': '旧统计表头。', 'source_citations': [{'source_id': a.id, 'quote': '旧值。', 'role': 'value'},
                {'source_id': a.id, 'quote': '旧统计表头。', 'role': 'metadata'}, {'source_id': b.id, 'quote': '新值。', 'role': 'value'}]})
        other = CompanyFact(unique_key=token + 'other', company_id=company.id, field='detail', label='残余来源', quote='旧值。', source_ids=[a.id, c.id],
            provenance={'source_citations': [{'source_id': a.id, 'quote': '旧值。'}]})
        db.add_all([fact, other]); db.flush()
        bind_company_sources(db, company.id)
        refs = entry_references(db, {'fact': [fact.id, other.id]})
        assert [(r['role'], r['text']) for r in refs[fact.id] if r['source_id'] == b.id] == [('value', '新值。')]
        assert not [r for r in refs[other.id] if r['source_id'] == c.id]
        db.rollback()


def test_document_entry_keeps_disclosed_plan_budget(client):
    """client为隔离API；经文档入口预览同一计划，必须保留真实预算/单位，不显示为未知。"""
    cid = client.post('/api/companies/import-history').json()['company_ids'][0]
    detail = client.get('/api/companies/' + cid).json()
    plan = next(p for p in detail['projects'] if p['payload'].get('budget') == 17571600)
    document = client.get(f"/api/companies/{cid}/documents/{plan['source_ids'][0]}").json()
    entry = next(r for r in document['entries'] if r['id'] == plan['id'])
    assert entry['payload']['budget'] == plan['payload']['budget']
    assert entry['payload']['unit'] == plan['payload']['unit']


def test_broad_table_quote_narrows_to_each_actual_relation_row(client):
    """client为隔离API；模型宽引文包含多行时只展示当前条目的真实行，统计表头独立保留。"""
    from app.db import Session, Evidence
    from app.company_models import Company, CompanyRelation
    from app.source_service import bind_company_sources, entry_references
    token = uuid.uuid4().hex
    table = '甲供应商有限公司 10.50 5.00%\n乙供应商有限公司 20.25 2.50%'
    with Session() as db:
        company = Company(identity_key=token, name='宽表引文隔离企业')
        db.add(company); db.flush()
        source = Evidence(id=token, body='2025年度供应商采购表，单位人民币元。\n' + table, source_meta={})
        db.add(source); db.flush()
        rows = []
        for name, amount, share in [('甲供应商有限公司', 10.5, 5), ('乙供应商有限公司', 20.25, 2.5)]:
            row = CompanyRelation(unique_key=token + name, company_id=company.id, counterparty_name=name,
                relation_type='supplier', amount=amount, share=share, currency='CNY', unit='元', report_period='2025',
                source_ids=[source.id], quote=table, payload={'source_citations': [{'source_id': source.id, 'quote': table, 'role': 'value'},
                    {'source_id': source.id, 'quote': '2025年度供应商采购表，单位人民币元。', 'role': 'metadata'}]})
            db.add(row); rows.append(row)
        db.flush(); bind_company_sources(db, company.id)
        refs = entry_references(db, {'relation': [r.id for r in rows]})
        values = [next(ref['text'] for ref in refs[row.id] if ref['role'] == 'value') for row in rows]
        assert values == table.splitlines()
        assert all(any(ref['role'] == 'metadata' for ref in refs[row.id]) for row in rows)
        db.rollback()
