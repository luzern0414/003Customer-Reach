"""确认已由历史初始化器建立的旧表，作为非破坏性版本基线。"""
from alembic import op, context
from sqlalchemy import inspect

revision = '20261008_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """无参数；验证旧表关键身份列，不通过则阻止标记基线。"""
    if context.is_offline_mode():
        return
    inspector = inspect(op.get_bind())
    for table, required in {'conversations': {'id', 'profile'}, 'jobs': {'id', 'status', 'metrics'},
                            'evidence': {'id', 'body'}, 'leads': {'id', 'facts'}}.items():
        actual = {column['name'] for column in inspector.get_columns(table)}
        if not required.issubset(actual):
            raise RuntimeError('旧数据库不满足基线结构：' + table)


def downgrade():
    """无参数；不删除旧数据，降级须使用迁移前备份。"""
    raise RuntimeError('不自动降级数据；请恢复一致性备份')
