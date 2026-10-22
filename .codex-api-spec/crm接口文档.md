# 需求描述

2026-10-10，Codex：上下游增加独立关系详情与真实对手方资料补查；简称先查证，歧义主体使用同Job确认接口，预算/checkpoint累计。新增接口完整定义见本文末“独立关系与名称确认”。沿用现有表和JSON字段，无DDL；Alembic head仍为20261009_04。

2026-10-09提速与可靠性修订，Codex：新消息仍由模型识别意图并新检索。`GET /api/companies`在分页前按最近保存时间降序。公司首批核验结果提交后先发`message.reset + message.delta`，补查结束以新的generation重置并发最终答复；客户端不可拼接不同generation。后台清洗和async checkpoint不代表事实已保存；persist事务及来源绑定完成才刷新企业卡片。无新增数据库表/字段，Alembic head仍为20261009_04。

Job.metrics新增可选`first_verified_result_ms`（提交至第一批非身份资料事务，毫秒）、`first_answer_ms`（提交至首批真实答复）、`pending_cleanup`（未完成清理数，0或缺失可恢复）。`POST /api/jobs/{id}/resume`若清理未结束返回409，error为“上一轮请求仍在停止清理，请稍后继续”，预算不清零；Worker重启解除旧进程在途标记。`GET /api/jobs/{id}/research`新增`pending_documents`（尚在后台整理的资料数）；搜索摘录整理后仍pending/has_full_text=false，不能当全文或事实。

项目引用追加buyer/quantity/project_number角色，各自source_id与连续quote。截止可为原日期或原时分秒，原文24:00仅输出该日日期并保留原引文，不推算次日；计划发布日期/文件获取期不填published_at。转载只在同买方、原始标题和真实日期等可核验条件一致时合并。企业原名直接查询`answer_mode=company_verified_summary`，来自数据库；自定义分析仍走模型回答。

历史重复项目/公告的原始行保留，以JSON `duplicate_of`逻辑归并，查询/计数/导出仅投影主记录并保留各来源独立引用；没有DDL。日期粒度不足而原文有明确时钟时可补齐，不能用同一天合并不同明确截止。前端同时显示首批与累计总耗时，首批不是模型首token。

2026-10-09研究v3修订，Codex：所有新消息提交返回queued，由模型intent节点识别quick/chat/document/research/company_query，恢复复用同Job成功决策。新增逐轮研究资料、数据集与LangSmith预览接口。企业结果仅来自核验保存的数据库记录；跨任务历史缓存可以复用，但新研究仍发起网络检索，历史复用不标为本轮新取得。旧“问候提交即completed/零模型”的调用假设失效，前端已改为SSE等待模型识别与回答。

2026-10-05每客户来源计数修订，Codex：普通research明确网站要求且有已存线索时answer_mode=verified_corroboration_summary，终答逐客户显示实际site_count，并汇总未满足客户数量；不请求额外回答模型，不把某条缺口套给全批。SSE协议/终态/指标原键保持；原文复核/解释/比较不套该摘要，混合渠道成功失败优先verified_process_summary。未满足多站或无联系仍partial，不把真实累计查询/模型预算重置。

2026-10-05渠道过程/异构名单修订，Codex：无HTTP参数或DDL变更。内部read_pages只投影真实有效正文页元信息，空摘要/标题URL/搜索摘录不作已读正文。普通research同渠道成功/失败并存时answer_mode=verified_process_summary，以已有SSE reset/delta/completed输出已存客户、多站缺口和账本渠道过程，不增加回答模型或网络调用、不作SDK熔断。解释/比较/原文复核/chat/document仍原流程。满额已知分店scope不被异站客户空scope撤销；网站链接排序按实际所属客户；跨站搜索将尽可先实际登记目录发现，原预算及显式平台前缀/用户URL/主体核验仍保持。

2026-10-05来源不足答复修订，Codex：无接口/DDL变更。回答模型上下文包含本轮网站要求，按每客户已存证据数说明不足；确定性联系摘要/SDK熔断/预算或异常降级保留同一site_target，不能在替换草稿时丢掉多站要求。既有SSE generation/reset/delta/completed及partial终态保持，追加缺口仅依据实际已存证据；不模拟模型流或新增网络/预算。

2026-10-05编排修订，Codex：无HTTP入参或DDL变化。当前消息明确“先尝试/先查/优先查”渠道优于画像先出现的渠道名词，仍受启用/否定范围；required_sites对“两家不同网站/两处独立来源”等量词识别为2，普通“两家客户”仍1。既有metrics.corroboration.required_sites按实际当前任务要求返回，来源不足仍partial；不改旧任务历史。

2026-10-05公开微信修订，Codex：Fact.field与CandidateBatch.missing_fields新增wechat；LeadInput.wechat可空字符串、最大64字符，清空沿原PATCH字段清空语义。自动字段要求明确微信标签、完整原值、连续引文及同主体归属；掩码/昵称/同号描述拒绝，重复引文逐实际位置核归属。仅微信标签公开的数字不得填phone。GET列表/详情facts.wechat追加copyable布尔投影，格式完整且非失效/争议才true，不存回Fact，不证明账户可添加；PATCH仍返回原serialize响应，需要GET读取contact_summary/copyable。人工更改记录manual_fields并重算资格/资料分；空值不制造联系方式。contact_summary.usable_fields/missing_fields支持wechat，电话缺口不因此取消；不会生成tel/weixin链接。原生Excel在末列新增“公开业务微信”，3表/冻结/筛选保持，无DDL。

内部NAVIGATION_POLICY19只复用完整主体实际href及成功原会话读取账本作为有界联系导航，不新增身份Fact/别名；ROLE_POLICY16参与重验，原任务预算/失败历史不清。主Skill1106字符，全部11渠道运行规则5971字符，不静默截断6000上限。

2026-10-05提取恢复修订，Codex：无新HTTP字段/DDL。空检索且无本轮新正文不重分析旧Evidence；确认SDK提取超时生成extract.partial事件并继续原预算内允许渠道，零候选不捏造，失败页保持未分析状态、不记已完成提取签名。既有warnings中的extract_model_timeout使最终partial；累计三次确认SDK事件可触发既有确定性答复熔断，新增识别extract.partial事件，预算/通用超时不当模型故障。确定性SSE结果补一句资料分析未完成，不变generation/reset/delta/completed协议；原失败账本不清。

2026-10-05目录正文修订，Codex：无HTTP字段/DDL变化。extract-policy-5/ROLE_POLICY14仅区分路径导航分类和纯导航内容；真实完整主体业务介绍进入项目Agent结构化候选分析，纯入口不进混合模型上下文。客户、角色、联系归属及来源条件仍完整persist核验，路径/介绍匹配不授资格。混合生产/经销依明确经销原文处理，未确认采购不填；升级恢复保持原预算和历史错误。

2026-10-05联系列表修订，Codex：无HTTP字段/DDL变化。ROLE_POLICY13仅识别原联系标签紧邻单换行Markdown列表姓名；连续引用和公开原值不改，不跨其他字段或将法人当业务联系人。公开业务联系人不要求证明采购岗位，contact_position仍仅有独立原文才可填。完整主体、角色、地区、联系归属及跨站完成条件仍独立核验，旧拒绝/客户不重写。

2026-10-05当前渠道约束/窗口修订，Codex：无HTTP字段/DDL变更。当前消息明确平台按出现位置执行；可识别的明确禁用/仅查作用于该任务options及恢复，不修改全局settings。被禁平台不发请求/不占实际尝试，已知平台不能借泛通道/缓存/跳转用于新证据或新保存；旧真实CRM/账本不删。内部public_entries第五可选prompt支持当前否定，空沿原设置。原DOM已采集40链接在去重/主体/分店过滤后取原读取预算，不先截8；单批客户/数量/模型预算保持。无搜索可执行时409语义文案为“本轮没有可执行公开来源，请调整本轮渠道要求或来源设置”，不误称全局配置全关。未发送平台不算尝试，来源不足仍partial。

2026-10-05读取摘要修订，Codex：对外工具投影新增可选read_summary字符串（未知/成功通常空）。GET会话/任务工具记录与tool.finished SSE提供相同摘要；例如“网页无可用正文，备用读取服务受限”，前端失败详情优先该字段，旧记录无值用原错误文本。原error/status/attempts/elapsed_ms/冷却不变，不新增DDL。ToolCall.result内部read_outcome只保存主/备用状态及HTTP状态/正文长度，不出工具UI、无原文/Key/协议；Agent仅消费受限人话摘要，无正文仍零Evidence/零客户，HTTP200不代表来源读取成功。NAVIGATION_POLICY17只改变商品目录选页，明确用户URL及同商户新闻权限保持。

2026-10-05裸城市分类修订，Codex：NAVIGATION_POLICY16仅内部DOM导航选页变更，无HTTP/DDL。保留同小块唯一可见分类context；九正企业首页地区链接仅写当前城市且无实际分类时跳过，不根据URL编号/结果页标题反推分类。旧导航附录也执行该选择规则。读后主体/电话/角色/采购证据校验及明确用户URL原范围保持。

2026-10-05跨站调度修订，Codex：无HTTP/DDL变更。已存可用联系而所需根域不足时优先真实新根域链接；聚合链接不再先截4条后过滤已读，Broker沿同允许集合复核。满额只补既有主体，已知目录模板中的无关公司详情不读，分类/未知模板及明确用户URL按原范围；明确品类不符分类不靠同城市加分。客户值/身份/电话归属/采购/原预算不改；网站不足仍partial，不能据读取成功标平台获客成功。

2026-10-05联系交付修订，Codex：无HTTP/DDL变更。标准research联系结果漏完整主体/有效联系原值时，最终answer_mode=verified_contact_summary，以新generation_id的message.reset、message.delta（完整真实摘要）、message.completed替换草稿，客户端须清旧内容；没有新增模型请求或SDK熔断。解释/比较/原文复核/chat/document不适用。既有客户明确续查可载入其实际引用身份证据，联系页只从原同源同商户可见导航选取，新字段完整persist核验。原生产客户和历史错误结果不改。

2026-10-05时效回答修订，Codex：captured_at原字段保持，含义仅系统采集日期，不能作为网页更新/发布日或营业证据；没有明文来源日期时回答时效待核。原字段/数据库事实不改，无HTTP/DDL变化。

2026-10-05模板复用修订，Codex：无HTTP/DDL变更。内部parse_account新增可选target_roles（最多5个既有角色，默认空沿旧商户语义），只作用于已取得且启用来源，不扩权限。PARSER_POLICY=public-account-5，模板mall完整名称/直接身份/同分店标题及城市原句校验，category仅实际入驻分区；电话/地址/法律主体/采购不补。原生候选仍persist，全量校验失败保留日志；无解析结果仍模型，不伪称全页核验完成。

2026-10-04直接身份修订，Codex：无HTTP字段/DDL变更。ROLE_POLICY12支持同源name及唯一连续原句“完整主体，是…原角色词”的主谓关联，通用网页标题不误拒；角色结束首句，否定/其他法律主体/所在地或服务动作仍拒。买家角色mall仍只证明公开场所定位，不确认工商运营公司、现行营业或采购；原预算/旧争议/拒绝日志保留。

2026-10-04复核/兜底/筛选修订，Codex：无HTTP请求字段/DDL变更。已有原文复核可按fetch原请求或成功响应最终URL对应本job正文，不误称重定向页面缺数据。自动目录兜底按明确目标角色排无关入口，未知用途及明确采购步骤/用户URL保持原权限。GET /api/leads city筛选接受深圳/深圳市等已有行政后缀比较等价值，展示原city不改，不拼地区或补统计。

2026-10-04城市比较修订，Codex：无HTTP/DDL变更。ROLE_POLICY11身份键仅将三字以上城市末尾市作为比较等价，原Lead.city和city引文不重写；同name/address的深圳与深圳市复用一个ID，满额仍可补第二网站。已知不同分店继续不同ID，归档旧指纹同地址不复活，原QA重复记录不自动删除。市场名称不代表工商运营公司，不把记录ID数等同不同买家数。

