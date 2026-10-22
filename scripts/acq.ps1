# acq 信息查询工具（PowerShell）。用法见 docs/02-产品与开发/设计文档/11-acq-query-tool.md
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "$Root\src\tools;$env:PYTHONPATH"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python -X utf8 -m acq_query @args
exit $LASTEXITCODE
