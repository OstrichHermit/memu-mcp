# ========================================
# MemU MCP Server - 计划任务创建脚本
# ========================================
# 用途：创建系统启动时自动启动 MemU MCP Server 的计划任务
# 使用方法：以管理员身份运行此脚本
# ========================================

#Requires -RunAsAdministrator

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  MemU MCP Server 计划任务创建工具" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# 配置参数
$TaskName = "MemU MCP AutoStart"
$BatPath = "D:\AgentWorkspace\MemU\memu-mcp\start_memu_service.bat"
$WorkingDirectory = "D:\AgentWorkspace\MemU\memu-mcp"

# 检查批处理文件是否存在
if (-not (Test-Path $BatPath)) {
    Write-Host "❌ 错误：找不到启动脚本" -ForegroundColor Red
    Write-Host "   路径：$BatPath" -ForegroundColor Red
    Write-Host ""
    pause
    exit 1
}

Write-Host "✓ 找到启动脚本：$BatPath" -ForegroundColor Green
Write-Host ""

# 删除已存在的同名任务（如果有）
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "⚠ 发现已存在的任务，正在删除..." -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "✓ 旧任务已删除" -ForegroundColor Green
    } catch {
        Write-Host "❌ 删除旧任务失败：$_" -ForegroundColor Red
        pause
        exit 1
    }
}

# 创建计划任务触发器（系统启动时）
$Trigger = New-ScheduledTaskTrigger -AtStartup
Write-Host "✓ 触发器：系统启动时" -ForegroundColor Green

# 创建计划任务操作
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BatPath`"" `
    -WorkingDirectory $WorkingDirectory
Write-Host "✓ 操作：运行 $BatPath" -ForegroundColor Green

# 创建计划任务主体
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Write-Host "✓ 运行身份：SYSTEM（系统账户）" -ForegroundColor Green

# 设置任务属性
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2)
Write-Host "✓ 设置：允许后台运行，失败后自动重试" -ForegroundColor Green

# 注册计划任务
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description "MemU MCP HTTP Server - 端口 3335" `
        -ErrorAction Stop

    Write-Host ""
    Write-Host "====================================" -ForegroundColor Green
    Write-Host "✅ 计划任务创建成功！" -ForegroundColor Green
    Write-Host "====================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "任务名称：$TaskName" -ForegroundColor White
    Write-Host "触发方式：系统启动时" -ForegroundColor White
    Write-Host "运行身份：SYSTEM" -ForegroundColor White
    Write-Host ""
    Write-Host "📝 验证任务：" -ForegroundColor Cyan
    Write-Host "   在 PowerShell 中运行：" -ForegroundColor Gray
    Write-Host "   Get-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "🗑️  删除任务：" -ForegroundColor Cyan
    Write-Host "   Unregister-ScheduledTask -TaskName `"$TaskName`" -Confirm:`$false" -ForegroundColor Yellow
    Write-Host ""

} catch {
    Write-Host ""
    Write-Host "====================================" -ForegroundColor Red
    Write-Host "❌ 创建失败" -ForegroundColor Red
    Write-Host "====================================" -ForegroundColor Red
    Write-Host "错误信息：$_" -ForegroundColor Red
    Write-Host ""
}

pause
