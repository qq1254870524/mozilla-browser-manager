from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata
from typing import Any

from .paths import BROWSERS_DIR, MANIFEST_PATH, MIHOMO_DIR, PATCHES_DIR, ROOT, ensure_layout


def _pkg_ver(name: str) -> str | None:
    try:
        return metadata.version(name)
    except Exception:
        return None


def build_manifest() -> dict[str, Any]:
    ensure_layout()
    mihomo = MIHOMO_DIR / ("mihomo.exe" if platform.system() == "Windows" else "mihomo")
    rebrowser = None
    for cand in (
        PATCHES_DIR / "rebrowser" / "chrome",
        PATCHES_DIR / "rebrowser" / "chrome.exe",
    ):
        if cand.exists():
            rebrowser = str(cand.relative_to(ROOT))
            break
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(ROOT),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        },
        "packages": {
            "playwright": _pkg_ver("playwright"),
            "patchright": _pkg_ver("patchright"),
            "camoufox": _pkg_ver("camoufox"),
            "httpx": _pkg_ver("httpx"),
            "pydantic": _pkg_ver("pydantic"),
        },
        "paths": {
            "browsers": str(BROWSERS_DIR),
            "mihomo_bin": str(mihomo),
            "mihomo_present": mihomo.exists(),
            "rebrowser_bin": rebrowser,
            "patches": str(PATCHES_DIR),
        },
        "engines": {
            "kernels": ["camoufox", "pw_chromium"],
            "patches": ["none", "patchright", "rebrowser"],
        },
    }


def write_manifest() -> dict[str, Any]:
    data = build_manifest()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def read_manifest() -> dict[str, Any] | None:
    if not MANIFEST_PATH.exists():
        return None
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
