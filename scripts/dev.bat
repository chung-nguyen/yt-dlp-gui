@echo off
setlocal
cd /d "%~dp0.."

call :resolve_python
if errorlevel 1 exit /b 1
call :ensure_venv
if errorlevel 1 exit /b 1

echo Installing development dependencies...
".venv\Scripts\python.exe" -m pip install -e . --disable-pip-version-check
if errorlevel 1 exit /b 1

echo Starting yt-dlp GUI...
".venv\Scripts\python.exe" -m ytdlp_gui %*
exit /b %errorlevel%

:resolve_python
set "PY_CMD="
where py >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD (
  where python >nul 2>&1 && set "PY_CMD=python"
)
if not defined PY_CMD (
  echo Python 3.11 or newer is required.
  exit /b 1
)
call %PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  exit /b 1
)
exit /b 0

:ensure_venv
if exist ".venv\Scripts\python.exe" exit /b 0
echo Creating .venv ...
call %PY_CMD% -m venv .venv
if errorlevel 1 exit /b 1
exit /b 0
