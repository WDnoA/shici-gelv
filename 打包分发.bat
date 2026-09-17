@echo off
chcp 65001 >nul 2>nul
title 打包诗词格律校验器

rem %~dp0 以反斜杠结尾，直接写成 "%~dp0" 会让结尾的 \" 被当成转义引号，
rem 必须先把尾部的反斜杠去掉。
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
cd /d "%HERE%"

echo.
echo   正在打包「诗词格律校验器」...
echo.

if not exist "%HERE%\main.py" (
  echo   [错误] 找不到 main.py，请把这个 .bat 放在项目根目录。
  echo.
  pause
  exit /b 1
)

set "STAGE=%TEMP%\shici_pack_stage"
set "OUT=%HERE%\诗词格律校验器.zip"

if exist "%STAGE%" rd /s /q "%STAGE%" >nul 2>nul

rem 排除缓存与版本库（robocopy 的成功码是 0-7，>=8 才算失败）
robocopy "%HERE%" "%STAGE%" /E /XD __pycache__ .git /XF *.pyc /NFL /NDL /NJH /NJS /NP >nul
if %ERRORLEVEL% GEQ 8 (
  echo   [错误] 复制文件失败（robocopy 代码 %ERRORLEVEL%）。
  echo.
  pause
  exit /b 1
)

if exist "%OUT%" del /f /q "%OUT%" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%OUT%' -CompressionLevel Optimal -Force"

set "RC=%ERRORLEVEL%"
rd /s /q "%STAGE%" >nul 2>nul

if not "%RC%"=="0" (
  echo   [错误] 压缩失败。
  echo.
  pause
  exit /b 1
)

for %%A in ("%OUT%") do set "SIZE=%%~zA"
set /a "KB=%SIZE%/1024"

echo   打包完成：
echo     %OUT%
echo     （约 %KB% KB）
echo.
echo   把这个 zip 发给别人，对方解压后双击「启动校验器.bat」即可使用。
echo   对方电脑上只需装有 Python 3.9 或更高版本。
echo.
pause
