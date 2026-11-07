#!/usr/bin/env bash
set -euo pipefail

# Resolve directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================================"
echo "  Google AI Pro (5 TB) 零成本两年 (US\$0.00 -> 24个月) Linux 控制台"
echo "======================================================================"

# 1. Locate Python 3.10+
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[-] 错误: 需要 Python 3.10 或更高版本。"
    echo "    请先安装 Python 3.10+ 并确保包含 venv 模块，例如:"
    echo "    Debian/Ubuntu: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo "    RHEL/Fedora:   sudo dnf install -y python3 python3-pip"
    echo "    Arch Linux:    sudo pacman -S python python-pip"
    exit 1
fi

echo "[*] 使用 Python: $("$PYTHON_BIN" --version) ($PYTHON_BIN)"

# 2. Setup or activate virtual environment (.venv)
VENV_DIR="${VENV_PATH:-$SCRIPT_DIR/.venv}"
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[*] 创建虚拟环境: $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# 3. Install requirements
echo "[*] 正在检查并安装 Python 依赖 (requirements.txt) ..."
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

# 4. Check for Chrome / Chromium / Playwright browser
CHROME_TARGET=""
if [ -n "${CHROME_PATH:-}" ] && [ -x "${CHROME_PATH}" ]; then
    CHROME_TARGET="${CHROME_PATH}"
else
    for candidate in \
        /usr/bin/google-chrome \
        /usr/bin/google-chrome-stable \
        /usr/bin/chromium \
        /usr/bin/chromium-browser \
        /snap/bin/chromium \
        /usr/bin/google-chrome-unstable \
        /usr/bin/google-chrome-beta; do
        if [ -x "$candidate" ]; then
            CHROME_TARGET="$candidate"
            break
        fi
    done
    if [ -z "$CHROME_TARGET" ]; then
        for name in google-chrome google-chrome-stable chromium chromium-browser chrome; do
            if command -v "$name" >/dev/null 2>&1; then
                CHROME_TARGET="$(command -v "$name")"
                break
            fi
        done
    fi
fi

if [ -n "$CHROME_TARGET" ]; then
    echo "[+] 检测到可用浏览器: $CHROME_TARGET"
else
    echo "[!] 提示: 系统默认路径未找到 Google Chrome 或 Chromium。"
    echo "    正在检查 Playwright Chromium 运行库..."
    # Ensure Playwright browser can be installed or is available
    if ! python -m playwright install --dry-run chromium >/dev/null 2>&1; then
        echo "[*] 正在通过 Playwright 安装 Chromium 浏览器..."
        python -m playwright install chromium || {
            echo "[!] 自动安装 Playwright 浏览器失败。若缺少系统依赖，可执行:"
            echo "    python -m playwright install --with-deps chromium"
            echo "    或安装系统原生 Chrome: sudo apt update && sudo apt install -y google-chrome-stable"
            echo "    若 Chrome 安装在自定义路径，请设置: export CHROME_PATH=/path/to/chrome"
        }
    else
        echo "[+] Playwright Chromium 已就绪。"
    fi
fi

# Allow dry-run verification
if [ "${1:-}" = "--dry-run" ]; then
    echo "[+] Dry-run 预检通过，已准备就绪。"
    exit 0
fi

# 5. Open Web Console if GUI desktop session is available
HOST="127.0.0.1"
PORT="8765"
CONSOLE_URL="http://${HOST}:${PORT}"

echo "======================================================================"
echo "  正在启动控制台服务: $CONSOLE_URL"
echo "  按 Ctrl+C 可停止运行"
echo "======================================================================"

if command -v xdg-open >/dev/null 2>&1 && [ -n "${DISPLAY:-${WAYLAND_DISPLAY:-}}" ]; then
    (
        sleep 2
        xdg-open "$CONSOLE_URL" >/dev/null 2>&1 || true
    ) &
else
    echo "[*] 检测到无图形界面环境或未设置 DISPLAY/WAYLAND_DISPLAY (跳过 xdg-open)"
    echo "    如在远程服务器运行，可通过 SSH 端口转发访问:"
    echo "    ssh -L ${PORT}:${HOST}:${PORT} user@remote-server"
    echo "    然后在本地浏览器访问: $CONSOLE_URL"
fi

# 6. Start FastAPI application
exec python app.py
