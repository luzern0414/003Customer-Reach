# 调研 02：数据源与合规

> 调研日期：2026-10-08
>
> 标注说明：**【验】**表示官方页面抓取或实测请求得到的结果，**【二】**表示来自第三方或二手资料，**【推】**表示经验推断。
>
> 部分官网用纯 HTTP 请求测试时返回 403、412 或 521；改用 OpenCLI 真实浏览器（Edge）访问后，联通、华能、ggzy 等都能正常读取（见 research/03 §5）。

## 0. 结论速览

1. **企业画像和关系数据的主数据源选企查查开放平台**。
   - 它公开了完整价格和文档：167 个 API，按元/次计价。
   - 另有官方 MCP：agent.qcc.com。
   - **启信宝**作为备选，定价公开，部分接口更便宜。
   - **天眼查**价格不公开，需要商务询价。
2. **"供应商/客户"接口只覆盖上市公司和发债主体**。这类数据"基于招股书、年报汇总"【验】。中小企业的上下游关系需要从以下几类数据推断：
   - 招投标中标关系：招标单位 → 中标单位
   - 股权与对外投资
   - 1688 供货关系
3. **招投标数据有两条路线**：
   - **商业 API**：企查查招投标 1 元/次、启信 0.2 元/次、剑鱼、cebpubservice 信息 API。
   - **官方公告源**：ccgp 搜索可以直接 GET；ggzy 列表页在真实浏览器中可以正常加载和检索（OpenCLI）。
4. **1688 官方开放平台**：
   - 需要企业认证，并且要逐个申请接口权限。
   - 搜索类接口门槛最高。
   - 没有官方 MCP。
   - 可以先用 OpenCLI 内置的 `1688` 适配器（已登录账号）读取商品、店铺和供应商信息。
5. **内容获取**：采用 API/MCP → Exa → OpenCLI 真实浏览器（已登录会员）多通道读取，并做完整性校验（见 `04-data-sources-integration.md`）。联系人和电话属于个人信息，适用《个人信息保护法》。

## A. 企业工商信息

### A1. 各平台对比

| 平台 | 官方 API | 鉴权 | 定价 | MCP | 备注 |
|---|---|---|---|---|---|
| **企查查开放平台** openapi.qcc.com | 167 个 API，分 10 类【验】 | Header 里放 `Token = MD5(key+Timespan+SecretKey)`，取 32 位大写；`Timespan` 是秒级时间戳；Query 参数带 `key=AppKey`【验】 | 公开标价（元/次），部分接口"面议"。单接口可免费试 20 次；招投标套餐 1000 元/1000 次【验】 | **agent.qcc.com**：10 个 Server，203 个工具，注册送 500 积分。MCP 和 CLI 共用同一个 Key【验】 | 敏感接口限企业实名，需审核应用场景【验】 |
| **天眼查** open.tianyancha.com（已 302 跳转到 tianyancha.com/data）【验】 | 有 | Header 里放 `Authorization: <token>`，接口路径 `open.api.tianyancha.com/services/open/...`【二】 | 不公开。网传部分接口 0.15 元/次【二】 | 没有官方 MCP，只有第三方封装【二】 | |
| **启信宝** data.qixin.com/api-list | 18 个分类，约 270 个接口【验/二】 | `MD5(appkey+timestamp+secret_key)`，Header 带 `Auth-Version: 2.0`，需配置 IP 白名单【二/验】 | 公开标价【验】：模糊搜索 0.01、工商照面 0.15、招投标搜索 0.2、客户尽调 3、合作风险排查 5（元/次） | 社区有 qixin-apiservice-mcp【二】 | 有"客商关系"分类（客户/供应商）【验】 |
| **爱企查**（百度） | 没有发现官方开放 API【二】 | — | — | 无 | robots 禁止 `/*ajax`【验】 |
| **国家企业信用信息公示系统** gsxt.gov.cn | 无 API | — | 免费，仅人工查询 | 无 | 纯 HTTP 返回 521（JS 环境检测页）；在真实浏览器中打开，需要用户在页面完成确认后再读取 |
| 阿里云/腾讯云市场、聚合数据 | 多为转售 | AppCode | 各家不同 | 无 | 授权链条不透明，只作兜底【推】 |

### A2. 企查查与获客相关的接口

