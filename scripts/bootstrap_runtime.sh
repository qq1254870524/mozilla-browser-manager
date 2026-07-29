#!/usr/bin/env bash
# Dual-end aware bootstrap — installs deps for *current* OS into ROOT only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ "$ROOT" != "/home/baoge/Mozilla" && "${ALLOW_ANY_ROOT:-0}" != "1" ]]; then
  # Allow Desktop copy tested under wine? On Linux force canonical unless override.
  if [[ ! -d "$ROOT/app/mozilla_manager" ]]; then
    echo "[bootstrap][ERROR] invalid ROOT=$ROOT" >&2
    exit 1
  fi
fi
echo "[bootstrap] ROOT=$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
exec python "$ROOT/scripts/install_all_deps.py" "$@"
