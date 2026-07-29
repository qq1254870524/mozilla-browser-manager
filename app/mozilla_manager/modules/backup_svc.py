"""v10 scheduled/full instance backup under data/backups (ROOT only)."""
from __future__ import annotations

import json
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mozilla_manager import db
from mozilla_manager.modules import machine_svc, notify_svc
from mozilla_manager.paths import BACKUPS_DIR, ROOT, ensure_layout, safe_resolve

_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()
_STATE: dict[str, Any] = {"every_hours": 0, "enabled": False, "keep": 10}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _state_path():
    ensure_layout()
    return safe_resolve(BACKUPS_DIR / "schedule.json")


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_STATE)


def _save_state(st: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def create_backup(*, label: str = "") -> dict[str, Any]:
    """Zip critical data dirs (not runtime browsers/cache binaries)."""
    ensure_layout()
    machine = machine_svc.get_machine()
    slug = f"backup_{machine['machine_id'][:8]}_{_now()}"
    if label:
        slug += f"_{label}"
    out = safe_resolve(BACKUPS_DIR / f"{slug}.zip")
    include_dirs = [
        "data/profiles",
        "data/app.db",
        "data/rpa",
        "data/totp",
        "data/watchdogs",
        "data/notices",
        "data/jobs",
        "data/env_packs",
        "data/fingerprints",
        "data/fleet/machine.json",
        "data/vault",  # encrypted secrets + key — physical access still sensitive
        "runtime/nodes",
        "data/exports/migrate",
    ]
    count = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "_backup_manifest.json",
            json.dumps(
                {
                    "format": "mozilla-backup-v10",
                    "created_at": _now_iso(),
                    "machine": machine,
                    "label": label,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        for rel in include_dirs:
            src = ROOT / rel
            if not src.exists():
                continue
            if src.is_file():
                zf.write(src, arcname=rel)
                count += 1
                continue
            for f in src.rglob("*"):
                if f.is_file():
                    # skip huge user-data Cache if any nested oddly
                    parts = set(f.parts)
                    if "Cache" in parts or "Code Cache" in parts or "GPUCache" in parts:
                        continue
                    arc = f.relative_to(ROOT).as_posix()
                    try:
                        zf.write(f, arcname=arc)
                        count += 1
                    except Exception:
                        pass
    machine_svc.touch_backup()
    db.audit("backup_create", detail={"path": str(out.relative_to(ROOT)), "files": count})
    notify_svc.push("backup", f"备份完成 {out.name}", level="success", detail={"files": count})
    _gc_old()
    return {"ok": True, "path": str(out.relative_to(ROOT)), "bytes": out.stat().st_size, "files": count}


def list_backups() -> dict[str, Any]:
    ensure_layout()
    rows = []
    for f in sorted(BACKUPS_DIR.glob("backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        rows.append({"name": f.name, "path": str(f.relative_to(ROOT)), "bytes": f.stat().st_size})
    return {"ok": True, "items": rows, "schedule": _load_state(), "machine": machine_svc.get_machine()}


def _gc_old() -> None:
    st = _load_state()
    keep = int(st.get("keep") or 10)
    files = sorted(BACKUPS_DIR.glob("backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    for f in files[keep:]:
        try:
            f.unlink()
        except Exception:
            pass


def configure_schedule(*, every_hours: float = 24.0, enabled: bool = True, keep: int = 10) -> dict[str, Any]:
    st = _load_state()
    st.update({"every_hours": float(every_hours), "enabled": bool(enabled), "keep": int(keep), "updated_at": _now_iso()})
    _save_state(st)
    if enabled and every_hours > 0:
        start_backup_loop()
    return {"ok": True, "schedule": st}


def _loop() -> None:
    import time

    while not _STOP.is_set():
        st = _load_state()
        if st.get("enabled") and float(st.get("every_hours") or 0) > 0:
            last = st.get("last_run_at")
            due = True
            if last:
                try:
                    last_dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    due = (datetime.now(timezone.utc) - last_dt).total_seconds() >= float(st["every_hours"]) * 3600
                except Exception:
                    due = True
            if due:
                try:
                    create_backup(label="scheduled")
                    st = _load_state()
                    st["last_run_at"] = _now_iso()
                    _save_state(st)
                except Exception:
                    pass
        _STOP.wait(60.0)


def start_backup_loop() -> dict[str, Any]:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return {"ok": True, "started": False, "alive": True}
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="backup-loop", daemon=True)
        _THREAD.start()
    return {"ok": True, "started": True, "alive": True}


def stop_backup_loop() -> dict[str, Any]:
    """Stop scheduled backup loop (client/process shutdown)."""
    _STOP.set()
    return {"ok": True, "stopping": True}
