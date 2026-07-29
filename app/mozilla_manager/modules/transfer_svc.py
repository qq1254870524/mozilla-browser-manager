"""v7 full profile migration pack (machine A → B)."""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mozilla_manager import db
from mozilla_manager.paths import MIGRATE_DIR, ROOT, ensure_layout, p, safe_resolve
from mozilla_manager.snapshots import export_profile_zip
from mozilla_manager.store import ProfileStore
from mozilla_manager.models import Profile, ProxyConfig, EnvBinding, EngineKind, ChromiumPatch


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def export_migrate_pack(profile_id: str) -> dict[str, Any]:
    """Export complete migratable zip under data/exports/migrate/."""
    ensure_layout()
    raw = export_profile_zip(profile_id, include_user_data=True, include_extensions=True, include_storage=True)
    # also include stealth.json explicitly + totp bindings note
    store = ProfileStore()
    prof = store.get(profile_id)
    out = safe_resolve(MIGRATE_DIR / f"migrate_{profile_id}_{_now()}.zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # copy all from raw export
        with zipfile.ZipFile(raw, "r") as src:
            for info in src.infolist():
                zf.writestr(info, src.read(info.filename))
        # stealth
        stealth = safe_resolve(ROOT / "data" / "profiles" / profile_id / "stealth.json")
        if stealth.exists():
            zf.write(stealth, arcname="stealth.json")
        # profile cookies_inject
        ud = safe_resolve(ROOT / prof.user_data_dir)
        for extra in ("cookies_inject.json", "restored_storage_state.json", "last_check.json"):
            f = ud / extra
            if f.exists():
                zf.write(f, arcname=f"extra/{extra}")
        manifest = {
            "format": "mozilla-migrate-v7",
            "profile_id": profile_id,
            "exported_at": _now(),
            "redacted": False,
            "includes": ["user_data", "storage_state", "extensions", "stealth", "profile_json"],
            "source_root_hint": str(ROOT),
        }
        zf.writestr("_migrate_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    db.audit("migrate_export", profile_id, {"path": str(out.relative_to(ROOT))})
    return {"ok": True, "path": str(out.relative_to(ROOT)), "bytes": out.stat().st_size, "source_export": str(raw.relative_to(ROOT))}


def import_migrate_pack(path: str | Path, *, new_name: str = "", keep_id: bool = False) -> dict[str, Any]:
    """Import migrate zip into a new (or same-id) profile under ROOT."""
    ensure_layout()
    src = safe_resolve(path)
    if not src.exists():
        raise FileNotFoundError(str(src))
    tmp = safe_resolve(p("tmp", f"migrate_import_{_now()}"))
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as zf:
        zf.extractall(tmp)

    prof_json = tmp / "_mozilla_profile.json"
    if not prof_json.exists():
        raise ValueError("invalid migrate pack: missing _mozilla_profile.json")
    raw = json.loads(prof_json.read_text(encoding="utf-8"))
    old_id = raw.get("id") or "imported"
    store = ProfileStore()

    # create skeleton via store.create semantics
    name = new_name or f"{raw.get('name') or old_id}-migrated"
    engine = raw.get("engine") or "pw_chromium"
    patch = raw.get("chromium_patch") or "patchright"
    env = raw.get("env") or {}
    proxy = raw.get("proxy") or {}
    meta = dict(raw.get("meta") or {})
    meta["migrated_from"] = old_id
    meta["migrated_at"] = _now()

    from mozilla_manager.modules.profiles import create_profile

    created = create_profile(
        name=name,
        engine=str(engine) if not isinstance(engine, str) else engine,
        patch=str(patch) if not isinstance(patch, str) else patch,
        country=str(meta.get("expected_country") or ""),
        timezone_id=str((env.get("timezone_id") or "")),
        locale=str(env.get("locale") or ""),
        lat=float(((env.get("geolocation") or {}) or {}).get("latitude") or 0),
        lon=float(((env.get("geolocation") or {}) or {}).get("longitude") or 0),
        auto_port=bool(proxy.get("mode") == "mihomo"),
        group=str(meta.get("group") or "migrated"),
        remark=f"migrated from {old_id}",
        fingerprint_id=str(((env.get("fingerprint") or {}) or {}).get("template_id") or ""),
        sub=str(meta.get("sub") or "default"),
        browser_only=bool(proxy.get("browser_only", True)),
    )
    new_id = created["id"]
    prof = store.get(new_id)

    # restore env/proxy/meta more faithfully
    try:
        env_m = EnvBinding.model_validate(env) if env else prof.env
        proxy_m = ProxyConfig.model_validate(proxy) if proxy else prof.proxy
        # rebind ports on this machine — clear mihomo_port for re-alloc
        if proxy_m.mode == "mihomo":
            from mozilla_manager.network.mihomo import allocate_port

            proxy_m.mihomo_port = allocate_port(new_id)
        meta["extensions"] = list(meta.get("extensions") or raw.get("meta", {}).get("extensions") or [])
        prof = store.update(new_id, env=env_m, proxy=proxy_m, meta=meta)
    except Exception:
        pass

    # copy user_data
    ud_src = tmp / "user_data"
    ud_dst = safe_resolve(ROOT / prof.user_data_dir)
    ud_dst.mkdir(parents=True, exist_ok=True)
    if ud_src.exists():
        for f in ud_src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(ud_src)
                dest = safe_resolve(ud_dst / rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)

    # storage state
    st = tmp / "storage_state.json"
    if st.exists():
        shutil.copy2(st, ud_dst / "restored_storage_state.json")
        # also cookies inject convenience
        try:
            state = json.loads(st.read_text(encoding="utf-8"))
            cookies = state.get("cookies") or []
            if cookies:
                (ud_dst / "cookies_inject.json").write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # stealth
    stealth = tmp / "stealth.json"
    if stealth.exists():
        sp = safe_resolve(ROOT / "data" / "profiles" / new_id / "stealth.json")
        sp.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(stealth.read_text(encoding="utf-8"))
        data["profile_id"] = new_id
        data["migrated_from"] = old_id
        sp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # extensions: copy into runtime/extensions if missing; enable on profile
    ext_root = tmp / "extensions"
    enabled = []
    if ext_root.exists():
        rt_ext = safe_resolve(ROOT / "runtime" / "extensions")
        for d in ext_root.iterdir():
            if not d.is_dir():
                continue
            target = rt_ext / d.name
            if not target.exists():
                shutil.copytree(d, target)
            enabled.append(d.name)
        if enabled:
            meta = dict(store.get(new_id).meta)
            cur = list(meta.get("extensions") or [])
            for e in enabled:
                if e not in cur:
                    cur.append(e)
            meta["extensions"] = cur
            store.update(new_id, meta=meta)

    # cleanup tmp
    shutil.rmtree(tmp, ignore_errors=True)
    db.audit("migrate_import", new_id, {"from": old_id, "path": str(src)})
    return {
        "ok": True,
        "old_id": old_id,
        "new_id": new_id,
        "name": name,
        "extensions": enabled,
        "user_data": prof.user_data_dir,
    }
