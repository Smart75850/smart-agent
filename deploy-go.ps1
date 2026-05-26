# Smart Agent Pro — Go 版本一键构建部署脚本
# 用法: .\deploy-go.ps1              # 构建 + 启动
#       .\deploy-go.ps1 --BuildOnly  # 仅构建

param(
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Smart Agent Pro — Go 版部署" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 检查 Go ──────────────────────────────────────
Write-Host "[1/4] 检查 Go ..." -ForegroundColor Yellow
try {
    $goVersion = go version 2>&1
    Write-Host "  $goVersion" -ForegroundColor Green
} catch {
    Write-Host "  X 未找到 Go！请先安装 Go 1.22+ https://go.dev/dl/" -ForegroundColor Red
    pause
    exit 1
}

# ── 2. 检查 Python sidecar ──────────────────────────
Write-Host "[2/4] 检查 Python 环境 ..." -ForegroundColor Yellow
try {
    $pyVersion = python --version 2>&1
    Write-Host "  $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "  X 未找到 Python！Sidecar 需要 Python 3.11+" -ForegroundColor Red
    pause
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Host "  ! .env 不存在，从 .env.example 复制..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "  ! 请编辑 .env 填入 DEEPSEEK_API_KEY" -ForegroundColor Yellow
}

# ── 3. 构建 Go 二进制 ───────────────────────────────
Write-Host "[3/4] 构建 Go 二进制 ..." -ForegroundColor Yellow
Set-Location "$projectRoot\go"

$env:GOOS = "windows"
$env:GOARCH = "amd64"
$env:CGO_ENABLED = "0"

go mod tidy 2>&1 | Out-Null
$buildStart = Get-Date
go build -ldflags "-s -w" -o "$projectRoot\smart-agent-go.exe" .\cmd\smart-agent\ 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  X 构建失败！" -ForegroundColor Red
    Set-Location $projectRoot
    pause
    exit 1
}
$buildTime = (Get-Date) - $buildStart
$binSize = (Get-Item "$projectRoot\smart-agent-go.exe").Length / 1MB
Write-Host "  构建完成: smart-agent-go.exe ($([math]::Round($binSize, 1))MB, 耗时 $([math]::Round($buildTime.TotalSeconds, 0))s)" -ForegroundColor Green

Set-Location $projectRoot

if ($BuildOnly) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  仅构建模式。二进制: smart-agent-go.exe" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    pause
    exit 0
}

# ── 4. 启动服务 ────────────────────────────────────
Write-Host "[4/4] 启动服务 ..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Python Sidecar: http://localhost:18500" -ForegroundColor Gray
Write-Host "  Go API:         http://localhost:8000" -ForegroundColor Cyan
Write-Host ""

# 启动 Python sidecar (后台)
$sidecarJob = Start-Job -Name "smart-agent-sidecar" -ScriptBlock {
    Set-Location $using:projectRoot
    python sidecar_server.py 2>&1 | Out-File "sidecar.log"
}
Write-Host "  Sidecar PID: $($sidecarJob.Id)" -ForegroundColor Green

# 等待 sidecar 就绪
Write-Host "  等待 Sidecar 就绪..." -ForegroundColor Yellow
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:18500/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { break }
    } catch { }
    Start-Sleep -Seconds 1
}
Write-Host "  Sidecar 就绪" -ForegroundColor Green

# 启动 Go 服务器 (前台)
Write-Host "  启动 Go API 服务器..." -ForegroundColor Yellow
Write-Host ""
& "$projectRoot\smart-agent-go.exe" --serve 2>&1
