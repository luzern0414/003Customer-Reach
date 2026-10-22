# 后端验证

- 2026-10-10 `test_company_identity_relations.py`覆盖10家独立地址/方向/片段、跨父404、组合主体拒单体、连续全文候选、别名与模糊名分流、对方事实归属/重复关系绑定/代码冲突、真实LangGraph候选确认并恢复原Job与预算、地区补充不改原名、耗尽读取后暂停仍分析三块归档。模型/网络替身与真实公网验收分开记录。

- 2026-10-09 `test_company_speed.py`覆盖分页前最新排序、搜索真实重叠/排队限流不耗额度、分段采购买方/数量/编号、后台重放及失败、首批消息、停止原因、24:00/计划发布用途、跨域转载及不同截止、集团电话、抑制取消时恢复409、关联主体可见性、采购/未来产品不作主营。SSE断言只拼最终generation，首批和最终不可相加。

## 研究v3/来源联合验收（2026-10-09）

- 当前完整集合576 passed in140.90s。research_pipeline_v3覆盖逐次模型意图、同Job复用、本地+新网络、两轮补查、全原文区间、逐企业/争议字段覆盖、失败片段与预算保留、跨JSON数值去重和失败模型/节点计时。
- company_citation_binding覆盖不同来源各自value/metadata、重确认不增关系、绑定失败事务回滚、集团任务对实际子公司买方的项目/公告绑定。entry_sources包含_03→_04保留数据与幂等、宽表行收窄、未定位不造页码与历史研究元信息保留。
- 切临时Session前加载所有持有Session别名的模块并成组patch/恢复；否则晚导入research_tools仍指向旧临时库，guard查不到Job而paused。workspace→overview→binding固定顺序16项已验证，product_match有外部模型fail-fast。
- 真实QA ccfd5d38740a4a94836e86732bed69da为13模型、4次新搜索各8来源、47清洗、3接受、gap追加2查询/round2、359910ms/partial。未取得采购公告保持缺口；来源数不是项目数，本地替身不冒称公网成功。

- 2026-10-09 test_entry_sources覆盖同年报10家独立真实原行、来源与定位读回、幂等、多来源拆段、强外键CHECK、事务回滚、重复/历史整理片段不造页码、_03->_04升级保留原文/原值。test_company_citation_binding验证新研究重确认使用各自source的value/metadata和整体回滚。

- 2026-10-09 `test_company_overview.py`覆盖明确收入区间、单时点/跨年不推测、真实数据库匹配上下文、有界来源和计划、显式company_match在模型误分类时仍走document、完整图不进搜索/保存、结果独立回显和企业事实不变。模型替身只证本地逻辑；另在本轮独立QA运行真实模型2次/21.02秒，不能把该测试文件当客户订单。

- 最终504 passed in66.80s覆盖网站计数确定性摘要，contact_answer参数化保留单站漏电话模型替换/多站零回答模型/混合渠道零回答模型三种真实save→SSE链；混合客户3站与1站不能全批套缺口。新自主ac942为349605ms/21模型/3客户/2phone、站数3/1/1，原模型误说全1；仅answer修后21→21真实核数。单样本慢于旧233秒，不称性能稳定优化；两个商户仍单站，采购均未知。

- 2026-10-05新增test_cross_site_owner（混合分店scope/实际owner跨站排序）、test_channel_summary（同平台先后成功失败/摘录/标题导航假正文不算读）、contact_answer参数化真实save→answer无模型过程摘要/SSE。首专项2失败因为旧预算/摘要夹具仅titleURL却期待已读取，补真正body/kind及核正文投影后28通过，未放宽生产正文判断。搜索预留实际gap账本测试保持3真实attempts、余1搜索先目录/原未来计划；15专项通过。新增前最后501 passed in75.96s，新增后完整待核。

- 最后网站要求摘要修订完整495 passed in66.09s；test_contact_answer实际原生保存→漏电话模型草稿→新generation SSE替换同时保留“两家不同网站”未满足提示。真实4e5867为233102ms/18调用/3潜线索/2phone/各1站、required_sites2、partial；两次真实answer复核预算18→20只分析原资料、不作新自主获客，原答恢复。仍有渠道过程概括偏差，绿回归不能证明全部模型语义准确。

