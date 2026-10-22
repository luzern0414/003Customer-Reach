# 企查查 MCP 应用内适配器设计

日期：2026-10-12

## 目标

把企查查官方 MCP 接入 Client Reach 的企业研究流程，首期支持采购线索企业核验：企业基本信息、经营信息、风险摘要和招投标关联。接入必须保留现有任务预算、暂停恢复、幂等账本和证据归档语义，不把授权数据伪装成公开网页资料。

## 已确认的官方接口

企查查官方接入指南提供基于 Streamable HTTP 的远端服务，所有服务共用 Bearer API Key：

- `https://agent.qcc.com/mcp/company/stream`
- `https://agent.qcc.com/mcp/operation/stream`
- `https://agent.qcc.com/mcp/risk/stream`
- `https://agent.qcc.com/mcp/tender/stream`

官方还提供 ipr、history、executive、regulation、case、document 等服务，以及需要 Node.js 20+ 的本地 `qcc-document-mcp`。本期不启用后者和其余服务，避免工具噪声、文件权限扩大和积分消耗失控。

## 方案与边界

采用应用内适配器。后端自己创建 MCP 客户端连接，业务代码只调用固定的 QCC 业务动作。QCC 服务器名称、端点和允许动作由代码常量/非敏感配置控制；模型不能提交任意服务器、端点、工具名或请求头。

`qcc_public` 继续表示企查查公开网页核验。授权 MCP 使用独立来源标识 `qcc_mcp`，其数据不能直接作为公开联系方式或网页证据；企业事实仍须经过现有 `company_validation.py` 的逐字段引文和主体校验。采购公告原文继续优先来自政府或企业公开源，QCC 招投标结果作为授权补充来源并保留其服务和工具出处。

本期不做：全量暴露 QCC 203 个工具；自动翻页；写入企查查；营销触达；通过公开网页绕过 MCP 认证、积分、限流或字段权限；自动猜测未标注的凭据。

## 组件设计

### 凭据加载

新增 QCC 专用读取函数，优先读取 `QCC_MCP_API_KEY` 环境变量；环境变量未设置时，只读 `config/apikey.txt` 中明确命名的 `qcc_mcp_key`、`qcc_api_key` 或等价 JSON 字段。兼容现有纯文本和 JSON 两种格式，但不把模型 Key、LangSmith Key、Exa Key 或未标注的普通行当作 QCC Key。

函数只返回内部字符串或空值/配置错误。日志、异常、工具结果、测试输出和文档只允许出现 `configured: true/false`、稳定错误码或哈希，不允许出现 Key、长度、前后缀或原始响应中的认证头。

### `backend/app/qcc_mcp.py`

该模块负责：

1. 根据受限的 server ID 解析固定官方端点；拒绝未知 ID、非 HTTPS、非 `agent.qcc.com` 的地址。
2. 用 `mcp==2.2.0` 的 `streamable_http_client` 建立连接。该 SDK 版本通过预配置的 `httpx2.AsyncClient(headers={"Authorization": "Bearer ..."})` 注入认证头，而不是把 headers 直接作为 transport 参数。
3. 初始化会话并执行 `tools/list`，缓存当前会话的工具 schema；只允许配置映射中的工具名。
4. 执行单次只读工具调用，统一超时、取消和关闭会话；不支持工具分页参数，除非以后通过显式配置和预算门禁启用。
5. 将 MCP 内容块规范化为 JSON/文本投影，保留原始结构化响应用于证据哈希，不把协议诊断和认证信息泄漏给调用方。
6. 把 HTTP 401/403、429、MCP `invalid_token`、积分不足、翻页未开通、未知工具、协议错误和超时映射为稳定的 `QccError` 类别；429 复用现有 `SourceRateLimit` 语义并尊重 Retry-After。

适配器不直接写业务数据库。调用方传入任务 ID、业务动作和规范化参数，适配器返回结构化结果、服务/工具元数据和安全错误。

### 业务工具层

在现有 ToolBroker 体系中新增受限的 QCC 工具动作，优先服务 `company_query` 路线：

