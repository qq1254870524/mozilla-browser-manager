#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONPATH="$ROOT/app"
export PLAYWRIGHT_BROWSERS_PATH="$ROOT/runtime/browsers"
export XDG_CACHE_HOME="$ROOT/runtime/cache"
exec python -m mozilla_manager.web
