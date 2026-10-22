# Web 前端约定

- Vue 3 + TypeScript + Vite + Element Plus，聊天用原生textarea和MIT markstream-vue渲染Markdown。
- 左侧仅工作台、查询结果、设置；浅色工作台，复用统一组件和状态，旧销售跟进入口为/legacy-leads。
- 所有业务数据来自后端 API；只在用户选择研究样本导入时展示历史灯具线索。
- 请求失败显示错误原因，不填模拟客户；轮询/SSE 在组件销毁时清理。
- 构建检查与本地真实浏览器验证，截图存 .codex-tmp。

## 企业研究工作台（2026-10-09）

- 全局侧栏固定为“工作台 / 查询结果 / 设置”；查询卡片、企业详情和三个Dock只消费`/api/companies`投影，不能写死企业名、金额、人数或项目数量。
- `CompanyDetail.vue`使用已确认的企业综合单页；四指标、基本信息、采购、上下游和AI区同时展示，不再使用三个Dock。旧`?tab=`不拆分页面，金额与报告期由API事实决定。
- 公开来源按条目evidence_refs显示精简卡片；文档列表读取`/api/companies/{id}/documents/{source_id}`，归档全文仅在显式点击后调用`/api/evidence/{id}`。导出、继续研究和Edge能力均调用后端，不推断联系方式归属。
- 桌面验收基准1672×941，移动验收390×844；要求Microsoft YaHei、无横向溢出、异步取消/版本守卫、真实错误和空状态。截图及量测放在`.codex-tmp/ui-workspace-check-final`。

## 已验证约定（2026-10-01）
- XSender v2通过ref.getModelValue().text取值、setText和clear操作，submit事件不携带正文；不是v1 Sender的v-model接口。
- 页面按路由懒加载，Vite将聊天/UI/vendor拆包；Element Plus全量包仍有体积提示，功能构建无错误。
- 会话详情jobs按时间降序，取[0]作为最近任务。SSE终态close，组件销毁close，连接失败由EventSource重连。
- 新建线索必须重置activeTab到profile，避免上次证据页导致空表单。修改时只PATCH已变更的允许字段，避免把公开电话重新标成人工值。
- 上传在首次发送创建对话时须保留待发附件；手工新建或测试线索应明确标签并在验证后归档。

## v0.2界面与流式约定（2026-10-02）
- 用户最新要求黑白灰（2026-10-03），包括状态色和品牌展示；图片原字节保留，通过CSS灰度。首页不显示顶部breadcrumb/线程标题，不添加重复完成数量卡或开发说明。
- markstream-vue设置html-policy=escape，不删除星号来伪装Markdown。头像/品牌图位于public；图片保持Imagegen原字节，只通过CSS展示。
- 每次切换会话递增epoch；所有await之后先复核epoch再改当前会话/任务/附件或订阅SSE。action先捕获jobId，不能await后读可变job.value.id。
- SSE delta必须按message_id和generation_id归并；reset替换旧草稿，终态刷新真实会话。后端已先排空持久事件再发终态。
- Markdown代码依赖拆为路由延迟加载chunk，不能在客户列表/设置提前加载整套聊天解析器。
- 桌面1500×960和窄屏390×844已自动截图核查；客户新建/跟进/反馈/归档、记忆CRUD、知识中文检索已实际浏览器执行。测试记录归档，测试记忆/知识停用。
- POST成功立即订阅SSE并追加临时用户消息，不先等待完整会话GET。终态刷新替换临时消息，必须测量浏览器提交至首答耗时。

## 字体与字号约定（2026-10-02）
- 用户要求全站与“客户线索”标题同类字体：统一 `Microsoft YaHei`，中英文、Markdown、代码/JSON、输入控件及Teleport浮层都使用 `--font-ui`；不另引入等宽字体或品牌字体。
- 当前字号集中在theme.css（style.css为旧版保留文件，入口不再导入）：主标题28px（窄屏24px），二级20px，三级18px，正文16px，控件15px，密集表格14px；用户2026-10-09要求所有可见文字至少14px，辅助文字及Teleport浮层也适用，移动端聊天正文仍为16px。
- 标题和客户名使用700字重；辅助信息不能只靠极浅颜色区分。无需为了文本字号调整SVG图标尺寸。
- 改字体需本地构建，然后实际检查首页、客户线索、设置全部子页及抽屉/弹窗在1440px和390px下的computed style与溢出；必要时通过Chromium CSS.getPlatformFontsForNode核实实际字体，不能只依赖CSS声明。

