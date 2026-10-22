# 本地脚本

后续可放置：目录检查、样本脱敏、原始数据校验、schema 验证和测试数据生成脚本。

外部仓库下载使用 `opensource-crawlers/bootstrap.ps1`，并只允许 allowlist 项目。

`mcp_probe.py` 提供 Exa、Fetch、Playwright 的实际协议调用测试；使用和环境依赖见 `../tools/mcp/README.md`。输出只能写到 `.codex-tmp/`，不是生产获客采集入口。
