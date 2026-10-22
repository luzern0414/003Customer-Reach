## Global Constraints

- QCC 只使用官方 `https://agent.qcc.com/mcp/{server}/stream` 端点；TLS 校验和主机白名单必须保持开启。
- 凭据优先 `QCC_MCP_API_KEY`，否则只读取 `config/apikey.txt` 中明确的 `qcc_mcp_key`/`qcc_api_key` 字段；不得猜测模型、LangSmith 或 Exa Key。
- 不把 Key 写入源码、配置提交、日志、异常、SSE、测试输出或 Codex 用户配置；状态只报告 `configured: true/false`。
- 首期仅允许 `qcc-company`、`qcc-operation`、`qcc-risk`、`qcc-tender`；不启用 document、本地文件解析、写入、营销和自动翻页。
- `qcc_public` 仍表示公开网页；授权来源必须使用 `qcc_mcp`，不把授权结果伪装成公开 URL 或公开联系方式。
- 所有 QCC 请求共用现有 Job、ToolCall、取消/暂停、最多两路供应商并发、错误冷却和模型预算语义。
- 真实验收只执行 `initialize`、`tools/list` 和一个低额度只读企业基本信息查询，输出写入 `.codex-tmp` 并经过敏感字段扫描。

---


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

