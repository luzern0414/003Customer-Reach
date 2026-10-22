# Open Source Crawlers

该目录只管理第三方采集/清洗工具，不把第三方代码直接视为业务代码。

## 内容

- `catalog.json`：候选项目、用途、仓库地址和适配建议
- `manifest.lock.json`：已下载仓库的分支、commit 和许可证文件
- `bootstrap.ps1`：只从 allowlist 克隆指定仓库；目标目录已存在时跳过，不覆盖本地文件
- `repos/`：实际下载的第三方仓库，默认不纳入项目版本库
- `manifests/`：仓库清单和复现说明
- `adapters/`：本项目对第三方工具的接入说明和边界
- `licenses/`：正式采用某个仓库后，把其 LICENSE 和版本信息登记在这里

## 推荐落地顺序

第一期：Scrapy + Playwright（按需）+ Trafilatura + RapidFuzz。

第二期：加入 python-phonenumbers、HanLP/PaddleNLP、PaddleOCR 和 Splink/dedupe。

规模增大后再考虑 Crawlab、Airflow、DolphinScheduler 或消息队列。

第三方框架不授予目标站点数据的使用权。企查查、1688 和门店平台必须先完成 API/合同/站点条款审核。
