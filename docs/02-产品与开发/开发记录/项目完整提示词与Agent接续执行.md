# Client Reach 项目完整提示词与 Agent 接续执行

更新日期：2026-10-14（Asia/Shanghai）。整理者：Codex。

## 2026-10-14 企业历史 MCP 最终适配（当前状态优先）

当前共享BidResearch为0.2.0，应用官方SDK使用绝对 `scripts/run_mcp.py` 入口与四工具白名单。企业history默认五页导航、逐条 `get_tender_detail` 保存，明确近期需求仍recent；详情预算独立累计，共用读取/请求额度，访问拒绝和同站限流不换读取器绕过。初次和恢复共用账本消费与详情队列，恢复后重算诊断，已成功原文不重复调用模型。完整口径与命令见[企业历史MCP与前端现场验收](../%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3/16-mcp-history-detail.md)。

隔离完整Agent `414d30e4201f43cd834fafec2d658637`取得50线索、8份新网络正文、7去重公告（2第二中标人、5候选/备选），1公告客户/10竞争线索及9项企业事实；工商/官网联系缺口使状态partial。8819前端桌面/390及原文入口已核验。最后统一采集节点另以新UUID取得2份真实正文，二次消费不增工具尝试；不能把节点验收当另一完整Agent。

最终恢复补丁相关175回归通过；扩展34通过，5历史工作台setup被缺少 `cleaned_byd_data.json` 阻塞。前端12回归/构建及独立复审通过。正式8000在0活动任务时加载API36284/Worker30324，health与heartbeat正常；5企业/16事实/228招投标记录/45招投标关系/238Evidence/9partial Job业务数量与摘要不变，未导入验收客户或清零预算。下文旧版本/PID/数量保留对应日期，不能作当前状态。

## 2026-10-13 真实数据链路修复（当前状态优先）

本轮诊断与验收见[Agent真实数据获取、恢复与展示](../%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3/15-live-agent-data.md)。修复成交候选/备选解析、同企业时间窗重复、MCP超时已完成资料丢失、应用补读解析、原生候选被模型故障中断、按来源恢复、QCC错误分类及企业招投标来源统计/原文入口。无模型摘要也展示候选和具体公告，不把采购0解释为无需求。

软件/AI服务自主获客Job `0ba2fdf1a307463db01d34d762dd6bfa`同任务恢复completed：东丰县职业高级中学虚拟仿真软件开发服务，预算1504100元，截止2026-10-16 09:30，1买方/1公告及真实AI分析在8816隔离前端展示；未提供已知公司/URL种子。宏天智定向MCP节点取得2候选/3竞争线索，8817展示2份原文；该节点包含工具缓存。

完整企业任务 `ec58d232a0754816abd03731451ca82e`恢复实际执行意图/QCC/MCP/补读/清洗/模型提取/保存，5资料/4来源/1候选/1竞争线索，MCP超时原子快照恢复真实触发。原360秒累计预算耗尽后partial；不能声称全字段研究完成，也不重置预算。8818为此任务持久结果预览。真实来源、原失败、截图和报告保存在`.codex-tmp/live-agent-data/`。

最新正式8000启动器API2336/Worker31496；此前API29252/Worker35620已由项目脚本核对停止，不代表异常退出。正式库8个Job仍partial、5企业/15事实/0采购项目/0公告/0Lead/209Evidence，未自动恢复旧任务或写测试客户。下文旧PID/统计与旧状态是各自日期记录，不作为当前状态。

主联合221通过/3历史归档环境项未选，最后摘要/恢复专项57通过；外部45通过+11subtests，前端8通过和构建通过。外部固定MCP目录`D:/Codes/000GithubProject/Result/001_bid_research_tool`未受Git管理，核心文件指纹见验收文档，升级不可覆盖适配。所有凭据原路径保持，Git提交使用`[ci skip]`，本轮不推送。

## 2026-10-13 企业获客工作台（覆盖旧查询入口描述）

查询结果默认展示自主获客Lead，并可切换Company企业档案。`/opportunities/:id`把逐公告需求、产品匹配、完整来源与CRM跟进放在同一页，原企业综合页保留。工作台右栏显示具体机会，不再只列客户名称。产品对话参数沿入口和API关联验证，避免同一客户串用另一产品画像。

采购标准交付使用结构化匹配，手动分析固定目标、只读归档资料，复用原LangGraph/Job/预算/暂停恢复，不新增Agent或迁移。模板在`backend/app/prompts/acquisition.py`，分析输入按完整记录裁剪、引用门禁与资料指纹复用在`lead_analysis.py`；自由文本结论仍是AI条件判断。流程、口径、真实模型与UI验收见[企业获客工作台](../%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3/14-acquisition-workspace.md)。

当前UI提交的隔离真实模型Job `3b2894b7834b475dac380d1cfcb0393c`约17.75秒/2模型/1项匹配，4证据与1公告均纳入，completed且未失效；只匹配已归档真实采购，不是新自主发现。详细规格仍待采购文件，未补造AI或知识库需求。CRM/来源/390px展示、延迟保存及失败草稿已真实浏览器核验；独立复审问题已修。

本轮最新生产状态：2026-10-13确认无活动任务后按项目脚本重新加载API28288/Worker35676（启动器PID），health=ok、worker_online=true，新分析接口与对话范围参数已加载；7个历史Job仍为partial，未自动恢复、未写入测试CRM、未推送。下节较早health超时属于当时观察。最终串行回归709通过/6未选、前端12通过和构建通过；完整命令及历史JSON/LibreOffice环境缺口见本轮计划，截图/模型报告在`.codex-tmp/acquisition-workspace/`。

## 2026-10-13 企业与采购 MCP 接入

当前代码保留 LangGraph/ToolBroker/checkpoint，接入企查查 HTTP MCP 与固定外部 BidResearch stdio MCP。凭据仍只读 config/apikey.txt，独立预算累计，已读正文直接消费，软件服务与当前开放期限在保存前按原文复核。完整实现、设置、原始公告及验收类型见 [Agent 的企业与采购 MCP](../%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3/13-agent-mcp.md)。

隔离真实完整 Agent 6a6c417359104e53881fe1473f933923 取得东丰县职业高级中学教学虚拟仿真软件开发公告，预算150.41万元、响应截止2026-10-16 09:30，1买方/9模型/249407ms/partial；有1次模型抽取超时。最终 MCP 重复调用和原文保存另独立核验，不能把缓存命中的工具耗时当冷启动或把待核验列表算当前机会。

