"""企查查 MCP 凭据、端点与协议适配器的离线契约测试。"""

import pytest

from app.config import qcc_mcp_configured, qcc_mcp_key
from app.qcc_mcp import QccConfigurationError, qcc_server_url


def test_qcc_env_key_wins_without_exposing_value(monkeypatch, tmp_path):
    monkeypatch.setenv("QCC_MCP_API_KEY", "synthetic-qcc-key")
    assert qcc_mcp_key(tmp_path / "missing") == "synthetic-qcc-key"
    assert qcc_mcp_configured(tmp_path / "missing") is True


def test_blank_qcc_env_falls_back_to_explicit_file_key(tmp_path, monkeypatch):
    path = tmp_path / "apikey.txt"
    path.write_text("qcc_mcp_key=file-qcc-key\n", encoding="utf-8")
    monkeypatch.setenv("QCC_MCP_API_KEY", "   ")
    assert qcc_mcp_key(path) == "file-qcc-key"


def test_qcc_file_parser_only_accepts_explicit_field(tmp_path, monkeypatch):
    path = tmp_path / "apikey.txt"
    path.write_text(
        "https://model.invalid/v1\nsk-model-key\nqcc_mcp_key=synthetic-qcc-key\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("QCC_MCP_API_KEY", raising=False)
    assert qcc_mcp_key(path) == "synthetic-qcc-key"


def test_qcc_json_parser_accepts_explicit_alias(tmp_path, monkeypatch):
    path = tmp_path / "apikey.json"
    path.write_text('{"qcc_api_key": "synthetic-qcc-key"}', encoding="utf-8")
    monkeypatch.delenv("QCC_MCP_API_KEY", raising=False)
    assert qcc_mcp_key(path) == "synthetic-qcc-key"


def test_qcc_parser_does_not_guess_unlabelled_model_key(tmp_path, monkeypatch):
    path = tmp_path / "apikey.txt"
    path.write_text("https://model.invalid/v1\nsk-model-key\n", encoding="utf-8")
    monkeypatch.delenv("QCC_MCP_API_KEY", raising=False)
    assert qcc_mcp_key(path) == ""
    assert qcc_mcp_configured(path) is False


@pytest.mark.parametrize('label', ['企查查', '企查查MCPKey', 'qcc_mcp_key'])
def test_qcc_parser_accepts_explicit_chinese_service_label(tmp_path, monkeypatch, label):
    path = tmp_path / 'apikey.txt'
    path.write_text('key=model-only\n' + label + '：synthetic-qcc-key\n', encoding='utf-8')
    monkeypatch.delenv('QCC_MCP_API_KEY', raising=False)
    assert qcc_mcp_key(path) == 'synthetic-qcc-key'


def test_qcc_label_can_precede_value_on_next_line(tmp_path, monkeypatch):
    path = tmp_path / 'apikey.txt'
    path.write_text('key=model-only\n\n企查查：\nsynthetic-qcc-key\n', encoding='utf-8')
    monkeypatch.delenv('QCC_MCP_API_KEY', raising=False)
    assert qcc_mcp_key(path) == 'synthetic-qcc-key'


def test_qcc_section_accepts_labeled_bearer_without_double_prefix(tmp_path, monkeypatch):
    path = tmp_path / 'apikey.txt'
    path.write_text('key=model-only\n企查查：\nmcp key： Bearer synthetic-qcc-key\n', encoding='utf-8')
    monkeypatch.delenv('QCC_MCP_API_KEY', raising=False)
    assert qcc_mcp_key(path) == 'synthetic-qcc-key'


def test_unscoped_mcp_key_is_not_qcc(tmp_path, monkeypatch):
    path = tmp_path / 'apikey.txt'
    path.write_text('mcp key: Bearer other-service-key\n', encoding='utf-8')
    monkeypatch.delenv('QCC_MCP_API_KEY', raising=False)
    assert qcc_mcp_key(path) == ''


@pytest.mark.parametrize("server", ["company", "operation", "risk", "tender"])
def test_qcc_official_endpoint_is_allowed(server):
    assert qcc_server_url(server).startswith("https://agent.qcc.com/mcp/")


def test_qcc_endpoint_rejects_unknown_server():
    with pytest.raises(QccConfigurationError, match="qcc_server_not_allowed"):
        qcc_server_url("document")


class _FakeTool:
    def __init__(self, name, schema=None):
        self.name = name
        self.description = "synthetic"
        self.inputSchema = schema or {"type": "object"}

class _FakeResult:
    def __init__(self, payload, is_error=False):
        self.payload = payload
        self.is_error = is_error
    def model_dump(self):
        return {"payload": self.payload, "isError": self.is_error}

class _FakeSession:
    def __init__(self):
        self.events = []
        self.called = None
    async def initialize(self):
        self.events.append("initialize")
    async def list_tools(self):
        self.events.append("list_tools")
        return type("Listed", (), {"tools": [_FakeTool("get_basic_info")]})()
    async def call_tool(self, name, arguments):
        self.events.append("call_tool")
        self.called = (name, arguments)
        return _FakeResult({"name": "合成企业"})

class _FakeHttpClient:
    instances = []
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.instances.append(self)

def test_qcc_client_initializes_lists_and_calls_allowlisted_tool():
    import asyncio
    from app.qcc_mcp import QccMcpClient
    fake = _FakeSession()
    _FakeHttpClient.instances.clear()
    client = QccMcpClient("company", key_loader=lambda: "synthetic-qcc-key",
                          http_client_factory=_FakeHttpClient,
                          session_factory=lambda *_args, **_kwargs: fake,
                          bindings={"basic": {"tool": "get_basic_info"}})
    result = asyncio.run(client.call("get_basic_info", {"name": "合成企业"}))
    assert fake.events[:2] == ["initialize", "list_tools"]
    assert fake.called == ("get_basic_info", {"name": "合成企业"})
    assert result.authorized is True and len(result.response_hash) == 64
    assert _FakeHttpClient.instances[0].kwargs["headers"] == {"Authorization": "Bearer synthetic-qcc-key"}


def test_qcc_client_rejects_tool_without_verified_binding():
    import asyncio
    from app.qcc_mcp import QccMcpClient
    fake = _FakeSession()
    client = QccMcpClient("company", key_loader=lambda: "synthetic-qcc-key",
                          http_client_factory=_FakeHttpClient,
                          session_factory=lambda *_args, **_kwargs: fake,
                          bindings={"basic": {"tool": "get_basic_info"}})
    with pytest.raises(Exception, match="qcc_tool_not_allowed"):
        asyncio.run(client.call("delete_company", {}))

def test_qcc_binding_requires_exact_advertised_tool():
    from app.qcc_mcp import QccTool, resolve_binding
    with pytest.raises(Exception, match="qcc_tool_unmapped"):
        resolve_binding("basic", [QccTool("other", "", {})], {"basic": {"tool": "get_basic_info"}})

def test_qcc_error_classification_does_not_leak_raw_text_or_key():
    from app.source_errors import qcc_error
    error = qcc_error("invalid_token synthetic-qcc-key")
    assert str(error) == "qcc_invalid_token"
    assert "synthetic-qcc-key" not in repr(error)


def test_qcc_empty_timeout_and_broken_transport_are_not_invalid_data():
    import httpx2
    import anyio
    from app.source_errors import qcc_error
    assert qcc_error(httpx2.ConnectTimeout('')).code=='qcc_timeout'
    assert qcc_error(ExceptionGroup('transport',[httpx2.ReadTimeout('')])).code=='qcc_timeout'
    wrapped=RuntimeError('synthetic protocol stopped');wrapped.__cause__=anyio.BrokenResourceError()
    assert qcc_error(wrapped).code=='qcc_unavailable'


@pytest.mark.parametrize("status,code", [(401, "qcc_invalid_token"), (403, "qcc_invalid_token"), (429, "qcc_rate_limited")])
def test_qcc_http_statuses_map_to_stable_codes(status, code):
    from app.source_errors import qcc_error
    error = qcc_error(type("HttpError", (), {"status_code": status})())
    assert str(error) == code


def test_qcc_retry_after_is_bounded_and_raw_error_is_hidden():
    from app.source_errors import qcc_error
    error = qcc_error(429, {"retry-after": "120"})
    assert str(error) == "qcc_rate_limited"
    assert error.retry_after == 120
    assert "120" not in str(error)


@pytest.mark.parametrize("message,code", [
    ("quota exhausted", "qcc_quota_exhausted"),
    ("pagination not enabled", "qcc_pagination_unavailable"),
    ("request timed out", "qcc_timeout"),
    ("invalid json from provider", "qcc_invalid_response"),
])
def test_qcc_message_errors_are_classified_without_provider_text(message, code):
    from app.source_errors import qcc_error
    error = qcc_error(message)
    assert str(error) == code
    assert message not in repr(error)
