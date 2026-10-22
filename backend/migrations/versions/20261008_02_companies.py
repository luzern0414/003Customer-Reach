"""企业研究模块增量迁移；DDL在本次版本生成时冻结，不跟随后续ORM变化。"""
from alembic import op, context
from sqlalchemy import inspect

revision = '20261008_02'
down_revision = '20261008_01'
branch_labels = None
depends_on = None

DDL = ['CREATE TABLE companies (\n\tid VARCHAR NOT NULL, \n\tidentity_key VARCHAR NOT NULL, \n\tname VARCHAR NOT NULL, \n\tshort_name VARCHAR, \n\tentity_kind VARCHAR, \n\tview_scope VARCHAR, \n\tvisibility VARCHAR, \n\tcredit_code VARCHAR, \n\torigin VARCHAR, \n\tresearch_as_of VARCHAR, \n\tmetadata_json JSON, \n\tcreated_at VARCHAR, \n\tupdated_at VARCHAR, \n\tPRIMARY KEY (id), \n\tUNIQUE (identity_key)\n)', 'CREATE INDEX ix_companies_name ON companies (name)', 'CREATE INDEX ix_companies_visibility ON companies (visibility)', 'CREATE TABLE company_facts (\n\tid VARCHAR NOT NULL, \n\tunique_key VARCHAR NOT NULL, \n\tcompany_id VARCHAR NOT NULL, \n\tcategory VARCHAR, \n\tfield VARCHAR NOT NULL, \n\tlabel VARCHAR NOT NULL, \n\traw_value JSON, \n\tnumeric_value NUMERIC(24, 4), \n\tunit VARCHAR, \n\traw_unit VARCHAR, \n\treport_period VARCHAR, \n\tas_of VARCHAR, \n\tscope VARCHAR, \n\tstatus VARCHAR, \n\tsource_ids JSON, \n\tquote TEXT, \n\tnote TEXT, \n\tprovenance JSON, \n\tcreated_at VARCHAR, \n\tupdated_at VARCHAR, \n\tPRIMARY KEY (id), \n\tUNIQUE (unique_key), \n\tFOREIGN KEY(company_id) REFERENCES companies (id)\n)', 'CREATE INDEX ix_company_facts_company_id ON company_facts (company_id)', 'CREATE INDEX ix_company_facts_field ON company_facts (field)', 'CREATE TABLE procurement_projects (\n\tid VARCHAR NOT NULL, \n\tunique_key VARCHAR NOT NULL, \n\tbuyer_id VARCHAR NOT NULL, \n\ttitle VARCHAR NOT NULL, \n\tproject_number VARCHAR, \n\trecord_kind VARCHAR, \n\tstage VARCHAR, \n\tpublished_at VARCHAR, \n\tdeadline VARCHAR, \n\tpayload JSON, \n\tsource_ids JSON, \n\tquote TEXT, \n\tcreated_at VARCHAR, \n\tupdated_at VARCHAR, \n\tPRIMARY KEY (id), \n\tUNIQUE (unique_key), \n\tFOREIGN KEY(buyer_id) REFERENCES companies (id)\n)', 'CREATE INDEX ix_procurement_projects_buyer_id ON procurement_projects (buyer_id)', 'CREATE INDEX ix_procurement_projects_record_kind ON procurement_projects (record_kind)', 'CREATE TABLE procurement_notices (\n\tid VARCHAR NOT NULL, \n\tunique_key VARCHAR NOT NULL, \n\tproject_id VARCHAR NOT NULL, \n\ttitle VARCHAR NOT NULL, \n\tnotice_type VARCHAR, \n\tpublished_at VARCHAR, \n\tplatform_published_at VARCHAR, \n\tdeadline VARCHAR, \n\tsource_ids JSON, \n\tpayload JSON, \n\tcreated_at VARCHAR, \n\tPRIMARY KEY (id), \n\tUNIQUE (unique_key), \n\tFOREIGN KEY(project_id) REFERENCES procurement_projects (id)\n)', 'CREATE INDEX ix_procurement_notices_project_id ON procurement_notices (project_id)', 'CREATE TABLE company_relations (\n\tid VARCHAR NOT NULL, \n\tunique_key VARCHAR NOT NULL, \n\tcompany_id VARCHAR NOT NULL, \n\tcounterparty_id VARCHAR, \n\tcounterparty_name VARCHAR NOT NULL, \n\trelation_type VARCHAR NOT NULL, \n\trank INTEGER, \n\treport_period VARCHAR, \n\tamount NUMERIC(24, 4), \n\tcurrency VARCHAR, \n\tunit VARCHAR, \n\tshare NUMERIC(12, 4), \n\tscope VARCHAR, \n\tsource_ids JSON, \n\tquote TEXT, \n\tnote TEXT, \n\tpayload JSON, \n\tcreated_at VARCHAR, \n\tPRIMARY KEY (id), \n\tUNIQUE (unique_key), \n\tFOREIGN KEY(company_id) REFERENCES companies (id), \n\tFOREIGN KEY(counterparty_id) REFERENCES companies (id)\n)', 'CREATE INDEX ix_company_relations_company_id ON company_relations (company_id)', 'CREATE INDEX ix_company_relations_relation_type ON company_relations (relation_type)', 'CREATE TABLE research_companies (\n\tid VARCHAR NOT NULL, \n\tunique_key VARCHAR NOT NULL, \n\tcompany_id VARCHAR NOT NULL, \n\tconversation_id VARCHAR NOT NULL, \n\tjob_id VARCHAR, \n\tposition INTEGER, \n\torigin VARCHAR, \n\tcreated_at VARCHAR, \n\tPRIMARY KEY (id), \n\tUNIQUE (unique_key), \n\tFOREIGN KEY(company_id) REFERENCES companies (id), \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tFOREIGN KEY(job_id) REFERENCES jobs (id)\n)', 'CREATE INDEX ix_research_companies_company_id ON research_companies (company_id)', 'CREATE INDEX ix_research_companies_conversation_id ON research_companies (conversation_id)', 'CREATE INDEX ix_research_companies_job_id ON research_companies (job_id)']

def upgrade():
    """无参数；建立六类企业结构并补旧表关联字段，保留已有会话和来源。"""
    for statement in DDL:
        op.execute(statement)
    additions = {'jobs': {'query_mode': "VARCHAR DEFAULT 'auto'", 'company_ids': "JSON DEFAULT '[]'"},
                 'evidence': {'source_meta': "JSON DEFAULT '{}'"}, 'leads': {'company_id': 'VARCHAR'}}
    for table, columns in additions.items():
        existing = set() if context.is_offline_mode() else {c['name'] for c in inspect(op.get_bind()).get_columns(table)}
        for name, definition in columns.items():
            if name not in existing:
                op.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    op.execute('CREATE INDEX IF NOT EXISTS ix_leads_company_id ON leads(company_id)')


def downgrade():
    """无参数；涉及数据的降级不自动删表，须恢复迁移前一致性备份。"""
    raise RuntimeError('不自动降级数据；请恢复一致性备份')
