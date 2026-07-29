from __future__ import annotations

import os
import platform
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .paths import BROWSERS_DIR, MIHOMO_DIR, PATCHES_DIR, ROOT, ensure_layout, under_root
from .runtime_manifest import write_manifest


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str
    level: str = "info"  # info|warn|error


def run_doctor() -> dict[str, Any]:
    ensure_layout()
    items: list[CheckItem] = []

    items.append(CheckItem("root", True, str(ROOT)))
    items.append(
        CheckItem(
            "root_writable",
            os.access(ROOT, os.W_OK),
            "writable" if os.access(ROOT, os.W_OK) else "not writable",
            "error" if not os.access(ROOT, os.W_OK) else "info",
        )
    )
    items.append(CheckItem("sandbox_under_root", under_root(BROWSERS_DIR), str(BROWSERS_DIR)))

    # python packages: kernels + patches
    for mod, level in (
        ("playwright", "error"),
        ("patchright", "warn"),
        ("camoufox", "warn"),
        ("httpx", "error"),
        ("pydantic", "error"),
        ("yaml", "error"),
        ("typer", "error"),
    ):
        try:
            __import__(mod if mod != "yaml" else "yaml")
            items.append(CheckItem(f"pkg:{mod}", True, "import ok"))
        except Exception as e:
            items.append(CheckItem(f"pkg:{mod}", False, str(e), level))

    # rebrowser-playwright optional drop-in
    try:
        import rebrowser_playwright  # noqa: F401

        items.append(CheckItem("pkg:rebrowser_playwright", True, "import ok"))
    except Exception:
        items.append(
            CheckItem(
                "pkg:rebrowser_playwright",
                False,
                "not installed (pip install rebrowser-playwright)",
                "warn",
            )
        )

    # browsers path
    pb = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    items.append(
        CheckItem(
            "PLAYWRIGHT_BROWSERS_PATH",
            bool(pb) and under_root(pb),
            pb or "(unset — launch defaults to runtime/browsers)",
            "warn" if not pb else "info",
        )
    )

    # Playwright / Patchright chromium trees
    pw_chromium = list(BROWSERS_DIR.glob("chromium-*")) if BROWSERS_DIR.exists() else []
    items.append(
        CheckItem(
            "playwright_chromium",
            bool(pw_chromium),
            ", ".join(p.name for p in pw_chromium) or "missing — run: python -m playwright install chromium",
            "warn" if not pw_chromium else "info",
        )
    )
    pr_shell = list(BROWSERS_DIR.glob("chromium_headless_shell-*")) if BROWSERS_DIR.exists() else []
    items.append(
        CheckItem(
            "patchright_browsers",
            bool(pr_shell) or bool(pw_chromium),
            f"headless_shell={len(pr_shell)} chromium={len(pw_chromium)}",
            "warn" if not (pr_shell or pw_chromium) else "info",
        )
    )

    # Camoufox browser under ROOT cache
    os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "runtime" / "cache"))
    cf_root = ROOT / "runtime" / "cache" / "camoufox"
    cf_bins = (
        list(cf_root.glob("browsers/*/*/camoufox-bin"))
        + list(cf_root.glob("browsers/*/*/camoufox.exe"))
        + list(cf_root.glob("browsers/*/*/camoufox"))
    )
    items.append(
        CheckItem(
            "camoufox_browser",
            bool(cf_bins),
            str(cf_bins[0].relative_to(ROOT)) if cf_bins else f"missing under {cf_root}",
            "warn" if not cf_bins else "info",
        )
    )
    geoip = list((cf_root / "geoip").glob("*.mmdb")) if (cf_root / "geoip").exists() else []
    items.append(
        CheckItem(
            "camoufox_geoip",
            bool(geoip),
            f"{len(geoip)} mmdb files" if geoip else "missing geoip mmdb",
            "info",
        )
    )

    # rebrowser-patches source
    rp_src = PATCHES_DIR / "rebrowser-patches"
    items.append(
        CheckItem(
            "rebrowser_patches_source",
            (rp_src / "README.md").exists() or (rp_src / "package.json").exists(),
            str(rp_src.relative_to(ROOT)) if rp_src.exists() else "missing runtime/patches/rebrowser-patches",
            "warn" if not rp_src.exists() else "info",
        )
    )
    reb = list((PATCHES_DIR / "rebrowser").glob("chrome*")) if (PATCHES_DIR / "rebrowser").exists() else []
    items.append(
        CheckItem(
            "rebrowser_custom_binary",
            bool(reb),
            ", ".join(str(x.name) for x in reb) or "optional custom chrome under runtime/patches/rebrowser/",
            "info",
        )
    )

    mihomo = MIHOMO_DIR / ("mihomo.exe" if platform.system() == "Windows" else "mihomo")
    items.append(
        CheckItem(
            "mihomo_binary",
            mihomo.exists() and mihomo.stat().st_size > 1_000_000,
            str(mihomo),
            "warn" if not mihomo.exists() else "info",
        )
    )

    usage = shutil.disk_usage(ROOT)
    free_gb = usage.free / (1024**3)
    items.append(
        CheckItem(
            "disk_free_gb",
            free_gb > 2,
            f"{free_gb:.1f} GiB free",
            "error" if free_gb < 1 else ("warn" if free_gb < 2 else "info"),
        )
    )

    # v3 sqlite index
    try:
        from mozilla_manager import db
        path = db.init_db()
        items.append(
            CheckItem("sqlite_app_db", path.exists(), str(path), "error" if not path.exists() else "info")
        )
    except Exception as e:
        items.append(CheckItem("sqlite_app_db", False, str(e), "error"))


    # v5: runtime/nodes local library + turnstile vendor
    try:
        from mozilla_manager.network import node_store
        from mozilla_manager.paths import RUNTIME_NODES_DIR, TURNSTILE_VENDOR_DIR

        subs = node_store.list_sub_names()
        active = node_store.get_active()
        items.append(
            CheckItem(
                "runtime_nodes_store",
                RUNTIME_NODES_DIR.exists(),
                f"active={active} subs={len(subs)} path=runtime/nodes",
                "info",
            )
        )
        ts_ok = (TURNSTILE_VENDOR_DIR / "turnstile_harvester.py").exists()
        items.append(
            CheckItem(
                "turnstile_vendor",
                ts_ok,
                str(TURNSTILE_VENDOR_DIR.relative_to(ROOT)) if ts_ok else "missing runtime/vendors/turnstile-harvester1",
                "warn" if not ts_ok else "info",
            )
        )
    except Exception as e:
        items.append(CheckItem("runtime_nodes_store", False, str(e), "warn"))

    # v6 stealth entropy / TLS personas
    try:
        from mozilla_manager.stealth.entropy import estimate_entropy_bits
        from mozilla_manager.stealth.tls_ja import TLS_PROFILES

        ent = estimate_entropy_bits(None)
        items.append(
            CheckItem(
                "stealth_entropy_model",
                bool(ent.get("meets_138")),
                f"bits={ent.get('entropy_bits')} core={ent.get('core_entropy_bits')} dims={ent.get('dimension_count')} tls={len(TLS_PROFILES)}",
                "warn" if not ent.get("meets_138") else "info",
            )
        )
    except Exception as e:
        items.append(CheckItem("stealth_entropy_model", False, str(e), "warn"))

    manifest = write_manifest()
    hard_ok = not any((not i.ok and i.level == "error") for i in items)
    return {
        "ok": hard_ok,
        "checks": [asdict(i) for i in items],
        "manifest": manifest,
    }