ApiCode 和价格均为【验】，单位是元/次。接口地址统一为 `https://api.qichacha.com/<Path>`。

| 用途 | 接口（ApiCode）与价格 |
|---|---|
| 搜索/识别 | 企业模糊搜索 886（0.10）；企业工商信息 410（0.20）；企业工商详情 735（2.00） |
| 股东/股权 | 股东信息 731（2.00）；股权穿透四层 642（面议）；实际控制人 643（面议）；企业图谱 962（面议）；企业关联关系 1002（面议） |
| 对外投资 | 对外投资核查 884（1.00）；对外投资穿透十层 663（面议） |
| 上下游 | **供应商 724**（`/Supplier/GetList`，面议）；**客户 723**（面议）；所属集团 880、集团成员 883（面议） |
| 招投标 | **招投标信息 958**（`/TenderCheck/GetList`，1.00）。可查近 2 年数据，最多返回 2000 条。`msgType`：3=招标，4=中标。返回字段含招标单位、中标单位、代理单位、预算/中标金额、联系人和电话 |
| 画像信号 | 招聘 718（0.50）；专利 514（0.30）；商标 231（0.30）；资质证书 255（0.30）；行政许可 892（0.50）；新闻舆情 701（0.50）；融资 950（0.50）；进出口信用 891（0.50）；上市企业 699（0.50）；荣誉 1001（1.00）；上榜榜单 959（1.00）；店铺/销售 1102–1109（面议） |
| 风险 | 经营异常 739（0.50）；失信 740（0.30）；被执行 741（0.30）；严重违法 748（0.50）；行政处罚 865（0.50）；风险扫描 736（6.00） |

**成本估算【推】**

- 一条线索的标准画像约 6–8 元，包含：工商详情、股东、对外投资、招投标、招聘、专利、经营异常。
- 需要按 KeyNo 或统一社会信用代码做 7–30 天缓存。

## B. 1688

| 项目 | 情况 |
|---|---|
| 官方入口 | open.1688.com（前端是 SPA，未能直接抓到文档正文）【验】 |
| 接入流程 | 1. 注册开发者<br>2. 企业实名认证：营业执照、法人、对公账户，审核需 1–3 个工作日<br>3. 创建应用（自用型或第三方）<br>4. 逐个申请 API 权限<br>【二】 |
| 常见接口 | `alibaba.product.search`：关键词搜索<br>`alibaba.product.get`：商品详情<br>`alibaba.product.rank.search`：榜单<br>`alibaba.image.search`：以图搜货，需白名单<br>另有跨境和分销铺货类接口<br>【二】 |
| 限流 | 普通开发者 100 次/分钟，认证开发者 300 次/分钟，部分接口每日上限 5000 次【二，需以官方为准】 |
| 官方 MCP | 未找到。"1688 AI 版 App" 提供 AK，供第三方 Skill（如 1688-shopkeeper）使用【二】 |
| 第三方渠道 | 万邦 OneBound（价格不公开）【二】<br>oxylabs/1688-scraper（547★，2026-06 仍在更新）【验】<br>Apify Actor【二】<br>QuoVadis86/ai-reverse（逆向 MTOP + MCP）【验】 |
| 读取方式 | 官方开放平台 API；或 OpenCLI 内置 `1688` 适配器（search / item / store），在已登录 1688 账号的 Edge 中读取 |

**获客场景下的定位**：1688 的主要用途是**供应商发现**。按品类找到工厂或批发商后，再用工商数据补全画像。如果目标是"找买方"，1688 价值有限。

## C. 招投标与政府采购

### C1. 官方公告源

