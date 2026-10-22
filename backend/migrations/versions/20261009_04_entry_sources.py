"""增量建立文档/片段/条目强外键，保留既有Evidence与所有业务原值。"""
from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

revision = '20261009_04'
down_revision = '20261009_03'
branch_labels = None
depends_on = None

DDL = [
    "CREATE TABLE source_documents (id VARCHAR NOT NULL PRIMARY KEY, evidence_id VARCHAR NOT NULL UNIQUE REFERENCES evidence(id), document_kind VARCHAR, origin VARCHAR, namespace VARCHAR, external_id VARCHAR, content_hash VARCHAR, created_at VARCHAR)",
    "CREATE TABLE source_fragments (id VARCHAR NOT NULL PRIMARY KEY, unique_key VARCHAR NOT NULL UNIQUE, document_id VARCHAR NOT NULL REFERENCES source_documents(id), text TEXT NOT NULL, quote_kind VARCHAR NOT NULL, location_status VARCHAR NOT NULL, char_start INTEGER, char_end INTEGER, page_start INTEGER, page_end INTEGER, created_at VARCHAR)",
    "CREATE INDEX ix_source_fragments_document_id ON source_fragments(document_id)",
    "CREATE TABLE entry_source_bindings (id VARCHAR NOT NULL PRIMARY KEY, company_id VARCHAR NOT NULL REFERENCES companies(id), fragment_id VARCHAR NOT NULL REFERENCES source_fragments(id), fact_id VARCHAR REFERENCES company_facts(id), relation_id VARCHAR REFERENCES company_relations(id), project_id VARCHAR REFERENCES procurement_projects(id), notice_id VARCHAR REFERENCES procurement_notices(id), role VARCHAR NOT NULL, ordinal INTEGER NOT NULL, created_at VARCHAR, CONSTRAINT ck_source_single_entry CHECK ((CASE WHEN fact_id IS NULL THEN 0 ELSE 1 END + CASE WHEN relation_id IS NULL THEN 0 ELSE 1 END + CASE WHEN project_id IS NULL THEN 0 ELSE 1 END + CASE WHEN notice_id IS NULL THEN 0 ELSE 1 END) = 1), UNIQUE(fact_id,fragment_id,role), UNIQUE(relation_id,fragment_id,role), UNIQUE(project_id,fragment_id,role), UNIQUE(notice_id,fragment_id,role))",
    *[f'CREATE INDEX ix_entry_source_bindings_{column} ON entry_source_bindings({column})' for column in ('company_id', 'fragment_id', 'fact_id', 'relation_id', 'project_id', 'notice_id')],
]


def upgrade():
    """无参数；建表及幂等回填参与Alembic事务，失败整体回滚，不修改事实/Evidence。"""
    for statement in DDL:
        op.execute(statement)
    from app.source_service import bind_company_sources
    connection = op.get_bind()
    with Session(bind=connection) as db:
        for company_id in connection.execute(text('SELECT id FROM companies')).scalars():
            bind_company_sources(db, company_id)
        db.flush()


def downgrade():
    """无参数；降级须恢复一致备份，不自动删除来源或证据关联。"""
    raise RuntimeError('请恢复迁移前业务库与checkpoint一致性备份')
