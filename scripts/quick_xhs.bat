@echo off
chcp 65001 >nul
echo ==========================================
echo   Smart Agent - 小红书/抖音 一键搜索
echo ==========================================
echo.

:: 自动启动 CDP Chrome（如果未运行）
echo [1/3] 启动 CDP Chrome...
powershell -ExecutionPolicy Bypass -File "%~dp0start_cdp_chrome.ps1"
if %errorlevel% neq 0 (
    echo 错误: CDP Chrome 启动失败
    pause
    exit /b 1
)

:: 自动设环境变量
set BROWSER_ENGINE=cdp

echo.
echo [2/3] 请在弹出的 Chrome 窗口中登录:
echo     小红书: https://www.xiaohongshu.com
echo     抖音:   https://www.douyin.com
echo.
echo 登录完成后，按任意键继续搜索...
pause >nul

:: 运行搜索
echo.
echo [3/3] 开始搜索...
echo.

if "%1"=="" (
    echo 用法: quick_xhs.bat [平台] [关键词]
    echo 示例: quick_xhs.bat xiaohongshu 穿搭
    echo        quick_xhs.bat douyin AI工具
    echo.
    set /p PLATFORM="平台 (xiaohongshu/douyin): "
    set /p KEYWORD="关键词: "
) else (
    set PLATFORM=%1
    set KEYWORD=%2
)

if "%KEYWORD%"=="" (
    echo 关键词不能为空
    pause
    exit /b 1
)

python "%~dp0..\main.py" --platform %PLATFORM% --keyword "%KEYWORD%"

echo.
echo ==========================================
echo   搜索完成，结果保存在 output\ 目录
echo ==========================================
pause
