---
name: company-intel
description: 给出一个企业名称，尽可能多地采集该企业的采购/招投标数据、企业工商信息与上下游关系，生成客户画像报告。数据源覆盖乙方宝会员控制台、千里马、中国采购与招标网、剑鱼标讯、必联网、中国政府采购网、全国公共资源交易平台、中国国际招标网（经 Exa）、Exa 全网检索，以及必联网企业库与工商信息页面。当用户说"查一下某某公司""这家企业在采购什么""给出客户画像/上下游/联系人""尽可能多地爬取某企业信息"时使用。
---

# company-intel：企业采购与工商信息全量采集

所有命令都在项目根目录 `D:\Codes\003Customer-Acq` 下执行。在 Git Bash 中用 `scripts/acq`，在 PowerShell 中用 `scripts\acq.ps1`。

## 标准流程

1. **环境检查**：运行 `scripts/acq doctor`。
   - 它会启动 Agent 专用 Edge（自动加载 OpenCLI 扩展），并安装或确认项目插件 `acq`。
   - 同时检查乙方宝登录状态。
2. **需要登录时，让用户来登录**：运行 `scripts/acq login yfbzb`，然后告诉用户："请在弹出的 Edge 窗口中登录乙方宝"。
   - 命令会一直等到用户登录完成。
   - 不要自己填写账号或密码。
   - 如果不登录，会员控制台会被跳过，自动改用乙方宝公开搜索。
3. **全量采集**：
   ```bash
   scripts/acq company "<企业全称>"            # 默认：近 365 天，每个源最多 60 条，全部数据源 + 企业信息
   ```
   - 只查部分数据源：`--sources yfbzb,qianlima,jianyu,ebnew,chinabidding,ccgp,ggzy,cborg,exa`
   - 增加乙方宝类型：`--types zhaobiao,zhongbiao,caigou,nijian,qianqi`
   - 扩大范围：`--days 730 --limit 150`
   - 全国公共资源交易平台如果弹出验证码，命令会等待最多 3 分钟。**提示用户去 Edge 中输入验证码**。
4. **读取结果**：
   - 报告：`data/processed/companies/<企业名>/latest.md`
   - 完整数据：同目录下最新的 `*.json`，包含 `profile`、`notices[]`、`analysis`、`source_status`
   - 原始返回：`data/raw/acq_query/<日期>/`
5. **（可选）补全联系人和上游供应商**：加 `--details N`，读取乙方宝会员详情。
   - 每条会消耗 1 次会员查看额度，**必须先征得用户同意**，同意后再加 `--yes`。

## 向用户汇报的内容

- **企业基本信息**：统一社会信用代码、法定代表人、成立日期、注册资本、企业类型/性质、行业、地区、主营产品、经营范围。
- **采购画像**：作为采购方的公告数、月度频次、主要采购品类、最近的采购公告（附链接）。
- **采购联系人**：姓名和电话，来自公开公告摘要，需注明"使用前请核实"。
- **上下游关系**：
  - 下游客户：本企业中标时的采购方；
  - 上游供应商：本企业采购时的中标方；
  - 竞争对手；
  - 常合作的招标代理。
- **数据源状态**：哪些源成功、为空或失败，以及失败原因（未登录 / 限流 / 超时 / 页面不可用）。

## 单独调用站点命令

每个命令都加 `-f json`。

| 站点 | 命令 | 说明 |
|---|---|---|
| 乙方宝会员 | `opencli yfbzb search "<词>" --type zhaobiao\|zhongbiao\|caigou\|nijian\|qianqi` | 需登录；列表不消耗额度 |
| 乙方宝会员详情 | `opencli yfbzb detail <content_id> --area <area_id>` | 消耗额度 |
| 乙方宝公开 | `opencli yfbzb public "<词>"` | 免登录，招标列表 |
| 千里马 | `opencli qianlima search "<词>" --days 365` | 公开接口，全文检索 |
| 中国采购与招标网 | `opencli chinabidding search "<词>"` | 公开接口；正文需登录 |
| 剑鱼标讯 | `opencli jianyu list "<词>"` | Edge 页面解析；摘要中有联系人和电话 |
| 必联网 | `opencli ebnew search "<词>"`、`opencli ebnew company "<企业名>"` | 公告检索与企业库 |
| 中国政府采购网 | `opencli ccgp search "<词>"` | 全文检索；有频率限制 |
| 全国公共资源交易平台 | `opencli ggzy search "<词>" --days 90` | 标题检索；有验证码时等待用户输入 |
| 中国国际招标网 | 无站内检索（后台不可达） | 由 acq 通过 Exa `site:chinabidding.org.cn` 检索 |

## 故障处理

| 现象 | 处理 |
|---|---|
| 浏览器命令卡住或超时 | 用 `scripts/acq doctor` 重新连接。acq 已默认使用 `OPENCLI_SITE_SESSION=ephemeral`，以避免复用的标签页失效 |
| 退出码 77 / AUTH_REQUIRED | 运行 `scripts/acq login yfbzb` |
| 某个源一直为空 | 单独运行上表中的对应命令，加 `-v` 复现；接口细节见 `docs/11-acq-query-tool.md` §4 |
