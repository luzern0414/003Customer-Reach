# MCP 运行环境约定

- Python 和 Node 依赖隔离在此目录，不改变已有系统环境或第三方仓库。
- 仅采用登记的官方服务；固定版本、保留锁文件并执行 MCP 握手/工具调用验证。
- Exa 只用匿名限额搜索/读取，不启用收费 Agent、账号登录或私有连接器。
- 搜索不得使用浏览器；Playwright 只用于页面读取/界面验证。
- 遇到登录、验证码、风控、付费墙或限流时停止；不得关闭 TLS 验证或改用伪装后端。
- QCC 仅使用官方 agent.qcc.com MCP；探针只执行 initialize/tools/list 或已验证的只读 basic，报告不得包含凭据。
- 当前新增 MCP 配置名为 clientreach-exa、clientreach-fetch、clientreach-playwright，不覆盖已有配置。
