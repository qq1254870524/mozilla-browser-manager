"""In-memory + on-disk + SQLite run registry with live process reconcile."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from . import db
from .paths import ensure_layout, p, safe_resolve

_REG = p("data", "runtime_registry.json")
_META_KEYS = {"browsers", "updated_at"}
_WATCH_STARTED = False
_WATCH_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load() -> dict[str, Any]:
    ensure_layout()
    path = safe_resolve(_REG)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _save(data: dict[str, Any]) -> None:
    path = safe_resolve(_REG)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_started(profile_id: str, info: dict[str, Any] | None = None) -> None:
    data = _load()
    data[profile_id] = {"started_at": _now(), **(info or {})}
    _save(data)
    try:
        db.set_run_state(
            profile_id,
            running=True,
            driver=(info or {}).get("driver"),
            extra=info or {},
        )
        db.audit("launch", profile_id, info or {})
        db.save_last_session([k for k, v in data.items() if isinstance(v, dict) and k not in _META_KEYS])
    except Exception:
        pass
    ensure_watchdog()


def mark_stopped(profile_id: str) -> None:
    data = _load()
    data.pop(profile_id, None)
    _save(data)
    try:
        db.set_run_state(profile_id, running=False)
        db.audit("stop", profile_id, {})
        db.save_last_session([k for k, v in data.items() if isinstance(v, dict) and k not in _META_KEYS])
    except Exception:
        pass


def _engine_live_ids() -> set[str]:
    """Ask engine modules which profile contexts are still alive."""
    live: set[str] = set()
    for mod_name in ("mozilla_manager.engines.chromium", "mozilla_manager.engines.camoufox_engine"):
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, "live_profile_ids", None)
            if callable(fn):
                live |= set(fn() or [])
                continue
            # fallback: inspect _RUNS
            runs = getattr(mod, "_RUNS", None) or {}
            lock = getattr(mod, "_LOCK", None)
            is_alive = getattr(mod, "is_run_alive", None)
            items = []
            if lock is not None:
                with lock:
                    items = list(runs.items())
            else:
                items = list(runs.items())
            for pid, run in items:
                ok = True
                if callable(is_alive):
                    ok = bool(is_alive(run))
                if ok:
                    live.add(pid)
        except Exception:
            continue
    return live


def reconcile_running(*, drop_missing_profiles: bool = True, check_live: bool = True) -> dict[str, Any]:
    """Drop registry entries that are stale (profile gone OR browser already closed)."""
    data = _load()
    changed = False
    live = _engine_live_ids() if check_live else None

    for pid in list(data.keys()):
        if pid in _META_KEYS:
            continue
        if not isinstance(data.get(pid), dict):
            data.pop(pid, None)
            changed = True
            continue
        # profile truth missing
        try:
            prof = safe_resolve(p("data", "profiles", pid))
            if drop_missing_profiles and not (prof / "profile.json").exists():
                data.pop(pid, None)
                changed = True
                try:
                    db.set_run_state(pid, running=False)
                except Exception:
                    pass
                continue
        except Exception:
            data.pop(pid, None)
            changed = True
            continue

        # browser no longer alive in this process → stop marker
        if live is not None and pid not in live:
            data.pop(pid, None)
            changed = True
            try:
                db.set_run_state(pid, running=False)
                db.audit("auto_stop", pid, {"reason": "browser_gone"})
            except Exception:
                pass
            # best-effort free worker / mihomo leftovers
            try:
                from mozilla_manager.engines.sync_bridge import drop_worker
                drop_worker(pid)
            except Exception:
                pass
            try:
                from mozilla_manager.store import ProfileStore
                from mozilla_manager.modules import mihomo_svc
                prof_o = ProfileStore().get(pid)
                port = getattr(prof_o.proxy, "mihomo_port", None)
                if port and getattr(prof_o.proxy, "mode", None) == "mihomo":
                    # only stop if nothing else claims live — already not live
                    mihomo_svc.stop(int(port))
            except Exception:
                pass

    if changed:
        _save(data)
        try:
            keys = [k for k, v in data.items() if isinstance(v, dict) and k not in _META_KEYS]
            db.save_last_session(keys)
        except Exception:
            pass
    # strip meta for API consumers expecting profile_id -> info
    return {k: v for k, v in data.items() if isinstance(v, dict) and k not in _META_KEYS}


def list_running() -> dict[str, Any]:
    ensure_watchdog()
    return reconcile_running(check_live=True)


def ensure_watchdog(interval: float = 3.0) -> None:
    """Background reconcile so manual browser close flips UI without clicking 停止."""
    global _WATCH_STARTED
    with _WATCH_LOCK:
        if _WATCH_STARTED:
            return
        _WATCH_STARTED = True

    def _loop() -> None:
        import time
        while True:
            try:
                reconcile_running(check_live=True)
            except Exception:
                pass
            time.sleep(interval)

    threading.Thread(target=_loop, name="mm-runtime-watch", daemon=True).start()
