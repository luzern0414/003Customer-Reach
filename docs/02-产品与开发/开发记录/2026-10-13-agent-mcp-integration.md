# Agent MCP Integration Implementation Plan

**Goal:** 在现有 Agent 中实际消费企查查和 BidResearch，统一预算、证据和恢复机制。

**Architecture:** 小模块负责 MCP 传输/参数契约/证据；ToolBroker 保留统一入口；现有 LangGraph 节点使用工具返回的实际数据。客户端对象和密钥不进入状态。

**Tech Stack:** Python 3.12、MCP SDK 2.2、LangGraph、SQLAlchemy、Pydantic。

## 约束

- 使用 dev 分支；提交 `[ci skip]`，不推送、不重启生产。
- 不覆盖旧 BidMonitor 与文档改动；不修改用户 apikey.txt。
- 外部包只从固定工具目录执行，参数数组/stdio；默认关闭 REA 浏览器调用。
- 聚焦离线回归使用隔离库；真实结果写 `.codex-tmp`，不当测试样例提交。

## 任务

- [x] 凭据：`app/config.py` 支持“企查查：\nmcp key：Bearer …”，拒绝未标注或其他服务 Key；测试先失败再通过。
- [x] QCC：修正真实参数映射和响应解包；`qcc_evidence.py` 验证 JSON 路径的实际值；基本信息精确主体与事实引用测试。
- [x] 工具账本：`mcp_tools.py` 提供 bounded execution，同任务成功/失败复用、并发防重、暂停、额度和耗时；替换原独立 QCC 分支。
- [x] BidResearch：`bidresearch_mcp.py` 实现固定 stdio 会话、health/capabilities/search、有界参数与安全输出、正文归档、列表及日期范围；实际 stdio 测试。
- [x] Agent：采购 search_accounts 路由与企业招标节点消费 BidResearch；已有工具失败可补公开发现，避免重复同站检索；QCC 精确工商事实进入原有持久校验；更新最小运行能力说明。
- [x] 验证：运行 MCP/企业/渠道/采购回归、compileall、Windows CRLF规则下的diff --check、源码快照一致性与真实凭据扫描；保留环境缺失项的明确记录。
- [x] 真实验收：企查查工具绑定和基本查询；BidResearch HTTP 采购软件 / AI 查询、同任务重复调用，隔离完整 Agent，记录 sources/verified fields/预算/失败。

## 验收记录（2026-10-13）

- 完整真实 Agent：东丰教学虚拟仿真软件开发采购，预算150.41万元、2026-10-16 09:30截止、完整项目编号/买方电话/原始URL；1个当前买方，9模型，249407ms，partial，1次模型抽取超时。
- 最终 MCP 与保存：真实工商事实和软件开发查询通过，4公告/2正文，重复调用复用且attempts=1；收紧后的原文开放门禁继续保存东丰5字段。外部工具有缓存命中，不能据此声称冷启动速度。
- UI：隔离8815 API，无Worker；MCP开关与额度保存/刷新、合法渠道枚举、1440/390无溢出，控制台无错误/警告。构建通过；验证浏览器和隔离API已关闭。
- 审查：截止语义、表格/连续金额、候选报价、条件停标、泛平台建设、同买方不同公告及Knowledge误争议均先复现后修正。最终只读复核没有未解决的Critical/Important。
- 初次广泛回归684 passed/6 failed/21 errors：历史样本JSON缺失与LibreOffice缺失。未运行的9身份测试也依赖缺失历史文件；没有伪造数据或削弱测试。
- 排除上述明确环境缺项后的一轮688 passed/3 failed/6 deselected，3失败均为未修改的停止/清理时限断言；单独运行test_harness.py 23 passed/13.87s。随后无并行外部验收的完整串行复核：**691 passed / 6 deselected / 236.67s**，包括这3个时限用例。时限断言没有放宽；不能把此结果说成缺历史资料/LibreOffice的测试也已通过。
- 最终报告：`.codex-tmp/agent-mcp-final-pytest-serial.xml`。45个明确文件无本地真实凭据命中；源码编译、快照校验及暂存diff检查通过。
- 源码提示词/Schema快照已同步，生成器仅解析白名单文本；不导入业务app或读取凭据。接入使用说明见[13-agent-mcp.md](../%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3/13-agent-mcp.md)。

## 检查方法

每个功能先写行为回归、观察预期失败，再最小实现并运行。所有故障保留稳定错误码与来源状态；完成报告明确区分安装、MCP 握手、真实工具调用与 Agent 实际保存。
