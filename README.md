# Client Reach

中文 B 端 Agent 工作台，v0.4 使用 LangGraph 编排企业研究（招投标采购、上下游、竞争对手、工商摘要），接通后端数据库与前端。

用户介绍产品或上传资料后，gpt-6-luna 自动整理画像，通过 Exa MCP 检索公开买家资料，逐字段匹配原文并保存线索。未知采购、营收、价格与频次保留为空；公开联系人不脱敏展示，调试日志不记录密钥与完整手机号码。

## v0.4 招投标情报、上下游与研究经验（2026-10-10）

查询某家企业的采购信息或上下游时，Agent 先查招投标平台，再让模型补查官网、联系方式和经营报告。详细设计、数据口径与验收数据见 `docs/02-产品与开发/设计文档/12-tender-intel.md`。

**能得到什么**

- 采购需求：企业发布的招标/询价公告，包含物资名称、型号、数量和预算（原文有披露时）。
- 中标与客户：企业中标或入围的项目，以及采购方。客户按公开招投标次数排序。
- 供应商：企业自身采购的中标方，加上平台的“合作乙方/常合作供应商”统计。
- 竞争对手：同一项目的共同投标企业及次数。
- 工商摘要：法定代表人、注册资本、成立日期、经营状态、信用代码、行业和地址，用来补齐基本信息卡。
- 企业标识：从官网取图标作为头像，取不到时显示企业首字。

**数据来源**：千里马、中国采购与招标网、必联网、乙方宝公开页（复用 `src/tools/acq_query` 的 OpenCLI 适配器，免登录）；千里马系企业招投标主页、建设通、水滴标讯（直接读取公开页面，Exa 已索引版本兜底）；Exa 全网检索原始公告。验证码和登录页一律不绕过。

**记忆与链路**

- 每个任务结束后，后台累计各来源的“尝试/成功/被采用”次数，并保存企业研究档案。档案中的有效入口包括招投标主页，下次研究会优先使用。
- LangSmith 追踪内容：每个任务的根运行名、意图标签、按工具命名的子运行，以及任务结束时写入的质量指标（核验事实数、采购/中标记录数、对手方数、模型调用数）。

**新增接口**

- `GET /api/companies/{id}`：新增 `tenders`（采购、中标、待核实记录与对手方汇总）和 `registration` 字段。
- `GET /api/companies`：列表项新增 `tender_purchases/tender_wins/tender_customers/tender_suppliers/logo_url` 字段。
- `GET /api/companies/{id}/logo`：返回企业标识。
- `POST /api/companies/{id}/logo/refresh`：重新获取企业标识。

**工具可靠性（v0.4.1）**：OpenCLI 内置于 `vendor/opencli`（定制插件目录 `OPENCLI_PLUGIN_DIRS`，见 `vendor/opencli/NOTICE.md`）；Exa 限流时自动改用 OpenCLI 百度/搜狗检索；网站指引、重试策略与 Pydantic 输出校验见 `backend/app/site_guides.py`、`tender_models.py`；24 小时内已采集的企业直接复用已保存数据。详见 `docs/02-产品与开发/设计文档/12-tender-intel.md` §9。

首次安装需补充：`cd vendor/opencli; npm install --omit=dev --ignore-scripts`，`cd tools/browser; npm ci`。

**数据库**：新增迁移 `20261010_05`，建了 `tender_records` 和 `tender_relations` 两张表，启动时自动执行。

