#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/app${PYTHONPATH:+:$PYTHONPATH}"
export PLAYWRIGHT_BROWSERS_PATH="$ROOT/runtime/browsers"
export XDG_CACHE_HOME="$ROOT/runtime/cache"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
exec python -m mozilla_manager.cli "$@"
