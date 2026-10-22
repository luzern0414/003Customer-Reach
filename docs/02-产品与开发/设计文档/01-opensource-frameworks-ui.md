# 调研 01：开源项目、Agent 框架、前端与版本选型

> 调研日期：2026-10-08
>
> - Star 数和推送日期取自 GitHub API 或 ungh.cc，版本号取自 PyPI 和 npm registry，均为当日查询结果。
> - 标注"未核实"的内容只来自搜索结果摘要。

## 1. 可借鉴的开源获客/销售 Agent 项目

| 项目 | Stars / License / 最近推送 | 做什么 | 可借鉴点 |
|---|---|---|---|
| [guy-hartstein/company-research-agent](https://github.com/guy-hartstein/company-research-agent) | 2.3k / Apache-2.0 / 2026-09-21 | 输入公司名，生成带出处的公司简报。<br>LangGraph 多 Agent 结构：company、industry、financial、news 四路并行，后接 collector → curator → editor。<br>FastAPI + React，用 WebSocket 推送进度，支持导出 PDF。 | **最接近"客户画像"链路**。可以参考它的图结构和前端节点进度 UI。 |
| [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research) | 12.7k / MIT / **已归档**（2026-08） | Deep Research 的参考实现 | 可以参考 supervisor/researcher 子图、上下文压缩、MCP 注入。只作参考，不依赖。 |
| [eracle/OpenOutreach](https://github.com/eracle/OpenOutreach) | 3.2k / GPL-3.0 | 从 ICP 出发找目标客户，给出可解释的匹配理由，再生成外联内容 | 只借鉴思路。GPL 协议，不复制代码。 |
| [xiongQvQ/AI_Find_Customer](https://gittrend.io/repo/xiongQvQ/AI_Find_Customer) | 约 143（未核实）/ 2026-07 | 外贸 B2B 客户挖掘。<br>技术栈：FastAPI + LangGraph + React。<br>流程：产品 → 关键词 → 搜索 → 线索 → 联系方式。 | 技术栈和我们最接近的中文项目 |
| [iPythoning/b2b-sdr-agent-template](https://github.com/iPythoning/b2b-sdr-agent-template) | 190 / MIT | 10 阶段销售管线，支持多渠道跟进 | 销售阶段状态机 |
| [JamesUgbanu/agent-sdr](https://github.com/JamesUgbanu/agent-sdr) | MIT / 2026-10 | 人工审批队列和审计日志 | HITL 与审计设计 |
| [kaymen99/sales-outreach-automation-langgraph](https://github.com/kaymen99/sales-outreach-automation-langgraph) | 398 / 2025-01 | 线索打分，回写 CRM | 打分节点设计 |
| [zhanglunet/qcc](https://github.com/zhanglunet/qcc) | Apache-2.0 / 2026-06 | **封装企查查官方 Agent MCP**（agent.qcc.com）。<br>146 个工具，提供 Python/TS 客户端和 8 个尽调 skill。 | 企查查直接走官方 MCP |
| [tyc-tech/tyc-cli](https://github.com/tyc-tech/tyc-cli) | MIT / 2026-06 | 天眼查 MCP 的 CLI，162 个业务工具 | 天眼查也有官方 MCP 入口 |
| [handaas/enterprise-mcp-server](https://github.com/handaas/enterprise-mcp-server)、[shuididata/mcp-server](https://github.com/shuididata/mcp-server) | 个位数 | 第三方工商 MCP | 低成本备用数据源 |
| [ir-st/TenderCrawler](https://github.com/ir-st/TenderCrawler) | MIT / 2026-06 | 抓取 cebpubservice 和 ccgp，带 Web 控制台 | 招投标采集器的起点 |
| [dg-procurement-rader](https://github.com/dongtianwen/dg-procurement-rader)、[bidding-ai-analyzer](https://github.com/ichthyoplanktonzyh/bidding-ai-analyzer) | — | LLM 筛选公告 → 结构化抽取 → 去重 → 推送 | 公告订阅流程 |
| [tlyyxjz/BidAgent（标小智）](https://github.com/tlyyxjz/BidAgent) | Apache-2.0 / 2026-09 | 中标公告核验，每个数字都能对应到原文的字符偏移 | **LLM 负责生成，程序做确定性校验**，用来抑制幻觉 |
| [liuhuanyong/ChainKnowledgeGraph](https://github.com/liuhuanyong/ChainKnowledgeGraph) | 779 | 产业链知识图谱：4654 家 A 股公司、511 个行业、9.5 万个产品，包含上下游关系 | **可直接用作上下游本体和种子数据** |
| [neo4j-labs/llm-graph-builder](https://github.com/neo4j-labs/llm-graph-builder) | 5.3k | 用 LLM 从文本抽取知识图谱，写入 Neo4j | 从公告和年报中抽取供应商/客户三元组 |
| [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | 85k / 0.9.4 | 把网页转成适合 LLM 读取的 Markdown | 抓取基础设施 |

**结论**

- 没有现成的开源项目同时覆盖"工商数据 + 1688 + 招投标 + 画像 + 供应链图谱"，这正是我们产品的差异化所在。
- 我们的做法是拼装：
  - company-research-agent 的图结构
  - 企查查/天眼查的官方 MCP
  - TenderCrawler + crawl4ai 做采集
  - BidAgent 的校验思想
  - ChainKnowledgeGraph 的本体
- wgpsec/ENScan_GO 现在访问返回 404，不依赖。

## 2. 后端 Agent 框架对比

| 框架 | Stars / License / 版本 | 工具调用 | 多 Agent | 流式输出 | HITL | 持久化 | 国产模型 | 成熟度 |
|---|---|---|---|---|---|---|---|---|
| **LangGraph** | 42.9k / MIT / **1.2.14** | ✅ ToolNode + MCP 适配器 | ✅ 子图、supervisor、swarm | ✅ 支持 values/updates/messages/custom | ✅ 原生 `interrupt()` | ✅ checkpoint-postgres 3.1.2，可时间回溯 | ✅ ChatOpenAI 改 base_url 即可；另有 langchain-deepseek | 1.x 版本 API 稳定 |
| OpenAI Agents SDK | 29.9k / MIT / 0.23.1 | ✅ | ✅ handoff | ✅ | 较弱 | Sessions | 通过 LiteLLM 接入 | 0.x |
| Claude Agent SDK | 8.2k / MIT / 0.2.164 | ✅ MCP | 子 Agent | ✅ | 钩子 | 会话级 | 只支持 Claude | 0.x |
| CrewAI | 59.4k / MIT / 1.15.25 | ✅ | ✅ 角色化 | 有 | 有限 | Flows | LiteLLM | 版本间常有 breaking change |
| AutoGen / AG2 | 61.3k / 5.0k | ✅ | ✅ | 有 | 有 | 弱 | ✅ | AutoGen 已停滞，**不推荐** |
| Agno | 42.6k / Apache-2.0 / 3.1.1 | ✅ | ✅ Team | ✅ | 有 | DB 存储 | ✅ | 轻量，大版本迭代频繁 |
| PydanticAI | 20.5k / MIT / 2.54.0 | ✅ 类型安全 | graph | ✅ | deferred tools | 有限 | ✅ | 适合结构化抽取 |
| Mastra | 28.6k / Apache-2.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | TS 生态首选，但我们后端用 Python |
| Dify | 158k / 自有开源协议（限多租户 SaaS） | 可视化 | 有限 | ✅ | 有 | 平台内置 | ✅ | 是平台而不是库，深度定制受限 |
| FastGPT | 29.8k / 有商用限制 | 同上 | 弱 | ✅ | 有 | 平台内置 | ✅ | 偏知识库场景 |
| Coze Studio | 21.7k / Apache-2.0 | 可视化 | 有 | ✅ | 有 | 平台内置 | ✅ | 更新放缓 |
| n8n | 207k / fair-code | AI 节点 | 弱 | 有 | ✅ | 工作流级 | ✅ | 适合做定时流水线 |
| **MCP** | python-sdk 24.5k；`mcp` 2.3.0、`fastmcp` 4.0.11 | 工具协议标准 | — | Streamable HTTP | elicitation | — | 与模型无关 | 事实标准 |

**推荐方案：LangGraph 1.2 + FastAPI，所有工具做成 MCP Server。** 理由如下：

1. 我们的流程是"意图识别 → 并行查询多个数据源 → 画像汇总 → 构建图谱"，需要有状态、可分支、可并行、可恢复的图。
2. `interrupt()` 配合 Postgres checkpointer，可以覆盖三种需要暂停的场景：
   - 消耗付费额度前请用户确认
   - 同名企业请用户消歧
   - 长任务断线后恢复
3. 前端生态成熟：
   - assistant-ui 提供专门的 LangGraph runtime
   - 也可以通过 ag-ui-langgraph 接入
4. 国产模型都提供 OpenAI 兼容接口，接入时注意：
   - 不要依赖 `parallel_tool_calls`
   - 每个模型都要做工具调用的回归测试
5. 工具层用 MCP 的好处：
   - 可以复用企查查、天眼查的官方 MCP
   - 计费、限流、缓存可以集中处理
   - 以后更换框架时，工具层不用重写

PydanticAI 可以用在"公告 → 结构化 JSON"这类抽取子任务里。Dify 和 Coze 不作为主框架。

## 3. 前端

| 方案 | Stars / License / 版本 | 评价 |
|---|---|---|
| **assistant-ui** | 12.4k / MIT / `@assistant-ui/react` 0.15.25，`react-langgraph` 0.14.33 | shadcn 风格的原语组件，有 LangGraph runtime，支持 interrupt、subgraph 和取消；用 Tool UI 渲染卡片和表格。**首选** |
| CopilotKit + AG-UI | 37.8k / 16.4k，MIT；`@ag-ui/client` 1.0.2 | 标准事件协议，支持状态双向同步，但 Python 后端前面通常要加一层 Node runtime。作为增强方案 |
| Vercel AI SDK | 27.2k / Apache-2.0 / **`ai` 7.0.x** | 已经是 v7；如果后端是 Python，需要自己适配流协议 |
| agent-chat-ui | 3.2k / MIT | LangGraph 官方的聊天壳，用于 PoC 和调试 |
| LobeHub / Open WebUI | 协议有品牌或商用限制 | 不作为产品界面 |
| LibreChat | 45k / MIT | 只适合内部工具 |
| shadcn/ui + Tailwind 4.3 | 125k / MIT | 基础组件 |

**生成式 UI 策略：采用静态生成式 UI。**

- 工具返回带 `type` 的结构化 JSON。
- 前端按 `type` 注册渲染组件，包括：采购公告卡片、企业画像卡、1688 供应商表格、上下游关系图。
- 不让 LLM 自由生成 UI。

**图可视化**

| 库 | Stars / 版本 / License | 用途 |
|---|---|---|
| **AntV G6** | 12.3k / 5.1.1 / MIT | 关系图首选。支持 dagre 分层（上游 → 本企业 → 下游）、力导向、Combo；国内股权穿透图多用它 |
| ECharts | 67k / 6.1.0 | 统计图表：金额趋势、地域分布 |
| Cytoscape.js | 11.2k / 3.34.3 | 图算法能力强 |
| React Flow | 38.6k / 12.12.0 | 偏向流程图编辑 |

## 4. 推荐版本（2026-10-08 实测）

| 层 | 组件与版本 |
|---|---|
| 后端 | Python 3.13.x（3.15 在 10-09 才发布，暂不用）<br>FastAPI 0.142.x、Pydantic 2.13.x、SQLAlchemy 2.1.x<br>LangGraph `>=1.2,<2`（1.2.3 已被撤回）、langchain 1.4.x、langchain-openai 1.6.x、langgraph-checkpoint-postgres 3.1.x<br>mcp 2.3、fastmcp 4.0<br>crawl4ai 0.9.x + Playwright<br>Langfuse 4.17 |
| 前端 | Next.js 16.4.0（**必须 ≥16.2.6**，修复了 13 个安全公告）、React 19.3.0、Tailwind 4.3<br>assistant-ui 0.15.x、@langchain/langgraph-sdk 1.12.x<br>@antv/g6 5.1.x、echarts 6.1.x |
| 数据 | PostgreSQL 18.x（19 仍在 beta）+ pgvector 0.8.6<br>Redis 8.x<br>Neo4j 2026.08+，Python driver 6.4 |
| 任务 | Arq 0.28（async 原生）或 Celery 5.6.3<br>Temporal 1.34 等到出现多日可靠订阅的需求时再引入 |

**图数据库路线**

- MVP 阶段：用 Postgres 边表 + 递归 CTE。
- 后续：当多跳查询、找共同供应商成为刚需时，再引入 Neo4j。

## Sources

- https://github.com/guy-hartstein/company-research-agent
- https://github.com/zhanglunet/qcc
- https://github.com/tyc-tech/tyc-cli
- https://github.com/ir-st/TenderCrawler
- https://github.com/tlyyxjz/BidAgent
- https://github.com/liuhuanyong/ChainKnowledgeGraph
- https://docs.ag-ui.com/introduction
- https://www.assistant-ui.com/docs/runtimes/langgraph/overview
- https://www.firecrawl.dev/blog/best-open-source-agent-frameworks
- https://nextjs.org/docs/app/guides/upgrading/version-16
