## Global Constraints

- QCC 只使用官方 `https://agent.qcc.com/mcp/{server}/stream` 端点；TLS 校验和主机白名单必须保持开启。
- 凭据优先 `QCC_MCP_API_KEY`，否则只读取 `config/apikey.txt` 中明确的 `qcc_mcp_key`/`qcc_api_key` 字段；不得猜测模型、LangSmith 或 Exa Key。
- 不把 Key 写入源码、配置提交、日志、异常、SSE、测试输出或 Codex 用户配置；状态只报告 `configured: true/false`。
- 首期仅允许 `qcc-company`、`qcc-operation`、`qcc-risk`、`qcc-tender`；不启用 document、本地文件解析、写入、营销和自动翻页。
- `qcc_public` 仍表示公开网页；授权来源必须使用 `qcc_mcp`，不把授权结果伪装成公开 URL 或公开联系方式。
- 所有 QCC 请求共用现有 Job、ToolCall、取消/暂停、最多两路供应商并发、错误冷却和模型预算语义。
- 真实验收只执行 `initialize`、`tools/list` 和一个低额度只读企业基本信息查询，输出写入 `.codex-tmp` 并经过敏感字段扫描。

---


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

