@echo off
REM ====================================
REM MemU MCP Server - 一键重启脚本
REM 端口：3335
REM ====================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo =====================================
echo   MemU MCP Server - 重启服务
echo =====================================
echo.

REM 查找占用端口 3335 的进程
echo [1/4] 检查端口 3335 使用情况...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3335 ^| findstr LISTENING') do (
    set "OLD_PID=%%a"
)

if defined OLD_PID (
    echo [2/4] 发现运行中的服务 (PID: !OLD_PID!)
    echo        正在停止...
    taskkill /PID !OLD_PID! /F >nul 2>&1

    REM 等待进程完全退出
    timeout /t 2 /nobreak >nul

    REM 验证进程是否已停止
    tasklist /FI "PID eq !OLD_PID!" 2>nul | findstr !OLD_PID! >nul
    if errorlevel 1 (
        echo        服务已成功停止
    ) else (
        echo        警告：进程可能仍在运行
    )
) else (
    echo [2/4] 未发现运行中的服务，跳过停止步骤
)

echo.
echo [3/4] 启动 MemU MCP Server...

REM 配置从 .env 读取（见 docs/INSTALL.md）：
REM   项目父目录的 .env 会被自动加载，也可用 MEMU_ENV_FILE 指定位置
set "PYTHONUNBUFFERED=1"

REM 启动服务（pythonw 无窗口模式，本脚本窗口保留用于显示状态）
start "MemU MCP Server" /b "C:\Users\ASUS\AppData\Local\Programs\Python\Python314\pythonw.exe" server.py --transport http --host 127.0.0.1 --port 3335 --project mcp-manager

REM 等待服务启动
timeout /t 3 /nobreak >nul

echo.
echo [4/4] 验证服务状态...

REM 检查服务是否已启动
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3335 ^| findstr LISTENING') do (
    set "NEW_PID=%%a"
)

if defined NEW_PID (
    echo.
    echo =====================================
    echo   重启成功
    echo =====================================
    echo   端口：3335
    echo   进程 ID：!NEW_PID!
    echo   状态：运行中
    echo =====================================
    echo.
) else (
    echo.
    echo =====================================
    echo   重启失败
    echo =====================================
    echo   无法检测到服务在端口 3335 上运行
    echo   请检查错误日志
    echo =====================================
    echo.
    pause
    exit /b 1
)

echo 提示：按任意键关闭此窗口...
pause >nul