2026-10-04检索目标修订，Codex：无HTTP/DDL变更。MCP web_search_exa实际objective参数带当前job已存原名/城市及有效phone/email作为补查背景，目录门店不扩工商名，其他会话不混入。内部ToolCall搜索policy=entity-objective-1+目标hash，成功结果内部新增search_context_hash用于同query目标一致性缓存，公开工具摘要仍白名单，无字段透出/正文/密钥。目标变化重新调用仍遵循原attempts预算与冷却，不伪造第二网站证据。

2026-10-04来源用途修订，Codex：无HTTP/DDL变更。零售/经销身份、联系、第二网站补查不覆写明确采购step为门店名，保留该平台原尝试但清主体focus；追加步骤按实际用途选来源，未核candidate不作采购人。分店短名第一次补查可带已校验完整原电话，后续按持久attempts回原名；不改客户原值、不证明接通/跨站身份。读页发现过滤的已存客户例外仅实际引用source_id/url，不再仅名称子串豁免无关厂商；用户明确URL规则保持。

2026-10-04分店及提取修订，Codex：无请求字段/DDL变更。ROLE_POLICY10拒跨分店Fact，错误“商户分店证据不一致，不能合并不同分店的联系方式”；同名同城不同分店新建不同Lead ID，display_name不改，原归档记录仍保护，满额拒新分店branch_identity_conflict。旧历史指纹/争议不重写。已有明确产品不因画像模型questions误写限制说明而needs_input，缺产品仍询问。extract-policy-3成功原生页不重复模型生成；未解析页模型超时且有原生候选时SSE事件extract.partial仅含error/parsed_count/pending_source_count，无正文/号码；候选仍persist完整核验，extract_model_timeout使任务partial，未处理签名不缓存为完成。取消/预算/其他异常保留原处理。

2026-10-04无联系候选降级修订，Codex：无HTTP/DDL变更。早期登记目录触发条件为未到max_leads且现有客户按contact_view没有可用phone/email/website；单有工商/行业摘录候选不封锁联系记录发现。明确平台真实尝试、同搜索轮一次、原预算/权限/URL去重与计划顺序保持，不把摘录候选当已可联系客户。

2026-10-04商户地址归属修订，Codex：无HTTP请求字段/DDL变更。ROLE_POLICY9对已验证目录retailer的address要求同商户Tel紧邻明确商户/门店/店铺/铺位地址原文，继承商场总地址返回“商户地址必须来自该商户独立记录，不能继承商场总地址”。该非法可选address及原畸形website错误可省字段后全量persist重验，不补值、不放松名称/城市/角色/电话归属。旧Lead地址/争议不自动改。满额详情上下文仅本轮实际出现的已存主体，普通发现和多主体新页保持。

2026-10-04早期目录/公平补查修订，Codex：无HTTP请求字段/DDL变更。checkpoint内部追加direct_read_target（已许可URL/channel）、early_directory_after（已做早期入口的实际搜索累计数）、enrichment_name（仅当前主体补查焦点）；不在公开state白名单返回。明确平台以实际ToolCall为准先执行，零保存时有界直读登记目录；只读步骤插下一cursor保留原计划，成功/失败尝试URL去重，原权限/读取预算不变。主体额度按持久attempts累计，最少次数优先、耗尽不盲搜；明确跨站要求时未满额也交替补主体/发现新客户。answer_context内部补最多4个连续联系证据卡片，name/phone同quote精确去重，不拼接/造关联，仍不确认工商实体/采购或营业时效。

2026-10-04名称/答复字段/限页修订，Codex：无HTTP/DDL变更。ROLE_POLICY8每条name Fact须与display_name归一后完全相同，混入第二简称也返回原“客户名称必须有对应原文name字段证据”，有界修复仍保留完整主体。answer_context内部附每字段最多4条精简alternatives、alternatives_count及alternatives_truncated，不改数据库原替代值，回答不能把name争议转述成address争议。reference_only补识别“仅复核此已读取目录”“不读取其他网页”，必须当前链接存在，plan直接read/gap不拓源；开放发现保持。

2026-10-04商场目录工具修订，Codex：无HTTP请求字段/DDL变更。内部parse_account仍接source_id/channel，沿原任务来源许可及启用渠道校验；已核验乐安居分店详情新增灯具商户候选批次（最多8条），原短名称、同商户完整电话、灯具分区由Pydantic输出，再逐条persist_lead核验，不继承商场地址或具体产品/采购。未知/非灯具分区、短号、多个分店、同名冲突电话不产候选。PARSER_POLICY=public-account-4参与工具缓存及提取签名，旧工具账本不删。预算失败降级摘要补传fetch.pages显示实际域名，不称读取成功为客户核验成功。

2026-10-04读取去噪与角色修复修订，Codex：无HTTP请求字段/DDL变更。checkpoint内部read_skipped最多64条source_id/reason，仅记录自主发现摘要被拒读原因，非对外客户事实；没有新正文且已拒读摘要时read_empty避免旧摘要重提取。ROLE_POLICY7拒公司名称内部角色词和所在地描述当经营角色，错误仍为“角色原文没有与该客户主体建立关联”。明确角色字段/身份谓词仍走原文完整校验；旧操作不删除，新策略重验。修复工具label去除cursor、加入策略，真实job+prompt键支持跨轮幂等；无name或丢原城市证明的修复结果不替换原候选，不新增模型预算或API权限。

2026-10-04普通网页电话归属修订，Codex：无HTTP请求字段或DDL变更。persist_lead的phone除原文/完整号码检查外，普通非采购页面需通过同源客户联系块或单主体页关联；最近平台联系标题、其他企业号码拒绝，错误为“电话未与该客户主体建立关联，不能借用平台或其他企业号码”。商场商户及采购人专用规则保留；归属拒绝不作为可选字段静默省略。ROLE_POLICY升级6以重验旧提取/保存缓存，旧Evidence/错误不删除。extract历史仅保留已存目标引用的身份证据和新正文，不改变保存完整原文验证或原预算。

2026-10-04终态恢复/联系区/市场字段修订，Codex：无新增HTTP入参或DDL。checkpoint新增内部validation_policy；同job/schema到END的partial恢复保留原来源/画像/计划/预算，不从空初态重做。角色/字段策略改变时仅重验已有正文并重新persist，同策略继续gap，明确as_node避免终态推断异常，旧ToolCall保留。ROLE_POLICY参与提取签名及persist缓存键；公开HTML联系区/目录统一解码并排隐藏子节点，旧有效Evidence缓存不重写。单主体市场类型/类别灯具市场、灯饰专业市场支持mall；categories原文引用市场类型的场所词返回“市场类型不能替代主营品类；缺证据请省略categories”，Agent可省略该可选字段再完整校验，不自动清历史争议。搜索标题/正文排序仅优先读页，不是资格/联系验证。电话format_valid/tel链接只表示格式可用，旧目录/不同根域证据不代表接通或独立调查。

2026-10-04角色结构与来源显示修订，Codex：无新增HTTP请求字段或DDL。角色Fact不接受否定语义，直接主谓及单主体回指入口一致校验；单主体完整标题/同源name下，仅完整主体开头的≤700字连续介绍及紧邻主营/专业句可跨句关联，竞争主体、目录分区、重复片段仍拒绝。内部checkpoint追加candidate_targets（最多3个完整主体补查名），仅name及引用已通过、角色关联被拒时登记，非CRM事实，不在公开state白名单中返回；下一允许渠道有界补查，原每主体与总预算不变。渠道字段继续代表请求路线，不授予页面类别；零保存摘要按实际成功fetch.pages域名列已读来源，工具前端读页标签为实际URL hostname，搜索标签为检索方向。候选账本proposed_records>0不回答0提议，未知工具错误用中文说明。

2026-10-04跨站候选规则澄清，Codex：无HTTP/DDL变更。单源具备完整主体/目标地区/明确买家角色的候选可以进入persist，required_sites仍由原gap/finish作研究完成约束；第二网站、电话或产品待核不等于主体无候选。资格原文校验不放宽，缺口仍partial，不把单源称跨站成功。

2026-10-04指定页面范围修订，Codex：无新HTTP参数/DDL。当前消息明确链接且仅复核/禁止其他页时，checkpoint内部reference_only=true；plan直接read，不能搜索或沿目录/网站外链补查，全部指定页已尝试或预算耗尽后整理真实结果。缺少电话仍partial，不造联系资料。开放跨站获客不受此规则限制。证据修复保留初次matched_products并仍校验用户产品范围，不允许修复器新增产品；无新增对外state投影。

2026-10-04提取历史与统计校验修订，Codex：无新增HTTP入口/请求字段/DDL。Agent checkpoint增加extraction_hashes（最多64个成功上下文签名），失败不标已处理；画像、规则、目标、来源正文或URL变化仍重新提取。自动headcount/revenue的scope必须是同quote原文，effective_date只接受原文支持的合法YYYY/ YYYY-MM/ YYYY-MM-DD统计周期，不补精度，不用成立/发布/版权/型号日期。错误仍为“营收/人数需要统计日期和主体口径，否则应留空”；Agent可省略被拒可选字段后完整重验。商场入驻目录仅标题之后的独立商户Tel记录支持retailer，标题及名单前总电话不支持；原QA历史不回写或混入生产。

2026-10-04企业外链与预算答复修订，Codex：无新HTTP请求字段/DDL。fetch_source可在原启用渠道/公网/robots/预算内读取同任务已存主体、原正文实际可见的网站链接；必须同源name及单主体标题绑定，链接仅授予读取许可，不是客户Fact或官网认证。平台关闭仍拒绝，非已发现地址仍url_not_discovered。导航附录不参与has_content或自动Fact引文核验。确定的模型/累计时长预算停止可追加Job.metrics.budget_exhausted=true、answer_mode=budget_summary，保留原错误和failed/partial终态；SSE给实际已存结果或0校验线索账本摘要，不增加回答模型调用、不模拟token流、不清预算。预算停止不是模型熔断。

2026-10-04失败补读修订，Codex：无新增HTTP请求或DDL。Agent checkpoint/图字段增加read_empty布尔，仅用于直接导航无来源时跳过旧上下文重复提取，原Evidence、ToolCall及缺口不删除。每次读取重算，成功正文/有效缓存解除；显式恢复仍核验待处理来源，原预算不变。不会将跳过重复提取称新增客户或多站核验成功。

2026-10-04来源统计修订，Codex：Lead.contact_summary追加site_count整数及sites字符串数组，来自该客户evidence的根域去重；source_count仍是客户证据按URL去重的页面数，sources保留页面链接。无证据为0/[]；同根域移动站/多页面合并为一个网站，网站数不代表独立调查或当前业务确认。本轮其他客户/目录页不计入该客户。无新HTTP接口、DDL或请求字段；前端来源折叠分别显示网站与页面。

2026-10-04，Codex：无新增HTTP入口/DDL。ResearchPlan.target_roles接受manufacturer仅用于当前明确厂家买家画像；Lead.qualification.manufacturer_target布尔记录该条件，默认false，角色manufacturer本身不代表符合目标或已采购。修改联系字段沿用原资格，nonbuyer反馈仍阻止资格恢复。零保存且非指定原文复核时，Agent答复按实际工具账本生成Markdown，Job.metrics.answer_mode=verified_empty；不会将未通过候选或页面标题说成已核验线索，不调用回答模型，SSE仍reset/delta/completed。model_circuit_open只有同job三次明确SDK超时才为true，零结果本身不是熔断。原文复核可使用同job真实读取正文，未入CRM不代表未读到。

2026-10-04分店发现与联系投影修订：无新增HTTP或DDL。Agent可从本任务实际读取的乐安居分店列表派生同站分店href，列表不生成客户；仍受原渠道/ICP/读取预算限制。contact_summary.missing_fields现在也包含格式无效的非空phone/email/website，其他有效入口不会掩盖该字段缺口。联系人/邮箱争议与失效状态保持原字段返回，列表及结果面板使用统一组件展示。answer_context按完整客户列表压缩输入，不再切整批JSON导致漏项；原事实/来源不改写。

