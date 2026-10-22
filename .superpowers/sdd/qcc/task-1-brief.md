## Global Constraints

- QCC 只使用官方 `https://agent.qcc.com/mcp/{server}/stream` 端点；TLS 校验和主机白名单必须保持开启。
- 凭据优先 `QCC_MCP_API_KEY`，否则只读取 `config/apikey.txt` 中明确的 `qcc_mcp_key`/`qcc_api_key` 字段；不得猜测模型、LangSmith 或 Exa Key。
- 不把 Key 写入源码、配置提交、日志、异常、SSE、测试输出或 Codex 用户配置；状态只报告 `configured: true/false`。
- 首期仅允许 `qcc-company`、`qcc-operation`、`qcc-risk`、`qcc-tender`；不启用 document、本地文件解析、写入、营销和自动翻页。
- `qcc_public` 仍表示公开网页；授权来源必须使用 `qcc_mcp`，不把授权结果伪装成公开 URL 或公开联系方式。
- 所有 QCC 请求共用现有 Job、ToolCall、取消/暂停、最多两路供应商并发、错误冷却和模型预算语义。
- 真实验收只执行 `initialize`、`tools/list` 和一个低额度只读企业基本信息查询，输出写入 `.codex-tmp` 并经过敏感字段扫描。

---


### Task 1: 独立凭据与官方端点白名单

**Files:**
- Modify: `backend/app/config.py` — 新增 `qcc_mcp_key(location: Path | None = None) -> str`、`qcc_mcp_configured(location: Path | None = None) -> bool`。
- Create: `backend/tests/test_qcc_mcp.py` — 先添加凭据和 endpoint 测试。
- Modify: `config/apikey.example.txt`、`config/README.md`、`config/sources.yaml`。

**Interfaces:**
- Produces `qcc_mcp_key()`，返回 QCC Key 或空字符串；不抛出包含密钥的错误。
- Produces `QCC_SERVER_URLS: dict[str, str]` in `qcc_mcp.py`，键为 `company|operation|risk|tender`，值必须是固定 `agent.qcc.com` HTTPS URL。
- Produces `qcc_server_url(server: str) -> str`，未知 server 抛 `QccConfigurationError("qcc_server_not_allowed")`。

- [ ] **Step 1: Write failing credential tests.**

```python
def test_qcc_env_key_wins_without_exposing_value(monkeypatch, tmp_path):
    monkeypatch.setenv("QCC_MCP_API_KEY", "synthetic-qcc-key")
    assert qcc_mcp_key(tmp_path / "missing") == "synthetic-qcc-key"
    assert qcc_mcp_configured(tmp_path / "missing") is True

def test_qcc_file_parser_only_accepts_explicit_field(tmp_path, monkeypatch):
    path = tmp_path / "apikey.txt"
    path.write_text("https://model.invalid/v1\nsk-model-key\nqcc_mcp_key=synthetic-qcc-key\n", encoding="utf-8")
    monkeypatch.delenv("QCC_MCP_API_KEY", raising=False)
    assert qcc_mcp_key(path) == "synthetic-qcc-key"

def test_qcc_parser_does_not_guess_unlabelled_model_key(tmp_path, monkeypatch):
    path = tmp_path / "apikey.txt"
    path.write_text("https://model.invalid/v1\nsk-model-key\n", encoding="utf-8")
    monkeypatch.delenv("QCC_MCP_API_KEY", raising=False)
    assert qcc_mcp_key(path) == ""
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_mcp.py -k "credential or parser" -q`

Expected: FAIL because the QCC loader does not exist.

- [ ] **Step 3: Implement the loader and endpoint constants.**

Use `os.getenv("QCC_MCP_API_KEY")` first; parse JSON keys `qcc_mcp_key`/`qcc_api_key`, then `key=value` lines with those exact names; reject blank values and never include the value in exceptions. Add the four fixed URLs and reject any URL whose parsed scheme is not `https` or hostname is not exactly `agent.qcc.com`.

- [ ] **Step 4: Add endpoint tests and run the task suite.**

```python
@pytest.mark.parametrize("server", ["company", "operation", "risk", "tender"])
def test_qcc_official_endpoint_is_allowed(server):
    assert qcc_server_url(server).startswith("https://agent.qcc.com/mcp/")

def test_qcc_endpoint_rejects_unknown_server():
    with pytest.raises(QccConfigurationError, match="qcc_server_not_allowed"):
        qcc_server_url("document")
```

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_mcp.py -q`

Expected: PASS with no output containing `synthetic-qcc-key`.

- [ ] **Step 5: Commit the isolated task.**

```powershell
git add backend/app/config.py backend/tests/test_qcc_mcp.py config/apikey.example.txt config/README.md config/sources.yaml
git -c user.name="Codex" -c user.email="codex@local" commit -m "feat: add qcc credential and endpoint boundaries [ci skip]"
```