- 2026-10-05最终完整495 passed in76.94s。test_channel_priority_phrasing复现画像先提家居城、后文先尝试1688/qcc，确保明确优先指令覆盖画像名词且不绕禁用/启用范围；两家/两处网站识别为来源数，客户家数仍不计。真实旧f32前序错误/required_sites1及单站partial保留，新无名URL任务4e5867单独验收，不复位旧预算。
- 导航19和wechat16新回归：真实same_subject事实门禁不变、原会话成功导航桥接/失败及别会话拒；微信标签位置归属、重复块、平台同值不能授权、数字微信不能填phone、GET copyable/人工维护/失效/争议/原生Excel完整覆盖。新增末列旧下标测试改按表头语义，488完整通过后再执行新编排495完整。

- 新增空搜索实际read→extract无新正文零模型，旧Evidence保留；SDK提取超时/通用超时/ServiceError预算三分流，失败不记处理签名，后续同原文仍可分析；extract.partial SDK3事件触发原SSE确定性熔断，预算事件不触发。32专项，额外熔断17专项，最终462 passed in69.70s。真实284a3f先204893ms/13调用OpenAITimeoutError/0客户，同job恢复累计349433ms/20调用/211653tokens/1完整公司0联系/单根域，预算耗尽partial；旧失败保留，不说首次整图/自动降级已通过。后续859a8b联系任务44951ms/4调用/2读取无联系partial，Agent原文复核4→5确认未知，不借平台技术支持。

- extract-policy-5新增test_directory_analysis：纯分类词/长导航/派生附录不产事实，完整介绍（含生产）进入分析但不授角色，未知路径沿原分析；真实extract→S别名解析→save→API隔离链只替模型，不联网；混合上下文省纯入口，跨主体角色引用仍ServiceError。15专项、加运行Skill及terminal_resume后19专项通过。真实自主整图另查项目Agent，不把fixture保存算买家成果。

- ROLE_POLICY13最终完整450 passed in71.03s；正式无活动备份后部署、生产原10条未改。本轮实际217秒/0客户仍属业务未通过，不把联系列表格式回归或旧引文True算整图/多站完成。

- 2026-10-05联系列表回归：7种紧邻Markdown换行/空值/法人及其他字段隔断，实际save_candidate→API→Evidence检查连续原引文不改、不授contact_position；专项20通过。真实9eb7bd自主217秒/16模型/0客户partial，模型复核预算16→18沿原账本；修正格式后同原contact引文匹配通过仅为技术重验，不代表真实客户保存/深圳经营地点或第二站通过。

- 2026-10-05目录窗口新增行业/分店两模板×前8已读/满额第9主体4个实际gap/read/Broker缓存用例，原DOM40与实际1次剩余额度不变；首次2失败是正确平台轮换干预夹具及缓存同URL碰撞，限制单平台用例并为每次生成独立原href后通过，生产轮换规则未放宽。新增当前平台顺序/否定/仅查/权限说明不误禁、故意错误模型plan、disabled先于预算/旧成功、泛目录/重定向/新响应/跨job及同job缓存/新persist拒已禁源，原账本保留。
- 首轮全量1 failed/438 passed in83.73s：最小options={}离线MCP正文缓存诊断被新默认空名单误拒；保留“缺渠道字段”与“显式空名单”区别后46专项通过。后续缓存/跳转/保存补测101专项，最终442 passed in69.94s。真实0c434a首个qcc请求、无mall/brand读，0客户partial，不能说业务获客达标；目录40许可fixture不是公网第9企业获客证明。

- 2026-10-05读取阶段回归以真实Trafilatura/Broker/SSE/ToolCall验证空HTML200+备用429保留双阶段及安全UI摘要、原协议占位不外泄；直接ConnectError→备用正文成功且幂等复用、同Broker并发一空一成功不串诊断、旧坏状态不使投影异常。24旧专项/25新增阶段专项/21并发相关专项通过，最终424 passed in68.46s。真实17c4092入口诊断16966ms/2模型/1读取/0客户partial，实际read_outcome primary empty_body/fallback provider_rate_limited/http200/body0，Node单测及浏览器另验，不作新自主获客。

- 本轮最终421 passed in62.32s覆盖POLICY16；第四真实无客户名/URL任务fa01d643cdb7401b86144e2db311626a为79318ms/4模型/16读取/1同商户完整phone/单站partial，没有再读地板/洁具分类及无关公司详情，仍读灯具商品目录、第二站未取得，不能称全渠道/性能通过。正式10客户未变，QA无并库。生产已部署API1072/Worker8844、health ok，156日志无Key；修复组合绿不代替缺失外部多站证据。