2026-10-03采购续读与无效分析修订：无HTTP/DDL变更。公开采购列表可沿本任务正文的可见下一页href续读，匹配公告优先、已尝试链接过滤、原预算保留；页面脚本或页码不授予URL许可。列表不会生成采购人候选或消耗提取模型，详情保留原核验。满额补查无目标完整名称的新页不再重提取旧事实。答复读取实际pages标题/URL说明覆盖范围，供应商限额不代表网页平台整体不可用。

2026-10-03自主验收修订：无新增HTTP接口或DDL。检索供应商限额后可在原预算内直接读取已登记公开目录，工具账本/SSE仍报告真实读取；最终回答使用实际search/fetch/persist轨迹区分未请求、受限、已读取与保存失败。HC23已知完整单主体模板加入parse_account，缓存及提取策略同步版本化；原有争议事实不会因此自动清除。

2026-10-03补查修订：已有客户但尚未满足数量/字段/来源要求也可走目录读取，任务原预算保持。自主发现与指定名单分开；达到上限后的新客户仍由Broker拒绝。CCGP列表仅提供发现入口，暂无符合条件的公告时返回partial和0线索；没有接口或数据库字段变更。

2026-10-02，Codex。Client Reach v0.2，LangGraph对话获客、上传、持久checkpoint、SSE文本增量、知识/记忆/反馈与CRM。实际完整机器契约：`GET /openapi.json`；交互入口 `/docs`。以下示例为接口说明用例，不是企业研究结果。

# 接口概览

2026-10-03模板/答复降级：持久工具轨迹新增parse_account（仅已取得source_id与原channel的白名单Pydantic参数，无自定义正文/规则），界面只给“解析商户资料”、原页链接和真实耗时。已知模板输出仍经原persist校验，卖方排除与角色不变；未知模板走模型。Job.metrics可追加answer_mode=verified_summary/saved_summary、model_circuit_open、model_timeout_count：同任务已有三次明确SDK超时才触发模型答复熔断，普通预算TimeoutError不算模型失败。研究超时已存结果可生成确定性Markdown，SSE先reset/delta/completed再发原partial/failed终态，错误与预算保留，不伪装LLM流式生成。无新HTTP入口/DDL，已耗尽预算的任务不重置。

2026-10-03去重/图修复：自动保存同一完整主体、同一明确单主体页面的地址片段差异时复用客户ID并标地址争议，不占第二个客户名额；不同分店目录或无主体证明仍分开。GET /api/agent/graph显式列出条件连线（包括gap→read/decide/answer），不是改变流程语义。无请求字段/DDL改变，原始引文与冲突值保留。

2026-10-03多链接研究修复：搜索限额不再让gap跳过尚未处理的用户公开链接；在原读取预算/启用渠道限制内直接read，不追加搜索决策。图State字段清单增加read_attempted_urls、recent_read_source_ids、direct_read_pending业务键；任务state接口的白名单保持不变，checkpoint按既有job_id持久化；原source_ids仍仅真实来源。新读正文优先进入提取，“以下/下列”同一句多主体名单不受60字窗口漏项，句号后其他主体不自动纳入。没有新请求字段/接口/DDL；读取成功数仍不等于验证买家数量。

2026-10-03渠道实测投影：GET /api/channels每项追加runtime.search/runtime.read，包含status（最近ToolCall原状态，无记录为unverified）、label（人话最近结果）、checked_at（上海时间或null）、source_count（来源数，不是客户数）、elapsed_ms（或null）；search另含cooling_down布尔。能力status=ready不表示平台保证可访问，enabled仍来自设置。供应商冷却作用于检索，站点失败不扩散其他渠道；到期cooling_down=false仍保留最近受限记录，不宣称恢复。返回不包含正文/查询/凭据，接口只读不触发网络，无DDL/破坏性字段变化。

2026-10-03字段语义校验：自动persist_lead的industry必须有明确行业分类原文，不能是当前城市或仅主营品类；无证据省略，否则既有工具校验失败并走有界原文修复。人工行业录入保持既有契约。无新字段/DDL/接口，原始失败Evidence保留，不写生产测试客户。

2026-10-03公告目录跟进：fetch_source允许来自本任务已取得ccgp网页正文中实际列表href的详情链接，限定已验证gkzb模板、同渠道、本轮地区和照明产品，未知链接仍url_not_discovered。图首次目录读取有剩余预算时跟进一个详情，不增加请求字段/DDL/接口；ToolCall、SSE、取消与预算保持既有语义。列表只供发现，采购事实与联系归属仍在详情独立校验。

2026-10-03读取质量与平台限制：fetch_source增加安全错误site_robots_disallowed（页面不允许自动读取）和site_policy_unavailable（规则暂不可核验），status=unavailable，不回传robots/供应商正文。1688规则404/410按无规则、429按站点冷却，其余未知不读；缓存/重定向也核验，不伪装搜索引擎UA。QCC567为既有site_access_restricted。只含标题/URL的正文返回empty_body、sources=[]/status=unavailable，不生成Evidence，旧归档保留但不作为模型网页正文。无新接口/DDL；普通有效缓存继续复用。

2026-10-03自主目录补查：无用户网址且检索无来源时，已启用mall_directory/brand_directory或directory父渠道可按本轮ICP读取已验证公开入口；仅登记URL，不制造客户/来源。fetch成功后来源与已有ToolCall/SSE/预算契约一致，仍记录实际平台、读取时间与未知项。provider_rate_limited未消除时保留partial及警告，不能将读页成功当搜索恢复。无新接口/请求字段/DDL。

2026-10-03商场目录修复：自动retailer角色支持已验证分店入驻品牌标题+独立店名紧邻电话的明确列表，phone须与同一条记录匹配；仅有品牌展示不满足。display_name仍为原文店名，不生成公司名称；商场位置在address.scope标范围、独立铺位未知。reference_urls在仅启用mall_directory/brand_directory时也可实际读取相应公开入口，不能因未启用official而丢掉链接。无新请求字段/DDL。

必要时evidence增加field=city的独立同分店介绍引文，仍为真实连续原文；不拼进name。协议初始化阶段限额也返回既有provider_rate_limited状态与retry_after_epoch；未发送的挡板搜索没有实际ToolCall尝试，公开HTML仍可执行。默认60秒为冷却下界，不代表免费额度届时恢复。

2026-10-03证据精度补充：procurement_signals增加可空buyer_quote/deadline_quote，分别为同一source_id的采购人及截止连续原文；quote为项目原文，旧记录缺省为空。facts.phone.alternatives的relation=additional_contact表示明确并列公开号码或相同拨号值，派生contact_href只读；父事实失效/争议时该链接为空。其余不同号码仍保留争议，不以号码格式通过证明接通。Job.metrics.contact_gaps保存无有效电话/邮箱/网站的客户ID，研究预算结束仍不足时status=partial。Excel事实表末尾增加采购人引文/截止时间引文，旧13列位置不变；无DDL变更。

2026-10-03公开多渠道扩充：GET /api/channels由source_catalog统一返回渠道id/name/status/description/provider/mode；public_index表示公开索引和网页能力，不表示授权API或保证电话完整。新增brand_directory/mall_directory/industry_directory/b2b_1688/qcc_public/ccgp/sz_procurement/public_registry，可由PATCH /api/settings的enabled_channels启用；company_api/rfq/intent仍待授权，尝试启用返回422。用户本期明确没有平台权限，未调用收费API。

GET /api/leads及详情新增contact_summary：usable_fields是phone/email/website的有效入口字段数组，status/purpose为联系状态及用途，missing_fields保留缺口，phone_incomplete表示短号，sources按URL去重包含platform/channel/title/captured_at。号码格式可用不代表接通或确认采购。失效/争议/掩码电话不能用于联系动作，原文8位短号不擅补区号；列表先按资格，再按有效联系入口，再按资料分排序。

2026-10-03第二轮：contact_summary增加phone_status（empty/masked/incomplete/invalid/format_valid）及phone_href，facts.phone增加只读contact_href；链接由phonenumbers离线生成RFC3966，原value不改，未通过格式/失效/争议链接为空。固话异常9位本地号码不提供拨号。Job.metrics.corroboration提供required_sites及lead_sites映射；用户明确跨站要求未满足时Job.status=partial，不能以有一条客户代替完成。工具新增site_login_required/site_verification_required错误码，status=unavailable；普通页脚登录链接不是限制页。当前用户明确给出的最多4个公开链接可供fetch_source读取，仍需启用渠道/公网/预算，链接本身不成为Evidence。无DDL变更。

POST/PATCH /api/leads新增可空字符串website/contact_name/contact_position（分别为联系网站、客户联系人、职位），人工录入明确标人工，不改写为公开证据。自动Fact扩充这三项和credit_code/registry_status（信用代码/登记状态），仍需真实source_id、连续quote和值原文。Excel主表增加邮箱、网站、联系人/职位、信用代码、状态、用途、缺口和来源平台；证据表增加渠道/平台，未知留空，三表及旧列顺序保持。

2026-10-03追踪凭据补齐：GET /api/tracing 的configured现在同时识别环境LANGSMITH_API_KEY及用户apikey.txt独立LangSmith字段/lsv2_行；enabled仍需开关且有效配置。无Key关闭，响应不返回凭据。环境显式空值优先关闭文件Key，模型Key不代替追踪Key，运行配置不等同云上传成功。

2026-10-03空Word修复：POST /api/attachments 对只有空表格或空嵌套表格的DOCX返回400“没有可分析内容”，不把生成的[表格]标记当正文。既有有文字表格、图片OCR与DOC转换路径保持。

2026-10-03知识飞轮修复：POST /api/knowledge 新增的product资料会被后续research的知识工具检索并进入有界产品背景，非公开客户证据，不生成source_ids。POST /api/leads/{id}/feedback 同时保留独立公告快照并禁止纠错/失效信号旧证据复用；同一公告不能新建无状态记录重新得分。记忆recipe JSON增加credited_lead_ids，用于learn去重与销售反馈精确归因；无SQL schema变更。

2026-10-03采购/导出修复：Lead响应增加procurement_signals数组，保留source_id/url/title/quote/stage/deadline/participant_role/verification，并提供selected和display_status。无公告返回[]；过期/争议/失效不获采购加分，列表排序、详情、导出按当前上海时间刷新派生分。原始公告阶段和历史不改写，无新公告不清历史。

Excel仍为三张表；事实表追加替代值、口径、统计日、来源及采购公告阶段/截止/时效。主表增加数据状态，买家角色仍最后列。前端导出使用当前已显示列表的已应用筛选，未提交输入不生效。错误反馈标记公告争议/失效并停止采购加分，原值与引文保留。

采购公告展示数组按source_id/buyer/participant_role/deadline去重，保留最完整分段引文及selected标志。同组失效/争议状态优先；原JSON历史不删除。不同截止的更正公告保留独立项，去重不意味着两个来源独立核验。

2026-10-03计时补充：metrics.clock_is_partial=true 表示异常中断存在未知尾段，elapsed_ms是已确认下界，前端显示“≥已确认耗时”。不能当精确总时长。tool.finished在暂停时也返回status=paused/attempts/elapsed_ms/error=operation_paused，耗时包含本次已执行部分。

2026-10-03停止修复：取消检查仍约0.4秒；外部任务取消清理最多等0.5秒，流关闭也有界，迟到返回不进入回答。paused表示应用已停止本轮等待/输出，不保证供应商停止计费。resume的POST等待中前端禁止重复操作和同会话发消息，收到真实状态后再继续SSE。

2026-10-03质量修复：PATCH /api/leads/{id} 修改buyer_role/phone/email/address时同步重算qualification.role/eligible与score；既有非买家反馈不会因改资料自动恢复资格。POST /api/leads/{id}/followups 的content仅空格/换行时422，不写记录。独立采购公告可用procurement_signal.source_id引用，仍必须在本任务已取得来源中且引文关联实际买方。响应结构保持，采购引文同时进入evidence。

