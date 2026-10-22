# 04 数据源接入与内容获取方案

> 本文说明如何**完整获取**各网站和接口的内容：获取通道、通道路由、完整性校验、数据源清单、采集 Worker、降级策略。
>
> - 各数据源的调研细节见 `research/02` 和 `research/03`。
> - 数据源注册表见 `config/sources.yaml`。

## 1. 内容获取通道

| 通道 | 能力 | 适用 |
|---|---|---|
| **① API / MCP** | 结构化数据，稳定 | 企查查 / 启信 / 天眼查开放平台、1688 开放平台、剑鱼 / cebpubservice 数据接口 |
| **② Exa** | `web_search_exa` 做全网检索；`web_fetch_exa` 从云端读取网页全文（Markdown） | 线索发现；公开公告页全文（已实测 ccgp、ggzy、采招网） |
| **③ OpenCLI 真实浏览器** | 在 Agent 专用 Edge 中打开页面，复用**已登录的会员账号**，能执行 JS、渲染 SPA。读取方式有四种：<br>`extract`：整页 Markdown<br>`eval`：DOM 文本或字段<br>`network`：拦截 XHR 拿到结构化 JSON<br>`state` + `click` / `fill`：搜索、翻页、展开 | 需要登录或会员的站点、SPA 控制台、动态渲染页面。例如：乙方宝 / 千里马控制台、企查查网页、1688、剑鱼、央企采购平台 |
| **④ 轻量 HTTP** | httpx / Crawl4AI 直接请求 | 静态页，批量列表页翻页 |

**实测结论（2026-10-08，OpenCLI + Edge）**：

- 中国联通采购与招标网、华能电子商务平台：之前用纯 HTTP 请求返回 412，**在真实浏览器中可以正常打开并读取**。
- 全国公共资源交易平台的交易列表页：可以正常加载。
- 企查查网页：要求登录。在 Agent 专用 Edge 中登录企查查会员账号后，即可读取。
- 乙方宝：公开页读取正常。完整字段需要会员账号，见 §4。

## 2. 通道路由与完整性校验（Fetch Router）

```
fetch(url | query, need_fields[])
  1. 本地快照命中且未过期 → 返回
  2. 按 source 配置的通道顺序依次尝试，例如：
       公开公告页: ② Exa fetch → ④ HTTP → ③ OpenCLI
       登录/会员站: ③ OpenCLI(会员账号)
       工商数据:   ① API/MCP → ③ OpenCLI(企查查网页, 已登录)
  3. 完整性校验 completeness_check(content, need_fields):
       - 是否包含 need_fields（如 采购企业、联系人、电话、金额）
       - 是否为占位内容：'****'、'点击登录查看'、登录页、'Environment Checking' 等等待页、空列表
     不完整 → 升级到下一个通道（如 Exa → OpenCLI 已登录会话）
  4. 需要用户在浏览器中操作才能继续（登录过期、页面要求人工确认）：
       → interrupt(type="browser_action", site, url, hint)
       → 前端提示"请在 Agent 浏览器窗口中完成登录/确认"，用户完成后点"继续"，Router 从第 3 步重试
  5. 会员额度类字段（如乙方宝详情的联系人）：
       → interrupt(type="cost_confirm") 确认后用会员账号读取详情
       → 同时尝试按"信息来源"回溯原始平台，读取原平台公开全文
  6. 保存快照 data/raw/<source>/<yyyymmdd>/<id>.{html,md,json} + 元信息
```

- **通道顺序和等待时间**在 `config/sources.yaml` 中按站点配置：
  - `channels`：通道顺序；
  - `wait_seconds`：页面渲染等待时间；
  - `need_login`：是否需要登录；
  - `account`：使用哪个账号。
- **OpenCLI 读取的最佳实践**：
  - 优先用 `network` 捕获页面自身的 XHR JSON，字段完整且稳定；
  - 其次用 `extract` 获取 Markdown；
  - 最后用 `eval` 读取 DOM。
  - SPA 页面通过 `wait selector/text/xhr` 等待目标内容出现，避免读到空页面。
