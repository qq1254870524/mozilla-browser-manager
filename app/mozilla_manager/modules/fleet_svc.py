"""v10 fleet sync: export/import machine packs between hosts (zip under data/fleet)."""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mozilla_manager import db
from mozilla_manager.modules import machine_svc, notify_svc
from mozilla_manager.paths import (
    FLEET_DIR,
    FLEET_INBOX,
    FLEET_OUTBOX,
    ROOT,
    RPA_WORKFLOWS_DIR,
    TOTP_DIR,
    WATCHDOGS_DIR,
    RUNTIME_NODES_DIR,
    ensure_layout,
    p,
    safe_resolve,
)
from mozilla_manager.store import ProfileStore


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def export_fleet_pack(
    *,
    include_profiles: list[str] | None = None,
    include_all_profiles_meta: bool = True,
    include_nodes: bool = True,
    include_rpa: bool = True,
    include_totp: bool = True,
    include_watchdogs: bool = True,
    include_profile_data: bool = False,
    name: str = "",
) -> dict[str, Any]:
    """Build a fleet zip for copying to another machine's data/fleet/inbox."""
    ensure_layout()
    machine = machine_svc.get_machine()
    store = ProfileStore()
    profiles = store.list()
    selected = include_profiles
    if selected is None and include_profile_data:
        selected = [p.id for p in profiles]
    selected = selected or []

    slug = name or f"fleet_{machine['machine_id'][:8]}_{_now()}"
    out = safe_resolve(FLEET_OUTBOX / f"{slug}.zip")
    out.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "format": "mozilla-fleet-v10",
        "exported_at": _now_iso(),
        "machine": machine,
        "options": {
            "include_nodes": include_nodes,
            "include_rpa": include_rpa,
            "include_totp": include_totp,
            "include_watchdogs": include_watchdogs,
            "include_profile_data": include_profile_data,
            "profile_ids": selected,
        },
        "counts": {},
    }

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # profiles metadata index
        meta_rows = []
        if include_all_profiles_meta:
            for pr in profiles:
                d = pr.model_dump(mode="json")
                # strip bulky nothing — already json
                meta_rows.append(d)
            zf.writestr("profiles_index.json", json.dumps(meta_rows, ensure_ascii=False, indent=2))
            manifest["counts"]["profiles_meta"] = len(meta_rows)

        # optional full migrate packs
        migrated = []
        if selected:
            from mozilla_manager.modules import transfer_svc

            for pid in selected:
                try:
                    r = transfer_svc.export_migrate_pack(pid)
                    src = safe_resolve(r["path"])
                    arc = f"profiles_data/{pid}.migrate.zip"
                    zf.write(src, arcname=arc)
                    migrated.append({"id": pid, "arc": arc, "bytes": r.get("bytes")})
                except Exception as e:
                    migrated.append({"id": pid, "error": str(e)})
            manifest["counts"]["profiles_data"] = len([x for x in migrated if "arc" in x])
            zf.writestr("profiles_data_index.json", json.dumps(migrated, ensure_ascii=False, indent=2))

        if include_watchdogs:
            wp = safe_resolve(WATCHDOGS_DIR / "watchdogs.json")
            if wp.exists():
                zf.write(wp, arcname="watchdogs.json")
                manifest["counts"]["watchdogs"] = 1

        if include_rpa:
            n = 0
            for f in RPA_WORKFLOWS_DIR.glob("*.json"):
                zf.write(f, arcname=f"rpa/workflows/{f.name}")
                n += 1
            manifest["counts"]["rpa_workflows"] = n

        if include_totp:
            tp = safe_resolve(TOTP_DIR / "accounts.json")
            if tp.exists():
                zf.write(tp, arcname="totp/accounts.json")
                manifest["counts"]["totp"] = 1

        if include_nodes:
            n = 0
            # copy lightweight node store files (not huge binaries)
            for f in RUNTIME_NODES_DIR.rglob("*"):
                if f.is_file() and f.suffix in (".json", ".yaml", ".yml", ".txt", ".list"):
                    rel = f.relative_to(RUNTIME_NODES_DIR)
                    zf.write(f, arcname=f"nodes/{rel.as_posix()}")
                    n += 1
            manifest["counts"]["node_files"] = n

        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    machine_svc.touch_sync()
    db.audit("fleet_export", detail={"path": str(out.relative_to(ROOT)), "counts": manifest["counts"]})
    notify_svc.push("fleet", f"Fleet 导出 {out.name}", level="success", detail=manifest["counts"])
    return {
        "ok": True,
        "path": str(out.relative_to(ROOT)),
        "bytes": out.stat().st_size,
        "manifest": manifest,
    }


