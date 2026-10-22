# 配置目录

本项目只有本机单工作空间（开发与生产同一套部署方式），配置分“本地密钥文件”“可提交的非敏感配置”“界面设置（数据库）”三类。

## 1. 文件清单

| 文件 | 是否提交 | 用途 | 必填 |
|---|---|---|---|
| `apikey.txt` | **否**（.gitignore） | 模型服务地址与 Key；可选 LangSmith Key（`lsv2_…`）、Exa Key（`exa_api_key=`）、企查查 MCP Key（`qcc_mcp_key=`）。模板见 `apikey.example.txt` | 是 |
| `langsmith.json` | 是（无密钥） | `enabled` 是否上报链路、`project` 项目名、`hide_inputs/hide_outputs` 是否隐藏提示词与输出 | 否 |
| `langsmith.example.json` | 是 | 生产建议值（默认关闭、隐藏输入输出） | — |
| `acq_tool.toml` | 是 | 招投标采集复用的 OpenCLI/Edge/Exa 配置：内置 OpenCLI 目录（`vendor/opencli`）、Agent 专用 Edge 配置目录、OpenCLI 扩展目录、插件目录、检索天数与条数 | 否 |
| `sources.yaml`、`sources/`、`policies/`、`schemas/` | 是 | 来源授权、限速、隐私与数据结构说明 | — |
| `backup-keys/`、`secrets/` | **否** | 加密备份的恢复钥与本地副本，只在本机 | — |

密钥只放在 `apikey.txt` 或环境变量中，不写进其他配置文件、日志或文档；`apikey.txt` 的读取只解析不回显。

## 2. 环境变量（优先于文件）

| 变量 | 默认 | 说明 |
|---|---|---|
| `CLIENTREACH_MODEL_URL` / `CLIENTREACH_MODEL_KEY` | 读 `apikey.txt` | 模型服务地址与 Key |
| `LANGSMITH_API_KEY` | 读 `apikey.txt` 中 `lsv2_` | 设为空字符串可显式关闭 |
| `LANGSMITH_TRACING` | `langsmith.json.enabled` | `true/false` |
| `LANGSMITH_PROJECT` | `client-reach` | LangSmith 项目名 |
| `LANGSMITH_HIDE_INPUTS` / `LANGSMITH_HIDE_OUTPUTS` | `langsmith.json`，缺省 `true` | `false` 时上传提示词与输出（含公开联系方式），仅在自有账号调试时使用 |
| `EXA_API_KEY` | 读 `apikey.txt` 中 `exa_api_key` | 不配置时匿名访问 Exa，密集使用会被限流（429） |
| `QCC_MCP_API_KEY` | 读 `apikey.txt` 中 `qcc_mcp_key` / `qcc_api_key` | 企查查官方 MCP Bearer Key；只报告是否配置，不回显 Key |
| `CLIENTREACH_DATA_DIR` | `data/app` | 业务库、checkpoint、上传文件、企业标识缓存（`logos/`）目录 |
| `CLIENTREACH_DATABASE_URL` | `sqlite:///data/app/clientreach.db` | 业务数据库连接 |
| `CLIENTREACH_TENDER_ENABLED` | 开启 | `false` 时不访问招投标平台（测试默认关闭） |
| `CLIENTREACH_SEARCH_FALLBACK` | 开启 | `false` 时 Exa 失败不再改用 OpenCLI 百度/搜狗检索（测试默认关闭） |
| `OPENCLI_PLUGIN_DIRS` | `src/opencli-plugin` | 内置 OpenCLI 从这些目录加载插件（`;` 分隔），无需 `opencli plugin install` |
| `CLIENTREACH_WEB_DIST` | `web/dist` | 前端构建目录 |
| `SSL_CERT_FILE` / `SSL_CERT_DIR` | certifi | 自定义 CA |

## 3. 界面设置（设置 → 工作空间，保存在数据库）

QCC MCP 探针使用 `scripts/mcp_probe.py --server qcc-company|qcc-operation|qcc-risk|qcc-tender --operation list|basic`。`basic` 只能调用 `config/qcc_mcp_bindings.yaml` 中与当前 tools/list 精确匹配的只读绑定，并要求显式 `--company-name`；探针输出和保存报告会脱敏凭据。

搜索/读取次数、模型调用与令牌预算、最长耗时、研究轮数、读取并发，以及 v0.4 新增：

- **招投标平台检索**（`tender_enabled`，默认开）：研究采购/上下游时先查招投标平台；
- **每家企业读取公告详情**（`tender_detail_reads`，默认 6，0–16）：用于补全物资清单、中标方与金额；
- **招投标数据复用时长**（`tender_reuse_hours`，默认 24，0 表示每次重新采集）：时长内直接复用已保存记录与检索结果。

## 4. 地址与服务

| 项 | 值 |
|---|---|
| 前端 + 后端 API | `http://127.0.0.1:8000`（只监听本机） |
| 接口文档 | `http://127.0.0.1:8000/docs` |
| 前端开发服务器 | `cd web; npm run dev`（`/api` 代理到 8000） |
| 数据库 | SQLite，启动时自动执行 Alembic 迁移（当前 head `20261010_05`） |

本项目没有账号体系、管理员账号或小程序端；仅本机访问，不对外开放端口。

## 5. 验证配置

```powershell
backend\.venv\Scripts\python.exe backend\check_v2_model.py      # 模型：工具调用/结构化输出/流式
Invoke-RestMethod http://127.0.0.1:8000/api/health              # 服务与后台任务
Invoke-RestMethod http://127.0.0.1:8000/api/tracing             # LangSmith 配置状态（不返回密钥）
scripts\acq doctor                                               # Agent 专用 Edge 与 OpenCLI 扩展（会员/验证码类来源需要）
```
