"""v10 machine identity for fleet sync."""
from __future__ import annotations

import json
import platform
import uuid
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import FLEET_DIR, ROOT, ensure_layout, safe_resolve


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path():
    ensure_layout()
    return safe_resolve(FLEET_DIR / "machine.json")


def get_machine() -> dict[str, Any]:
    path = _path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    mid = uuid.uuid4().hex[:16]
    row = {
        "machine_id": mid,
        "name": platform.node() or "mozilla-host",
        "platform": platform.platform(),
        "system": platform.system(),
        "root": str(ROOT),
        "created_at": _now(),
        "updated_at": _now(),
        "last_sync_at": None,
        "last_backup_at": None,
    }
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def touch_sync() -> dict[str, Any]:
    row = get_machine()
    row["last_sync_at"] = _now()
    row["updated_at"] = _now()
    _path().write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def touch_backup() -> dict[str, Any]:
    row = get_machine()
    row["last_backup_at"] = _now()
    row["updated_at"] = _now()
    _path().write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def set_name(name: str) -> dict[str, Any]:
    row = get_machine()
    row["name"] = name.strip() or row["name"]
    row["updated_at"] = _now()
    _path().write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row
