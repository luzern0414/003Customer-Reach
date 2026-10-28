# 停止 DealRadar API 进程；运行中的研究任务会在下次启动后显示为“已暂停”，可继续。
$root = $PSScriptRoot
$pidFile = Join-Path $root 'data\app\logs\api.pid'
if (-not (Test-Path $pidFile)) { Write-Host 'DealRadar 未在运行'; exit 0 }
$proc = Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue
if ($proc -and $proc.Path -eq (Join-Path $root 'backend\.venv\Scripts\python.exe')) { Stop-Process -Id $proc.Id -Force; Write-Host "已停止（$($proc.Id)）" }
Remove-Item -LiteralPath $pidFile -Force
