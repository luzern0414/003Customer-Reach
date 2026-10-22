# 仅停止PID文件指向且命令行确认属于本项目的进程，不按名称批量终止。
$projectRoot = $PSScriptRoot
foreach ($serviceName in @('api','worker')) {
    $pidFile = Join-Path $projectRoot ".codex-tmp\runtime\$serviceName.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }
    $savedPid = [int](Get-Content -LiteralPath $pidFile)
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid"
    if ($proc -and $proc.ExecutablePath -eq (Join-Path $projectRoot 'backend\.venv\Scripts\python.exe') -and $proc.CommandLine -like '*app.*') {
        # 只记录核对后的停止意图；stop脚本也可能由部署调用，不能一概标成用户手动操作。
        $stamp = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'China Standard Time').ToString('yyyy-MM-dd HH:mm:ss')
        Add-Content -LiteralPath (Join-Path $projectRoot '.codex-tmp\runtime\lifecycle.jsonl') -Encoding UTF8 -Value (@{time=$stamp;event='stop_requested';service=$serviceName;process_id=$savedPid;caller_id=$PID} | ConvertTo-Json -Compress)
        # Windows venv启动器有一个实际Python子进程；仅停止已核对父进程的直接业务子进程。
        foreach ($child in (Get-CimInstance Win32_Process -Filter "ParentProcessId=$savedPid")) {
            if ($child.CommandLine -like '*app.main:app*' -or $child.CommandLine -like '*app.worker*') {
                Stop-Process -Id $child.ProcessId
            }
        }
        Stop-Process -Id $savedPid -ErrorAction SilentlyContinue
        Write-Host "$serviceName stopped ($savedPid)"
    }
}
