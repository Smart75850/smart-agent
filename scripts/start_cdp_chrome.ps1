# Start Chrome with CDP for Smart Agent
$CHROME = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$PROFILE = "C:\Users\guohu\workspace\smart-agent\browser_data\chrome_profile"
$PORT = 9222

if (-not (Test-Path $CHROME)) {
    Write-Host "ERROR: Chrome not found at $CHROME"
    exit 1
}

New-Item -ItemType Directory -Force -Path $PROFILE | Out-Null

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$PORT/json/version" -UseBasicParsing -TimeoutSec 2
    Write-Host "CDP Chrome already running on port $PORT"
    exit 0
} catch {
    Write-Host "Starting CDP Chrome on port $PORT..."
}

Start-Process -FilePath $CHROME -ArgumentList @(
    "--remote-debugging-port=$PORT",
    "--user-data-dir=$PROFILE",
    "--no-first-run",
    "--no-default-browser-check"
)

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$PORT/json/version" -UseBasicParsing -TimeoutSec 2
        Write-Host "CDP Chrome ready! (port $PORT)"
        exit 0
    } catch {
        Write-Host -NoNewline "."
    }
}
Write-Host "`nERROR: CDP Chrome failed to start within 30s"
exit 1
