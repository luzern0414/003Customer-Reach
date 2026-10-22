## Global Constraints

- QCC 只使用官方 `https://agent.qcc.com/mcp/{server}/stream` 端点；TLS 校验和主机白名单必须保持开启。
- 凭据优先 `QCC_MCP_API_KEY`，否则只读取 `config/apikey.txt` 中明确的 `qcc_mcp_key`/`qcc_api_key` 字段；不得猜测模型、LangSmith 或 Exa Key。
- 不把 Key 写入源码、配置提交、日志、异常、SSE、测试输出或 Codex 用户配置；状态只报告 `configured: true/false`。
- 首期仅允许 `qcc-company`、`qcc-operation`、`qcc-risk`、`qcc-tender`；不启用 document、本地文件解析、写入、营销和自动翻页。
- `qcc_public` 仍表示公开网页；授权来源必须使用 `qcc_mcp`，不把授权结果伪装成公开 URL 或公开联系方式。
- 所有 QCC 请求共用现有 Job、ToolCall、取消/暂停、最多两路供应商并发、错误冷却和模型预算语义。
- 真实验收只执行 `initialize`、`tools/list` 和一个低额度只读企业基本信息查询，输出写入 `.codex-tmp` 并经过敏感字段扫描。

---


### Task 2: Streamable HTTP client、工具发现与错误分类

**Files:**
- Modify: `backend/app/qcc_mcp.py` — add `QccMcpClient`, schema projection, binding resolution and safe exceptions.
- Modify: `backend/app/source_errors.py` — add QCC-specific `qcc_error`/retry mapping without raw provider text.
- Test: `backend/tests/test_qcc_mcp.py`.
- Create: `config/qcc_mcp_bindings.example.yaml`.

**Interfaces:**
- `QccMcpClient(server: str, key_loader: Callable[[], str] = qcc_mcp_key, http_client_factory: Callable | None = None, session_factory: Callable | None = None)`.
- `await client.list_tools() -> list[QccTool]`, where `QccTool(name: str, description: str, input_schema: dict)` contains no headers or secrets.
- `await client.call(tool_name: str, arguments: dict) -> QccCallResult`, where result contains `server`, `tool`, `response`, `response_hash`, `retrieved_at`, and `authorized=True`.
- `canonical_arguments(arguments: dict) -> dict` and `operation_key(server: str, tool: str, arguments: dict) -> str` are deterministic and exclude credentials.

- [ ] **Step 1: Write failing mock transport tests.**

Use a fake async context manager that records the `httpx2.AsyncClient` headers and returns a fake `ClientSession` implementing `initialize`, `list_tools`, `call_tool`, and `close`. Assert the Authorization header is exactly `Bearer synthetic-qcc-key`, `initialize` and `tools/list` occur before the call, and the result has a SHA-256 response hash.

```python
async def test_qcc_client_initializes_lists_and_calls_allowlisted_tool(monkeypatch):
    fake = FakeQccSession(tools=[FakeTool("get_basic_info", {"type": "object"})], payload={"name": "合成企业"})
    client = QccMcpClient("company", key_loader=lambda: "synthetic-qcc-key", session_factory=lambda *_: fake)
    result = await client.call("get_basic_info", {"name": "合成企业"})
    assert fake.events[:2] == ["initialize", "list_tools"]
    assert fake.called == ("get_basic_info", {"name": "合成企业"})
    assert result.authorized is True and len(result.response_hash) == 64
```

- [ ] **Step 2: Run the mock test and verify it fails.**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_mcp.py::test_qcc_client_initializes_lists_and_calls_allowlisted_tool -q`

Expected: FAIL because the adapter and result types are absent.

- [ ] **Step 3: Implement the client with `httpx2.AsyncClient`.**

Create the client with fixed URL, `headers={"Authorization": "Bearer " + key}`, TLS defaults, bounded connect/read/write/pool timeout, and `streamable_http_client(url, http_client=http_client)`. Call `ClientSession(read, write, read_timeout_seconds=timedelta(seconds=45))`, then `initialize`, `list_tools`, and only after schema discovery call the requested tool. The default `httpx2` client must be closed in `finally`; injected fakes remain caller-owned.

- [ ] **Step 4: Add safe error classification tests and implementation.**

Cover HTTP 401/403, HTTP 429 with `Retry-After: 120`, JSON-RPC `invalid_token`, quota text, pagination-not-enabled text, unknown tool, and timeout. Each must produce a fixed code such as `qcc_invalid_token`, `qcc_rate_limited`, `qcc_quota_exhausted`, `qcc_pagination_unavailable`, `qcc_tool_not_allowed`, or `qcc_timeout`; assert the raw message and synthetic key are absent from `str(error)` and serialized result.

- [ ] **Step 5: Add binding projection and run tests.**

`resolve_binding(action, tools, bindings)` must require an exact configured tool name whose advertised schema is present; missing binding returns `qcc_tool_unmapped` rather than guessing by name. `config/qcc_mcp_bindings.example.yaml` documents the nonsecret shape; `null` is intentionally invalid at runtime and is replaced only after the real `tools/list` probe:

```yaml
version: 1
servers:
  company:
    actions:
      basic: {tool: null}
```

The placeholder is documentation syntax only; runtime rejects it. Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_mcp.py -q`.

- [ ] **Step 6: Commit the transport task.**

```powershell
git add backend/app/qcc_mcp.py backend/app/source_errors.py backend/tests/test_qcc_mcp.py config/qcc_mcp_bindings.example.yaml
git -c user.name="Codex" -c user.email="codex@local" commit -m "feat: add qcc streamable http adapter [ci skip]"
```

