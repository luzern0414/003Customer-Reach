# 调研 03：搜索、抓取与浏览器自动化工具（含本机实测）

> 调研/实测日期：2026-10-08
>
> 本机环境：Windows 11、Node 24、Python 3.14、uv 0.11。没有 Docker。

## 1. 本机已安装的工具

| 工具 | 版本 | 安装方式 | 状态 |
|---|---|---|---|
| **OpenCLI**（jackwener/OpenCLI，约 29.9k★） | 1.8.8，扩展 1.0.24 | `npm install -g @jackwener/opencli` | ✅ 通过 Edge 扩展连通，实测抓取乙方宝详情页成功（见第 5 节） |
| **Agent Reach**（Panniantong/Agent-Reach，MIT） | 1.5.0 | `uv tool install --index-url https://mirrors.aliyun.com/pypi/simple/ https://github.com/Panniantong/agent-reach/archive/main.zip` | ✅ doctor 显示 4/16 渠道可用 |
| mcporter | 0.14.2 | `npm install -g mcporter`<br>`mcporter config add exa https://mcp.exa.ai/mcp --scope home` | ✅ 可调用 Exa MCP |
| yt-dlp | 最新 | uv tool | ✅（本项目用不到） |
| Playwright（Python） | 1.60 | 已有 | — |

注意：在 Windows 上运行 `agent-reach doctor` 前，要先设置 `PYTHONIOENCODING=utf-8`，否则中文输出会报错。

## 2. Agent Reach

- **定位**：它是安装器、健康检查器和路由器，本身不封装任何能力。Agent 实际调用的是它装好的上游工具：
  - 网页读取：Jina Reader
  - 全网搜索：Exa（通过 mcporter 调用 mcp.exa.ai，免 Key）
  - 其他：yt-dlp、gh、RSS 等
  - 社交平台：通过 OpenCLI 或 cookie 接入
- **没有企查查、1688、招标网渠道**。在本项目里它只负责"通用网页读取和搜索"这一层。
- **网络问题**：`r.jina.ai` 在本机网络下 DNS 被污染，需要用 `curl --doh-url https://1.1.1.1/dns-query` 才能访问。另外 Jina 的服务器在境外，访问 qcc.com 时会返回"海外访问拦截"页。

## 3. Exa

- **托管 MCP**（`https://mcp.exa.ai/mcp`）**免 Key 可用**：
  - 版本 exa-search-server 3.2.1
  - 默认工具：`web_search_exa`、`web_fetch_exa`
  - 免费额度据第三方说法约 3 QPS、150 次/天，未证实
- **API 定价**：每月赠送 10 美元额度

  | 调用 | 价格 |
  |---|---|
  | search（auto） | $7 / 1k 次 |
  | deep | $12 / 1k 次 |
  | contents | $1 / 1k 页 |
  | answer | $5 / 1k 次 |

- **实测**：查询"2026 政府采购 服务器 中标公告"
  - 首条结果来自 ccgp.gov.cn：重庆师范大学算力服务器中标公告 CQS26A03104（2026-08-14，金额 ¥2,419,000），返回内容带采购人、联系人、中标供应商、金额、品牌型号。
  - 其他命中：采招网、十环招标网、中国能源招标投标网。
  - **中文采购信息的召回质量良好。**
- `web_fetch_exa` 能读取 ccgp 和 ggzy 的页面；读取 1688 搜索页时返回 `CRAWL_EMPTY_CONTENT`。

## 4. 搜索、抓取工具对比

