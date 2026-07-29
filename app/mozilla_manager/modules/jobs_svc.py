"""Simple in-process job center (v8). All under data/jobs/."""
from __future__ import annotations

import json
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mozilla_manager.paths import JOBS_DIR, LOG_DIR, ensure_layout, safe_resolve

_LOCK = threading.Lock()
_THREADS: dict[str, threading.Thread] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path(job_id: str) -> Path:
    ensure_layout()
    return safe_resolve(JOBS_DIR / f"{job_id}.json")


def _save(job: dict[str, Any]) -> dict[str, Any]:
    path = _path(job["id"])
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def _load(job_id: str) -> dict[str, Any]:
    path = _path(job_id)
    if not path.exists():
        raise KeyError(job_id)
    return json.loads(path.read_text(encoding="utf-8"))


def set_progress(job_id: str, *, current: int, total: int, message: str = "") -> dict[str, Any]:
    j = _load(job_id)
    total = max(int(total), 1)
    current = max(0, min(int(current), total))
    j["progress"] = {
        "current": current,
        "total": total,
        "pct": round(100.0 * current / total, 1),
        "message": message,
        "updated_at": _now(),
    }
    return _save(j)


def reap_stale(max_age_sec: float = 600.0) -> dict[str, Any]:
    """Mark running/pending jobs older than max_age as error (orphaned workers)."""
    ensure_layout()
    n = 0
    now = datetime.now(timezone.utc)
    for f in JOBS_DIR.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if j.get("status") not in ("running", "pending"):
            continue
        started = j.get("started_at") or j.get("created_at")
        if not started:
            continue
        try:
            ts = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if (now - ts).total_seconds() > max_age_sec:
            j["status"] = "error"
            j["ok"] = False
            j["error"] = j.get("error") or "stale/orphaned job worker"
            j["summary"] = "stale"
            j["finished_at"] = _now()
            f.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
            n += 1
    return {"ok": True, "reaped": n}


def list_jobs(limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
    try:
        reap_stale(600)
    except Exception:
        pass
    ensure_layout()
    rows = []
    for f in sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if kind and j.get("kind") != kind:
            continue
        rows.append(
            {
                "id": j.get("id"),
                "kind": j.get("kind"),
                "status": j.get("status"),
                "created_at": j.get("created_at"),
                "finished_at": j.get("finished_at"),
                "ok": j.get("ok"),
                "summary": j.get("summary"),
                "progress": j.get("progress"),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def get_job(job_id: str) -> dict[str, Any]:
    return _load(job_id)


def submit(kind: str, payload: dict[str, Any] | None = None, fn: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
    """Submit a background job. `fn` receives the job dict and returns result."""
    ensure_layout()
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "kind": kind,
        "status": "pending",
        "payload": payload or {},
        "result": None,
        "error": None,
        "ok": None,
        "summary": None,
        "progress": {"current": 0, "total": 1, "pct": 0.0, "message": "queued"},
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
    }
    _save(job)

    def _run():
        j = _load(job_id)
        j["status"] = "running"
        j["started_at"] = _now()
        _save(j)
        try:
            if fn is None:
                raise RuntimeError("no job function")
            result = fn(j)
            j = _load(job_id)
            j["status"] = "done"
            j["ok"] = True if not isinstance(result, dict) else bool(result.get("ok", True))
            j["result"] = result
            if isinstance(result, dict):
                j["summary"] = result.get("summary") or result.get("message") or f"ok={j['ok']}"
            else:
                j["summary"] = "done"
            j["finished_at"] = _now()
            _save(j)
        except Exception as e:
            j = _load(job_id)
            j["status"] = "error"
            j["ok"] = False
            j["error"] = str(e)
            j["summary"] = str(e)
            j["traceback"] = traceback.format_exc()[-2000:]
            j["finished_at"] = _now()
            _save(j)
        try:
            log = safe_resolve(LOG_DIR / "jobs" / f"{job_id}.json")
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(json.dumps(_load(job_id), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        try:
            from mozilla_manager import db

            db.audit("job_done", detail={"id": job_id, "kind": kind, "ok": j.get("ok")})
        except Exception:
            pass
        try:
            from mozilla_manager.modules import notify_svc
            lvl = "success" if j.get("ok") else "error"
            notify_svc.push(
                "job",
                f"任务{'完成' if j.get('ok') else '失败'}: {kind} ({job_id})",
                level=lvl,
                detail={"id": job_id, "kind": kind, "summary": j.get("summary")},
            )
        except Exception:
            pass

    th = threading.Thread(target=_run, name=f"job-{job_id}", daemon=True)
    with _LOCK:
        _THREADS[job_id] = th
    th.start()
    return {"ok": True, "id": job_id, "kind": kind, "status": "pending"}
