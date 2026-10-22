# ADR-0001 关键架构决策

状态：提议（待评审） · 日期：2026-10-08

| # | 决策 | 备选方案 | 理由 |
|---|---|---|---|
| 1 | Agent 编排使用 **LangGraph 1.2**（Python） | OpenAI Agents SDK、CrewAI、Agno、Dify/Coze | 支持有状态图、并行扇出、`interrupt` HITL 和 Postgres checkpoint，生产采用最多；不绑定特定模型 |
| 2 | 工具层采用 **MCP** 加内部 Tool Gateway | 直接写 LangChain Tool | 企查查、天眼查都有官方 MCP；工具层可以跨框架复用；缓存、限流、记账集中处理 |
| 3 | 前端使用 **Next.js 16 + assistant-ui + AntV G6** | CopilotKit/AG-UI、LobeChat、Open WebUI | assistant-ui 原生支持 LangGraph 且采用 MIT 协议；G6 最适合做企业关系图；LobeChat、Open WebUI 的协议限制定制和商用 |
| 4 | **招采数据离线入库优先**，实时查询兜底 | 每次对话实时抓取 | 延迟可控，抓取频率可控，合规风险低；数据可以沉淀为采购历史和上下游关系 |
| 5 | 企业数据以**企查查 API/MCP 为主，企查查网页（已登录会员）补充** | 只用网页 | API 结构化、稳定；网页补充 API 未购买的字段 |
| 6 | 登录态站点用 **OpenCLI Browser Bridge + Edge 专用配置** | DrissionPage、Playwright 自建 | 已在本机实测可用；内置 1688、jianyu 等适配器；复用合法登录态，不需要逆向 |
| 7 | **多通道 + 完整性校验**获取完整内容：API/MCP → Exa → OpenCLI 已登录真实浏览器；需要人工操作时由用户在 Agent 浏览器中完成 | 单一通道纯 HTTP 抓取 | 真实浏览器能正常渲染动态页面，复用会员权益，实测可以读取纯 HTTP 返回 412 的站点 |
| 8 | MVP 图存储用 **PG 边表 + 递归 CTE**，二期引入 Neo4j | 一开始就上 Neo4j | 减少运维组件；数据量小时性能足够 |
| 9 | LLM 走 **OpenAI 兼容网关**，按任务路由并配置回退 | 绑定单一厂商 | 国产模型都兼容 OpenAI 接口；控制成本；避免单点故障 |
| 10 | 关键数字采用"**LLM 生成 + 确定性校验**" | 直接信任 LLM 输出 | 金额、日期、主体名不能出现幻觉 |