- `qcc_company_lookup`：按企业名称或统一社会信用代码查基本信息。
- `qcc_operation_lookup`：按已解析的企业标识查经营状态、经营范围、变更或分支。
- `qcc_risk_lookup`：按企业标识查风险摘要；只在用户请求尽调/风险或企业研究缺口需要时执行。
- `qcc_tender_lookup`：按企业标识查与该企业相关的招投标记录；只输出记录和状态，不把候选/中标阶段合并成新企业。

每个动作都有 Pydantic 参数模型：企业名称/代码长度有界，server 和工具由程序注入，禁止原始 MCP 参数透传。业务动作共享现有 Job、ToolCall、model budget、暂停恢复和最多两路供应商并发门禁。

### 缓存、预算和证据

规范化键为 `server + action/tool + canonical arguments + adapter version` 的 SHA-256。相同任务和相同键复用成功结果；失败结果只按错误类别和冷却时间复用，不把带 Key 的连接细节写入账本。默认不分页，每个企业每种动作最多一次新请求，风险和招投标可使用更短 TTL。

每次成功调用都生成授权来源记录，至少包含：

- `origin=qcc_mcp`、server、tool、adapter version；
- 参数哈希、请求时间、响应哈希、返回状态；
- 原始结构化响应的受控归档路径（仅项目本地证据目录）；
- 字段级连续引文或结构化字段路径；
- `authorized=true` 和积分/预算状态（若官方响应提供）。

原始响应大小、字段数量和归档目录均有上限。响应中的 URL 若不存在，不人为补造公开 URL；回答引用使用 server/tool/时间/字段路径作为授权来源标识。

## 数据流

```text
用户企业研究请求
  -> company_plan / 缺口决策
  -> QCC 业务工具参数校验
  -> qcc_mcp.py 固定 server + Bearer Key
  -> initialize -> tools/list -> 允许的只读 tool call
  -> 规范化结果 + 响应哈希 + 授权 Evidence
  -> company_clean / company_extract
  -> company_validation.py 逐字段校验
  -> 企业详情、关系或采购摘要
```

QCC 失败时保留稳定错误和缺口，不自动把同一请求改成公开网页搜索；如果用户同时允许公开来源，后续步骤由现有计划显式决定并单独记录来源。

## 错误与安全策略

- 缺少 Key：`qcc_not_configured`，启动检查只返回布尔状态。
- 401/403 或 `invalid_token`：`qcc_invalid_token`，停止本轮 QCC 请求。
- 429 或积分限制：`qcc_rate_limited` / `qcc_quota_exhausted`，写入冷却，不立即重试。
- 翻页未开通：`qcc_pagination_unavailable`，返回首屏结果和缺口。
- 工具 schema 缺失或名称不在 allowlist：`qcc_tool_not_allowed`。
- MCP/网络超时：`qcc_timeout`，保留调用尝试，不宣称取得数据。
- 任何响应解析失败：`qcc_invalid_response`，归档安全摘要和响应哈希，不把原始异常正文放入日志。

所有网络连接保持 TLS 校验和官方域名白名单；不使用浏览器登录、不关闭 robots/TLS、不改写来源、不自动发送消息。

## 测试与验收

先用 TDD 写离线测试：

1. 凭据解析：环境变量优先、明确字段读取、旧模型格式不串用、输出不泄密。
2. 端点白名单：四个官方端点通过，未知/非 HTTPS/伪造域名拒绝。
3. MCP 连接：mock `httpx2.AsyncClient` 和 transport 验证 Authorization 头、initialize、tools/list、固定工具调用及会话关闭。
4. 错误分类：401/403、429、Retry-After、invalid_token、分页未开通、未知工具和超时都映射为稳定错误。
5. 业务动作：参数有界、工具名不能由模型注入、相同规范化参数幂等、授权来源与 `qcc_public` 分离。
6. 企业研究集成：QCC 结果可进入现有清洗/验证流程；重复阶段不重复产生企业；失败不会写入未经验证的事实。

完成离线测试后，再使用本机 Key 做一次最小真实验收：`initialize`、`tools/list`、一个低额度企业基本信息只读查询。真实验收结果仅写 `.codex-tmp` 下的受控报告，报告通过敏感字段扫描后才可交付。

## 后续扩展条件

只有当首期四个 Server 的工具 schema、积分消耗、字段引文和业务价值稳定后，才评估 executive、ipr、history、legal 或 document。扩展必须新增明确的业务动作、预算和证据规则，不能通过删除 allowlist 直接开放全量工具。
