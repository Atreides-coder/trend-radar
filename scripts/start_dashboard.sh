#!/bin/bash
# 启动 Trend Radar Dashboard（本地）。用法：./scripts/start_dashboard.sh   端口可用 PORT=9000 覆盖
set -e
cd "$(dirname "$0")/.."
PORT="${PORT:-8765}"

if [ ! -x .venv/bin/python ]; then
  echo "找不到 .venv，请先按 README 安装依赖。" >&2
  exit 1
fi

# 前端没构建过，或源码比构建产物新时，重新构建
if [ ! -f dashboard/dist/index.html ] || \
   [ -n "$(find dashboard/src dashboard/index.html -newer dashboard/dist/index.html -print -quit)" ]; then
  if ! command -v npm >/dev/null; then
    echo "需要 Node.js / npm 来构建前端（只在第一次或前端代码改动后需要）。" >&2
    exit 1
  fi
  echo "构建前端…"
  (cd dashboard && { [ -d node_modules ] || npm install --silent; } && npm run build --silent)
fi

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "端口 $PORT 已被占用——Dashboard 可能已经在运行： http://localhost:$PORT" >&2
  echo "换端口： PORT=9000 ./scripts/start_dashboard.sh" >&2
  exit 1
fi

echo "Trend Radar Dashboard: http://localhost:$PORT   （Ctrl+C 停止）"
# NO_OPEN=1 时不自动打开浏览器
[ -n "$NO_OPEN" ] || (sleep 1.5 && open "http://localhost:$PORT") >/dev/null 2>&1 &
exec .venv/bin/python -m uvicorn src.dashboard.api:app --host 127.0.0.1 --port "$PORT" --log-level warning
