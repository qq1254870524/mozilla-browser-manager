"""v8 ops: dashboard, bulk diagnose, history, profile summary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mozilla_manager.paths import LOG_DIR, RPA_RUNS_DIR, ensure_layout, safe_resolve
from mozilla_manager.store import ProfileStore
from mozilla_manager.modules import jobs_svc


def dashboard() -> dict[str, Any]:
    ensure_layout()
    store = ProfileStore()
    profiles = store.list()
    running = 0
    need_relogin = 0
    by_country: dict[str, int] = {}
    by_engine: dict[str, int] = {}
    tagged = 0
    run_ids: set[str] = set()
    try:
        from mozilla_manager import runtime_registry as rr
        if hasattr(rr, "list_running"):
            raw = rr.list_running() or []
            if isinstance(raw, dict):
                run_ids = set(raw.keys())
            else:
                run_ids = set(raw)
        elif hasattr(rr, "running_ids"):
            run_ids = set(rr.running_ids() or [])
    except Exception:
        pass
    if not run_ids:
        try:
            from mozilla_manager.engines.chromium import _RUNS
            run_ids = set(_RUNS.keys())
        except Exception:
            run_ids = set()

    for p in profiles:
        # running flag may be injected by list serialization
        is_run = p.id in run_ids
        if not is_run:
            try:
                from mozilla_manager.modules import profiles as pm
                # cheap: check registry mark
                pass
            except Exception:
                pass
        if is_run:
            running += 1
        meta = p.meta or {}
        if meta.get("need_relogin") or "需重登" in (meta.get("tags") or []):
            need_relogin += 1
        if meta.get("tags"):
            tagged += 1
        cc = meta.get("expected_country") or "?"
        by_country[cc] = by_country.get(cc, 0) + 1
        eng = getattr(p.engine, "value", None) or str(p.engine)
        by_engine[eng] = by_engine.get(eng, 0) + 1

    packs_n = 0
    try:
        from mozilla_manager.env_packs import list_packs

        packs_n = len(list_packs())
    except Exception:
        pass

    jobs = jobs_svc.list_jobs(limit=8)
    notices_unread = 0
    locked_n = 0
    wd = {"count": 0, "alive": False}
    machine = {}
    try:
        from mozilla_manager.modules import notify_svc, lock_svc, watchdog_svc, machine_svc
        notices_unread = notify_svc.list_notices(limit=1).get("unread") or 0
        locked_n = len(lock_svc.list_locked())
        wd = watchdog_svc.status()
        machine = machine_svc.get_machine()
    except Exception:
        pass
    return {
        "ok": True,
        "version": "1.10.10-v10.10",
        "profiles": len(profiles),
        "running": running,
        "need_relogin": need_relogin,
        "tagged": tagged,
        "packs": packs_n,
        "by_country": dict(sorted(by_country.items(), key=lambda x: -x[1])[:20]),
        "by_engine": by_engine,
        "recent_jobs": jobs,
        "notices_unread": notices_unread,
        "locked": locked_n,
        "watchdogs": wd,
        "machine_id": machine.get("machine_id"),
        "machine_name": machine.get("name"),
    }


def profile_summary(profile_id: str) -> dict[str, Any]:
    p = ProfileStore().get(profile_id)
    d = p.model_dump(mode="json")
    return {
        "ok": True,
        "id": p.id,
        "name": p.name,
        "engine": getattr(p.engine, "value", None) or str(p.engine),
        "patch": getattr(p.chromium_patch, "value", None) or str(p.chromium_patch),
        "proxy": d.get("proxy"),
        "env": d.get("env"),
        "meta": {
            "group": (p.meta or {}).get("group"),
            "tags": (p.meta or {}).get("tags") or [],
            "expected_country": (p.meta or {}).get("expected_country"),
            "need_relogin": (p.meta or {}).get("need_relogin"),
            "webrtc_mode": (p.meta or {}).get("webrtc_mode"),
            "doh_mode": (p.meta or {}).get("doh_mode"),
            "enable_virtual_media": (p.meta or {}).get("enable_virtual_media"),
        },
        "clipboard": (
            f"{p.name} | {p.id} | {(p.meta or {}).get('expected_country') or '-'} | "
            f"{(p.env.timezone_id if p.env else '')} | {(p.env.locale if p.env else '')}"
        ),
    }


def bulk_diagnose(profile_ids: list[str] | None = None, samples: int = 3, async_job: bool = True) -> dict[str, Any]:
    ids = list(profile_ids or [])
    if not ids:
        ids = [p.id for p in ProfileStore().list()]

    def _fn(job: dict[str, Any]) -> dict[str, Any]:
        from mozilla_manager.network.diagnose import diagnose_profile
        from mozilla_manager.modules import jobs_svc

        results = []
        ok_n = 0
        total = max(len(ids), 1)
        jid = job.get("id")
        for i, pid in enumerate(ids):
            if jid:
                try:
                    jobs_svc.set_progress(jid, current=i, total=total, message=f"diagnose {pid}")
                except Exception:
                    pass
            try:
                r = diagnose_profile(pid, samples=samples)
                results.append({"profile_id": pid, "ok": bool(r.get("ok")), "summary": r.get("summary") or r.get("ok")})
                if r.get("ok"):
                    ok_n += 1
            except Exception as e:
                results.append({"profile_id": pid, "ok": False, "error": str(e)})
        if jid:
            try:
                jobs_svc.set_progress(jid, current=total, total=total, message="done")
            except Exception:
                pass
        return {
            "ok": ok_n == len(ids),
            "summary": f"diagnose {ok_n}/{len(ids)} ok",
            "total": len(ids),
            "passed": ok_n,
            "results": results,
        }

    if async_job:
        return jobs_svc.submit("bulk_diagnose", payload={"profile_ids": ids, "samples": samples}, fn=_fn)
    return _fn({"id": "sync"})


def history(limit: int = 30) -> dict[str, Any]:
    ensure_layout()
    rpa_runs = []
    for f in sorted(RPA_RUNS_DIR.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            rep = json.loads(f.read_text(encoding="utf-8"))
            rpa_runs.append(
                {
                    "run_id": rep.get("run_id") or f.parent.name,
                    "workflow_id": rep.get("workflow_id"),
                    "profile_id": rep.get("profile_id"),
                    "ok": rep.get("ok"),
                    "started_at": rep.get("started_at"),
                    "steps": len(rep.get("steps") or []),
                }
            )
        except Exception:
            continue

    diagnoses = []
    ddir = safe_resolve(LOG_DIR / "diagnose")
    if ddir.exists():
        for f in sorted(ddir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                rep = json.loads(f.read_text(encoding="utf-8"))
                diagnoses.append(
                    {
                        "file": str(f.relative_to(f.parents[2])) if False else f.name,
                        "profile_id": rep.get("profile_id"),
                        "ok": rep.get("ok"),
                        "at": rep.get("at"),
                    }
                )
            except Exception:
                continue

    return {
        "ok": True,
        "rpa_runs": rpa_runs,
        "diagnoses": diagnoses,
        "jobs": jobs_svc.list_jobs(limit=limit),
    }
