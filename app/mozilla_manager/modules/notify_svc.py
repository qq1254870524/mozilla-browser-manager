"""v9 notification center — file-backed, ROOT-locked."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import NOTICES_DIR, ensure_layout, safe_resolve

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path():
    ensure_layout()
    return safe_resolve(NOTICES_DIR / "notices.json")


def _load() -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("items") or [])
    except Exception:
        return []


def _save(items: list[dict[str, Any]]) -> None:
    # keep last 500
    items = items[-500:]
    _path().write_text(json.dumps({"items": items, "updated_at": _now()}, ensure_ascii=False, indent=2), encoding="utf-8")


def push(
    kind: str,
    title: str,
    *,
    level: str = "info",
    profile_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "title": title,
        "level": level,  # info|warn|error|success
        "profile_id": profile_id,
        "detail": detail or {},
        "read": False,
        "created_at": _now(),
    }
    with _LOCK:
        items = _load()
        items.append(row)
        _save(items)
    try:
        from mozilla_manager import db

        db.audit("notify", profile_id, {"kind": kind, "title": title, "level": level})
    except Exception:
        pass
    return row


def list_notices(limit: int = 50, unread_only: bool = False) -> dict[str, Any]:
    with _LOCK:
        items = _load()
    items = list(reversed(items))
    if unread_only:
        items = [x for x in items if not x.get("read")]
    items = items[:limit]
    unread = sum(1 for x in _load() if not x.get("read"))
    return {"ok": True, "items": items, "unread": unread, "total": len(_load())}


def mark_read(ids: list[str] | None = None, all_: bool = False) -> dict[str, Any]:
    with _LOCK:
        items = _load()
        n = 0
        idset = set(ids or [])
        for x in items:
            if all_ or x.get("id") in idset:
                if not x.get("read"):
                    x["read"] = True
                    n += 1
        _save(items)
    return {"ok": True, "marked": n}


def clear(read_only: bool = True) -> dict[str, Any]:
    with _LOCK:
        items = _load()
        if read_only:
            items = [x for x in items if not x.get("read")]
        else:
            items = []
        _save(items)
    return {"ok": True, "remaining": len(items)}
