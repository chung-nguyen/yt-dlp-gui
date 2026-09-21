@echo off
setlocal
cd /d "%~dp0.."

call :resolve_python
if errorlevel 1 exit /b 1
call :ensure_venv
if errorlevel 1 exit /b 1

echo Installing build dependencies...
".venv\Scripts\python.exe" -m pip install -e ".[build]" --disable-pip-version-check
if errorlevel 1 exit /b 1

echo Building dist\yt-dlp-gui ...
".venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name yt-dlp-gui ^
  --noupx ^
  --paths src ^
  --collect-all customtkinter ^
  --collect-all yt_dlp ^
  --collect-submodules ytdlp_gui ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  --exclude-module PIL ^
  --exclude-module PySide6 ^
  --exclude-module PyQt6 ^
  --exclude-module tkinter.test ^
  src\ytdlp_gui\__main__.py
if errorlevel 1 exit /b 1

echo.
echo Distribution folder: %CD%\dist\yt-dlp-gui
echo Run: dist\yt-dlp-gui\yt-dlp-gui.exe
exit /b 0

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
