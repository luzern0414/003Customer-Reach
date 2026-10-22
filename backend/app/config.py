"""运行配置及用户密钥文件加载；禁止将密钥加入调试输出。"""
from pathlib import Path
import os
import re
import json
import certifi


def configure_tls() -> None:
    """无入参；未指定SSL_CERT_FILE/DIR时采用certifi CA，避免Windows原生链查询阻塞，保持证书及主机名校验。"""
    if not os.getenv('SSL_CERT_FILE') and not os.getenv('SSL_CERT_DIR'):
        os.environ['SSL_CERT_FILE']=certifi.where()


configure_tls()

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv('CLIENTREACH_DATA_DIR', str(ROOT / 'data/app')))
DATA.mkdir(parents=True, exist_ok=True)


def credentials() -> tuple[str, str]:
    """只读用户文件或环境变量；返回端点及密钥，缺失时抛 ValueError，不打印原文。"""
    url, key = os.getenv('CLIENTREACH_MODEL_URL', ''), os.getenv('CLIENTREACH_MODEL_KEY', '')
    location = ROOT / 'config/apikey.txt'
    text = location.read_text(encoding='utf-8-sig') if location.exists() else ''
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            url = url or parsed.get('base_url', parsed.get('url', ''))
            key = key or parsed.get('api_key', parsed.get('key', ''))
    except ValueError:
        pass
    urls = re.findall(r'https?://[^\s"\'<>]+', text)
    keys = re.findall(r'sk-[A-Za-z0-9_\-]+', text)
    if not url and urls:
        url = urls[0].rstrip('/')
    if not key and keys:
        key = keys[0]
    if not key:
        for line in text.splitlines():
            if 'http' in line.lower() or not line.strip():
                continue
            candidate = re.split(r'[:：=]', line, maxsplit=1)[-1].strip().strip('"\'')
            if candidate.startswith('lsv2_') or 'langsmith' in line.lower():
                continue
            if len(candidate) >= 16:
                key = candidate
    if not url or not key:
        raise ValueError('模型配置缺少服务地址或 API Key，请检查 config/apikey.txt')
    url = re.sub(r'/(chat/completions|responses|models)/?$', '', url)
    if not url.endswith('/v1'):
        url += '/v1'
    return url, key


def langsmith_key(location: Path | None=None) -> str:
    """location为可空凭据文件路径，默认用户apikey.txt；环境变量优先（显式空值关闭）。

    只读取独立LangSmith字段或lsv2_密钥，不使用模型Key；不存在/损坏返回空值，无日志或写操作。
    """
    if 'LANGSMITH_API_KEY' in os.environ:return os.environ['LANGSMITH_API_KEY'].strip()
    try:
        content=(location or ROOT/'config/apikey.txt').read_text(encoding='utf-8-sig')
    except OSError:return ''
    try:
        value=json.loads(content)
        if isinstance(value,dict):
            nested=value.get('langsmith')
            key=value.get('langsmith_api_key') or value.get('LANGSMITH_API_KEY') or (nested.get('api_key') if isinstance(nested,dict) else '')
            return key.strip() if isinstance(key,str) else ''
    except ValueError:pass
    found=re.findall(r'(?<![\w-])lsv2_[A-Za-z0-9_-]+',content)
    return found[0] if len(found)==1 else ''


def exa_mcp_url() -> str:
    """无参数；返回Exa MCP地址。配置了EXA_API_KEY环境变量或apikey.txt中的exa_api_key时附带密钥以提高额度，否则匿名访问。"""
    from urllib.parse import quote
    key = os.getenv('EXA_API_KEY', '').strip()
    if not key:
        try:
            value = json.loads((ROOT / 'config/apikey.txt').read_text(encoding='utf-8-sig'))
            key = str(value.get('exa_api_key', '')).strip() if isinstance(value, dict) else ''
        except (OSError, ValueError):
            key = ''
        if not key:
            try:
                found = re.search(r'exa[_ -]?api[_ -]?key\s*[:：=]\s*([A-Za-z0-9\-]{20,})', (ROOT / 'config/apikey.txt').read_text(encoding='utf-8-sig'), re.I)
                key = found.group(1) if found else ''
            except OSError:
                key = ''
    base = 'https://mcp.exa.ai/mcp?tools=web_search_exa,web_fetch_exa'
    return base + ('&exaApiKey=' + quote(key) if key else '')


def qcc_mcp_key(location: Path | None = None) -> str:
    """读取独立企查查 MCP Key；环境变量优先，永不回显或猜测其他服务密钥。"""
    env_value = os.getenv('QCC_MCP_API_KEY', '').strip()
    if env_value:
        return env_value
    path = location or ROOT / 'config/apikey.txt'
    try:
        content = path.read_text(encoding='utf-8-sig')
    except OSError:
        return ''
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        value = None
    if isinstance(value, dict):
        for key_name in ('qcc_mcp_key', 'qcc_api_key', '企查查', '企查查MCPKey'):
            candidate = value.get(key_name)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    lines = content.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r'^\s*(qcc_mcp_key|qcc_api_key|企查查(?:\s*MCP\s*Key)?)\s*[:：=]\s*(.*?)\s*$', line, re.I)
        if match:
            candidate = match.group(2).strip()
            if not candidate and index + 1 < len(lines):
                following = lines[index + 1].strip()
                scoped = re.fullmatch(r'mcp\s*key\s*[:：=]\s*(?:Bearer\s+)?([A-Za-z0-9_./+\-=]+)', following, re.I)
                # Only the immediately following single token belongs to this label.
                if scoped:
                    candidate = scoped.group(1)
                elif re.fullmatch(r'[A-Za-z0-9_./+\-=]+', following):
                    candidate = following
            if candidate:
                return re.sub(r'^Bearer\s+', '', candidate.strip('"\''), flags=re.I)
    return ''


def qcc_mcp_configured(location: Path | None = None) -> bool:
    """只返回企查查 MCP 是否已配置，不返回密钥本身或任何长度信息。"""
    return bool(qcc_mcp_key(location))