- NAVIGATION_POLICY16新增同城裸标签灯具/地板/未知三分类DOM及旧附录测试，保持原链接、混合产品保留真实地板context，不靠编号猜品类。首次命令误写不存在test_navigation_heading.py无测试执行，修正真实三个文件后23 passed in3.47s。此前420 passed in64.04s仅覆盖POLICY15，第四自主任务/新完整回归待核；真实POLICY15未改善裸城市分类，不能用绿替外部验收。

- 2026-10-05public_website新增实际gap/read/Broker缓存验证同页四联系入口加第五跨站入口不遮蔽、有联系时跨站优先/无联系仍联系优先；directory_waterfall新增满额选页过滤已知无关公司详情、保留主体标签/本商户about/未知模板/分类及实际gap→read选原分类href。29专项通过，首次完整419 passed in73.39s。之后NAVIGATION_POLICY15新增明确不符品类/特殊灯具分类及混合产品保留，24专项通过，最终完整待核；mock不作公网客户获取证据。

- 2026-10-05新增test_contact_answer：实际parse/save/answer/SSE隔离账本验证漏电话模型草稿被新generation替换且最终Message一致，一次模型流，无追加请求；争议/失效/短号不作可用，解释/比较/原文复核不替换。专项11通过，全量416 passed in63.31s。真实871814回答节点沿原预算4→5给出完整主体/联系人/手机/来源及采购未知，原错误整图回答保留；此真实调用未触发漏项回退，回退由fixture验证，不称新自主发现或多站完成。

- 新自主adf95b349347439ms/10模型/12fetch/2不同市场/0联系/各1根域partial，i20原生工具实际命中；原答误写“来源于2026-10-05”，原预算10→11真实answer复核日期仅采集，相关26回归通过。两次整体时长/模型生成有差异，不把单次少7调用证明稳定快或完整获客。

- public-account-5新增市场目标实际extract→Broker.parse_account(target_roles=mall)→persist零提取模型；fixture覆盖标题前/后简介、外地/否定/服务/竞争主体/分店尾名不符/厂家角色拒、retailer原行为和不借Tel。首轮category quote只有2字违反Fact min3，改连续分区+首商户行并排Tel；角色厂家漏过滤修正。真实77bf第一版parse0后fallback4模型，不算原生成功，原实页标题在offset0、简介12、了解更多594揭示边界；850bd新诊断48200ms/3模型/1parse候选/1persist/零extract模型/0联系partial，未知字段未补。最终402 passed in65.78s，单样本48秒不代表整体性能达标。

- 新自主dd5fd869416479ms/17模型/12fetch/1市场保存/0联系/单站partial，未给名称URL，真实ROLE12 direct句persist成功；供应商仍限额，时长约7分钟不算性能通过。原误拒QA0客户不改，不将限页诊断混作自主获客。

- ROLE_POLICY12使用真实checked_candidate覆盖通用标题+完整主体逗号是商场、之一、否定、所在地/服务、另一法律主体、重复原句拒绝；首轮夹具缺captured_at修正后45专项，追加所在地/服务边界33专项，最终全量399 passed in66.39s。真实限页5146d413 51842ms/4模型/1fetch/零搜索/1市场保存/0联系partial，未借租户Tel；是诊断而非自主发现。

- bf5129真实降级任务380199ms/17调用/12fetch/0客户partial；用途筛选实际未再读西门子/CCGP。市场候选角色关联多次拒，不能把0客户称获客通过或增加预算掩盖，下一步Agent原文复核拒因。正式392回归与健康检查通过只证明各自范围。

- review_context新增最终响应URL可复核且不选同结果其他URL/失败/假后缀。public_entries覆盖市场自动兜底排西门子零售/CCGP、未知行业入口保留、明确采购step仍允许，真实gap适用入口耗尽就停止；首次kwargs导致旧lambda *args测试失败，调用改四位置参数后21专项通过。city列表别名/原值回归62专项通过，最终完整392 passed in62.74s。真实supplier限额整图仍待终态，不能作联系验收成功。

- ROLE_POLICY11 test_branch_identity新增两根域同市场/同地址、深圳市→深圳时save/Broker同ID且原city不改、满额仍补第二站；旧指纹带市归档仍拒。既有跨分店串号/不同ID/满额/归档专项共41通过，最终完整388 passed in62.47s。真实cd4aed原2ID缘于city原值深圳市/深圳，不能报告两买家，原QA不清；新限页Agent诊断218528正在执行。

