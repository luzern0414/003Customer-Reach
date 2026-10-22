# 09 开发计划与测试

> 估算口径：1 名全栈开发 + AI 辅助。每个里程碑结束时都有可以演示的成果。

## 已完成

- **acq 定制信息查询工具 v0.1**（`docs/02-产品与开发/设计文档/11-acq-query-tool.md`）
  - OpenCLI 插件：`yfbzb` search / detail / login / whoami，`ccgp` search。
  - Python 编排：自动启动 Edge、登录引导、yfbzb + ccgp + Exa 多源查询、角色判定、上下游汇总、报告输出。
- M1 中的 `tender_search`、`web_search`、`browser_read` 工具，将直接复用这个插件和 `src/tools/acq_query` 中的模块。

## 里程碑

| 里程碑 | 周期 | 内容 | 验收 |
|---|---|---|---|
| **M0 工程骨架** | 2 天 | uv 工程（Python 3.13）+ pnpm Next.js 工程；本地 PG18/Redis；Alembic 迁移；配置加载（settings、sources、models）；日志 | `scripts/dev` 一键启动，健康检查通过 |
| **M1 工具层** | 5 天 | Tool Gateway（缓存 / 限流 / 通道路由 + 完整性校验 / 记账 / 来源标注）<br>工具：`web_search`（Exa + 博查）、`web_read`、`tender_search`（ccgp 实时 + 本地库）、`company_resolve` / `company_profile`（企查查 OpenAPI 核心 10 个接口）<br>OpenCLI 封装：`browser.read(url)`、`whoami` | 每个工具都有契约测试（录制回放 fixture）；ccgp 检索返回结构化公告 |
| **M2 Agent 核心** | 5 天 | LangGraph：supervisor + tender / company / relation 子图 + verifier + reporter<br>Postgres checkpointer<br>interrupt：cost_confirm、entity_pick | 命令行跑通 3 类标准问题，过程中有确认环节 |
| **M3 API + 前端 MVP** | 6 天 | FastAPI SSE；Next.js 对话工作台（assistant-ui）；Tool UI 卡片（TenderTable / ProfileCard / CostConfirm / EntityPicker）；G6 关系图 | 浏览器中完成"找采购方 → 画像 → 关系图"的完整演示 |
| **M4 采集与入库** | 5 天 | Arq Worker；ccgp adapter；乙方宝 OpenCLI adapter（控制台列表 + 按需详情）；解析 + LLM 抽取 + 校验 + 去重；relations 自动派生 | 每天增量入库；`tender_award` 边自动生成 |
| **M5 1688 + 线索库** | 4 天 | `supplier_search_1688`（OpenCLI 过渡 / 开放平台）；线索库页面与导出；规则评分 | 完成"找供应商"场景；线索可以导出 |
| **M6 质量与评测** | 3 天 | 20 题评测集（tests/agent_eval）；Langfuse 接入；成本报表；合规检查清单 | 召回率 ≥80%，关键字段准确率 ≥95% |
| 二期 | — | 订阅推送、央企平台 adapter、Neo4j 产业链、尽调报告导出、多租户 | — |

MVP 合计约 **30 个工作日**。

## 测试策略

| 层 | 方法 |
|---|---|
| 解析器 | 以 `data/raw/samples` 为基础做快照单测；每个 adapter 至少 3 个样例 |
| 工具契约 | 用 VCR 方式录制真实响应并回放，CI 中不访问外网；另有夜间"活体检测"任务验证各数据源是否可用 |
| Agent | 评测集（问题 + 期望工具序列 + 关键事实），以 LLM-judge 为主，辅以规则断言；每个候选模型都跑一遍工具调用回归 |
| 前端 | 组件用 Storybook（可选）；核心流程用 Playwright E2E |
| 内容完整性 | 用样例断言 completeness_check 能识别占位内容（`****`、登录页、等待页）并升级通道；每个 adapter 断言关键字段齐全 |

## 开发前置条件（需要你提供或决定）

- [ ] LLM：主力模型选择，以及 API Key（DeepSeek / Qwen / Kimi / GLM / Claude）
- [ ] 企查查开放平台：AppKey、SecretKey，以及充值预算
- [ ] 博查 API Key（可选）；Exa API Key（可选，免费 MCP 可以先用）
- [ ] 乙方宝：是否开通黄金会员，以及开通哪些地区
- [ ] 1688 开放平台：是否用企业主体申请
- [ ] 本机安装 PostgreSQL 18 + Redis（或 Memurai）；也可以装 Docker Desktop，统一用 Compose
- [ ] 我方产品词表（用于需求匹配评分）
