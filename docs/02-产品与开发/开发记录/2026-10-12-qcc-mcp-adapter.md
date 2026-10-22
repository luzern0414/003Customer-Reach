# 企查查 MCP 应用内适配器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Client Reach 中接入企查查官方 MCP，提供受限的企业基本信息、经营、风险和招投标只读查询，并将授权结果以可审计证据进入企业研究流程。

**Architecture:** `backend/app/qcc_mcp.py` 负责凭据、固定官方端点、Streamable HTTP、工具发现和稳定错误；`research_tools.py` 负责 Job/ToolCall 预算与业务动作白名单；QCC 响应以独立 `qcc_mcp`/`授权数据` 来源归档后，交给现有企业校验链。真实工具名先由 `tools/list` 发现，再写入非敏感绑定配置，避免猜测 QCC schema。

**Tech Stack:** Python 3.12；`mcp==2.2.0`；`httpx2.AsyncClient`；FastAPI/SQLAlchemy；Pydantic；pytest；PowerShell。

## Global Constraints

- QCC 只使用官方 `https://agent.qcc.com/mcp/{server}/stream` 端点；TLS 校验和主机白名单必须保持开启。
- 凭据优先 `QCC_MCP_API_KEY`，否则只读取 `config/apikey.txt` 中明确的 `qcc_mcp_key`/`qcc_api_key` 字段；不得猜测模型、LangSmith 或 Exa Key。
- 不把 Key 写入源码、配置提交、日志、异常、SSE、测试输出或 Codex 用户配置；状态只报告 `configured: true/false`。
- 首期仅允许 `qcc-company`、`qcc-operation`、`qcc-risk`、`qcc-tender`；不启用 document、本地文件解析、写入、营销和自动翻页。
- `qcc_public` 仍表示公开网页；授权来源必须使用 `qcc_mcp`，不把授权结果伪装成公开 URL 或公开联系方式。
- 所有 QCC 请求共用现有 Job、ToolCall、取消/暂停、最多两路供应商并发、错误冷却和模型预算语义。
- 真实验收只执行 `initialize`、`tools/list` 和一个低额度只读企业基本信息查询，输出写入 `.codex-tmp` 并经过敏感字段扫描。

---

## 文件结构

- Create: `backend/app/qcc_mcp.py` — 凭据、端点、transport、schema 发现、工具绑定、错误分类和安全结果投影。
- Create: `backend/tests/test_qcc_mcp.py` — 凭据、白名单、mock transport、schema 发现、错误分类和幂等键测试。
- Create: `backend/tests/test_qcc_tools.py` — ToolBroker QCC 动作、预算、Evidence 归档和 `qcc_public` 隔离测试。
- Modify: `backend/app/config.py` — 增加 QCC Key 的独立只读加载与配置状态函数。
- Modify: `backend/app/source_errors.py` — 将 QCC 429/积分/协议限流映射为安全错误类别。
- Modify: `backend/app/research_tools.py` — 增加 QCC Pydantic 参数、工具白名单、ToolCall 落账和调用入口。
- Modify: `backend/app/company_validation.py` — 接受 `授权数据` 证据，并校验结构化字段路径/连续 JSON 引文。
- Modify: `backend/app/company_identity.py` — 企业名称无法由本地/公开来源确认时，允许调用 QCC 基本信息作为身份候选。
- Modify: `backend/app/company_research.py` — 在已确认主体的企业研究缺口阶段调用 QCC 业务动作并把授权 Evidence 送入清洗/提取。
- Modify: `backend/app/source_catalog.py` — 登记 `qcc_mcp` 来源显示与授权状态；不将其加入公开 URL 搜索渠道。
- Modify: `backend/app/channel_status.py` — 返回 QCC 是否已配置及首期服务能力，不暴露 Key。
- Modify: `scripts/mcp_probe.py` — 增加 QCC server 的 `list` 和单次只读调用模式，保存目录仍限 `.codex-tmp`。
- Modify: `config/apikey.example.txt` — 增加非敏感的 `qcc_mcp_key=` 示例。
- Modify: `config/README.md` — 记录 QCC Key 的环境变量/文件字段和不回显规则。
- Modify: `config/sources.yaml` — 将 QCC MCP 端点、四个 server、预算/TTL 说明与旧 OpenAPI 配置分开。
- Modify: `tools/mcp/README.md`、`tools/mcp/AGENTS.md` — 登记 QCC MCP 的应用内适配方式和真实验证状态。
- Create: `config/qcc_mcp_bindings.example.yaml` — 非敏感工具绑定格式示例，不含真实工具名或 Key。
- Create (local only): `.codex-tmp/qcc-mcp-verification/*.json` — 真实探针报告，不提交。

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

