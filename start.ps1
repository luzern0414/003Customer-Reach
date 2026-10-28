# 启动 DealRadar：单个 API 进程（研究任务在进程内运行），日志写入 data/app/logs。
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$logs = Join-Path $root 'data\app\logs'
$pidFile = Join-Path $logs 'api.pid'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
if (-not (Test-Path $python)) { throw '缺少 backend/.venv，请先按 README 安装依赖' }
if (-not (Test-Path (Join-Path $root 'web\dist\index.html'))) { throw '请先在 web 目录执行 npm run build' }
if (Test-Path $pidFile) {
    $saved = Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue
    if ($saved -and $saved.Path -eq $python) { Write-Host "DealRadar 已在运行（$($saved.Id)）：http://127.0.0.1:8000"; exit 0 }
}
$proc = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
    -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs 'api.out.log') -RedirectStandardError (Join-Path $logs 'api.err.log')
Set-Content -LiteralPath $pidFile -Value $proc.Id
$deadline = [DateTime]::UtcNow.AddSeconds(30)
do {
    try { if ((Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2).ok) { Write-Host 'DealRadar：http://127.0.0.1:8000'; exit 0 } } catch { }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $deadline)
throw '服务未在 30 秒内就绪，请查看 data/app/logs/api.err.log'