2026-10-03恢复补充：POST /api/jobs/{id}/resume 在供应商全局冷却时返回409，error为“检索服务暂时受限，请N秒后重试”；不清空预算。成功工具复用，临时失败仅显式恢复重试，checkpoint已越过检索节点也重放失败工具，新来源重新核验。站点冷却只限制相同host，允许换其他来源。

工具持久投影和SSE新增attempts整数（历史默认1）；elapsed_ms为累计尝试耗时。单页混合PDF也OCR，保留原文字层并明确OCR警告；达到OCR上限标部分解析。

默认URL `http://127.0.0.1:8000`，路径均以 `/api` 开头。HTTP JSON，上传为multipart，导出为xlsx，事件为SSE。

| 方法与路径 | 用途 | 入参 | 成功响应 | 特定失败/边界 |
|---|---|---|---|---|
| GET /api/health | Web与Worker状态 | 无 | 200 Health | 无心跳worker_online=false |
| GET /api/tracing | LangSmith配置状态 | 无 | 200 TracingStatus | 无key关闭，不执行云端测试 |
| GET /api/conversations | 最近100个对话 | 无 | 200 Conversation[] | 空库[] |
| POST /api/conversations | 新建对话 | 无body | 201 Conversation | 每次新建，不幂等 |
| GET /api/conversations/{id} | 对话详情 | 非空对话ID | 200 ConversationDetail | 404不存在 |
| POST /api/conversations/{id}/messages | 消息并创建任务 | MessageInput | 202 Job | 重复token返回原任务；其他活动任务409；附件不存在404 |
| POST /api/attachments | 上传产品文件 | multipart file | 201 AttachmentMeta | 空或>10MB413；格式不支持415；损坏/加密/无文字400 |
| GET /api/attachments/{id} | 解析预览 | 非空附件ID | 200 AttachmentDetail | 不存在404，禁止返回磁盘路径 |
| GET /api/jobs/{id} | 进度、来源数、事件 | 非空任务ID | 200 JobDetail | 404不存在 |
| GET /api/jobs/{id}/events | 持久化事件流 | ID，after非负整数默认0 | 200 text/event-stream | 404；断开结束，终态结束 |
| POST /api/jobs/{id}/pause | 安全暂停 | ID，无body | 200 Job | 404；排队立即paused，运行cancelling；终态无变化 |
| POST /api/jobs/{id}/resume | 恢复 | ID，无body | 200 Job | paused/failed/partial可恢复；活动冲突、供应商冷却或在途清理未结束409 |
| GET /api/leads | 筛选分页 | LeadQuery | 200 LeadPage | 空items[]，越界页空列表 |
| POST /api/leads | 人工新建 | LeadInput，名称必填 | 201 Lead | 名称空白400；类型/枚举422 |
| GET /api/leads/{id} | 详情与跟进 | 非空客户ID | 200 LeadDetail | 不存在/归档404 |
| PATCH /api/leads/{id} | 人工修改 | LeadInput，可部分 | 200 Lead | 404；日期格式400；未知字段422 |
| DELETE /api/leads/{id} | 软归档 | ID | 200 Archive | 重复调用404，历史不删除 |
| POST /api/leads/{id}/followups | 记录跟进 | FollowupInput | 201 Followup | 404；空内容422，无自动触达 |
| GET /api/leads/export | 导出当前筛选 | q/status/city/buyer_role同LeadQuery | 200 xlsx | 最多10000条，三张表；未知空白 |
| POST /api/leads/import-sample | 明确导入历史样本 | 无 | 200 ImportResult | 去重幂等；不触发网络；文件缺失500 |
| GET /api/settings | 非敏感配置 | 无 | 200 SettingsView | 缺密钥model_configured=false |
| PATCH /api/settings | 保存配置 | SettingsInput | 200 SettingsView | 未知字段/预算范围422 |
| POST /api/settings/test-model | 真调用模型与工具探针 | 无 | 200 ModelTest | 超时/调用失败502；最长90秒 |
| GET /api/evidence/{id} | 实际工具归档正文 | 非空来源ID | 200 Evidence | 404；历史样本外链不一定有此归档ID |
| GET /api/channels | 渠道实际状态 | 无 | 200 Channel[] | 商业来源authorization_required，不能启用 |
| GET /api/memories | 有效工作空间记忆 | 无 | 200 Memory[] | 空库[]；含画像/偏好/排除/配方/反馈 |
| POST /api/memories | 用户明确记忆 | MemoryInput | 201 Memory[] | 同类型同内容幂等更新；空白400/结构422 |
| DELETE /api/memories/{id} | 停用记忆 | 非空记忆ID | 200 Inactive | 不存在404；重复停用200 |
| GET /api/knowledge | 知识列表/中文检索 | q可空字符串 | 200 KnowledgePage | 空q最近150含失效项；非空q有效FTS最多30条 |
| POST /api/knowledge | 添加第一方产品资料 | KnowledgeInput | 201 Knowledge | 相同内容去重；结构422 |
| DELETE /api/knowledge/{id} | 停用知识 | 非空知识ID | 200 Inactive | 404不存在；重复200；原文保留 |
| POST /api/leads/{id}/feedback | 销售纠错与相关性 | FeedbackInput | 201 Feedback | 404归档/不存在；非幂等，每次生成新反馈 |
| GET /api/agent/graph | 图节点/边/State字段 | 无 | 200 GraphInfo | 不包含用户原始内容 |
| GET /api/jobs/{id}/state | checkpoint及待执行节点 | 非空任务ID | 200 CheckpointView | 404任务不存在；尚未运行next=[]/state={} |

# 鉴权与通用约定

v0.2无账号鉴权，全部API只用于本机工作空间；默认仅监听127.0.0.1。没有跨团队隔离。浏览器允许本机5173开发源。不要直接暴露公网。

响应包含`X-Request-ID`，业务失败JSON含同一ID，便于查日志。密钥仅后台只读，不经API保存或返回。模型测试/消息会产生真实provider调用，其他CRM读写不会发销售消息。

普通GET/CRM操作按需调用，无强制频率限制；首页SSE每秒更新，health按需刷新，避免并行重复任务。任务worker串行领取；队列持久化。`client_token`跨对话唯一，同token重复会返回原任务，不校验重试body一致性。人工更新无版本锁，并发最后完成者覆盖；批量修改是前端逐条PATCH，可能部分成功。

# 数据模型（请求/响应）

时间全部Asia/Shanghai，`yyyy-MM-dd HH:mm:ss`。金额和统计信息为保留原文的字符串，单位随来源，不转换币种或估计采购价。ID为字符串，Message/JobEvent/Followup ID为整数。

## 输入

MessageInput：content必填1..20000字符且非空白；attachment_ids默认[]、最多5个；client_token必填8..100字符。没有附件时可省略数组。

2026-10-02延迟修复：当前消息区分quick/chat/research。POST /api/conversations/{id}/messages仍成功202返回Job；quick（问候/应用身份）在同一请求完成，Job.status=completed、stage=chat、metrics.intent=quick/model_calls=0，已有message.completed可从SSE重放。普通解释走queued→running→completed单次answer，无研究工具及画像更新；明确研究才进入研究图。没有新增body字段。已有client_token幂等与同会话活动409仍生效。

2026-10-09查询路由修订：`query_mode=auto`下，“查询/查一下/研究某主体的信息、资料、情况”以及船厂、医院等无“公司”后缀主体进入`company_query`；普通解释、附件问题、销售获客和明确禁止检索仍保持原路由。同一会话的“都要/全部/确认/继续”等短确认只承接最近一轮企业请求，用户原始`Job.prompt`不改写，获授权的完整研究要求写入`Job.metrics.research_prompt`。Company研究结果只在结构化提取和逐字段证据校验成功后写入Company/ResearchCompany，模型超时仅保留Evidence与可恢复任务。会话列表/详情的`title`投影为最多10字的问题概括，不增加模型调用。

2026-10-03：新增document内部路由。明确只读附件/提取规格且无获客指令时context→answer→END，不执行公网检索；无本轮附件可读取该对话最近一次上传的附件（不受短消息窗口限制），不自动更新公司画像。已有上传但明确寻客仍走research；一般解释里的“资料/表格”不算文件引用。接口body不变。

POST /api/jobs/{id}/pause用于停止回答：queued立即paused，running/cancelling设置cancel_requested并在等待首块/下一块最多约0.4秒的检查点取消客户端请求、关闭流，最终paused。后端/网络延迟使UI耗时可能更长；不保证provider停止计费。部分助手消息保留，resume继续使用原任务预算与checkpoint；正常终态不再追加delta。旧任务未记录的时间不可推测。

GET /api/tracing无需鉴权，无参数，可重复读取，不触发网络，成功200：

```jsonc
{
  "provider": "LangSmith", // 原生SDK供应商
  "configured": false, // 后台环境是否存在非空Key，不返回Key
  "enabled": false, // 开关且Key均满足才启用
  "project": "client-reach", // 追踪项目名
  "hide_inputs": true, // 默认不上传原始输入
  "hide_outputs": true // 默认不上传原始输出
}
```

无Key、关闭或非对象/损坏的非敏感配置不会凭空视为成功上传；enabled代表运行开关，不代表云端已收到trace。key来自LANGSMITH_API_KEY或config/apikey.txt的独立LangSmith字段；显式空环境变量关闭文件凭据。默认元信息只有关联ID，自定义工具参数/结果先白名单投影。所有请求失败沿用统一HTTP错误语义。

Worker研究/普通问答各1槽，总并发2；另一会话的问答不等待研究结束。metrics新增submitted_epoch（诊断Unix秒float）、request_to_first_text_ms（提交至首个用户文本毫秒）、profile_reused/plan_reused（可选bool）；ttft_ms只计最终模型开始至首块，不能当完整任务首答。旧任务时间只有秒级created_at，未带submitted_epoch时端到端估算有约1秒精度差。固定应用回答不伪装为模型delta。

```jsonc
{
  "content": "销售吊灯，找深圳经销商", // 用户产品与获客目标
  "attachment_ids": [], // 已上传附件ID，空数组表示无附件
  "client_token": "request-token-0001" // 每次新发送唯一；重试保持同值
}
```

LeadInput所有字段可省略；POST额外要求display_name。PATCH中缺失或null表示不修改，空字符串清除可清空字段，tags=[]清除标签；名称不能清空。未知字段拒绝。

| 字段 | 类型 | 长度/约束 |
|---|---|---|
| display_name | string/null | 2..200，非空白，POST必填 |
| city | string/null | <=100 |
| industry | string/null | <=200 |
| status | string/null | new/review/contacted/nurture/converted/invalid |
| owner | string/null | <=100 |
| next_followup | string/null | <=30，空字符串或指定时间格式 |
| phone | string/null | <=100，保留用户原文，不脱敏 |
| email | string/null | <=200 |
| address | string/null | <=500 |
| tags | string[]/null | 最多20个标签 |

```jsonc
{
  "display_name": "接口说明客户", // 示例名称，人工录入未核验
  "city": "深圳", // 示例城市
  "industry": "灯饰经销", // 人工行业
  "status": "new", // 新线索
  "owner": "", // 尚未指定负责人
  "next_followup": "", // 尚未安排跟进，可清除已有值
  "phone": "", // 未提供电话
  "email": "", // 未提供邮箱
  "address": "", // 未提供地址
  "tags": [] // 无标签
}
```

FollowupInput content必填1..5000字符；kind默认note，可选note/phone/visit/email。写入人工跟进，不变成网页采购事实。

```jsonc
{"content":"记录销售跟进情况", /* 跟进内容 */ "kind":"note" /* 备注类型 */}
```

SettingsInput为完整默认合并模型（省略字段会回到默认值，不是保留旧值），未知字段422。

