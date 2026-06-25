#!/bin/bash
# Clipboard History — Launch Script
# Starts the clipboard history menu bar app in the background.

set -e

cd "$(dirname "$0")"

echo "=== 历史粘贴板 ==="
echo ""

# Ensure dependencies are installed
echo "[1/2] 检查依赖..."
pip3 install -r requirements.txt -q 2>/dev/null
echo "      依赖就绪"

# Start the app
echo "[2/2] 启动应用..."
nohup python3 clipboard_history.py > data/app.log 2>&1 &
PID=$!
echo "      已启动 (PID: $PID)"
echo ""
echo "📋 菜单栏中应出现剪贴板图标。如果没有看到，请检查 data/app.log"
echo "   停止: kill $PID"
