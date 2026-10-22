# 客户获客工具：安装与验证

日期：2026-09-30；执行者：Codex。

## 已安装与配置

| 组件 | 版本/来源 | 状态 |
| --- | --- | --- |
| playwright Skill | openai/skills/skills/.curated/playwright | 已安装、已验证 CLI 启动/快照/关闭 |
| exa-search Skill | exa-labs/exa-mcp-server/skills/search | 已安装，补充当前 MCP Schema 兼容说明 |
| clientreach-exa MCP | https://mcp.exa.ai/mcp?tools=web_search_exa,web_fetch_exa | 已登记；匿名 initialize/list/search/fetch 均返回成功 |
| clientreach-fetch MCP | mcp-server-fetch 2026.8.18 | 已登记；读取明宇和首旅官网返回电话/地址/邮箱 |
| clientreach-playwright MCP | @playwright/mcp 0.0.83 | 已登记；读取首旅官网联系页、取得快照并关闭浏览器 |
| Context7 MCP | 本机原有配置 | 本轮文档查询成功，未重复安装 |

MCP 新增配置保存在本机 Codex 的用户配置中，未覆盖原有服务器。`codex mcp list` 的 enabled 状态不等于连接测试通过，本轮额外执行了实际协议调用。

当前聊天原有工具目录不一定即时发现新增 MCP。独立 MCP 协议客户端已验证可调用；重新打开聊天或重新加载客户端后核查新增的原生工具是否出现。Exa 显示 `not_logged_in` 是因为本轮使用匿名限额模式，不代表匿名测试失败。没有启用 OAuth 登录、API Key 或付费 Agent。

## 本地路径

- Skill：`C:/Users/admin/.codex/skills/playwright`、`C:/Users/admin/.codex/skills/exa-search`。
- Fetch：`D:/Codes/Client-reach/tools/mcp/.venv/Scripts/mcp-server-fetch.exe`。
- Playwright：`D:/Codes/Client-reach/tools/mcp/playwright/node_modules/@playwright/mcp/cli.js`。
- 验证脚本：`D:/Codes/Client-reach/scripts/mcp_probe.py`。
- Node：`C:/Users/admin/.codex/nodejsv24.18.0/node.exe`。

这两个本地 MCP 使用项目内绝对路径；移动/删除项目或更换 Codex 运行时后需要重新登记。Node 依赖版本保存在 `playwright/package-lock.json`，Python 新增依赖版本保存在 `requirements.local-lock.txt`。

## Python 环境说明

本机已有 Python 3.10.4 是嵌入式运行时。下载额外 Python/全量二进制依赖较慢，因此使用项目虚拟环境只读复用现有全局库，并把新增的 Fetch/SDK/解析依赖安装在项目虚拟环境。未卸载、升级或覆盖全局 MCP 1.28.1。

`include-system-site-packages=true` 在此嵌入式环境下未自动找到真正的全局库目录，所以本地虚拟环境的 `Lib/site-packages/clientreach_shared_runtime.pth` 明确加入了已有运行时的库路径。这是本机兼容配置，不是可移植的完全隔离环境。

迁移到标准 Python 3.12+ 后，建议用普通隔离虚拟环境重新安装 `requirements.txt`，不再依赖这条本机共享路径。Fetch 在本轮 MCP 子进程中使用纯 Python 正文提取，输出 Node/npm 未发现的警告，但真实网页字段读取成功；需要 Readability.js 时再配置子进程 Node 路径。

## 可重复调用

```powershell
.\tools\mcp\.venv\Scripts\python.exe scripts\mcp_probe.py --server exa --operation list
.\tools\mcp\.venv\Scripts\python.exe scripts\mcp_probe.py --server exa --operation search --query "酒店集团官方会员FAQ与企业合作入口" --limit 5
.\tools\mcp\.venv\Scripts\python.exe scripts\mcp_probe.py --server fetch --operation fetch --url "https://www.bthhotels.com/Contact"
.\tools\mcp\.venv\Scripts\python.exe scripts\mcp_probe.py --server playwright --operation browser --url "https://www.bthhotels.com/Contact"
```

`--save` 只允许保存到本项目 `.codex-tmp/`，并会移除 Authorization、api_key、token 及已配置 QCC Key。企查查探针支持 `qcc-company|qcc-operation|qcc-risk|qcc-tender` 的 `list` 与 `basic`；basic 必须提供企业全称并使用当前账号 tools/list 已验证的绑定，禁止任意工具名。工具名称、积分和分页能力按账号变化，绑定文件只保存工具名/Schema，不保存密钥。

## 实测与限制

- Exa 服务 3.2.1 的搜索 Schema 要求 `query` 和 `objective`，旧 Skill 示例没有后者；本地已按实时 Schema 修正。
- Exa 是外部服务，只发送公开企业查询词和官方 URL；不上传项目文件、客户库或真实凭据。匿名额度可能变化，429 时停止并报告，不自动开通付费。
- Fetch 保留默认 robots 检查，没有配置 ignore-robots 或关闭 HTTPS 校验。
- Playwright 只负责需要渲染的页面读取/验证；搜索采用无浏览器 MCP。
- 企查查、1688 等授权数据源未接入，不表示工具已能批量获得企业工商数据或个人手机号。

## 官方来源

- [Codex MCP 配置文档](https://developers.openai.com/codex/mcp)
- [官方 Playwright Skill](https://github.com/openai/skills/tree/main/skills/.curated/playwright)
- [Exa MCP 文档](https://docs.exa.ai/reference/exa-mcp)
- [Exa Skill 源码](https://github.com/exa-labs/exa-mcp-server/tree/main/skills/search)
- [官方 Fetch 源码](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch)
- [官方 Playwright MCP](https://github.com/microsoft/playwright-mcp)