```jsonc
{
  "company_name": "", // 公司名称，<=200
  "default_region": "深圳", // 默认地区，1..100字符
  "max_leads": 8, // 单任务总线索上限，1..20，恢复保留已取得数量
  "max_searches": 8, // 任务搜索上限，1..16，恢复沿用累计额度
  "max_reads": 10, // 任务正文读取上限，0..24
  "max_seconds": 600, // 累计执行秒数，60..1800，不含暂停
  "max_model_calls": 32, // 累计模型调用上限，1..100，含失败及纠正
  "max_model_tokens": 180000, // 任务令牌账本上限，4000..1000000
  "max_candidate_searches": 3, // 已选客户定向补查上限，1..8
  "enabled_channels": ["knowledge","official","directory","procurement"], // 实际启用渠道
  "model": "gpt-6-luna" // 唯一允许模型
}
```

LeadQuery：q默认""（名称包含匹配、转义通配符）、status默认""（枚举过滤，未知值返回空）、city默认""（精确匹配）、buyer_role默认""（角色枚举精确匹配，空不限）。page默认1且>=1；page_size默认20，1..100。空字符串不筛选。按score降序、updated_at降序。stats为全库未归档状态统计，不受筛选影响。导出使用相同四个筛选，不分页、忽略page/page_size。

上传：file必填，支持txt/csv/pdf/doc/docx/xls/xlsx；文件<=10MB。PDF非加密、最多100页，逐页检测文字，最多10页本地中文OCR；Word保留段落/表格顺序、嵌套及页眉页脚，最多10张插图OCR，DOC经隔离LibreOffice转换；Excel每表最多1000行30列，保留坐标、日期、合并范围、公式与缓存值，无缓存公式不计算。解压<=50MB，提取最多12万字符。超出读取范围truncated=true，parse.warnings说明限制；OCR不保证表格还原或型号/金额完全正确。模型单附件选择首尾及关键词相关原文块，总原文预算2万字符，明确提示其他片段未进入本轮模型上下文。

## 输出（接口概览对应这些结构）

Health：status="ok"，version="0.3.0"，worker_online boolean，model="gpt-6-luna"，engine="LangGraph"，worker_heartbeat为诊断用Unix秒float（无心跳0）。启动脚本等待新Worker本次启动之后的心跳，不拿旧进程心跳冒充已就绪。

Conversation含id/title/profile/created_at/updated_at。ConversationDetail额外messages（按整数ID升序），jobs（创建时间降序，同秒按submitted_epoch降序），attachments（消息关联的附件元信息）。每个job包含tools真实工具摘要及累计elapsed_ms；reply_message_id关联对应助手消息，不能给所有历史轮次套用最新任务耗时。空profile={}，空messages/jobs/attachments=[]。

```jsonc
{
  "id": "conversation-id", // 对话UUID
  "title": "新的获客对话", // 首条用户消息后改为截取标题
  "profile": {}, // 未分析；完成后含products/region/target_buyers/summary/questions
  "created_at": "2026-10-01 23:00:00", // 上海创建时间
  "updated_at": "2026-10-01 23:00:00" // 上海更新时间
}
```

Message含id（整数）、conversation_id、role（user/assistant）、content（纯文字，前端不执行HTML）、attachment_ids、created_at。ProductProfile含company_name可null、products数组（name/model/specifications/price/source；未知字段null）、region、target_buyers、exclusions、summary、questions。questions非空进入needs_input。

```jsonc
{
  "id": "job-id", // 任务UUID
  "conversation_id": "conversation-id", // 所属对话
  "client_token": "request-token-0001", // 幂等标识
  "prompt": "销售吊灯，找深圳经销商", // 原始用户要求
  "attachment_ids": [], // 已关联附件
  "status": "queued", // 状态枚举见下文
  "stage": "等待执行", // 当前阶段
  "progress": 0, // 0..100，仅阶段进度非ETA
  "cancel_requested": false, // 是否请求暂停
  "lead_ids": [], // 实际保存线索ID
  "error": "", // 无错误；失败为安全异常类型
  "created_at": "2026-10-01 23:00:00", // 创建时间
  "updated_at": "2026-10-01 23:00:00" // 最近变化
}
```

JobDetail额外含最近100个events、source_count、tools（不含结果正文）、graph_version、started_at/finished_at可null、elapsed_ms毫秒、reply_message_id可null、generation_id和metrics。JobEvent增加event_type/payload。metrics含stage_timings、ttft_ms、channels、source_ids、model_budget；model_budget含calls/accounted_tokens/reported_tokens/estimated_calls/max_calls/max_tokens。reported_tokens只计provider实测，estimated_calls是保守预留请求数量。Job状态全集：queued/running/cancelling/paused/completed/partial/failed/needs_input。只有queued/running/cancelling为活动态。partial不保证有结果。恢复从同一checkpoint继续，不重置累计调用/令牌/时间，不回滚已保存结果。

当前消息中“最多/仅/只…数字…条/家/个”明确数量上限与设置取较小值；达到数量上限只禁止新增主体，仍补全已有客户。此前多条历史结果不会因降低数量上限而删除。恢复允许更新数量与启用渠道，其余沿用checkpoint原任务预算。

SSE：事件stage、run.started/run.completed/run.paused/run.failed/run.partial、tool.started/tool.finished/tool.reused/tool.result、node.finished、message.reset/message.delta/message.completed均含持久id、event_id/created_at/stage/message；status无事件ID，携带JobDetail去除events/tools。游标为max(after,Last-Event-ID)，无效header回退after。每批150条先排空再发终态，客户端收到终态可close；断网自动重连不新建任务。文本直接来自模型astream。reset含message_id/generation_id；delta附delta字符串；completed附完整content。新generation必须清空旧草稿。

AttachmentMeta：id/filename/size字节/characters整数/truncated boolean/created_at，以及parse对象。parse包含format/method/elapsed_ms/warnings，按格式可包含pages/ocr_pages/page_details、tables/images_ocr、sheets/formula_without_cache。旧附件parse={}。POST不返回磁盘路径或正文；AttachmentDetail额外text，为实际保存的最多12万字符解析原文。

2026-10-02：首页工具轨迹采用operation_id合并真实tool.started/tool.finished/tool.reused事件与持久快照，默认折叠。工具投影保留query/url/channel/schema或customer，屏蔽其他入参；结果只给source_count/sources（前5条title/url）/knowledge_count/error/reused。不发送来源正文或内部结构化模型账本。tool.started含arguments/status，tool.finished含status/elapsed_ms及结果摘要，tool.reused含完成状态、入参及真实复用摘要。

### 附件解析与预览（本轮新增/变更）

POST /api/attachments：multipart字段file必填，无鉴权，每次上传生成新ID，不按相同文件自动幂等；解析在线程执行。成功201：

```jsonc
{
  "id": "attachment-example", // 附件标识，仅示例
  "filename": "产品.xlsx", // 原文件名
  "size": 5400, // 原始文件字节数
  "characters": 240, // 已保存解析字符数
  "truncated": false, // 是否因限制遗漏内容
  "parse": { // 确定性解析元信息
    "format": "xlsx", // 文件格式
    "method": "Excel单元格/公式/缓存值", // 实际使用方法
    "elapsed_ms": 120, // 本地解析毫秒
    "warnings": ["1个公式没有缓存结果，保留公式但未自动计算"], // 可核对的限制
    "formula_without_cache": 1 // 无缓存公式数量
  },
  "created_at": "2026-10-02 23:00:00" // 上海时间
}
```

GET /api/attachments/{attachment_id}：路径attachment_id必填非空，无鉴权，可重复读取，成功200为上面元信息额外包含text。例如：

```jsonc
{ "text": "[工作表: 产品]\nB2: CR-T20 | D2: 58" } // 实际提取原文，其他元信息同AttachmentMeta
```

失败响应统一：

```jsonc
{
  "error": "附件不存在", // 404未知ID；400格式损坏/加密/空白；413空字节或超10MB；415不支持后缀
  "request_id": "example-request" // 与响应头一致的调试ID
}
```

范围超限但已有文字时成功且truncated=true；空白工作表、无法识别的纯扫描内容不能用页签/占位符充当成功文字。公式只读，不执行宏、外链刷新或重新计算；DOC使用独立高宏安全级别的LibreOffice配置目录。并发OCR用实例锁，预览不再次解析。解析失败不创建附件记录，前端应保留其他已成功上传文件并允许重试。

Lead含id/dedupe_key/display_name/legal_name(null可用)/city/industry/status/owner/next_followup/score/match_reason/matched_products/facts/evidence/manual_fields/tags/archived/created_at/updated_at。facts是字段名到FactValue的字典；不存在字段是未知，不是0。FactValue含value、verification、source_id（人工null/历史可缺失）、scope/effective_date（可缺失）。evidence是逐字段引文数组，含field/value/quote/source_id/url/title/captured_at/kind；历史样本可额外带原研究字段。LeadDetail另含followups倒序。

```jsonc
{
  "items": [], // 当前页Lead数组，没有线索时为空
  "total": 0, // 筛选后的总数
  "page": 1, // 当前页
  "page_size": 20, // 页容量
  "stats": {"new":0, /* 新线索 */ "review":0, /* 待核验 */ "contacted":0, /* 已联系 */ "nurture":0, /* 持续跟进 */ "converted":0, /* 成交 */ "invalid":0 /* 无效 */} // 全库统计
}
```

Followup含id整数/lead_id/content/kind/created_at；Archive=`{"archived":true /* 已软归档 */}`；ImportResult=`{"imported":0 /* 新增数量，重复导入为0 */,"message":"已导入2026-09-30研究样本，非本次实时搜索" /* 日期提示 */}`。

SettingsView含SettingsInput全部字段，加model_configured boolean、base_url非敏感端点、search_provider="Exa MCP"、database="SQLite"、credential_source="config/apikey.txt"、version="0.2.0"、agent_engine="LangGraph"。ModelTest额外含structured_output/streaming boolean、chunks/elapsed_ms整数。

Evidence含id/job_id/url/title/body/kind/captured_at/channel/content_hash/published_at(null)/expires_at(null)。body为实际返回文字，不保证全文完整。expires_at是系统复核TTL，不是公告截止时间。Lead新增buyer_role（dealer/retailer/mall/project_buyer/manufacturer/unknown）与qualification维度；FactValue可能有verification=disputed/inactive及alternatives数组，前端不能当确认值；采购信号qualification.procurement_signal可null，历史不加active评分。

## v0.2新增输入输出示例

所有新增接口为本地无鉴权、按需操作；GET没有副作用，POST反馈无幂等。资源ID不存在404，结构或枚举错误422，业务空白400，统一错误格式见下文。记忆与知识停用为软失效，不删除证据或checkpoint。

```jsonc
{"kind":"preference", /* company/preference/exclusion */ "content":"只找深圳零售门店" /* 必填1..4000字符，拒绝空白 */}
```

POST /api/memories成功201返回当前有效Memory[]；Memory含id/namespace/key/value/status/created_at/updated_at。namespace固定local下各类型，value为记录结构。GET /api/memories相同200。DELETE /api/memories/{id}成功200返回`{"inactive":true /* 已停用 */}`。

```jsonc
{"title":"轨道灯产品", /* 必填1..200 */ "body":"公司实际产品资料" /* 必填1..20000 */}
```

POST /api/knowledge成功201返回Knowledge：id/workspace_id/title/body/kind/source_id(null)/source_url/entity_id(null)/status/expires_at(null)/created_at/updated_at。新增kind固定product、workspace_id固定local；不能伪装为公开采购证据。GET /api/knowledge?q=轨道灯成功200返回`{"items":[], /* 知识数组，空检索为空 */ "active":0 /* 返回集合有效条数 */}`。DELETE /api/knowledge/{id}成功200返回Inactive。

```jsonc
{"kind":"stale", /* relevant/nonbuyer/incorrect/stale */ "content":"原联系方式已失效" /* 可空，最多2000 */}
```

