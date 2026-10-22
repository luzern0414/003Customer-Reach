# 页面约定

- 2026-10-10：上下游名称导航到`/companies/:id/relations/:relationId`，详情分为关系证据与对方独立企业资料。交易方向/报告期从API取值，不复制主企业介绍、不从对方产品推交易标的。
- Home候选卡绑定对应原Job，仅最新needs_input可确认；补全称/地区单独提交identity-confirmation。epoch/Job ID/revision守卫、同请求token重试；普通聊天输入不暗中作为确认。
- 跨1280px断点同步结果栏状态，避免桌面浮层遮挡390px候选按钮；页面、候选卡、来源链接可见文字均>=14px。

- 2026-10-09提速：工作台回答不显示“查看运行链路/查看清洗资料”，资料保留右栏折叠入口。首批答复和最终答复按generation reset替换；过程事件只更新工具行，persist完成/状态变更再刷新真实产物，减少无关GET。查询结果后端分页前按updated_at降序。
- 最后收尾：首批时间在回答元信息同行，不能重新拉开正文空白；泛化“新研究”标题在单主体真实产物加载后回退到其真实简称/原名，不使用静态企业名。

- 2026-10-09每轮可打开其数据集，selectedResearchId不替换正在执行Job；epoch与请求token防迟到覆盖。LangSmith按真实可读状态展示，截断预览给完整链接。
- 工作台双向无气泡、16px正文，可见文字至少14px。Markstream默认系统字体须在theme覆盖子节点；同时查computed style和CDP平台字形，不能只查父容器。

## 条目来源卡片（2026-10-09，Codex）

- CompanyDetail所有事实/关系/项目/AI依据入口传完整条目，不能只传source_ids[0]。companySources.ts投影名称、金额、报告期及evidence_refs，项目下公告独立成卡，原站URL保持原参数。
- 同一真实年报可共享文档，但每家关系绑定自己的证据；全文仅显式读取。文档入口以当前company_id限制关联条目，默认8项再展开。
- 来源列表/文档/完整片段/归档全文共用sourceVersion守卫；关闭/切企业/新选择均废弃迟到响应。所有可见字体>=14px，移动grid使用minmax(0,1fr)防止长主体撑大轨道。

- 公开业务微信独立表单/列表/详情字段，右侧结果同FactValue。仅变更PATCH，不把数字微信写成业务电话，不把公开联系标成采购确认；联系方式有效性仍由后端决定。2026-10-05真实Agent终态22.8秒位于该轮回答上方，Markdown/来源/2网站4页面核查完成。

