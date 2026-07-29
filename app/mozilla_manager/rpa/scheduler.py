"""Simple in-process RPA scheduler (interval / cron-ish HH:MM)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import RPA_SCHEDULES_DIR, ensure_layout, safe_resolve

from .runner import run_workflow

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sched_path() -> Any:
    ensure_layout()
    return safe_resolve(RPA_SCHEDULES_DIR / "schedules.json")


def list_schedules() -> list[dict[str, Any]]:
    path = _sched_path()
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("items") or [])
    except Exception:
        return []


def _save(items: list[dict[str, Any]]) -> None:
    path = _sched_path()
    path.write_text(json.dumps({"updated_at": _now(), "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_schedule(
    *,
    schedule_id: str,
    workflow_id: str,
    profile_id: str,
    every_minutes: int | None = None,
    daily_at: str | None = None,  # "HH:MM" local
    enabled: bool = True,
    headless: bool = True,
) -> dict[str, Any]:
    items = list_schedules()
    items = [x for x in items if x.get("id") != schedule_id]
    row = {
        "id": schedule_id,
        "workflow_id": workflow_id,
        "profile_id": profile_id,
        "every_minutes": every_minutes,
        "daily_at": daily_at,
        "enabled": enabled,
        "headless": headless,
        "last_run_at": None,
        "last_ok": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    items.append(row)
    _save(items)
    return row


def remove_schedule(schedule_id: str) -> dict[str, Any]:
    items = list_schedules()
    n = len(items)
    items = [x for x in items if x.get("id") != schedule_id]
    _save(items)
    return {"ok": True, "removed": n - len(items)}


def _due(item: dict[str, Any], now: datetime) -> bool:
    if not item.get("enabled", True):
        return False
    last = item.get("last_run_at")
    every = item.get("every_minutes")
    daily = item.get("daily_at")
    if every:
        if not last:
            return True
        try:
            # last is Zulu
            ts = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            return (now - ts).total_seconds() >= int(every) * 60
        except Exception:
            return True
    if daily:
        hhmm = str(daily)
        try:
            local = datetime.now().strftime("%H:%M")
            if local != hhmm:
                return False
            if last and str(last)[:10] == now.strftime("%Y-%m-%d"):
                return False
            return True
        except Exception:
            return False
    return False


def tick_once() -> list[dict[str, Any]]:
    """Check schedules and run due workflows."""
    now = datetime.now(timezone.utc)
    items = list_schedules()
    results = []
    changed = False
    for item in items:
        if not _due(item, now):
            continue
        try:
            rep = run_workflow(
                item["workflow_id"],
                profile_id=item.get("profile_id"),
                headless=bool(item.get("headless", True)),
            )
            item["last_run_at"] = _now()
            item["last_ok"] = bool(rep.get("ok"))
            item["last_run_id"] = rep.get("run_id")
            results.append({"schedule_id": item["id"], "ok": rep.get("ok"), "run_id": rep.get("run_id")})
        except Exception as e:
            item["last_run_at"] = _now()
            item["last_ok"] = False
            item["last_error"] = str(e)
            results.append({"schedule_id": item["id"], "ok": False, "error": str(e)})
        changed = True
    if changed:
        _save(items)
    return results


def _loop(interval: float = 30.0) -> None:
    while not _STOP.is_set():
        try:
            with _LOCK:
                tick_once()
        except Exception:
            pass
        _STOP.wait(interval)


def start_scheduler(interval: float = 30.0) -> dict[str, Any]:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return {"ok": True, "running": True, "reused": True}
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, kwargs={"interval": interval}, name="mozilla-rpa-scheduler", daemon=True)
        _THREAD.start()
        return {"ok": True, "running": True, "reused": False}


def stop_scheduler() -> dict[str, Any]:
    _STOP.set()
    return {"ok": True, "stopping": True}