**验证**

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests -q          # 当前 585 通过
cd ..\web
node --test tests/company-overview.test.cjs tests/markdown.test.ts
npm run build
```

当前有 36 个测试失败或报错（6 个失败、30 个报错），都是本机缺失项，不是代码问题：

- 缺历史研究原始数据（`.codex-tmp/*-research/*.json`、`data/normalized/*.json`），这些只在加密备份中，恢复钥未随仓库提供。
- 缺 LibreOffice 和 Poppler。

**已知限制**

- 未配置 `EXA_API_KEY` 时，Exa 以匿名方式访问，密集使用会触发 429 限流，主页发现和原始公告追溯会受影响（已有数据库和记忆兜底）。
- 大型采购单位的结果公告多在付费墙后，供应商只能取得一部分。
- 乙方宝会员、中国政府采购网、剑鱼、全国公共资源交易平台需要 OpenCLI 扩展连接 Agent 专用 Edge（用 `scripts/acq doctor` 检查），本机当前未连接。

\r\n## BidMonitor 公开采购工具（2026-10-12）

独立工具安装在 `D:/Codes/000GithubProject/003_BidMonitor-AI`，当前项目通过子进程查询软件 / AI 等采购需求，返回公告正文、连续引文、字段冲突、公告版本及覆盖范围。来源为中国政府采购网、深圳政府采购公告子站、南方电网；详细范围与数据门禁见 [工具说明](docs/02-%E4%BA%A7%E5%93%81%E4%B8%8E%E5%BC%80%E5%8F%91/%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3/11-acq-query-tool.md)。

```powershell
.\scripts\bidmonitor.ps1 "软件" --keyword "人工智能" --keyword "AI" --keyword "大模型" --sources "csg,ccgp,shenzhen" --days 30 --limit 20 --max-details 18 --max-requests 40 --timeout 180 --new-only
```

默认查询会返回本轮匹配的已见公告；`--new-only` 只返回该组查询条件下未见的公告版本。同 URL 改文可形成新版本，不同公告阶段分别保留。`partial` / 退出码 2 表示有覆盖缺口，须继续读取 JSON 内已取得的结果与错误。第二次软件/AI真实验收首次返回6条，完全相同查询重复匹配6条但新增0条；详细请求、快照哈希、边界与覆盖限制见 [验收记录](D:/Codes/000GithubProject/003_BidMonitor-AI/data/verification/20261012-final-v2/ACCEPTANCE.md)。此入口输出原始采购情报，后续仍经 Evidence 与人工 review 才进入 CRM。

\n\r\n## 本地运行

HTTPS 默认使用 certifi CA 包且保留证书/主机名验证，避免本机 OpenAI3.22→httpx2→Windows truststore 系统链查询同步阻塞 Worker。已有 SSL_CERT_FILE 或 SSL_CERT_DIR 不覆盖；需要自定义 CA 时使用这两个标准环境变量。不会使用 verify=False。

日期：2026-10-02，执行者：Codex。默认本机单工作空间，SQLite业务库、官方AsyncSqliteSaver checkpoint、持久WorkspaceStore及中文FTS5知识库，无外部销售消息发送。

```powershell
cd D:\Codes\003Customer-Reach
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
# 停止本项目进程（不删除数据）
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

访问 http://127.0.0.1:8000 ，接口参考 http://127.0.0.1:8000/docs 。Web与Worker为独立隐藏进程，关闭网页不会停止任务。脚本检查已有PID，并最多等待30秒确认API和本次Worker心跳就绪；Worker使用单实例锁。异常重启会把遗留运行任务标为暂停，可在首页恢复。

启动/停止操作写入`.codex-tmp/runtime/lifecycle.jsonl`，仅记录事件、进程和调用者PID、上海时间，不记录凭据或环境。stop_requested是已核对目标的停止意图，不等于所有退出均由用户引起；若进程意外消失，需要结合持有句柄的退出码及系统日志判断，不能仅凭一次连接失败推断崩溃。

2026-10-03 Windows部署记录确认10:36:59的Codex升级使用ForceTargetApplicationShutdownOption强制关闭目标应用，10:37:09完成注册，与本次服务消失时段吻合。由Codex启动的本地服务可能随客户端更新停止；更新后运行start.ps1恢复，数据库/checkpoint保留，未结束任务恢复为可继续的暂停状态。本项目没有安装系统服务，不承诺跨客户端更新常驻。

首次安装（Python 3.12+、Node 20.19+/22.12+，本机已安装依赖）：

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd web
npm ci
npm run build
cd ..
```

模型只读 `config/apikey.txt`，支持一行API URL、一行Key，或JSON配置；固定模型 `gpt-6-luna`。请勿把该文件提交版本库。模型服务会产生实际调用。检索连接已配置的匿名 Exa MCP，配额受服务限制；限流保留部分结果，不绕过验证码或改用浏览器搜索。

前端开发 `cd web; npm run dev`，/api代理到8000。后端可分别在backend运行 `.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` 和 `.venv/Scripts/python.exe -m app.worker`。

验证：在backend执行 `.venv/Scripts/python.exe -m pytest tests -q`，隔离库保存在 `.codex-tmp/tests`；`check_v2_model.py`验证真实6luna工具/Pydantic/流式能力；`verify_v2_budget.py`验证真实任务模型预算。

`verify_runtime.py`检查实际本机API、每条证据原文、Excel导出数量和密钥未泄露。本地回归覆盖会话路由、文件解析、流式停止、LangSmith本地协议/正文隐藏与初始化降级、并发/预算/恢复、证据/反馈及CRM。Windows PowerShell5.1启动脚本保留UTF8 BOM，请勿去除。

- `backend/app/`：Agent、API、服务、SQLite队列、附件解析与证据校验。
- `backend/skills/buyer-research/SKILL.md`：Agent运行时实际加载的买家研究规则。
- `web/`：Vue 3、Element Plus、markstream-vue Markdown；工作台/查询结果/设置。参考图由D:/Codes/Imagegen生成，原图保留；页面为真实Vue组件。
- `data/app/`：真实CRM数据库与上传文件。备份时先停止服务，复制整个目录。
- `log/web/api-<PID>.jsonl`、`agent-<PID>.jsonl`：请求/任务日志按进程分流，2MB轮转、3份备份；旧固定名日志保留作历史。
- `.codex-tmp/runtime/`：进程PID与标准输出；不含配置文件副本。
- `.codex-api-spec/`、`.codex-sql/`、`.codex-log/`：接口、建表与执行报告。

首页可查看产品画像、实时任务日志、暂停/恢复。线索页支持筛选、分页、新增/编辑、负责人、状态、下次跟进、标签、批量改状态、跟进、软归档及三张工作表的Excel导出。历史研究必须主动导入，明确标记日期，不冒充新搜索。

运行范围：只监听127.0.0.1，尚无账号/权限/多租户。PDF最多100页（逐页中文OCR最多10页），Word支持DOCX与LibreOffice转换DOC，Excel支持XLS/XLSX（每表1000行30列），附件10MB、解压50MB、提取12万字符；Agent单附件最多选择2万字符首尾/相关原文，明确提示未进入上下文的部分。未计算公式与OCR置信度/遗漏范围在附件预览中说明，不补写未知值。当前未接MySQL/PostgreSQL或商业企业数据API。

首页黑白灰，左侧常驻历史/新对话，不显示历史时间、搜索框或矩形选中卡；移动端从左侧抽屉打开。每轮助手回答上方显示自己的持久耗时和默认折叠的真实工具过程，展开显示操作摘要和来源，不显示JSON。停止按钮取消首块/下一块客户端等待，并保留已输出内容；不保证provider随客户端取消停止计费。输入自动44..220px伸缩，支持Shift+Enter换行及组合输入。右侧结果/文件/数据显示当前对话的真实关联记录；新普通问答不清空该对话已保存结果。中英文、Markdown与代码区统一微软雅黑，正文16px、辅助最低13px。旧任务未记录的耗时显示—，不补造。

文档依赖：rapidocr+ONNX Runtime本地CPU中文OCR，模型缓存data/ocr-models；本机Poppler与LibreOffice已发现，可用CLIENTREACH_PDFTOPPM/CLIENTREACH_SOFFICE指定可执行路径。首次OCR需要下载模型，已在本机预热；离线部署应一并准备该模型目录。临时转换与光栅图保留在.codex-tmp/documents，不自动递归删除。解析日志仅记录ID、格式、字符数、警告数和耗时，不记录原文。

## v0.3 企业研究（2026-10-09，Codex）

侧栏为工作台、查询结果、设置；横向企业卡片进入统一的企业综合详情（基本信息、采购、上下游与AI研判同页）。企业数据从API读取，历史研究带快照日期，新事实必须经真实工具读取和逐项校验。旧销售跟进位于`/legacy-leads`，`web/src/theme.css`为当前视觉入口。

企业分支为 `company_context → company_plan → company_collect → company_extract → company_save → company_gap → company_answer`，不经过卖方产品门禁；复用任务、预算、checkpoint、暂停恢复、Worker和SSE。企业模型为Company、CompanyFact、ProcurementProject、ProcurementNotice、CompanyRelation、ResearchCompany。接口见`.codex-api-spec/crm接口文档.md`。

浏览器安装：在`tools/browser`执行`npm ci`，需要Node 20.19+与Microsoft Edge。固定OpenCLI1.8.8和Playwright1.62.0，通过专用Edge profile/CDP执行`opencli web read`，该路径免登录且无需Browser Bridge扩展。`GET /api/browser/status`查看安装/实测状态；缺依赖返回`browser_runtime_unavailable`，受限页保留错误。网页读取成功不等于企业字段已核验。

数据库由启动初始化执行Alembic，当前revision为`20261008_02`。升级先停止服务并备份整个`data/app`（含checkpoint和来源）；也可在backend执行`.venv/Scripts/python.exe -c "from app.db import initialize; initialize()"`。项目使用编程式Alembic Config，不能运行没有alembic.ini的裸`alembic upgrade head`。冻结DDL全文见`.codex-sql/20261009002500_企业研究工作台增量迁移.md`。

正式日志为`log/web/<name>-<PID>.jsonl`，API/Worker按进程分流，避免Windows轮转锁冲突；每文件2MB轮转、3份备份。隔离DATA使用`DATA/logs/<name>.jsonl`。

实际验收：独立库任务`9fccd350beb94a66977e645c46daeeb7`完成真实官网/报告读取、8次模型调用、结构化保存和流式回答，终态`partial`；部分字段/上下游引文未通过核验，未作完整画像成功。历史快照与本轮资料分开，未知数量、单价、复购频次仍为空。

## 既有产品获客验证记录

2026-10-03来源质量补充：实际1688带查询参数厂页被robots拒读，现复用BSD三条款Protego0.7.0核验同源规则，不冒充Googlebot、不去参数或换供应商绕读；QCC567分类访问受限。仅标题/URL的响应不生成正文Evidence，旧归档保留但不传入网页提取上下文。普通有效缓存继续离线复用。当前具体QCC页/公示框架复核未取得新可联系买家，厂商/OEM或吊销主体不自动当正常零售线索。

无用户网址的自主目录路径已实际验证：本轮画像为深圳灯具，检索供应商限额下，图按已启用目录渠道读取PUBLIC_ENTRIES中的核验入口；入口不含客户事实，真实fetch后才产生来源。专用mall_directory/brand_directory或本来覆盖商户目录的directory父渠道可用，official/QCC等其他渠道不借用入口。未知地区/产品不匹配不读，读取仍受数量/时间/同站限制。真实6luna任务94秒、5次模型，保存星烁灯饰及完整电话；搜索警告保留，任务partial。最新版五主体表：`data/exports/20261003_深圳灯具多渠道复核_自主目录读取.xlsx`。

最新五主体真实复核表：`data/exports/20261003_深圳灯具多渠道复核_商场门店扩展.xlsx`。新增乐安居沙井店目录的星烁灯饰门店及13169928365；商场位置、店名与经营公司分开，未知铺位/采购/人数/营收留空。读取复用lxml保留已验证目录模板的分店上下文，入驻记录的电话须对应该店，不能借相邻品牌号码。运行Skill已同步，省略标记不作为引文。

Exa免费限额可能在MCP初始化阶段以JSON-RPC -32000返回，现统一供应商冷却；换平台关键词仍共享同一供应商，不重复发送。已给定公开URL继续走受控HTTP，真实限流后的降级已验证。60秒是未知重置时间的冷却下界，不承诺额度恢复，不挪用模型Key。QA自定义DATA的日志存DATA/logs，避免与正式log/web在Windows争用轮转文件。

start.ps1仅在确认对应服务不运行时归档此前stdout/stderr到`.codex-tmp/runtime/archive`，避免重启覆盖退出证据；已运行服务不移动日志。Windows曾记录同时间段Codex客户端挂起，没有发现对应Python崩溃事件，不能据此确定旧API/Worker退出原因。2026-10-03原生PowerShell夹具与完整218项回归通过；服务重启前应先确认无活动任务并保留一致性备份。

2026-10-03最新完整后端回归228项通过。指定完整买方与卖方身份分离，短来源编号精确恢复，不扩成其他集团/分店。长采购公告支持同源项目、采购人、截止时间分段引文；采购联系字段拒代理/咨询热线，历史公告不加当前采购分。联系页明确并列座机和手机保留两个入口；异常号码没有拨号链接，无有效联系入口保持partial。

最新复核表：`data/exports/20261003_深圳灯具多渠道复核_七主体.xlsx`，6个有公开联系入口的商户/门店及1个无有效联系入口的历史学校采购主体。新增飞利浦灯饰18926563839、TCL罗格朗灯饰13794469638来自同一乐安居目录，不是两个独立来源。真实6luna复测141秒/6模型调用、partial（搜索限额保留）；一条品类引文自动原文修复后保存。行业无分类原文留空，不将深圳填industry；地址争议保留。電話接通、更新时间、采购等仍未知；错误旧导出移至.codex-tmp留存，没有混入生产。

最新真实复核导出：`data/exports/20261003_深圳灯具多渠道复核_采购与联系校验.xlsx`，四个主体，逐条引用匹配真实存档。百明丰三个根域可核验主体，公开电话/邮箱只来自其中一个联系页；学校只有历史采购及异常号码，不能直接拨号。公开目录旧资料不保证仍营业或接通，未知人数、营收、进货价与采购频次为空。

公开渠道统一在`backend/app/source_catalog.py`：官网、品牌门店、家居商场商户、行业黄页、1688公开索引、企查查公开核验、中国/深圳采购、政府公示。设置启用后，图按渠道能力和缺口选择来源；指定1688/企查查会实际尝试，限定平台结果校验真实域名并排除接口文档。公开索引不等于授权API；用户尚无平台权限，企查查与1688授权入口保留待授权，不调用收费接口。

此前九主体表：`data/exports/20261003_深圳灯具多渠道复核_九主体.xlsx`。新增三雄照明深圳销售主体（13428788412、魏先生）及公明辉煌灯饰店（电话争议、伍石山先生）；共7有有效联系入口，辉煌及历史学校没有拨号入口。该轮美东原页已读但模型未完成保存，未列入该表。真实三链接任务经历3次模型读取超时，同job恢复保留预算；最终到480秒预算结束，不能当稳定验收成功。未知规模/营收/采购等仍为空。

最新十主体表：`data/exports/20261003_深圳灯具多渠道复核_十主体.xlsx`。新增美东原文电话`86 0755 23493726`、经销批发角色、主营与地址，共8有有效联系入口，另有辉煌电话争议及学校历史采购。云发了已验证模板通过白名单parse_account生成Pydantic原文事实，再经persist校验；真实独立整图27.5秒/4模型调用，提取未调用模型，搜索仍限额所以partial。一般网页仍由模型处理，不宣称全部模板支持。

同任务真实SDK超时3次后，研究答复可直接列出已保存CRM结果，不再调用模型；通用预算TimeoutError不当模型失败。研究超时已有客户时仍通过SSE reset/delta/completed反馈确定性结果再发原错误终态，不模拟逐字流式、不清预算。已耗尽任务仍终止，节点级真实熔断验证不冒称整任务恢复成功。恢复无新来源保留最近补读页，卖方排除和字段证据规则在模板分支同样有效。当前完整回归228项通过，前端构建/真实桌面和窄屏工具详情验收通过。

2026-10-03最新后端回归235项通过。自主客户发现只给项目Agent产品、地区和角色，不提供客户名/URL；Codex只检查结果与账本。已有客户未满足数量/字段要求仍可转公开目录，新目录发现不被旧名单锁住。独立真实Agent读取两个商场目录和一个品牌目录，保存4条目录门店线索，其中3有格式有效的电话、1为短号待核，282.5秒/partial；不等于4家可联系企业或同主体跨站核验成功。公开采购Agent成功读CCGP列表但0符合条件客户，29.99秒/partial。答复节点已使用CRM有效性投影，真实6luna复测将短号明确标“待核，不作有效联系入口”。检索供应商仍限额，QA数据不写正式CRM，旧Excel不改。目标仍active。

后续最新回归239项通过。采购列表按真实可见下一页href在原预算续读，实际本轮没有可用下一页，未生成猜测链接；列表不进入采购人模型，真实Agent调用数5→4，27.2秒/0客户/partial。满额补查无目标完整名的新页跳过旧事实重提取；真实同job从分析超时恢复，约8.4秒新增一次模型答复，累计预算/失败事件保留、4条线索未变，仍partial。该恢复不是首次整轮耗时已达标的证明。实际lxml6.1.3已显式固定依赖并核实安装包许可，pip check通过。

2026-10-04最新回归249项通过。Agent从实际分店列表发现7个href并读取7分店，真实隔离任务保存8目录门店记录，3格式完整公开电话、5短号待核；全部同一商场网站，不是8独立企业或跨站成功。原任务432.4秒超时，同job按分店scope恢复至累计451.6秒/10调用，历史预算保留。答复结构改为覆盖全部客户的精简数据，真实答复节点另1调用后8条齐全、分店标签据角色原文，不能据此称整轮速度达标。名单文件：`data/exports/20261004_深圳灯具自主Agent目录候选8.xlsx`，由项目原生API数据导出，客户/事实/引文逐格核对、短号缺口保留，未知采购营收等空白。正式CRM/原十主体表未混入QA数据。

客户表格和右侧面板现共用FactValue展示电话、邮箱、联系人与职位状态；有其他有效入口不掩盖短号/失效字段缺口。1440px/390px隔离浏览器验证无错误动作或横向溢出，字体仍Microsoft YaHei。生产API/Worker健康；目标仍active，1688/QCC、多独立来源及更丰富可联系资料尚未验收。

多链接编排已修复：搜索限额不丢未读用户链接，有预算直接回read；新HTTP来源优先提取，“以下/下列”长名单不漏后项，已保存主体不反复生成。单主体同页地址片段差异不重复建客户，冲突仍保留；不同分店不强行合并。图API显式展示gap→read/decide/answer回路。代码224项回归通过；模型超时及辉煌电话归属争议还需进一步验收，不据此宣称全项目完成。

设置渠道页分别展示账本中的最近检索/网页结果，ready仍表示能力已配置，不表示平台持续可用。检索供应商冷却不清除网页最近成功，冷却到期也不宣称恢复；无实测显示尚未实测、空来源显示最近无结果。投影只读不触发搜索、不返回正文或凭据。真实两门店隔离库及生产API/DOM已验证，1440px/390px无溢出。

CCGP已取得的静态gkzb列表可跟进实际公告href，按本轮地区和照明产品过滤，未知模板不猜链接，详情仍占读取预算并独立核验。不会自动全站翻页或把目录记录当已确认采购。2026-10-03公开25页500条标题只有安徽显微镜设备照明匹配，不符合深圳普通灯具ICP，本轮未新增客户；最后目录请求403已停止，不宣称持续可读或全站没有采购。

销售联系资料包括电话、邮箱、网站、地址、联系人/职位、主体信用/登记状态、用途、来源平台与日期。未知字段不补造；短号保留原文且不提供拨号，争议/失效事实不提供联系动作。列表资格优先，再按有效联系入口排序；详情、首页结果和Excel共享同一事实口径。正文提取额外保留静态可见联系侧栏，隐藏区/脚本不进入证据；已选客户原始身份页面优先补读，检索摘要角色信号只用于阅读排序，不能直接充当买家事实。

规划与提取按启用渠道实际加载`backend/skills/buyer-research/references/runtime-playbook.md`，保留共同规则及全部启用平台，不静默截断。`source-playbook.md`保存历史实测，`source-reuse-catalog.md`保存开源评估；既知客户/网址及冗长调试记录不注入每轮规划。现阶段继续复用httpx、Trafilatura、lxml和Exa，不把下载候选仓库当作已接通数据源。

补充实际复用phonenumbers9.0.40（Apache-2.0）：离线号码格式/固话长度检查和RFC3966链接，原号码和引用不改变、不验证接通。明确登录/验证页及旧缓存不当客户正文。用户提供的最多4个公开链接进入真实读取，不制造指针Evidence、不绕过关闭平台；指定采购项目号精确筛选，找不到不以其他项目替代。明确跨站数量按根域计数，未满足时partial；单主体介绍/角色表头的结构关联仍须真实name证据和逐字校验。有界格式修复仅用已取得原文，不因修复绕过校验。

Markdown渲染复用标准markdown-it与MIT markdown-it-cjk-friendly，通过markstream-vue的customMarkdownIt保持真实流式节点；中文标点旁的粗体正确渲染，原文、代码星号与转义文本不重写，HTML始终关闭。

2026-10-03检索修复：新一轮来源优先进入提取，同URL以正确解码的完整正文为主；长目录保留中段商户记录。HTML直接读取原始字节并识别GB2312等声明，乱码缓存不复用，原证据不改写。每批候选最多8个，任务总量可分批达到20个。单独采购公告引用仍验证作用域、客户买方、阶段与原文截止日，不要求复制进基础资料字段。

潜在线索与具体产品/采购确认分开展示。已核实销售点可以作为待核验产品适配的线索，不把“缺采购证据”说成“没有客户”。普通结果追问读取当前对话真实CRM资料，优先于旧助手总结。

知识飞轮实际消费产品知识：用户知识条目进入最多6000字符产品背景，不冒充公开客户来源。真实6luna已从隔离手动知识读出QA-KNOW-02；渠道经验仅同地区同产品排序，基于验证客户产出及精确关联反馈，learn重放按客户ID去重。独立采购公告受失效/纠错反馈约束，旧信号不能复活采购分。

纯继续复用画像不调用模型；新地区/角色需求重新结构化提取并保留产品背景，不依赖城市白名单。2026-10-03真实成都覆盖深圳通过，原型号保留，1次模型调用约8.1秒。前端终态刷新有job/连接守卫及有界重试，旧GET不覆盖下一轮；右侧临时失败保留已有结果并重试，404归档行移除。完整后端回归119项通过。

2026-10-03采购/导出阶段115项回归通过；最终完整后端130项及Markdown4项通过。采购历史不被无公告补查清空，截止后在列表/详情/导出自动撤销采购加分；争议/失效资料带状态，替代值保留统计口径/日期/来源。三表Excel同步保留这些信息，导出采用当前已应用筛选，未提交的输入草稿不改变导出范围。LangSmith云端已完成真实任务验收，见下方记录。

当前消息先路由：问候/身份即时回答；普通解释和已有结果问答走单次流式answer并结束；明确获客/产品资料请求进入 context → profile → plan → decide → search → read → extract → save → gap → answer → learn。历史请求不授权本轮研究，普通聊天不更新画像。产品未变时复用画像，提取证据去重并限制上下文。Worker研究/问答各1个并发槽。State只checkpoint业务值，thread_id固定为job_id。`/api/agent/graph`查看图，`/api/jobs/{id}/state`查看过滤checkpoint；模型bind_tools提出搜索，应用侧独立校验预算与证据。

明确只读文件/提取型号/不要找客户走document：context → answer → END，沿用本轮或最近已上传附件，不进入公网检索/买家画像/采购流程。仅出现“资料/表格”不会把一般解释误判成读取文件。只读文件仍入第一方知识，不能充当公开买家证据。

## Harness复用与链路追踪

运行引擎直接复用MIT LangGraph、官方SQLite checkpointer/Store接口、LangChain模型工具/流式SDK与LangSmith SDK，业务证据与预算规则留在应用层。本轮下载Codex、DeepSeek Harness和Agent Chat UI源码至.codex-tmp/harness-reference，核实生命周期/停止/工具配对/交付物投影后参考适配，没有把Rust、Cordis或Next.js整体移植进Vue/Python，也没有宣称Codex Desktop右栏源码开源。

LangSmith支持后台环境变量或只读`config/apikey.txt`中的独立LangSmith凭据。当前用户文件含模型Key和`lsv2_`追踪Key，`config/langsmith.json`已启用追踪。环境变量优先，显式空`LANGSMITH_API_KEY`可关闭文件凭据；两类Key不得混用。也可用环境变量：

```powershell
$env:LANGSMITH_API_KEY = '<你的LangSmith Key>'
$env:LANGSMITH_TRACING = 'true'
$env:LANGSMITH_PROJECT = 'client-reach'
# 如需非US区域或多工作空间：LANGSMITH_ENDPOINT / LANGSMITH_WORKSPACE_ID
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

默认Client.hide_inputs/hide_outputs=true，元信息关联job_id/conversation_id；自定义工具通过官方traceable加入原生图链路。输入输出可通过LANGSMITH_HIDE_INPUTS/LANGSMITH_HIDE_OUTPUTS显式调整。无key即使开关true也关闭追踪，不发送未经配置的请求。可选config/langsmith.json只保存enabled/project非凭据，示例config/langsmith.example.json；GET /api/tracing和设置“运行”显示实际配置状态，不返回key。

2026-10-03真实云端验收：隔离LangGraph问答的父记录`01a0ff98-dd72-73f3-a34f-b5661c4a7a51`及6个子记录已读取，包含完成的图/模型调用，输入输出正文隐藏。本机collector与云回执分开记录。完整验收证据见.codex-log/20261003010000_黑白灰分屏与Agent完整调试.md。

实际启用第一方产品知识、企业官网、品牌/商户目录、公开采购公告。Exa负责发现，公开HTML/Trafilatura负责正文读取；这些渠道共享搜索供应商，不是多个独立搜索引擎。RFQ、授权企业数据、商业Intent在设置中显示待授权，当前不能调用。资料缺口会换渠道；来源仍不足时保持未知。

公司画像/偏好/排除项长期持久化，客户原文带来源与复核期限写入知识库；销售反馈使知识失效、旧事实不能被缓存恢复，并改变渠道配方排序。原始证据不改写，助手总结不自动成为企业事实。冲突字段保留原值及alternatives，标记disputed；仅角色已证实的买家具有资格分，历史采购不算当前意向。

SSE直接发送模型astream的message.delta，支持事件ID/Last-Event-ID重放；草稿重新生成使用generation_id和message.reset。Markdown禁止执行原始HTML。累计耗时不含暂停/停机；异常中断只计到最后可观测活动并标metrics.clock_is_partial，UI显示≥已确认耗时。原生阻塞可使心跳一起停止，未知尾段不能宣称最多只有5秒。外部模型请求在节点中断时可能重执行，不承诺exactly-once；成功工具和结构化模型结果先落账本后复用。

设置可管理搜索、读取、单客户补查、累计时间、模型调用和令牌预算。模型每次请求前预留输入估算+最大输出+协议余量，失败请求不退款；provider给出usage则记录reported_tokens，否则保留保守估算estimated_calls，不把估算写成实测费用。恢复使用原任务预算，降低线索上限只禁止新增主体，不跳过已有客户补全。

## 目录

- `docs/`：产品方案、数据来源和工具选型文档
- `src/`：采集、清洗、实体解析、线索评分和后续 Agent 模块
- `config/`：数据来源、隐私策略和数据结构配置
- `data/`：原始、标准化、人工复核和导出数据目录；真实数据默认不入库
- `opensource-crawlers/`：第三方开源仓库清单、下载脚本和本地仓库目录
- `log/`：运行日志；过程留痕仍放在 `.codex-log/`
- `scripts/`：项目维护和本地验证脚本
- `tests/`：后续采集器、标准化和评分测试
- `tools/mcp/`：已安装的 MCP 运行环境、版本和调用验证说明

## 酒店获客样本

已安装并测试 Exa 搜索/读取、官方 Fetch 和 Playwright MCP，安装与复现见 `tools/mcp/README.md`。

酒店智能客服助手的7家企业研究见 `docs/01-商务与需求/客户资料/酒店智能客服助手_B端客户研究_20260930.md`；结构化候选见 `data/normalized/hotel-b2b-research-20260930.json`。候选未确认采购意向，不自动导入或触达。

## 原预研方向

1. 选择一个物料品类和一个销售团队作为试点。
2. 确认可用的授权企业数据 API 或人工导出文件。
3. 先实现企业去重、证据链和线索评分，再接入页面采集。
4. 以销售反馈验证线索质量后，再扩展到产品匹配和 Agent CRM。

## 运行边界

第三方开源仓库只是采集和处理框架，不代表目标网站数据可以任意复制或用于营销。每个来源都要单独核对服务条款、API/数据许可、robots、限速、登录权限和个人信息处理要求。

## 深圳灯具获客示例

- 数据：`data/normalized/shenzhen_lighting_20260930.json`。
- Excel：`data/exports/深圳灯具潜在客户与产品采购参考_20260930.xlsx`。
- 工具：`scripts/research/lead_research.py`、`build_lighting.mjs`、`verify_lighting.mjs`。
- 完整运行方法、结果与限制：`.codex-log/20260930164904_深圳灯具客户采集与Excel验证.md`。

上述2026-09-30脚本为独立历史研究工具，不含LLM。新增初代Web应用有独立6luna Agent与Worker，可以自行执行产品分析和公开研究；匿名搜索配额仍不能保证无限采集。无采购证据不补造采购、营收、供货价