- entity-objective-1专项以实际Broker/工具账本验证先泛查后同job保存主体会改变目标并新请求、相同目标成功复用、phone变disputed后目标改变且无原号、其他会话客户不泄漏。首轮改search参数破坏外部测试替身导致6失败，恢复既有search(args)签名后67专项通过；新增目标回归61通过，最终全量386 passed in62.65s。mock仅证协议/缓存，不证明改善真实获客。

- 最新完整385 passed in62.14s。最新真实4c6883beea344b489c151280dc9f4269整图136567ms/14模型/1保存/1完整phone/单站partial；Agent答复明确跨站未完成。无采购工具补电话，但有同品牌制造企业页仍被读取，因为未知角色摘要不强拒；不能称已清除所有歧义结果。正式10条未变，QA独立。

- 来源用途专项覆盖零售客户第二网站补查不改明确CCGP原step、下一官网仍主体补查；未核candidate+procurement gap仍非采购，真实project_buyer公告query不拼电话字段/未核名。目录首次补查原完整phone、持久attempts后不锁号码、短号不锚点。read_selection加入已存短品牌名与无关制造商摘要同名时仍跳过，显式URL例外仍可读；17 passed。最新全量正在执行，不能将前一383项绿覆盖后续修改。

- 2026-10-04：test_branch_identity覆盖混分店Fact拒绝、同名不同分店不同ID、满额不借同名、旧指纹归档不复活。profile专项明确产品不被questions限制说明阻断，缺产品仍询问。mall_account_parser新增成功页+空候选页只交未解析页给模型、超时仍save原生候选且不标签名完成；事件必须用emit传payload，不能把dict当record_event.message。
- 最新完整380 passed in63.09s；实际5bedc114同job首次130096ms/3调用模型超时零保存，修复后累计278679ms/8调用/7保存/3完整电话/4短号partial。2 fetch零搜索，2同名分店不同ID，无争议/地址继承。指定URL诊断不是自主发现；最后新增超时降级在fixture验过，本次真实恢复未再次触发该分支。

- test_uncontactable_index_candidate_does_not_block_early_directory覆盖无联系工商候选不挡目录、已有完整联系字段不抢原计划。真实26edca147558ms/16调用仅QCC摘录1候选/0入口partial，不算可联系获客成功；早期条件补丁专项17 passed。旧结果保留，不把未取得正文说成QCC全文已读。

- test_mall_address_ownership用真实checked_candidate拒继承商场地址、接受同商户Tel紧邻明确门店地址；实际save/Broker省非法地址/畸形website后全量校验，禁止模型请求。test_identity_context满额新公司页只带相关主体及身份证据，提示也不提其它旧客户。371 passed in63.73s；真实7b08有4保存/3电话，但479762ms/OpenAITimeoutError/partial，地址历史争议仍保留，新任务验证新版，未标目标完成。

- test_research_schedule实际账本验证平台前缀先执行、早期目录一步/同搜索计数一次、失败URL去重和未执行计划恢复；公平选择按attempts重试累计、已耗主体不再盲搜。新增未满额跨站/开放发现交替及extract仅聚焦本轮主体，旧身份页有界保留。partial分店回归首次1失败发现提前载入selected改变scope，恢复仅满额过滤后83通过；专项23通过。test_answer_context新增原文联系卡片，不拼接字段。

- 限页修复真实36d5c44b：24568ms/3模型调用/1 fetch/1 parse_account/2 persist、零搜索、2商户公开完整电话；已读Agent答案与账本，属于给已有目录URL的诊断，不计新自主发现。最新完整364 passed in62.34s；生产10条保持，测试库独立。

- 最新364 passed in60.70s覆盖每条name一致及答复替代值/计数/部分标记。真实319d13无名URL任务323945ms/20调用/2保存/1公开电话partial；后续仅answer_node真实复核两次沿原预算20→22，确认原回答将name争议错述为address并补完整替代值上下文；原错误答复/争议不修改。目录工具真实诊断89aad9已有URL、2商户虽通过persist，但额外搜索违反限页，不算完整通过；新增“不读取其他网页/仅复核此已读取目录”识别回归6 passed，正用新隔离任务核验scope。

- test_mall_account_parser使用真实parse_accounts/checked_candidate及extract→Broker.parse_account→persist：同记录完整电话、分区/城市、原名、无继承地址/产品推断，拒短号/其他分类/冲突同名电话/多分店。只禁模型及网络，不冒充真实网页获客。旧分店回归首次因粗URL模板识别触发无Job夹具的Broker guard失败，supports_template改为实际目录标题+灯具分区结构后恢复；真实guard不放宽。预算停止回归新增实际域名展示断言。

