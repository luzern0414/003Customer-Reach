"""运行Alembic增量升级；复用当前连接，版本和数据位于同一数据库。"""
from alembic.config import Config
from alembic import command
from .config import ROOT


def upgrade_database(engine) -> None:
    """engine为本地SQLAlchemy引擎，不可为空；升级到head，失败抛原异常且不删表。"""
    config = Config()
    config.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