POST /api/leads/{id}/feedback成功201返回`{"id":"feedback-id", /* 反馈ID */ "lead_id":"lead-id", /* 实际客户 */ "kind":"stale", /* 反馈类型 */ "content":"原联系方式已失效", /* 用户原因 */ "created_at":"2026-10-02 12:00:00" /* 上海时间 */}`。nonbuyer进入排除项并score=0；incorrect/stale使关联知识失效，阻止旧事实恢复；relevant/负反馈参与渠道配方排序。LeadDetail增加feedback数组。

GET /api/channels成功200返回Channel[]，字段id/name/status/description/enabled；status=ready或authorization_required。GET /api/agent/graph成功200含engine/version/nodes/edges/state_fields/checkpoint/store。GET /api/jobs/{id}/state成功200含next字符串数组、checkpoint_id可null、state白名单计划/来源/缺口/尝试/预算/耗时/metrics；不输出原始对话/文件内容或API配置。

```text
id: 21
event: message.delta
data: {"event_id":21,"message_id":3,"generation_id":"generation-id","delta":"深圳"}

```

此SSE示例event_id为持久游标，message_id为助手消息，generation_id为草稿版本，delta为实际文本；实际事件还带created_at/stage/message。客户端不应把工具JSON作为用户回答显示。

# 接口清单

逐接口方法、入参、返回HTTP状态、失败及边界见“接口概览”。所有接口均无需鉴权。没有输入的POST不需要`{}`；未知ID404；枚举和字段范围由Pydantic校验422。附件需multipart，不能JSON提交文件路径。导出`Content-Disposition`文件名client-reach-leads.xlsx，三张表含完整字段与证据；公式型文本被保护。

# 错误码与错误语义

400业务数据无效；404资源不存在；409执行状态/幂等标识冲突；413附件超限或为空；415格式不支持；422请求结构校验失败；500内部故障；502模型探针失败。任务执行失败通常以Job.failed/partial返回200，不能只检查HTTP成功。

```jsonc
{
  "error": "任务不存在", // 可公开错误原因
  "request_id": "request-id" // 与响应头一致，查API日志
}
```

422采用FastAPI标准`detail`数组，元素含type/loc/msg/input等（输入可能反映用户提供内容，不能作为服务器秘密配置日志）。前端渲染文本，不注入HTML。所有接口5xx均不回显provider密钥或原始响应。

# 兼容性与变更记录

2026-10-02 v0.2替换PydanticAI为LangGraph，SSE由旧progress改为stage和文本事件；旧前端需同步构建。已有客户/证据保留，新表和列为加法迁移，未知角色旧分数降为待核等级。Settings PATCH仍采用完整默认合并，CRM PATCH缺失字段保留。停机前备份业务库及checkpoint，不能将v0.2 checkpoint套用v0.1引擎。

2026-10-03：新增只读/tracing与document路由、流式等待可取消；没有破坏旧请求body或删除数据。工具UI改为文字摘要，真实账本/SSE字段仍保留。文件预览响应继续返回实际原文和范围。

# 注意事项

评分拆分角色/产品/有效信号/证据，unknown不具备角色资格。主体关联与逐字校验同时执行，但不代替销售核验。完全名称/城市/地址去重；相同名称城市的唯一缺地址记录可补全，有分店地址冲突不合并。手动字段受保护；归档不是文件删除。未知事实空，采购价不从零售价推算。没有自动触达。异常杀进程的不可观测尾段可能低估，未知尾段没有5秒上限；不把停机时间计入活动耗时。

# 企业研究工作台接口（v0.3，2026-10-09）

本模块使用本地无鉴权工作空间；时间统一为 `Asia/Shanghai` 的 `yyyy-MM-dd HH:mm:ss`。企业事实、采购项目、公告和关系均来自后端持久投影，前端不得从Markdown或图片值推导。未知值使用`null`、空数组或“未取得”展示，不能转换为0。历史导入标记`origin=historical_snapshot`，不生成Job/ToolCall；实时补查标记`origin=agent`并绑定Job。

## GET /api/companies

用途：分页读取查询结果卡片。参数`q`企业名/简称模糊搜索，可空；`entity_kind`取`legal|brand|unknown`，可空；`visibility`默认`primary`，取`primary|related|counterparty`；`conversation_id`可空，非空时只返回该研究会话的ResearchCompany成员；`page>=1`默认1；`page_size`1—100默认20。成功200：

```jsonc
{
  "items": [], // 当前页已保存主体摘要，字段详见下方Company/header；空数组不证明企业不存在
  "total": 0, // 当前筛选后的总记录数，不是实际市场企业总数
  "page": 1, // 当前页，最小1
  "page_size": 20 // 每页数量，默认20，上限100
}
```

卡片项目数按实际买方项目去重；品牌应用和投资计划在详情中单独标记。排序固定为`updated_at DESC, created_at DESC, id`，在offset/limit之前执行。明确研究的既有关联主体会成为primary查询结果。空结果返回`items:[]`，不是错误。`conversation_id`不存在返回404。

## POST /api/companies/import-history

用途：幂等导入项目内已审阅公开资料快照。无请求体，成功200返回`company_ids`、`conversation_ids`、`origin=historical_snapshot`、`imported_at`。重复调用不增加事实、来源、项目、公告、关系或ResearchCompany；原文文件缺失/哈希不符返回422。该接口不调用模型、不搜索网页、不创建实时Job。

## GET /api/companies/{company_id}

用途：企业综合单页的聚合投影。成功200返回`header`、`facts`、`fact_groups`、`projects`、`relations`、`sources`、`research_memberships`、`coverage`、`gaps`、`procurement_summary`、`relation_summary`与可空`purchase_analysis`。`projects`中`record_kind`取`procurement|plan|brand_application`；采购项目的`payload.quantity`是公告需求量，`payload.budget`是原文预算/原单位，`currency_confirmed:false`表示原文未明确币种；`temporal_status`可能为“截止已过 · 结果未知”或“候选公示 · 非最终成交”。`relations.relation_type`取`supplier|customer|subsidiary|service_supplier`，交易金额是企业与对手方的年度交易额，不是对手方营收。不存在返回404。

2026-10-09，Codex：`CompanyFact.period_kind`增加明确同年`yyyy-01-01至yyyy-12-31`与`yyyy-01-01至yyyy-06-30`识别，分别为annual和half_year；单一截至6月时点、跨年区间仍不推断年度或半年。

`purchase_analysis=null`表示当前企业尚无完成的专项产品匹配，不填模拟结论。非空时包含`job_id`、`conversation_id`、`created_at`（上海时间）、`source_as_of`（所用企业资料日期）、`status`、`origin=model_document_match`与`content`（真实Markdown回答）。只选本企业最新completed/partial匹配任务；结论和企业facts隔离，原始事实不会因AI建议改变。

### 指定企业的产品匹配（复用消息接口）

依次使用`POST /api/attachments`上传解析、`POST /api/conversations`创建分析会话、`POST /api/conversations/{id}/messages`提交。无额外鉴权；只有用户点击开始分析才排队模型任务。请求：

```jsonc
{
  "content": "只读取上传的产品資料，不要搜索其他客户。分析产品与目标企业采购方向的匹配依据和待核验条件。", // 本轮分析要求，1..20000字符
  "attachment_ids": ["example-attachment-id"], // 已成功上传的1..5份资料ID，空数组不能执行company_match
  "company_id": "example-company-id", // 必填持久企业ID，不存在返回404；不以名称相似度选企业
  "query_mode": "company_match", // 明确文件匹配操作；仍识别需求，执行范围只允许document分析
  "client_token": "example-idempotency-token" // 8..100字符，网络重试必须复用，防重复创建任务
}
```

成功202返回现有Job字段；排队不表示分析完成。Worker复用意图/回答模型、预算、checkpoint和SSE，读取有界附件与所选企业数据库事实/计划/来源，不进行客户搜索、企业补查或企业事实写入。真实模型判断记录`metrics.model_intent`，明确操作范围记录`operation_scope=company_document_match`，执行意图为document；完成后`metrics.company_match_context=true`和`company_match_as_of`保留依据日期。结果先在工作台流式呈现，再由企业详情`purchase_analysis`读取。

失败：缺企业或附件返回400“产品匹配需要指定企业和已上传资料”；未知企业/附件404；活动会话冲突409；非法参数422。模型失败/预算/取消通过现有Job/SSE保留真实状态及部分回答，不虚构购买概率、采购日期、剩余预算或订单。上传、提交失败时前端保留已解析资料；重复提交复用token。

## GET /api/companies/{company_id}/export

用途：导出当前企业事实、采购项目、上下游关系和来源为XLSX。成功200，`Content-Disposition`为`company-research.xlsx`；未知字段留空，原值、统计期、主体口径、引文和来源ID保留。不存在404；不导出API密钥、内部checkpoint或原文磁盘路径。

## POST /api/companies/{company_id}/research

用途：对指定企业继续研究，绕过卖方产品画像门禁，仍共享现有Worker、ToolBroker、模型预算、checkpoint、暂停恢复和SSE。请求：

```jsonc
{
  "client_token": "enterprise-research-example-01", // 必填8—100字符，同一次用户操作重试复用
  "conversation_id": null, // 可空；null/省略创建该企业的新会话，非空必须存在
  "content": "核验最新公开采购信息和上下游" // 可空；省略/空串采用默认补查，最多20000字符
}
```

`client_token`必填8—100字符，重复请求幂等；`conversation_id`可空，空值创建只属于该企业的新会话；`content`可空，空值使用默认补查范围，最多20000字符。成功202返回标准Job，含`id`、`conversation_id`、`query_mode:"company_query"`、`status:"queued"`。同一token不同企业或不同会话返回409；企业不存在404；当前会话有活动任务409。Agent只从真实已读正文提取字段，模型输出必须逐项绑定Evidence连续引文；主体、年度/半年度口径、采购实际买方、候选/成交阶段和上下游方向分别校验。

## GET /api/browser/status、PATCH /api/browser/settings、POST /api/browser/test

`GET /api/browser/status`返回Edge/Node/OpenCLI/Playwright安装状态、`opencli_version`、最近真实读取和固定策略；没有成功读取时`last_read:null`，不声称已连接。`PATCH`请求字段为`enabled`、`preferred_backend`（`auto|opencli|playwright`）、`max_pages`1—8、`max_chars`2000—100000、`command_timeout`15—120；拒绝任意命令、脚本、profile路径和凭据字段，结构错误422。

`POST /api/browser/test`只允许公网HTTP(S)无凭据URL。成功200返回`url/title/body_chars/total_chars/truncated/backend/elapsed_ms/opencli_version/preview`，不创建企业事实或Job；访问受限、验证码、robots、私网、空正文或超时返回错误。请求示例：

```jsonc
{
  "url": "https://www.hanon.cc/contact", // 必填明确公网页面，非搜索入口；不可传私网或含凭据URL
  "backend": "auto" // auto/opencli/playwright；省略默认auto
}
```

当前该页OpenCLI1.8.8 + Edge实测814字符、HTTP200、约10秒；只证明当时读取能力，不自动改变企业事实。

## 变更记录

2026-10-09 v0.3新增Company/CompanyFact/ProcurementProject/ProcurementNotice/CompanyRelation/ResearchCompany及Job查询模式、企业卡片/详情/导出/历史导入/继续研究和浏览器能力接口；数据库迁移版本`20261008_02`，旧表与旧API加法兼容。`Evidence.source_meta`只投影允许的来源元数据；来源正文仍通过`/api/evidence/{id}`读取。`/api/health`新增`data_as_of`。
2026-10-09 v0.3.1修订auto企业查询路由、短确认承接和会话短标题；无DDL和请求body变更。
计划结束且已读正文无法确认请求主体时，企业任务为needs_input并询问企业全称或官网；确认SDK提取超时保留缺口并继续其他步骤，预算/取消行为不变。Job.metrics包含intent、conversation_title（最多10字）；承接短确认时另有research_prompt，Job.prompt始终为本轮原文。