2026-10-13只读现状：当前原生持续目标为空；生产 data/app/clientreach.db 的7个Job均为partial，没有queued/running/cancelling；8000 health请求超时，原因未诊断。本轮没有重启生产、推送Git或写入生产CRM；下文旧PID、部署指纹及测试计数仅是对应日期历史。最终本地回归及依赖缺口以本轮计划为准。

## 2026-10-09马尾查询提速（覆盖下文旧工作台调试入口与同步调度描述）

每条新消息仍真实模型识别；跨任务历史可复用、每轮新搜索。两路检索并行，读取小批先出结果，非关键摘要清洗持久pending后Worker后台整理。原文片段定位进入checkpoint，完整配置片段保留待分析。保存在线程事务执行，核验与来源绑定后才反馈；LangGraph async checkpoint可能在突发进程退出时少最后一个checkpoint，已落账副作用仍幂等重放。

公司首批真实事务后立即输出确定性答复，最终以新generation替换；first_verified_result_ms/first_answer_ms分别记录。API查询按updated_at降序分页；回答两个调试按钮已删除，右栏为精简企业卡、画像/导出操作及折叠来源；Markdown自身token覆盖首段间距，手机产物可打开和关闭。LangSmith后端可观测性仍保留。

company-evidence-6按分段身份/买方/编号/数量/日期核验。集团页尾电话、采购设备、视频标题、未来拓展计划不作为本主体联系/已实现产品。唯一明确截止从原文绑定，24:00保持日期粒度，下载或计划日不作实际发布日期；同买方/标题/真实日期合并转载，未知字段仍空。并行暂停取消兄弟请求，持久pending_cleanup防立即恢复重复发送；原预算不清零。

真实隔离8aa827首批66885ms，但该早期版本仍有页尾电话/转载/日期问题，其结果不得作质量完成证据。修正后的accepted-live首次e1f260fca1864de3a053bc7fa8d6e7cf首批53798ms、全轮244229ms、26核验资料/2项目；复用e02911b0174f425b9132fb20f4158a08首批44555ms、全轮199519ms、22本轮核验资料/2项目，两次均新网络、partial。固定公开入口为实际读过的马尾官网/集团原始公告，只作导航，不手工注入客户字段。日志`.codex-log/20261009202123_马尾企业检索提速与紧凑产物.md`，证据`.codex-tmp/mawei-speed/`。部署与最终回归以该日志最后记录为准。

正式最终：77917首批45709ms、全轮247646ms；6982c22ba009416e8b5bec0ba15cf19d首批96638ms、全轮294304ms、21项本轮核验，独立深挖取得2025电加热器。数据库最终3不同采购项目/3公告；旧日期精度/长短标题转载以duplicate_of可逆归并并保留来源/历史。当前正式API21576/Worker39976，heartbeat正常，后端588全量与最后30专项、前端12/构建/9页真实验收通过，最终指纹8813a6ac65f64705eaf0343fc42d22f5a8d56fe05f201589b566926100df859e。人员/营收/具名上下游仍未知，业务partial；当前没有活动任务。保留旧错误回答用于审计，不能改成成功。

## 研究v3与条目来源统一交付（2026-10-09）

此节取代下文旧quick零模型、regex路由、三个Dock、_02 head的现状描述；旧实测保留原日期。

新消息统一模型意图识别；本地历史与每轮新网络检索融合，经计划→采集→清洗→提取→核验→保存→逐企业缺口评估→补查→最终快照。首轮保留补查预算，暂停恢复不清零；相同事实合并引用，摘要/模型回答不作为企业事实。

Alembic _03为逐轮ResearchDataset，_04为原Evidence文档版本/条目原文片段/强外键绑定。每次保存各来源自身value/metadata/日期/预算/买方引文，实际子公司买方分别绑定；历史回填保留Evidence、业务原值/状态和当前研究元信息，共享年报不伪造不同URL。

前端沿用后来确认的企业综合单页及独立来源卡；工作台消息无气泡、清洗资料入口和真实LangSmith预览，所有可见文字≥14px、Markdown实际Microsoft YaHei。正式8000/API/Worker已重启并到20261009_04；17:41备份`.codex-tmp/research-v3-backup-20261009174124/`。

部署前后53企业/725事实/34项目/15公告/38关系/29任务/363 Evidence数量不变，Evidence与业务核心字段摘要一致，0外键问题；新增67文档/600片段/860绑定。最终live/dist SHA256：`9b39587488b0f7b6bad9fd6e84be5f1f34fe771b84d8ec6641dd181a44a4acec`。

完整后端576通过/140.90s；前端12项与构建通过；来源正式26状态（1672/1440/390）及工作台/结果/设置12页面检查通过，无溢出/页面错误。最终字体小修另有CDP/工作台重验，不把旧26状态说成新构建同一轮。证据：`.codex-tmp/v3-deployment-report.json`、`source-entry-redesign/production-ui-report.json`及其final-font/build报告、`research-v3-ui/`。

真实QA ccfd5d38740a4a94836e86732bed69da：13模型/4新搜索各8来源/47清洗/3接受/真实gap追加2查询进入round2/359910ms/partial。未获取采购公告保持缺口，来源数不等于采购项目；LangSmith云端父子模型/工具可读，预览100条、完整链接可用，输入输出隐藏。

联合日志：`.codex-log/20261009135452_模型驱动研究清洗沉淀与缺口补查链路.md`与`20261009163857_条目来源关联与精简界面.md`。以当前代码/API/原文引用接续，不能沿用旧阶段图或旧测试数字回退实现。

用途：将本文作为开发 Agent 接手本项目的任务上下文。第 1 节可直接复制给接手 Agent；后续章节是执行契约、架构、真实验收记录、待办和复现入口。当前实际运行提示词的完整拼装表达式、主 Skill、全部渠道规则、工具 Schema 和输出契约见 [Agent运行提示词源码快照](../%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3/Agent%E8%BF%90%E8%A1%8C%E6%8F%90%E7%A4%BA%E8%AF%8D%E6%BA%90%E7%A0%81%E5%BF%AB%E7%85%A7.md)。

## 2026-10-09 用户消息与工具耗时核验

