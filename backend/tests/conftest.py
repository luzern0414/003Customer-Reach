"""测试使用临时目录中的独立 SQLite，绝不连接 data/app 的业务库。"""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix='dealradar-test-')
os.environ['DEALRADAR_DATA_DIR'] = _tmp
os.environ['DEALRADAR_CRAWL_DIR'] = str(Path(_tmp) / 'crawl')
os.environ['DEALRADAR_DATABASE_URL'] = 'sqlite:///' + (Path(_tmp) / 'test.db').as_posix()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.auth import ensure_admin  # noqa: E402
from app.db import init_db  # noqa: E402

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(scope='session', autouse=True)
def database():
    init_db()
    ensure_admin()


@pytest.fixture
def ccgp_text() -> str:
    return (FIXTURES / 'ccgp_award.txt').read_text(encoding='utf-8')
