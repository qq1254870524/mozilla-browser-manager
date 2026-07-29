#!/usr/bin/env bash
# One-click deps for current OS (Ubuntu/WSL dev root).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ "$ROOT" != "/home/baoge/Mozilla" ]]; then
  echo "[install][ERROR] DEV root must be /home/baoge/Mozilla (got $ROOT)" >&2
  exit 1
fi
exec bash "$ROOT/scripts/bootstrap_runtime.sh" "$@"