工作台用户消息也改为透明、无边框/圆角/内边距，桌面/手机正文16px。回答上方标“总耗时”；工具空检索显示“无匹配结果”，企业保存显示后端实际通过核验项数。TypeScript/Vite构建与Edge四视口检查通过，日志`.codex-log/20261009133855_用户消息去气泡与工具耗时核验.md`，证据`.codex-tmp/user-message-tool-latency/`。

只读实测：最新马尾查询b9702024505c4ef3a3ea8fad21c3a256总121665ms，其中规划模型79953ms、网络40922ms；4次读页正文/hash真实，2次搜索为空，23.906秒慢页是直读ReadTimeout后备用成功5187字。海能验证总112933ms，模型节点105547ms（约93.5%）、网络7093ms，已接受2项资料/关联企业卡。原福州累计351176ms包含两次约90秒提取超时，失败模型不在成功ToolCall/stage_timings里，不能把总耗时当工具耗时。读取成功与主体匹配/入库成功分开判断。未更改模型、缓存新鲜度、读取并发或后端执行；没有新发供应商请求。

## 2026-10-09 企业查询与紧凑工作台修复

企业查询入口已修复：auto模式支持“查询福州船厂的信息”等无公司后缀主体；同会话“都要/确认/继续”等明确短确认承接最近企业请求，原始消息不重写，完整授权研究正文存metrics.research_prompt。页面只显示最多10字的规则短标题，助手正文无外框，输入区提示已删除，聊天和输入间距收紧。

本轮最终544 passed in106.39s、专项31 passed in6.14s、前端两次构建通过；Edge四视口无溢出/pageerror。福州任务e9e733818b78448aa9bd3a6e0ecd69ca曾提取超时，后加正文主体筛选及SDK超时降级，恢复完成3次搜索/6页读取，正文未确认请求主体，最终needs_input询问全称/官网。准确名称任务b3a2f2fd7da5406d8a8c11ec6145d2f7真实3模型/112933ms/接受2事实，已关联Company/ResearchCompany；工作台产物→查询卡→完整画像实际浏览器通过，终态partial保留资料缺口，已有304事实含历史存档。证据见.codex-tmp/workbench-save-fix及.codex-log/20261009093112_企业查询保存链与紧凑工作台修复.md。

## 2026-10-09 当前企业工作台（覆盖下方历史产品UI与暂停状态描述）

用户已明确授权继续完成企业工作台。当前UI为“工作台 / 查询结果 / 设置”，Vue3/Element Plus，视觉入口`web/src/theme.css`；查询横向企业卡片，详情`CompanyDetail.vue`为四指标、基本信息/采购/上下游和AI研判同屏的综合页；原三个Dock已合并。保留`/legacy-leads`销售跟进。

后端沿用FastAPI/SQLAlchemy/SQLite，Alembic1.20.0 revision `20261008_02`。新增六类企业表；`company_service.py`负责投影和原生导出、`company_import.py`负责幂等历史归档、`company_validation.py`负责实时原文/主体/统计/采购事件校验。企业分支`company_query`不要求卖方产品，沿用Worker、ToolBroker、checkpoint和模型预算；增加`fetch_browser`、`persist_company`工具。

专用Edge由固定OpenCLI1.8.8的`web read`经CDP读取，不需要登录或Browser Bridge扩展；Playwright1.62.0备用。安装`tools/browser`的npm锁定依赖，通过`/api/browser/status`检查。原始URL/正文/哈希与读取后端写Evidence，权限/robots/验证码不能因切换读取器而绕过。

当前企业任务证据：隔离任务`9fccd350beb94a66977e645c46daeeb7`，375669ms、8次真实模型调用、120306报告token、partial；正式两企业报告任务`300e8511dbc447ea85c32a34e3e6bf58`，124010ms、4次真实模型调用、42690报告token、partial，排队暂停/恢复后两家公司进入同一会话。前者不是8个任务，`company_updates=40`是字段接受次数而非40个净新增事实。拒绝字段和未知数据保留缺口。

当前本地回归517 passed in90.19s；Edge 1672/1440/390三宽×五视图共15页，无pageerror/横向溢出，实际字体微软雅黑；搜索、统一Dock、来源正文、XLSX下载、两家会话产物已自动验收。证据目录`.codex-tmp/ui-workspace-verified`。真实来源/字段不足的研究终态仍为partial，不代表全部公开网站或采购字段已取得。

正式API与Worker由`start.ps1`运行，监听127.0.0.1:8000；日志按`log/web/<name>-<PID>.jsonl`分流并轮转，隔离DATA为自己的logs。最新接口见唯一`.codex-api-spec/crm接口文档.md`，冻结SQL见`.codex-sql/20261009002500_企业研究工作台增量迁移.md`。下方2026-10-05及更早验证记录保留日期，不作为当前UI/目标状态。

本文不含密钥。它是交接说明，不覆盖当前用户指令、系统要求或模块 AGENTS.md；不会自动恢复暂停目标、启动服务、重采客户或发送销售消息。执行前必须以当前磁盘、接口、进程和数据库核查状态，不把历史记录当当前运行结果。

## 1. 可直接使用的接续任务提示词

