"""运行路径、模型凭据与工作空间默认设置。密钥只读取，不写日志、不回显。"""
import json
import os
import re
from pathlib import Path

import certifi

if not os.getenv('SSL_CERT_FILE') and not os.getenv('SSL_CERT_DIR'):
    # Windows 原生证书链查询会阻塞事件循环，统一使用 certifi，保留证书与主机名校验。
    os.environ['SSL_CERT_FILE'] = certifi.where()

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv('DEALRADAR_DATA_DIR', str(ROOT / 'data/app')))
CRAWL_OUT = Path(os.getenv('DEALRADAR_CRAWL_DIR', str(ROOT / 'data/crawl')))
UPLOADS = DATA / 'uploads'
LUZ_CRAWL = Path(os.getenv('LUZ_CRAWL_HOME', 'D:/Codes/Luz-Crawl'))
WEB_DIST = ROOT / 'web/dist'
for _path in (DATA, CRAWL_OUT, UPLOADS):
    _path.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv('DEALRADAR_DATABASE_URL', 'sqlite:///' + (DATA / 'dealradar.db').as_posix())
MODEL_NAME = os.getenv('DEALRADAR_MODEL', 'gpt-6-luna')

# 账号：管理员不限次数；注册用户默认可发起 DEFAULT_QUOTA 次研究。
ADMIN_USERNAME = os.getenv('DEALRADAR_ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('DEALRADAR_ADMIN_PASSWORD', 'admin')
DEFAULT_QUOTA = int(os.getenv('DEALRADAR_DEFAULT_QUOTA', '5'))
SESSION_DAYS = 7

# 设置页可修改的默认值；数据库只保存与默认值不同的键。
DEFAULT_SETTINGS = {
    'company_name': '',
    'company_profile': '',
    'target_regions': [],
    'exclusions': [],
    'default_days': 90,
    'max_queries': 8,
    'max_reads': 12,
    'max_enrich': 5,
    'target_leads': 10,
    'max_rounds': 3,
    'max_model_calls': 40,
    'max_minutes': 20,
    'cache_hours': 24,
    'crawl_profile': '',
    'sources': {},
}


def credentials() -> tuple[str, str]:
    """返回模型服务 (base_url, api_key)；环境变量优先，其次 config/apikey.txt。缺失时抛 ValueError。"""
    url, key = os.getenv('DEALRADAR_MODEL_URL', ''), os.getenv('DEALRADAR_MODEL_KEY', '')
    location = ROOT / 'config/apikey.txt'
    text = location.read_text(encoding='utf-8-sig') if location.exists() else ''
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            url = url or parsed.get('base_url', parsed.get('url', ''))
            key = key or parsed.get('api_key', parsed.get('key', ''))
    except ValueError:
        pass
    if not url:
        found = re.findall(r'https?://[^\s"\'<>]+', text)
        url = found[0].rstrip('/') if found else ''
    if not key:
        found = re.findall(r'sk-[A-Za-z0-9_\-]+', text)
        key = found[0] if found else ''
    if not url or not key:
        raise ValueError('模型配置缺少服务地址或 API Key，请检查 config/apikey.txt')
    url = re.sub(r'/(chat/completions|responses|models)/?$', '', url)
    return (url if url.endswith('/v1') else url + '/v1'), key
