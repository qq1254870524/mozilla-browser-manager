#!/usr/bin/env python3
"""One-click dual-platform dependency installer (ROOT-locked).

Canonical DEV root : /home/baoge/Mozilla
Windows runtime    : C:\\Users\\zhang\\Desktop\\Mozilla

Detects the *current* OS and downloads only what that OS needs:
  - Python venv + requirements.txt (shared)
  - Playwright / Patchright / rebrowser Chromium (OS-native)
  - Camoufox + geoip (OS-native)
  - mihomo binary (linux amd64 / windows amd64)
  - layout dirs under ROOT only

Usage:
  python scripts/install_all_deps.py
  python scripts/install_all_deps.py --skip-optional
  python scripts/install_all_deps.py --force-mihomo
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "requirements.txt"
VENV = ROOT / ".venv"
IS_WIN = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
ARCH = platform.machine().lower()


def _die(msg: str, code: int = 1) -> None:
    print(f"[install][ERROR] {msg}", file=sys.stderr)
    raise SystemExit(code)


def _step(n: str, title: str) -> None:
    print()
    print("=" * 60)
    print(f"[{n}] {title}")
    print("=" * 60)


def _run(cmd: list[str], *, check: bool = True, env: dict | None = None) -> int:
    print("[install] $", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT), env=env)
    if check and r.returncode != 0:
        _die(f"command failed ({r.returncode}): {' '.join(cmd)}")
    return r.returncode


def ensure_root_ok() -> None:
    if not (ROOT / "app" / "mozilla_manager").is_dir():
        _die(f"not project root: {ROOT}")
    if not REQ.is_file():
        _die(f"missing {REQ}")
    # refuse accidental System32 / weird places on Windows markers
    s = str(ROOT).replace("/", "\\").lower()
    if "\\windows\\system32" in s or "\\windows\\syswow64" in s:
        _die(f"refusing system directory ROOT={ROOT}")
    print(f"[install] ROOT={ROOT}")
    print(f"[install] OS={platform.system()} arch={ARCH} python={sys.version.split()[0]}")


def layout() -> None:
    for rel in (
        "runtime/browsers",
        "runtime/mihomo",
        "runtime/patches/rebrowser",
        "runtime/patches/rebrowser-patches",
        "runtime/cache/camoufox",
        "runtime/cache/camoufox/geoip",
        "runtime/extensions",
        "runtime/nodes/subs",
        "runtime/nodes/exports",
        "runtime/nodes/imports",
        "runtime/nodes/mihomo",
        "runtime/vendors",
        "runtime/xdg-config",
        "runtime/xdg-data",
        "logs",
        "tmp",
        "tmp/wheels",
        "data/profiles",
        "data/nodes",
        "data/exports",
        "data/env_packs",
    ):
        (ROOT / rel).mkdir(parents=True, exist_ok=True)


def venv_python() -> Path:
    if IS_WIN:
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def ensure_venv() -> Path:
    py = venv_python()
    if py.is_file():
        print(f"[install] venv OK: {py}")
        return py
    print(f"[install] creating venv -> {VENV}")
    # Prefer current interpreter (already chosen by launcher)
    _run([sys.executable, "-m", "venv", str(VENV)])
    py = venv_python()
    if not py.is_file():
        _die(f"venv python missing after create: {py}")
    return py


def env_for(py: Path) -> dict[str, str]:
    e = os.environ.copy()
    e["VIRTUAL_ENV"] = str(VENV)
    e["PYTHONPATH"] = str(ROOT / "app")
    e["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / "runtime" / "browsers")
    e["XDG_CACHE_HOME"] = str(ROOT / "runtime" / "cache")
    e["XDG_CONFIG_HOME"] = str(ROOT / "runtime" / "xdg-config")
    e["XDG_DATA_HOME"] = str(ROOT / "runtime" / "xdg-data")
    e["MOZILLA_MANAGER_ROOT"] = str(ROOT)
    # Put venv scripts first
    if IS_WIN:
        scripts = str(VENV / "Scripts")
        e["PATH"] = scripts + os.pathsep + e.get("PATH", "")
    else:
        e["PATH"] = str(VENV / "bin") + os.pathsep + e.get("PATH", "")
    # Camoufox / playwright caches under ROOT
    e["CAMOUFOX_CACHE"] = str(ROOT / "runtime" / "cache" / "camoufox")
    return e


def pip_install(py: Path, env: dict[str, str]) -> None:
    _run([str(py), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"], env=env)
    _run([str(py), "-m", "pip", "install", "-r", str(REQ)], env=env)
    # Windows desktop client often needs these extras implicitly via pywebview
    if IS_WIN:
        # pythonnet optional; pywebview uses EdgeChromium/WebView2 by default
        _run([str(py), "-m", "pip", "install", "-U", "pywebview"], env=env, check=False)


def install_browsers(py: Path, env: dict[str, str], *, skip_optional: bool) -> None:
    _step("3", f"Browser kernels for {platform.system()} (mirrors + resume)")
    # Chromium: our fetcher supports multi-mirror + .part resume
    fetch_cr = ROOT / "scripts" / "fetch_chromium.py"
    if fetch_cr.is_file():
        _run([str(py), str(fetch_cr)], env=env, check=False)
    else:
        # fallback official (no good resume)
        env2 = dict(env)
        env2.setdefault("PLAYWRIGHT_DOWNLOAD_HOST", "https://npmmirror.com/mirrors/playwright")
        _run([str(py), "-m", "playwright", "install", "chromium"], env=env2, check=False)
        _run([str(py), "-m", "patchright", "install", "chromium"], env=env2, check=False)
    if skip_optional:
        print("[install] skip optional camoufox/rebrowser")
        return
    fetch_cf = ROOT / "scripts" / "fetch_camoufox.py"
    if fetch_cf.is_file():
        _run([str(py), str(fetch_cf)], env=env, check=False)
    else:
        _run([str(py), "-m", "camoufox", "fetch"], env=env, check=False)
    # rebrowser uses playwright-like browsers path; try mirror host
    env2 = dict(env)
    env2.setdefault("PLAYWRIGHT_DOWNLOAD_HOST", "https://npmmirror.com/mirrors/playwright")
    _run([str(py), "-m", "rebrowser_playwright", "install", "chromium"], env=env2, check=False)


def download(url: str, dest: Path, *, timeout: int = 180) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MozillaManagerInstaller/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dest.write_bytes(r.read())


def install_geoip() -> None:
    """Install MaxMind GeoLite2 city mmdb for Camoufox.

    Camoufox (with XDG_CACHE_HOME=runtime/cache) expects:
      runtime/cache/camoufox/geoip/mmdb/maxmind geolite2-ipv4.mmdb
      runtime/cache/camoufox/geoip/mmdb/maxmind geolite2-ipv6.mmdb
      runtime/cache/camoufox/geoip/config.yml
    We also keep plain copies under geoip/ for doctor readability.
    """
    _step("4", "Camoufox geoip (mirrors)")
    base = ROOT / "runtime" / "cache" / "camoufox" / "geoip"
    mmdb_dir = base / "mmdb"
    base.mkdir(parents=True, exist_ok=True)
    mmdb_dir.mkdir(parents=True, exist_ok=True)

    assets = [
        (
            "geolite2-city-ipv4.mmdb",
            "maxmind geolite2-ipv4.mmdb",
            [
                "https://cdn.jsdelivr.net/npm/@ip-location-db/geolite2-city-mmdb/geolite2-city-ipv4.mmdb",
                "https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/geolite2-city-mmdb/geolite2-city-ipv4.mmdb",
                "https://ghfast.top/https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/geolite2-city-mmdb/geolite2-city-ipv4.mmdb",
            ],
        ),
        (
            "geolite2-city-ipv6.mmdb",
            "maxmind geolite2-ipv6.mmdb",
            [
                "https://cdn.jsdelivr.net/npm/@ip-location-db/geolite2-city-mmdb/geolite2-city-ipv6.mmdb",
                "https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/geolite2-city-mmdb/geolite2-city-ipv6.mmdb",
                "https://ghfast.top/https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/geolite2-city-mmdb/geolite2-city-ipv6.mmdb",
            ],
        ),
    ]

    for plain_name, cf_name, urls in assets:
        plain = base / plain_name
        cf_path = mmdb_dir / cf_name
        # reuse any existing good copy
        src_existing = None
        for cand in (cf_path, plain):
            if cand.exists() and cand.stat().st_size > 1_000_000:
                src_existing = cand
                break
        if src_existing is not None:
            for dest in (plain, cf_path):
                if dest != src_existing and (not dest.exists() or dest.stat().st_size < 1_000_000):
                    try:
                        dest.write_bytes(src_existing.read_bytes())
                    except Exception:
                        pass
            print(f"[geoip] ok {plain_name} ({src_existing.stat().st_size})")
            continue

        print(f"[geoip] download {plain_name}")
        data = None
        last_err = None
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MozillaManagerInstaller/1.0"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = r.read()
                if data and len(data) > 1_000_000:
                    print(f"[geoip] got {plain_name} via {url.split('/')[2]} ({len(data)} bytes)")
                    break
                data = None
            except Exception as e:
                last_err = e
                data = None
        if not data:
            print(f"[geoip] fail {plain_name}: {last_err}")
            continue
        plain.write_bytes(data)
        cf_path.write_bytes(data)
        print(f"[geoip] saved {plain_name} + camoufox mmdb/{cf_name}")

    # Camoufox active source config
    cfg = base / "config.yml"
    try:
        cfg.write_text("name: MaxMind GeoLite2\n", encoding="utf-8")
        print(f"[geoip] config.yml -> MaxMind GeoLite2")
    except Exception as e:
        print(f"[geoip] config.yml fail: {e}")


def mihomo_target() -> tuple[Path, list[str], bool]:
    """Return (bin_path, urls, is_gzip)."""
    ver = "v1.19.12"
    base = f"https://github.com/MetaCubeX/mihomo/releases/download/{ver}"
    mirror = f"https://ghfast.top/{base}"
    # normalize arch
    arch = ARCH
    if arch in ("x86_64", "amd64"):
        arch_tag = "amd64"
    elif arch in ("aarch64", "arm64"):
        arch_tag = "arm64"
    else:
        arch_tag = "amd64"

    dest_dir = ROOT / "runtime" / "mihomo"
    if IS_WIN:
        name = f"mihomo-windows-{arch_tag}-{ver}.zip"
        bin_path = dest_dir / "mihomo.exe"
        # zip asset
        urls = [f"{base}/{name}", f"{mirror}/{name}"]
        return bin_path, urls, False  # zip handled specially
    else:
        # linux gz
        name = f"mihomo-linux-{arch_tag}-{ver}.gz"
        bin_path = dest_dir / "mihomo"
        urls = [f"{base}/{name}", f"{mirror}/{name}"]
        return bin_path, urls, True


def install_mihomo(*, force: bool = False) -> None:
    import gzip
    import io
    import zipfile
    import sys as _sys

    _step("6", f"mihomo proxy core ({platform.system()}) — mirrors + resume")
    _sys.path.insert(0, str(ROOT / "scripts"))
    from netfetch import download_resume, github_mirrors  # type: ignore

    bin_path, urls, is_gz = mihomo_target()
    # expand github mirrors for each primary url
    all_urls: list[str] = []
    for u in urls:
        all_urls.extend(github_mirrors(u))
    # de-dup
    seen = set()
    mirrors = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            mirrors.append(u)

    dest_dir = bin_path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    if bin_path.exists() and bin_path.stat().st_size > 1_000_000 and not force:
        print(f"[mihomo] present {bin_path} ({bin_path.stat().st_size})")
        return

    # download archive with resume
    if is_gz or (mirrors and mirrors[0].endswith(".gz")):
        arch_path = dest_dir / "mihomo.download.gz"
        download_resume(mirrors, arch_path, min_bytes=1_000_000, label="mihomo", expect_zip=False)
        raw = gzip.decompress(arch_path.read_bytes())
        bin_path.write_bytes(raw)
    else:
        arch_path = dest_dir / "mihomo.download.zip"
        download_resume(mirrors, arch_path, min_bytes=1_000_000, label="mihomo", expect_zip=True)
        with zipfile.ZipFile(arch_path) as zf:
            members = zf.namelist()
            print(f"[mihomo] zip members: {members[:8]}")
            cand = None
            for m in members:
                low = m.lower()
                if low.endswith("mihomo.exe") or low.endswith("/mihomo.exe"):
                    cand = m
                    break
            if cand is None:
                for m in members:
                    if m.lower().endswith(".exe") and "mihomo" in m.lower():
                        cand = m
                        break
            if cand is None:
                raise RuntimeError(f"mihomo.exe not in zip: {members[:20]}")
            bin_path.write_bytes(zf.read(cand))
    if not IS_WIN:
        bin_path.chmod(bin_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"[mihomo] ok {bin_path} ({bin_path.stat().st_size})")


def _newest_chromium_exe() -> Path | None:
    """Pick highest-revision chrome under runtime/browsers."""
    bdir = ROOT / "runtime" / "browsers"
    if not bdir.is_dir():
        return None
    found: list[Path] = []
    for pattern in (
        "chromium-*/chrome-win64/chrome.exe",
        "chromium-*/chrome-win/chrome.exe",
        "chromium-*/chrome-linux64/chrome",
        "chromium-*/chrome-linux/chrome",
    ):
        found.extend(bdir.glob(pattern))
    found = [x for x in found if x.is_file()]
    if not found:
        return None

    def rev_key(path: Path) -> int:
        for part in path.parts:
            if part.startswith("chromium-"):
                try:
                    return int(part.split("-", 1)[1])
                except Exception:
                    return 0
        return 0

    found.sort(key=rev_key, reverse=True)
    return found[0]


def ensure_rebrowser_stack() -> None:
    """补齐 rebrowser / patchright 补丁栈（源码 + 默认内核挂接）。

    说明：rebrowser 的「补丁」在 pip 包 rebrowser-playwright 驱动层，
    不需要单独下载改过的 Chrome。自定义 chrome 二进制是可选增强。
    """
    _step("5", "补丁栈 rebrowser / patchright")
    dest = ROOT / "runtime" / "patches" / "rebrowser-patches"
    git = shutil.which("git")
    if (dest / "README.md").exists() or (dest / "package.json").exists():
        print("[补丁] rebrowser-patches 源码: 已就绪")
        if git:
            subprocess.run(
                [git, "-C", str(dest), "pull", "--ff-only"],
                cwd=str(ROOT),
                check=False,
                capture_output=True,
            )
    else:
        if not git:
            print("[补丁] git 不可用，跳过克隆 rebrowser-patches（pip 驱动仍可用）")
        else:
            print("[补丁] 克隆 rebrowser-patches ...")
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [git, "clone", "--depth", "1", "https://github.com/rebrowser/rebrowser-patches.git", str(dest)],
                cwd=str(ROOT),
                check=False,
            )

    # 挂接默认 Chromium，消除「缺少补丁/缺少内核」误解
    reb = ROOT / "runtime" / "patches" / "rebrowser"
    reb.mkdir(parents=True, exist_ok=True)
    readme = reb / "README.txt"
    if not readme.exists():
        readme.write_text(
            "此目录可放置自定义 chrome/chrome.exe（可选）。\n"
            "rebrowser 反检测补丁已包含在 Python 包 rebrowser-playwright 中。\n"
            "未放置自定义内核时，自动使用 runtime/browsers 下的 Chromium。\n"
            "install 会写入 chrome.path 指向当前最新 Chromium。\n",
            encoding="utf-8",
        )
    chrome = _newest_chromium_exe()
    path_file = reb / "chrome.path"
    if chrome is not None:
        # store relative path when possible for portability across WSL/Windows copies
        try:
            rel = chrome.resolve().relative_to(ROOT.resolve())
            path_file.write_text(str(rel).replace("\\", "/") + "\n", encoding="utf-8")
        except Exception:
            path_file.write_text(str(chrome.resolve()) + "\n", encoding="utf-8")
        print(f"[补丁] 默认 Chromium 已挂接: {path_file.read_text(encoding='utf-8').strip()}")
    else:
        print("[补丁] 尚未找到 Chromium，请先完成浏览器内核下载")

    # 确认 pip 补丁包
    try:
        import importlib
        # just informational — actual import is in venv during verify
        print("[补丁] patchright / rebrowser-playwright: 由 requirements.txt 安装（见步骤 2）")
    except Exception:
        pass
    print("[补丁] 说明: 自定义 chrome 二进制=可选；驱动补丁=pip 已打好")


def optional_rebrowser_patches() -> None:
    """Backward-compatible name used by main()."""
    ensure_rebrowser_stack()


def verify(py: Path, env: dict[str, str]) -> None:
    _step("7", "Verify imports + doctor")
    code = """