```text
你接手的是 D:\Codes\Client-reach，一个已经实现初代的中文 B 端获客 CRM。请在既有代码上继续工作，不另建演示应用，不用模拟数据制造成功。

最终产品：用户在首页介绍自家公司产品或上传 PDF、Word、Excel；项目内的 LangGraph＋gpt-6-luna Agent 分析产品与买家画像，自主搜索多个公开渠道，补全真实客户与公开业务联系方式，逐字段保存原文证据，形成 CRM 线索、跟进与可导出的 Excel。每次发现、补全、评分、反馈和知识沉淀必须可追踪。没有证据的采购、供应商、供货价、频次、人数和营收保持空白。

你是开发和调试者。业务客户发现与分析应由项目 Agent 完成，你读取其回答、Evidence、ToolCall、JobEvent、checkpoint 和模型预算来优化。自主发现验收仅给产品、城市和目标角色，不提供已知客户姓名或 URL；不要自己搜到客户后塞给 Agent，或人工补库，再称 Agent 自动找到。用户明确要求你直接调研时可直接研究，但应单独标注为技术/可获取性调查，不充当自主获客验收。

当前用户未提供企查查、1688 开放平台 API 权限，先用公开信息。模型 Key 和 LangSmith Key 不能用于其他平台。公开索引、成功 HTTP、读到正文、客户字段证据、实际可联系和确认采购是不同层级，不能混用。不绕登录、验证码、robots、付费墙或限流，不解掩码、不补号、不猜联系人、不推断法人本人电话。

保持现有 Vue 3＋TypeScript＋Vite＋Element Plus 前端，以及 FastAPI＋SQLAlchemy＋SQLite 后端。Agent 复用 LangGraph、官方 SQLite checkpointer、LangChain 的模型工具调用和 Pydantic 输出、LangSmith；优先复用现有组件和已核实许可证的开源能力。PostgreSQL、MinIO、OpenSearch/pgvector、Scrapy、Playwright 是可选技术，不要把规划当已经部署，或为追求架构复杂度重做系统。

所有自动字段要有真实 source_id、原文 value、连续 quote 和正确主体/字段语义。主体、城市、买家角色、分店、电话归属、统计口径和采购阶段由后端核验，提示词不能替代核验。同名不同门店不合并，其他公司、平台客服、品牌总部、代理机构的电话不能借给目标客户。

UI 保持白色背景、黑白灰、全站微软雅黑，标题/副标题/正文层级清晰、字号足够、布局紧凑。左侧导航只有首页、客户线索、设置；首页左边放历史与新对话，无历史搜索/时间/矩形卡。每轮回答上方显示该轮真实耗时及可折叠工具过程；详情用操作摘要和来源，不显示 JSON/代码。真实 Markdown＋SSE，停止按钮真正暂停任务，输入框随内容伸缩，上限后才滚动。右侧结果/文件/数据只来自当前对话，不能串会话。删除重复完成说明、工作空间面包屑和无效占位文案。

当前最重要的未完成项：两个有电话的商户仍缺第二网站证据，市场有三网站证据但缺业务联系；部分泛目录读取没有补查收益；真实自主任务仍耗时较长。多电话分类、法定代表人独立字段尚未开发。法人姓名可见于企查查官方授权接口文档，不表示公开网页或 API 已获取成功。先核查这些问题的真实链路，不随意放宽证据或增加任务预算。

先读项目 docs/README.md、README.md、相关模块 AGENTS.md、最新接口文档和交接中的真实任务记录。需求已明确且已授权的修复自主实施；新增多电话数据模型等行为修改先按照既有 brainstorming 门禁形成并确认方案。本轮如果只要求整理文档，不进入业务实现。原生 Codex goal 目前暂停，未经当前用户明确恢复，不自动恢复持续获客任务。

所有验证在本地由 AI 自动执行，无 CI、远程流水线或人工验收。真实 QA 使用 .codex-tmp 下独立 SQLite 和独立 DATA 日志，不污染正式 CRM。保留失败任务、原始 Evidence、旧回答与累计预算，恢复不能清零。测试绿不等于真实多渠道成功，单节点复核、指定 URL 诊断和既有客户续查不能冒称首次自主发现。

每次变更完成相关冒烟和回归；交付前完成本地完整验证及必要的真实浏览器/API/Agent验收。按模块更新 AGENTS.md、接口文档、涉及 DDL 时的 SQL 留痕，并把真实验证规则沉淀到 buyer-research Skill。临时产物只放 .codex-tmp，操作日志放 .codex-log。只读凭据，不把它们打印、复制进 docs 或日志。不要递归删除；需要移除的文件移到同目录 delete 文件夹。Git commit/push、破坏性 schema 修改按当前用户规则确认。

完成标准是完整需求逐项有当前证据，不是“写完代码”“一次测试通过”或“一条线索成功”。报告实际改动、真实结果、限制和下一步；缺证据就继续，不能随便将整个 goal 标记完成。保持中文、简洁、明确。
```

## 2. 用户需求与业务验收契约

### 2.1 首个真实业务场景

卖方销售家居配件，试点产品为家用吊灯、壁灯、吸顶灯；优先深圳买家。目标包含卖灯具的经销商、零售商、家居城/大卖场。产品未指定型号、参数、价格时不得自行编造。明确提供产品后不反复要求确认；没有产品时才提必要问题。

客户字段尽量完整：名称、法律主体、城市、行业、主营品类、经营品牌、地址、人员规模、年营收、联系人/职位、电话、邮箱、公开微信、网站、信用代码、登记状态、近期采购、供应商、采购成交价、采购频次。输出可排序、可联系、可追溯，未知留空；公开业务原值按用户要求展示，不生成私人号码或补齐掩码。

“资料匹配分”不等于成交概率；角色与产品相关性不等于采购意向。采购/供应关系、成交价和频次只能来自明确证据，不用零售价、工程预算、注册资本、经营范围、招聘、融资、品牌代理声明代替。

### 2.2 客户、联系人和多电话边界

- 当前 `phone`、`email`、`website`、`wechat` 是事实字段；电话支持有限的明确并列号码投影 `additional_contact`，并不是已完成通用联系人/多号码模型。
- 联系人姓名和销售负责人 `owner` 分开；法人姓名不自动作为业务或采购联系人。当前 `Fact.field` 没有独立法定代表人字段。
- 微信必须明确微信/WeChat 标签、完整原值和同主体联系块；数字微信不得自动写 `phone`。复制成功不等于账号可添加或已经联系。
- 失效、争议、短号、格式异常保留原文状态，不提供正常拨号/复制动作；号码格式有效不证明接通。
- 最新提出的方向：一个企业保存多个联系记录，并细分企业总机、销售、售后、招商、采购、用途未标注；法人姓名单独保存，法人本人电话须独立明文归属。这个方向仍是待设计/实现，不能写成现成接口。
- 一个号码可有多条来源；相同号码去重不删除证据，不同用途或冲突号码保留各自语义与时效，不简单把全部号码判为互相矛盾。迁移既有事实/人工值/争议/反馈状态时必须明确方案。

### 2.3 多渠道契约

既有公开渠道 ID：`official`、`directory`、`procurement`、`brand_directory`、`mall_directory`、`industry_directory`、`b2b_1688`、`qcc_public`、`ccgp`、`sz_procurement`、`public_registry`，另有本地 `knowledge`。

