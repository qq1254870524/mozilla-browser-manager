#!/usr/bin/env bash
# Build a portable folder dist/MozillaManager (still under this repo tree)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
pip install -r requirements-dev.txt
export PLAYWRIGHT_BROWSERS_PATH="$ROOT/runtime/browsers"
pyinstaller \
  --noconfirm \
  --clean \
  --name MozillaManager \
  --paths "$ROOT/app" \
  --add-data "$ROOT/data:data" \
  --distpath "$ROOT/dist" \
  --workpath "$ROOT/tmp/pyinstaller" \
  "$ROOT/app/mozilla_manager/cli.py"
echo "Portable build at $ROOT/dist/MozillaManager (copy runtime/ beside it as needed)"
