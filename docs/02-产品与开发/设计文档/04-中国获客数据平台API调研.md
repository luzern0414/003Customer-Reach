# 买接口、读原文、不破墙：中国获客数据接入路线

截至 2026 年 10 月，中国 B2B 获客数据里，**真正能自助开通、明码标价、可合规接入的 API 主要在企业工商这一侧**，招投标和电商 B2B 两侧都没有。企查查开放平台公开了 167 个接口的单价，例如模糊搜索 0.10 元/次、照面 0.20 元/次、招投标 958 接口 1.00 元/次，每个接口送 20 次免费试用。它在 2026 年 3 月上线的官方 MCP 平台 agent.qcc.com 有 203 个工具，覆盖工商、风险、标讯，注册即送 500 积分。对一个 LangGraph Agent 来说，这是成本最低、合规性最好的入口。招投标这边，中国政府采购网、全国公共资源交易平台、中国招标投标公共服务平台三个国家级平台**都没有面向社会的免费开放 API**。千里马、采招网、剑鱼、比地等商业标讯平台的 API 都要申请后由销售报价，会员年费（398 元至 21999 元）买到的只是网页查看权。电商 B2B 平台则**没有任何一家向第三方开放全站买家求购池**：1688 询价单接口要求采购商本人授权，阿里国际站开放 API 也是"终端用户授权 + ISV"模式。法律上，2025-10-15 施行的新《反不正当竞争法》第十三条第三款，已经把"避开或者破坏技术管理措施"获取他人数据明确列为违法行为，最高罚 500 万元；司法判例的主线也很清楚：数据公开不能当作抗辩理由，看的是是否突破技术措施、是否违反 robots、是否实质性替代对方产品。开源方面，招投标采集没有成熟项目（专用项目最高约 200 Star），老的工商爬虫基本停在 2023 年以前，而且依赖破解验证码。对本项目的建议：工商和"按企业查中标"改用企查查 MCP/API；招投标原文优先读政府源头；现有商业平台适配器限定在"用户本人账号、人工规模"，并在商业化之前逐站审查 robots 和用户协议。

## 工商数据：企查查明码标价，官方 MCP 是最便宜的入口