授权入口 `company_api`、`rfq`、`intent` 尚未接通。渠道状态 `ready` 表示能力已配置，不保证当前平台访问成功或客户产出。渠道最近搜索和网页结果分别从真实账本投影，刷新设置状态不应爬外网。

明确“先查/优先尝试”按当前用户顺序执行，不被画像先提“家居城”或学习配方抢先。当前明确禁止/仅查限定应用到搜索、网页、重定向、缓存和保存；无 API 权限不自动禁止平台公开信息。官网路由不是官网认证，真实平台标签按 URL 确定。

同一客户多站核验按该客户已保存字段证据的不同根域数 `contact_summary.site_count`；同平台子域/移动桌面合并。一个任务读过十站不代表一条客户有十站证明。不同网站也可能转载同一资料，根域计数不证明独立调查或现行经营。

## 3. 当前实现与代码地图

| 模块 | 当前职责及关键文件 |
| --- | --- |
| API | `backend/app/main.py`：会话、附件、任务/SSE、CRM、导出、设置、记忆、知识、渠道、图与checkpoint投影；控制器只编排 |
| 业务与数据库 | `service.py`：候选校验、保存、CRM与原生Excel；`db.py`：SQLAlchemy实体、队列与时间；生产库 `data/app/clientreach.db` |
| Agent 图 | `agent.py`：ResearchState、context/profile/plan/decide/search/read/extract/save/gap/answer/learn、原预算恢复 |
| 模型 | `model_gateway.py`：固定 `gpt-6-luna`、Chat Completions、Pydantic function_calling、任务级调用/令牌预算 |
| 工具 | `research_tools.py`：ToolBroker、白名单schema、幂等工具账本、限速/冷却、访问范围；`gateway.py`：Exa MCP与正文存档 |
| 采集与导航 | `public_directory.py`、`industry_navigation.py`、`public_website.py`、`public_accounts.py`、`public_contacts.py`、`source_policy.py`、`source_access.py`、`source_content.py` |
| 证据与主体 | `evidence_context.py`、`evidence_role.py`、`contact_owner.py`、`contact_view.py`、`statistics_evidence.py`、`procurement.py`、`identity.py` |
| 回答与UI投影 | `answer_summary.py`：从保存事实/账本生成摘要；`tool_views.py`：不显示原始JSON/正文；`channel_status.py`：只读能力和近期状态 |
| 知识与追踪 | `knowledge.py`：持久WorkspaceStore、中文FTS5、产品/证据/反馈知识；`tracing.py`：原生LangSmith且默认隐藏输入输出 |
| 文件 | `files.py`、`document_parser.py`、`document_context.py`：PDF/Word/Excel本地解析、OCR、预览、上限及选择上下文 |
| 前端 | `web/src/pages/Home.vue`、`Leads.vue`、`Settings.vue`；`components/FactValue.vue`、`ToolActivity.vue`、`ResultPanel.vue`；`style.css`集中视觉规范 |
| Worker/生命周期 | `worker.py`：研究/普通问答分别一个槽；根 `start.ps1`/`stop.ps1`：只操作核实本项目PID、保留日志 |
| 运行Skill | `backend/skills/buyer-research/SKILL.md` 与 `references/runtime-playbook.md`；`source-playbook.md`是历史实测，`source-reuse-catalog.md`是技术研究 |

锁定依赖见 `backend/requirements.txt`；前端声明见 `web/package.json`，实际安装与锁文件需复核。当前没有 MySQL/PostgreSQL、MinIO/OpenSearch、账号权限或多租户。早期 `src/`、研究脚本及 PydanticAI 记录不是当前生产获客引擎。

## 4. Agent、记忆与工具执行契约

### 4.1 路由与状态

- 问候/身份是服务端 quick 回答；普通解释/已有结果问答走 `answer → END`，不因历史获客指令自动研究。
- 文件只读问题走 `context → answer → END`，不搜索买家、不更新研究画像；新附件研究须重新分析产品。
- 研究走 `context → profile → plan → decide → search → read → extract → save → gap`，gap按缺口回read/decide或answer，最终learn结束。实际图以 `build_graph` 与 `/api/agent/graph` 为准。
- `ResearchState` 是 `TypedDict`：画像/计划/当前步骤、来源ID、候选/已存ID、缺口、已尝试URL、导航补读、指定页范围、预算、警告及消息等业务值；不存密钥、客户端或数据库会话。
- 官方 `AsyncSqliteSaver` 保存到 `DATA/checkpoints.db`，`thread_id=job_id`；长期记忆在WorkspaceStore/业务库，不能把checkpointer当长期知识库。
- `ToolCall.operation_id`是实际幂等键，成功结构化结果及工具返回可复用。规则升级使用策略版本重验，不清旧错误或证据。终态恢复不是从空状态重新执行。

### 4.2 工具调用与结构化输出

工具白名单只有 `search_accounts`、`fetch_source`、`search_knowledge`、`parse_account`、`persist_lead`。模型决策绑定 `SearchAccounts`，严格单次工具调用；它不是可随意执行Python、登录网站或发消息的通用终端Agent。读取、模板解析、保存仍由图和Broker执行。

Pydantic 主契约：`ProductProfile`、`ResearchPlan`、`CandidateBatch`、`Candidate`、`Fact`、`ProcurementSignal`、`RoleCorrection`、`ResearchResult`。每批候选最多8个、`Fact.quote`3–1500字符；来源S1/S2只能精确映射本批真实ID，不接受猜ID。结构化校验失败仅允许既有一次有界纠正；错误可选字段可省略后全量重验，不改变核心主体/电话归属门槛。

后端最终保存必须验证逐字引文、value子串、主体/分店/地区/字段语义、当前渠道范围。网页中的指令不执行，工具派生导航不能作为Fact引文。模板解析成功也要走同一persist校验，不能把原生解析作为跳过核验的捷径。

### 4.3 检索、恢复、降级与性能

采用已配置的Exa MCP搜索，正文优先受控HTTP＋Trafilatura/lxml；搜索渠道共享供应商，不是假装多个搜索引擎。公开目录入口只授权起点读取，不是客户事实种子；只沿实际可见链接，不猜页码、公司编号或参数。

关键规则：同主体联系导航绑定；满额仅补已选客户；异构名单按已有分店scope保护；网站补查按实际owner和缺口排序；未满额跨站不重复旧主体吃尽搜索；搜索将尽可以先登记目录发现，留原搜索给后来客户。读取预算、访问范围和事实证据不因排序改变。

