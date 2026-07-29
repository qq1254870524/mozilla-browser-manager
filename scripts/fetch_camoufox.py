#!/usr/bin/env python3
"""Fetch Camoufox browser into ROOT/runtime/cache/camoufox with mirrors + resume.

Official GitHub is often throttled in CN (~200KB/s, multi-hour, easy fail).
This installer:
  1) probes ALL mirror channels in parallel and picks the fastest
  2) multi-connection download + resumes .part files (HTTP Range)
  3) can install from a local zip
  4) never writes outside project ROOT

Examples:
  python scripts/fetch_camoufox.py
  python scripts/fetch_camoufox.py --force
  python scripts/fetch_camoufox.py --zip tmp/camoufox-....zip
  python scripts/fetch_camoufox.py --url https://..../camoufox-....zip
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(ROOT / "scripts"))
from netfetch import download_resume, github_mirrors, human  # type: ignore

# Pinned build (matches common camoufox[geoip] wheel expectations)
VERSION = "152.0.4-beta.28"
TAG = f"v{VERSION}"

OS_MAP = {"Windows": "win", "Linux": "lin", "Darwin": "mac"}
ARCH_MAP = {
    "AMD64": "x86_64",
    "x86_64": "x86_64",
    "x86": "x86_64",
    "i386": "i686",
    "i686": "i686",
    "ARM64": "arm64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

# GitHub release asset is ~492MB (win) / ~630MB (lin)
MIN_ZIP_BYTES = 80 * 1024 * 1024


def os_arch() -> tuple[str, str]:
    os_key = OS_MAP.get(platform.system())
    if not os_key:
        raise SystemExit(f"unsupported OS: {platform.system()}")
    arch = ARCH_MAP.get(platform.machine(), "x86_64")
    if os_key == "win" and arch not in ("x86_64", "i686"):
        arch = "x86_64"
    if os_key == "mac" and arch not in ("x86_64", "arm64"):
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
    return os_key, arch


def asset_name(os_key: str, arch: str) -> str:
    return f"camoufox-{VERSION}-{os_key}.{arch}.zip"


def github_url(os_key: str, arch: str) -> str:
    return (
        f"https://github.com/daijro/camoufox/releases/download/{TAG}/"
        f"{asset_name(os_key, arch)}"
    )


def install_dir() -> Path:
    d = ROOT / "runtime" / "cache" / "camoufox"
    d.mkdir(parents=True, exist_ok=True)
    # Force libraries that honor XDG to stay in ROOT
    os.environ["XDG_CACHE_HOME"] = str(ROOT / "runtime" / "cache")
    return d


def already_installed(os_key: str) -> Path | None:
    root = install_dir()
    names = {
        "win": ("camoufox.exe", "camoufox-bin", "camoufox"),
        "lin": ("camoufox-bin", "camoufox"),
        "mac": ("camoufox",),
    }[os_key]
    # config active
    cfg = root / "config.json"
    cands: list[Path] = []
    if cfg.exists():
        try:
            rel = json.loads(cfg.read_text(encoding="utf-8")).get("active_version")
            if rel:
                cands.append(root / str(rel))
        except Exception:
            pass
    browsers = root / "browsers"
    if browsers.exists():
        for repo in browsers.iterdir():
            if repo.is_dir():
                for ver in sorted(repo.iterdir(), reverse=True):
                    if ver.is_dir():
                        cands.append(ver)
    cands.append(root)
    for base in cands:
        for n in names:
            p = base / n
            if p.is_file() and p.stat().st_size > 10_000:
                return p
            if os_key == "mac":
                mac = base / "Camoufox.app" / "Contents" / "MacOS" / "camoufox"
                if mac.is_file():
                    return mac
    return None


def install_zip(zip_path: Path, os_key: str) -> Path:
    """Extract zip into multiversion layout under runtime/cache/camoufox."""
    if not zip_path.is_file():
        raise SystemExit(f"zip not found: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise SystemExit(f"not a zip: {zip_path}")

    root = install_dir()
    ver_dir = root / "browsers" / "official" / f"{VERSION}-local"
    if ver_dir.exists():
        shutil.rmtree(ver_dir)
    ver_dir.mkdir(parents=True, exist_ok=True)

    print(f"[camoufox] extracting -> {ver_dir}")
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            raise SystemExit(f"corrupt zip member: {bad}")
        zf.extractall(ver_dir)

    # Some zips contain a single top-level folder — flatten if needed
    children = [p for p in ver_dir.iterdir() if p.name not in (".", "..")]
    if len(children) == 1 and children[0].is_dir():
        top = children[0]
        # if binary not at ver_dir root, move up
        bins = ("camoufox.exe", "camoufox-bin", "camoufox")
        if not any((ver_dir / b).exists() for b in bins) and any((top / b).exists() for b in bins):
            for item in top.iterdir():
                target = ver_dir / item.name
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                shutil.move(str(item), str(target))
            try:
                top.rmdir()
            except OSError:
                pass

    meta = {
        "version": "152.0.4",
        "build": "beta.28",
        "prerelease": True,
        "sha256": None,
        "source": "fetch_camoufox.py",
        "os": os_key,
        "zip": zip_path.name,
    }
    (ver_dir / "version.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # executable bits (posix)
    for name in ("camoufox-bin", "camoufox", "camoufox.exe"):
        f = ver_dir / name
        if f.exists() and os_key != "win":
            f.chmod(f.stat().st_mode | 0o755)

    (root / ".0.5_FLAG").touch()
    cfg_path = root / "config.json"
    data = {}
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["active_version"] = f"browsers/official/{VERSION}-local"
    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # direct check in ver_dir first
    bin_path = None
    for n in ("camoufox.exe", "camoufox-bin", "camoufox"):
        cand = ver_dir / n
        if cand.is_file() and cand.stat().st_size > 10_000:
            bin_path = cand
            break
    if bin_path is None:
        bin_path = already_installed(os_key)
    if not bin_path:
        raise SystemExit(
            f"extract ok but binary not found under {ver_dir}. "
            f"contents: {[p.name for p in ver_dir.iterdir()][:20]}"
        )
    print(f"[camoufox] active={data['active_version']}")
    print(f"[camoufox] binary={bin_path}")
    return bin_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Camoufox fetch with mirrors + resume (ROOT-locked)")
    ap.add_argument("--force", action="store_true", help="re-download even if installed")
    ap.add_argument("--zip", type=str, default="", help="install from local zip path (under ROOT preferred)")
    ap.add_argument("--url", type=str, default="", help="override primary download URL")
    ap.add_argument("--keep-zip", action="store_true", help="keep zip under tmp/ after install")
    args = ap.parse_args(argv)

    if not (ROOT / "app" / "mozilla_manager").is_dir():
        print(f"[camoufox][ERROR] not project root: {ROOT}", file=sys.stderr)
        return 1

    os_key, arch = os_arch()
    print(f"[camoufox] ROOT={ROOT}")
    print(f"[camoufox] target OS={os_key} arch={arch} version={VERSION}")

    if not args.force:
        hit = already_installed(os_key)
        if hit:
            print(f"[camoufox] already installed: {hit}")
            return 0

    # local zip
    zip_path: Path | None = None
    if args.zip:
        z = Path(args.zip)
        if not z.is_absolute():
            z = (ROOT / z).resolve()
        # must stay under ROOT
        try:
            z.relative_to(ROOT.resolve())
        except ValueError:
            # allow absolute outside with warning? contract says ROOT only for project files
            # still allow read-only external zip to install into ROOT
            print(f"[camoufox] warning: zip outside ROOT (read-only): {z}")
        zip_path = z
    else:
        # auto-detect local tmp zip for this OS
        auto = ROOT / "tmp" / asset_name(os_key, arch)
        if auto.is_file() and auto.stat().st_size >= MIN_ZIP_BYTES and zipfile.is_zipfile(auto):
            print(f"[camoufox] found local zip {auto}")
            zip_path = auto

    if zip_path is None:
        primary = args.url.strip() or github_url(os_key, arch)
        urls = github_mirrors(primary)
        # If user passed official win URL form, still expand mirrors
        dest = ROOT / "tmp" / asset_name(os_key, arch)
        # if partial exists print hint
        part = dest.with_suffix(dest.suffix + ".part")
        if part.exists():
            print(f"[camoufox] continuing partial {part} ({human(part.stat().st_size)})")
        zip_path = download_resume(urls, dest, min_bytes=MIN_ZIP_BYTES, label="camoufox", expect_zip=True)

    install_zip(zip_path, os_key)

    if not args.keep_zip and zip_path.is_file() and zip_path.resolve().is_relative_to(ROOT.resolve()):
        # keep by default actually — large re-download pain. Only delete with env.
        if os.environ.get("CAMOUFOX_DELETE_ZIP") == "1":
            zip_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            print("[camoufox] deleted zip (CAMOUFOX_DELETE_ZIP=1)")
        else:
            print(f"[camoufox] zip kept at {zip_path} (resume/reinstall)")

    print("[camoufox] DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
