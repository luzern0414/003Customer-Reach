# 07 后端 API 设计（FastAPI）

基础路径：`/api/v1`。鉴权方式为 JWT。MVP 阶段可以只用单用户，配合本地 token。

## 1. 对话与运行

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/threads` | 新建会话 → `{thread_id}` |
| GET | `/threads` / `/threads/{id}` | 会话列表与历史消息（从 checkpoint 读取） |
| DELETE | `/threads/{id}` | 删除会话 |
| POST | `/threads/{id}/runs/stream` | 发起运行，返回 **SSE** 流（见 §2） |
| POST | `/threads/{id}/runs/{run_id}/resume` | 恢复 interrupt，请求体为 `{type:"cost_confirm", decision:"approve"\|"free_only"\|"cancel"}`、`{type:"entity_pick", credit_code}` 等 |
| POST | `/threads/{id}/runs/{run_id}/cancel` | 取消运行 |

## 2. SSE 事件协议

| event | data | 说明 |
|---|---|---|
| `run.started` | `{run_id}` | |
| `plan` | `Plan` | supervisor 生成的计划 |
| `message.delta` | `{id, text}` | LLM token 流 |
| `tool.started` | `{call_id, tool, args_summary, source}` | |
| `tool.progress` | `{call_id, source, status, count}` | 多源并行时，单个源完成就推送 |
| `tool.finished` | `{call_id, status, latency_ms, cache_hit, cost, result_type}` | |
| `ui.block` | `{type, data, sources}` | 生成式 UI 载荷 |
| `interrupt` | `{type, payload}` | HITL，等待 resume |
| `error` | `{scope: source\|run, message}` | |
| `run.finished` | `{status, total_cost, usage}` | |

## 3. 业务资源

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/tenders?kw=&region=&from=&to=&type=&min=&max=&buyer=&page=` | 招采库检索，不经过 Agent |
| GET | `/tenders/{id}` | 详情（含来源、证据） |
| POST | `/tenders/{id}/detail:fetch` | 实时拉取详情（可能消耗额度，需要传 `confirm=true`） |
| GET | `/companies/search?q=` | 企业检索：先查本地库，未命中再走 `company_resolve` |
| GET | `/companies/{id}` | 画像 |
| POST | `/companies/{id}/refresh?sections=` | 刷新画像（付费） |
| GET | `/companies/{id}/graph?depth=1&types=` | 关系图，返回 nodes 和 edges |
| GET | `/companies/{id}/tenders?role=buyer\|winner` | 采购或中标历史 |
| GET | `/contacts/{id}/reveal` | 查看完整联系方式，写审计日志 |
| CRUD | `/leads` | 线索 |
| GET | `/leads/export.xlsx` | 导出 |
| GET | `/quota` | 各数据源额度、余额与当日消耗 |
| GET | `/sources/health` | 数据源状态 |
| POST | `/sources/{name}/login-check` | 调用 OpenCLI `whoami` 检查登录态 |
| GET | `/admin/tool-calls?run_id=` | 调用审计 |

## 4. 内部服务边界

```
api (FastAPI) ──▶ agents (LangGraph, 进程内) ──▶ tools.gateway ──▶ MCP clients / adapters
      │                                              │
      └────────▶ db (SQLAlchemy async) ◀─────────────┘
worker (Arq) ──▶ crawlers.adapters ──▶ parsers/extract ──▶ db
```

- `tools.gateway` 同时供 Agent 和 Worker 使用，二者共享缓存、限流和记账。
- MCP Server 既可以作为独立进程运行（stdio 或 streamable-http），也可以在开发时进程内直调，由 `config/settings.yaml` 的 `mcp.mode` 切换。

## 5. 错误码约定

| code | 含义 |
|---|---|
| `USER_ACTION_REQUIRED` | 需要用户在 Agent 浏览器中完成登录或页面确认 |
| `CONTENT_INCOMPLETE` | 所有通道读取后仍缺少字段（如会员额度用尽），返回已获取部分 |
| `LOGIN_REQUIRED` | 登录态失效 |
| `QUOTA_EXCEEDED` | 额度或预算超限 |
| `CONFIRM_REQUIRED` | 需要用户确认 |
| `ENTITY_AMBIGUOUS` | 企业名有歧义 |
| `UPSTREAM_ERROR` | 上游异常，可重试 |