在工商平台中，只有企查查的价格能从官网一手核实。接口 886 企业模糊搜索 0.10 元/次，410 企业工商照面 0.20 元/次，套餐 1,000 元/5,000 次。410 返回统一社会信用代码、法定代表人、注册资本、经营范围、经营状态、曾用名等照面字段（[企查查 API 410](https://openapi.qcc.com/dataApi/410)）。**735 企业工商详情 2.00 元/次**，另外返回股东及股比、主要人员、分支机构、变更记录和**联系方式**（[企查查 API 735](https://openapi.qcc.com/dataApi/735)）。其余单价：股东 2.00 元、主要人员 0.50 元、税号开票信息 1.00 元（含电话）、风险扫描 6.00 元；**供应商查询 724 和客户查询 723 均为"面议"**（[企查查接口列表](https://openapi.qcc.com/dataApi)）。这个缺口对本项目影响很大：上下游关系数据在两大平台都属于需要商务谈判的高价值产品。开通门槛同样明确，**限企业实名用户，且需提供应用场景审核**，个人开发者无法开通（[企查查开放平台](https://openapi.qcc.com/)）。聚合数据等云市场商品也写明"个人实名用户无法使用"（[聚合数据 205](https://www.juhe.cn/docs/api/id/205)）。照这个价目，按"模糊搜索 + 照面"组合，单家企业约 0.3 元；需要股东和联系方式时换成 735，约 2 元。

2026 年的变化是工商数据转向 MCP。企查查 2026-03-30 推出智能体数据平台，用标准 MCP 协议接入阿里云百炼、扣子、飞书等，MCP 与 CLI 共用 API Key，不重复计费（[新浪财经](https://finance.sina.cn/2026-04-03/detail-inhtfrex8751482.d.html)）。官网首页列出 10 个核心服务、**203 个工具**，其中 qcc-operation（经营罗盘）包含**标讯/招投标**、资质、税务等 35 个工具；页面写明"注册即领 500 积分，每日还有赠送积分"（[agent.qcc.com](https://agent.qcc.com/)）。端点格式为 `https://agent.qcc.com/mcp/<server>/stream`，用 Bearer Token 鉴权（[zhanglunet/qcc](https://github.com/zhanglunet/qcc)），可以直接挂到本项目已配置的 mcporter 上。积分单价和每个工具消耗多少积分，本次没有抓到，需要注册后确认。

其他工商平台的信息明显少得多。天眼查开放平台现在 302 跳转到 tianyancha.com/data，页面由 JS 渲染，无法核实价格（[天眼查数据页](https://www.tianyancha.com/data)）。检索摘要显示"企业基本信息"约 0.15 元/次（[天眼查 api_list 摘要](https://open.tianyancha.com/api_list)），转售页标包年 1,500 元/1 万次（[幂简集成](https://www.explinks.com/api/scd20240730497120ba8e52)），两者都属二手信息。启信宝有官方 MCP 包 `@qixin-api/apiservice-mcp`，用 AppKey/SecretKey 鉴权（[mcp.so](https://mcp.so/zh/servers/qixin-apiservice-mcp?tab=config)），价格未公开。**爱企查、水滴信用、企查猫是否提供面向公众的开放 API，没有找到可靠来源。**网上流传的"天眼查免费每日 500 次""企查查 0.02 元/次"等说法，与官方单价矛盾，来源也有利益关联，本报告不采信。

真正免费的权威源是国家企业信用信息公示系统（gsxt）。它日均访问 1.3 亿次，定位为官方、免费的查询平台（[人民日报 2023-12](https://paper.people.com.cn/rmrbwap/html/2023-12/13/nw.D110000renmrb_20231213_1-17.htm)），但**没有面向社会的 API**，还有滑动或点选验证码（[i-search 博客](https://support.i-search.com.cn/article/1553085251057)）。按本项目规则，只能由用户人工处理验证码，所以 gsxt 适合做人工核验，不适合批量接入。地方公共数据开放平台也是一条补充渠道，上海平台提供数据接口和安全沙箱（[上海平台操作指南](https://data.sh.gov.cn/assets/data/%E4%B8%8A%E6%B5%B7%E5%B8%82%E5%85%AC%E5%85%B1%E6%95%B0%E6%8D%AE%E5%BC%80%E6%94%BE%E5%B9%B3%E5%8F%B0%E6%93%8D%E4%BD%9C%E6%8C%87%E5%8D%9720250527V3.0.0.pdf)），但是否开放企业登记数据集未能核实。

## 招投标：国家级平台没有开放 API，商业标讯 API 全靠询价

政府侧的结论很直接：三个国家级平台都不提供面向获客方的数据订阅。中国招标投标公共服务平台的"直连对接"是基于 OAuth 的 RESTful API，交换项目、公告、开标记录、中标、合同和市场主体数据，但流程要求注册、选择对接等级、签署对接协议（[cebpubservice 直连对接](http://www.cebpubservice.cn/system/joint/index.shtml)）。它的法定定位是交易平台按《电子招标投标办法》上报数据的通道（[cebpubservice 系统对接](http://cebpubservice.cn/system/index.shtml)），获客企业基本拿不到。全国公共资源交易平台的"数据服务"只能在网页上按主体名称或信用代码查询，汇集了 160 多万个成交项目（[国家发改委 2020-09](https://www.ndrc.gov.cn/fzggw/jgsj/fgs/sjdt/202009/t20200903_1237618.html)）。本仓库实测发现，它的列表接口返回 code=829 时弹出验证码，短时间请求过多会被临时拦截（本地 `docs/02-产品与开发/设计文档/11-acq-query-tool.md` §4）。ccgp.gov.cn 和 ggzy.gov.cn 的 robots.txt 都返回 404。政府采购公告依财政部第 101 号令属于"应公开信息"（[中国政府网](https://www.gov.cn/zhengce/2019-11/27/content_5717201.htm)），所以低频读取原文是整个领域里风险最低的做法。目前唯一确认免费且机器可读的是地方开放数据，例如达州"政府采购中标信息"无条件开放 6,795 条，支持 CSV/JSON/API（[达州开放平台](https://www.dazhoudata.cn/oportal/catalog/ea1bb6c8276047cba1d677dbf986360f)），北京平台也有中标公告类数据（[北京开放平台](https://data.beijing.gov.cn/)）。这些数据零散，覆盖不全国。

商业标讯平台的通行做法是"会员年费买查看权，API 另签 DaaS 合同"。千里马官网标价普通 7,999、高级 12,999、VIP 21,999 元/年，另有"标准 API 服务"但没有标价；免费用户只能看 7 天前的公告，而且看不到联系人（[千里马会员服务](https://www.qianlima.com/common/huiyuan.jsp)）。剑鱼会员从超级订阅 680 元/年到专家版 19,999 元/年，没有任何档位含 API。剑鱼的**数据定制导出按条计费，预充值最低 0.075 元/条**，50 多个字段（含标的物、中标企业、联系人），可通过 API 交付，需先审核样例（[剑鱼数据定制导出](https://www.jianyu360.cn/front/dataMarket/customExport)）。这是批量结构化数据里少数公开报价的选项。采招网 VIP 只享受"API 8 折"，说明 API 是单独计费的产品（[采招网开通页](https://www.bidcenter.com.cn/zaixiankaitong/index.aspx)）。比地的数据接口页摘要显示列表约 0.05 元/次、详情约 0.25 元/次，但页面抓取为空，未能核实（[比地数据接口](https://www.bidizhaobiao.com/sjjk/0)）。按企业名查中标，标价最透明的是**企查查 958**：1 元/次，20 次免费试用，返回采购人、中标人、金额、代理机构及其联系人，限近 2 年、单次最多 2,000 条（[企查查 958](https://openapi.qcc.com/dataApi/958)）。长尾报价有迪信宝 0.15 元/次（[迪信宝](https://open.indeeda.com/apidetail?apiid=1029)）和百度 API 商城约 0.13–0.15 元/次（[百度 API 商城](https://apis.baidu.com/store/detail/4bec8a20-d6e8-4419-9490-727bcca7f75e)），供应商资质和数据来源不明。**建设通（cbi360）、必联网、中国采购与招标网、水滴标讯的会员价和 API 都没有查到可靠信息**。必联网收费应用需要企业验证后才显示价格（[必联网帮助中心](https://asynclogin.ebnew.com/ebnew-web/help/supplier/show.htm?id=428368299&typeid=428353300)）。

robots.txt 对本项目现有适配器有直接约束。**千里马 robots 对所有 UA 禁止 yfb 子域、搜索与关键词页，以及带 `id`/`contentid` 参数的详情和导出页**（[qianlima.com/robots.txt](https://www.qianlima.com/robots.txt)）。剑鱼只禁止支付、拟建详情、地区标签和移动端路径（[jianyu360.cn/robots.txt](https://www.jianyu360.cn/robots.txt)）。乙方宝和千里马都属于这个 robots 范围，所以本项目的乙方宝、千里马适配器只能定位为"用户本人会员账号、人工规模的辅助查看"，不能扩展成批量采集。千里马系企业主页（anfangzhaobiao 等）、建设通、水滴标讯、采招网、必联网的 robots 和用户协议本次没有抓取，是待补的合规缺口。

## 电商 B2B：买家求购数据对第三方完全封闭

如果"获客"指拿到买家的求购需求，主流电商平台的 API 都走不通。1688 开放平台"大企业采购"类目确实有询价单接口 `caigou.api.buyOffer.getBuyOfferById`，也有"采购商发布询价"消息，但都要求 `access_token` 用户授权（[1688 开放平台](https://open.1688.com/api/apidocdetail.htm?aopApiCategory=purchase_integrate&id=cn.alibaba.open%3Acaigou.api.buyOffer.getBuyOfferById-1)；[1688 消息订阅](https://open.1688.com/message/topicDetail.htm?id=CAIGOU_MSG_BUYER_PUBLISH_BUYOFFER&topicGroup=CAIGOU)）。它的用途是把采购商自己 ERP 里的采购申请同步到 1688 寻源，供应商一方无法用它读取别人的询价单。这个询价市场本身规模可观，官方称累计询价单 50 万+、每日商机 8,000+，供应商每次报价收费 10–15 元（[1688 大企业采购](https://page.1688.com/html/go/home.html)；[报价宝](https://page.1688.com/tgc/171cd4c6.html)），但只能在供应商自己的账号里浏览和报价。**1688 robots 对通用爬虫禁止 `/offer/`、`/member/` 等目录和所有带参数的 URL**，只对搜索引擎开放 `/xunjia/`、`/baojia/` 等询价 SEO 页（[1688 robots.txt](https://www.1688.com/robots.txt)），所以这些页面只适合通过 Exa 检索命中，作为弱信号使用。阿里国际站的 RFQ 市场对供应商公开浏览，但官方 Open API 要求 ISV 经终端用户授权，本次没有找到 RFQ 拉取接口（[Alibaba.com Open API](https://developer.alibaba.com/docs/doc.htm?treeId=684&articleId=118416&docType=1)）。Apify 上的第三方 RFQ 抓取器未经阿里授权（[Apify](https://apify.com/xtracto/alibaba-rfq-scraper)）。

供应商画像这一侧（"谁在卖什么"）可以走 API。第三方资料称 1688 基础 API 免费、QPS 约 10–20，资源包约 980–1,980 元/年，个人可读商品基础信息，高级能力需要企业实名和"ERP/采购"类应用标签（[阿里云开发者社区](https://developer.aliyun.com/article/1740045)；[阿里云开发者社区](https://developer.aliyun.com/article/1751134)）。这些都是非官方数字。京东 VOP（慧采）是给已签约企业采购客户用的下单接口（[packagist jd_biz](https://packagist.org/packages/xiaoyukarl/jd_biz)）。淘宝、拼多多、抖店的开放平台都以商家授权为核心，敏感数据必须在平台云内处理，不提供跨商家的买家名录。**百度爱采购、慧聪、中国制造网都没有找到公开 API**，爱采购的 robots.txt 返回 404（[b2b.baidu.com/robots.txt](https://b2b.baidu.com/robots.txt)）。万邦等聚合商采用余额扣费（[onebound](https://clawhub.ai/jeff2011eng/onebound-api)），数据来源未经平台授权，不建议在商业 SaaS 中使用。

## 法律边界：新反法把"避开技术措施"写进条文

2025 年起，规制分成三层。民事和行政层面，新《反不正当竞争法》第十三条第三款禁止"以欺诈、胁迫、避开或者破坏技术管理措施等不正当方式"获取、使用他人合法持有的数据，情节严重的**处 100 万至 500 万元罚款**，2025-10-15 施行（[新华网](https://www.news.cn/legal/20250627/4b6ec78bc9be4ea9a2968a9d34abd724/c.html)）。监管层面，《网络数据安全管理条例》第十八条要求自动化采集"评估对网络服务带来的影响，不得非法侵入他人网络，不得干扰网络服务正常运行"，无论数据是否公开都适用，2025-01-01 施行（[网信办](https://www.cac.gov.cn/2024-09/30/c_1729384452307680.htm)）。刑事层面是刑法第 285 条：伪造 UA、IP 绕过频控已被认定为"其他技术手段"（[锦天城](https://www.allbrightlaw.com/CN/10475/3a742750e4a53fcc.aspx)），超越授权使用正常账号也可构成"侵入"。个人信息方面，PIPL 允许在"合理范围内"处理已公开的个人信息，但最高法入库案例明确，深度画像、截流营销属于超出合理范围（[最高人民法院 2025-07](https://www.court.gov.cn/zixun/xiangqing/471171.html)）。2026-05-01 起，未经明示同意不得发送商业短信（[IT之家](https://www.ithome.com/0/945/850.htm)）。

判例显示，"数据是公开的"在聚合平台案件中基本不能作为抗辩。最接近本项目的几个案件如下：

| 案件 | 关键行为 | 结果 | 对本项目的含义 |
|---|---|---|---|
| 北大法宝诉同业案（[北京日报](https://xinwen.bjd.com.cn/content/s68103115d5de115726cd485a.html)） | 抓取公开法规数据库 | 判赔 30 万元 | 原文公开，但平台整理后的数据集合受保护，可类比千里马、剑鱼对公告的聚合 |
| 最高法第 262 号指导案例（[最高人民法院](https://www.court.gov.cn/shenpan/xiangqing/474451.html)） | 搬运 5 万条短视频并向公众提供 | 判赔 500 万元 | "实质性替代"即构成不正当竞争 |
| 淘宝诉慢某案，宁波中院 2025（[网易转载](https://www.163.com/dy/article/K19CO3J0051200BP.html)） | 违反 robots，破解 IP 限制和滑块 | 判赔 500 万元 | 确立公开、附条件公开、不公开三层数据保护 |
| 镇江"搬家软件"案 2025（[扬子晚报](https://www.yzwb.net/news/jiangsu/202509/t20250915_264429.html)） | 绕过验证采集 1.63 亿条商品数据 | 判赔 500 万元 | 平台商业数据"不是公共资源" |
| 微信公众号爬取案 2024（[知产财经](https://www.ipeconomy.cn/dongtai/8705.html)） | 无视 robots 禁止 | 判赔 300 万元 | robots 是认定主观恶意的证据 |
| 淘宝诉美景案（[中新网](https://www.chinanews.com.cn/m/sh/2019/01-22/8735576.shtml)） | 组织共享会员账号获取数据产品 | 判赔 200 万元 | 共享或批量会员账号属于高风险 |
| 晟品爬取今日头条案（[锦天城](https://www.allbrightlaw.com/CN/10475/3a742750e4a53fcc.aspx)） | 伪造 device_id、UA、IP | 单位及责任人定罪 | 绕频控即入刑 |
| 丁某"精准获客工具"案（[最高人民法院](https://www.court.gov.cn/zixun/xiangqing/459621.html)） | 销售突破反爬的获客爬虫 | 有期徒刑一年六个月、缓刑两年 | 对外提供绕过型采集工具涉刑 |
| 南山法院 2019 案（[知乎转载](https://zhuanlan.zhihu.com/p/472608207)） | 爬取政府网站致其瘫痪 | 破坏计算机信息系统罪 | 对政府站点必须限速 |

有两个空白需要说明：**没有找到任何"爬取招投标网站"被判刑的公开判决，也没有找到千里马、剑鱼等标讯平台起诉爬虫方的判决**。这不等于安全，只说明这个细分领域还没有先例，判断只能参照上述跨行业判例。由此推出的合规分级如下。低风险：低频读取无访问控制的政府公告原文、购买官方 API、通过 Exa 等检索服务"索引加链接回源"、用户本人在会员协议范围内人工查看。有风险：抓取商业聚合平台的列表和详情（哪怕不用登录）、用自动化工具驱动会员账号批量查询、把公告中的自然人手机号入库做联系人画像。禁止：破解验证码或滑块、伪造身份绕过频控、批量注册或共享账号、反遮蔽 `****` 字段、未经同意群发短信。本项目"不绕过验证码和登录、不反遮蔽"的原则正好落在低风险区。但千里马系企业主页上的"合作单位、竞争对手、工商"栏目本身是平台的二次加工成果，一旦把它们包装成对外销售的同类检索产品，就会进入"实质性替代"的风险区。

## 开源生态：招投标没有成熟项目，工商方向转向官方 MCP 的薄封装

以下 Star 数、推送日期和许可证均取自 2026-10-10 的 GitHub API。"许可证 none"表示 GitHub 没有识别到 LICENSE 文件，默认保留全部权利，不能直接复制代码。Gitee 的搜索 API 未认证时返回空，Gitee 覆盖不全。

| 方向 | 仓库 | Star | 最近推送 | 许可证 | 可用性判断 |
|---|---|---|---|---|---|
| 招投标 | [zhiqianzheng/BidMonitor-AI](https://github.com/zhiqianzheng/BidMonitor-AI) | 204 | 2025-12-19 | none（侧栏称 MIT，冲突） | Selenium 采集 40+ 站并做 AI 分析；只有 1 个 commit |
| 招投标 | [gugug168/bid-collect-skill](https://github.com/gugug168/bid-collect-skill) | 0 | 2026-08-24 | MIT | 覆盖 32 省公共资源交易平台，靠逆向前端 JS；182 个 commit，但无社区验证 |
| 招投标 | [baizhan007/bid-crawler-delivery-skill](https://github.com/baizhan007/bid-crawler-delivery-skill) | 8 | 2026-07-17 | MIT | capture→replay→validate→diff 方法论，明确不绕过登录和验证码，**最值得借鉴** |
| 招投标 | [BruceLee1024/ggzy-scraper](https://github.com/BruceLee1024/ggzy-scraper) | 2 | 2026-05-26 | none（README 称 MIT） | 用 Playwright 过 ggzy 的 WAF；可作接口线索 |
| 招投标 | [qianqianjie-999/tenders](https://github.com/qianqianjie-999/tenders) | 8 | 2026-08-24 | none（README 称 MIT） | Scrapy 抓山东、江苏地方站 |
| 招投标 | [ABoeotian/CrawlerForCCGP](https://github.com/ABoeotian/CrawlerForCCGP) | 30 | 2025-05-12 | none | ccgp 招标公告，未细查 |
| 招投标 | [guangshu100/BidMaster-Pro](https://github.com/guangshu100/BidMaster-Pro) | 368 | 2026-09-03 | AGPL-3.0 | 偏标书生成，不是采集器 |
| 招投标 | [keeker765/qianlimaCrawler](https://github.com/keeker765/qianlimaCrawler) | 0 | 2025-11-02 | none | 含验证码 JS 逆向，**法律风险高，不可用** |
| 工商 | [bouxin/company-crawler](https://github.com/bouxin/company-crawler) | 734 | 2023-02-16 | MIT | 天眼查、企查查爬虫，已归档，失效 |
| 工商 | [RunningGump/gsxt_captcha](https://github.com/RunningGump/gsxt_captcha) | 184 | 2019-11-01 | NOASSERTION | 破解 gsxt 点选验证码，违反本项目原则 |
| 工商 | [iamsk/tianyancha](https://github.com/iamsk/tianyancha) | 15 | 2024-09-23 | MIT | 天眼查开放平台的社区 Python SDK |
| 工商 MCP | [zhanglunet/qcc](https://github.com/zhanglunet/qcc) | 2 | 2026-06-10 | Apache-2.0 | 企查查 MCP 的第三方封装，146 个工具，含 8 个尽调 skill |
| 工商 MCP | [Ace-Kelly/qcc-mcp-batch](https://github.com/Ace-Kelly/qcc-mcp-batch) | 4 | 2026-04-27 | MIT | 调企查查 MCP 批量取 67 项字段，支持断点续跑 |
| 工商 MCP | [DevnorsAI/devnors-data-mcp](https://github.com/DevnorsAI/devnors-data-mcp) | 482 | 2026-09-15 | MIT | 付费工商 API 的 MCP，不含招投标，上游数据源未披露 |
| 工商 | [HG-ha/ICP_Query](https://github.com/HG-ha/ICP_Query) | 1081 | 2026-08-29 | none | 查 ICP 备案主体，可补充"企业到网站"的映射 |
| 1688 | [zhangjiancong/MarketSpider](https://github.com/zhangjiancong/MarketSpider) | 438 | 2025-05-26 | MIT | 淘宝、京东、1688 关键词商品爬虫 |
| 1688 | [QuoVadis86/ai-reverse](https://github.com/QuoVadis86/ai-reverse) | 24 | 2026-05-15 | none | 逆向 MTOP 签名，需要粘贴 cookie，前端一改版就失效 |
| 1688 SDK | [sellerartifact/1688-open-sdk-v2](https://github.com/sellerartifact/1688-open-sdk-v2) | 1 | 2025-08-09 | MIT | 1688 开放平台的社区 TS SDK |
| 慧聪 | [pysunday-plugins/tools-huicong](https://github.com/pysunday-plugins/tools-huicong) | 0 | 2025-04-25 | none | 慧聪方向唯一近两年有推送的仓库 |
| 框架 | [jackwener/OpenCLI](https://github.com/jackwener/OpenCLI) | 30002 | 2026-10-10 | Apache-2.0 | 本项目现用框架 |
| 框架 | [scrapy/scrapy](https://github.com/scrapy/scrapy) / [apify/crawlee](https://github.com/apify/crawlee) / [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | 64703 / 26096 / 85124 | 2026-10 | BSD-3 / Apache-2.0 / Apache-2.0 | 可商用 |
| 框架 | [g1879/DrissionPage](https://github.com/g1879/DrissionPage) / [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) | 12503 / 190033 | 2026-09 / 10 | 商用须授权 / AGPL-3.0 | 不宜直接商用（firecrawl 可只调用云端 API） |

整体情况是：GitHub 搜 "cebpubservice" 结果为 0，剑鱼、千里马各只命中 1 个仓库（[GitHub Search](https://api.github.com/search/repositories?q=cebpubservice)），百度爱采购没有专用仓库，HuggingFace 上也没有中国招投标数据集。所以**本项目现有的 OpenCLI 适配器在覆盖面和工程化程度上大概率已经超过公开的开源实现**。开源方面能借的是方法和接口线索，而不是代码。企查查、天眼查、1688 都没有在 GitHub 上发布官方 SDK，npm 的 `1688-open-sdk` 自己也写明"官方没有提供 node 版本 sdk"（[jsDelivr README](https://cdn.jsdelivr.net/npm/1688-open-sdk@0.1.3/README.md)）。需要注意，以上所有"可用性"判断都基于 README 和推送日期，没有逐个实际运行。

## 按平台的对比表与接入优先级

下表的推荐度以本项目为参照：按企业名生成采购信息、客户画像和上下游关系，并坚持不破墙原则。★ 越多越优先。

| 类别 | 平台 | 接入方式 | 成本 | 免费额度 | 主要数据字段 | 合规风险 | 推荐度 |
|---|---|---|---|---|---|---|---|
| 工商 | 企查查 | 官方 HTTP API + 官方 MCP（agent.qcc.com） | 0.1–6 元/次；供应商和客户关系面议 | 每接口 20 次；MCP 注册送 500 积分，另有每日积分 | 照面、股东、人员、变更、联系方式、招投标、风险 | 低（需企业实名和场景审核） | ★★★★★ |
| 工商 | 天眼查 | 官方 HTTP API（预充值或包年） | 约 0.15 元/次（未核实） | 未知 | 基本信息、司法、招投标 | 低 | ★★★ |
| 工商 | 启信宝 | 官方 API + MCP | 未公开 | 未知 | 工商、股权、司法 | 低 | ★★★ |
| 工商 | 爱企查、水滴、企查猫 | 未发现开放 API；网页摘要可经 Exa 获取 | — | — | 打码的照面信息 | 爬取有风险，Exa 摘要低风险 | ★★（仅作检索兜底） |
| 工商 | gsxt | 只有网页和 App，有验证码 | 免费 | 不限（人工查询） | 权威登记、年报、异常 | 人工查询低风险，破解验证码高风险 | ★★（人工核验） |
| 工商 | 地方开放平台 | 数据集 API 或下载 | 免费 | 无条件开放 | 视数据集而定（覆盖未核实） | 低 | ★★ |
| 招投标 | 企查查 958 | 官方 API | 1 元/次 | 20 次 | 采购人、中标人、金额、联系人（近 2 年） | 低 | ★★★★★ |
| 招投标 | ccgp / ggzy | 读网页原文（无 robots），ggzy 有验证码 | 免费 | 不限，但要限速 | 公告全文、预算、中标结果 | 低频读取低风险；高并发有风险 | ★★★★ |
| 招投标 | cebpubservice | 直连 API 只面向交易平台 | 需签协议 | — | 全流程交易数据 | 获客方无资格 | ★ |
| 招投标 | 千里马 / 乙方宝 | 会员网页；API 需询价 | 会员 7,999–21,999 元/年；乙方宝 398 元/年 | 只能看 7 天前公告，无联系人 | 公告、中标、联系人（会员） | robots 禁止 yfb 子域和详情页，批量抓取风险高 | ★★★（只限用户本人账号人工查看；商业化走 API） |
| 招投标 | 剑鱼 | 会员网页；数据市场按条导出或 API | 680–19,999 元/年；导出 ≥0.075 元/条 | 未知 | 50 多个字段，含标的物、品牌、联系人 | robots 较宽松，会员墙内容不应自动化读取 | ★★★★（批量数据首选的付费渠道） |
| 招投标 | 采招网 | API 需申请和报价 | 未公开（VIP 打 8 折） | 未提及 | 字段可自选，近十年数据 | 未审查 robots | ★★★ |
| 招投标 | 比地 | 按次 API | 列表约 0.05 元、详情约 0.25 元（未核实） | 未知 | 公告列表和详情 | 低（API） | ★★★（值得询价验证） |
| 招投标 | 建设通、必联网、中国采购与招标网、水滴标讯 | 网页（本项目已适配）；API 未发现 | 未公开 | 未知 | 公告、企业库 | robots 和协议未审查，待补 | ★★★（维持现状，补合规审查） |
| 招投标 | 迪信宝、百度 API 商城、知了标讯 | 第三方 API | 0.1–0.5 元/次 | 未知 | 公告基本字段 | 数据来源不明，有转授权风险 | ★★ |
| 电商 | 1688 | 开放平台（自用型商品/搜索 API）；询价单接口需采购商授权 | 基础接口免费；资源包约 980–1,980 元/年（第三方数据） | 基础 QPS 10–20 | 店铺、商品（供应商画像） | API 低；MTOP 逆向或爬取高 | ★★★（只做供应商画像） |
| 电商 | 阿里国际站 | ISV + 终端用户授权 | 未知 | — | 本账号数据；RFQ 无 API | 爬取 RFQ 违反条款 | ★ |
| 电商 | 京东 VOP、淘宝、拼多多、抖店 | 商家或采购客户授权 | 不等 | JOS 每日数万次（第三方数据） | 授权方自己的订单和商品 | 低，但与获客无关 | ★ |
| 电商 | 慧聪、中国制造网、百度爱采购 | 未发现 API | — | — | 求购和商品页 | 未审查 | ★（只用 Exa 检索命中） |

据此给出四档优先级。

**P0（立即做）：接入企查查。**用公司主体完成企业实名，先用 agent.qcc.com 的 500 积分和 openapi 每接口 20 次试用做概念验证，重点验证三件事：886 + 410 能否把"企业名"规范为统一社会信用代码；958 和 qcc-operation 的标讯工具能否补齐"按企业查中标"；735 的联系方式是否合法可用。这一步可以用合规的付费数据，替代当前通过 Exa 抓爱企查、企查查摘要页的做法，单家企业成本控制在 0.3–3 元。同时，在 `docs/02-产品与开发/设计文档/11-acq-query-tool.md` 里补上每个适配器的 robots 和用户协议审查记录，千里马、乙方宝、anfangzhaobiao 系主页、建设通、水滴标讯优先。乙方宝 `--details` 已经做到"先征得用户同意"，这个设计应保留。

**P1（下一迭代）：加厚政府源头。**提高 ccgp、ggzy 原文的权重，按《网络数据安全管理条例》第十八条的要求做单线程限速、使用可识别的 UA、记录来源 URL，验证码继续交给用户处理。挑选几个北京、达州之类的地方开放数据集做增量补充。适配器维护借鉴 bid-crawler-delivery-skill 的 replay/diff 回归方法，接口一变就能检测到。

**P2（商业化前）：询价并签订数据合同。**向剑鱼数据市场（按条 0.075 元起）、比地、采招网、千里马询价批量 API，用合同替代对商业标讯平台的自动化读取，询价时重点确认能否在自有 SaaS 中向第三方展示。上下游关系向企查查 723/724 询价，在拿到报价之前，继续用"中标方即供应商、招标方即客户"的方式从招投标记录推导。天眼查、启信宝作为企查查的备选做价格对比。1688 申请自用型应用，只用于"谁在卖什么"的供应商画像。

**P3（不做）：**破解 gsxt 或千里马验证码、逆向 1688 MTOP 签名、抓取阿里国际站 RFQ、使用万邦等来源不明的聚合商、复用无许可证或采用 GPL/AGPL 的小仓库代码、把公告联系人手机号做成联系人画像或用于群发短信。

## 结论

本次调研最重要的变化是：2026 年获客数据的合规成本曲线已经反转。过去爬取是免费的、API 是贵的。现在企查查把工商加标讯打包成 MCP，注册就送积分，而新反法第十三条第三款和 500 万元级的判赔，让"破墙爬取"的预期成本远高于每家企业几毛到几元的接口费。对一个 Agent 产品来说，数据层最可防御的形态，是"官方 API/MCP 做骨架，加政府原文做证据，再加用户本人账号做补充"，而不是靠适配器数量取胜。

本项目目前最大的未知风险，不在于技术违规（不破墙原则已经避开了刑事红线），而在于**商业定位**：如果对外销售的产品把千里马、剑鱼、千里马系企业主页上的聚合结果原样重组成同类检索服务，就会触碰 262 号案和北大法宝案确立的"实质性替代"标准，而且这个标准对是否登录、是否公开都不敏感。因此，商业化前真正要做的决定，是哪些数据源转为合同授权，哪些只做"索引加链接回源"。这个决定应先于继续扩展站点适配器。
