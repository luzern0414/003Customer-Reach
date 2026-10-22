# Task 1 Review

Reviewed commit `18449d4` against `task-1-brief.md`. The focused evidence supplied for this review is `backend/.venv/Scripts/python.exe -m pytest tests/test_qcc_mcp.py -q`: 9 passed.

## Findings

### Important

- `backend/app/config.py:qcc_mcp_key` treats the mere presence of `QCC_MCP_API_KEY` as authoritative and returns `""` when it is blank/whitespace. This prevents fallback to an explicitly configured `qcc_mcp_key`/`qcc_api_key` in `config/apikey.txt`, even though the requirement says blank values must be rejected and the file is the fallback source. Treat a stripped empty environment value as absent, then continue with file parsing; add a regression test covering blank env plus a valid file key.

## Minor

- The endpoint allow-list is duplicated in `config/sources.yaml` and `backend/app/qcc_mcp.py`. Only `qcc_server_url` validates scheme and hostname; consumers reading the YAML can bypass that invariant. Prefer making the runtime constant the single source of truth (or add a consistency check/test that all configured YAML endpoints exactly match `QCC_SERVER_URLS`).
- The tests cover the happy path and unknown server, but do not assert that the returned endpoint has the exact expected `/mcp/{server}/stream` path or reject malformed configured constants. Add exact-value assertions so an accidental path change cannot pass merely because it starts with `https://agent.qcc.com/mcp/`.

## Verdicts

- **Spec compliance:** Conditional pass. The committed implementation satisfies the explicit key parsing and fixed endpoint behavior for normal configuration, but the blank environment-variable case violates the required fallback semantics and should be fixed before acceptance.
- **Task quality:** Needs revision for the Important issue above; otherwise the change is small, readable, and the supplied focused suite passes.