### Task 3: 授权 Evidence 归档与企业校验支持

**Files:**
- Modify: `backend/app/qcc_mcp.py` — add `archive_qcc_result(job_id, call_result, title, body) -> dict`.
- Modify: `backend/app/company_validation.py` — allow `授权数据` and validate QCC field paths/quotes.
- Modify: `backend/app/company_identity.py` — accept QCC identity candidates after exact requested name lookup.
- Modify: `backend/app/company_research.py` — include QCC evidence in clean/extract source selection.
- Test: `backend/tests/test_qcc_tools.py`.

**Interfaces:**
- `archive_qcc_result(job_id: str, call_result: QccCallResult, title: str) -> dict` creates/reuses an `Evidence` row with `channel="qcc_mcp"`, `kind="授权数据"`, `url=""`, stable JSON body, `content_hash`, and `source_meta` containing the fixed origin, server, tool, authorization flag and response hash.
- `cited_source(db, source_id, quote, allowed, allow_history=False)` accepts `授权数据` only when the QCC body contains the compacted quote and the quote is accompanied by a valid structured path in the proposed fact provenance.
- Company research source-kind sets include `授权数据`; public URL readers remain unchanged.

- [ ] **Step 1: Write failing Evidence and validation tests.**

```python
def test_qcc_result_is_archived_as_authorized_evidence(client):
    job_id = isolated_job(client)
    result = archive_qcc_result(job_id, fake_call_result(), "合成企业基本信息")
    assert result["channel"] == "qcc_mcp" and result["kind"] == "授权数据"
    assert result["source_meta"]["authorized"] is True
    assert result["url"] == ""

def test_public_source_does_not_satisfy_qcc_authorized_citation(client):
    with Session.begin() as db:
        db.add(Evidence(id="public-qcc-isolation", job_id="job-qcc-isolation", channel="qcc_public",
                        kind="网页正文", title="公开页面", url="https://www.qcc.com/firm/example",
                        body="公开页面正文。"))
    with Session() as db, pytest.raises(ServiceError, match="字段没有本任务已读全文证据"):
        cited_source(db, "public-qcc-isolation", "公开页面正文。", {"public-qcc-isolation"})
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_tools.py -k "archive or citation" -q`

Expected: FAIL because `archive_qcc_result` and the `授权数据` validation path do not exist.

- [ ] **Step 3: Implement deterministic QCC Evidence.**

Serialize only the bounded response projection with sorted keys and UTF-8 JSON; compute SHA-256 over that exact body; reuse by `(job_id, channel, response_hash)`. Do not place the bearer token, request headers, or unbounded provider error text in `body` or `source_meta`.

- [ ] **Step 4: Extend validation and source selection.**

Add `授权数据` to the allowed source-kind set only for QCC structured paths. Require `source_meta.origin == "qcc_mcp"`, `authorized is True`, and `quote`/`metadata_quote` to be contiguous in the stored JSON body after whitespace normalization. Store provenance with `server`, `tool`, `response_hash`, and JSON path; keep `url` empty so UI cannot render it as a public link.

- [ ] **Step 5: Run company regression tests.**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_tools.py backend/tests/test_company_agent.py backend/tests/test_entry_sources.py -q`

Expected: all existing public-source tests pass and new QCC tests pass; no public `qcc_public` source is changed.

- [ ] **Step 6: Commit the Evidence task.**

```powershell
git add backend/app/qcc_mcp.py backend/app/company_validation.py backend/app/company_identity.py backend/app/company_research.py backend/tests/test_qcc_tools.py
git -c user.name="Codex" -c user.email="codex@local" commit -m "feat: archive qcc authorized evidence safely [ci skip]"
```

### Task 4: ToolBroker 业务动作与企业研究集成

**Files:**
- Modify: `backend/app/research_tools.py` — add QCC Pydantic schemas, action dispatch, ToolCall budget/idempotency, and result projection.
- Modify: `backend/app/company_identity.py` — use `qcc_company_lookup` for exact-name identity fallback.
- Modify: `backend/app/company_research.py` — run QCC actions after identity resolution and before gap exhaustion.
- Modify: `backend/app/source_catalog.py`、`backend/app/channel_status.py` — expose capability status without making QCC a public URL channel.
- Test: `backend/tests/test_qcc_tools.py`.

**Interfaces:**
- `QccCompanyLookup`: `name: str = Field(min_length=2, max_length=200)`, `credit_code: str | None = Field(default=None, max_length=30)`, with Pydantic `extra="forbid"`.
- `QccOperationLookup`, `QccRiskLookup`, `QccTenderLookup`: consume `company_id`/`credit_code` resolved by the previous action, each max 64 characters and no arbitrary query object.
- `ToolBroker.execute("qcc_company_lookup", arguments) -> {"error": "", "company": {}, "sources": [], "authorized": True}`; analogous operation/risk/tender actions return bounded records and source IDs.
- `qcc_company_lookup(job_id: str, request: QccCompanyLookup) -> dict` is the private async dispatch function monkeypatched by offline tests; the other actions use the same `(job_id, request) -> dict` shape.
- `qcc_operation_key(server: str, tool: str, arguments: dict) -> str` uses the same canonical operation hash as Task 2; ToolBroker persists it in `ToolCall.operation_id` with `channel="qcc_mcp"`.

- [ ] **Step 1: Write failing business-action tests.**

```python
def test_qcc_tool_rejects_model_supplied_tool_name(client, monkeypatch):
    job_id = isolated_job(client)
    broker = ToolBroker(job_id, {"enabled_channels": ["official"], "max_qcc_calls": 1}, {})
    result = asyncio.run(broker.execute("qcc_company_lookup", {"name": "合成企业", "tool": "evil_tool"}))
    assert result["error"] == "qcc_tool_not_allowed"

