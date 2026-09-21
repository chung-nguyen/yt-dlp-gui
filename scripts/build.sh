#!/usr/bin/env bash
# Freeze a windowed folder build into dist/yt-dlp-gui. ffmpeg is not bundled.
# From the repo root: bash scripts/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."

resolve_python() {
  if command -v python3 >/dev/null 2>&1; then
    PY_CMD=(python3)
  elif command -v python >/dev/null 2>&1; then
    PY_CMD=(python)
  else
    echo "Python 3.11 or newer is required." >&2
    exit 1
  fi
  if ! "${PY_CMD[@]}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Python 3.11 or newer is required." >&2
    exit 1
  fi
}

ensure_venv() {
  if [[ -x .venv/bin/python ]]; then
    return
  fi
  echo "Creating .venv ..."
  "${PY_CMD[@]}" -m venv .venv
}

resolve_python
ensure_venv

echo "Installing build dependencies..."
.venv/bin/python -m pip install -e '.[build]' --disable-pip-version-check

echo "Building dist/yt-dlp-gui ..."
.venv/bin/python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name yt-dlp-gui \
  --noupx \
  --paths src \
  --collect-all customtkinter \
  --collect-all yt_dlp \
  --collect-submodules ytdlp_gui \
  --exclude-module numpy \
  --exclude-module pandas \
  --exclude-module PIL \
  --exclude-module PySide6 \
  --exclude-module PyQt6 \
  --exclude-module tkinter.test \
  src/ytdlp_gui/__main__.py

echo
echo "Distribution folder: $(pwd)/dist/yt-dlp-gui"
echo "Run: dist/yt-dlp-gui/yt-dlp-gui"