def import_fleet_pack(
    path: str | Path,
    *,
    import_watchdogs: bool = True,
    import_rpa: bool = True,
    import_totp: bool = False,
    import_nodes: bool = True,
    import_profiles_data: bool = True,
    import_profiles_meta_as_tags: bool = True,
) -> dict[str, Any]:
    """Import fleet zip. Profile full data creates new profiles via migrate import."""
    ensure_layout()
    src = safe_resolve(path)
    if not src.exists():
        # also try inbox
        alt = safe_resolve(FLEET_INBOX / Path(path).name)
        if alt.exists():
            src = alt
        else:
            raise FileNotFoundError(str(path))

    tmp = safe_resolve(p("tmp", f"fleet_import_{_now()}"))
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as zf:
        zf.extractall(tmp)

    man_path = tmp / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    if manifest.get("format") not in (None, "mozilla-fleet-v10"):
        # still allow
        pass

    result: dict[str, Any] = {"ok": True, "imported": {}, "errors": [], "source_machine": (manifest.get("machine") or {})}

    if import_watchdogs and (tmp / "watchdogs.json").exists():
        dest = safe_resolve(WATCHDOGS_DIR / "watchdogs.json")
        # merge items by id
        try:
            incoming = json.loads((tmp / "watchdogs.json").read_text(encoding="utf-8"))
            existing = {}
            if dest.exists():
                existing = json.loads(dest.read_text(encoding="utf-8"))
            items = {x.get("id"): x for x in (existing.get("items") or []) if x.get("id")}
            for x in incoming.get("items") or []:
                if x.get("id"):
                    items[x["id"]] = x
            dest.write_text(json.dumps({"items": list(items.values()), "updated_at": _now_iso()}, ensure_ascii=False, indent=2), encoding="utf-8")
            result["imported"]["watchdogs"] = len(items)
        except Exception as e:
            result["errors"].append(f"watchdogs: {e}")

    if import_rpa and (tmp / "rpa" / "workflows").exists():
        n = 0
        for f in (tmp / "rpa" / "workflows").glob("*.json"):
            target = safe_resolve(RPA_WORKFLOWS_DIR / f.name)
            shutil.copy2(f, target)
            n += 1
        result["imported"]["rpa_workflows"] = n

    if import_totp and (tmp / "totp" / "accounts.json").exists():
        # merge by id
        try:
            dest = safe_resolve(TOTP_DIR / "accounts.json")
            incoming = json.loads((tmp / "totp" / "accounts.json").read_text(encoding="utf-8"))
            # support list or {accounts:[]}
            inc_list = incoming if isinstance(incoming, list) else list(incoming.get("accounts") or incoming.get("items") or [])
            cur = []
            if dest.exists():
                raw = json.loads(dest.read_text(encoding="utf-8"))
                cur = raw if isinstance(raw, list) else list(raw.get("accounts") or raw.get("items") or [])
            by_id = {str(x.get("id") or x.get("name")): x for x in cur}
            for x in inc_list:
                by_id[str(x.get("id") or x.get("name"))] = x
            merged = list(by_id.values())
            dest.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            result["imported"]["totp"] = len(merged)
        except Exception as e:
            result["errors"].append(f"totp: {e}")

    if import_nodes and (tmp / "nodes").exists():
        n = 0
        for f in (tmp / "nodes").rglob("*"):
            if f.is_file():
                rel = f.relative_to(tmp / "nodes")
                dest = safe_resolve(RUNTIME_NODES_DIR / rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                n += 1
        result["imported"]["node_files"] = n

    if import_profiles_data and (tmp / "profiles_data").exists():
        from mozilla_manager.modules import transfer_svc

        created = []
        for f in (tmp / "profiles_data").glob("*.migrate.zip"):
            try:
                r = transfer_svc.import_migrate_pack(f)
                created.append(r)
            except Exception as e:
                result["errors"].append(f"profile {f.name}: {e}")
        result["imported"]["profiles_data"] = len(created)
        result["created_profiles"] = created

    if import_profiles_meta_as_tags and (tmp / "profiles_index.json").exists():
        # annotate local matching names with fleet tag — non-destructive note file
        try:
            note = safe_resolve(FLEET_DIR / "last_import_profiles_index.json")
            shutil.copy2(tmp / "profiles_index.json", note)
            result["imported"]["profiles_meta_note"] = str(note.relative_to(ROOT))
        except Exception as e:
            result["errors"].append(f"profiles_meta: {e}")

    # copy pack into inbox archive
    try:
        archived = safe_resolve(FLEET_INBOX / src.name)
        if src.resolve() != archived.resolve():
            shutil.copy2(src, archived)
        result["archived"] = str(archived.relative_to(ROOT))
    except Exception:
        pass

    machine_svc.touch_sync()
    db.audit("fleet_import", detail={"path": str(src), "imported": result.get("imported"), "errors": result.get("errors")})
    level = "success" if not result["errors"] else "warn"
    notify_svc.push("fleet", f"Fleet 导入 {src.name}", level=level, detail=result.get("imported"))
    result["ok"] = len(result["errors"]) == 0
    return result


def list_fleet_packs() -> dict[str, Any]:
    ensure_layout()
    def scan(d: Path, kind: str):
        rows = []
        if d.exists():
            for f in sorted(d.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
                rows.append({"kind": kind, "name": f.name, "path": str(f.relative_to(ROOT)), "bytes": f.stat().st_size})
        return rows
    return {
        "ok": True,
        "machine": machine_svc.get_machine(),
        "outbox": scan(FLEET_OUTBOX, "outbox"),
        "inbox": scan(FLEET_INBOX, "inbox"),
    }
