"""v3: temp files only under ROOT/tmp — periodic GC. Never write HOME."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from .paths import ROOT, TMP_DIR, ensure_layout, safe_resolve


def enforce_no_home_writes() -> dict[str, Any]:
    """Best-effort: point common cache envs into ROOT; never touch system proxy."""
    ensure_layout()
    cache = safe_resolve(ROOT / "runtime" / "cache")
    tmp = safe_resolve(TMP_DIR)
    cache.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    mapped = {
        "XDG_CACHE_HOME": str(cache),
        "XDG_DATA_HOME": str(safe_resolve(ROOT / "runtime" / "xdg-data")),
        "XDG_CONFIG_HOME": str(safe_resolve(ROOT / "runtime" / "xdg-config")),
        "TMPDIR": str(tmp),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "PLAYWRIGHT_BROWSERS_PATH": str(safe_resolve(ROOT / "runtime" / "browsers")),
    }
    # ensure xdg dirs
    for k in ("XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        Path(mapped[k]).mkdir(parents=True, exist_ok=True)
    applied = {}
    for k, v in mapped.items():
        os.environ[k] = v
        applied[k] = v
    # never set system proxy vars here
    return {
        "ok": True,
        "root": str(ROOT),
        "env": applied,
        "system_proxy": "never",
        "home_writes": "forbidden — caches remapped under ROOT",
    }


def gc_tmp(*, max_age_hours: float = 24.0, dry_run: bool = False) -> dict[str, Any]:
    """Delete files/dirs under tmp/ older than max_age_hours."""
    ensure_layout()
    tmp = safe_resolve(TMP_DIR)
    tmp.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - max_age_hours * 3600
    removed: list[str] = []
    kept = 0
    bytes_freed = 0
    for item in list(tmp.iterdir()):
        try:
            mtime = item.stat().st_mtime
        except Exception:
            continue
        if mtime >= cutoff:
            kept += 1
            continue
        try:
            if item.is_file():
                size = item.stat().st_size
                if not dry_run:
                    item.unlink(missing_ok=True)
                bytes_freed += size
            elif item.is_dir():
                # size estimate
                for f in item.rglob("*"):
                    if f.is_file():
                        try:
                            bytes_freed += f.stat().st_size
                        except Exception:
                            pass
                if not dry_run:
                    shutil.rmtree(item, ignore_errors=True)
            removed.append(str(item.relative_to(ROOT)))
        except Exception:
            pass
    return {
        "ok": True,
        "removed": removed,
        "kept": kept,
        "bytes_freed": bytes_freed,
        "max_age_hours": max_age_hours,
        "dry_run": dry_run,
    }
