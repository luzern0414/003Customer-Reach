# CLAUDE.md — AI 获客系统（003Customer-Acq）

> 给所有在本仓库工作的 Agent（Claude Code / Codex / Cursor 等）的项目说明。`AGENTS.md` 与本文件内容一致。

## 项目在做什么

一个 **B2B AI 获客系统**。用户通过对话提出需求，Agent 自动调用工具，从以下数据源查询目标企业的信息：

- 招投标与政府采购：乙方宝（会员控制台 + 公开搜索）、千里马、中国采购与招标网、剑鱼标讯、必联网、中国政府采购网、全国公共资源交易平台、中国国际招标网（经 Exa）、Exa 全网检索
- 企业工商：必联网企业库 + Exa 检索工商公开页（爱企查、企查查等摘要）；后续接入企查查 API
- 货源：1688

输出内容包括：

- **采购信息**
- **客户画像**
- **上下游关系**：供应商、客户、竞争对手

当前阶段：

- 设计文档已完成（`docs/`）。
- 已实现第一个可用工具：**`acq` 定制信息查询工具**。它基于 OpenCLI + Edge + Exa，按企业名采集 10 个数据源的招投标信息和企业工商信息，并生成报告。对应的项目 skill 为 `.claude/skills/company-intel`。
- 主系统（FastAPI + LangGraph + Next.js）**尚未开始编码**，开发计划见 `docs/02-产品与开发/开发记录/09-dev-plan.md`。

## 关键入口

| 想做什么 | 看哪里 / 用什么 |
|---|---|
| 了解需求与架构 | `README.md` → `docs/01-商务与需求/客户资料/01-PRD.md`、`docs/02-产品与开发/设计文档/02-architecture.md`、`docs/02-产品与开发/设计文档/03-agent-and-tools.md` |
| **按企业全量采集采购和企业信息**（最常用） | skill `company-intel`，即 `scripts/acq company "企业全称"`，详见 `docs/02-产品与开发/设计文档/11-acq-query-tool.md` |
| 检查浏览器、插件和登录状态 | `scripts/acq doctor` |
| 登录站点（乙方宝等） | `scripts/acq login yfbzb`：自动在 Agent 专用 Edge 打开登录页，等待用户完成登录 |
| 直接调用单个站点命令 | `opencli yfbzb search/public/detail/whoami/login`、`qianlima search`、`chinabidding search`、`jianyu list`、`ebnew search/company`、`ccgp search`、`ggzy search`（加 `-f json`） |
| 修改或新增站点适配器 | `src/opencli-plugin/`（OpenCLI 插件 `acq`），规范见 `docs/11` §5 |
| 数据源接入策略 | `docs/02-产品与开发/设计文档/04-data-sources-integration.md`、`config/sources.yaml` |

## 目录约定

```
config/                 配置：acq_tool.toml（查询工具）、sources.yaml、models.yaml、settings.example.yaml
data/browser-profile/   Agent 专用 Edge 配置（含登录态 cookie，不提交，不要删除）
data/processed/companies/<企业名>/   查询报告（latest.md + 时间戳 .json/.md）
data/raw/               原始快照（acq_query/<日期>/、samples/ 实测样例）
docs/                   设计文档（01–11）、research/ 调研、adr/ 决策
src/opencli-plugin/     OpenCLI 插件 acq：yfbzb-*.js、qianlima/chinabidding/jianyu-list/ebnew/ccgp/ggzy-*.js、lib/
src/tools/acq_query/    Python 编排工具（只用标准库）：cli / edge / opencli / exa / sources / report
scripts/acq(.cmd/.ps1)  acq 启动脚本
```

## 工作规则（Agent 必读）

1. **浏览器使用 Edge，不使用 Chrome**。
   - Agent 专用 Edge 配置目录为 `data/browser-profile/edge-agent`，OpenCLI 扩展位于 `C:\Users\Chilth\.opencli\browser-extension`。
   - `scripts/acq` 会自动启动这个 Edge，并保证扩展已连接。不要用个人浏览器配置做自动化。
2. **需要登录或输入验证码时，让用户来做**。
   - 运行 `scripts/acq login <site>`，或在 `company` 流程中自动提示。工具会在 Edge 前台打开登录页并轮询，用户完成后自动继续。
   - 全国公共资源交易平台弹出验证码时，ggzy 命令会等待用户在 Edge 中输入。
   - 不要尝试自己填写账号密码，也不要自动识别验证码。
3. **内容获取走多通道**：API/MCP → Exa → OpenCLI 真实浏览器（已登录会员）。
   - 读到占位内容时升级到下一个通道，例如 `****`、`点击登录查看`、登录页。
   - 会员详情（联系人、电话）会消耗乙方宝每日查看额度，**调用 `--details` 前需征得用户同意**。
4. **修改 `src/opencli-plugin/*.js` 后**：
   - 先运行 `node --check` 检查语法；
   - 再用 `opencli yfbzb search "航天广通" --limit 3 -f json` 等命令实测；
   - 插件通过 `file://` 链接安装，改动即时生效。新增命令文件时，需重启 daemon：`opencli daemon restart`。
5. **站点接口知识**（已实测的 endpoint、参数、字段含义）写在 `docs/02-产品与开发/设计文档/11-acq-query-tool.md` §4。接口变化时同步更新该文档。
6. 不提交 `data/browser-profile/`、`.env`、`config/settings.yaml`。
7. 文档用中文；代码注释风格与周围代码保持一致。

## 环境

- Windows 11，Git Bash 与 PowerShell 均可用。
- Node 24、Python 3.14（`acq` 只用标准库，无需安装依赖）、uv、pnpm。
- 已全局安装的工具：
  - OpenCLI 1.8.8：`npm i -g @jackwener/opencli`
  - Agent Reach 1.5.0
  - mcporter：已配置 Exa MCP
- 详见 `docs/02-产品与开发/设计文档/10-env-setup.md`。
