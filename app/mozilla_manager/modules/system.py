"""System module: boot, health, layout, GC, sandbox."""
from __future__ import annotations

from typing import Any

from mozilla_manager import db
from mozilla_manager.consistency import check_consistency
from mozilla_manager.env_packs import seed_packs
from mozilla_manager.fingerprints import seed_fingerprints
from mozilla_manager.paths import ROOT, ensure_layout
from mozilla_manager.tmp_gc import enforce_no_home_writes, gc_tmp


def boot() -> dict[str, Any]:
    ensure_layout()
    db.init_db()
    seed_packs()
    seed_fingerprints()
    env = enforce_no_home_writes()
    # v5 migrate nodes to runtime/nodes
    try:
        from mozilla_manager.network.node_store import migrate_legacy_to_runtime
        migrate_legacy_to_runtime()
    except Exception:
        pass
    # v7: re-seed packs to pick global countries; start RPA scheduler
    try:
        seed_packs(force=False)
    except Exception:
        pass
    try:
        from mozilla_manager.rpa.scheduler import start_scheduler
        start_scheduler(interval=30.0)
    except Exception:
        pass
    # v9: watchdog loop (login/diagnose schedules)
    try:
        from mozilla_manager.modules.watchdog_svc import start_watchdog_loop
        start_watchdog_loop(interval=30.0)
    except Exception:
        pass
    # v10 machine id + backup schedule loop
    try:
        from mozilla_manager.modules import machine_svc, backup_svc
        machine_svc.get_machine()
        stcfg = backup_svc._load_state()
        if stcfg.get("enabled"):
            backup_svc.start_backup_loop()
    except Exception:
        pass
    # sync existing profiles into sqlite index (non-destructive)
    try:
        from mozilla_manager.store import ProfileStore

        for prof in ProfileStore().list():
            db.upsert_profile_row(prof)
    except Exception:
        pass
    return {"ok": True, "root": str(ROOT), "sandbox": env}


def health() -> dict[str, Any]:
    return {
        "ok": True,
        "root": str(ROOT),
        "module": "system",
        "version": "1.10.8-v10.7",
        "db": str(db.db_path()),
    }


def gc(max_age_hours: float = 24.0, dry_run: bool = False) -> dict[str, Any]:
    tmp = gc_tmp(max_age_hours=max_age_hours, dry_run=dry_run)
    mihomo = {"ok": False, "skipped": True}
    try:
        from mozilla_manager.modules import mihomo_svc
        mihomo = mihomo_svc.cleanup_orphans(dry_run=dry_run)
    except Exception as e:
        mihomo = {"ok": False, "error": str(e)}
    # also reconcile runtime registry
    runtime = {}
    try:
        from mozilla_manager.runtime_registry import reconcile_running
        runtime = reconcile_running(drop_missing_profiles=True)
    except Exception as e:
        runtime = {"ok": False, "error": str(e)}
    return {"ok": True, "tmp": tmp, "mihomo_orphans": mihomo, "runtime": runtime}


def consistency(repair: bool = False) -> dict[str, Any]:
    return check_consistency(repair=repair)


def sandbox_status() -> dict[str, Any]:
    return enforce_no_home_writes()


def shutdown_all(*, stop_browsers: bool = True, stop_mihomo: bool = True) -> dict[str, Any]:
    """Full process teardown used when desktop client closes.

    Stops:
      - all running browser profiles
      - all Mozilla-owned mihomo instances under ROOT
      - RPA scheduler / watchdog / backup loops
    Does NOT touch non-Mozilla processes (other projects' mihomo/python).
    """
    report: dict[str, Any] = {"ok": True, "browsers": [], "mihomo": {}, "loops": {}}

    # 1) stop background loops first so they don't re-launch work
    try:
        from mozilla_manager.rpa.scheduler import stop_scheduler

        report["loops"]["rpa"] = stop_scheduler()
    except Exception as e:
        report["loops"]["rpa"] = {"ok": False, "error": str(e)}
    try:
        from mozilla_manager.modules.watchdog_svc import stop_watchdog_loop

        report["loops"]["watchdog"] = stop_watchdog_loop()
    except Exception as e:
        report["loops"]["watchdog"] = {"ok": False, "error": str(e)}
    try:
        from mozilla_manager.modules.backup_svc import stop_backup_loop

        report["loops"]["backup"] = stop_backup_loop()
    except Exception as e:
        report["loops"]["backup"] = {"ok": False, "error": str(e)}

    # 2) stop every running profile (browser + its mihomo)
    if stop_browsers:
        try:
            from mozilla_manager.modules import profiles as profiles_mod
            from mozilla_manager.runtime_registry import list_running

            running = list(list_running().keys()) if callable(list_running) else []
            # list_running may return dict
            if isinstance(running, dict):
                running = list(running.keys())
            for pid in list(running):
                if pid in {"browsers", "updated_at"}:
                    continue
                try:
                    report["browsers"].append(profiles_mod.stop(str(pid)))
                except Exception as e:
                    report["browsers"].append({"ok": False, "id": pid, "error": str(e)})
        except Exception as e:
            report["browsers_error"] = str(e)

    # 3) sweep remaining Mozilla mihomo under ROOT (no keep ports)
    if stop_mihomo:
        try:
            from mozilla_manager.modules import mihomo_svc

            report["mihomo"] = mihomo_svc.cleanup_orphans(keep_ports=[], dry_run=False)
        except Exception as e:
            report["mihomo"] = {"ok": False, "error": str(e)}

    try:
        from mozilla_manager import db

        db.audit("shutdown_all", detail={"browsers": len(report.get("browsers") or []), "mihomo": report.get("mihomo")})
    except Exception:
        pass
    return report