2026-10-02，Codex，继承web/AGENTS.md。
- Home左侧桌面常驻历史/新对话，手机从左侧抽屉打开；不显示搜索、时间或矩形历史框，不造样例。
- 助手消息按reply_message_id关联自身Job；历史耗时不能全部取最新Job。当前Job/当前会话jobs需同步，实时工具用operation_id合并started/finished/reused。
- 每次异步会话/预览请求持有epoch，切换后忽略迟到响应；新建会话不停止其他会话后台任务。
- 附件按钮打开后端真实解析原文/警告，已发送附件通过conversation.attachments恢复文件名。部分解析不伪装为全部完成。
- 耗时和工具放各轮回答上方，停止按钮调用真实pause并等待paused，不能只关SSE。未知历史耗时显示—。
- 右侧聚合同对话结果；切换/上传/预览有独立版本守卫，防迟到结果污染当前对话或锁住新输入。Settings读取/tracing只显示状态不收集Key。
- send入口也检查uploading，不能只禁按钮（Enter会绕过）。结果请求签名包含任务状态/更新时间，lead_ids不变也刷新补查事实。
- Leads列表、详情、来源各有请求版本守卫。反馈新增标签合并进当前表单，不能保存时删掉新反馈标签；保存/跟进迟到响应不切回旧客户。
- 用户/助手Markdown共用configureMarkdown：官方markdown-it加MIT CJK插件。markstream内部markdown-it-ts没有inline.State，不能直接对它注册CJK插件；通过customMarkdownIt返回标准解析器。HTML关闭，代码/转义/表格不能为消星号而改写。
- 打开历史先用conversation已有elapsed_ms初始化计时，再请求job详情，避免已完成回答短暂显示0秒。
- action的POST等待也计入busy，禁用重复继续/停止和输入发送；先应用POST返回真实状态再读详情。切会话/新建时清acting，迟到finally只能操作原epoch。
- Leads导出使用成功加载列表时保存的appliedQuery；尚未应用的q/city草稿不能改变导出范围。详情和右侧结果共用事实/公告组件，失效值不展示为正常联系方式。
- SSE回调除epoch还须检查jobId与连接身份；终态GET等待中允许新轮次，但旧GET不得覆盖新job或正在POST的send/resume。终态GET失败有界重试，原流文本保留。
- 结果签名仅整批成功或404后保存；临时失败保留已显示行并最多重试两次，404归档行移除。api错误保留HTTP status供此判断。联系事实有口径/日期/替代值时，即使正常也显示元信息。
- send在POST前固定sentFiles快照，请求和临时消息用同一组ID；busy期间附件不显示关闭按钮，close处理器仍检查busy，防程序触发绕过。POST失败保留待发附件。
- Leads人工表单区分客户联系人/职位与销售负责人；仅发送有改动字段，不能抹掉未改公开事实引用。列表显示邮箱、原文电话和状态，详情联系入口依contact_summary，未知信用/登记字段保留空值。
- Leads表单的事实元信息组件也要传phone/email/website类型，确保其他公开号码可用且遵守父事实失效守卫，不仅结果面板支持。
- Settings渠道开关仍按能力status控制，最近检索/网页结果只读runtime分开展示；最近成功不写平台可用/电话验证，不因冷却到期显示恢复。状态时间来自后端记录并放title，无卡片/彩色标签；刷新不额外爬取外部网站。
- 联系方式列复用FactValue，同时显示短号/异常提示；存在有效电话时失效邮箱仍标状态，不能只靠整体“有联系入口”覆盖单字段失效。

## 企业详情页面约定（2026-10-09）

- 详情切换company_id时关闭来源抽屉、递增sourceVersion并重置展开/补查状态；迟到的补查POST不能把用户导航回旧企业会话。
- 上下游默认使用后端relation_summary对应最新报告期，金额/占比null展示未披露；不同年度或币种不能由前端求和。

- `QueryResults.vue`的卡片分页、搜索和会话筛选只读取`/api/companies`；取消旧请求后才接收新结果，空值保持未取得。
- `CompanyDetail.vue`改为综合单页，共享header并同屏展示基本信息/采购/上下游/AI；来源抽屉读取真实Evidence，继续研究失败重试保留同一幂等token。

- 2026-10-09综合页：保留全部项目规格、建设计划、品牌应用、关联主体与全部事实的折叠入口；三Dock只在历史文档留存。关闭来源抽屉即递增sourceVersion；企业切换同时取消详情请求并清空产品匹配准备。
- 2026-10-09上传资料响应的解析元数据为`parse`，不是`parse_info`；展示warnings/truncated，选择器只能给后端支持的格式。匹配明确绑定当前持久企业ID，不由文本相似名称猜目标。
- 2026-10-09 Home的research_summary更新需先判断job非空；两个可选ID都是undefined时相等，不能据此向null写属性。没有任务的历史会话也要浏览器回归。
- 采购需求、建设计划、品牌应用线索使用不同record_kind；金额/币种/报告期由后端返回，组件不可从标题或名称推断。
- Home紧凑研究标题直接使用后端统一短标题；提交返回metrics.conversation_title立即同步，不在前端截取原始问题。企业阶段标签覆盖company_*；查询入口只显示已保存companyResults的数量，不在聊天底部重复堆数据覆盖说明卡。
- 用户与助手都使用直接文字流；移除用户.user-content气泡必须同步760px断点padding，保留原始消息/附件/Markdown与角色标识。“总耗时”为Job累计执行，ToolActivity行才是单操作/多attempt累计时间。
