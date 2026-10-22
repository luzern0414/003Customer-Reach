# src 模块约定

- `collectors` 只获取原始数据和来源元信息，不直接写 CRM 主数据。
- 数据流固定为 raw → staging → normalized → evidence/fact → review → CRM。
- 关键字段必须有来源、时间、置信度和核验状态；无证据返回未知。
- 企查查/1688 适配器在授权 API 或客户导出确认前不得实现页面批量抓取。
- Agent 只能查询已核验证据、创建候选/任务和生成报价草稿，不能自动营销或发送报价。