def test_qcc_company_lookup_is_idempotent_and_archives_once(client, monkeypatch):
    calls = []
    async def fake_lookup(*args, **kwargs):
        calls.append(1)
        return fake_call_result()
    monkeypatch.setattr("app.research_tools.qcc_company_lookup", fake_lookup)
    job_id = isolated_job(client)
    broker = ToolBroker(job_id, {"enabled_channels": ["official"], "max_qcc_calls": 1}, {})
    first = asyncio.run(broker.execute("qcc_company_lookup", {"name": "合成企业"}))
    second = asyncio.run(broker.execute("qcc_company_lookup", {"name": "合成企业"}))
    assert first["authorized"] is True and second["reused"] is True and len(calls) == 1
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_tools.py -k "broker or lookup" -q`

Expected: FAIL because ToolBroker has no QCC schemas or dispatch path.

- [ ] **Step 3: Add schemas, dispatch and atomic budget reservation.**

Extend the schema map without adding QCC to `SearchChannel`; before the network call reserve `max_qcc_calls` inside the existing `BEGIN IMMEDIATE` transaction, check cooldown and duplicate operation ID, then release the transaction before calling QCC. Reuse successful ToolCall rows; record `qcc_not_configured`, `qcc_tool_unmapped`, rate limits and timeouts as stable statuses.

- [ ] **Step 4: Integrate company identity and gap decisions.**

When QCC is configured and the request explicitly asks for enterprise information, call the basic action with the exact requested name after local identity candidates are exhausted. Use only returned exact name/credit-code evidence to create identity candidates; never resolve a similar name solely by fuzzy matching. After identity resolution, call operation/risk/tender only when requested fields or a recorded gap requires them; do not call all four by default.

- [ ] **Step 5: Add channel status and authorization labeling tests.**

`/api/channels` must report `qcc_mcp` as `ready` only when configured and `authorization_required` otherwise; settings cannot enable `qcc_mcp` as a public search channel. Answer/source projections must display “企查查授权 MCP” and `authorized=true`, while `qcc_public` remains “企查查公开核验”.

- [ ] **Step 6: Run the integration suite.**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_tools.py backend/tests/test_company_identity_relations.py backend/tests/test_company_agent.py backend/tests/test_channel_preferences.py -q`

Expected: new QCC tests pass; existing public channel and company-query tests remain green.

- [ ] **Step 7: Commit the business integration task.**

```powershell
git add backend/app/research_tools.py backend/app/company_identity.py backend/app/company_research.py backend/app/source_catalog.py backend/app/channel_status.py backend/tests/test_qcc_tools.py
git -c user.name="Codex" -c user.email="codex@local" commit -m "feat: expose bounded qcc company research tools [ci skip]"
```

### Task 5: 探针、文档与最小真实验收

**Files:**
- Modify: `scripts/mcp_probe.py` — add QCC server choices, `list` operation and one configured read-only action; preserve existing Exa/Fetch/Playwright behavior.
- Modify: `tools/mcp/README.md`、`tools/mcp/AGENTS.md`、`config/README.md`、`config/sources.yaml`。
- Test: `backend/tests/test_qcc_mcp.py` and a new `backend/tests/test_qcc_probe.py`.
- Local only: `.codex-tmp/qcc-mcp-verification/initialize.json`, `tools.json`, `basic.json`, `audit.json`.

