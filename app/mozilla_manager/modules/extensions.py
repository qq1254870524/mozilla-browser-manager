"""v3 unified extensions under runtime/extensions/ + profile enable list."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from mozilla_manager import db
from mozilla_manager.paths import ROOT, ensure_layout, p, safe_resolve
from mozilla_manager.store import ProfileStore

EXT_ROOT = lambda: safe_resolve(p("runtime", "extensions"))  # noqa: E731


def list_extensions() -> list[dict[str, Any]]:
    ensure_layout()
    root = EXT_ROOT()
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        manifest = d / "manifest.json"
        name = d.name
        version = ""
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                name = data.get("name") or name
                version = str(data.get("version") or "")
            except Exception:
                pass
        out.append(
            {
                "id": d.name,
                "name": name,
                "version": version,
                "path": str(d.relative_to(ROOT)),
            }
        )
    return out


def profile_extensions(profile_id: str) -> list[str]:
    prof = ProfileStore().get(profile_id)
    return list((prof.meta or {}).get("extensions") or [])


def set_profile_extensions(profile_id: str, ext_ids: list[str]) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    available = {e["id"] for e in list_extensions()}
    unknown = [x for x in ext_ids if x not in available]
    meta = dict(prof.meta)
    meta["extensions"] = [x for x in ext_ids if x in available]
    updated = store.update(profile_id, meta=meta)
    db.upsert_profile_row(updated)
    db.audit("extensions_set", profile_id, {"extensions": meta["extensions"], "unknown": unknown})
    return {"ok": True, "extensions": meta["extensions"], "unknown": unknown, "profile": updated.model_dump(mode="json")}


def resolve_extension_paths(profile_id: str) -> list[str]:
    """Absolute paths of enabled extensions for launch args."""
    ids = profile_extensions(profile_id)
    root = EXT_ROOT()
    paths = []
    for i in ids:
        d = root / i
        if d.is_dir():
            paths.append(str(d))
    return paths


def install_extension_dir(src: str, ext_id: str | None = None) -> dict[str, Any]:
    """Copy an unpacked extension directory into runtime/extensions/<id>/."""
    ensure_layout()
    src_path = Path(src)
    # must already be under ROOT (sandbox)
    src_path = safe_resolve(src_path)
    if not src_path.is_dir():
        raise FileNotFoundError(f"not a directory: {src_path}")
    eid = ext_id or src_path.name
    dest = EXT_ROOT() / eid
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src_path, dest)
    db.audit("extension_install", detail={"id": eid, "from": str(src_path.relative_to(ROOT))})
    return {"ok": True, "id": eid, "path": str(dest.relative_to(ROOT))}