- **请求节奏**：每个站点配置 `rate`（请求最小间隔）和 `daily_cap`（每日上限），使用单一会话顺序访问，节奏接近正常人工浏览，从而保证会话长期稳定。

## 3. 数据源清单与优先级

| 源 | 通道 | 用途 | MVP | 节奏 / 额度 | 缓存 TTL |
|---|---|---|---|---|---|
| 企查查开放平台 / 官方 MCP（agent.qcc.com） | ① | 主体识别、工商、股权、风险、信号、招投标 958 | ✅ | 按预算 | 工商 30 天，风险 7 天，招投标 1 天 |
| 企查查网页（已登录会员） | ③ | API 没覆盖的字段、关系图谱页、补充核对 | ✅ | 间隔 ≥3 秒 | 同上 |
| 启信宝 / 天眼查 | ① / ③ | 备选 | ⏳ | — | 同上 |
| **乙方宝 / 千里马 会员控制台** | ③ | 标讯搜索列表（摘要含采购企业）、按企业查采购历史、详情（含联系人） | ✅ | 列表间隔 ≥3 秒；详情受会员额度限制（黄金会员 30 条/天） | 列表 1 天，详情永久 |
| 中国政府采购网 ccgp | ② → ④ → ③ | 政府采购公告（招标、中标、合同） | ✅ | 间隔 ≥1 秒 | 永久快照 |
| 全国公共资源交易平台 ggzy | ③ → ② | 工程、政采、土地等交易公告 | ✅ | 间隔 ≥3 秒 | 永久快照 |
| 中国招标投标公共服务平台 | ② / ③；信息 API ① | 依法必须招标项目，覆盖央企 | ✅ 页面；API 需商务洽谈 | — | 永久快照 |
| 剑鱼标讯 | ③（已登录）/ ① 数据接口 | 标讯 + 采购单位库 | ⏳ | — | — |
| 央企电子采购平台（国网 ecp、易派客、中国移动 b2b、电信阳光、联通、华能、华电、国铁 95306、电建、云筑等） | ③ → ② | 集团集采公告 | 二期（先接联通、华能，已实测可读） | 间隔 ≥3 秒 | 永久快照 |
| 航天电子采购平台 e-casic | ③ / ② | 航天科工体系询价单（乙方宝很多数据的原始来源） | 二期 | — | — |
| 省级政府采购网 / 交易中心 | ② / ④ / ③ | 地方采购 | 二期 | — | — |
| 1688 开放平台 | ① | 商品与供应商 | 申请中 | 100–300 次/分钟 | 7 天 |
| OpenCLI `1688` 适配器（search / item / store） | ③ | 商品、店铺、供应商信息 | ✅ | 间隔 ≥3 秒 | 7 天 |
| Exa（MCP / API） | ② | 全网线索发现 + 网页全文 | ✅ | 免费 MCP 额度低，正式环境用 API key | 1 天 |
| 博查 Bocha | 搜索 API | 中文网搜 | ✅ | 按套餐 | 1 天 |
| 国家企业信用信息公示系统 gsxt | ③ | 工商登记、年报、经营异常（权威来源） | 二期 | 需要用户在浏览器中完成页面确认 | 30 天 |

## 4. 乙方宝（千里马）完整内容获取（已实测，已实现为 OpenCLI 插件 `yfbzb`，见 `11-acq-query-tool.md`）

