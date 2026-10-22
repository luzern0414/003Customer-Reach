"""新增招投标记录与对手方汇总表：平台公告逐条保存角色、对手方与原文出处，不改动既有企业事实。"""
from alembic import op

revision = '20261010_05'
down_revision = '20261009_04'
branch_labels = None
depends_on = None

DDL = [
    "CREATE TABLE tender_records (id VARCHAR NOT NULL PRIMARY KEY, unique_key VARCHAR NOT NULL UNIQUE, company_id VARCHAR NOT NULL REFERENCES companies(id), job_id VARCHAR REFERENCES jobs(id), role VARCHAR NOT NULL, title VARCHAR NOT NULL, notice_type VARCHAR, project_number VARCHAR, published_at VARCHAR, buyer_name VARCHAR, winner_names JSON, candidate_names JSON, agency_name VARCHAR, amount VARCHAR, budget VARCHAR, region VARCHAR, items JSON, platform VARCHAR, url VARCHAR, evidence_id VARCHAR REFERENCES evidence(id), quote TEXT, confidence VARCHAR, payload JSON, created_at VARCHAR, updated_at VARCHAR)",
    *[f'CREATE INDEX ix_tender_records_{column} ON tender_records({column})' for column in ('company_id', 'job_id', 'role', 'published_at')],
    "CREATE TABLE tender_relations (id VARCHAR NOT NULL PRIMARY KEY, unique_key VARCHAR NOT NULL UNIQUE, company_id VARCHAR NOT NULL REFERENCES companies(id), counterparty_name VARCHAR NOT NULL, relation_type VARCHAR NOT NULL, deal_count INTEGER, amount_total VARCHAR, latest_at VARCHAR, record_ids JSON, platform VARCHAR, url VARCHAR, evidence_id VARCHAR REFERENCES evidence(id), quote TEXT, basis VARCHAR, payload JSON, created_at VARCHAR, updated_at VARCHAR)",
    *[f'CREATE INDEX ix_tender_relations_{column} ON tender_relations({column})' for column in ('company_id', 'relation_type')],
]


def upgrade():
    """无参数；仅建新表与索引，失败整体回滚。"""
    for statement in DDL:
        op.execute(statement)


def downgrade():
    """无参数；招投标记录可由重新研究再生，降级仅删除本表。"""
    op.execute('DROP TABLE tender_relations')
    op.execute('DROP TABLE tender_records')
