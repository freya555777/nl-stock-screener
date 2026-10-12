#!/usr/bin/env bash
# 选股意图解释器 · 一键启动 (macOS / Linux)
set -e
cd "$(dirname "$0")"
echo "[1/2] 检查依赖..."
python3 -c "import flask" 2>/dev/null || python3 -m pip install -r requirements.txt
echo "[2/2] 启动服务: http://127.0.0.1:8000"
python3 app.py
