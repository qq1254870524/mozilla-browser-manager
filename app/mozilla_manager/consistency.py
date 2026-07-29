"""v3: DB ↔ directory ↔ profile.json consistency checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import db
from .models import Profile
from .paths import ROOT, ensure_layout, p, safe_resolve
from .store import ProfileStore


def check_consistency(*, repair: bool = False) -> dict[str, Any]:
    """Compare profiles.json index, per-dir profile.json, SQLite, and directories.

    Truth order for repair:
      1. data/profiles/<id>/profile.json  (if exists)
      2. data/profiles.json entry
      3. orphan dir discovery
    """
    ensure_layout()
    db.init_db()
    store = ProfileStore()
    index = {x.id: x for x in store.list()}
    issues: list[dict[str, Any]] = []
    repaired: list[str] = []

    profiles_root = safe_resolve(p("data", "profiles"))
    dir_ids: set[str] = set()
    if profiles_root.exists():
        for d in profiles_root.iterdir():
            if d.is_dir():
                dir_ids.add(d.name)

    # index vs dir
    for pid, prof in index.items():
        rel = prof.user_data_dir
        try:
            abs_dir = safe_resolve(ROOT / rel)
        except Exception as e:
            issues.append({"level": "error", "id": pid, "issue": f"path sandbox: {e}"})
            continue
        if not abs_dir.exists():
            issues.append({"level": "error", "id": pid, "issue": "user_data_dir missing"})
            if repair:
                abs_dir.mkdir(parents=True, exist_ok=True)
                store._write_profile_file(prof)
                repaired.append(f"recreate-dir:{pid}")
        else:
            pj = abs_dir / "profile.json"
            if not pj.exists():
                issues.append({"level": "warn", "id": pid, "issue": "profile.json missing"})
                if repair:
                    store._write_profile_file(prof)
                    repaired.append(f"write-profile.json:{pid}")
            else:
                try:
                    disk = Profile.model_validate(json.loads(pj.read_text(encoding="utf-8")))
                    if disk.id != pid:
                        issues.append(
                            {
                                "level": "error",
                                "id": pid,
                                "issue": f"profile.json id mismatch disk={disk.id}",
                            }
                        )
                    # truth = disk profile.json
                    if repair and disk.model_dump(mode="json") != prof.model_dump(mode="json"):
                        # prefer disk truth into index
                        items = [disk if x.id == pid else x for x in store.list()]
                        # rewrite via store internals
                        store._write(items)
                        store._write_profile_file(disk)
                        db.upsert_profile_row(disk)
                        repaired.append(f"sync-index-from-disk:{pid}")
                        issues.append(
                            {"level": "info", "id": pid, "issue": "index diverged from profile.json (repaired)" if repair else "index diverged from profile.json"}
                        )
                except Exception as e:
                    issues.append({"level": "error", "id": pid, "issue": f"profile.json invalid: {e}"})

        # db row
        row = db.get_profile_row(pid)
        if not row:
            issues.append({"level": "warn", "id": pid, "issue": "missing sqlite row"})
            if repair:
                db.upsert_profile_row(prof)
                repaired.append(f"db-upsert:{pid}")

    # orphan dirs not in index
    for did in sorted(dir_ids - set(index.keys())):
        pj = profiles_root / did / "profile.json"
        if pj.exists():
            issues.append({"level": "warn", "id": did, "issue": "orphan dir with profile.json not in index"})
            if repair:
                try:
                    disk = Profile.model_validate(json.loads(pj.read_text(encoding="utf-8")))
                    items = store.list()
                    if not any(x.id == disk.id for x in items):
                        items.append(disk)
                        store._write(items)
                        db.upsert_profile_row(disk)
                        repaired.append(f"reindex-orphan:{did}")
                except Exception as e:
                    issues.append({"level": "error", "id": did, "issue": f"orphan repair failed: {e}"})
        else:
            issues.append({"level": "info", "id": did, "issue": "orphan dir without profile.json"})

    # sqlite rows without index
    for row in db.list_profile_rows():
        if row["id"] not in index and row["id"] not in dir_ids:
            issues.append({"level": "warn", "id": row["id"], "issue": "sqlite orphan row"})
            if repair:
                db.delete_profile_row(row["id"])
                repaired.append(f"db-delete-orphan:{row['id']}")

    errors = [x for x in issues if x["level"] == "error"]
    return {
        "ok": len(errors) == 0,
        "index_count": len(index),
        "dir_count": len(dir_ids),
        "db_count": len(db.list_profile_rows()),
        "issues": issues,
        "repaired": repaired,
        "truth": "data/profiles/<id>/profile.json",
    }


def preflight_consistency(profile_id: str, *, repair: bool = True) -> dict[str, Any]:
    """Lightweight single-profile check before launch."""
    store = ProfileStore()
    try:
        prof = store.get(profile_id)
    except KeyError:
        return {"ok": False, "blocks": [f"profile not in index: {profile_id}"]}
    blocks: list[str] = []
    warnings: list[str] = []
    d = safe_resolve(ROOT / prof.user_data_dir)
    if not d.exists():
        if repair:
            d.mkdir(parents=True, exist_ok=True)
            store._write_profile_file(prof)
            warnings.append("recreated missing user_data_dir")
        else:
            blocks.append("user_data_dir missing")
    pj = d / "profile.json"
    if not pj.exists():
        if repair:
            store._write_profile_file(prof)
            warnings.append("rewrote missing profile.json")
        else:
            blocks.append("profile.json missing")
    else:
        try:
            disk = json.loads(pj.read_text(encoding="utf-8"))
            if disk.get("id") != profile_id:
                blocks.append(f"profile.json id mismatch: {disk.get('id')}")
        except Exception as e:
            blocks.append(f"profile.json invalid: {e}")
    db.upsert_profile_row(prof)
    return {"ok": not blocks, "blocks": blocks, "warnings": warnings, "profile_id": profile_id}