| 项 | 结论 |
|---|---|
| 公开页 `www.yfbzb.com/inviteBid/detail/{yyyymmdd}_{id}.html` | 能读到标题、地区、日期、询价人、物资明细、信息来源。会员字段显示为 `****`，即使登录后公开页也一样 |
| **会员控制台搜索** `qiye.qianlima.com/new_qd_yfbsite/#/infoCenter/search` | 登录后可以关键词搜索，列表摘要含**采购企业、询价单编号、询价人、中标确认时间**，可以按企业查到完整采购历史。读取列表不消耗详情额度 |
| **会员控制台详情** `#/infoCenter/infoDetail/{contentId}/{areaId}/zhaobiao` | 完整字段（询价单名称/编号、询价人电话、采购企业、联系人）在这里展示。每看一条消耗一次查看额度，黄金会员每天 30 条 |
| 地区权限 | 由账号开通的地区决定（当前为北京、广东）。搜索全国时需要开通"全国" |
| **获取完整内容的流程** | ① OpenCLI 在控制台搜索，拿到列表和 contentId<br>② 列表摘要直接入库<br>③ 需要联系人时，按 contentId 打开控制台详情，经 `cost_confirm` 确认额度后读取完整字段<br>④ 同时根据"信息来源"回溯原始平台（如 e-casic），读取原平台全文进行补全和交叉验证 |
| 开发待办 | 写 OpenCLI adapter：`yfbzb search` / `yfbzb detail` / `yfbzb buyer-history`（参考 `opencli-adapter-author` skill）。优先拦截控制台 XHR JSON |

## 5. 企查查接入

- **API 方式**：
  - Header `Token = MD5(AppKey + Timespan + SecretKey)`，转 32 位大写；
  - `Timespan` 为秒级时间戳；
  - Query 参数 `key=AppKey`。
- **调用链**：
  1. 886 模糊搜索
  2. 410 工商信息
  3. 按需调用：731 股东、884 对外投资、739/740/741 风险、718 招聘、514 专利、958 招投标
- **网页方式（已登录）**：在 Agent 专用 Edge 中登录企查查会员，用 OpenCLI 读取企业详情页（基本信息、股东、对外投资、招投标、供应商客户等标签页）。适用两种情况：
  - API 没有购买对应接口时，补全字段；
  - 需要展示企查查图谱页内容时。
- **成本控制**：
  - 按 `credit_code + api_code` 缓存；
  - 每次 run 设预算上限；
  - 超出预算时优先改用网页通道。

## 6. 采集 Worker（src/crawlers）

```
SourceAdapter (抽象)
  ├─ name, channels[], rate, daily_cap, ttl, account
  ├─ search(query) -> list[RawListItem]
  ├─ fetch_detail(item) -> RawDetail          # 经 Fetch Router，含完整性校验
  ├─ parse(raw) -> TenderNotice               # 规则解析 + LLM 抽取 + 原文校验
  └─ session_check() -> ok | login_required | need_user_action
```

- **调度**（Arq cron）：
  - 每天 3 次：按"订阅关键词 × 地区"增量拉取 ccgp、乙方宝控制台、ggzy 的列表。
  - 每小时 1 次：对新增条目抓取详情，做解析、抽取、校验，然后去重合并。
- **浏览器任务队列**：同一个 Edge 配置的 OpenCLI 任务**串行执行**，Agent 的实时请求优先于后台采集。
- **会话保活**：
  - 定时执行 `opencli <site> whoami` 或访问控制台首页，检查登录状态；
  - 登录失效时，在前端设置页提示重新登录。
- **快照**：保存原文和元信息（URL、时间、账号、通道、HTTP 状态），用于证据回溯和重新解析。

## 7. 降级矩阵

| 情况 | 处理 |
|---|---|
| Exa 读取的内容不完整（缺字段或是占位内容） | 升级到 OpenCLI 已登录会话读取 |
| 登录过期 / 页面要求人工确认 | `browser_action` interrupt：用户在 Agent 浏览器中处理后继续 |
| 企查查 API 余额不足 | 改用企查查网页（已登录）→ 启信 / 天眼查 |
| 乙方宝详情额度用完 | 回溯原始平台读取全文；第二天额度恢复后补全联系人 |
| Exa 限额用完 | 改用博查 + OpenCLI 直接读取 |
| LLM 主模型故障 | 按 models.yaml 的 fallback 切换 |
