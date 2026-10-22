# 研究与导出脚本约定

- 此目录提供由 AI 编排的公开业务资料采集、事实校验和 Excel 导出，不是无人值守 LLM 服务。
- 搜索仅调用已登记 Exa MCP；网页使用 Exa fetch，不使用浏览器搜索、登录或验证码绕过。
- 事实必须引用来源及逐字证据；未知值保留 null，分析建议与采购事实分开。
- 门店、集团、卖场运营方、品牌经销商和采购供应商不混为同一主体。
- 原始资料与客户输出进入忽略版本管理的 data 目录；测试用合成资料。
- Excel 使用 bundled @oai/artifact-tool；node_modules 是运行时 junction，不提交、不修改依赖。
- 修改脚本后运行 tests/test_lead_research.py 和真实单页采集冒烟验证。