| 站点 | URL 模式 | 开放接口 | 读取方式 |
|---|---|---|---|
| **中国政府采购网** ccgp.gov.cn | `http://search.ccgp.gov.cn/bxsearch?searchtype=1&page_index=1&bidSort=0&pinMu=0&bidType=1&dbselect=bidx&kw=关键词&timeType=2&start_time=YYYY:MM:DD&end_time=...&displayZone=&zoneId=&pppStatus=0`<br>**实测可用**，返回标题、时间和详情页链接；详情页形如 `/cggg/dfgg/gkzb/202610/t20261008_xxx.htm`【验】<br>`bidType` 是公告类型，`timeType` 是时间范围【推】 | 无 | HTTP GET / Exa fetch / OpenCLI，均可读取 |
| **全国公共资源交易平台** ggzy.gov.cn | 列表页：`/deal/dealList.html?HEADER_DEAL_TYPE=01/02/03/90`（工程/政采/土地/其他）<br>数据接口：`POST /information/pubTradingInfo/getTradList`【验】 | data.ggzy.gov.cn 提供中标查询和主体成交记录，但没有公开 API 文档【验】 | OpenCLI 真实浏览器加载列表页检索；Exa fetch 读取详情页 |
| **中国招标投标公共服务平台** cebpubservice.com | 公告：bulletin.cebpubservice.com<br>交易公开：`/ctpsp_iiss/searchbusinesstypebeforedooraction/getSearch.do`【验】 | **信息 API 服务** `/webapi/index.html`【验】：<br>3000 万+ 公告，700 万+ 中标记录<br>可试用，需签合同<br>商务电话 010-88484118-860/853 | 中等【推】 |
| 军队采购网 plap.mil.cn | 可访问【验】 | 无 | OpenCLI |
| 省级平台 | 浙江 zfcg.czt.zj.gov.cn、广东 gdgpo.czt.gd.gov.cn、四川 ccgp-sichuan.gov.cn、重庆 cqggzy.com、北京 ggzyfw.beijing.gov.cn 均返回 200；上海 ccgp-shanghai 返回 403【验】 | 无 | 各省不同 |

### C2. 商业标讯平台

| 平台 | 数据 API | 说明 |
|---|---|---|
| **剑鱼标讯** jianyu360.cn | **有**：`/front/dataMarket/dataInterface`，需企业资质审核【验】 | 企业库 5400 万+，采购单位库 260 万+；价格未公开，热线 400-108-6670【验】 |
| 千里马/乙方宝 | DaaS，需商务对接【二】 | 两者同体系 |
| 采招网 bidcenter.com.cn | 未找到官方 API【二】 | |
| 中国采购与招标网 chinabidding.cn、必联网 ebnew.com | 未发现公开 API | |
| 企查查/启信招投标接口 | 企查查 1.0 元/次，启信 0.2 元/次【验】 | 中标单位已结构化，**最适合构建"甲方→乙方"关系** |
| Apify CCGP Actor | 5 美元/1000 条【二】 | 托管在境外，涉及数据出境问题 |

## D. 央企与企业采购平台

以下站点均于 2026-10-08 实测可访问（HTTP 200）。多数平台要求注册供应商后才能看全文，公开部分一般只有标题和摘要。

| 集团/平台 | URL |
|---|---|
| 国家电网新一代电子商务平台 | https://ecp.sgcc.com.cn |
| 南方电网供应链统一服务平台 | https://www.bidding.csg.cn |
| 中国石化 易派客 | https://www.epec.com |
| 中国石油招标投标网 | https://www.cnpcbidding.com |
| 中国移动采购与招标网 | https://b2b.10086.cn |
| 中国电信阳光采购网 | https://caigou.chinatelecom.com.cn |
| 中国联通采购与招标网 | https://www.chinaunicombidding.cn（纯 HTTP 返回 412；OpenCLI 浏览器可正常读取） |
| 国铁采购平台 | https://cg.95306.cn |
| 国家能源集团招标 | https://www.chnenergybidding.com.cn |
| 中国电建集采 | https://ec.powerchina.cn |
| 中国能建电子采购 | https://ec.ceec.net.cn |
| 大唐电商 | https://www.cdt-ec.com |
| 华能 ec.chng.com.cn、华电 chdtp.com | 纯 HTTP 返回 412；OpenCLI 浏览器可正常读取华能平台（已实测） |
| 中建 云筑网 | https://www.yzw.cn |
| 中铁 鲁班商务网 | https://www.crecgec.com |
| 中化商务 | https://www.sinochemitc.com |
| 中招联合招标采购网 | https://www.365trade.com.cn |
| 优质采 | https://www.youzhicai.com |
| 政采云 | https://www.zcygov.cn |
| 京东慧采/京东万商 | https://b.jd.com 、https://b2b.jd.com |
| 中海油 buy.cnooc.com.cn | 返回 401，需要登录 |
| 华润守正 szecp.crc.com.cn | 返回 502 |
| 中国铁建 crcc.cn | 返回 403 |

