"""v4 环境快照（时间旅行）：Cookies + LocalStorage + Session 还原点."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mozilla_manager import db
from mozilla_manager.modules import cookies as cookies_mod
from mozilla_manager.paths import ROOT, ensure_layout, p, safe_resolve
from mozilla_manager.store import ProfileStore


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _root(profile_id: str) -> Path:
    return safe_resolve(p("data", "exports", "timetravel", profile_id))


def create_restore_point(profile_id: str, *, label: str = "", include_user_data: bool = False) -> dict[str, Any]:
    ensure_layout()
    store = ProfileStore()
    prof = store.get(profile_id)
    ts = _now()
    dest = _root(profile_id) / ts
    dest.mkdir(parents=True, exist_ok=True)

    # storage state (live preferred)
    state = cookies_mod._live_storage(profile_id) or cookies_mod.load_pending_storage_state(profile_id) or {
        "cookies": [],
        "origins": [],
    }
    (dest / "storage_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # open pages / tabs
    tabs: list[str] = list((prof.meta or {}).get("tabs") or [])
    groups = list((prof.meta or {}).get("tab_groups") or [])
    live_tabs = _capture_live_tabs(profile_id)
    if live_tabs:
        tabs = live_tabs
    (dest / "tabs.json").write_text(
        json.dumps({"tabs": tabs, "tab_groups": groups}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # profile config snapshot
    (dest / "profile.json").write_text(
        json.dumps(prof.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if include_user_data:
        src = safe_resolve(ROOT / prof.user_data_dir)
        if src.exists():
            shutil.copytree(
                src,
                dest / "user_data",
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("Singleton*", "lockfile", "LOCK", "*.log", "Cache", "Code Cache", "GPUCache"),
            )

    meta = {
        "profile_id": profile_id,
        "ts": ts,
        "label": label or ts,
        "at": ts,
        "cookies": len(state.get("cookies") or []),
        "origins": len(state.get("origins") or []),
        "tabs": tabs,
        "has_user_data": include_user_data,
        "path": str(dest.relative_to(ROOT)),
    }
    (dest / "point.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    db.audit("timetravel_create", profile_id, meta)
    return meta


def list_points(profile_id: str) -> list[dict[str, Any]]:
    ensure_layout()
    root = _root(profile_id)
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        pj = d / "point.json"
        if pj.exists():
            try:
                out.append(json.loads(pj.read_text(encoding="utf-8")))
                continue
            except Exception:
                pass
        out.append({"profile_id": profile_id, "ts": d.name, "path": str(d.relative_to(ROOT))})
    return out


def rollback(profile_id: str, ts: str, *, restore_user_data: bool = False) -> dict[str, Any]:
    """一键回滚到还原点（不要求浏览器重启后的配置一致即可注入）."""
    store = ProfileStore()
    prof = store.get(profile_id)
    src = _root(profile_id) / ts
    if not src.exists():
        raise FileNotFoundError(f"restore point not found: {profile_id}/{ts}")

    restored: list[str] = []
    ud = safe_resolve(ROOT / prof.user_data_dir)
    ud.mkdir(parents=True, exist_ok=True)

    # storage → inject files
    st = src / "storage_state.json"
    if st.exists():
        raw = st.read_text(encoding="utf-8")
        (ud / "restored_storage_state.json").write_text(raw, encoding="utf-8")
        (ud / "cookies_inject.json").write_text(raw, encoding="utf-8")
        restored.append("storage_state")
        # if browser running, inject live
        try:
            from mozilla_manager.engines import chromium as chromium_mod

            run = getattr(chromium_mod, "_RUNS", {}).get(profile_id)
            if run and run.get("context"):
                cookies_mod.inject_cookies_to_context(run["context"], profile_id)
                restored.append("live_inject")
        except Exception:
            pass

    tabs_f = src / "tabs.json"
    if tabs_f.exists():
        try:
            tdata = json.loads(tabs_f.read_text(encoding="utf-8"))
            meta = dict(prof.meta)
            meta["tabs"] = tdata.get("tabs") or []
            meta["tab_groups"] = tdata.get("tab_groups") or []
            store.update(profile_id, meta=meta)
            restored.append("tabs")
        except Exception:
            pass

    if restore_user_data and (src / "user_data").exists():
        for item in (src / "user_data").iterdir():
            target = ud / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        restored.append("user_data")

    # clear need_relogin on successful rollback of cookies
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    if "需重登" in list(meta.get("tags") or []):
        meta["tags"] = [t for t in meta.get("tags") or [] if t != "需重登"]
        meta["need_relogin"] = False
        store.update(profile_id, meta=meta)

    result = {"ok": True, "profile_id": profile_id, "ts": ts, "restored": restored}
    db.audit("timetravel_rollback", profile_id, result)
    return result


def _capture_live_tabs(profile_id: str) -> list[str]:
    try:
        from mozilla_manager.engines import chromium as chromium_mod

        run = getattr(chromium_mod, "_RUNS", {}).get(profile_id)
        if not run:
            return []
        ctx = run.get("context")
        if not ctx:
            return []
        urls = []
        for page in getattr(ctx, "pages", []) or []:
            try:
                u = page.url
                if u and not u.startswith("chrome") and not u.startswith("about:") and not u.startswith("data:"):
                    urls.append(u)
            except Exception:
                pass
        return urls
    except Exception:
        return []
