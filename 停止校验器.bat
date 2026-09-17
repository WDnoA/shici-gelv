@echo off
chcp 65001 >nul 2>nul
title 停止诗词格律校验器
cd /d "%~dp0"

echo.
echo   正在查找诗词格律校验器服务...
echo.

rem 两道网：
rem   ① 按端口找 —— 但只杀「进程名以 python 开头」的，
rem      否则会误伤占用同端口的其它程序（开发机上 8080 就被系统服务占着）。
rem   ② 按命令行找 —— 捕捉「端口不在候选列表里」的残留进程。
rem      典型情形：你曾解压副本到临时目录、把目录删了却忘了停服务，
rem      那个进程指着不存在的 web/ 目录，会让所有页面都 404。
rem      排除 -c，避免把「恰好提到 server.py 的内联脚本」也算进来。
powershell -NoProfile -ExecutionPolicy Bypass -Command "$k=@(); foreach($p in 8765,8766,8767,8768,8080,8000){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | ForEach-Object { $n=(Get-Process -Id $_.OwningProcess -EA SilentlyContinue).ProcessName; if($n -like 'python*'){ Write-Host ('    停止端口 '+$p+'（PID '+$_.OwningProcess+'）'); Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue; $k+=$_.OwningProcess } } }; Get-CimInstance Win32_Process -EA SilentlyContinue | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*server.py*' -and $_.CommandLine -notlike '*-c *' } | ForEach-Object { if($k -notcontains $_.ProcessId){ Write-Host ('    停止残留服务（PID '+$_.ProcessId+'）'); Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue; $k+=$_.ProcessId } }; if($k.Count -eq 0){ Write-Host '    没有发现正在运行的校验服务。' } else { Write-Host ''; Write-Host ('    共停止 '+$k.Count+' 个进程。') }"

echo.
echo   完成。按任意键关闭本窗口。
pause >nul
