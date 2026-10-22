# QCC Task 2 Review

Reviewed brief and implementation range `9def818..d2875e4` (QCC files only). Existing focused test result reported by controller: `21 passed`.

## Spec Compliance

**Verdict: Partial / needs follow-up.** The adapter uses the fixed HTTPS QCC endpoints, enables TLS verification, sends the bearer key only in the HTTP client, performs `initialize` then `tools/list` before calls, projects tool schemas, hashes canonicalized responses with SHA-256, and maps provider failures to stable `QccError` codes. Binding resolution requires an exact advertised tool and rejects null/missing bindings.

The implementation does not itself enforce bindings or a read-only tool allowlist in `QccMcpClient.call`: any tool name advertised by the provider can be invoked when supplied by the caller. `resolve_binding` is separate and is not consulted by `call`, so a caller can bypass the configured action mapping (including a future write/document tool). The task/global safety rules require the configured exact binding and the restricted first-release surface to be enforced at the execution boundary.

## Task Quality

**Verdict: Needs improvement.** Resource ownership and secret-safe exception projection are generally clear, but tests cover only the happy fake transport, a few pure mappings, and string redaction. They do not exercise default streamable HTTP lifecycle, injected/default client close behavior, timeout/invalid-token/quota/pagination errors through the client, malformed tool schemas, `list_tools`, binding projection under `servers:`, or rejection of an unbound/unsafe advertised tool. This leaves the most security-sensitive behavior untested.

## Findings

### Important

1. **Execution bypasses configured bindings/allowlist.** `QccMcpClient.call()` checks only membership in the provider's discovered names and then calls the requested name. It never calls `resolve_binding`, accepts no binding map, and has no read-only/action allowlist. Any discovered tool can therefore be reached by an upstream caller that skips binding resolution. Enforce the resolved binding (or make the higher-level boundary mandatory and test it) and reject tools outside the first-release allowlist.

2. **Security/lifecycle coverage is too shallow.** The added tests inject a fake session and HTTP factory, so they do not verify `streamable_http_client` setup, default `httpx2.AsyncClient` closure in `finally`, or classification of transport exceptions raised during initialize/list/call. Add focused tests for timeout, 401/403/429 and JSON-RPC errors through `QccMcpClient`, plus ownership/close assertions.

### Minor

3. `qcc_error` recognizes only exact lowercase `qcc_*` strings after lowercasing and otherwise collapses unknown tool messages unless they contain specific keywords. Add explicit tests for the actual MCP unknown-tool error shape and ensure it consistently maps to `qcc_tool_not_allowed`.

4. The Task 2 commit does not modify `config/qcc_mcp_bindings.example.yaml`; it was already present in the base range. This is harmless for content, but the requested artifact is not represented by the task commit and should be checked in the final integration audit.

