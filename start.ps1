# 本地启动脚本；仅启动本项目进程，凭据由后端只读加载。
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$runtimeDir = Join-Path $projectRoot '.codex-tmp\runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
. (Join-Path $projectRoot 'scripts\runtime-logs.ps1')
if (-not (Test-Path $pythonPath)) { throw '缺少 backend/.venv，请先按README安装依赖' }
if (-not (Test-Path (Join-Path $projectRoot 'web\dist\index.html'))) { throw '请先在web执行npm run build' }
$workerStartupEpoch = 0
foreach ($serviceName in @('api','worker')) {
    $pidFile = Join-Path $runtimeDir "$serviceName.pid"
    if (Test-Path $pidFile) {
        $savedPid = [int](Get-Content -LiteralPath $pidFile)
        $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid"
        if ($existing -and $existing.CommandLine -like '*app.*' -and $existing.ExecutablePath -eq $pythonPath) { Write-Host "$serviceName already running ($savedPid)"; continue }
    }
    Preserve-ServiceLogs -RuntimeDirectory $runtimeDir -ServiceName $serviceName | Out-Null
    $argsList = if ($serviceName -eq 'api') { @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') } else { @('-m','app.worker') }
    if ($serviceName -eq 'worker') { $workerStartupEpoch = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 }
    $proc = Start-Process -FilePath $pythonPath -ArgumentList $argsList -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "$serviceName.stdout.log") -RedirectStandardError (Join-Path $runtimeDir "$serviceName.stderr.log")
    Set-Content -LiteralPath $pidFile -Value $proc.Id
    # 记录已确认的进程创建，后续能区分重启部署和没有退出记录的意外消失；不记录环境或命令原文。
    $stamp = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'China Standard Time').ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -LiteralPath (Join-Path $runtimeDir 'lifecycle.jsonl') -Encoding UTF8 -Value (@{time=$stamp;event='service_created';service=$serviceName;process_id=$proc.Id;caller_id=$PID} | ConvertTo-Json -Compress)
    Write-Host "$serviceName started ($($proc.Id))"
}
# LangGraph冷启动会加载模型/分词依赖；进程创建不等于Agent已经可领取任务。
$readyDeadline = [DateTime]::UtcNow.AddSeconds(30)
$serviceReady = $false
do {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
        if ($health.status -eq 'ok' -and $health.worker_online -and $health.worker_heartbeat -ge $workerStartupEpoch) { $serviceReady = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $readyDeadline)
if (-not $serviceReady) { throw '服务未在30秒内就绪，请查看 .codex-tmp/runtime 下本项目日志' }
Write-Host 'Client Reach: http://127.0.0.1:8000'