- test_read_selection覆盖精确exa.ai/library与伪子域、未知/混合/明确manufacturer目标、自主发现零fetch及用户URL例外；真实read_empty抑制被排摘要提取。test_repair_idempotency仅替structured，实际cached_model/ToolCall跨cursor同原文一次、新原文可重修；故意删name不保存且保留补查目标。角色新增真实checked_candidate拒名称内词、所在地宾语，保留明确身份谓词。首轮所在地用例2失败揭示名称经营部误作经营谓词，调用前剥完整主体后修复；专项92 passed。

- test_public_phone_owner使用真实checked_candidate及隔离库验证industry_directory/official不能借平台服务中心号码，明确客户块接受、其他企业及平台页脚拒绝。test_identity_context用真实extract入口连续两次补查，保留身份证据/当前新页、排除未引用旧页及上次补查页；模型替身不代表真实网络成果。343项完整回归通过，尚需真实Agent公开来源验收。

- test_read_priority以实际read验证标题/正文/地区及四目标排序；信号不作客户事实。test_contact_encoding用实际GBK及UTF-8旧GB2312声明、88b6c7f8扩展字节、线程/native stderr验证联系区/目录保留，排除隐藏父子节点。
- test_terminal_resume使用实际AsyncSqliteSaver/StateGraph/save/finish，终态旧策略仅extract重验、同策略仅gap继续；初态/网络节点替身明确禁止，来源/客户/7次模型预算不重置。首次三次诊断InvalidUpdateError后复盘，终态更新显式as_node修复，不称mock是公网恢复。
- test_role_ownership还覆盖单主体市场类型字段/目录/否定、旧persist策略拒绝不能跨规则升级复用，以及市场类型不能污染产品类别。真实同job恢复db330有5→8调用、未重抓、1市场无联系partial；12读自主3e091有2市场/1业务电话/两根域证据，模型预算停止partial，不能据此标整个目标完成。

- test_role_ownership覆盖否定直接/回指两入口、其他角色否定不误排、单主体连续介绍跨句、目录/竞争/重复片段/分区拒绝；实际save/gap保留被拒角色补查方向、空批次不抹去。test_proposal_summary以mall查询实际招聘URL验证域名展示，不冒充商场来源。外部整图另查Agent候选/拒绝/保存和联系证据，322绿不代表多站获客成功。

- test_reference_scope覆盖有链接限页/开放发现、实际read/gap受限后停止及关闭渠道；真实save/persist验证修引文不新增产品匹配。网络替身只证明范围约束，实际Agent的零保存/字段拒绝仍原样报告。

- 2026-10-04：test_extraction_history实际extract_node验证A→B→A只提取两次，产品/规则/正文变化重新处理；模型替身只证明调用去重，不证明真实模型提速。
- test_statistics_evidence通过真实checked_candidate覆盖空白/虚构scope、非法日期、日期精度、成立/发布/版权/型号日期与合法原文年度；test_mall_directory拒绝入驻名单前商场标题+总电话，保留真实后续租户形状。306项本地回归通过仍不代表真实多站获客验收。