**Interfaces:**
- CLI choices: `--server qcc-company|qcc-operation|qcc-risk|qcc-tender`, `--operation list|basic`.
- `--save` remains restricted to a path below `ROOT/.codex-tmp`; serialized reports redact `Authorization`, `api_key`, `token`, and any configured secret value before writing.
- Exit code `0` means protocol call succeeded; `2` means safe classified failure; output contains server, tool, status, hashes and error code only.

- [ ] **Step 1: Write failing probe redaction tests.**

```python
def test_probe_report_redacts_auth_headers_and_key(tmp_path):
    report = serialize_probe_report({"headers": {"Authorization": "Bearer synthetic-qcc-key"}, "text": "qcc_mcp_key=synthetic-qcc-key"})
    assert "synthetic-qcc-key" not in report
    assert "Authorization" not in report
```

- [ ] **Step 2: Implement QCC probe dispatch and documentation.**

Reuse `QccMcpClient`; `list` calls only initialize/tools-list. `basic` requires an explicit `--company-name` and uses the verified basic binding, with `--save` path validation identical to existing probe behavior. Document that tool names are discovered from the current account and that QCC pagination/points may differ by account.

- [ ] **Step 3: Run offline probe tests and existing probe tests.**

Run: `backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_qcc_probe.py backend/tests/test_mcp_protocol_limit.py -q`

Expected: PASS; existing `--server exa|fetch|playwright` parser tests remain unchanged.

- [ ] **Step 4: Discover the real tool schema with the provided Key.**

Run only the low-cost schema probe:

```powershell
backend\\.venv\\Scripts\\python.exe scripts\\mcp_probe.py --server qcc-company --operation list --save .codex-tmp\\qcc-mcp-verification\\company-tools.json
```

Inspect only tool names, descriptions, input schemas, server info, and safe status fields. Add the verified nonsecret action binding to a local ignored file or a committed binding file only if it contains tool names and schemas, never the Key. If initialize/tools-list fails, preserve the safe error report and stop before a data query.

- [ ] **Step 5: Execute one real read-only basic lookup and scan the report.**

```powershell
backend\\.venv\\Scripts\\python.exe scripts\\mcp_probe.py --server qcc-company --operation basic --company-name "小米科技有限责任公司" --save .codex-tmp\\qcc-mcp-verification\\basic.json
```

Run a sensitive-value scan over the three reports and source tree; the scan must find no bearer token, API key, or `apikey.txt` value. Record whether the call completed, returned a stable QCC error, or was blocked by account permissions/points. Do not retry automatically.

- [ ] **Step 6: Run the full verification gate.**

Run:

```powershell
backend\\.venv\\Scripts\\python.exe -m pytest backend/tests -q
backend\\.venv\\Scripts\\python.exe -m compileall -q backend/app scripts/mcp_probe.py
git diff --check
```

Expected: all tests pass, compileall succeeds, and `git diff --check` produces no output. Summarize real QCC status as configured/handshake/tools-list/basic-query separately; do not claim integration success from configuration alone.

- [ ] **Step 7: Commit documentation and probe changes.**

```powershell
git add scripts/mcp_probe.py backend/tests/test_qcc_probe.py tools/mcp/README.md tools/mcp/AGENTS.md config/README.md config/sources.yaml
git -c user.name="Codex" -c user.email="codex@local" commit -m "docs: verify qcc mcp integration boundaries [ci skip]"
```

## Plan Self-Review

- Spec coverage: credentials and official host validation are Task 1; Streamable HTTP, tool discovery and stable errors are Task 2; authorized evidence and citation semantics are Task 3; ToolBroker/company-query integration is Task 4; probe, documentation and real low-cost validation are Task 5.
- Safety coverage: no secret output, no public-channel aliasing, no arbitrary tool/URL injection, no automatic pagination, no web bypass, and no marketing behavior are global constraints and are tested in Tasks 1, 2, 3 and 5.
- Type consistency: `QccMcpClient`, `QccCallResult`, `qcc_mcp_key`, `qcc_server_url`, `archive_qcc_result`, `QccCompanyLookup`, and `ToolBroker.execute` signatures are defined before later tasks consume them.
- Placeholder scan: no TODO/TBD or unspecified “appropriate handling” remains; the example binding uses `null` and the runtime explicitly rejects an unbound action until a real `tools/list` name is recorded.
- Scope check: all tasks implement one adapter subsystem; public crawler, CRM marketing and unrelated refactors are excluded.
