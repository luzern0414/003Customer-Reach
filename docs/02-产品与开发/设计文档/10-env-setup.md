# 10 本机环境与工具安装记录

> 记录日期：2026-10-08。本机环境：Windows 11、Node 24.15、Python 3.14.5、uv 0.11.20、pnpm 9.15.9、git 2.54。没有 Docker。

## 1. 已安装

| 工具 | 命令 | 验证 |
|---|---|---|
| OpenCLI 1.8.8 | `npm install -g @jackwener/opencli` | `opencli doctor` 显示 Extension: connected |
| OpenCLI 浏览器扩展 1.0.24 | 已解压到 `C:\Users\Chilth\.opencli\browser-extension` | 见第 2 节 |
| Agent Reach 1.5.0 | `uv tool install --index-url https://mirrors.aliyun.com/pypi/simple/ https://github.com/Panniantong/agent-reach/archive/main.zip` | 先设置 `PYTHONIOENCODING=utf-8`，再运行 `agent-reach doctor` |
| mcporter 0.14.2 + Exa MCP | `npm install -g mcporter`<br>`mcporter config add exa https://mcp.exa.ai/mcp --scope home` | `mcporter call exa.web_search_exa query="..."` |

## 2. 在 Edge 中添加 OpenCLI 扩展

### 方式 A：手动加载解压后的扩展（推荐）

1. 打开 Edge，在地址栏输入 `edge://extensions/`。
2. 打开左下角的 **"开发人员模式"**。
3. 点击 **"加载解压缩的扩展"**，选择 `C:\Users\Chilth\.opencli\browser-extension`，也就是 `manifest.json` 所在的目录。
4. 确认列表中出现 **OpenCLI 1.0.24**，并且处于启用状态。
5. 在终端执行 `opencli doctor`，看到 `[OK] Extension: connected` 即成功。

### 方式 B：从 Chrome 应用商店安装

1. 在 `edge://extensions/` 打开"允许来自其他应用商店的扩展"。
2. 打开 https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk ，点击"获取"。

### 方式 C：Agent 专用 Edge 配置（推荐生产使用，与个人浏览器隔离）

在 PowerShell 中执行：

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
  --user-data-dir="D:\Codes\003Customer-Acq\data\browser-profile\edge-agent" `
  --load-extension="C:\Users\Chilth\.opencli\browser-extension" `
  --no-first-run
```

之后在这个窗口中登录乙方宝、1688、剑鱼等网站，OpenCLI 会复用这些登录态。

### 注意事项

- Chrome 137 及以上的品牌版已经禁用了 `--load-extension`，所以统一使用 Edge。
- 多个配置同时连接时，用 `opencli profile list` 查看，再用 `opencli profile use <alias>` 指定要用的配置。
- 升级扩展：下载新版 `opencli-extension-v*.zip`，覆盖解压到上面的目录，然后在扩展页点"重新加载"。

### 方式 D：由 acq 工具自动管理（项目默认）

`scripts/acq doctor` 或 `scripts/acq company ...` 运行时，如果检测到扩展未连接，会自动完成以下操作：

1. 用 `data/browser-profile/edge-agent` 配置启动 Edge，并带上 `--load-extension`；
2. 在该配置中写入 `extensions.ui.developer_mode=true`；
3. 轮询 `opencli doctor`，直到扩展连接成功。

第 2 步的原因：Edge 再次启动时，会停用"命令行加载的解压扩展"，除非开启了开发人员模式。

各站点的登录态保存在这个配置目录中，**不要删除，也不要提交**。

## 3. OpenCLI 常用命令

```bash
opencli doctor
opencli list                                  # 169 个站点适配器（含 1688 / jianyu / powerchina）
opencli 1688 search "RFSOC 板卡"               # 需登录 1688
opencli browser work open "<url>"
opencli browser work state                    # 带编号的 DOM 快照
opencli browser work fill <idx> "关键词" && opencli browser work click <idx>
opencli browser work extract                  # 输出 markdown
opencli browser work eval "document.body.innerText"
opencli browser work tab list
# 项目插件 acq（src/opencli-plugin，file:// 链接安装）
opencli yfbzb whoami | login | search "<关键词>" | detail <content_id>
opencli ccgp search "<关键词>"
opencli plugin install file:///D:/Codes/003Customer-Acq/src/opencli-plugin   # 首次安装；acq doctor 会自动处理
```

## 4. 开发阶段还需要安装

- Python 3.13：`uv python install 3.13`
- PostgreSQL 18 + pgvector + zhparser：Windows 上可以用 EDB 安装包。也可以装 Docker Desktop，用 `pgvector/pgvector:pg18` 镜像。
- Redis：Windows 上用 Memurai，或在 WSL2 中运行 `redis-server`。
- 可选：gh CLI（Agent Reach 的 GitHub 渠道需要）、Langfuse（Docker 自托管）。

## 5. 已知网络问题

- 本机访问 `r.jina.ai` 时 DNS 被污染，需要走 DoH 或代理。
- 企查查网页和部分政府站点会拦截境外 IP。生产环境建议部署在大陆服务器上，境外搜索服务（Exa）单独配置出口。