| 工具 | 中文站适配 | 动态页 / 登录态支持 | 成本 | License | 本项目定位 |
|---|---|---|---|---|---|
| **Exa** | 好 | 由云端处理 | 见第 3 节 | 商业 | **线索发现**（全网搜公告和企业页） |
| **博查 Bocha** | 原生中文 | — | 需在控制台查询价格 | 商业 | **中文搜索主力**，与 Exa 互补 |
| 秘塔 Metaso | 原生中文 | — | 约 ¥0.03/次 | 商业 | 备选 |
| 百度千帆 AI 搜索 | 中文覆盖最好 | — | 每天免费 100 次 | 商业 | 备选 |
| 阿里云 / 腾讯云联网搜索 | 好 | — | ¥12–80 / 千次 | 商业 | 备选 |
| Tavily | 一般 | — | 每月免费 1000 credit | 商业 | 不优先 |
| SerpApi（百度引擎） | 真实百度结果 | 由服务方处理 | $25 / 1k 次 | 商业 | 不优先 |
| Bing Search API | — | — | **2025-08 已下线** | — | 不用 |
| Jina Reader | 能读 ccgp；qcc 拦截海外访问；DNS 被污染 | 基础 | 有免费额度 | Apache-2.0 | 备选 |
| Firecrawl | 云端出口在境外，会受地域限制 | 云端有隐身代理 | 订阅制 | **AGPL-3.0** | 不自托管 |
| **Crawl4AI** | 从大陆 IP 运行效果好 | Playwright + stealth | 免费 | Apache-2.0 | **ccgp 等政府公告的批量采集** |
| Scrapy | 静态分页站点 | 自带中间件 | 免费 | BSD-3 | 省级站批量采集 |
| **OpenCLI** | 内置 169 个站点适配器，含 **1688、剑鱼 jianyu、电建 powerchina、boss、maimai**；复用用户已登录的浏览器 | 使用真实浏览器和用户会话 | 免费 | Apache-2.0（以仓库为准） | **需要登录或动态渲染的站点**（乙方宝、1688、剑鱼）的抓取通道 |
| DrissionPage | 国内常用，可用于 1688、企查查 | 通过 CDP 控制真实浏览器，没有 webdriver 指纹 | 免费 | BSD-3（需核对具体版本） | OpenCLI 的备选 |
| browser-use / Playwright MCP / Stagehand | 通用 | 真实浏览器 | 免费 + LLM 费用 | MIT / Apache | 未知页面的兜底 |
| MediaCrawler | C 端社交平台 | — | — | **禁止商用** | 不用 |

### OpenCLI 中与本项目相关的内置适配器

| 适配器 | 命令 |
|---|---|
| 1688 | `search`（商品搜索）、`item`（商品详情）、`store`（店铺/供应商公开信息，含联系方式和主营）、`login`、`whoami` |
| jianyu | `login`、`whoami`（还需要自己编写 adapter 补充搜索功能） |
| powerchina | `login`、`whoami` |
| 通用 | `opencli browser <session> open/state/extract/eval/network …`，可以对任意页面做抓取和交互 |

以上命令都需要浏览器处于登录态，并且都带 `[cookie]` 标记。

## 5. 实测：用 OpenCLI + Edge 抓取乙方宝招标详情

### 测试对象

- URL：https://www.yfbzb.com/inviteBid/detail/20261008_636513843.html
- 页面标题：**北京航天广通科技有限公司采购防火墙招标公告**（北京，2026-10-08）

### 未登录状态下取到的字段

- **基本信息**：询价人"秦劲松"，采购类型"单次采购"
- **报价商品明细**：防火墙 1 套，属"机电产品"，附完整的硬件、功能、性能参数
- **信息来源**：航天科工航天电子采购平台 e-casic.com 的询价单接口，链接中的 askSheetId 被打码

### 被会员墙隐藏的字段

询价单名称、询价单编号、询价日期、询价人电话、采购企业。这些字段在会员控制台详情页中展示（见下）。

### 样例文件

- `data/raw/samples/yfbzb_20261008_636513843.json`：结构化后的结果
- `data/raw/samples/yfbzb_20261008_636513843.txt`：页面原文

### 可用的命令

```bash
opencli browser work open "<url>"
opencli browser work wait time 3
opencli browser work extract              # 导出为分块 markdown
opencli browser work eval "document.body.innerText"
```

### 结论

1. 乙方宝、千里马类的聚合站点可以用 OpenCLI 读取公开字段。如果需要完整字段，有两种合规做法：
   - **使用公司自己的会员账号登录后读取**，前提是遵守该账号协议，并且只供内部使用；
   - 按"信息来源"字段回溯到原始采购平台（例子中是 e-casic.com）读取公开页。
2. 聚合站点适合用来**发现线索**。原始采购平台是**权威来源**。系统里对每条线索都要记录 `source_url` 和 `origin_url`。

### 登录后测试结果

测试账号：免费个人会员，可选地区为北京、广东。

- `www.yfbzb.com` 的公开详情页**登录后仍是打码状态**，因为登录态在 `qiye.qianlima.com` 域名下。
- **会员控制台搜索可用**，入口：`https://qiye.qianlima.com/new_qd_yfbsite/#/infoCenter/search`。
  - 关键词搜索结果的**列表摘要里直接能看到**：采购企业（如"北京航天广通科技有限公司"）、询价单编号、询价人、中标结果确认时间，以及电话的前几位。
  - 可以按采购企业列出它的**采购历史**，可直接用于画像：采购品类、采购频次、偏好品牌。