## 紧凑分屏与调试（2026-10-03）
- 历史只显示文字标题，无搜索/时间/矩形选中框；过程和耗时在回答上方，输入框上方不堆状态卡。ToolActivity无固定卡片，展开人话操作和来源，禁止JSON详情。
- ResultPanel仅汇总当前对话jobs关联lead_ids/附件/资料，不混入全站CRM；普通追问不清空旧结果，文件预览同会话也用独立token防迟到覆盖。
- changing锁定新建/切换期间输入，清旧草稿须在await之前；否则用户快速输入会被创建响应清掉。上传token隔离会话，旧上传不锁住新对话、不追加文件或弹错。
- textarea实际按scrollHeight伸缩44..220px，超限才滚动；检查组合输入、换行、清空和分屏宽度变化。
- displayMarkdown只过滤流式/中断的未完成粗体开头，保护代码/转义/完整最终原文，不重写持久消息。需要实际监测流式DOM，最终正常不代表过程中没有裸标记。
- Vite emptyOutDir=false，保留旧hash资源避免已打开页面懒加载404，不自动递归删dist。需要清理时移动到delete目录，且先明确使用状态。
- 2026-10-09工作台紧凑布局：Home只显示当前问题的最多10字规则短标题；移除固定“企业采购研究”副标题和输入区覆盖提示，助手正文无外层卡片背景/边框/内边距，工具过程保持直接文本行。company_query的阶段文案使用company_context/plan/collect/extract/save/gap/answer；查询结果入口只在后端真实Company投影非空时显示。
- 2026-10-09用户消息同样无气泡背景/边框/圆角/内边距，桌面和390px正文16px。回答上方显示“总耗时”，包含规划/工具/分析/回答累计执行，不能称全部为工具或纯网络耗时。

## 企业综合页（2026-10-09，Codex）

- `company-overview.css`在theme.css之后加载：统一桌面222px侧栏/60px顶栏、综合页网格和蓝/青绿/浅紫/琥珀语义色；移动断点回到0px侧栏。业务值不进入CSS或截图背景。
- `companyOverview.ts`只处理真实投影，供应商/客户按各自最新同一期展示；混单位/币种不共用刻度、不相加，未知金额/占比不填零，非CNY金额保留原数值和币种。
- 产品匹配上传/解析后显式提交`company_match + company_id + attachment_ids`，用户确认前不调用模型；失败保留资料和幂等token。真实结果在工作台和详情`purchase_analysis`展示，不能把初始资料线索称作已执行AI分析。
- 主按钮可能Teleport到body（例如产品匹配对话框），背景与文字颜色必须在全局primary规则里成对定义，不能仅在详情后代覆盖白底。


## 获客工作台（2026-10-13，覆盖旧查询仅Company约定）

- `/leads`默认获客Lead，可切换`view=companies`企业档案；`/opportunities/:id`展示逐公告需求、产品匹配、来源和CRM。原Company综合页保留，返回企业结果时带`view=companies`。
- 机会卡两个详情入口均传产品`conversation_id`；详情API验证关联，产品画像和旧分析按该对话隔离。工作台机会卡使用真实API，不注入验收样本。
- CRM修改仅PATCH跟进字段；刷新保留未提交草稿，路由版本与读取版本分开，保存/刷新等待时禁用对应输入，失败保留文本。来源全文仅显式读取；手机需求/匹配先展示，顶部锚点到跟进。
- 匹配表显示来源原文、AI条件判断、缺口和下一步；程序引用核验不称全部语义准确，不输出购买概率，预算/限价/成交分开，未知条件保留。