## 企业模块字段与边界补充（2026-10-09，Codex）

所有接口本机无鉴权，不发送销售消息。GET可重复读取，无自动外部采集；导入与研究POST按上文幂等规则。分页默认先集团汇总、再实际采购项目数量降序、创建日期与名称；越界页返回空items，page<1或page_size越界422。`entity_kind`未知字符串当前返回空筛选结果，`visibility`空串不筛类型。字段缺失不要猜0；nullable金额、人数、占比未知为null；报告期/发布日期未知为空串；空列表表示尚无已保存资料，不证明实际不存在。

| 类型 | 核心字段、单位与语义 |
| --- | --- |
| Company/header/items | id/identity_key字符串；name完整原名；short_name可空；entity_kind=legal/brand/unknown；view_scope=group/entity；visibility=primary/related/counterparty；credit_code可空；origin=agent/historical_snapshot；research_as_of为核查日，非网页发布日期；metadata_json为带缺口/范围的投影；created_at/updated_at为上海时间 |
| 摘要facts | industry/business/products/headcount/revenue/address/website/stock_code均为CompanyFact或null；fact_count/source_count/project_count/notice_count/plan_count/supplier_count/customer_count是已存计数；buyer_names/采购分类为空时不补猜 |
| CompanyFact | id/unique_key/company_id/category/field/label；raw_value保留原值，numeric_value可空；unit/raw_unit不自动换算；report_period/as_of/scope；status=verified/pending/disputed/inactive/masked；source_ids/quote/note；period_kind=annual/half_year/quarter/as_of；contact_href仅有效联系值派生，空串禁止正常拨号/邮件操作 |
| ProcurementProject | id/unique_key/buyer_id/buyer_name/title/project_number/record_kind/stage；published_at/deadline为空或实际披露日期时间，不补午夜；payload包含product/quantity/unit/budget/specifications，候选报价与预算分开；source_ids/quote；notices保留公告事件；temporal_status为展示状态 |
| ProcurementNotice | id/unique_key/project_id/title/notice_type/published_at/platform_published_at/deadline/source_ids/payload/created_at；公告日期与平台日期分开，转载和附件不增独立项目 |
| CompanyRelation | id/unique_key/company_id/counterparty_id可空/counterparty_name/relation_type/rank可空/report_period/amount可空/currency可空/unit/share可空/scope/source_ids/quote/note/payload/created_at；share单位百分比，如4.83代表4.83% |
| relation_summary | supplier/customer分别返回count、period、amount、share、unit、currency；仅最新同一报告期，同值关系合并来源，不同币种/单位不能相加，金额或占比未知为null |
| Source | id/url/title/channel/published_at/captured_at/origin/reference/evidence_kind；省略磁盘路径/凭据；原文用GET /api/evidence/{id}取得 |
| ResearchCompany | id/unique_key/company_id/conversation_id/job_id可空/position/origin/created_at；历史快照无Job，不伪造实时工具 |

完整详情可复制的空值形状（说明示例，不是真实企业结果；header实际还含上表Company与摘要字段）：

```jsonc
{
  "header": {"id":"example-company", "name":"验证企业", "facts":{}}, // 共享企业头，真实GET包含上表完整字段
  "facts": [], // 全部逐项原文事实，空数组表示尚未保存
  "fact_groups": {}, // category→事实数组，不由前端猜类别
  "projects": [], // 采购/计划/品牌应用按record_kind区分
  "relations": [], // 具名年度关系及子公司
  "sources": [], // 公开来源摘要
  "research_memberships": [], // 实际研究会话成员
  "coverage": [], // 历史检索覆盖记录，可空
  "gaps": [], // 已记录缺口，空不承诺所有字段完整
  "procurement_summary": {"projects":0,"notices":0,"plans":0,"quantity_disclosed":0}, // 已存项目/公告/计划/需求量披露条数
  "relation_summary": {
    "supplier": {"count":0,"period":"","amount":null,"share":null,"unit":"","currency":null}, // 未取得上游统计
    "customer": {"count":0,"period":"","amount":null,"share":null,"unit":"","currency":null} // 未取得下游统计
  }
}
```

浏览器设置PATCH使用完整默认模型合并，省略字段恢复下列默认值，而不是保留旧值；extra字段422。成功200返回相同设置对象：

```jsonc
{
  "enabled": true, // 是否允许受控Edge读取，默认true
  "preferred_backend": "auto", // auto/opencli/playwright，默认auto
  "max_pages": 3, // 1—8，每任务读取额度同时受共享max_reads限制
  "max_chars": 40000, // 2000—100000，单页正文截断上限
  "command_timeout": 90 // 15—120秒，外层读取命令超时
}
```

浏览器状态200示例（安装状态仅说明依赖存在，last_read空不冒称已连接）：

```jsonc
{
  "settings": {"enabled":true,"preferred_backend":"auto","max_pages":3,"max_chars":40000,"command_timeout":90}, // 当前非敏感配置，语义见上
  "edge_installed": true, // 是否发现Edge可执行文件
  "node_installed": true, // 是否发现Node
  "opencli_installed": true, // 固定项目依赖是否存在
  "opencli_version": "1.8.8", // 本地实际版本，未安装空串
  "playwright_installed": true, // Playwright依赖是否存在
  "last_read": null, // 无实测为null；成功记录checked_at/backend/url/body_chars/elapsed_ms/opencli_version/success
  "strategy": "专用 Edge · OpenCLI web/read CDP · Playwright 备用" // 固定策略说明
}
```

历史导入成功200返回company_ids、conversation_ids数组、origin=historical_snapshot、imported_at上海时间；缺文件/哈希不符422且事务不提交半份数据。继续研究202返回完整Job（见本文已有Job字段），GET /api/jobs/{id}读取真实tools/events；status=queued/running/cancelling/paused/completed/partial/needs_input/failed，不能把202当研究成功。请求重发返回原Job及其当前状态；同会话活动冲突409。数据库client_token唯一；极短同时提交可能在事务中触发唯一约束500，前端应先GET或复用token重试，不能新建token制造重复任务。

通用业务错误示例：

```jsonc
{
  "error": "企业不存在", // 中文业务原因；此示例为404，冲突409、导入校验422另有对应文字
  "request_id": "example-request-id" // 本次请求关联ID，响应X-Request-ID同值
}
```

结构错误422采用FastAPI `detail`数组（loc/type/msg/input），字段位置与约束见OpenAPI；未捕获内部错误500返回安全error/request_id。浏览器已知业务失败400：url_not_public、browser_disabled、browser_runtime_unavailable、empty_body、site_http_*、访问/robots限制；不可据错误直接换身份重试。外层未捕获超时可500，不保证所有第三方错误均为400。

