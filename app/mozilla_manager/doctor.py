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
    # Camoufox real path: runtime/cache/camoufox/geoip/mmdb/<name>-ipv4.mmdb
    # Legacy/plain: runtime/cache/camoufox/geoip/*.mmdb
    geo_dir = cf_root / "geoip"
    geoip = []
    if geo_dir.exists():
        geoip = list(geo_dir.glob("*.mmdb")) + list((geo_dir / "mmdb").glob("*.mmdb")) if (geo_dir / "mmdb").exists() else list(geo_dir.glob("*.mmdb"))
        if (geo_dir / "mmdb").exists():
            geoip = list(geo_dir.glob("*.mmdb")) + list((geo_dir / "mmdb").glob("*.mmdb"))
    # de-dup by resolve
    seen = set()
    uniq = []
    for g in geoip:
        try:
            key = str(g.resolve())
        except Exception:
            key = str(g)
        if key in seen:
            continue
        seen.add(key)
        if g.is_file() and g.stat().st_size > 1_000_000:
            uniq.append(g)
    geoip = uniq
    items.append(
        CheckItem(
            "camoufox_geoip",
            bool(geoip),
            f"{len(geoip)} mmdb files" if geoip else "missing geoip mmdb — 运行「下载依赖」或 install_geoip",
            "warn" if not geoip else "info",
        )
    )

    # rebrowser-patches source + stack readiness
    rp_src = PATCHES_DIR / "rebrowser-patches"
    rp_ok = (rp_src / "README.md").exists() or (rp_src / "package.json").exists()
    items.append(
        CheckItem(
            "rebrowser_patches_source",
            rp_ok,
            str(rp_src.relative_to(ROOT)) if rp_ok else "missing — 将由「下载依赖」自动克隆",
            "warn" if not rp_ok else "info",
        )
    )
    # Optional custom chrome: NOT required. rebrowser patches live in pip rebrowser-playwright.
    reb_dir = PATCHES_DIR / "rebrowser"
    reb_bins = []
    if reb_dir.exists():
        # real binaries only (not chrome.path pointer / README)
        allow = {"chrome", "chrome.exe", "chromium", "chromium.exe"}
        reb_bins = [p for p in reb_dir.iterdir() if p.is_file() and p.name.lower() in allow]
    path_file = reb_dir / "chrome.path"
    path_target = ""
    if path_file.is_file():
        try:
            path_target = path_file.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        except Exception:
            path_target = ""
    if reb_bins:
        items.append(
            CheckItem(
                "rebrowser_custom_binary",
                True,
                "自定义内核: " + ", ".join(p.name for p in reb_bins),
                "info",
            )
        )
    elif path_target and Path(path_target).exists():
        items.append(
            CheckItem(
                "rebrowser_custom_binary",
                True,
                f"已挂接默认 Chromium: {path_target}",
                "info",
            )
        )
    else:
        # Still OK — driver-level patch does not need a custom browser binary
        items.append(
            CheckItem(
                "rebrowser_custom_binary",
                True,
                "可选：未放自定义内核（正常）。rebrowser 补丁在 pip 包 rebrowser-playwright，使用 runtime/browsers 内 Chromium",
                "info",
            )
        )
    # Aggregate rebrowser stack
    try:
        import rebrowser_playwright  # noqa: F401
        rb_pkg = True
    except Exception:
        rb_pkg = False
    rb_chromium = bool(pw_chromium)
    stack_ok = rb_pkg and rp_ok and rb_chromium
    items.append(
        CheckItem(
            "rebrowser_stack",
            stack_ok,
            f"pkg={'OK' if rb_pkg else 'MISS'} source={'OK' if rp_ok else 'MISS'} chromium={'OK' if rb_chromium else 'MISS'}",
            "warn" if not stack_ok else "info",
        )
    )
    # patchright stack
    try:
        import patchright  # noqa: F401
        pr_pkg = True
    except Exception:
        pr_pkg = False
    items.append(
        CheckItem(
            "patchright_stack",
            pr_pkg and bool(pw_chromium or pr_shell),
            f"pkg={'OK' if pr_pkg else 'MISS'} browsers={'OK' if (pw_chromium or pr_shell) else 'MISS'}",
            "warn" if not (pr_pkg and (pw_chromium or pr_shell)) else "info",
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