import importlib
mods = ['playwright','patchright','camoufox','fastapi','uvicorn','webview']
for m in mods:
    try:
        importlib.import_module(m if m!='webview' else 'webview')
        print('OK', m)
    except Exception as e:
        print('FAIL', m, e)
try:
    import rebrowser_playwright
    print('OK rebrowser_playwright')
except Exception as e:
    print('WARN rebrowser_playwright', e)
from pathlib import Path
import platform
root = Path('.').resolve()
mh = root/'runtime'/'mihomo'/('mihomo.exe' if platform.system()=='Windows' else 'mihomo')
print('mihomo', mh.exists(), mh)
print('browsers dir', list((root/'runtime'/'browsers').glob('*'))[:8])
"""
    _run([str(py), "-c", code], env=env, check=False)
    _run([str(py), "-m", "mozilla_manager.cli", "doctor"], env=env, check=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mozilla dual-platform one-click dependency installer")
    ap.add_argument("--skip-optional", action="store_true", help="skip camoufox/rebrowser/patches")
    ap.add_argument("--force-mihomo", action="store_true", help="re-download mihomo")
    ap.add_argument("--skip-doctor", action="store_true")
    args = ap.parse_args(argv)

    ensure_root_ok()
    _step("0", "Layout under ROOT only")
    layout()

    _step("1", "Python venv")
    # If already running inside project venv, reuse; else ensure/create
    py = venv_python()
    if not py.is_file():
        # create with current interpreter
        ensure_venv()
        py = venv_python()
    else:
        print(f"[install] using {py}")
    # If installer was launched with system python, switch work to venv python for pip etc.
    env = env_for(py)

    _step("2", "pip install requirements.txt (shared dual-end deps)")
    pip_install(py, env)

    install_browsers(py, env, skip_optional=args.skip_optional)
    if not args.skip_optional:
        install_geoip()
        optional_rebrowser_patches()
    install_mihomo(force=args.force_mihomo)

    if not args.skip_doctor:
        verify(py, env)

    print()
    print("=" * 60)
    print("[install] DONE")
    print(f"[install] ROOT={ROOT}")
    print(f"[install] OS-specific binaries installed for: {platform.system()} / {ARCH}")
    if IS_WIN:
        print("[install] Next: start_client.bat  or  start_web.bat")
    else:
        print("[install] Next:")
        print(f"  source {VENV}/bin/activate")
        print(f"  export PYTHONPATH={ROOT}/app")
        print(f"  export PLAYWRIGHT_BROWSERS_PATH={ROOT}/runtime/browsers")
        print(f"  python -m mozilla_manager.cli doctor")
        print(f"  bash scripts/run_client.sh   # or bash start.sh")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
