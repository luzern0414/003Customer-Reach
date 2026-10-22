# 企业获客工作台 Implementation Plan

> **For agentic workers:** 在当前 dev 工作区按任务顺序执行；用户已授权直接优化，不新增审批步骤。用 executing-plans 跟踪验证，用 requesting-code-review 独立审查。

**Goal:** 打通采购检索、证据匹配、清楚展示与销售跟进。

**Architecture:** Company 与 Lead 保留独立实体，共享查询入口。新增 acquisition 投影及 lead_analysis 业务模块，复用现有 Job、ToolCall 和 LangGraph，不新增 Agent 或数据库迁移。

**Tech Stack:** Python/FastAPI/SQLAlchemy/Pydantic/LangGraph，Vue3/TypeScript/Element Plus。

## Global Constraints

- 只读 config/apikey.txt，测试不接触生产 data/app；UUID 隔离验收，最终可在无活动任务时按项目脚本加载已验证代码。
- 所有可见文字至少14px，Microsoft YaHei，390px无横向溢出。
- 原始来源与引文不重写；预算/限价/成交分开，不造概率。
- Git 提交带 [ci skip]，精确暂存本轮文件，旧 dirty 保留。

### Task 1: 获客数据投影与查询

Files: backend/app/acquisition.py、service.py、main.py、tests/test_acquisition_workspace.py。

Produces: acquisition_view(db, lead_view) 返回 projects、gaps、research_context；list_leads 新增 conversation_id，筛选和统计同范围。

- [x] 写隔离 API 测试：不同会话2条线索，筛选只返回关联1条；2条公告保留，过期不算开放；预算和成交不混。
- [x] 运行 `.venv/Scripts/python.exe -X utf8 -m pytest tests/test_acquisition_workspace.py -q`，确认断言失败。
- [x] 投影使用 procurement_views 与 Evidence；项目字段从本公告连续原文提取，不拼接他项目，不用数量推金额。
- [x] 同命令通过，新增字段不改变现有 /leads 与公司投影。

### Task 2: 有证据的 AI 匹配

Files: backend/app/lead_analysis.py、prompts/acquisition.py、agent.py、intent.py、schemas.py、main.py、tests/test_lead_analysis.py。

Produces: AnalysisBatch 契约；分析输入含产品、已保存事实、项目片段、状态、反馈及完整覆盖计数；输出引文引用必须属于同条输入。

- [x] 测试伪造来源、非连续引文、失效事实、不存在产品索引被拒绝；产品改变后旧分析显示待更新。
- [x] 先运行测试失败，再实现 prompt/schema/输入及输出校验。
- [x] 接入 answer 节点，采购获客复用结构化结果生成可追溯答复；失败交付真实数据和明确“分析未完成”，暂停按原语义抛出。
- [x] POST /api/leads/{id}/analysis 排原 Job 队列，固定目标和产品上下文；同token复用、无产品拒绝，禁止公网工具。
- [x] 跑对应回归并同步提示词白名单快照。

### Task 3: 查询与获客详情

Files: web/src/pages/QueryResults.vue、LeadDetail.vue、components/OpportunityCard.vue、LeadAnalysis.vue、ArtifactPanel.vue、main.ts、acquisition.css。

- [x] 查询页增加获客视图、状态/对话筛选、真实计数和空状态；公司卡维持既有投影。
- [x] 获客详情展示完整项目、联系口径、事实/替代值、全部来源、反馈和跟进；修改只 PATCH CRM字段。
- [x] AI 面板显示逐需求匹配、依据、条件与下一步，按钮提交真实排队任务，可进入工作台查看过程。
- [x] 工作台结果栏直接显示机会摘要和详情入口；旧销售跟进支持指定 lead_id 深链。
- [x] `npm run build`，真实隔离 API 浏览器1440/390检查、跟进保存刷新、异步失败和无溢出。

### Task 4: 整体验证与交付

- [x] 真实公告隔离导入/真实模型有界匹配，读取保存结论与连续引文、记录时长和限制。
- [x] 后端可运行完整回归、前端现有测试/build、源码快照 --check。
- [x] 独立代码审查，修复问题后复测受影响路径。
- [x] 更新业务使用说明与接续文档，凭据扫描、diff --check、精确提交 [ci skip]。

## 最终执行记录（2026-10-13）

- 来源范围、预算/限价、公告状态、多行需求、资料变化、预算传播、同Job超时恢复、跨Job分析复用、按产品对话隔离、来源闭包均有隔离回归；跨对话及第13来源问题先复现red，修复后green。
- 真实UI提交分析Job `3b2894b7834b475dac380d1cfcb0393c`：17.75秒、2模型调用、1项匹配、4/4片段与1/1公告，completed/非stale/无公网工具；这是已归档采购的真实匹配，不是新自主发现。
- UI1440/390无溢出、可见文字≥14px，实际Microsoft YaHei；跟进/日期/沟通保存刷新、负责人草稿保留、归档原文、企业空状态、编辑深链、工作台机会卡通过。延迟PATCH/POST禁用输入，模拟500保留反馈草稿。
- 独立复审发现多买方串字段、预算异常吞掉、多行技术条件丢失、多站要求丢失、跨对话产品串用、CRM草稿/异步更新及来源独立裁剪问题；已修并复核无剩余阻断。
- 第一轮完整可运行组707 passed/1 failed/6 deselected，失败为原暂停计时断言（5.3秒<2秒）；独立harness第一次22通过/1同计时失败，其后单用例通过、harness完整23通过。最终串行709 passed/6 deselected/171.54秒，未放宽断言、未修改暂停实现，计时抖动的根因未证明。
- 前端现有12测试通过，最后构建通过；Element Plus及Markdown原有大包提示保留。提示词快照生成与--check通过。
- 历史JSON归档及LibreOffice环境缺失：沿上阶段明确排除3个历史/文档测试模块及6个相同依赖用例，不伪造资料；新企业匹配上下文仍有独立规格/期限/引用与来源闭包测试。
- 最终确认生产无活动任务后，按stop.ps1/start.ps1加载API与Worker，新接口及conversation_id在运行中OpenAPI核验，health=ok、worker_online=true；7个历史partial任务保持原状态。未写生产测试客户、未推送Git。

最终后端命令（backend目录）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests --ignore=tests/test_company_identity_relations.py --ignore=tests/test_company_workspace.py --ignore=tests/test_documents.py -k 'not test_sample_import_and_rich_export and not test_company_match_context_preserves_facts_plans_and_sources and not test_product_match_runs_document_graph_with_bound_company and not test_history_distinct_relation_fragments_and_document_scope and not test_history_source_backfill_preserves_latest_research_metadata and not test_document_entry_keeps_disclosed_plan_budget' -q --tb=short --junitxml=../.codex-tmp/acquisition-workspace/pytest-final.xml
```

当前真实模型报告 `.codex-tmp/acquisition-workspace/84dc60d895d04b60b3750db6f5cb02f1/report-current.json`；浏览器截图在`.codex-tmp/acquisition-workspace/`。临时API8816和专用浏览器已停止；生产服务按项目脚本保留运行。

最终源码compileall、提示词快照--check、Windows CRLF规则下diff检查通过；30个本轮文件的本地与暂存字节已用实际模型/LangSmith/QCC凭据扫描，无泄露且无密钥回显。精确暂存，不包含原README、BidMonitor桥接等旧dirty。
