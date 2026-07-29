#!/usr/bin/env bash
# Install Camoufox from local zip OR download with mirrors+resume into ROOT only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY=python3
fi
export XDG_CACHE_HOME="$ROOT/runtime/cache"
if [[ "${1:-}" != "" && -f "${1:-}" ]]; then
  exec "$PY" "$ROOT/scripts/fetch_camoufox.py" --zip "$1"
fi
exec "$PY" "$ROOT/scripts/fetch_camoufox.py" "$@"
