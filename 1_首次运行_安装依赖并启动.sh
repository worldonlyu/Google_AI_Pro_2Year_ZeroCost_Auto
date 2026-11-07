#!/usr/bin/env bash
# 首次运行：安装 Python 依赖并启动控制台（Ubuntu / Linux）
set -e
cd "$(dirname "$0")"

PY=python3
command -v "$PY" >/dev/null 2>&1 || { echo "❌ 未找到 python3，请先安装 Python 3.10+"; exit 1; }
command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1 \
  || command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 \
  || echo "⚠️ 未在 PATH 中找到 Chrome/Chromium；如装在自定义路径，请先 export CHROME_PATH=/path/to/chrome"

echo "======================================================================"
echo "  正在安装 Python 依赖 (fastapi, uvicorn, playwright)..."
echo "======================================================================"
"$PY" -m pip install -r requirements.txt

echo "======================================================================"
echo "  正在启动 Web 控制台 (http://127.0.0.1:8765) ..."
echo "  注意：自动化需要图形会话（有显示器/远程桌面），请在本机桌面终端里运行本脚本。"
echo "======================================================================"
(sleep 2; xdg-open "http://127.0.0.1:8765" >/dev/null 2>&1 || true) &
exec "$PY" app.py
