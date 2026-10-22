[CmdletBinding()]
param(
    [ValidateSet('scrapy', 'crawlee', 'playwright', 'crawlab', 'feapder', 'trafilatura', 'rapidfuzz', 'splink', 'python-phonenumbers', 'paddleocr')]
    [string[]] $Project
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repos = Join-Path $root 'repos'

$allowlist = @{
    'scrapy' = 'https://github.com/scrapy/scrapy.git'
    'crawlee' = 'https://github.com/apify/crawlee.git'
    'playwright' = 'https://github.com/microsoft/playwright.git'
    'crawlab' = 'https://github.com/crawlab-team/crawlab.git'
    'feapder' = 'https://github.com/Boris-code/feapder.git'
    'trafilatura' = 'https://github.com/adbar/trafilatura.git'
    'rapidfuzz' = 'https://github.com/rapidfuzz/RapidFuzz.git'
    'splink' = 'https://github.com/moj-analytical-services/splink.git'
    'python-phonenumbers' = 'https://github.com/daviddrysdale/python-phonenumbers.git'
    'paddleocr' = 'https://github.com/PaddlePaddle/PaddleOCR.git'
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw '未找到 git。请先安装 Git，再运行此脚本。'
}

if (-not $Project -or $Project.Count -eq 0) {
    Write-Host '未指定项目。示例：'
    Write-Host '.\bootstrap.ps1 -Project scrapy,rapidfuzz'
    Write-Host '脚本只从 allowlist 克隆仓库，不执行第三方代码，也不会覆盖已有目录。'
    exit 0
}

New-Item -ItemType Directory -Force -Path $repos | Out-Null

foreach ($name in $Project) {
    $target = Join-Path $repos $name
    if (Test-Path -LiteralPath $target) {
        Write-Host "跳过已存在目录：$target"
        continue
    }

    Write-Host "克隆 $name ..."
    & git clone --depth 1 $allowlist[$name] $target
    if ($LASTEXITCODE -ne 0) {
        throw "克隆 $name 失败，退出码：$LASTEXITCODE"
    }
}

Write-Host '完成。请逐个核对仓库 LICENSE、版本和目标数据源授权，不要直接运行未知仓库中的脚本。'
