# opencli-plugin-acq

AI 获客系统的定制 OpenCLI 插件。插件名为 `acq`，注册以下站点的命令：

| 命令 | 说明 |
|---|---|
| `opencli yfbzb whoami` | 乙方宝/千里马会员控制台登录状态 |
| `opencli yfbzb login [--timeout 600]` | 在 Edge 前台打开登录页，等待用户登录 |
| `opencli yfbzb search <关键词> [--type zhaobiao\|zhongbiao\|caigou\|nijian\|qianqi] [--days 365] [--area ''] [--limit 60]` | 标讯搜索，列表不消耗额度 |
| `opencli yfbzb detail <content_id> [--area 2] [--type zhaobiao] [--public_url URL]` | 会员详情，消耗 1 次额度；额度不足时回退读取公开页 |
| `opencli ccgp search <关键词> [--days 365] [--fulltext true] [--limit 40]` | 中国政府采购网检索 |
| `opencli yfbzb public <关键词>` | 乙方宝公开搜索（免登录） |
| `opencli qianlima search <关键词> [--days 365] [--title_only false]` | 千里马公开接口 |
| `opencli chinabidding search <关键词>` | 中国采购与招标网公开接口 |
| `opencli jianyu list <关键词> [--scope title,content]` | 剑鱼标讯结果页解析（含联系人和电话） |
| `opencli ebnew search <关键词>` / `opencli ebnew company <企业名>` | 必联网公告检索 / 企业库 |
| `opencli ggzy search <关键词> [--days 90]` | 全国公共资源交易平台（验证码时等待用户输入） |

安装方式为本地开发链接，改动即时生效：

```bash
opencli plugin install file:///D:/Codes/003Customer-Acq/src/opencli-plugin
opencli daemon restart   # 新增命令文件后需要执行
```

接口说明、字段和维护方法见 `../../docs/02-产品与开发/设计文档/11-acq-query-tool.md`。
