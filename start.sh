#!/usr/bin/env bash
# Ubuntu 一键启动 Mozilla Browser Manager（Web 管理台）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PID_FILE="$ROOT/runtime/mozilla-web.pid"
LOG_FILE="$ROOT/logs/mozilla-web.log"
mkdir -p "$ROOT/logs" "$ROOT/runtime" "$ROOT/runtime/cache"

if [[ -f "$PID_FILE" ]]; then
  old="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${old:-}" ]] && kill -0 "$old" 2>/dev/null; then
    echo "[mozilla] 已在运行 pid=$old  →  http://127.0.0.1:17888/"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONPATH="$ROOT/app"
export PLAYWRIGHT_BROWSERS_PATH="$ROOT/runtime/browsers"
export XDG_CACHE_HOME="$ROOT/runtime/cache"

# 避免与前台占用冲突：后台启动
nohup python -m mozilla_manager.web >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
sleep 1
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[mozilla] 启动成功 pid=$(cat "$PID_FILE")"
  echo "[mozilla] 打开: http://127.0.0.1:17888/"
  echo "[mozilla] 日志: $LOG_FILE"
  echo "[mozilla] 停止: $ROOT/stop.sh"
else
  echo "[mozilla] 启动失败，查看日志: $LOG_FILE" >&2
  tail -30 "$LOG_FILE" >&2 || true
  exit 1
fi