- pytest本地执行，不接CI。
- test_app.py在导入应用前设置UUID隔离库；不得删真实数据或复用data/app/clientreach.db。
- 单元测试的“测试客户”仅隔离验证；真实任务另用已提供产品场景验证。
- 外部模型/搜索失败不能被模拟成功替代；诊断探针独立运行并报告真实限制。
- test_documents.py使用实际DOC/DOCX/XLS/XLSX/PDF文件、真实RapidOCR和LibreOffice；测试文件明确标记验证用途，不能当客户事实。样例保留.codex-tmp/document-fixtures，OCR模型复用本机缓存。
- 全链路真实模型/搜索验证使用独立数据库与8001端口，前端生产资源共用web/dist；最终部署到8000另查健康与迁移，不覆盖生产画像/客户来制造通过。
- test_harness.py覆盖等待首token/流停顿停止、普通解释与document路由、原生LangSmith本机HTTP收集器的嵌套与隐私。云端没Key不能宣称云端验收。
- test_tool_recovery.py覆盖真实图越过失败search后的resume、同操作并发、累计预算、供应商/站点冷却及同站并发排队重查。HTTP限制用隔离MockTransport，不请求真实429或提前重试。
- test_documents.py单页mixed PDF有真实文字标题+扫描正文，必须核对型号/价格与text+ocr；跨页混合测试不能替代单页测试。
- test_quality_contracts.py覆盖新来源/完整正文/长目录中段、GB2312原始字节与乱码缓存、独立采购公告、人工角色资格与非买家、空白跟进、追问CRM会话作用域、安全错误栈。
- harness覆盖供应商抑制CancelledError的停止与超时（业务等待有界、迟到内容不回写），以及实际SDK SSL上下文为标准ssl/CERT_REQUIRED/check_hostname/CA非空；保留用户SSL_CERT_FILE/DIR。
- interrupted_clock以实际最后活动测下界，不把停机500秒算进2秒已知耗时，且API带clock_is_partial。暂停工具账本/SSE累计耗时保持非零、状态paused、error=operation_paused。
- conversation_latency分别验证纯继续零模型复用与杭州/成都/武汉/苏州新目标进入结构化提取；真实模型地区覆盖探针使用.codex-tmp/verify-target-update.py的UUID独立库，不启动公网获客。
- test_knowledge_flywheel覆盖独立公告反馈不能绕过、真实FTS/ToolBroker产品知识进入load_context、learn实际产出影响下一轮同产品plan排序、重放learn不重复计客户，以及反馈不污染其他产品。真实6luna知识消费另用隔离探针验证，不用mock planner冒充模型验收。
- conftest强制普通回归LANGSMITH_TRACING=false，防用户真实凭据使测试上传云端；专项用隔离ROOT/夹具Key或本机collector。test_credential_sources覆盖独立文件来源/环境覆盖/空值关闭/模型与追踪Key不混用；真实云验收在.codex-tmp/verify-langsmith-cloud.py，须读取实际父子回执才能成功。
- test_source_channels覆盖限定域名/官方文档排除、指定平台实际规划、运行Skill加载、短号/失效联系、排序与导出、原页补读、联系侧栏和角色优先阅读。真实多平台另用.codex-tmp/verify-multisource-agent.py的UUID库，必须同时检查lead_count及contact_fields，不能把completed或搜索来源数当获客成功。
- 新回归覆盖登录/验证缓存与fallback、来源根域/明确来源数、未知采购字段不误强制渠道、空格联系人、同批冲突、现有证据修复、phonenumbers固话/分机/短号、项目编号精确筛选、结构角色关联及用户URL读取。graph模型替身按本用例job_id选来源且查询含UUID，避免共享知识/缓存让固定引文引用别的测试source_id；必须同时跑source_channels在graph前的顺序检查。
- test_evidence_precision覆盖完整主体/卖方排除/短ID、长引文角色、分段采购日期时间、同源反馈、并存电话及失效父值、采购联系方式归属、联系标签直接绑定。真实图多域成功与无联系partial另用隔离实际6luna/Exa任务，不能以fixture代替。
- test_procurement_projection验证同一采购公告多轮换引文只展示一次，完整原文保留、底层历史不改、不同截止不合并、失效反馈不被覆盖。
- test_mall_directory验证真实模板形状的分店上下文/隐藏父级/未知URL、长目录短店名定位、仅启用商场渠道的明确URL读取、品牌目录优先、相邻商户号码拒绝及法律主体不可生成。外部实际目录验收另留真实6luna/Exa隔离记录。
- test_isolated_logs实际触发小容量JSONL轮转并核对隔离DATA/logs；测试日志不能再向生产log/web写入。
- test_mcp_protocol_limit覆盖协议initialize限流、嵌套异常组、明确冷却和普通协议错误不误分类。真实限额到工具挡板/公开HTTP验证用.codex-tmp/verify-mcp-limit-fallback.py，不制造真实429；第二渠道未发送应没有ToolCall实际尝试，不能要求伪造attempts=0账本。
- test_public_entries覆盖无用户URL/无搜索来源的真实read/Broker路径、读取前无Evidence、未知链接拒绝、预算0不读、ICP地区/产品/关闭渠道限制及中段灯饰块。复用asyncio.run而非新增pytest-asyncio依赖；真实完整图另用无网址获客消息，不能用返回空来源的mock作外部验收。
- test_source_read_quality覆盖标题/URL假正文、旧上下文、1688已缓存资料仍遵守query通配robots且不冒充Googlebot、QCC567不fallback、空来源不生成Evidence/状态unavailable。test_conversation_latency已有有效MCP缓存禁止重复联网约定不可破坏；真实限制探针独立脚本，不用模拟响应冒充平台可访问成功。
- test_procurement_directory覆盖GB2312真实模板形状、隐藏行/外域/产品地区过滤、实际href许可与未知URL拒绝、read_node选链。模拟缓存只核验本地编排，不宣称外部详情成功；真实CCGP列表探针在.codex-tmp/inspect-ccgp-listings.py，终端JSON用ensure_ascii避免Windows输出编码误判。
- test_app增加行业语义验证：城市/主营品类不能因逐字命中写industry，明确零售业分类通过，即使城市被贴行业标签仍拒绝。真实模型复核需检查导出各列语义，不只核验source_id/引文存在。
- test_channel_status覆盖最近读成功不清检索受限、全供应商冷却与到期、空结果/单站失败及响应不含正文/Key。合成未来冷却账本必须按本fixture独立job_id清理，不能污染后续Broker全局挡板；不删除其他测试记录或生产记录。
- test_runtime_logs以真实PowerShell5.1验证BOM/解析、固定双日志原字节归档、另一服务不动与重复归档不覆盖。只在.codex-tmp唯一夹具目录执行定义文件，不dot-source根start触发生产启动；夹具保留，不递归删除。
- test_direct_read_completion覆盖限流后第三用户链接仍读取、读取前置失败无账本仍防空转、预算/关闭渠道、长名单第三主体和句号后排除、最新补读正文优先、单主体本商场角色及其他主体拒绝。真实三链接模型另在UUID隔离库执行，必须核对三页Evidence及逐主体实际保存，不能把三页已读说成三个客户。
- 同模块还验证同主体地址片段不重复建客户但保留争议、跨分店/不同来源拒并、新补读指定主体上下文不重生成已保存主体，以及图接口明确条件连线。真实测试模型超时不以mock成功替代，恢复保留同job/预算/来源；一个客户多ID不能算多个买家。
- test_public_account_parser覆盖模板原文/页头平台热线排除/未知字段省略、错误地区/模板/制造拒绝、真实Broker/extract/persist、卖方排除、三次SDK错误账本的无模型答复/SSE顺序、一般预算超时不触发模型熔断，以及恢复无新来源保留优先页。client确保隔离表已初始化；已有库的节点验收不等于整任务恢复成功，真实模板整图另用新UUID任务。
- test_directory_phone_pair核验HC23完整单主体双电话原文及争议父值，不从掩码补号；test_public_entries覆盖gap在检索受限后主动切公开目录、入口耗尽和零预算终止。真实自主验收不给客户名或URL，只交产品/地区/角色条件，并读取Agent最终分析。
- test_public_entries验证已有客户后仍实际选择下一目录及采购渠道关闭不能借directory绕过；test_direct_read_completion验证自主新主体不被旧名单过滤、只分析本轮新正文，用户明确多主体用例仍保留。真实CCGP无名无URL任务成功读列表但0客户，不能当采购获客成功。
- test_procurement_directory覆盖真实可见下一页href、外域/隐藏/脚本/倒页排除，公告优先但已读后下一页仍可选，真实gap/Broker许可与预算耗尽停止；列表零模型、详情仍模型。test_direct_read_completion覆盖满额新页不关联目标时零模型；真实同任务恢复保留原预算与历史超时。
- test_mall_directory覆盖分店列表真实href/隐藏/外域/重复/查询链接、ICP/原渠道/预算、列表零模型及同名不同分店满额排除。真实Agent无名称/URL输入取得7链接并读7分店，但8记录只有3有效电话，不能算8可联系企业。
- test_contact_projection覆盖无效电话/邮箱/网站与其他可用入口并存时的字段缺口；test_answer_context以12条大引文客户检验整批覆盖、原状态/统计口径/公告截止保留，不算真实客户验证。真实答复节点另核验8条记录全呈现与分店标签原文。
- test_industry_navigation核验真实href原查询/重复/空键、隐藏节点/模板/member/子域/外端口/凭据拒绝，40记录8候选限制、产品无关详情排除、真实Broker/gap/read授权与预算、入口零模型和导航从事实剥离。本地fixtures不当公网可访问或获客成功证明；实际无名称/URL任务另由verify-multisource-agent运行并查看Agent最终分析。
- test_mall_directory新增满额明确branch作用域在HTTP前过滤其他分店、真实gap/read转另一渠道；同分店/未知作用域/未满额不误过滤。跨站补查不能先耗光预算于品牌同名其他门店。
- test_runtime_source_rules验证全部11公开渠道同批完整包含、关闭平台不加载、授权项不误开放、没有既知客户名称/号码/详情URL种子，以及超限配置明确失败不截断。真实规划/获取仍另用项目Agent隔离任务，不能把规则测试当平台响应成功。
- test_candidate_selection以真实save/Broker/persist验证短号候选先出现时完整原文电话优先且只保存1条/1次工具调用；造引文/未知source/冲突不抢排名。graph/v2_audit/source_channels联合顺序曾暴露学习重排用户QCC优先级，现明确前缀不参与绩效重排；不能只单独跑source_channels掩盖记忆相互影响。
- test_proposal_summary验证3提议1保存、失败/修复/persist不当新提议、跨批同名计记录不冒充不同公司，未保存原文不送答复。真实回答节点379663另复核，节点成功不作新整图获客或耗时证据。
- 行业导航新增同平台真实子域/默认端口/HTTP原href、假后缀/外平台/凭据拒绝及商户根页不误跳过；九正gc-r地区分类零模型而数字店铺不跳过；同城物流/不同地区分类/商品/广告/移动副本排除。单导航耗尽用例隔离PUBLIC_ENTRIES避免新入口让正确换渠道被误当失败；外部真实无名/URL任务与主页资格探针严格区分。
- test_new_directory_policy用真实Protego/MockTransport覆盖两个新平台子域原query拒绝、crawl-delay与规则缓存，真实Broker已有正文缓存不绕过robots；不假装外部规则允许。test_directory_waterfall用实际gap/read查询隔离账本验证单平台4次后转未试门户、子域/失败计数及已存主体不拦；新入口提取测试无已选客户+旧公司正文仍新入口零模型。
- 分类上下文测试多个“深圳”分别属卫浴/灯具，按唯一小块原标题优先灯具；隐藏子标题、多个标题不关联，factual_body仍无分类附录。泛产品类别不得抬到目标城市公司之前，灯饰子域原公司href可读；导航测试不代表商户角色/采购或联系方式核验。
- test_graph_read_depth保留run_job/真实StateGraph/SQLite checkpoint/计时，外部业务节点替无网络输入，实际循环24读能到answer/learn、无GraphRecursionError；不把此fixture当实际网页/模型/客户验证。真实24读失败及同job恢复独立复核累计预算和旧失败，不重置调用/时长。
- test_review_context检查同job真实正文与URL对应、标题假正文拒绝；实际回答另逐条核对引文。test_manufacturer_target覆盖卖方/否定/嵌套经销商、显式厂家及省略错误可选事实后完整persist；test_public_subject覆盖主标题及实读旧双栏目结构、隐藏/跨块/竞争名字拒绝。厂家诊断不替代原成品灯经销商自主验收。
- test_directory_waterfall覆盖已有客户但无关链接仍切未试门户、主体标签才能豁免及八方s数字文章排除。test_contact_projection区分三URL/两根域、移动站合并与空证据，不把任务读页数算客户跨站证据；真实Agent多网站验收仍须看已保存字段来源。
- test_direct_read_completion实际read→extract隔离失败补读链有旧Evidence但零新来源时不得重新调用模型；旧证据仍保留。原恢复测试同时检查无新来源不丢recent待核页面，避免用跳过失败补读破坏显式恢复。
- test_public_website验证可见网站字段/标题主体、原查询、隐藏/页尾/凭据/歧义/平台关闭拒绝、工具注入附录不能作为自动Fact，以及真实gap/read/Broker缓存的选页许可。缓存fixture不是公网官网读取/多站获客证明；实际指定URL诊断须另读Agent回答/账本。
- test_budget_answer保留真实图/checkpoint/finish/SSE，以确定预算异常验证零保存也有账本摘要且不调用回答模型；真实失败任务另同job恢复检查调用预算不增长、历史错误不清，不能以fixture声称外部故障已恢复。
- 2026-10-09新增test_company_conversation.py：覆盖无公司后缀主体路由、普通问答/禁止检索隔离、同会话短确认、原始消息与research_prompt分离、标题投影、提交幂等；test_company_agent同时核验企业Company/ResearchCompany保存后可由conversation_id查询。真实6luna超时只能报告失败/可恢复，不用夹具替代外部成功。
- test_company_extraction_recovery保留原Evidence，核验无目标主体正文零模型、SDK超时保留缺口/事件且零Company、预算异常仍上抛；真实任务的跨来源继续流程另外检查ToolCall，不把异常夹具当供应商稳定性证据。
