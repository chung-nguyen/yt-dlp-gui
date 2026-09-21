#!/usr/bin/env bash
# Development launcher. From the repo root: bash scripts/dev.sh
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

echo "Installing development dependencies..."
.venv/bin/python -m pip install -e . --disable-pip-version-check

echo "Starting yt-dlp GUI..."
exec .venv/bin/python -m ytdlp_gui "$@"
