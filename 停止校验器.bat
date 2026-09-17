@echo off
chcp 65001 >nul 2>nul
title 停止诗词格律校验器
cd /d "%~dp0"

echo.
echo   正在查找诗词格律校验器服务...
echo.

rem 只杀「监听校验器端口 且 进程名以 python 开头」的进程，
rem 避免误伤占用同端口的其它程序。
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ports = 8765,8766,8767,8768,8080,8000;" ^
 "$hit = $false;" ^
 "foreach ($p in $ports) {" ^
 "  Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object {" ^
 "    $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue;" ^
 "    if ($proc -and $proc.ProcessName -like 'python*') {" ^
 "      Write-Host ('    停止端口 ' + $p + '（PID ' + $_.OwningProcess + '）');" ^
 "      Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue;" ^
 "      $hit = $true" ^
 "    }" ^
 "  }" ^
 "}" ^
 "if (-not $hit) { Write-Host '    没有发现正在运行的校验服务。' }"

echo.
echo   完成。按任意键关闭本窗口。
pause >nul
