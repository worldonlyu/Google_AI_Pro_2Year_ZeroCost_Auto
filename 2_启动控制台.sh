#!/usr/bin/env bash
# 日常启动控制台（Ubuntu / Linux）
set -e
cd "$(dirname "$0")"
echo "======================================================================"
echo "  正在启动 Google AI Pro (5 TB) 零成本两年全自动控制台..."
echo "  控制台地址: http://127.0.0.1:8765"
echo "======================================================================"
(sleep 2; xdg-open "http://127.0.0.1:8765" >/dev/null 2>&1 || true) &
exec python3 app.py
