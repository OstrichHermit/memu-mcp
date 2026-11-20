$conn = Get-NetTCPConnection -LocalPort 3335 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Write-Output "MemU (PID $($conn.OwningProcess)) stopped" } else { Write-Output "MemU not running" }