- 控制台详情页的 URL 格式：`#/infoCenter/infoDetail/{contentId}/{areaId}/zhaobiao`。
- **详情页受每日额度限制**：免费额度当天用完后，会提示开通"黄金会员"（¥398/年，每天 30 条，含"查看联系人"）。开通后即可在控制台详情页读取完整字段。

**结论**：拿到完整联系人和手机号需要开通会员，每天最多看 30 条详情。系统设计上：

- **列表摘要批量入库**，不消耗额度；
- **详情按需查看**，会消耗额度，需用户确认（HITL）；
- 记录每次额度消耗。

### 已知限制

- OpenCLI 的 `OPENCLI_CDP_ENDPOINT` 只适用于 Electron App；`browser` 命令**必须连接 Browser Bridge 扩展**。
- Chrome 137 及以上版本的品牌版禁用了 `--load-extension` 参数，所以改用 Edge。

## 6. Edge 安装 OpenCLI 扩展（Browser Bridge）

扩展包已经解压到 `C:\Users\Chilth\.opencli\browser-extension`（版本 1.0.24），可以直接使用。

### 方式 A：在日常使用的 Edge 中手动加载（推荐）

1. 打开 Edge，在地址栏输入 `edge://extensions/`。
2. 打开左侧的 **"开发人员模式"** 开关。
3. 点击 **"加载解压缩的扩展"**，选择文件夹 `C:\Users\Chilth\.opencli\browser-extension`，也就是 `manifest.json` 所在的目录。
4. 确认扩展列表里出现 **OpenCLI 1.0.24** 并且已启用。建议在"扩展"按钮里把它固定到工具栏。
5. 在终端运行 `opencli doctor`，看到 `[OK] Extension: connected` 就说明连通了。
6. 需要登录的站点（1688、剑鱼、乙方宝会员等），先在这个 Edge 里正常登录，OpenCLI 会复用登录态。

### 方式 B：从 Chrome 应用商店安装

Edge 支持 Chrome 商店的扩展。步骤如下：

1. 在 `edge://extensions/` 打开"允许来自其他应用商店的扩展"。
2. 访问 https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
3. 点击"获取"。

### 方式 C：使用独立的 Edge 配置启动（本次实测所用）

适合给 Agent 单独准备一个浏览器，与个人浏览器隔离：

```bash
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" ^
  --user-data-dir="D:\Codes\003Customer-Acq\data\browser-profile\edge-agent" ^
  --load-extension="C:\Users\Chilth\.opencli\browser-extension" ^
  --no-first-run
```

### 升级扩展

1. 到 GitHub Releases 下载新的 `opencli-extension-v*.zip`。
2. 解压覆盖 `C:\Users\Chilth\.opencli\browser-extension`。
3. 在 `edge://extensions/` 点击该扩展的"重新加载"。

### 多配置

如果有多个 Edge 配置都装了扩展，用 `opencli profile list` 查看，用 `opencli profile use <name>` 指定。

## 7. 开源爬虫（GitHub）

- **招投标类**：
  - 都是小项目：ABoeotian/CrawlerForCCGP（30★）、ir-st/TenderCrawler（2026-06）、qianqianjie-999/tenders（2026-08）、kaii9/CCGP-Spider 等。
  - 只参考它们的 URL 参数和解析逻辑。
- **企查查、天眼查类**：
  - bouxin/company-crawler 有 733★，但 2023 年后已停更。
  - 这类站点抓取有法律风险，**改用官方 MCP**：agent.qcc.com，以及天眼查的 tyc-cli。
- **1688 类**：
  - 可参考 zhangjiancong/MarketSpider（437★）。
  - 实际使用**官方开放平台和 OpenCLI `1688` 适配器**。

## 8. 工具层最终建议

| 场景 | 工具 |
|---|---|
| 发现线索 | Exa（MCP/API）+ 博查（中文） |
| 政府采购公告批量入库 | Crawl4AI 或 Scrapy，部署在大陆 IP 上，低频抓取 |
| 需要登录或强动态渲染的站点（乙方宝、剑鱼、1688 店铺、电建等） | **OpenCLI Browser Bridge + 专用 Edge 配置** |
| 工商数据 | 企查查、天眼查**官方 API/MCP**；企查查网页（已登录会员）用 OpenCLI 补充 |
| 内容不完整（占位、打码、需登录） | Fetch Router 升级到 OpenCLI 已登录会话；需要用户操作时在 Agent 浏览器中完成；会员字段使用会员额度读取 |
