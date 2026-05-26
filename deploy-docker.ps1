# Smart Agent Pro — Docker 一键部署脚本
# 用法: .\deploy-docker.ps1              # 构建 + 启动
#       .\deploy-docker.ps1 --BuildOnly  # 仅构建
#       .\deploy-docker.ps1 --Rebuild    # 强制重建（--no-cache）
#       .\deploy-docker.ps1 --WithMySQL  # 构建 + 启动 + MySQL

param(
    [switch]$BuildOnly,
    [switch]$Rebuild,
    [switch]$WithMySQL
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Smart Agent Pro — Docker 部署" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 检查 Docker ──────────────────────────────────
Write-Host "[1/5] 检查 Docker ..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "  $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "  X 未找到 Docker！请先安装 Docker Desktop https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
    pause
    exit 1
}

# 检查 Docker 是否在运行
try {
    docker ps 2>&1 | Out-Null
} catch {
    Write-Host "  X Docker 未运行！请先启动 Docker Desktop" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "  Docker 运行中" -ForegroundColor Green

# ── 2. 检查 .env 配置 ───────────────────────────────
Write-Host "[2/5] 检查配置文件 ..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  ! 已从 .env.example 创建 .env" -ForegroundColor Yellow
    Write-Host "  ! 请编辑 .env 填入 DEEPSEEK_API_KEY 后重新运行！" -ForegroundColor Yellow
    if ($BuildOnly) { exit 0 }
    Write-Host ""
    Write-Host "  按任意键打开 .env 进行编辑..." -ForegroundColor Cyan
    pause | Out-Null
    Start-Process notepad ".env"
    Write-Host "  编辑保存后按任意键继续..." -ForegroundColor Cyan
    pause | Out-Null
} else {
    Write-Host "  .env 已存在" -ForegroundColor Green
}

# 检查 API Key 是否还是默认值
$envContent = Get-Content ".env" -Raw
if ($envContent -match "DEEPSEEK_API_KEY=sk-your-api-key-here") {
    Write-Host "  ! 警告：DEEPSEEK_API_KEY 仍为默认值，Agent 分析将使用降级模式" -ForegroundColor Yellow
}

# ── 3. 构建镜像 ──────────────────────────────────────
Write-Host "[3/5] 构建 Docker 镜像 ..." -ForegroundColor Yellow
$buildArgs = @("compose", "build")
if ($Rebuild) {
    $buildArgs += "--no-cache"
    Write-Host "  (强制重建 --no-cache)" -ForegroundColor Yellow
}
$buildArgs += "app"

$buildStart = Get-Date
docker @buildArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "  X 构建失败！" -ForegroundColor Red
    pause
    exit 1
}
$buildTime = (Get-Date) - $buildStart
Write-Host "  构建完成 (耗时 $([math]::Round($buildTime.TotalSeconds, 0))s)" -ForegroundColor Green

if ($BuildOnly) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  仅构建模式，镜像已就绪。" -ForegroundColor Green
    Write-Host "  运行 .\deploy-docker.ps1 启动容器" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    pause
    exit 0
}

# ── 4. 启动容器 ──────────────────────────────────────
Write-Host "[4/5] 启动容器 ..." -ForegroundColor Yellow

# 停止并移除旧容器
docker compose down 2>$null
Write-Host "  已清理旧容器" -ForegroundColor Gray

$upArgs = @("compose", "up", "-d")
if ($WithMySQL) {
    $upArgs += "--profile", "mysql"
}

docker @upArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "  X 启动失败！" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "  容器已启动" -ForegroundColor Green

# ── 5. 展示状态 ──────────────────────────────────────
Write-Host "[5/5] 检查服务状态 ..." -ForegroundColor Yellow

# 等 3 秒俾容器初始化
Start-Sleep -Seconds 3

Write-Host ""
docker compose ps

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Docker 部署完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  WebUI:  http://localhost:8000" -ForegroundColor Cyan
Write-Host "  API:    http://localhost:8000/api/config" -ForegroundColor Cyan
if ($WithMySQL) {
    Write-Host "  MySQL:  localhost:3307 (容器内 3306)" -ForegroundColor Gray
}
Write-Host ""
Write-Host "  常用命令：" -ForegroundColor White
Write-Host "    查看日志:  docker compose logs -f app" -ForegroundColor Gray
Write-Host "    停止服务:  docker compose down" -ForegroundColor Gray
Write-Host "    重启服务:  docker compose restart app" -ForegroundColor Gray
if ($WithMySQL) {
    Write-Host "    进 MySQL:  docker compose exec mysql mysql -u root -p" -ForegroundColor Gray
}
Write-Host ""

pause
