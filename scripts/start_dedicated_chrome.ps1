# 養號專用 Chrome Profile 啟動腳本
# 使用獨立 profile，唔影響大佬正常 Chrome
# 需要時開呢個 Chrome 上抖音，正常瀏覽，累積信任

$Port = 9223
$ChromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$ProfileDir = "$PSScriptRoot\..\browser_data\dedicated_chrome"
New-Item -ItemType Directory -Force $ProfileDir | Out-Null

# Kill existing on this port
$existing = netstat -ano | Select-String ":$Port.*LISTENING"
if ($existing) {
    $pidMatch = [regex]::Match($existing, '\s+(\d+)$')
    if ($pidMatch.Success) {
        Stop-Process -Id $pidMatch.Groups[1].Value -Force -ErrorAction SilentlyContinue
        Start-Sleep 2
    }
}

Start-Process $ChromePath "--remote-debugging-port=$Port", "--user-data-dir=$ProfileDir"
Start-Sleep 3

$check = netstat -ano | Select-String ":$Port.*LISTENING"
if ($check) {
    Write-Host "養號 Chrome 已啟動 (CDP port $Port)"
    Write-Host "請打開 douyin.com，解 CAPTCHA 並登錄，然後正常瀏覽"
    Write-Host "目標：每日至少用 10-15 分鐘，累積瀏覽歷史同信任分"
} else {
    Write-Host "啟動失敗"
}
