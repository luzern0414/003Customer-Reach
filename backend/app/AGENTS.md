# Agent与CRM模块

## 招投标情报、记忆与标识（2026-10-10，Claude）

- `tender_intel.py`在`company_resolve`与`company_plan`之间执行，只在请求采购/上下游字段或未指定字段时运行；`CLIENTREACH_TENDER_ENABLED=false`关闭（测试默认关闭）。外部调用一律经`Ledger.run`落ToolCall并推送tool事件，同Job同参数完成后复用。
- 角色只按原文标签/适配器原始buyer、winner字段判定；`acq_query._notice`会把推断角色写回buyer/winner，平台结果必须改用`out.raw`原始字段，不要直接信任归一化后的winner。
- 解析器（`tender_parse.py`、`tender_html.py`）是纯函数，新增站点先存真实页面到`tests/fixtures/tender/`再写测试；遮挡值不取，引文取连续原文。
- 记录键`title_key(title, company)`去企业名前缀/类别/平台后缀；高置信度（detail>listing>index）不被低置信度覆盖，未识别角色的详情只补字段。展示层`tender_view`再按同键合并历史粗键。
- 招投标关系与年报关系分表存放（`tender_relations`/`company_relations`），次数不是金额，界面与回答都需注明口径。
- `search_memory.learn_from_job`、`tracing.record_quality`、`logo_service.refresh_logo`在`finish`后的后台线程执行，失败只记日志；学习按`learned_jobs`幂等。
- 企业标识只从已核验官网/工商官网/首页含企业名的候选站取；`/logo`接口必须保留`CSP: sandbox`（SVG可能内嵌脚本）。
- OpenCLI只用`vendor/opencli`内置定制版（插件经`OPENCLI_PLUGIN_DIRS`从`src/opencli-plugin`加载）；修改内置包须同步`vendor/opencli/NOTICE.md`。
- 新外部来源先在`site_guides.py`登记能力/重试/质量规则；外部调用经`Ledger.run(model=…, policy=retry_policy(…), reuse_days=…)`，输出必须有Pydantic模型。
- `save_snapshot`中年度关系行变量为`saved_relation`，不得复用`relation`（父关系）；对手方不得绑定到本企业自身；原文写明“本企业是对方子公司”的子公司关系拒绝入库，历史数据在详情投影中过滤。
- Exa失败的兜底检索在`web_search.py`/`tools/browser/search-edge.cjs`，结果只保留原始地址；测试默认`CLIENTREACH_SEARCH_FALLBACK=false`保持离线。

## 独立上下游与主体确认（2026-10-10，Codex）

- `relation_service.py`提供方向/原因/稳定关系地址，`counterparty_profile`只读对手方自己的verified事实和来源；组合披露不能绑定单体，未知交易产品不从主营推算。
- `company_identity.py`位于context与plan之间；简称映射唯一才自动补名，模糊名称先确认。候选仅存在Job/identity数据集，全文与连续原文门禁不弱于事实；候选地址/行业必须有本主体归属。
- `identity-confirmation`校验会话、候选revision、token和活动冲突，恢复原Job/checkpoint/累计预算。`name`和`context`分开；只补地区仍沿原名消歧。resolver尚未结束的恢复不能接collect后继。
- 对手方补查沿原Job，`counterparty_states`记录每家公司下一阶段、来源和待分析队列；片段正文从Evidence读回，暂停后优先处理已归档资料，再检查新增网络额度。explicit-only终态恢复回到counterparties。
- `save_snapshot(relation_id=...)`校验真实父关系授权，同名信用代码冲突整事务拒绝；对方主营/地址等不能仅凭报告出现名字授归属。同语义重复关系同步身份绑定，不污染主Job.company_ids。
- 当前请求字段已核验齐全后停止继续分析其余历史片段，未分析归档保留；完成某范围不代表年报全文研究完成。

## 马尾查询提速与可靠性（2026-10-09，Codex）

- 独立搜索两路并行，供应商槽在预算预留前；`parallel`异常时取消兄弟请求并有界清理。`pending_cleanup`持久阻止立即恢复重发，新Worker解除旧进程标记。线程保存用shield，提交与来源绑定完成才展示成功。
- 清洗摘要先写ResearchDataset pending任务，Worker单个maintenance线程批量重放；摘要整理后仍has_full_text=false。checkpoint只存原文片段定位，所有配置片段保留待处理；官方async durability与下一节点重叠写，业务副作用独立幂等落账。
- company-evidence-6：买方、项目号、数量、日期各用连续原文；ground_batch只绑定实际完整身份/省略不可核验可选项目字段，原始提议与修正记录均保留。24:00不推算次日，下载/计划发布不是实际发布日期。未知金额/供应商不补造。
- 马尾公开入口经真实读取登记，只供导航，不作为事实种子；新Job仍模型意图和新网络搜索。正文中的集团页尾电话、视频标题、采购设备及未来拓展不能作为本主体联系方式/已有产品。
- 同买方、真实截止/发布日期、原始相同或明确包含的标题才合并跨域转载；缺日期不凭相似名称合并。明确研究的既有关联Company提升为primary，避免保存后被查询筛选隐藏。
- 日期/时钟精度由原文补齐；同一已核项目公告的原始长短标题不增加事件。旧重复行以payload.duplicate_of保留，API计数/详情/导出只投影主记录，引用与来源绑定各自保留，不删除历史。
- 首张非identity核验事务记录first_verified_result_ms；首批确定性答复记录first_answer_ms，最终用新generation替换。企业原名直接查询用结构化摘要，不能把首页新闻/下载起始日期写成公司介绍日期。

## 研究v3联合交付（2026-10-09）

- 每个新Job通过真实模型intent，原始用户Message/Job.prompt保留；同Job成功决策可恢复复用，跨Job不跳过识别。company_match操作范围限定document。
- Company链为intent→local context→plan→collect→clean→extract→validate/save→gap→补查/answer。首轮保留一半搜索额度，逐企业检查缺口；新研究尝试网络，历史复用与新取得分开标记。
- ResearchDataset沉淀摘要/全文清洗、连续片段、未核验提议、接受/拒绝、缺口和最终快照。搜索摘要pending/has_full_text=false；失败/未分析片段保留，恢复预算不清零。
- company-evidence-4对同主体/字段/周期/口径/单位的JSON数字与文本数值去重，零值保持零；争议不复活。引用只折叠排版空白，不改变标点/大小写。
- evidence_citations按每次实际source保存各角色quote和url，不能借旧metadata。save_snapshot结束flush后对主公司与实际子公司买方分别bind_company_sources，同事务，不自行commit。
- llm_request从请求开始即落账，失败/暂停耗时与首块时间保留；节点finally记录node_timings/失败事件。LangSmith真实读取后才available，预览最多100条并显式truncated/完整链接。

## 文档与条目来源（2026-10-09，Codex）

