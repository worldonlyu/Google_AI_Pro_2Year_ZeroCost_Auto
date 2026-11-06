#!/bin/bash
cd "$(dirname "$0")"

echo "======================================================================"
echo "  Google AI Pro (5 TB) 零成本两年全自动控制台 (macOS)"
echo "  控制台地址: http://127.0.0.1:8765"
echo "======================================================================"

python3 -m pip install -q -r requirements.txt

( sleep 2 && open "http://127.0.0.1:8765" ) &

python3 app.py

read -p "按回车键退出..."
