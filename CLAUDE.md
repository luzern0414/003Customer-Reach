# CLAUDE.md — DealRadar AI 智能获客系统

> 给在本仓库工作的 Agent（Claude Code / Codex / Cursor 等）的项目说明。`AGENTS.md` 与本文件内容一致。

## 项目在做什么

B2B 获客系统。销售在工作台用一句话描述产品或输入企业名，系统用 **LuzCrawl** 在招投标与企业信息网站上检索、阅读原文，由模型抽取结构化信息，**逐字核验原文**后入库，输出：

- 找买家：正在或近期采购某类产品的单位 → 线索
- 查企业：工商信息、采购记录、中标记录，以及由公告推导出的客户、供应商、竞争对手

## 架构

```
web/ (Vue 3 + Element Plus)  →  backend/app (FastAPI，单进程)
                                   ├─ research/pipeline.py  研究管线（阶段可恢复）
                                   ├─ crawl.py              LuzCrawl CLI 适配层（唯一采集通道）
                                   ├─ sites.py              数据来源注册表（检索方式、详情链接规则）
                                   ├─ llm.py                模型网关（JSON Schema 结构化输出、流式）
                                   ├─ research/store.py     只保存通过原文核验的字段
                                   ├─ services.py           API 查询；上下游由公告参与方推导
                                   └─ db.py                 SQLite 数据模型
```

管线阶段：`understand → identify(查企业) → search → screen → read → enrich(找买家，补充采购方工商信息) → profile(查企业) → answer`。进度写入 `job.plan`，暂停、重启、用户登录后从中断处继续。需要登录、验证码或选择企业时任务进入 `awaiting_user`，前端显示交接卡片。

## 工作规则

1. **采集只走 LuzCrawl**（`D:\Codes\Luz-Crawl`，CLI 子进程）。不要再引入 Exa、OpenCLI 插件、Playwright 或 HTTP 直读。默认使用已连接的 Edge（`doctor` 返回的 `context_id`），多个无头进程会争用同一资料目录而失败。
2. **登录、验证码由用户处理**，系统不填写账号密码、不识别验证码；限流（rate_limited）不重试、不换入口。
3. **事实必须可追溯**：模型输出的每个字段带 quote，`research/verify.py` 核验 quote 出现在来源正文中、值出现在 quote 中，未通过一律不保存。未披露的金额、联系人保持为空。
4. **数据源**：内置站点在 `sites.py`（文件头注释记录实测结论与日期）；用户在“数据源”页面新增的站点存于 `custom_sites` 表，`all_sites()` 合并两者，管线只通过它取站点。新增内置站点前先用 LuzCrawl 实测列表页与详情页正文（是否有详情链接、正文是否完整、是否打码），或用 `POST /api/sources/test` 验证。
5. 模型服务只支持 `json_schema` / `json_mode` 结构化输出（强制 tool_choice 会被拒绝）。
6. 不提交 `config/apikey.txt`、`data/`。文档用中文；代码注释风格与周围代码一致。

## 常用命令

```powershell
# 后端（Python 3.12，依赖见 backend/requirements.txt）
cd backend; .venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
# 前端
cd web; npm run dev        # /api 代理到 8000
npm run build
# 一键启动 / 停止（生产方式）
powershell -File start.ps1 ; powershell -File stop.ps1
# 采集工具状态
node D:\Codes\Luz-Crawl\scripts\luz-crawl.mjs doctor
```

## 目录

```
backend/app/        后端源码；backend/tests/ 测试（fixtures 为真实采集正文）
web/                前端
config/apikey.txt   模型服务地址与 Key（不提交）
data/app/           dealradar.db、上传文件、日志（不提交）
data/crawl/         LuzCrawl 任务目录与原始证据（不提交）
docs/               商务需求、设计文档
```
