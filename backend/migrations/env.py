"""Alembic使用应用提供连接；不自行解析凭据或另连数据库。"""
from alembic import context

config = context.config
if context.is_offline_mode():
    context.configure(url='sqlite://', literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    connection = config.attributes['connection']
    context.configure(connection=connection, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()
