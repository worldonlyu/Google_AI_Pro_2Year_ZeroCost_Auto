#!/usr/bin/env bash
# Google AI Pro console - Linux launcher.
# First run: creates a venv, installs dependencies, then starts the console.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
VENV=.venv

if [ ! -x "$VENV/bin/python" ]; then
  echo "==> Creating virtualenv in $VENV"
  "$PY" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

if [ ! -f "$VENV/.deps-ok" ]; then
  echo "==> Installing dependencies"
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r requirements.txt
  touch "$VENV/.deps-ok"
fi

if ! command -v google-chrome >/dev/null 2>&1 \
   && ! command -v chromium >/dev/null 2>&1 \
   && ! command -v chromium-browser >/dev/null 2>&1 \
   && [ -z "${CHROME_PATH:-}" ]; then
  echo "!! No Chrome/Chromium found on PATH. Install one, e.g.:"
  echo "   Debian/Ubuntu: sudo apt install chromium    |  Fedora: sudo dnf install chromium"
  echo "   or point CHROME_PATH=/path/to/chrome at an existing install."
fi

echo "==> Console: http://127.0.0.1:8765"
exec python app.py
