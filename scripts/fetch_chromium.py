#!/usr/bin/env python3
"""Download Playwright/Patchright Chromium with mirrors + resume into runtime/browsers."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from netfetch import download_resume, human, playwright_mirrors  # type: ignore


def _browsers_json(mod_name: str) -> Path | None:
    try:
        mod = __import__(mod_name)
    except Exception:
        return None
    base = Path(mod.__file__).resolve().parent
    cand = base / "driver" / "package" / "browsers.json"
    return cand if cand.is_file() else None


def _desc(browsers_json: Path, name: str) -> dict:
    data = json.loads(browsers_json.read_text(encoding="utf-8"))
    for b in data.get("browsers", []):
        if b.get("name") == name:
            return b
    raise KeyError(name)


def _platform_asset() -> tuple[str, str]:
    """Return (cft_folder_file, extract_dir_name hint)."""
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        return "win64/chrome-win64.zip", "chrome-win64"
    if system == "Darwin":
        if machine in ("arm64", "aarch64"):
            return "mac-arm64/chrome-mac-arm64.zip", "chrome-mac-arm64"
        return "mac-x64/chrome-mac-x64.zip", "chrome-mac-x64"
    # Linux
    if machine in ("arm64", "aarch64"):
        # older non-cft path sometimes; try cft linux arm not always available
        return "linux64/chrome-linux64.zip", "chrome-linux64"  # fallback name
    return "linux64/chrome-linux64.zip", "chrome-linux64"


def _headless_asset() -> tuple[str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        return "win64/chrome-headless-shell-win64.zip", "chrome-headless-shell-win64"
    if system == "Darwin":
        if machine in ("arm64", "aarch64"):
            return "mac-arm64/chrome-headless-shell-mac-arm64.zip", "chrome-headless-shell-mac-arm64"
        return "mac-x64/chrome-headless-shell-mac-x64.zip", "chrome-headless-shell-mac-x64"
    return "linux64/chrome-headless-shell-linux64.zip", "chrome-headless-shell-linux64"


def _install_one(
    *,
    browser_name: str,
    revision: str,
    browser_version: str,
    rel_suffix: str,
    browsers_dir: Path,
    force: bool,
) -> Path:
    """Download and extract one browser build."""
    # playwright uses chromium-1223 with underscores for hyphenated names replaced
    dir_name = browser_name.replace("-", "_") + f"-{revision}"
    target = browsers_dir / dir_name
    marker = target / "INSTALLATION_COMPLETE"
    if marker.is_file() and not force:
        print(f"[chromium] OK {dir_name} (already installed)")
        return target

    rel = f"builds/cft/{browser_version}/{rel_suffix}"
    urls = playwright_mirrors(rel)
    zip_path = ROOT / "tmp" / f"playwright-{browser_name}-{revision}-{Path(rel_suffix).name}"
    print(f"[chromium] {browser_name} rev={revision} ver={browser_version}")
    print(f"[chromium] path={rel}")
    download_resume(
        urls,
        zip_path,
        min_bytes=5_000_000,
        label=f"chromium:{browser_name}",
        expect_zip=True,
    )

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    print(f"[chromium] extract -> {target}")
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"corrupt zip member {bad}")
        zf.extractall(target)
    (target / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")
    (target / "DEPENDENCIES_VALIDATED").write_text("", encoding="utf-8")
    print(f"[chromium] installed {target} ({human(sum(p.stat().st_size for p in target.rglob('*') if p.is_file()))})")
    return target


def install_from_module(mod_name: str, *, force: bool, with_headless: bool) -> None:
    bj = _browsers_json(mod_name)
    if not bj:
        print(f"[chromium] skip {mod_name}: package not installed")
        return
    browsers_dir = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (ROOT / "runtime" / "browsers"))
    browsers_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)

    cr = _desc(bj, "chromium")
    suffix, _ = _platform_asset()
    _install_one(
        browser_name="chromium",
        revision=str(cr["revision"]),
        browser_version=str(cr.get("browserVersion") or ""),
        rel_suffix=suffix,
        browsers_dir=browsers_dir,
        force=force,
    )
    if with_headless:
        try:
            hs = _desc(bj, "chromium-headless-shell")
            hs_suffix, _ = _headless_asset()
            _install_one(
                browser_name="chromium-headless-shell",
                revision=str(hs["revision"]),
                browser_version=str(hs.get("browserVersion") or cr.get("browserVersion") or ""),
                rel_suffix=hs_suffix,
                browsers_dir=browsers_dir,
                force=force,
            )
        except Exception as e:
            print(f"[chromium] headless-shell skip: {e}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chromium fetch with mirrors + resume")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-headless", action="store_true")
    ap.add_argument("--only", choices=["playwright", "patchright", "both"], default="both")
    args = ap.parse_args(argv)

    if not (ROOT / "app" / "mozilla_manager").is_dir():
        print(f"[chromium][ERROR] bad ROOT {ROOT}", file=sys.stderr)
        return 1
    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    (ROOT / "runtime" / "browsers").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "runtime" / "browsers"))
    os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "runtime" / "cache"))

    print(f"[chromium] ROOT={ROOT}")
    print(f"[chromium] OS={platform.system()} arch={platform.machine()}")
    print(f"[chromium] BROWSERS={os.environ['PLAYWRIGHT_BROWSERS_PATH']}")

    mods = []
    if args.only in ("playwright", "both"):
        mods.append("playwright")
    if args.only in ("patchright", "both"):
        mods.append("patchright")

    errors = []
    for m in mods:
        try:
            print()
            print(f"=== {m} ===")
            install_from_module(m, force=args.force, with_headless=not args.no_headless)
        except Exception as e:
            errors.append(f"{m}: {e}")
            print(f"[chromium][ERROR] {m}: {e}")

    if errors:
        print("[chromium] partial failure:", "; ".join(errors))
        return 1
    print("[chromium] DONE (all resume-capable mirrors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
