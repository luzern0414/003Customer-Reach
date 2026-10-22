# 02 总体架构与技术选型

> 选型依据见 `research/01~03`。关键决策另记于 `adr/0001-key-decisions.md`。

## 1. 架构总览

```
┌──────────────────────────── 前端 Web (Next.js 16 + React 19) ────────────────────────────┐
│  对话区(assistant-ui)  │  工具结果卡片(Tool UI)  │  关系图(AntV G6)  │  线索库/报表(ECharts) │
└───────────────▲───────────────────────────────────────────────────────────────────────────┘
                │ HTTP + SSE（LangGraph 流式事件：messages / updates / custom / interrupt）
┌───────────────┴──────────── 后端 API (FastAPI) ─────────────────────────────────────────────┐
│  /threads /runs(stream) /leads /companies /tenders /graph /quota /admin                     │
│  鉴权(JWT) · 限流 · 审计日志 · 额度记账                                                      │
├──────────────────────────── Agent 层 (LangGraph 1.2) ───────────────────────────────────────┤
│  Supervisor(规划/路由)                                                                      │
│   ├─ TenderResearcher   招采检索子图（多源并行 → 归一 → 去重 → 排序）                       │
│   ├─ CompanyProfiler    企业画像子图（解析主体 → 工商/风险/信号 → 采购偏好）                │
│   ├─ RelationMapper     上下游子图（股权/集团/招中标关系 → 图）                             │
│   ├─ SupplierFinder     1688 供应商子图                                                     │
│   └─ Reporter           汇总 + 线索评分 + 校验(数字对原文)                                  │
│  Checkpointer: Postgres（断点续跑 / interrupt 人工确认 / 历史回溯）                          │
├──────────────────────────── 工具层 (MCP Servers + 内部 Tool Gateway) ───────────────────────┤
│  Tool Gateway：统一 Schema · 缓存 · 限流 · 通道路由 · 完整性校验 · 额度确认 · 成本记账 · 来源标注       │
│   ├─ mcp-qcc        企查查官方 MCP(agent.qcc.com) / OpenAPI                                 │
│   ├─ mcp-tyc        天眼查 MCP（备选）  · mcp-qixin 启信（备选/低价招投标）                  │
│   ├─ mcp-tender     自建：招采库检索(本地库) + 实时源适配器(ccgp/乙方宝/剑鱼/央企平台)      │
│   ├─ mcp-1688       自建：1688 开放平台 API + OpenCLI 1688 适配器                           │
│   ├─ mcp-websearch  Exa MCP + 博查 API（发现/补全）                                         │
│   └─ mcp-browser    OpenCLI Browser Bridge（需登录态站点的受控读取）                         │
├──────────────────────────── 采集层 (Workers, Arq) ──────────────────────────────────────────┤
│  定时采集：ccgp / 乙方宝控制台列表 / 剑鱼 / cebpubservice API / 央企平台公开公告             │
│  解析：规则 + LLM 结构化抽取(PydanticAI) + 原文偏移校验 → 入库                               │
├──────────────────────────── 数据层 ─────────────────────────────────────────────────────────┤
│  PostgreSQL 18 + pgvector（业务库/公告全文/向量）· Redis 8（缓存/限流/队列）                │
│  对象存储/本地 data/（原文快照）· 二期 Neo4j（产业链图谱）· Langfuse（Trace/评测）           │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 2. 关键设计原则

1. **离线入库优先，实时查询兜底。**
   - 招投标公告由 Worker 定时采集入库，Agent 先查本地库，所以响应快，也能控制抓取频率。
   - 本地库没有命中、或用户要求"最新"时，再调用实时源。
2. **工具层用 MCP 标准化。**
   - 企查查、天眼查直接复用官方 MCP；自建数据源也封装成 MCP Server。
   - 以后更换 Agent 框架时，工具层不需要重写。
3. **所有外部调用都经过 Tool Gateway。** Gateway 统一负责：
   - 缓存：key 为 `(tool, normalized_args)`，TTL 按数据源分别配置；
   - 限流：令牌桶，按 source 和账号分开计；
   - 通道路由：API/MCP → Exa → OpenCLI 真实浏览器（已登录会员）逐级升级，直到内容完整（见 04 §2）；
   - 需要用户操作（登录、页面确认）时触发 `browser_action` interrupt，用户完成后自动继续；
   - 计费和额度：消耗付费额度前触发 LangGraph `interrupt()`，请用户确认。
4. **结构化优先。**
   - 每个工具都返回带 `type` 的 JSON，前端按 `type` 渲染对应卡片。
   - LLM 只做规划、抽取和总结，不让它直接"编造字段"。
5. **可追溯，可校验。**
   - 每个事实字段都带 `source`、`source_url`、`fetched_at`、`evidence`（原文片段或偏移）。
   - 金额、日期、企业名都要做确定性校验（参考 BidAgent 的做法）。
6. **一切以合规为边界。** 详见 `08-compliance-security.md`。

## 3. 技术选型

| 层 | 选型 | 版本（2026-10） | 理由 |
|---|---|---|---|
| 前端框架 | Next.js（App Router）+ React | 16.4.x（≥16.2.6）/ 19.3 | 主流，SSR + 路由 |
| UI | shadcn/ui + Tailwind | Tailwind 4.3 | 可定制，MIT 协议 |
| 对话组件 | assistant-ui + `@assistant-ui/react-langgraph` | 0.15.x / 0.14.x | 原生支持 LangGraph（interrupt、子图事件），Tool UI 可渲染卡片 |
| 图可视化 | AntV G6 | 5.1.x | 支持 dagre 分层（上游→本企业→下游）、Combo 集团分组，中文生态好 |
| 统计图表 | ECharts | 6.1.x | 金额趋势、地域分布 |
| 后端 | FastAPI + Pydantic 2 + SQLAlchemy 2.1 | 0.142 / 2.13 / 2.1 | async，类型安全 |
| Python | CPython | 3.13.x | 生态最稳；本机已有 3.14，用 uv 管理 3.13 |
| Agent | LangGraph + langchain-openai | 1.2.x / 1.6.x | 有状态图、并行、interrupt、checkpoint |
| 抽取 | PydanticAI 或 LangChain structured output | — | 公告 → 结构化 JSON |
| 工具协议 | MCP（`mcp` 2.3 / `fastmcp` 4.0） | — | 业界标准，企查查、天眼查有官方 MCP |
| LLM | OpenAI 兼容网关：DeepSeek / Qwen / Kimi / GLM，可选 Claude | — | 按任务路由：规划用强模型，抽取用便宜模型；配置回退 |
| 任务队列 | Arq + Redis | 0.28 / 8.x | async 原生，轻量；二期如需长期可靠调度再评估 Temporal |
| 数据库 | PostgreSQL + pgvector | 18.x / 0.8.6 | 业务数据、全文检索（zhparser/pg_jieba）、向量检索 |
| 图数据库 | MVP：PG 边表 + 递归 CTE；二期：Neo4j | 2026.08+ | 先简单，再按需升级 |
| 抓取 | Crawl4AI（静态/政府站）、OpenCLI（登录态站点）、httpx（API） | 0.9.x / 1.8.8 | 详见 research/03 |
| 搜索 | Exa（MCP/API）+ 博查 Bocha | — | Exa 已实测中文效果好；博查是原生中文搜索 |
| 可观测 | Langfuse（自托管）+ 结构化日志 | 4.17 | Trace、成本、评测 |
| 包管理 | uv（Python）、pnpm（前端） | 0.11 / 9.15 | 本机已安装 |
| 部署 | 本地开发直接运行进程；生产用 Docker Compose（大陆云主机） | — | 本机未装 Docker，开发阶段使用本地 PG/Redis |

## 4. 目录结构（规划）

```
003Customer-Acq/
├─ docs/                     # 本文档集
│  ├─ research/              # 调研报告
│  └─ adr/                   # 架构决策记录
├─ config/                   # 配置（不含密钥）
│  ├─ settings.example.yaml  # 应用配置样例
│  ├─ sources.yaml           # 数据源注册表（启用/限流/TTL/成本/合规级别）
│  ├─ models.yaml            # LLM 路由配置
│  └─ .env.example           # 密钥模板（真实 .env 不入库）
├─ data/
│  ├─ raw/                   # 原文快照（html/txt/json），按 source/date 分区
│  │  └─ samples/            # 样例（乙方宝实测）
│  ├─ processed/             # 清洗后的导出数据
│  ├─ seeds/                 # 种子：行业词表、地区编码、产业链本体
│  ├─ cache/                 # 本地缓存（开发用）
│  └─ browser-profile/       # Agent 专用 Edge 配置（登录态，gitignore）
├─ src/
│  ├─ backend/               # FastAPI 应用（api / services / db / models）
│  ├─ agents/                # LangGraph 图、prompts、state、节点
│  ├─ tools/                 # Tool Gateway + 工具实现（统一 schema）
│  ├─ mcp_servers/           # 自建 MCP：tender / 1688 / browser / websearch
│  ├─ crawlers/              # 采集 Worker：各源 adapter + 解析器 + 调度
│  └─ frontend/              # Next.js 应用
├─ scripts/                  # 初始化/运维脚本（建库、导入种子、评测）
└─ tests/                    # 单测 / 工具契约测试 / Agent 评测集
```

## 5. 部署拓扑

| 环境 | 组成 |
|---|---|
| 开发（本机 Windows） | Next.js dev + uvicorn + Arq worker；本地 PostgreSQL 18、Redis（Memurai 或 WSL）；Edge（OpenCLI 扩展，Agent 专用配置） |
| 生产（建议） | 大陆云主机（2C4G 起步）+ Docker Compose：web、api、worker、postgres、redis、langfuse。浏览器类任务放在单独的 Windows 或带 GUI 的 Linux 节点上，挂 OpenCLI。原因有二：境外 IP 会被企查查、部分政府站拦截；Exa、Jina 等境外服务需要能出境的网络 |
