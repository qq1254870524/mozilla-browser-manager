"""v9 profile locks — prevent concurrent destructive/launch ops."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import ensure_layout, p, safe_resolve
from mozilla_manager.store import ProfileStore

_LOCK = threading.Lock()
_MEM: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _disk(profile_id: str):
    ensure_layout()
    d = safe_resolve(p("data", "profiles", profile_id))
    d.mkdir(parents=True, exist_ok=True)
    return d / "lock.json"


def is_locked(profile_id: str) -> dict[str, Any]:
    with _LOCK:
        mem = _MEM.get(profile_id)
    if mem and mem.get("locked"):
        # expire?
        exp = float(mem.get("expires_at_epoch") or 0)
        if exp and time.time() > exp:
            unlock(profile_id, force=True)
            return {"locked": False, "profile_id": profile_id}
        return {"locked": True, "profile_id": profile_id, **{k: mem.get(k) for k in ("reason", "owner", "locked_at", "expires_at")}}
    path = _disk(profile_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            exp = float(data.get("expires_at_epoch") or 0)
            if exp and time.time() > exp:
                unlock(profile_id, force=True)
                return {"locked": False, "profile_id": profile_id}
            if data.get("locked"):
                with _LOCK:
                    _MEM[profile_id] = data
                return {"locked": True, "profile_id": profile_id, **data}
        except Exception:
            pass
    return {"locked": False, "profile_id": profile_id}


def lock(profile_id: str, *, reason: str = "manual", owner: str = "ui", ttl_sec: int = 3600) -> dict[str, Any]:
    ProfileStore().get(profile_id)
    cur = is_locked(profile_id)
    if cur.get("locked"):
        return {"ok": False, "error": "already locked", **cur}
    exp = time.time() + max(60, int(ttl_sec))
    row = {
        "locked": True,
        "profile_id": profile_id,
        "reason": reason,
        "owner": owner,
        "locked_at": _now(),
        "expires_at": datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at_epoch": exp,
    }
    with _LOCK:
        _MEM[profile_id] = row
    _disk(profile_id).write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    # mirror meta
    try:
        store = ProfileStore()
        prof = store.get(profile_id)
        meta = dict(prof.meta)
        meta["locked"] = True
        meta["lock"] = {"reason": reason, "owner": owner, "locked_at": row["locked_at"]}
        store.update(profile_id, meta=meta)
    except Exception:
        pass
    return {"ok": True, **row}


def unlock(profile_id: str, *, force: bool = False) -> dict[str, Any]:
    with _LOCK:
        _MEM.pop(profile_id, None)
    path = _disk(profile_id)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            path.write_text(json.dumps({"locked": False}, indent=2), encoding="utf-8")
    try:
        store = ProfileStore()
        prof = store.get(profile_id)
        meta = dict(prof.meta)
        meta["locked"] = False
        meta.pop("lock", None)
        store.update(profile_id, meta=meta)
    except Exception:
        pass
    return {"ok": True, "profile_id": profile_id, "locked": False, "force": force}


def require_unlocked(profile_id: str) -> None:
    st = is_locked(profile_id)
    if st.get("locked"):
        raise RuntimeError(f"profile locked: {profile_id} reason={st.get('reason')}")


def list_locked() -> list[dict[str, Any]]:
    rows = []
    for p in ProfileStore().list():
        st = is_locked(p.id)
        if st.get("locked"):
            rows.append(st)
    return rows
