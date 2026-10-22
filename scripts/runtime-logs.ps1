function Preserve-ServiceLogs {
    <#
    .SYNOPSIS
    保留上一次服务日志，避免Start-Process重定向覆盖退出证据。
    .PARAMETER RuntimeDirectory
    本项目runtime目录；必须存在，空值报错。不遍历目录，仅移动两个固定日志。
    .PARAMETER ServiceName
    api或worker；其他值报错。调用方必须已确认该服务没有运行。
    .OUTPUTS
    已归档文件路径；无旧日志返回空，不读取日志内容，移动失败抛异常阻止覆盖。
    #>
    param(
        [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$RuntimeDirectory,
        [Parameter(Mandatory=$true)][ValidateSet('api','worker')][string]$ServiceName
    )
    $resolvedRuntime = (Resolve-Path -LiteralPath $RuntimeDirectory -ErrorAction Stop).Path
    $archiveDirectory = Join-Path $resolvedRuntime 'archive'
    $archiveStamp = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'China Standard Time').ToString('yyyyMMddHHmmssfff')
    $archiveToken = [Guid]::NewGuid().ToString('N')
    foreach ($streamName in @('stdout','stderr')) {
        $oldLog = Join-Path $resolvedRuntime "$ServiceName.$streamName.log"
        if (-not (Test-Path -LiteralPath $oldLog -PathType Leaf)) { continue }
        New-Item -ItemType Directory -Force -Path $archiveDirectory -ErrorAction Stop | Out-Null
        $archivedLog = Join-Path $archiveDirectory "$ServiceName.$archiveStamp.$archiveToken.$streamName.log"
        # 先移动成功再允许启动；不覆盖同名归档、不递归删除，不读取可能敏感的正文。
        Move-Item -LiteralPath $oldLog -Destination $archivedLog -ErrorAction Stop
        $archivedLog
    }
}