可直接复制执行的有效浏览器请求（正文为严格JSON，无注释）：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/browser/test -Method Post -ContentType 'application/json' -Body '{"url":"https://www.hanon.cc/contact","backend":"auto"}'
Invoke-RestMethod 'http://127.0.0.1:8000/api/companies?page=1&page_size=20'
```

实时采购日期必须有对应连续原文，已写标准published_at/deadline；同买方精确原项目号跨历史/实时关联，公告跨任务重读追加source_ids而不增加事件。无编号不凭标题模糊合并；新阶段须有已核验事件日期，不能按抓取先后覆盖当前阶段。

## 2026-10-09 研究资料与运行链路接口

本机服务无账号鉴权，以下接口均只读、可重复调用。日期为Asia/Shanghai的 `yyyy-MM-dd HH:mm:ss`；未知数值为null，不补零。GET研究资料不发搜索或模型请求，GET trace仅在点击时查询既有LangSmith记录。

| 方法与路径 | 必填路径参数 | 用途与成功响应 |
| --- | --- | --- |
| GET `/api/jobs/{job_id}/research` | job_id：字符串，已存在Job ID | 200，本轮清洗、提取、核验计数，逐企业覆盖/缺口及可预览数据集列表 |
| GET `/api/research-datasets/{dataset_id}` | dataset_id：字符串，已存在数据集ID | 200，阶段、状态、来源引用和实际清洗内容/提议/核验回执/最终快照 |
| GET `/api/jobs/{job_id}/trace` | job_id：字符串，已存在Job ID | 200，追踪开关、云端可读状态、真实URL和最近至多100条安全运行元数据 |

三个接口均无body、分页或额外查询参数；不存在的Job/数据集返回404。空研究返回零计数与空列表，不能据零值宣称企业没有采购。trace disabled、无trace_id或云端不可读仍返回200/available=false；error_type/error_stage仅为安全诊断，不包含原错误、输入输出或凭据。

研究汇总示例（jsonc注释用于说明，网络响应为严格JSON）：

```jsonc
{
  "cleaned_documents": 3, // 清洗资料数，包含有明确标记的搜索摘要；不是已读全文数量
  "extracted_batches": 2, // 完成结构化提议的批次数，不等于核验通过批次
  "accepted": 4, // 去重后的已接受记录数；身份记录不计入此数
  "new_records": 2, // 本轮新建记录数
  "reconfirmed_records": 2, // 已有记录的再次核验数，不算新增企业
  "rejected": 1, // 字段或候选核验拒绝数
  "coverage": { // 逐目标覆盖，A的字段不能替B完成
    "requested_fields": ["name", "business"], // 模型从当前问题识别的字段
    "verified_fields": ["name", "business"], // 所有目标均已覆盖的字段
    "missing_fields": [], // 尚有任一目标未覆盖的字段
    "companies": [{"target":"示例企业有限公司", "company_ids":["example-company-id"], "verified_fields":["name","business"], "missing_fields":[]}], // 每个目标的真实记录引用及缺口
    "source_count": 3, // 当前任务参与研究的来源条数
    "analyzed_chunks": 2, // 成功分析的原文连续片段数
    "pending_chunks": 0 // 仍待分析或失败待恢复的片段数
  },
  "gaps": [], // 原文未披露、访问限制、核验拒绝和其他实际缺口
  "round": 1, // 已进行的研究轮次
  "stop_reason": "requested_fields_covered", // 停止原因；不代表所有公开信息均已查全
  "dataset_count": 6, // 所有阶段的数据集总数
  "datasets": [{"id":"example-dataset-id", "phase":"clean", "status":"completed", "source_ids":["example-source-id"], "created_at":"2026-10-09 16:00:00", "title":"公开报告", "origin":"network", "source_kind":"网页正文"}] // 仅清洗与最终阶段的预览入口
}
```

数据集响应为：id/unique_key/job_id/conversation_id/company_id/phase/status/source_ids/payload/cleaning_version/model_version/created_at/updated_at。company_id可null，表示来源/批次阶段没有唯一已核验企业。phase取clean/extract/save/review/final；status取pending/completed/failed/rejected/partial/needs_input。clean.payload包含cleaned_body、cleaned_hash、original_chars、cleaned_chars、chunks、total_chunks、source_kind、has_full_text、origin；chunks含start/end/body/score/key，区间基于实际连续原文，不将远处片段拼接举证。搜索摘要为pending/has_full_text=false；原始Evidence不重写。extract.payload是待核验模型提议，不可当作客户事实渲染。save.payload含accepted_refs、new_records、reconfirmed_records、rejected及真实记录ID。final.status与Job实际终态一致；paused不新建伪终态快照，保留中间资料。

追踪响应示例：

```jsonc
{
  "provider":"LangSmith", // 当前追踪后端
  "enabled":true, // 开关与独立Key已配置；不是上传成功证明
  "available":true, // 本次真实云端读取成功
  "trace_id":"example-trace-id", // 本轮实际云端根链ID
  "url":"https://smith.langchain.com/example", // SDK返回的真实地址，示例值不能用于导航
  "truncated":false, // 满100条时true，完整链路需打开真实url
  "runs":[{"id":"example-run-id", "name":"ChatOpenAI", "type":"llm", "parent_id":"example-parent-id", "elapsed_ms":2300, "has_error":false, "tool_name":null, "phase":"intent"}] // 安全元数据；未结束时elapsed_ms为null
}
```

通用404示例：`{"error":"研究数据集不存在","request_id":"example-request-id"}`。error为中文原因，request_id用于本次诊断；JSON字段说明与前述通用错误相同。无敏感入参。重复GET不增加模型或工具预算，trace查询也不会重跑任务；云端故障不会回滚已存企业资料。

设置新增字段：research_max_rounds（1..8，默认3）；research_pages_per_query（1..8，默认4）；research_read_concurrency（1..4，默认2）；research_chunks_per_source（1..16，默认6）；research_no_gain_rounds（1..4，默认2）。仍受原有search/read/model/token/time总预算限制，恢复不清零。新SSE事件intent.completed、model.started/model.finished、node.finished/node.failed/node.paused均为实际执行账本，不是模拟进度。intent.completed提供intent/title/requested_fields；标题最多10字。节点失败耗时与模型失败尝试仍计入持久指标，elapsed_ms是累计执行而不是纯网络等待。

## 条目证据与原站链接（2026-10-09，Codex）

企业详情的facts、header.facts、fact_groups、relations、projects及projects.notices新增evidence_refs；旧字段保留。每条引用对应独立片段和条目绑定，关系合并保留全部引用。SourceDocument与不可变Evidence一对一；同URL但正文/采集版本不同不强行合并。

evidence_refs字段：id/binding_id/document_id/source_id为真实持久ID；title为原来源标题；url/source_url为真实HTTP(S)原站地址（不可用时空串）；page_url仅在真实PDF解析页界存在时提供；published_at未知为null，captured_at为上海时间yyyy-MM-dd HH:mm:ss。text默认最多800字符，truncated表示尚未完整展示。quote_kind取continuous/historical_excerpt/unlocated_excerpt；location_status取located/unlocated；page_start/page_end未知为null。role区分value/metadata/buyer/publication/deadline/budget等片段角色，不把多段拼作一段。

| 接口 | 必填路径参数 | 成功200 |
| --- | --- | --- |
| GET /api/companies/{company_id}/documents/{source_id} | company_id为企业持久ID；source_id为该企业关联Evidence ID；空/未知/未关联返回404 | source（详情来源白名单元信息）+ entries（当前文档关联的独立条目） |
| GET /api/source-fragments/{fragment_id} | fragment_id为片段持久ID；空/未知返回404 | id/text/quote_kind/page_start/page_end，text为完整片段 |
| GET /api/evidence/{source_id}（原接口） | source_id为Evidence ID，未知404 | 明确打开归档全文时使用，详情默认不调用 |

本机单工作区无鉴权；按需GET，重复调用幂等、不发网络/模型请求、不增加任务预算。文档入口只返回当前企业已关联条目，没有片段时evidence_refs为空，不能从其他条目补位；空条目返回entries:[]。条目字段包含kind（fact/relation/project/notice）、id、title、value（事实原JSON值，其余可null）、period、evidence_refs，及存在的record_kind/relation_type/amount/share/unit/raw_unit/currency/scope/buyer_name/stage/temporal_status/deadline。金额保留原单位，未知为null。文档接口不返回body或本地路径。

```jsonc
{
  "source": {"id":"example-evidence-id", "title":"公开报告", "url":"https://example.org/report.pdf"}, // 示例来源ID、原标题与地址；实际还包含详情来源的日期/渠道字段
  "entries": [{
    "kind":"fact", // 企业事实类型
    "id":"example-fact-id", // 示例条目持久ID，实际从详情取得
    "title":"主营产品", // 当前事实标题
    "value":"仪器", // 当前事实原值
    "period":"2025", // 真实报告期，未知空串
    "evidence_refs":[] // 未取得片段则为空，不补造引文
  }]
}
```

```jsonc
{"id":"example-fragment-id", "text":"示例原文片段。", "quote_kind":"continuous", "page_start":null, "page_end":null} // 各值依次为真实片段ID、完整原文、摘录类型与未知页码；示例ID需换成详情evidence_refs.id
```

失败404示例：

```jsonc
{"error":"企业未关联此来源", "request_id":"example-request-id"} // 中文错误原因和本次诊断ID
```

不存在企业/片段或企业未关联文档返回404；数据库错误沿通用500处理，不返回本地存档路径。多个引用全部返回并按绑定序号排序，不同企业/文档不能互相替代。

前端直接联调：先GET /api/companies/475adf481fef46ce9b09f5f469c708d8，以响应sources[].id调用文档入口，以facts/relations[].evidence_refs[].id调用完整片段入口；来源归属与未知值均以这次响应为准。

## 独立关系与名称确认（2026-10-10）

以下接口沿用本机无账号模式，无新增鉴权；仅显式POST执行模型与网络，GET不触发采集。所有路径ID使用前一步响应的真实ID，不从名称拼接。业务时间为Asia/Shanghai，核验时间按原字段日期或`yyyy-MM-dd HH:mm:ss`展示。

### GET /api/companies/{company_id}/relations/{relation_id}

用途：该企业的一条双端关系和对手方自身资料。无请求体；`company_id`、`relation_id`为必填持久字符串。页面打开/重试时调用，可安全重复。

成功200响应：

```jsonc
{
  "company": {"id":"查询企业ID", "name":"查询企业全称", "short_name":"查询企业简称"}, // 关系一端，值来自当前主档
  "relation": {
    "id":"关系ID", // 独立持久关系ID
    "counterparty_name":"原报告对方名称", // 保留组合披露原名
    "counterparty_id":null, // 身份未核验则空，不能填主企业ID
    "relation_type":"supplier", // supplier/customer/subsidiary/service_supplier等原关系类型
    "relation_label":"采购供应商", // 中文关系名称
    "direction":"查询企业向该企业采购", // 真实交易或控制方向
    "from_name":"供应商名称", "to_name":"查询企业简称", // 供货箭头的起点、终点
    "reason":"2025年报 · 第1位", // 已披露报告期及名单排序，未推断产品
    "report_period":"2025", // 原报告期
    "amount":null, "share":null, // 未披露金额/占比保持空，不填零
    "amount_label":"采购额", "unit":"元", "currency":null, // 金额含义、原单位、未知币种
    "trade_product":null, // 没有交易产品专属证据则空
    "detail_url":"/companies/查询企业ID/relations/关系ID", // 每条关系自己的地址
    "identity_status":"reported_name", // reported_name/verified/composite
    "evidence_refs":[] // 原条目引用投影，包含binding_id/text/url等字段
  },
  "counterparty":null, // 未绑定为空；有值含id/name/short_name/facts/sources/research_as_of/profile_url，只读对方自己的verified字段
  "research_state":{} // 尚未补查为空；已执行含status/job_id/updated_at
}
```

对手方facts允许name/short_name/business/products/industry/address/website，字段值结构沿用企业详情fact_view。来源只来自这些字段自己的source_ids，不借用查询企业介绍。一个年报可证明多家关系，真实同一报告URL保持相同，原文片段分别绑定。

失败404：

```jsonc
{"error":"企业关系不存在", "request_id":"本次请求诊断ID"} // 企业/关系不存在或归属不一致；不返回其他企业资料
```

未知类型使用“公开关系”兜底；组合主体counterparty始终为空。主企业与关系必须同归属；金额/统计期不跨口径汇总。

### POST /api/companies/{company_id}/counterparties/research

用途：显式补当前最新报告期首屏供应商/客户，默认各5家。响应202为真实queued Job，后续通过现有SSE/status读取。`company_id`必填且存在。每次动作生成token；失败重试复用相同token。

### POST /api/companies/{company_id}/relations/{relation_id}/research

用途：只补当前关系对手方；两个ID必填且同归属。允许supplier/customer/service_supplier/subsidiary，组合主体保留缺口。成功202和请求体与上一个接口一致：

| 字段 | 类型与约束 | 空值行为 |
| --- | --- | --- |
| client_token | 必填string，8..100字符 | 空/过短422 |
| conversation_id | 可选string，最多64字符 | 空则创建明确补查会话 |
| content | 可选string，最多20000字符 | 服务固定为已选上下游补查范围 |

```jsonc
{"client_token":"前端生成的UUID", "conversation_id":null, "content":""} // 值分别为幂等标识、新建会话、采用固定补查范围
```

成功202：

```jsonc
{"id":"真实JobID", "conversation_id":"实际会话ID", "status":"queued", "company_ids":[], "metrics":{"counterparty_only":true,"counterparty_relation_ids":["实际关系ID"]}} // 沿用完整Job投影；空结果表示尚未执行
```

失败404企业或关系不存在；422暂无可补齐关系；409会话有活动任务/token已用于另一操作。

```jsonc
{"error":"此对话已有执行中的任务", "request_id":"本次请求诊断ID"} // 409原因和诊断ID，保留当前任务供重试
```

无隐式子Job。模型/搜索/读取/累计时长共用这个Job；每家补查有持久子阶段，暂停后优先分析已归档来源。部分资料/预算不足返回partial及counterparty_progress.pending，不补造网址。同名代码冲突拒绑定，组合主体不截断后缀绑定单公司。

### POST /api/jobs/{job_id}/identity-confirmation

用途：明确选择候选或补充全称/地区，续接原needs_input任务。无新增鉴权；同会话、候选revision、活动任务及来源再次验证。仅身份候选确认可调用，普通聊天/文件匹配沿原入口。

| 字段 | 类型与约束 | 空值行为 |
| --- | --- | --- |
| conversation_id | 必填string，1..64字符 | 不匹配原Job返回404 |
| resolution_revision | 必填int，>=1 | 不是当前版本409 |
| client_token | 必填string，8..100字符 | 同token同请求幂等，不同请求409 |
| candidate_id | 可选string，最多64字符 | 空表示补充信息；无此候选422 |
| name | 可选string，最多200字符 | 空且有context沿原requested_name核验 |
| context | 可选string，最多500字符 | 空则没有新增地区/行业/官网条件 |

选择候选：

```jsonc
{"conversation_id":"当前会话ID", "resolution_revision":1, "client_token":"前端生成的UUID", "candidate_id":"当前候选ID", "name":"", "context":""} // 值依次为原会话、当前候选版本、幂等标识、明确选择、无补充全称、无补充条件
```

补地区：

```jsonc
{"conversation_id":"当前会话ID", "resolution_revision":1, "client_token":"前端生成的UUID", "candidate_id":null, "name":"", "context":"江苏"} // 沿原requested_name消歧，地区不能成为企业名称
```

candidate_id与name/context互斥；补充方式至少name/context一个非空。成功202沿原Job投影，id不变、status=queued，model_budget/elapsed_ms保留，原Job.prompt/原用户消息不改，另加一条确认消息。等待用户期间不累计执行时间。

失败：404任务/会话不匹配；409版本更新、当前非待确认、活动冲突、来源不可用或token冲突；422无效候选/空输入/互斥冲突。

```jsonc
{"error":"候选已更新，请重新读取后选择", "request_id":"本次请求诊断ID"} // 409原因与诊断ID；重新读取原任务，不新建任务清零预算
```

Job.metrics.company_resolution包含requested_name/status/revision/candidates/name；status为pending/insufficient/needs_confirmation/resolved。候选包含id/name/company_id/source_id/identity_quote/alias_quote/address/industry/url/title/automatic；地址/行业未知为空。候选不自动存CompanyFact；只有真实全文明确名称映射且候选唯一才自动补全。SSE附加identity.resolved/identity.candidates；终态GET取得同样metrics，旧前端仍可读文字答复，新确认交互需更新前端。

增量迁移20261009_04保留Evidence/事实/任务，新增文档、片段、强外键绑定；每个绑定恰有事实/关系/项目/公告一种条目。bind_company_sources同步参与原保存事务、不commit，重复绑定新增数为0。研究保存逐source+quote+role追加source_citations；历史回填仅补引用，保留后续研究日期/元信息和人工审核字段。连续原文唯一匹配只折叠排版空白；人工页码/多处重复/合并摘录不能生成定位。
