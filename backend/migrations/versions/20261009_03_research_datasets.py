"""逐轮清洗数据集增量迁移；保留原始来源和所有既有企业资料。"""
from alembic import op

revision='20261009_03'
down_revision='20261008_02'
branch_labels=None
depends_on=None

DDL=[
    "CREATE TABLE research_datasets (id VARCHAR NOT NULL PRIMARY KEY, unique_key VARCHAR NOT NULL UNIQUE, job_id VARCHAR NOT NULL REFERENCES jobs(id), conversation_id VARCHAR NOT NULL REFERENCES conversations(id), company_id VARCHAR REFERENCES companies(id), phase VARCHAR NOT NULL, status VARCHAR, source_ids JSON, payload JSON, cleaning_version VARCHAR, model_version VARCHAR, created_at VARCHAR, updated_at VARCHAR)",
    'CREATE INDEX ix_research_datasets_job_id ON research_datasets(job_id)',
    'CREATE INDEX ix_research_datasets_conversation_id ON research_datasets(conversation_id)',
]


def upgrade():
    """无参数；按冻结DDL建立数据集及查询索引，不重写旧表数据。"""
    for statement in DDL:op.execute(statement)


def downgrade():
    """无参数；数据降级应恢复一致性备份，禁止自动删除逐轮资料。"""
    raise RuntimeError('请恢复迁移前业务库与checkpoint一致性备份')
