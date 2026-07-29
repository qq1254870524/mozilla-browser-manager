#!/usr/bin/env bash
# v1 six-item smoke verify — all under /home/baoge/Mozilla
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONPATH="$ROOT/app"
export PLAYWRIGHT_BROWSERS_PATH="$ROOT/runtime/browsers"

echo "[1] Profile CRUD"
python -m mozilla_manager.cli create -n v1-smoke --country DE --engine pw_chromium --patch patchright --auto-port
ID=$(python - <<'PY'
from mozilla_manager.store import ProfileStore
print([p.id for p in ProfileStore().list() if p.name=='v1-smoke'][-1])
PY
)
test -d "$ROOT/data/profiles/$ID"
python -m mozilla_manager.cli show "$ID" >/dev/null
echo "  ok id=$ID dir=data/profiles/$ID"

echo "[2] Engines listed"
python -m mozilla_manager.cli engines >/dev/null
python -m mozilla_manager.cli create -n v1-smoke-ff --engine camoufox --country JP >/dev/null
echo "  ok chromium+camoufox"

echo "[3] Subscription / mihomo"
python -m mozilla_manager.cli sub-list | head -5
PORT=$(python - <<PY
from mozilla_manager.store import ProfileStore
print(ProfileStore().get("$ID").proxy.mihomo_port)
PY
)
python -m mozilla_manager.cli mihomo-start --port "$PORT" --sub default
echo "  ok mihomo port=$PORT"

echo "[4] Binding present"
python -m mozilla_manager.cli show "$ID" | grep -E 'timezone_id|locale|mihomo_port|latitude' | head -10

echo "[5] Check page"
python -m mozilla_manager.cli write-check-page "$ID"
test -f "$ROOT/data/profiles/$ID/check.html"
grep -q '出口 IP' "$ROOT/data/profiles/$ID/check.html"
echo "  ok check.html"

echo "[6] Export / stop / delete"
python -m mozilla_manager.cli export "$ID" >/dev/null
python -m mozilla_manager.cli stop "$ID" >/dev/null || true
python -m mozilla_manager.cli delete "$ID"
echo "  ok export+delete"

echo "V1 VERIFY PASS"