任务搜索/读取按持久attempts，时间/模型/令牌按原任务累计。失败模型请求占额度、无usage计保守估算；`BEGIN IMMEDIATE`预算事务中不发网络。恢复不退款、不清零、不新建任务隐藏失败。同job连续确认SDK超时才触发熔断；预算触顶/通用超时不冒充模型故障。

有已存结果时预算结束/超时仍反馈真实部分结果；来源或联系不足标partial。搜索供应商限额不等于网页站点受限；无可用正文不生成企业Evidence。尊重全局供应商/站点冷却，不通过换供应商绕站点robots、登录或验证码。

性能必须测量：提交至首答、模型TTFT、逐节点/逐工具耗时、累计时长、模型次数/令牌、无增益读取和修复次数。历史任务约350秒，不能说已达到稳定响应指标；用户尚未约定数值SLA，不擅自将“10秒”之类写成验收通过标准。

### 4.4 知识飞轮

产品画像/偏好/排除项只来自用户资料。客户知识来自真实字段证据且带期限；助手总结不能升级为企业事实。反馈 `relevant/nonbuyer/incorrect/stale`改变知识/资格/联系状态，并防旧缓存复活已纠正事实。渠道配方仅同地区同品类，以有效线索和反馈归因排序；真实learn重放按客户ID去重，不覆盖当前明确平台优先级。

### 4.5 回答与流式

正常模型使用真实 `astream`；SSE通过事件ID可重放，按 `message_id/generation_id`归并，`message.reset`先清草稿再delta/completed。确定性摘要一次输出完整真实内容，不伪装模型逐字token。

普通多站研究用 `verified_corroboration_summary`逐客户列实际网站数/不足；同渠道成功读取与失败并存时用 `verified_process_summary`保留两者。零结果、漏联系、确认SDK熔断、预算停止有各自分支，不能都称熔断。解释、比较、指定页复核仍保留模型回答；生成模式记录在metrics。停止为真实paused，不能只关闭浏览器EventSource。

## 5. 前端、CRM与文件解析验收

前端视觉契约：白底黑白灰、不用绿色；统一 `Microsoft YaHei`，标题28px（窄屏24）、二级20、三级18、正文16、控件15、密集表格14、辅助最低13，字重/大小以当前style.css为准。首页无重复面包屑/“工作空间”/重复完成卡；历史只有文字标题与新对话。

每条助手回答显示其自己的累计耗时，不取全部会话最新任务；耗时和工具位于回答上方。工具真实、默认折叠、无固定卡片，展开是人话命令/摘要/来源。输入44–220px自动伸缩、中文组合输入和Shift+Enter可用。右侧结果/文件/数据是同会话实际记录，异步epoch/job/连接守卫防串会话和旧响应覆盖新任务。

CRM支持分页筛选、状态、负责人、标签、下次跟进、跟进、反馈、软归档、原生Excel。编辑只PATCH有变化字段，不把未改公开事实变成人工录入。详情/列表/结果面板共享FactValue，GET有效性投影不能写回facts；PATCH响应不承诺含GET派生contact_summary/copyable，需要刷新GET。

文件实际支持PDF、DOCX、DOC（LibreOffice转换）、XLSX、XLS。pypdf/python-docx/openpyxl/xlrd负责解析，RapidOCR＋ONNX Runtime处理图片/扫描页；Poppler/LibreOffice为本机外部依赖，不承诺其他电脑自带。

已有上限：文件10MB、解压50MB、总提取12万字符、PDF100页/OCR最多10页、每Excel表1000行30列、每附件进入模型最多2万字符首尾/相关块。必须报告实际截断/OCR/公式缓存情况，不称完整分析未读部分。空表/页签/占位符不能冒充正文；公式缺缓存不能生成数字。未知附件/解析失败保留原错误，不用旧画像凑回答。

UI验证必须真实浏览器/API，桌面1440×960及窄屏390×844检查三页/详情浮层、Markdown流式、停止/恢复、上传和结果一致性。代码编译不能证明可用；不得点击拨号/发信来证明联系号码存在。

## 6. 已验证记录与当前状态

以下历史数字来自项目日志和隔离任务，日期固定，不承诺今天仍同样运行。2026-10-08本次仅做文档核查，没有重新跑504项测试或启动业务Agent。

| 项目 | 证据与结论 |
| --- | --- |
| 最后完整后端验证 | 2026-10-05：504 passed in66.80s，详见 .codex-log主记录（历史引用，当前本机未找到原件）；不代表所有外部平台或业务指标完成 |
| 最新无名/无URL自主任务 | `ac942f90c91e4499b7ebcd5d2ccc195f`；QA库 `.codex-tmp/multisource-7f35310839d441d6ae3a9d887bc8b088/clientreach.db`；partial、349605ms、21模型、8搜索、16读取；3线索、2完整电话、网站数3/1/1 |
| 当前仍缺什么 | 市场无联系；两个有电话商户单站；采购/营收/人数/供应价/频次未知；泛品牌/分店目录有无增益读；耗时较长 |
| 网站计数修正的真实验证 | 原answer误说全部1站；后仅answer_node复核21→21、正确3/1/1，原整图答复/partial恢复；这不是新整图成功证据 |
| 微信续查样本 | `f1a6721b4ae24de9b50128fb319f9927`；QA库 `.codex-tmp/multisource-6722374e02a94d7e8b8d959dc177a252/clientreach.db`；completed、22847ms、3模型、已存客户2根域且仅wechat可用，phone空；不是首次自主发现 |
| 2026-10-05部署 | 最后记录API35092/Worker5780、health正常、188日志无真实Key；备份 `.codex-tmp/production-20261005101234.db`；旧PID只作历史，不能据此杀进程 |
| 2026-10-08只读现状 | 生产库10条（包含归档行）、queued/running/cancelling任务为空；health请求未连通，具体服务/网络失败原因未诊断，不称已运行或崩溃 |
| 原生Codex目标 | 2026-10-08读取状态paused，原完整目标未complete；必须由当前用户恢复持续执行，不因交接文件自动恢复 |
| 版本控制 | 当前根目录不存在 `.git`，不要反复git status或未经要求初始化仓库 |

真实导出：

