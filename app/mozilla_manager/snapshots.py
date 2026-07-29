"""Export / snapshot — v3 full dump, 禁止脱敏."""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import ROOT, ensure_layout, p, safe_resolve
from .store import ProfileStore


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def snapshot_profile(profile_id: str, note: str = "") -> Path:
    """Copy profile dir + metadata into data/exports/snapshots/<id>/<ts>/."""
    ensure_layout()
    store = ProfileStore()
    prof = store.get(profile_id)
    src = safe_resolve(ROOT / prof.user_data_dir)
    dest = safe_resolve(p("data", "exports", "snapshots", profile_id, _ts()))
    dest.mkdir(parents=True, exist_ok=True)
    if src.exists():
        for item in src.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
    meta = {"profile": prof.model_dump(mode="json"), "note": note, "at": _ts(), "redacted": False}
    (dest / "snapshot.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def _try_live_storage(profile_id: str) -> dict[str, Any] | None:
    try:
        from mozilla_manager.engines import chromium as chromium_mod

        run = getattr(chromium_mod, "_RUNS", {}).get(profile_id)
        if run and run.get("context") is not None and hasattr(run["context"], "storage_state"):
            return run["context"].storage_state()
    except Exception:
        return None
    return None


def export_profile_zip(
    profile_id: str,
    *,
    include_user_data: bool = True,
    include_extensions: bool = True,
    include_storage: bool = True,
) -> Path:
    """一键导出 profile zip：cookies/storage/扩展/配置 — 不做脱敏."""
    ensure_layout()
    store = ProfileStore()
    prof = store.get(profile_id)
    src = safe_resolve(ROOT / prof.user_data_dir)
    out = safe_resolve(p("data", "exports", f"{profile_id}_{_ts()}.zip"))
    out.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "profile_id": profile_id,
        "exported_at": _ts(),
        "redacted": False,  # 导出禁止脱敏
        "include_user_data": include_user_data,
        "include_extensions": include_extensions,
        "include_storage": include_storage,
        "profile": prof.model_dump(mode="json"),
    }

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "_mozilla_profile.json",
            json.dumps(prof.model_dump(mode="json"), ensure_ascii=False, indent=2),
        )
        # live or on-disk storage
        if include_storage:
            state = _try_live_storage(profile_id)
            if state is None:
                disk_state = src / "restored_storage_state.json"
                if disk_state.exists():
                    try:
                        state = json.loads(disk_state.read_text(encoding="utf-8"))
                    except Exception:
                        state = None
            if state is not None:
                zf.writestr(
                    "storage_state.json",
                    json.dumps(state, ensure_ascii=False, indent=2),
                )
                manifest["has_storage_state"] = True
            else:
                manifest["has_storage_state"] = False

        if include_user_data and src.exists():
            for f in src.rglob("*"):
                if not f.is_file():
                    continue
                # skip huge locks/caches lightly but DO NOT strip cookies/logins
                name = f.name.lower()
                if name in ("lock", "lockfile") or name.startswith("singleton"):
                    continue
                arc = str(f.relative_to(src))
                if arc == "profile.json":
                    arc = "profile.dir.json"
                zf.write(f, arcname=f"user_data/{arc}")

        if include_extensions:
            from mozilla_manager.modules.extensions import resolve_extension_paths

            ext_paths = resolve_extension_paths(profile_id)
            manifest["extensions"] = []
            for ep in ext_paths:
                ep_path = Path(ep)
                if not ep_path.exists():
                    continue
                manifest["extensions"].append(ep_path.name)
                for f in ep_path.rglob("*"):
                    if f.is_file():
                        arc = f"extensions/{ep_path.name}/{f.relative_to(ep_path)}"
                        zf.write(f, arcname=arc)

        zf.writestr("_export_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return out


def export_profile_zip_incremental(profile_id: str) -> Path:
    """差异备份：仅导出相对 last_storage_state 有变化的 cookies/origins + 配置.

    大幅缩小体积；若无基线则退化为 storage-only 导出。
    """
    ensure_layout()
    store = ProfileStore()
    prof = store.get(profile_id)
    src = safe_resolve(ROOT / prof.user_data_dir)
    out = safe_resolve(p("data", "exports", f"{profile_id}_incr_{_ts()}.zip"))
    out.parent.mkdir(parents=True, exist_ok=True)

    def load_state(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"cookies": [], "origins": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"cookies": [], "origins": []}

    current = _try_live_storage(profile_id)
    if current is None:
        # prefer last dump or inject file
        for name in ("last_storage_state.json", "restored_storage_state.json", "cookies_inject.json"):
            cand = src / name
            if cand.exists():
                current = load_state(cand)
                break
        current = current or {"cookies": [], "origins": []}
    baseline = load_state(src / "last_storage_state.baseline.json")
    if not (src / "last_storage_state.baseline.json").exists():
        # first incremental: use empty baseline so all current cookies exported, then set baseline
        baseline = {"cookies": [], "origins": []}

    def ckey(c: dict[str, Any]):
        return (c.get("name"), c.get("domain") or c.get("url"), c.get("path") or "/", c.get("value"))

    base_set = {ckey(c) for c in (baseline.get("cookies") or []) if isinstance(c, dict)}
    changed_cookies = [c for c in (current.get("cookies") or []) if isinstance(c, dict) and ckey(c) not in base_set]

    def okey(o: dict[str, Any]):
        return (o.get("origin"), json.dumps(o.get("localStorage") or {}, sort_keys=True))

    base_o = {okey(o) for o in (baseline.get("origins") or []) if isinstance(o, dict)}
    changed_origins = [o for o in (current.get("origins") or []) if isinstance(o, dict) and okey(o) not in base_o]

    delta = {
        "cookies": changed_cookies,
        "origins": changed_origins,
        "baseline_cookies": len(baseline.get("cookies") or []),
        "current_cookies": len(current.get("cookies") or []),
        "redacted": False,
        "incremental": True,
        "profile": prof.model_dump(mode="json"),
        "exported_at": _ts(),
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("_incremental.json", json.dumps(delta, ensure_ascii=False, indent=2))
        zf.writestr(
            "storage_state.delta.json",
            json.dumps({"cookies": changed_cookies, "origins": changed_origins}, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "_mozilla_profile.json",
            json.dumps(prof.model_dump(mode="json"), ensure_ascii=False, indent=2),
        )
    # update baseline to current after successful export
    try:
        (src / "last_storage_state.baseline.json").write_text(
            json.dumps(current, ensure_ascii=False), encoding="utf-8"
        )
        (src / "last_storage_state.json").write_text(
            json.dumps(current, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass
    return out
