@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "PROJECT_ROOT=%~dp0"
set "PORT=5000"
set "HEALTH_URL=http://127.0.0.1:%PORT%/api/graph/stats"

cd /d "%PROJECT_ROOT%"

echo ========================================
echo  TGCN交通路径规划系统启动脚本
echo ========================================
echo 项目目录: %PROJECT_ROOT%
echo 服务端口: %PORT%
echo.

echo [1/4] 检查 Python 环境...
where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
    ) else (
        echo 未找到 Python。请先安装 Python 3.8+，并加入 PATH。
        echo.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% --version
if errorlevel 1 (
    echo Python 可执行文件检测失败。
    echo.
    pause
    exit /b 1
)
echo.

echo [2/4] 释放 %PORT% 端口...
set "FOUND_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "FOUND_PID=%%a"
    echo 发现占用端口 %PORT% 的进程 PID: %%a
    taskkill /F /PID %%a >nul 2>nul
)

if not defined FOUND_PID (
    echo 端口 %PORT% 当前未被占用。
) else (
    timeout /t 2 /nobreak >nul
)
echo.

echo [3/4] 启动后端服务...
if not exist "backend\app.py" (
    echo 未找到 backend\app.py，请确认脚本位于项目根目录。
    echo.
    pause
    exit /b 1
)

start "TGCN Backend Server" /D "%PROJECT_ROOT%" cmd /k "%PYTHON_CMD% backend\app.py"
echo 等待服务初始化，首次加载路网可能需要更久...
echo.

echo [4/4] 健康检查...
set "SERVER_READY=0"
for /l %%i in (1,1,45) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%HEALTH_URL%'; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
    if !errorlevel!==0 (
        set "SERVER_READY=1"
        goto :health_ok
    )
    echo 等待服务响应... %%i/20
    timeout /t 2 /nobreak >nul
)

:health_ok
echo.
if "%SERVER_READY%"=="1" (
    echo ========================================
    echo 服务启动成功！
    echo ========================================
    echo 主页面:   http://127.0.0.1:%PORT%/
    echo 备用页面: http://localhost:%PORT%/index.html
    echo 比对页面: http://127.0.0.1:%PORT%/compare.html
    echo 健康检查: %HEALTH_URL%
    echo.
    start "" "http://127.0.0.1:%PORT%/"
) else (
    echo ========================================
    echo 服务可能仍在启动，健康检查暂未通过。
    echo ========================================
    echo 请查看新打开的后端窗口日志。
    echo 手动访问: http://127.0.0.1:%PORT%/
    echo 备用访问: http://localhost:%PORT%/index.html
    echo.
)

pause
endlocal