- 20261005_Agent自主深圳灯具三条线索.xlsx（历史引用，当前本机未找到原件）：项目原生导出、3线索2电话，三表及逐字段证据，不是采购客户确认名单。
- 20261005_Agent深圳灯具客户_公开微信.xlsx（历史引用，当前本机未找到原件）：真实既有客户续查结果，公开微信与电话分开。

QA未并入正式10条，不能为了数量指标手工合并。旧失败/争议和旧Excel不可改成成功以掩盖问题。

## 7. 企查查法人及多电话的最新调研边界

用户2026-10-08要求“先不要调用Agent，你自己先搜索”，该授权限本次可获取性调查，不能据此把以后自主获客改成人工代搜。

实测：Exa三查询都返回免费额度限制，0新搜索结果；直接读取 [企查查官方886文档](https://openapi.qcc.com/dataApi/886) HTTP200，字段 `OperName`明确为法定代表人姓名，另有Name/CreditCode/StartDate/Status/No/Address。它允许电话作为搜索条件，返回字段列表没有电话，不能说该接口提供法人电话。

官方接口要求独立AppKey、Secret、Token、企业实名及场景审核。未调用收费API、未获平台权限。410与2001文档读取ConnectTimeout；具体企业页面/多电话能力本轮未验证。详见 .codex-log企查查核查（历史引用，当前本机未找到原件）。

多电话下一阶段建议先确认数据契约：每条号码原值、类型/用途、联系人/职位、来源URL/连续quote、公开日期/采集时间、核验状态、是否历史；法人姓名独立公司字段。明确电话用途才分类，否则“用途未标注”，不因法人姓名相邻或企业有号码就认作法人手机。此模型未实现，也未授权自动拨号、加微信或发消息。

## 8. 接续执行顺序与待办

1. **核实环境**：目标是否恢复；相关AGENTS/依赖/当前代码；8000接口与进程是否存在；生产/QA库和已有任务是否终态。不要重跑一个尚在运行的任务，不凭旧PID/锁文件判活动。
2. **读真实失败链**：从上述ac942任务读取最终答复、ToolCall、Evidence和预算；识别已存主体未核第二站的具体原因、后续无增益读及耗时瓶颈。不要直接注入已知客户URL。日志中的早期“进行中”以该章节最终终态及数据库为准。
3. **继续优化自主多站补查**：按主体/分店/已用网站/联系缺口筛目标页面，降低泛品牌和同站分店列表耗费；研究搜索结果相关性、渠道目的与主体绑定，但不降低资格/来源证明，不增预算掩盖失败。
4. **完善丰富联系资料**：用户确认多电话/法人数据契约后再实现后端Pydantic、事实校验、存储/迁移、API、知识反馈、CRM、Agent回答及Excel整链；公开法人姓名与联系人岗位分开。未获API权限时保持公开渠道与待授权状态。
5. **验证速度与回复正确性**：普通问答/文件问答不启动研究；反复发送问题测首答及停止恢复。验证自由回答与确定性摘要各自职责，多站准确不意味着所有解释都准确。
6. **扩充来源与开源研究**：API/软件文档用Context7，无浏览器搜索用已配置MCP；报告搜索限制，不擅自改浏览器搜索。核实仓库许可证/SDK/实际返回再复用，技术文档不当客户Evidence。已下载不等于已集成，AGPL/SSPL等不当自由闭源组件。
7. **隔离全链验证**：无名URL自主新任务、已存续查、指定页面诊断、原文节点复核分别标类型；验证多条可联系主体的实际证据。当前Exa额度问题应先核真实状态，不能轮换账户/参数绕限制。
8. **交付并沉淀**：相关/完整本地测试，必要前端build与真实UI，日志/AGENTS/Skill/接口/SQL同步；正式无活动任务后备份再重启，检查真实health/Worker心跳/密钥泄漏。目标完成审计仍按原完整范围，不用一条样本代替。

若没有新授权可做的实现，交付已核实事实和具体缺口，不自行变更范围；普通文档任务完成不等于恢复或完成长期获客目标。

## 9. 可复现命令与诊断入口

这些命令由接手 Agent 在对应任务已获执行授权后使用。本次整理未运行其中的模型、重启或完整回归命令。

```powershell
# 无网络的本地回归：必须在backend工作目录，否则app导入可能失败。
Set-Location D:\Codes\Client-reach\backend
.venv\Scripts\python.exe -m pytest -q

# 相关后端回归，按本次变更选范围。
.venv\Scripts\python.exe -m pytest tests/test_research_schedule.py tests/test_cross_site_owner.py tests/test_channel_summary.py tests/test_contact_answer.py tests/test_wechat_contact.py -q

# 前端检查，build内含vue-tsc。
Set-Location D:\Codes\Client-reach\web
npm run build
```

```powershell
# 只读某个真实QA任务已存最终回答/指标；UTF-8避免控制台误码。
Set-Location D:\Codes\Client-reach
$env:PYTHONIOENCODING='utf-8'
& backend/.venv/Scripts/python.exe .codex-tmp/inspect-agent-reply.py .codex-tmp/multisource-7f35310839d441d6ae3a9d887bc8b088/clientreach.db ac942f90c91e4499b7ebcd5d2ccc195f

# 健康仅证明本次返回，失败需核进程，不自动判崩溃。
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health -TimeoutSec 3
```

```powershell
# 真实自主验收：会产生模型/公网请求；脚本新建独立QA库，不写正式CRM。
# 启动前先阅读脚本，确认当前服务/配额/权限与任务需求，不重复已有活跃进程。
Set-Location D:\Codes\Client-reach
$env:PYTHONIOENCODING='utf-8'
$env:CLIENTREACH_VERIFY_MAX_LEADS='3'
$env:CLIENTREACH_VERIFY_MAX_READS='16'
& backend/.venv/Scripts/python.exe .codex-tmp/verify-multisource-agent.py '我们销售家用吊灯、壁灯、吸顶灯。请自主寻找深圳经销商、零售商和家居城，最多3家。先尝试1688、企查查公开信息，不足换行业黄页、品牌网点、商场目录和企业公开网页。每个客户至少两个不同网站核验；公开电话、微信、邮箱、联系人、地址、主营只取明文及真实归属。未知采购、供应商、价格、频次、人数、营收留空。简洁列结果及缺口。'
```

`.codex-tmp/review-agent-discovery.py`会调用项目回答节点、临时将QA任务置running，沿原预算且finally恢复原终态/答复；不是纯只读，不与同库活跃任务并发，不当新自主发现。`verify-existing-contact-followup.py`是既有主体续查，不能替代无名URL验收。

```powershell
# 部署前验证必须顺序执行，失败立刻停止；不可无条件拼接check和stop。
Set-Location D:\Codes\Client-reach
& backend/.venv/Scripts/python.exe .codex-tmp/deploy-procurement-check.py
if ($LASTEXITCODE -ne 0) { throw '存在活动任务或备份失败，停止部署' }
# 仅在上述检查通过且本次确需部署时执行。
& ./stop.ps1
& ./start.ps1
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health -TimeoutSec 3
& backend/.venv/Scripts/python.exe .codex-tmp/check-secret-logs.py
```

正式API/Worker由start脚本隐藏启动，监听127.0.0.1；日志保留`.codex-tmp/runtime/archive`与lifecycle。脚本确认API和新Worker心跳后才算就绪。不承诺客户端升级期间服务常驻。

核心API用于核查：`GET /api/health`、`GET /api/conversations/{id}`、`GET /api/jobs/{id}`、`GET /api/jobs/{id}/events`、`POST /api/jobs/{id}/pause`、`POST /api/jobs/{id}/resume`、`GET /api/jobs/{id}/state`、`GET /api/evidence/{id}`、`GET /api/leads`、`GET /api/leads/export`、`GET /api/channels`、`GET /api/agent/graph`。请求/响应以 [.codex-api-spec/crm接口文档](../../../.codex-api-spec/crm%E6%8E%A5%E5%8F%A3%E6%96%87%E6%A1%A3.md)及实际main.py为准，不能根据本列表猜参数。

## 10. 数据、密钥与日志管理

- 凭据只从 `D:\Codes\Client-reach\config\apikey.txt` 或现有配置机制只读加载；文档仅引用路径，不输出值，不把模型Key冒充LangSmith/企查查/1688Key。配置存在不等于连通成功。
- SQLite在线备份用一致性backup；完整恢复还需checkpoint、上传文件、知识与OCR依赖，单业务库备份不等于完整工作空间备份。不要直接复制活跃SQLite主文件忽略WAL。
- QA设置 `CLIENTREACH_DATABASE_URL`、`CLIENTREACH_DATA_DIR`指向独立`.codex-tmp`目录，并在导入app前设置；QA日志写独立DATA/logs。真实QA不得用正式库代替；不要把临时合成数据或人工试验混入正式线索。
- 原始Evidence、失败账本、manual_fields、冲突alternatives、失效与反馈都保留。人工字段不能被自动提取覆盖，归档主体不能因搜索复活。
- 对用户的来源信息可按授权展示真实公开业务原值；普通调试日志不记录密钥、完整电话号码、上传原文或网页正文。输出错误类型/安全栈位置/ID/计数/时长，不打印环境全量。
- 开发日志放 `.codex-log/`；多渠道开发继续维护主记录，新的独立任务按用户日期规范留一份日志。接口维持唯一 `.codex-api-spec/crm接口文档.md`。新增/改表写`.codex-sql`，破坏性变更按当前授权处理。
- 子模块改前读AGENTS、完成后更新；Skill差异审计有实测稳定经验再反向维护，不为流程空改。全局memories仅用户明确要求才写，不把项目交接请求理解为更新全局记忆。

## 11. 完整目标与完成审计

原生目标原文：

> 扩充Client-reach多来源获客渠道：持续调研1688、企查查及公开信息/采购平台和相关开源爬虫、授权数据源，核实可访问性、真实返回及复用边界，将已验证接入与渠道规则沉淀到买家研究Skill；优化搜索与CRM结果展示，提供可供销售联系的真实企业信息、公开业务联系方式、来源与时效，缺失项不捏造；完成本地自动化及真实多渠道验收后才标记完成。

完成前逐项确认：

- 当前需求范围/最新用户方向都覆盖；暂停未被擅自恢复，授权接口仍按实际权限；多电话方向不能当已经实现。
- 产品介绍和PDF/Word/Excel上传能真实解析；问答/文件/研究路由准确，前后端/DB完整连通。
- Agent从产品自主取得客户，实际多渠道尝试/正文/同主体证据可核查；有缺口能换渠道，不靠手动种子造成功。
- 多个可联系客户的主体/号码归属、地区、分店、角色和来源时效都可审计；客户名和号码无编造/补齐。
- 原要求的网站数逐客户达标；若仍缺来源、联系或关键验收，结论partial而非complete。历史采购不计当前意向。
- 性能、错误恢复、自动降级、SDK熔断、预算终止、停止恢复及重启恢复有相应真实或本地故障验证；验证范围与结论匹配。
- Markdown/SSE、耗时、工具折叠、历史、输入伸缩、右侧分屏、CRM编辑/反馈/跟进、导出及字体布局在真实UI可用。
- 原生Excel从Agent保存结果产生，逐值/证据/空值/冻结/筛选校验；不能仅看文件存在就称完成。
- 本地相关及完整测试、必要build/真实Agent/API/UI、文档/AGENTS/Skill/SQL/日志一致，密钥未泄漏，正式数据未污染。

有任何项缺当前证据就保留未完成；“504测试通过”“一次读取企查查文档成功”“有两个电话”均不能支撑完整完成。接续时每轮交付实际推进和具体剩余项，不把旧状态复述当进展。

## 12. 提示词维护与文档使用

当前提示词不集中在单一文本文件：`model_gateway.structured`公共系统约束＋各图节点动态prompt＋buyer-research主Skill＋启用渠道运行规则＋Pydantic/tool schema＋本轮用户/证据上下文共同组成。不能只改本文就认为模型生效；本文件和源码快照均不是运行时读取文件。

需要修改运行行为时，先定位并读实际节点/规则/后端校验，再小步修改和验证，更新源码快照及其SHA-256清单。避免将本文的历史客户名、测试网址、长日志或开源文档注入每轮规划，这会把调试种子混入自主发现。

接手 Agent 的第一条更新应说明当前已核实状态、下一步依据和必要权限边界；最终交付中文说明变化、真实验证和仍未通过事项。所有步骤使用AI可调用工具完成，无需用户手动帮忙验证。