**汇集平台**

- 央企采购数据会汇集到**中资阳光采购交易平台**【二】。
- cebpubservice 依法汇集"依法必须招标项目"的公告【二】。
- 因此**应优先对接 cebpubservice 信息 API，一次覆盖大部分央企的公开招标**【推】。

## E. 其他信号源

| 类别 | 来源 |
|---|---|
| 海关/外贸 | 企查查进出口信用 891（0.5 元/次）【验】；腾道 tendata【二】；topease 海关 MCP【二】。中国海关原始报关明细不公开 |
| 招聘（购买信号） | 企查查 718（0.5 元/次）【验】。不直接抓 Boss 直聘等招聘站 |
| 新闻舆情 | 企查查 701；启信新闻舆情分类【验】 |
| 专利 | 企查查专利 514（0.3 元/次）【验】；CNIPA 只有网页，无公开 API；PatSnap 是商业方案【二】 |

## F. 法律参考

| 法规 | 与本项目相关的要点 |
|---|---|
| 《个人信息保护法》 | 联系人姓名、电话属于个人信息；对已公开的个人信息，可以在合理范围内处理（第 13 条）。系统需要提供删除通道，并记录来源 |
| 《数据安全法》 | 数据分类分级管理 |
| 《网络数据安全管理条例》（2025-01-01 施行） | 网络数据处理的一般要求 |
| 《反不正当竞争法》（2025 修订） | 涉及数据获取和使用的竞争行为规范；原始数据不对外转售 |

## G. GitHub 开源爬虫

以下数据通过 GitHub API 实测得到。

| 仓库 | ★ | 最后 push | 说明 |
|---|---|---|---|
| bouxin/company-crawler | 733 | 2023-02 | 天眼查、企查查爬虫，已不活跃 |
| oxylabs/1688-scraper | 547 | 2026-06 | 代理厂商的示例项目 |
| acpyin/tianyancha | 92 | 2021-01 | |
| OliverFoh/zhaobiao_spider | 33 | 2020 | 多站招投标 |
| ABoeotian/CrawlerForCCGP | 30 | 2025-05 | ccgp 招标公告 |
| QuoVadis86/ai-reverse | 24 | 2026-05 | 1688 MTOP 逆向，**不采用** |
| robertzhangwenjie/qichacha_crawler | 17 | 2024-04 | Scrapy |
| LianQi-Kevin/ccgp_spider | 8 | 2024-03 | ccgp 合同公告 |
| BruceLee1024/ggzy-scraper | 2 | 2026-05 | |
| BruceLee1024/bidding-monitor | 3 | 2026-06 | 陕西 ggzy 监控 Skill |
| tfmcg3/qcc-mcp-server | 0 | 2026-09 | 企查查官方 API 的 MCP 封装 |

**评价**：

- 查询类网站的爬虫普遍已经失效，而且有法律风险，**不采用**。
- ccgp 爬虫可以参考它们的 URL 参数。

## 待商务确认

- 天眼查各接口单价
- 剑鱼、cebpubservice、千里马 API 的价格和限流
- 1688 搜索类权限的当前门槛
- 企查查 API 的 QPS 限制

## Sources

- 企查查：https://openapi.qcc.com/dataApi ，https://openapi.qcc.com/dataApi/958 ，https://openapi.qcc.com/dataApi/724 ，https://agent.qcc.com/
- 启信：https://data.qixin.com/api-list ，https://mcp.so/zh/servers/qixin-apiservice-mcp
- 天眼查：https://www.tianyancha.com/data
- 1688：https://developer.aliyun.com/article/1748878 ，https://developer.aliyun.com/article/1682441
- 招投标：http://search.ccgp.gov.cn/bxsearch ，https://www.ggzy.gov.cn/deal/dealList.html ，http://www.cebpubservice.com/webapi/index.html ，https://www.jianyu360.cn/front/dataMarket/dataInterface
- 法律：https://www.dehenglaw.com/CN/tansuocontent/0008/034390/7.aspx?MID=0902 ，https://junhe.com/legal-updates/2639 ，https://www.allbrightlaw.com/CN/10475/3a742750e4a53fcc.aspx
