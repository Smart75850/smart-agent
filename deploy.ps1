# Smart Agent Pro — Windows 一键部署脚本
# 用法: .\deploy.ps1              # 完整部署 + 启动 WebUI
#       .\deploy.ps1 --setup-only # 仅安装依赖
#       .\deploy.ps1 --with-cookie-bridge  # 部署 + Cookie 同步服务

param(
    [switch]$SetupOnly,
    [switch]$WithCookieBridge
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Smart Agent Pro — Windows 部署" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 检查 Python ──────────────────────────────────
Write-Host "[1/6] 检查 Python ..." -ForegroundColor Yellow
try {
    $pyVersion = python --version 2>&1
    Write-Host "  $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "  ❌ 未找到 Python！请先安装 Python 3.11+ https://www.python.org/downloads/" -ForegroundColor Red
    pause
    exit 1
}

# ── 2. 创建虚拟环境 ─────────────────────────────────
Write-Host "[2/6] 虚拟环境 ..." -ForegroundColor Yellow
$venvPath = Join-Path $projectRoot "venv"
if (-not (Test-Path $venvPath)) {
    python -m venv venv
    Write-Host "  虚拟环境已创建" -ForegroundColor Green
} else {
    Write-Host "  虚拟环境已存在，跳过" -ForegroundColor Green
}

# 激活
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
. $activateScript

# ── 3. 安装 Python 依赖 ─────────────────────────────
Write-Host "[3/6] 安装 Python 依赖 ..." -ForegroundColor Yellow
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
Write-Host "  依赖安装完成" -ForegroundColor Green

# ── 4. 安装 Playwright 浏览器 ─────────────────────────
Write-Host "[4/6] 安装 Playwright 浏览器 ..." -ForegroundColor Yellow
$playwrightBrowsers = Join-Path $env:LOCALAPPDATA "ms-playwright"
if (Test-Path $playwrightBrowsers) {
    Write-Host "  浏览器已安装，跳过 (如需重装请删 $playwrightBrowsers)" -ForegroundColor Green
} else {
    playwright install chromium firefox
    Write-Host "  浏览器安装完成" -ForegroundColor Green
}

# ── 5. 检查 .env 配置 ───────────────────────────────
Write-Host "[5/6] 检查配置文件 ..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  ⚠️  已从 .env.example 创建 .env" -ForegroundColor Yellow
    Write-Host "  ⚠️  请编辑 .env 填入 DEEPSEEK_API_KEY 后重新运行！" -ForegroundColor Yellow
    if ($SetupOnly) { exit 0 }
    Write-Host ""
    Write-Host "  按任意键打开 .env 进行编辑..." -ForegroundColor Cyan
    pause | Out-Null
    Start-Process notepad ".env"
    Write-Host "  编辑保存后按任意键继续..." -ForegroundColor Cyan
    pause | Out-Null
} else {
    Write-Host "  .env 已存在" -ForegroundColor Green
}

# ── 6. 创建目录 ──────────────────────────────────────
Write-Host "[6/6] 创建数据目录 ..." -ForegroundColor Yellow
foreach ($dir in @("output", "downloads", "browser_data")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  $dir/ 已创建" -ForegroundColor Green
    }
}

# ── 完成 ─────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  部署完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($SetupOnly) {
    Write-Host "  仅安装模式，不启动服务。" -ForegroundColor Yellow
    Write-Host "  运行 .\deploy.ps1 启动 WebUI" -ForegroundColor Yellow
    pause
    exit 0
}

# ── 启动服务 ─────────────────────────────────────────
$env:PYTHONPATH = $projectRoot

if ($WithCookieBridge) {
    Write-Host "  启动 CookieBridge + WebUI ..." -ForegroundColor Cyan
    Write-Host "  CookieBridge: http://localhost:8765" -ForegroundColor Gray
    Write-Host "  WebUI:        http://localhost:8000" -ForegroundColor Gray
    Write-Host ""
    Start-Process python -ArgumentList "-m", "api.main" -NoNewWindow
    python main.py --cookie-bridge
} else {
    Write-Host "  启动 WebUI: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "  启动 CLI:   python main.py --engine langgraph --type aggregate --keyword <关键词> --pipeline full" -ForegroundColor Gray
    Write-Host ""
    python -m api.main
}

pause
