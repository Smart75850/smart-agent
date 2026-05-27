# Smart Agent CDP Chrome 啟動腳本
# 用大佬真實 Chrome profile + 遠程調試端口

param(
    [string]$Mode = "main",           # main=真實profile, dedicated=養號專用
    [int]$Port = 9222                 # CDP 端口（dedicated 用 9223）
)

$ChromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"

if ($Mode -eq "main") {
    $ProfileDir = "$env:LOCALAPPDATA\Google\Chrome\User Data"
    Write-Host "=== 啟動真實 Chrome Profile (CDP port $Port) ==="
} else {
    $ProfileDir = "$PSScriptRoot\..\browser_data\dedicated_chrome"
    New-Item -ItemType Directory -Force $ProfileDir | Out-Null
    Write-Host "=== 啟動養號專用 Chrome Profile (CDP port $Port) ==="
}

# Kill existing Chrome on this port
$existing = netstat -ano | Select-String ":$Port.*LISTENING"
if ($existing) {
    Write-Host "端口 $Port 已被佔用，嘗試關閉..."
    $pidMatch = [regex]::Match($existing, '\s+(\d+)$')
    if ($pidMatch.Success) {
        Stop-Process -Id $pidMatch.Groups[1].Value -Force -ErrorAction SilentlyContinue
        Start-Sleep 2
    }
}

Start-Process $ChromePath "--remote-debugging-port=$Port", "--user-data-dir=$ProfileDir"
Start-Sleep 3

# Verify
$check = netstat -ano | Select-String ":$Port.*LISTENING"
if ($check) {
    Write-Host "Chrome 已啟動 (CDP port $Port) - 就緒"
} else {
    Write-Host "啟動失敗，請檢查 Chrome 路徑: $ChromePath"
}
