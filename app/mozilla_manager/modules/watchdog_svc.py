"""v9 watchdog: schedule login-check / diagnose / custom hooks."""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import WATCHDOGS_DIR, LOG_DIR, ensure_layout, safe_resolve
from mozilla_manager.modules import notify_svc, jobs_svc

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path():
    ensure_layout()
    return safe_resolve(WATCHDOGS_DIR / "watchdogs.json")


def _load() -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("items") or [])
    except Exception:
        return []


def _save(items: list[dict[str, Any]]) -> None:
    _path().write_text(json.dumps({"items": items, "updated_at": _now()}, ensure_ascii=False, indent=2), encoding="utf-8")


def list_watchdogs() -> list[dict[str, Any]]:
    with _LOCK:
        return _load()


def upsert(
    *,
    watchdog_id: str | None = None,
    kind: str = "login_check",  # login_check | diagnose | net_quality
    profile_id: str,
    every_minutes: int | None = 60,
    daily_at: str | None = None,
    enabled: bool = True,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _LOCK:
        items = _load()
        wid = watchdog_id or f"wd-{uuid.uuid4().hex[:8]}"
        row = None
        for it in items:
            if it.get("id") == wid:
                row = it
                break
        if row is None:
            row = {"id": wid, "created_at": _now()}
            items.append(row)
        row.update(
            {
                "id": wid,
                "kind": kind,
                "profile_id": profile_id,
                "every_minutes": every_minutes,
                "daily_at": daily_at,
                "enabled": enabled,
                "params": params or {},
                "updated_at": _now(),
                "last_run_at": row.get("last_run_at"),
                "last_ok": row.get("last_ok"),
                "last_error": row.get("last_error"),
            }
        )
        _save(items)
    start_watchdog_loop()
    return row


def remove(watchdog_id: str) -> dict[str, Any]:
    with _LOCK:
        items = _load()
        n = len(items)
        items = [x for x in items if x.get("id") != watchdog_id]
        _save(items)
    return {"ok": True, "removed": n - len(items), "id": watchdog_id}


def _due(row: dict[str, Any], now: datetime) -> bool:
    if not row.get("enabled"):
        return False
    last = row.get("last_run_at")
    last_dt = None
    if last:
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            last_dt = None
    every = row.get("every_minutes")
    daily = row.get("daily_at")
    if every:
        if last_dt is None:
            return True
        return (now - last_dt).total_seconds() >= float(every) * 60
    if daily:
        try:
            hh, mm = str(daily).split(":")[:2]
            target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except Exception:
            return False
        if last_dt and last_dt.date() == now.date():
            return False
        return now >= target
    return False


def _run_one(row: dict[str, Any]) -> dict[str, Any]:
    kind = row.get("kind")
    pid = row.get("profile_id")
    params = row.get("params") or {}
    result: dict[str, Any]
    if kind == "login_check":
        from mozilla_manager.modules import login_health

        result = login_health.check_login(pid, headless=bool(params.get("headless", True)))
        if result.get("need_relogin"):
            notify_svc.push(
                "login_watch",
                f"需重登: {pid}",
                level="warn",
                profile_id=pid,
                detail=result,
            )
        elif result.get("ok"):
            notify_svc.push("login_watch", f"登录态正常: {pid}", level="success", profile_id=pid, detail={"ok": True})
        else:
            notify_svc.push("login_watch", f"登录巡检失败: {pid}", level="error", profile_id=pid, detail=result)
    elif kind == "diagnose":
        from mozilla_manager.network.diagnose import diagnose_profile

        result = diagnose_profile(pid, samples=int(params.get("samples") or 2))
        if not result.get("ok"):
            notify_svc.push("diagnose", f"诊断异常: {pid}", level="error", profile_id=pid, detail=result.get("summary") or {})
            # auto-heal: try failover once
            if params.get("auto_failover"):
                try:
                    from mozilla_manager.modules import failover as failover_mod

                    fr = failover_mod.auto_failover(pid)
                    result["failover"] = fr
                    notify_svc.push("failover", f"自动切节点: {pid}", level="warn", profile_id=pid, detail=fr)
                except Exception as e:
                    result["failover_error"] = str(e)
        else:
            notify_svc.push("diagnose", f"诊断通过: {pid}", level="success", profile_id=pid)
    elif kind == "net_quality":
        from mozilla_manager.modules import stealth_svc

        result = stealth_svc.net_quality_for_profile(pid, samples=int(params.get("samples") or 3))
        if not result.get("ok"):
            notify_svc.push("net_quality", f"网络质量差: {pid}", level="warn", profile_id=pid, detail=result)
    else:
        result = {"ok": False, "error": f"unknown kind {kind}"}
    return result


def tick_once() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    ran = []
    with _LOCK:
        items = _load()
    for row in items:
        if not _due(row, now):
            continue
        try:
            result = _run_one(row)
            ok = bool(result.get("ok"))
            err = None if ok else (result.get("error") or result.get("message") or "failed")
        except Exception as e:
            result = {"ok": False, "error": str(e)}
            ok = False
            err = str(e)
        with _LOCK:
            items2 = _load()
            for it in items2:
                if it.get("id") == row.get("id"):
                    it["last_run_at"] = _now()
                    it["last_ok"] = ok
                    it["last_error"] = err
                    it["last_result_summary"] = {
                        "ok": ok,
                        "keys": list(result.keys())[:12] if isinstance(result, dict) else [],
                    }
            _save(items2)
        ran.append({"id": row.get("id"), "ok": ok, "kind": row.get("kind"), "profile_id": row.get("profile_id")})
        try:
            log = safe_resolve(LOG_DIR / "watchdogs" / f"{row.get('id')}_{int(time.time())}.json")
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(json.dumps({"row": row, "result": result}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return ran


def _loop(interval: float = 30.0) -> None:
    while not _STOP.is_set():
        try:
            tick_once()
        except Exception:
            pass
        _STOP.wait(interval)


def start_watchdog_loop(interval: float = 30.0) -> dict[str, Any]:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return {"ok": True, "started": False, "alive": True}
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, kwargs={"interval": interval}, name="watchdog-loop", daemon=True)
        _THREAD.start()
    return {"ok": True, "started": True, "interval": interval}


def stop_watchdog_loop() -> dict[str, Any]:
    """Stop background watchdog loop (client/process shutdown)."""
    _STOP.set()
    return {"ok": True, "stopping": True}


def status() -> dict[str, Any]:
    alive = bool(_THREAD and _THREAD.is_alive())
    items = list_watchdogs()
    return {"ok": True, "alive": alive, "count": len(items), "enabled": sum(1 for x in items if x.get("enabled"))}
