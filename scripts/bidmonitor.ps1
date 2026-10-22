# 独立公开采购情报入口：.\scripts\bidmonitor.ps1 "软件" --keyword "人工智能"
# 仅透传参数给 acq bidmonitor；不操作生产服务。
& "$PSScriptRoot\acq.ps1" bidmonitor @args
exit $LASTEXITCODE
