@echo off
REM ====================================
REM MemU MCP Server - HTTP 服务启动脚本
REM 端口：3335
REM 协议：MCP over HTTP
REM ====================================

cd /d "%~dp0"

REM 后台启动服务（使用 pythonw 无窗口模式）
start "" /b "C:\Users\ASUS\AppData\Local\Programs\Python\Python314\pythonw.exe" server.py --transport http --host 127.0.0.1 --port 3335 --project mcp-manager

echo MemU MCP Server 已在后台启动
echo 日志文件: %~dp0logs\memu.log
