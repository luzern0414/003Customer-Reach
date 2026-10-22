# 共享组件约定

- 2026-10-09产物精简：ArtifactPanel企业卡片合并画像/导出，研究计数和来源列表折叠；来源资料不等同核验事实。手机has-panel覆盖原display:none，以可关闭侧栏呈现；真实1672/1440/390宽度核查，不仅看DOM存在。

- 2026-10-09 ArtifactPanel使用实际研究计数、来源与阶段；搜索摘要显式标记，清洗不等于全文核验。历史轮次的数据集入口保留，所有文字最低14px。

- 2026-10-05 FactValue.wechat仅对后端copyable===true且非失效/争议的完整原值显示复制，不生成tel/weixin链接，不发消息；失败提示选择文本。真实Agent结果隔离副本实际复制15013617190成功，stale后原值保留、复制按钮0，1440/390页面无横向溢出、微软雅黑、控制台无warn/error。

- ToolActivity新增可选read_summary短文本（SSE及持久GET一致），失败时优先其“网页无可用正文，备用读取服务受限”摘要；旧记录无此字段沿原错误文本，不显示read_outcome/HTTP代码/JSON。1440×960/390×844隔离真实任务实际展开、刷新、截图检查，微软雅黑/无横向溢出/控制台无警告。桌面已打开面板缩到手机会遮聊天，先关闭真实结果抽屉再验工具；首次窄屏刷新默认面板关闭，不以DOM有文本当屏幕已可见。

- ToolActivity搜索标签附“检索”说明查询方向，fetch标签使用arguments.url实际hostname；例如mall_directory返回招聘页仍显示zhaopin.com，不授予商场/官网身份。URL解析失败回公开网页，不显示参数JSON。

2026-10-02，Codex，继承web/AGENTS.md。
- ToolActivity只呈现真实工具账本/SSE投影；operation_id稳定合并，默认折叠，内层显示参数、来源摘要、状态及耗时。
- 不把隐式推理、模型格式化步骤或前端模拟进度称为工具调用。刷新后使用后端持久轨迹，不仅依赖本次EventSource事件。
- 原生details保留键盘可操作性；重放事件不能重复增加工具行。字体来自全局--font-ui。
- 最新UI为无边框文本过程行；详情使用query/url/customer总结，不渲染JSON。ResultPanel显示同对话真实结果、原文预览、解析统计，空值保持空，不从模型字符串猜文件。
- 累计耗时配合attempts显示次数；仅completed复用显示已复用。错误码显示人话，未知异常不直接显示代码/JSON。
- ResultPanel按实际matched_products显示相关产品或“产品适配待核验”，已核验角色与确认采购不是同一状态。
- 右面板来源链接按URL去重，不把同页各字段引文重复显示成多个来源；后端逐字段证据保持完整。
- FactValue统一展现原值、争议/失效、口径/日期和可折叠替代值；失效/争议电话保留完整号码但不提供tel操作。ProcurementSignals显示独立公告时效/截止/来源，原文默认折叠；汇总链接排除已展示公告URL。
- ResultPanel联系详情含角色、邮箱、网站、地址、联系人和缺口，来源用原生折叠按URL去重显示平台/日期。FactValue安全生成tel/mailto/HTTP(S)，原文短号不拨号、不补区号，失效/争议无联系动作。
- 电话操作只用后端派生contact_href，不在前端按数字长度重新猜测；原文文本不格式化。异常phone_status显示“号码格式待核验”，登录/验证工具失败显示人话，不暴露JSON或内部模型修复内容。
- FactValue的additional_contact显示后端派生链接，父事实失效/争议禁止动作；ProcurementSignals折叠展示同源项目/采购人/截止三个独立片段，不合并为一段原文。
- robots拒读/规则未知显示简短人话，不展示代码或供应商原始响应，不能将来源无正文标为取得企业数据。
- parse_account显示“解析商户资料”及原页链接，参数source_id不展示为代码。official历史通道可能读取第三方公开链接，工具标签改“公开网页”，不以路由名授予企业官网身份；真实平台仍按来源域名显示。
- ResultPanel联系人姓名/职位也复用FactValue，原值保留且争议/失效状态可见；不直接拼接原始字段绕过核验。隔离8011夹具在1440px/390px实际DOM/截图验证，无横向溢出、无短号拨号或失效邮箱动作；夹具不得混入正式CRM。
- 来源折叠标题使用后端contact_summary.site_count与source_count分别显示网站/页面，移动站同根域合并；汇总链接仍按URL去重并排除已展示公告链接，不能用剩余链接数冒充客户全部证据数。2026-10-04隔离8011三页面/两网站夹具在1440/390实测展开与无溢出，原字段状态保持。

## 企业工作台共享组件（2026-10-09）

- `EnterpriseCard.vue`只渲染后端摘要；`ArtifactPanel.vue`只列真实企业导出/详情入口和附件，不从回答文本解析客户。
- `theme.css`保持基础组件/字体，`company-overview.css`维护最新统一外框与综合详情网格/390px断点；新增页面沿用token，不另起品牌色或字体。EnterpriseCard和ArtifactPanel都直接链接企业综合详情，不再传tab。
- ToolActivity把empty_results显示为“无匹配结果”，completed不能自动当取得资料；persist_company用后端company_id/accepted_fields/rejected_count展示“企业已保存/通过核验/待核验”，不显示“0个来源”作为保存结论。fetch_browser和persist_company使用中文操作名；模型不是网络工具，不向工具列表添加隐式推理。
