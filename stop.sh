#!/usr/bin/env bash
# Ubuntu 一键停止 Mozilla Browser Manager
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT/runtime/mozilla-web.pid"

stop_pid() {
  local pid="$1"
  [[ -n "$pid" ]] || return 0
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.3
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "[mozilla] 已停止 pid=$pid"
  fi
}

if [[ -f "$PID_FILE" ]]; then
  stop_pid "$(cat "$PID_FILE" 2>/dev/null || true)"
  rm -f "$PID_FILE"
fi

# 兜底：按模块名清理（不误杀其它 uvicorn）
pgrep -f "python -m mozilla_manager.web" | while read -r p; do
  stop_pid "$p"
done || true

# 可选：清理本项目临时 mihomo（不碰系统其它 mihomo）
if [[ -d "$ROOT/data/nodes" ]]; then
  for f in "$ROOT/data/nodes"/mihomo-*.pid; do
    [[ -f "$f" ]] || continue
    stop_pid "$(cat "$f" 2>/dev/null || true)"
    rm -f "$f"
  done
fi

echo "[mozilla] 全部停止完成"
