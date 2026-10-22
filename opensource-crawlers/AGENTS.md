# opensource-crawlers 模块约定

- `catalog.json` 管候选项目，`manifest.lock.json` 管已下载仓库的 commit。
- 只能通过 `bootstrap.ps1` 的 allowlist 下载，不执行未知仓库脚本。
- 采用仓库前必须阅读 LICENSE，并单独审查目标网站的数据授权。
- 第三方框架许可证只覆盖代码，不覆盖企查查、1688、门店平台等目标数据。
- 本目录不保存 API Key、Cookie、客户导出文件或个人手机号。