- source_models.py定义SourceDocument（一对一Evidence版本）、SourceFragment、EntrySourceBinding（事实/关系/项目/公告强外键且恰一种）。原始Evidence不可变，不能按相同URL合并不同正文版本。
- source_service.bind_company_sources(db,company_id)同步幂等、不commit，在save_snapshot/import_history同事务末尾调用；异常随原事务回滚。source_citations按source_id+quote+role追加，显式映射覆盖旧字段fallback，不给新来源复制旧metadata。
- 连续片段定位只折叠空白并要求唯一；历史年报关系只有同一原始行具名且金额/占比全部吻合才回填原行。人工页码、合并摘录和重复句不能生成定位。仅真实PDF PAGE标记产生page_url。
- company_detail批量投影evidence_refs（<=800字符）；关系去重必须合并全部refs。company_document限定当前企业来源，片段/full Evidence为显式读取入口，不将清洗分块当事实引用。
- _04冻结DDL并迁移回填；db.initialize排除三个source表以避免create_all提前建表。降级恢复一致备份，不自动删表。

## 企业综合页与产品匹配（2026-10-09，Codex）

- `company_match`为MessageInput的明确操作类型，必须有持久company_id及1..5个已解析附件；真实模型仍识别意图，intent_node按用户操作限制document，不因模型误判扩大到公网查询。记录model_intent和operation_scope，不能伪称模型正确选了路径。
- 只有document+本轮附件+目标company_id才由company_match_context追加有界企业事实/计划/来源；纯文件问答、普通聊天和企业公开查询沿原路径。资料局部取样范围须保留，模型分析不写CompanyFact、不做learn。
- `company_detail.purchase_analysis`只读取本企业有company_match_context的completed/partial真实任务回复；不存在返回null，不从助手文本解析新事实。保留分析时间和source_as_of，不将历史分析当最新已确认意向。
- 明确同年01-01至12-31/06-30收入区间才识别annual/half_year；单一截至6月时点或跨年区间仍as_of。

- 普通research明确多站要求时verified_corroboration_summary直接用保存事实/每客户site_count及缺口生成终答，不让回答模型把3/1/1概括为全1。解释/复核/比较保持原模型流程；同渠道混合失败优先verified_process_summary，网站要求与原预算仍保留。真实ac942无名URL3客户/2phone/站数3,1,1，answer节点修后预算21→21复核准确，原自主错误答复不重写。

- 2026-10-05异构名单：满额matches_branches只按已知乐安居name scope筛该平台分店，不要求所有异站客户都有scope；全未知/未满额/用户明确URL仍原契约。prioritize_websites可选sources用原website_links重新绑定owner，仅原启用链接排序，不以A链接补B网站数；无联系客户不阻塞其他有联系客户独立站排序。
- 跨站未满额已查主体不重复抢补查搜索；剩余搜索<=未满客户数且明确平台前缀已尝试时，可提前读取实际登记目录，同轮一次、attempts/读取/模型预算不增。满额继续按原最少次数主体补查。
- answer_summary.read_pages复用has_content/factual_body核真实正文，返回最小元信息，不含body；empty_summary只能用该投影称已读取。channel_summary从同job账本保留摘录/正文/部分失败；普通research有混合成功/失败时verified_process_summary走原reset/delta/completed，无新回答模型，不是SDK熔断；解释/原文复核/比较/chat/document保持原回答。

- answer提示提供当前required_sites，实际每客户site_count不被本任务总读取网站数替代；部分平台读失败后成功不能说整个平台无正文。saved_summary新增site_target默认1，联系漏项回退/SDK熔断/预算与异常降级均传原要求，有多站不足明确一行缺口。真实4e5867自主18调用后两次answer复核18→19→20不作新获客，原答/终态恢复、预算仍累计。

- requested_channels明确“先/优先尝试或查”优于画像先提平台名词；未明确优先仍按原文本位置。禁用/仅查/启用范围先过滤，不扩大访问权限。required_sites允许两家/两处不同网站，只紧随网站/平台/来源类名词，不能把两家客户当两站。真实f32旧错误保留，修复不重写已完成任务。

- 2026-10-05 NAVIGATION_POLICY19只授导航：既有完整名证据的实际href→同商户完整主体页→同origin联系页，最多3跳，不改same_subject_page或新增别名事实。明确续查桥接最多8页，只复用原身份证据所属会话成功fetch账本，不借别会话、失败或任意旧缓存。
- ROLE_POLICY16：wechat独立Fact，仅明确微信标签完整原值及同主体归属；重复原文逐位置核验，不以平台同值电话授权微信。仅微信数字不得填phone。GET派生copyable、联系缺口/评分/知识/原生导出统一支持，争议/失效无动作；PATCH原响应不承诺GET投影。无DDL、无微信账户可添加性验证。

- 空检索且read没有本轮新正文时也标read_empty，不回退全量旧Evidence再模型提取；有新搜索摘录/成功缓存/实际补读及显式恢复仍沿原上下文。确认SDK提取超时（APITimeoutError/OpenAITimeoutError）即使零原生候选也发extract.partial并继续其他允许渠道，不标extraction_hash完成；ServiceError预算和无原生候选的通用TimeoutError仍抛。answer累计extract.partial中的确认SDK超时进入既有3次熔断，未完成分析在确定性摘要说明，不把预算熔断。真实284a3f第一次正是在空官网检索后旧页extract超时；修复后效果不可拿旧恢复成功冒称首次自动降级通过。

- 2026-10-05 extract-policy-5/ROLE_POLICY14：is_index只作目录路径分类，navigation_only剥派生导航后检查原连续完整主体介绍，含介绍的gc/st分类页仍由项目模型提取，不能一概零模型。纯导航从混合提取上下文排除，导航许可、save角色/电话/地区/预算不变；升级策略供终态恢复重验，原错误账本不清。介绍模式仅分析门禁，不能当客户资格或来源字段。

- 2026-10-05 ROLE_POLICY13：项目Agent真实候选contact_name引文为“联系人：”下一行Markdown列表姓名，旧contact_identity误拒且修复器重复相同引文。只忽略联系标签紧邻单换行列表符号，原value/quote不改；法人/中间其他字段仍拒，公开业务联系不等于采购岗位。旧任务/拒绝不重写，主体角色/地区/第二站仍独立验证，不把格式修复算获客成功。

- NAVIGATION_POLICY18行业/分店链接聚合返回DOM原最多40条，不能先截8再排已读/无关主体；read/gap仍原1–2读取额度、原4次发现平台轮换、原分店/主体选择，Broker同原href集合。Fixture第9目标与前8已读/无关覆盖，不增候选保存/模型/网络预算。
- source_catalog按当前文字位置排明确平台，解析可识别的明确否定/仅查约束；不要捏造/绕登录、无API权限不作禁止公开渠道，官网作为单纯待补字段不强制前缀。“先只查…”为阶段安排，不作永久仅查。本轮Scope由run_job（含恢复）/plan返回options/Broker构造共同应用，不改全局settings。public_entries第五可选prompt禁止泛directory借已禁目录；blocked_source只对已知根域或登记门店路径，不猜未知站点用途。
- 已禁平台不发请求/不记实际尝试、不复用旧成功查询，HTTP逐跳/备用返回及搜索新结果/同job与跨job缓存均按当前范围筛；旧ToolCall/Evidence不重写。新的persist也拒已知被禁源，不把其旧证据重新作新客户许可。离线内部fetch最小options可无渠道字段而复用合法缓存；明确空名单仍拒，execute缺渠道配置不发外部请求。禁止关键词覆盖范围有限，不声称理解所有自然语言或保证全部未知网站类型。

- NAVIGATION_POLICY17排九正子域根路径/goods/商品列表，旧导航附录同样过滤；同商户/数字/news/及用户指定URL原范围不变。真实Agent原文复核goods“商业照明推荐/价格”，不能据商品目录给当前商户第二站身份。西门子虽有真实授权店名录，未证明当前商户及具体灯型，不盲目整体关闭。
- ToolBroker.read_outcomes仅一次实例按原URL隔离的状态/计数，execute成功/异常后复制到ToolCall.result.read_outcome，不存正文/供应商协议。primary HTTP200/empty_body与fallback provider_rate_limited分开；缓存/未发送/直接失败/备用成功保留真实状态，不改原error/冷却/预算。tool_views只投影read_summary字符串，原嵌套诊断不出UI；未知旧值为空，不重写旧历史。answer观察账本同短摘要，empty_summary给失败入口范围，不把响应200或无来源算已读取正文。

- NAVIGATION_POLICY16补实际裸城市分类结构：heading_context保留唯一可见灯具及非灯具分类标题，relevant_detail使用原context判断品类；九正企业首页的区域分类链接仅写当前城市且无context时跳过，不能根据gc编号补品类。旧附录即使已缓存也在navigation_links重新筛选，用户URL/具体明文标签保持原范围。第三真实任务53.572秒/4调用仍读地板分类，说明POLICY15仅按label过滤不足，原失败不清，第四新任务验证16。

- 2026-10-05网站补查website_links不在聚合层截前4，单页DOM限额仍保留；gap/read先排已读再选预算，Broker复核同完整允许集合。prioritize_websites在全部已有客户有有效联系且缺所需根域时先新根域，无联系仍先原联系页。满额目录补查enrichment_allowed仅对已知云发了/九正数字商铺/八方公司页排无关详情；真实完整主体标签或已存同主体同商户介绍仍保留，目录分类/未知模板/用户明确URL不被撤销，事实校验不变。
- NAVIGATION_POLICY15排照明ICP中明确地板/洁具/吊顶/管材等非目标目录分类，家用灯型排车灯/医疗等明确特殊照明分类；用户明确混合品类仍保留，未知企业名不硬拒。地区匹配不是品类证明。真实Agent第二轮避免无关企业后却读地板等分类，第三新隔离任务验新规则；原失败结果保留，不拿少耗时证明稳定性能。

- 2026-10-05明确既有完整主体续查只加载实际引用、当前启用/有效身份证据，排除卖方、否定/归档/争议/长名子串。contact导航须same_subject_page、同源同端口同商户路径；优先实际DOM联系标签，其他公司/平台联系拒绝。extract-policy-4提供当前S编号的原始身份引文卡，不能授予新号码归属。错误可选categories原引文仅省略后完整重验，核心身份/电话仍拒。
- answer标准获客/联系补查检查完整主体、usable_fields和有效contact_name；遗漏时saved_summary通过新generation的reset→delta→completed替换草稿，不追加模型、不称SDK熔断。answer_mode=verified_contact_summary；解释/比较/原文复核及chat/document不适用。只能检测必要原值漏项，不证明全部模型语义准确。摘要保留联系来源/scope和时效待核，不将历史文章日期当联系表更新时间。

- answer中captured_at仅采集日期，不能写“来源于某日期”作网页更新/发布日期或营业时效；未知页面日期待核，明确问采集才标采集。真实adf原回答混淆，原预算10→11 answer复核已纠正，不伪改原历史答复。

- PARSER_POLICY public-account-5：parse_account可选target_roles受5种既有角色Literal约束，旧省略参数仍原商户行为；图按明确角色传参。已验证乐安居分店模板mall解析只取“了解更多”前原完整乐安居…店名字及同句是…商场身份，必须与原分店标题尾名相同、城市在原句、scoped_role通过。仅入驻分区category，不填租户Tel/商场地址/工商名/具体灯型/采购；未知页或无候选仍模型。成功解析走完整persist，缓存/提取签名同步升级。

- ROLE_POLICY12补正文直接身份句：同源name、唯一连续原句以完整主体开头“，是…原角色词”时，通用标题不阻断；角色必须结束首句（可之一），否定/其他法律主体/位于或服务等动作仍拒。不以店名/行业推角色，不补工商运营公司。原修复器及预算保留，不改旧拒绝结果为成功。

- 2026-10-04 review_context接受本job成功fetch的原请求URL或实际响应URL，最终URL复核不误说正文缺失；失败/未指定返回页仍排除，无新网络。public_entries的roles只筛明确用途入口：西门子零售入口dealer/retailer、CCGP列表project_buyer；未知用途不硬拒，选定采购步骤和用户URL原读取许可保持。Broker登记许可不因图选页筛选扩大或缩小。
- list_leads城市筛选复用city_values，深圳/深圳市均可命中，列表原city不改；与去重相同语义，无DDL。

- ROLE_POLICY11：city_key仅比较三字以上城市的末尾市后缀，city_values用于SQL候选/归档匹配，原Lead.city和city Evidence不改。“深圳/深圳市”不能拆同名同地址客户，满额Broker同键允许补第二站；地址/分店保护原样，旧指纹归档同地址不能复活，无历史清洗/DDL。identity.py为无业务依赖比较工具。

- 2026-10-04 entity-objective-1：搜索goal复用实际MCP objective字段，补查仅带同job已保存且query含原名的name/city及有效phone/email，目录商户明确非已确认工商名并排同品牌其他主体。objective不是Evidence；其他会话、争议/短号联系人不进入。工具幂等policy含目标hash，24小时跨任务查询缓存也校验search_context_hash；目标变化按原预算重新检索，不清原失败/attempts。

- 2026-10-04来源用途修复：非project_buyer的身份/联系/第二网站缺口不能把原采购step覆写为门店名；明确平台原步骤仍尝试，enrichment_name为空。追加采购仅project_buyer或已有主体且身份/联系补查充分之后的采购缺口，query使用公告/采购人/标的/截止字段，不拿未核candidate_target作采购人。纯采购列表只在project_buyer目标产生procurement缺口。
- 已验证分店短名首次主体补查可带原文完整phone定位，真实attempts>0后回原名，短号/争议不当锚点；不把同号码或搜索相关性当主体核验。read_selection豁免仅实际客户Evidence.source_id/url或原priority；名称子串不能给同品牌工厂豁免。明确用户URL及实际导航保留原读取许可。

- 2026-10-04 ROLE_POLICY10：name证据的已知分店必须唯一，所有已知分店Fact须同scope；同名同城不同分店新建不同ID，不扩写display_name。满额Broker也校验分店，不借同名补别店电话。旧指纹归档同scope仍阻止复活；不改历史事实/指纹，无DDL。
- profile已有products时questions清空，执行限制放summary；缺产品仍阻断并询问。extract-policy-3逐来源保留parse_account成功结果，只将未解析页交模型；超时且有原生候选时emit extract.partial，保留候选经save全量核验，未处理签名不记完成，extract_model_timeout强制partial。取消、预算、未知异常仍上抛。

- 早期目录条件用“尚未满额且现有客户无可用联系入口”，而非仅零保存；QCC摘录保存无电话企业时仍可发现目录联系记录。已有完整phone/email/website则不插早期目录，原各主体补查/发现计划继续。实际26edca原仅1无联系摘录partial揭示此调度偏置；历史结果不改，新任务验证。

- ROLE_POLICY9：已验证入驻目录商户地址必须是该条Tel紧邻明确商户/门店/店铺/铺位地址标签，商场简介/总地址不能继承；错误字段只省略后全量persist重验，旧历史争议不清。畸形可选website也省略后重验，不补域名或弱化电话归属。满额新页只补实际出现的已存名字，来源选择及提示尾部保持同一名单，避免重生成其它客户/无谓修复。

- 2026-10-04：gap从真实search_accounts ToolCall.attempts累计主体查询次数，未满额度且次数最少者优先，原计划及新增步骤共用选择；全满额主体均耗尽则不盲搜，实际用户URL/网站/目录读取仍原预算。明确跨站要求时未满额也交替主体补查/开放发现，enrichment_name仅该查询提取聚焦，下一发现轮清空，不把已有客户当永久指定名单。
- 零保存且明确平台均已真实尝试后，同一search_count最多一次早期登记目录（early_directory_after），无须等搜索耗尽。gap在下一cursor插只读step，保留原计划suffix；direct_read_target必须实际登记或真实链接且原范围可读，不被旧摘要抢占，read完成清空。行业frontier及分店scope保留，未满额可发现其他分店。新增可选checkpoint字段，不重置预算/原账本、不新建图节点。
- answer_context同时提供有界连续name/phone/contact_name/city证据卡片，精确相同URL/quote去重且字段分别列出，不拼原文；角色表头不再遮掉商户同条Tel。真正已验入驻记录可称目录商户潜线索，不推独立工商实体/采购/仍营业。

- 2026-10-04：ROLE_POLICY8要求每条name Fact均等于display_name的完整原名，不能先给合格name再混第二简称；原QA简称争议记录不人工清。answer_context保留每字段最多4个替代值/真实总数/是否部分，长quote不注入；回答逐字段核对状态，不把name争议说成address争议。额外真实answer_node复核沿原任务预算计费、还原原终态/原答复，非新自主发现。
- reference_only支持“仅复核此已读取目录”“不读取其他网页”等明确约束，仍须当前真实链接；开放发现不受影响。真实首次诊断100600ms/7调用虽目录解析2商户，却错误搜索两次，范围验收失败，原账本保留；修复后同文本新隔离任务验证零搜索，不重置旧预算。

- 2026-10-04：PARSER_POLICY public-account-4复用既有parse_account工具，parse_accounts在已验证乐安居分店详情正文按灯饰/灯具/照明分区取同条商户Tel，复用mall_listing/mall_city_quote及phone_info。主体短原名不扩写，商场地址不继承，具体产品匹配留空；非灯具目标、短号、分类跨区、多个分店标题、同名冲突电话不生成。模型分支/公司模板保持；mall-only目标不强行改成retailer，未知模板仍原核验路径。所有候选必须再经persist，不以解析工具成功授资格。
- 预算停止的operations也传真实fetch.pages供empty_summary显示实际域名，避免丢失已读来源；不输出未核验公司名，不新增模型请求/SSE伪token。

- 2026-10-04：ROLE_POLICY7拒名称内角色词与所在地宾语授予业务身份，direct/scoped入口一致；完整身份谓词/经营字段仍核验。read_selection仅自主发现搜索摘录排明确manufacturer-only（目标未含manufacturer）及精确exa.ai/library/，未知/混合不拒；用户URL、原客户证据和实际导航保持许可。read_skipped最多64条内部source_id/reason，日志不含客户正文；没有新正文且已跳过摘要时read_empty防旧摘要重提取。
- role_correction/candidate_repair稳定label含ROLE_POLICY不含cursor，沿用真实job+prompt持久ToolCall键。相同证据跨轮缓存、新相关来源改变prompt允许重修；不得把通用模型预算异常当SDK熔断。修复丢name或原有城市引文时保留原候选/原失败类别，不清待核目标、不放宽persist。

- 2026-10-04：contact_owner.public_phone在普通非采购页核验号码前最近完整主体与平台联系标题，拒绝平台/建站/其他法律主体号码；已验证商场模板与采购买方块保留专用校验。ROLE_POLICY升级6，旧persist结果重验。规则是确定性结构边界，不能保证识别所有隐含第三方主体或电话接通。
- 已存目标补查仅带本轮正文及Lead.evidence实际引用的name/buyer_role/city历史来源；未引用旧页不重复进入提取模型，服务端原始来源不删。明确未存多主体/自主发现分支不变，extract-policy-2参与去重签名。不硬裁身份引文，保留原有excerpt选择。

- 2026-10-04：read_node把真实标题与正文一并用于角色/地区/完整联系信号排序，补mall/project_buyer及显式manufacturer目标。仅决定读页，不能由搜索排序直接确认买家或电话归属。
- public_contacts及乐安居详情DOM复用Trafilatura.decode_file→UTF-8 bytes→显式HTMLParser，修复GBK实际内容/旧GB2312声明导致native错误与联系区空白；隐藏子节点/脚本/样式同样排除。fetch操作策略contact-decode-3，旧有效正文缓存仍可复用，不伪称历史重解析。
- run_job识别同job/schema的终态checkpoint，partial到END不再从空初态重做。终态选明确as_node，规则变更回read后继extract核验已有来源，同策略回save后继gap继续；原来源/预算/旧账本不清零。validation_policy=ROLE_POLICY，当前role-policy-12，提取签名及persist操作都参与，搜索协议不因角色升级重置。
- 同源完整单主体标题/name下，市场类型/类别灯具市场或灯饰专业市场可证明mall，不证明采购。categories不能取明确市场类型的场所词；可选错误仅省略后完整重验，旧争议记录不自动清除。

- 2026-10-04角色关联修复：evidence_role拒绝角色否定，direct/scoped两入口均执行；跨句只认完整主体开头的≤700字连续介绍及紧邻主营/专业句，单主体title、同源name、唯一原文片段和无竞争/目录分区均必需。不为修复器补代词。
- candidate_targets是最多3个未核实角色主体的补查方向，只有persist明确角色关联拒绝（name/引用已过）才登记，非客户/事实；每主体原max_candidate_searches约束及原平台优先级/预算保持。空提取批不清目标，已保存后去掉。
- empty_summary按实际成功fetch.pages域名标已读来源，不以channel（查询方向）授予官网/目录身份。proposed_records>0时不能按用户错误前提回答没有候选。

- 单源候选准入和required_sites完成条件分开：提取有主体/地区/明确角色即可提议，联系方式/第二网站缺口交gap；不能让模型提前把跨站要求作过滤条件，也不能降低persist身份门槛。真实Agent复核明确单页零售表述仍无候选，规则升级需无名/URL任务验证，不把提示修改当获客成功。

- source_scope.reference_only只识别当前明确链接限页指令，plan→read跳过搜索，read过滤到原链接，gap不扩展，extract只用指定页正文；开放多渠道任务不受影响。证据修复冻结初次matched_products，原列表仍经persist校验，不允许修复器新增用户产品。

- 2026-10-04：extraction_hashes按任务保存最多64个成功上下文签名，包含画像/规则/目标/排序来源原文，避免A→B→A反复调用提取模型；失败不标已处理，改变产品或原文仍重新分析。
- statistics_evidence统一营收/人数口径与周期校验：scope须同quote原文字串，日期合法且精度由原文支持，成立/注册/发布/版权/型号日不作统计周期。维持原校验错误以支持可选字段省略后完整重验。
- public_directory.mall_listing仅扫描“分店 入驻品牌”标题之后的商户Tel记录，标题本身及名单前总电话不作retailer。真实旧QA误判记录保留作诊断，不移入生产或算合格客户。

继承backend/AGENTS.md。2026-10-02，Codex。

- 对外入口main.py只编排服务；业务事实进入service.py，记忆进入knowledge.py，公开渠道工具进入research_tools.py。
- ToolCall.operation_id唯一，成功操作与结构化模型输出可恢复复用；暂停不是永久失败。
- Job.metrics.model_budget是任务级持久预算；callbacks在每个真实模型请求前预留，不能在恢复时清零。
- 所有非空自动事实都要逐字quote/value和实际source_id。角色还需要同语句主体关联，不能把另一个商户的身份套用。
- 知识复核TTL与采购公告截止时间是不同概念。采购历史只能保留历史，active意向评分必须来自有截止原文的买方公告。
- 冲突/失效字段不能用于完整度评分；用户非买家反馈进入排除记忆。原始来源保留供审计。
- LangGraph State使用TypedDict逐字段合并；StateGraph(dict)会替换root值，不可用于模拟真实恢复测试。
- 身份问答不是ProductProfile.questions；不能再将画像模型输出当普通回答。chat仅answer节点，不写画像/公司记忆。
- 路由须覆盖问候、解释、已有结果、含问候的明确找客户指令、产品介绍、继续补查。模型TTFT与提交至首答耗时必须分开记录。
- document_parser.py只做确定性本地解析；files.py持久化及预览，parse_info为新增非破坏JSON列。DOC转换独立LibreOffice profile，OCR模型在data/ocr-models，临时产物留.codex-tmp/documents，不用TemporaryDirectory递归删文件。
- Word按iter_inner_content保持段落/表格顺序；XLSX同步读公式和缓存簿，read_only缓存簿不得逐格随机访问；空表不能把页签/竖线当内容。缺公式缓存、OCR和读取上限必须显式标记。
- 上传新附件时必须重新分析产品画像，即使已有产品记忆；2万字模型上下文优先首尾/相关块，其他文字未读不能声称完整分析。
- tool_views.py屏蔽内部模型结果/来源正文/任意参数，只给真实工具状态和摘要。conversation_detail批量提供每轮tools与attachment元信息，避免历史N+1请求；同秒任务按submitted_epoch稳定排序。
- document路由context→answer，不调用profile/plan/search/learn；普通解释、改写、计算不能因为提到“搜索/采购”就触发获客。最新文件从完整会话查，而不是只看最近3条用户消息。
- tracing.py与原生LangSmith上下文集成，tool_views.trace_tool_inputs只投影name/arguments，SDK默认隐藏原文。凭据优先环境变量（显式空值关闭），否则只读apikey.txt中的独立lsv2_/langsmith_api_key字段；模型Key不作追踪Key。凭据不进DB/API/日志；配置异常关闭，不把enabled当上传成功。
- ToolCall.attempts累计预算、last_attempt_epoch区分显式恢复、retry_after_epoch持久冷却。成功复用，永久拒绝不重试，临时失败仅resume重试；source_errors不传播原始错误正文。
- resume与工具供应商挡板使用全局冷却；site仅限制同host，排队请求实际发出前再检查。provider受限不妨碍直接公开HTML/缓存正文，不能改供应商绕过site冷却。
- 恢复checkpoint即使已越过search也重放失败工具；新source_ids进入extract/save核验，预算保持。没有新来源不把provider warning无条件清空。
- PDF单页文字层与图片并存仍OCR，原文字层保留；达到OCR上限保留文字层并标部分解析，标题可提取不能证明扫描正文已读。
- evidence_context.py按真实来源顺序优先本轮URL，同URL保留完整正文；长目录保留中部角色记录，不只首尾。模型每批最多8个，不能用任务20个上限要求单批20个。
- 公开HTML给trafilatura原始bytes并favor_recall；httpx无charset头默认UTF-8会损坏GB2312网页。乱码缓存不复用且原Evidence保留，替换字符异常的正文不进核验上下文。
- procurement_signal.source_id也须纳入作用域及正文校验，独立公告引文进入证据和知识。不能要求它先冒充基础资料Fact才允许验证。
- CRM人工修改角色/联系资料时重算qualification/score，已标非买家的反馈继续阻止资格恢复。空白跟进422，不能只依赖前端trim。
- 最终回答必须区分已核验潜在线索与尚未确认具体产品/采购；普通结果追问读取同会话真实CRM优先于旧回答，不能跨对话取客户。error_details只记录异常类型链/系统码/栈位置，无正文或局部变量。
- config.configure_tls在未指定SSL_CERT_FILE/DIR时采用certifi CA；OpenAI3.22默认httpx2的Windows truststore.CertGetCertificateChain曾同步卡住主线程/心跳。不能为修复卡顿关闭证书或主机名校验，用户已有CA配置不覆盖。
- cancellable取消后仅最多等待0.5秒，迟到请求消费异常并记录pending；流忙时延后aclose，不能finally无界gather或aclose拖住paused。PENDING_CLEANUP不持久化返回正文、不重新发请求；客户端停止不承诺供应商计费停止。
- Worker中断计时标clock_is_partial，下界显示≥，不能宣称最后尾段最多只误差5秒（原生阻塞会让心跳一起停）。暂停工具也写累计elapsed_ms和真实tool.finished状态，不能显示0秒或保留上一失败码。
- 采购公告历史保存在qualification.procurement_signals；无新公告不能清旧记录。procurement.py统一计算展示状态/有效分，列表排序、详情和导出先刷新派生分，不改原文阶段/截止日。
- 争议/失效反馈同步标公告verification；Excel事实表包含alternatives、统计日期/口径/来源及独立公告。归档主体不能被自动save_candidate重新激活。
- 产品画像只在纯“继续/继续补查”等无新约束消息时零模型复用；地区/角色变更用Pydantic结构化提取，不以七城白名单截断当前要求。真实成都覆盖深圳及原产品型号保留已验证。
- 独立采购信号也检查invalidated_procurement，纠错引文不能重贴，失效旧source不能复用；反馈快照保存公告且兼容旧Lead历史，不能新建无verification记录复活采购分。
- 产品知识命中进入有界用户资料上下文，不进入source_ids或当公开买家证据。渠道绩效仅同地区同产品，以真实valid_leads及反馈排序；credited_lead_ids去重learn产出并精确归因反馈，未知归因旧统计不猜测更新。
- DOCX表格仅实际非空行生成[表格]标记，空表/空嵌套表不能冒充正文；真实上传API拒绝空表文件400，图片OCR及已有文本表格不受影响。
- source_catalog统一渠道、范围、用途和Skill规则。public_index是公开搜索能力，不是平台API授权；限定渠道连重定向及fallback都必须校验域名。用户无QCC/1688权限，本期不实现收费请求。
- contact_view统一有效联系入口/缺口/来源投影及SQLite排序函数；人工联系人与owner销售负责人分开。原文短号不补区号，争议/失效不生成联系动作；格式有效不代表接通。
- public_contacts补正文漏掉的静态联系侧栏，隐藏区/脚本排除；不给制造商或目录主办方电话套买家身份。read先还原搜索顺序，再依摘要角色信号分配正文预算；信号只影响读页，不替代persist_lead核验。
- source_access识别明确登录/验证入口，原文/缓存/fallback均检查，普通页脚不误判。reference_urls最多4个当前用户链接，只有fetch真实响应入Evidence，不制造空指针证据；关闭平台不借official绕过，读取仍检查公网/预算。
- 用户明确跨站核验时，required_sites按来源数而非客户家数解析，移动/桌面按根域合并；未满足标partial，metrics.corroboration保留要求/实际数。网站数不是独立事实调查数。
- evidence_role只补充可证明的结构关联：单主体标题及同源name、明确介绍段代词回指、角色表头下真实行；中间其他法律主体拒绝。模型quote/value仍逐字校验。格式/来源ID/采购引文失败先用已有原文有界修复一次，仍不合格就换来源，不降低门槛。
- phonenumbers9.0.40离线生成contact_href/phone_href、检查CN固话长度；原值不改变，异常长度/短号/掩码/失效/争议不提供操作。API投影键不能写回事实。相同拨号值及完整公司联系页明确并列的座机/手机保留additional_contact，其余不同号码仍争议；父事实失效/争议不生成替代号码动作。
- evidence_context用S1/S2精确映射存档ID，未知别名拒绝；用户指定完整目标优先，不扩成集团/国际部，不把卖方自己作买家。事实name归一后须与display_name相等。
- ProcurementSignal的quote/buyer_quote/deadline_quote分别逐段连续原文、同source_id；日期与时间必须匹配，三个片段均保存证据/知识。纠错同源信号不能靠换引文复活。
- contact_owner采购联系方式必须在完整买方信息块；代理/项目咨询/技术热线拒绝。contact_name须直接跟联系标签，不借同页联系人标签给法人授予采购身份。gap/finish/资料分共用contact_view.usable_fields，异常phone非空不能让研究completed。
- procurement_views展示按source_id/完整买方/参与角色/截止去重，同组保留最完整分段引文，失效/争议状态不可被长引文覆盖；底层signals历史不删除，截止不同仍分开。
- public_directory只识别已验证乐安居subbranch-detail/subbranch-det静态模板，保留可见分店介绍及列表，未知模板回到Trafilatura。入驻品牌只有分店标题+独立店名紧邻Tel才支持retailer，电话必须该条记录；店名不拼商场/城市作法律主体。evidence_context短店名只从用户明确指令和原文独立行交集定位。
- observability隔离DATA的日志写入DATA/logs，不与正式ROOT/log/web争用Windows轮转文件。正式api/agent目录保持，测试/QA启动必须先设独立DATA；不要只隔离SQLite却共用日志。
- source_limit也识别初始化JSON-RPC error.message中的明确限流，未知协议错误不误判；只返回安全scope/delay，不保存原供应商消息。限额未知60秒只作为冷却下界，不能承诺额度恢复。
- 商场原文短店名的城市可由public_directory.mall_city_quote从同分店明确在/位于城市介绍补独立引用；name/phone已有同源商户关联，无该结构就保持原城市校验，不从附近城市/查询词猜位置。
- PUBLIC_ENTRIES是已核验公开目录入口，不是客户证据。按地区/产品/启用专用或非采购directory父渠道返回，CCGP不能借directory绕过关闭。Broker允许实际读取，read_node在首次无来源或gap明确补查时逐页使用。读取前不生成Evidence，关闭渠道/未知链接/总预算仍拒绝。
- source_content排除仅标题/URL的正文和旧网页上下文，原Evidence不删。普通有效缓存继续离线复用；1688缓存/重定向受source_policy同源robots检查，Protego固定0.7.0，未知规则不读取，robots429入站点冷却。QCC567为site_access_restricted，不换读取器绕过。
- CCGP静态gkzb列表保留原href/标题/记录，decode_file识别编码；procurement_links优先匹配公告，其后只接实际可见下一页href，脚本声明/页码不生成URL。Broker只从allowed_sources的同渠道正文授予许可，图按原预算及已尝试URL逐页续读。列表不进入采购人提取模型，详情仍完整核验；无真实入口不翻页，不制造买家。
- checked_candidate.industry须有行业分类表述，值不能是当前城市（含市后缀）；主营分区放categories。逐字出现不能证明字段语义。真实6luna曾把深圳误填行业，错误隔离库/导出保留供复核，不得并入交付；生产未发现industry=city，不做盲目清库。
- channel_status只读ToolCall账本，能力status与runtime.search/read分开；最近成功不是全平台开放/买家产出证明。供应商有效冷却只覆盖检索，站点失败不扩散其他渠道，冷却到期仍保留最近受限记录不宣称恢复。API不包含查询/正文/Key，刷新不发外部请求。
- 搜索限额时gap仍须处理尚未读取的明确reference_urls，有预算则直接回read，不花新模型/搜索调用；read_attempted_urls记录预检查失败也不空转。recent_read_source_ids使新HTTP正文进入extract优先上下文，显式恢复也更新该字段；不能只看空搜索摘录而丢第三页。target_names支持“核验以下/下列…”同一句多URL名单，句号后的主体不自动纳入。
- scoped_role的本商场回指仅限完整单主体title、同源name证据、同句400字内明确角色且无竞争法律主体；目录/其他主体仍拒绝。不是以简称或销售范围推断角色。
- 同一完整主体+同一单主体页的重复地址片段不另建客户，仍保留disputed；same_subject_page只从name证据/同URL或ID/单主体标题证明，跨分店目录/其他主体不合并，Broker满额补查也沿用。source_id本身不是身份证明。
- 明确多主体补读优先新页面里尚未保存的指定主体，避免再生成已保存主体字段；无明确新主体时仍按原补全流程。所有条件分支显式path_map，保证图接口保留gap→read/decide/answer回路，不能以可视化器推断lambda路径。
- public_accounts解析已核验云发了公司模板及HC23完整公司页；HC23必须同一完整主体标题/企业名称、本商场一级经销商原文、目标城市地址及完整双电话页尾，不扩写掩码，不取平台邮箱或传真。parse_account仍需allowed_sources及启用渠道，候选经persist_lead；PARSER_POLICY同时参与工具缓存及extraction_hash，规则升级不能复用旧解析。
- 显式恢复无新source时保留recent_read_source_ids，不能清空待核验页面。answer只按同job真实run.failed/partial的明确SDK超时3次打开熔断；通用TimeoutError可能是预算，不能当模型故障。answer_summary只反馈已保存资料，争议联系不作正常入口；研究超时有已存客户时finish仍通过reset/delta/completed反馈一次确定性摘要，再发原错误终态，不模拟逐字输出、不重置预算。
- 检索受限且数量/联系资料/来源要求尚未满足时，gap按ICP选择未尝试PUBLIC_ENTRIES进入read，已有客户不封锁补查；预算、启用渠道和read_attempted_urls仍有效。自主发现未达上限时，已存客户不是指定名单，新正文独立分析；满额或用户明确名单仍聚焦原主体并保留多源证据。
- 客户自主获取验收只能调用项目Agent并检查其回答、工具账本与Evidence。Codex手工客户搜索、提供已知客户URL的任务、单节点补解析是调试证据，不是自主发现成果。
- 满额补查的新正文没有任何已选主体完整名时，extract不重生成旧事实；实际失败任务同job恢复验证此分支，原超时事件/预算预留不清零。answer使用真实pages标题/URL解释已读范围，不把检索供应商受限说成网页平台需恢复。
- 乐安居/subbranch/只保留真实可见同站分店href，directory_links按ICP/原渠道授予Broker许可；入口列表零模型且不产客户。满额补查时，全部原客户的name证据已有明确分店key，新正文全属其他分店则不以同名品牌补原店；同分店仍正常核验。
- contact_view.missing_fields与usable_fields共用格式/争议/失效规则，有有效邮箱不能掩盖短号电话缺口。answer_context覆盖全部客户，压缩冗长引文而不切整批JSON；分店标签只据role_context或scope，不能按URL编号猜；同名不同分店仍分行。
- 一次性数据交付复用原生export_workbook/API，数据必须来自项目Agent。表格工具重导出需额外核对冻结、autoFilter、全单元格原值和未知空白；Artifact Tool当前会丢sheet.autoFilter，本轮仅以标准OpenXML复制原生筛选元素修复，未改客户数据。不把该一次性修复混入运行导出代码。

## 企业工作台模块（2026-10-09）

- 正式日志为`log/web/<name>-<PID>.jsonl`；API和Worker不能共同持有同一个RotatingFileHandler文件，Windows跨进程重命名会WinError32。隔离DATA仍用自己的logs目录；双进程小容量轮转已有本地回归。
- company-evidence-2只接受精确完整名或同句完整名/简称映射；统计字段还要核验主体或合并口径。明确reference_only不追加既有官网/报告读取入口。
- 实时公告日期须连续日期引文/用途标签，写入标准published_at/deadline；精确买方/原项目号可连接历史项目，同公告跨任务复读追加来源不增事件。日期未知不靠抓取顺序更新阶段。
- relation_summary按最新同一期统计，重复同值关系只合并来源，币种/单位不同不相加；未知金额/占比为null而非0，前端须处理空值。

- `company_import.py`保留原文存档、来源哈希、报告期、主体范围和摘录类型；两个数据集的相同source_id不能跨命名空间关联。历史快照不伪造Job/ToolCall。
- `company_research.py`只研究当前指定主体；`company_validation.py`拒绝行业数量冒充行业、季度值冒充年度、对手方交易额冒充营收、无主体归属的联系方式和无公告角色的采购项目。
- `CompanyRelation`的supplier/customer金额是本企业与对手方的年度交易额；service_supplier和brand_application单独展示。`ProcurementNotice`保存公告阶段，重招/转载/候选不增加独立项目计数。
- `Evidence.source_meta`可存来源数据集、OpenCLI/Playwright后端、版本、哈希对象和归档状态；公开API只投影白名单元数据，不能返回密钥或本地路径。
- 浏览器读取能力不是企业事实：先检查公网/访问策略/来源许可，真实正文才归档；空正文、登录、人机验证、robots和私网地址必须保留缺口。
- industry_navigation仅已核验www.yunfale.com可见静态同scheme/host/port原href，保留查询串，不取member/隐藏/script/子域/外端口。导航附录用于Broker/read/gap发现，factual_body剥离后才进客户提取；主页/company入口零模型。照明ICP不读无照明标签随机详情，最新目录优先，不表示全站覆盖；fetch policy升级不改原Evidence。source.http/parsed/read_failed只存状态/字节/长度/链接数/错误类型，无正文/Key/查询参数。实际自主4页6调用0客户是失败覆盖证据，不是渠道买家产出。
- 满额且所有客户name证据均有明确branch_key时，read/gap在HTTP前过滤其他分店实际链接/登记入口，把预算留给其他网站；明确用户提供的URL仍按原读取契约执行。未满额、未知scope、不同网站不限制；extract原分店身份校验保留，不能以URL推法律主体。
- source_rules只加载runtime-playbook共同及全部启用渠道，不注入source-playbook的既知客户/长实测日志。2026-10-04旧6000字整段裁剪曾让1688/QCC规则全部丢失；现全11渠道2288字且有明确渠道标题，超6000报channel_rules_exceed_limit，不能静默忽略平台约束。历史参考仍保留，不是客户Evidence。
- 候选池与保存配额分开：自主发现单批允许最多3至8个候选（指定/满额仍原范围），save先用本任务连续原文及contact_view格式预排序，再走完整persist核验；造引文、短号、同字段多值不提升预排序。满额跳过新名字，原主体仍可补全，不改公开值/争议或角色门槛。learn经验不能重排用户明确指定的平台前缀，只排序其余步骤。
- answer读取同job成功extract/parse_account的候选输出记录数与实际保存数，不能把“只保存1条”说成“只取得1候选”。记录可跨批重复，不代表不同公司或所有候选已核验；只问比较时说明，普通答复不加无效计数。proposal_summary不把未保存名称/电话送到回答事实上下文。
- 新行业入口b2b168/jc001主页均由实际Agent读过，登记只授予目录起点不存客户。新平台分类/商户子域只认实际DOM href和平台根域默认端口，云发了仍同scheme/host/port。九正商品/供应/招商/新闻/广告/移动副本不进买家前沿；八方照明首页不跟同城物流链接，灯饰分类内可选实际深圳公司href。页面自造导航标记先剥离，分类/主页不冒充客户；九正已核验gc/st目录零模型，数字商户详情仍提取，不按URL判断买家角色。
- source_policy.requires_policy覆盖1688及新增b2b168/jc001根域/子域，缓存和重定向同样检查robots；原Protego/小时缓存/未知拒绝规则保留。行业目录自主发现单平台4次后先试未读独立入口，子域合并计数、失败尝试计额度；已选客户/明确用户URL不被这条发现限额拦住，全部平台已尝试后解除，总预算仍有效。尚无客户的开放式发现也只分析最新正文，不反复带旧公司令新入口调用模型；明确名单/已选主体保留多源上下文。
- heading_context只保留最近小块DOM的唯一可见产品分类标题，原label/href不改，目录分类附录仍从事实上下文剥离。裸城市链接可按灯具标题优先，不从gc编号推品类；多个显式标题/隐藏子标题/大块拒绝关联。类别加权只给目标城市或企业/经销目录，不能把泛灯具类别抬到城市公司前导致绕分类圈。八方dengshi子域也属已实读灯饰目录，不因不含/dengshi/路径误过滤公司原href。Yunfale平台/about不作买家联系前沿。
- run_job图步上限按搜索/读取预算计算（至少100），恢复后重新按原checkpoint预算计算；24读支持的read/extract/save/gap回路不可撞固定100步而丢总结。模型/HTTP/累计时长独立硬预算不变，增加图步不是增加工具额度。真实24读任务曾GraphRecursionError，同job修复恢复15→16模型调用、91658→98505累计ms，旧失败保留、当前partial/0客户，不当首次整图成功或新买家。
- 2026-10-04复核回答可用review_context读取同job成功fetch的实际正文，按请求URL分配预算；标题摘要不是全文。explicit manufacturer_target只认当前明确目标，不继承历史，也不把卖方生产介绍作厂家买家；qualification记录此条件，原成品灯经销规则保留。
- persist可有界省略已被确定性校验拒绝的可选事实再走完整校验，不改值/引文、不省核心身份/角色/电话归属。public_subject旧八方模板仅两个可见同块gsjj/jbzl栏目完整名一致时补标题；模型名字/URL编号不参与。原始HTML诊断捕获仅显式环境开关且DATA位于.codex-tmp内，不对生产启用。
- 零保存非指定原文复核使用verified_empty账本摘要，不让回答模型从pages标题捏造已核实客户；SSE真实单次摘要不伪装逐token，零结果不算模型熔断。企业类型与经营模式一样仅在同源单主体owner成立时接受紧邻明确值；否定/竞争主体拒绝。未知工具异常追加安全error_details栈位置，不记录正文/参数。
- NAVIGATION_POLICY13不再以“存在已保存客户”为全部无关链接解锁单平台发现配额，仅真实导航label包含已选主体才豁免；明确用户URL仍原规则。八方/s数字.html文章/供应链接不进目录前沿。contact_summary.site_count/sites按客户已保存证据根域计数，source_count仍原页面数；本轮其他网站不计入客户。
- read_empty只标记本轮直接导航补读无成功来源，extract不回退旧source重复提取；普通检索摘要提取不受影响。每次read重算，实际成功/有效缓存有来源即解除；显式recover保留待核recent来源并解除标记，原预算/证据/错误保留，不清掉旧Evidence。
- NAVIGATION_POLICY14扩展明确室外/室内照明灯具黄页的地域排除。public_website仅实际DOM可见网站字段或标题主体完整名称href，不取脚本/页尾/隐藏/歧义多链接；已存同源name+单主体标题才授予补查，平台关闭不借official绕过。gap/read优先该补查页，Broker独立再校验；新页仍完整验证，不授予官网身份。factual_body剥离两个工具导航附录，has_content与checked_candidate也使用该原正文，修复模型不能用派生标记举证。
- 确定的模型/累计时间预算ServiceError也由run_job用实际账本/已存资料生成budget_summary；零结果不称客户，保留原failed/partial/error，SSE先reset/delta/completed再终态，不请求新回答模型。metrics.budget_exhausted不代表SDK故障熔断，不重置预算；finish尊重传入answer_mode。真实同任务恢复调用25→25验证。
- 2026-10-09查询路由：企业主体查询允许“查询某主体的信息/资料/情况”及船厂、医院等无公司后缀主体；短确认只承接同会话最近的企业请求，原始Job.prompt保留，授权研究正文写入metrics.research_prompt。普通解释、明确禁止检索、附件问题和卖方获客不升级为company_query。结构化提取超时只保留已归档Evidence与失败/可恢复Job，不能把回答或网页标题写入Company。
- 企业提取前：新主体必须在factual_body出现请求名，搜索相关性/标题不能给其他企业授身份；已核验持久身份仍可补本轮新事实。只对确认的APITimeoutError/OpenAITimeoutError降级为extract.partial并继续其他研究步骤，预算/取消/未知异常仍上抛；不记录成功提取缓存、不保存空企业。
- company_gap仅在计划结束、确实已读全文、无Company且正文未出现请求名时询问全称/官网，结果needs_input；空正文或模型拒绝不等同企业不存在。真实海能名称任务3次模型/接受2事实/1张会话卡已验收，历史304事实不能当本轮新取得。
- 耗时诊断以ToolCall.elapsed_ms（操作各attempt累计）/Job.elapsed_ms（全轮恢复累计）/node.finished（成功节点）区分。cached_model失败无成功ToolCall及node.finished；用预算预留和run.failed事件复核漏掉的等待，不能从成功stage_timings把失败90秒说成782ms。读取成功须核Evidence非空正文+哈希及operation_id事件对，completed+empty_results只说明调用完成、无来源。
