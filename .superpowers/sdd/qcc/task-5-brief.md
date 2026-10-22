## Global Constraints

- QCC 只使用官方 `https://agent.qcc.com/mcp/{server}/stream` 端点；TLS 校验和主机白名单必须保持开启。
- 凭据优先 `QCC_MCP_API_KEY`，否则只读取 `config/apikey.txt` 中明确的 `qcc_mcp_key`/`qcc_api_key` 字段；不得猜测模型、LangSmith 或 Exa Key。
- 不把 Key 写入源码、配置提交、日志、异常、SSE、测试输出或 Codex 用户配置；状态只报告 `configured: true/false`。
- 首期仅允许 `qcc-company`、`qcc-operation`、`qcc-risk`、`qcc-tender`；不启用 document、本地文件解析、写入、营销和自动翻页。
- `qcc_public` 仍表示公开网页；授权来源必须使用 `qcc_mcp`，不把授权结果伪装成公开 URL 或公开联系方式。
- 所有 QCC 请求共用现有 Job、ToolCall、取消/暂停、最多两路供应商并发、错误冷却和模型预算语义。
- 真实验收只执行 `initialize`、`tools/list` 和一个低额度只读企业基本信息查询，输出写入 `.codex-tmp` 并经过敏感字段扫描。

---


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

