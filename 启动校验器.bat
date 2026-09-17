@echo off
rem 控制台切到 UTF-8，与本文件（UTF-8）及 Python 的输出保持一致，
rem 否则中文在 cmd 里会变成乱码。
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"
title 诗词格律校验器
cd /d "%~dp0"

echo.
echo   诗 词 格 律 校 验 器
echo   ==================================================
echo.

rem ---- 找一个可用的 Python ----
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  where py >nul 2>nul && set "PY=py"
)

if not defined PY (
  echo   [错误] 没有找到 Python。
  echo.
  echo   请先安装 Python 3.9 或更高版本：
  echo     https://www.python.org/downloads/
  echo   安装时务必勾选 "Add Python to PATH"。
  echo.
  pause
  exit /b 1
)

rem ---- 检查项目文件是否齐全 ----
if not exist "%~dp0server.py" (
  echo   [错误] 找不到 server.py。
  echo   请把这个 .bat 放在项目根目录（与 server.py 同级）。
  echo.
  pause
  exit /b 1
)

echo   已找到 Python：
for /f "delims=" %%v in ('%PY% -c "import sys;print(sys.version.split()[0])"') do echo     %%v
echo.
echo   正在启动本地服务，浏览器会自动打开...
echo   （若没有自动打开，请手动访问窗口里显示的地址）
echo.

"%PY%" "%~dp0server.py"
set "CODE=%ERRORLEVEL%"

echo.
if not "%CODE%"=="0" (
  echo   服务已结束（退出代码 %CODE%）。
  echo.
  echo   如果你刚才用了「停止校验器.bat」，这是正常的，忽略即可。
  echo   如果是自行退出的，请把上面的报错信息截图反馈。
) else (
  echo   服务已正常停止。
)
echo.
pause
