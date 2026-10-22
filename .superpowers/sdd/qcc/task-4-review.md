# Task 4 review

## Verdict

**CONDITIONAL FAIL.** The ToolBroker unit path is partly sound and the focused QCC tests pass, but Task 4 is not complete. The implementation does not yet integrate QCC into identity/company research orchestration, and its idempotency guard permits duplicate in-flight calls. These are release-blocking for the stated brief.

## Findings

### P0 — duplicate operation IDs can execute concurrently

`ToolBroker._execute` checks for an existing `ToolCall`, but only reuses rows with `status == "completed"`. A second request arriving while the first row is pending increments `attempts`, leaves the transaction, and invokes the same async action. Thus the atomic reservation does not provide idempotency under concurrency and can spend two provider calls for one operation. A pending/in-progress row needs an explicit stable handling path (or a lock/claim state) before releasing the transaction.

### P1 — required company research and identity hooks are absent

`company_identity.py` and `company_research.py` contain no QCC fallback after local identity exhaustion and no conditional operation/risk/tender calls after identity resolution. The task report itself lists these hooks as a known limitation. This leaves the primary Task 4 business integration unimplemented even though the broker endpoints exist.

### P1 — operation lookup can be called without a resolved identifier

The schemas make `company_id` and `credit_code` individually optional, so `{}` is rejected by current Pydantic validation only because both fields happen to be absent? There is no schema-level “at least one” validator; callers can provide either field as an empty string (accepted by `min_length`-less fields) or invoke follow-up actions without proving that the identifier came from the preceding authorized action. Add non-empty constraints and enforce provenance/resolution in the broker/orchestration layer.

### P1 — operation idempotency lookup is not job-scoped

The existing-row query uses only `ToolCall.operation_id`. Since the operation key intentionally excludes `job_id`, a completed call from another job can be returned as `reused` without archiving a result for the current job. Reuse must be scoped to the current job (or the result/source must be copied into the current job explicitly).

### P2 — only model `tool` injection is explicitly rejected

The broker rejects an argument named `tool`, while Pydantic `extra="forbid"` rejects any other extra fields. This is acceptable for the current schemas, but the rejection result for extras other than `tool` is the generic `qcc_invalid_arguments`; keep this stable contract documented if clients depend on `qcc_tool_not_allowed` specifically for model-supplied tool names.

## Passing checks

- QCC request models use bounded lengths and `extra="forbid"`.
- `resolve_binding` requires a non-empty exact configured name present in `tools/list`; it does not substring-guess or call with an empty binding.
- QCC calls use the fixed official HTTPS server map, TLS verification, and `channel="qcc_mcp"` ToolCall records.
- `qcc_mcp` is exposed as a capability status and is not added to `SearchChannel`; `qcc_public` remains the public web channel.
- Existing focused QCC tests cover authorization labeling, public/authorized source separation, payload bounding, model tool injection, successful reuse, and missing follow-up arguments.

## Validation

Controller reported `test_qcc_tools.py` (8 tests) and the broader focused suite (49 tests) passing after the controller fixes. Those tests do not cover concurrent duplicate requests, cross-job operation reuse, or company identity/research orchestration.
