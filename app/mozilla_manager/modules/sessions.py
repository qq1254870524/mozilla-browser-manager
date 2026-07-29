"""v2 session backup / restore.

Layout: data/exports/sessions/<profile_id>/<ts>/
  - session.json   metadata
  - profile.json   profile model dump
  - storage_state.json  cookies+origins if capturable
  - user_data/     optional full user-data copy (heavy)
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mozilla_manager.paths import ROOT, ensure_layout, p, safe_resolve
from mozilla_manager.store import ProfileStore


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sessions_root(profile_id: str) -> Path:
    return safe_resolve(p("data", "exports", "sessions", profile_id))


def list_sessions(profile_id: str | None = None) -> list[dict[str, Any]]:
    ensure_layout()
    base = safe_resolve(p("data", "exports", "sessions"))
    base.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    roots = [base / profile_id] if profile_id else sorted(base.iterdir()) if base.exists() else []
    for root in roots:
        if not root.is_dir():
            continue
        pid = root.name
        for d in sorted(root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            meta_path = d / "session.json"
            meta: dict[str, Any] = {"profile_id": pid, "ts": d.name, "path": str(d.relative_to(ROOT))}
            if meta_path.exists():
                try:
                    meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
                except Exception:
                    pass
            out.append(meta)
    return out


def backup_session(
    profile_id: str,
    *,
    label: str = "",
    include_user_data: bool = False,
    storage_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backup profile config + optional cookies/storage + optional full user_data."""
    ensure_layout()
    store = ProfileStore()
    prof = store.get(profile_id)
    ts = _ts()
    dest = safe_resolve(_sessions_root(profile_id) / ts)
    dest.mkdir(parents=True, exist_ok=True)

    # try live storage_state from running chromium
    if storage_state is None:
        storage_state = _try_capture_storage(profile_id)

    profile_dump = prof.model_dump(mode="json")
    (dest / "profile.json").write_text(
        json.dumps(profile_dump, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if storage_state is not None:
        (dest / "storage_state.json").write_text(
            json.dumps(storage_state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    tabs = list((prof.meta or {}).get("tabs") or [])
    user_data_copied = False
    if include_user_data:
        src = safe_resolve(ROOT / prof.user_data_dir)
        udest = dest / "user_data"
        if src.exists():
            shutil.copytree(
                src,
                udest,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("Singleton*", "lockfile", "LOCK", "*.log"),
            )
            user_data_copied = True

    meta = {
        "profile_id": profile_id,
        "ts": ts,
        "label": label,
        "at": ts,
        "tabs": tabs,
        "has_storage_state": storage_state is not None,
        "has_user_data": user_data_copied,
        "path": str(dest.relative_to(ROOT)),
        "engine": prof.engine.value if hasattr(prof.engine, "value") else str(prof.engine),
        "name": prof.name,
    }
    (dest / "session.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def restore_session(
    profile_id: str,
    ts: str,
    *,
    restore_user_data: bool = True,
    restore_profile_json: bool = True,
) -> dict[str, Any]:
    """Restore a previous session backup into the live profile directory."""
    ensure_layout()
    store = ProfileStore()
    prof = store.get(profile_id)
    src = safe_resolve(_sessions_root(profile_id) / ts)
    if not src.exists():
        raise FileNotFoundError(f"session not found: {profile_id}/{ts}")

    restored: list[str] = []
    # restore profile model fields (env/proxy/meta) but keep id + user_data_dir
    pjson = src / "profile.json"
    if restore_profile_json and pjson.exists():
        data = json.loads(pjson.read_text(encoding="utf-8"))
        from mozilla_manager.models import ChromiumPatch, EngineKind, EnvBinding, ProxyConfig

        patch: dict[str, Any] = {}
        if "name" in data:
            patch["name"] = data["name"]
        if "engine" in data:
            patch["engine"] = EngineKind(data["engine"])
        if "chromium_patch" in data:
            patch["chromium_patch"] = ChromiumPatch(data["chromium_patch"])
        if "proxy" in data:
            patch["proxy"] = ProxyConfig.model_validate(data["proxy"])
        if "env" in data:
            patch["env"] = EnvBinding.model_validate(data["env"])
        if "meta" in data:
            meta = dict(data["meta"])
            # keep restore marker
            meta["last_restore"] = {"ts": ts, "at": _ts()}
            patch["meta"] = meta
        store.update(profile_id, **patch)
        restored.append("profile.json")

    udest = safe_resolve(ROOT / prof.user_data_dir)
    usrc = src / "user_data"
    if restore_user_data and usrc.exists():
        udest.mkdir(parents=True, exist_ok=True)
        for item in usrc.iterdir():
            target = udest / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        restored.append("user_data")

    # stash storage_state for next launch injection
    sstate = src / "storage_state.json"
    if sstate.exists():
        target = udest / "restored_storage_state.json"
        udest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sstate, target)
        restored.append("storage_state.json")

    return {
        "ok": True,
        "profile_id": profile_id,
        "ts": ts,
        "restored": restored,
        "path": str(src.relative_to(ROOT)),
    }


def _try_capture_storage(profile_id: str) -> dict[str, Any] | None:
    """Best-effort: if chromium is running, dump storage_state."""
    try:
        from mozilla_manager.engines import chromium as chromium_mod

        runs = getattr(chromium_mod, "_RUNS", {})
        run = runs.get(profile_id)
        if not run:
            return None
        ctx = run.get("context")
        if ctx is None:
            return None
        if hasattr(ctx, "storage_state"):
            return ctx.storage_state()
    except Exception:
        return None
    return None
