#!/usr/bin/env python3
"""ROOT-locked multi-mirror HTTP downloader with resume (.part).

Used by Chromium / Camoufox / mihomo fetchers.
"""
from __future__ import annotations

import time
import zipfile
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def human(n: float | int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if x < 1024 or unit == "GB":
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024.0
    return str(n)


def github_mirrors(primary: str) -> list[str]:
    clean = primary.strip()
    extras = [
        clean,
        f"https://ghfast.top/{clean}",
        f"https://ghproxy.net/{clean}",
        f"https://mirror.ghproxy.com/{clean}",
        f"https://gitclone.com/{clean}",
        f"https://gh.ddlc.top/{clean}",
        f"https://github.moeyy.xyz/{clean}",
        f"https://gh-proxy.com/{clean}",
    ]
    out: list[str] = []
    seen: set[str] = set()
    for u in extras:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def playwright_mirrors(rel_path: str) -> list[str]:
    """rel_path like builds/cft/148.0.7778.96/win64/chrome-win64.zip"""
    rel = rel_path.lstrip("/")
    hosts = [
        "https://cdn.playwright.dev",
        "https://npmmirror.com/mirrors/playwright",
        "https://cdn.npmmirror.com/binaries/playwright",
        "https://playwright.azureedge.net",
        "https://playwright.download.prss.microsoft.com/dbazure/download/playwright",
    ]
    return [f"{h}/{rel}" for h in hosts]


def download_resume(
    urls: Iterable[str],
    dest: Path,
    *,
    min_bytes: int = 1_000_000,
    timeout: int = 45,
    label: str = "download",
    expect_zip: bool = False,
) -> Path:
    """Download with HTTP Range resume across mirrors. Keeps dest.part until complete."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    last_err: Exception | None = None

    # already complete?
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        if expect_zip and not zipfile.is_zipfile(dest):
            dest.unlink(missing_ok=True)
        else:
            print(f"[{label}] already have {dest} ({human(dest.stat().st_size)})")
            return dest

    for url in urls:
        existing = part.stat().st_size if part.exists() else 0
        headers = {
            "User-Agent": "Mozilla/5.0 MozillaManager-NetFetch/1.2",
            "Accept": "*/*",
        }
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"
            print(f"[{label}] resume {human(existing)} <- {url}")
        else:
            print(f"[{label}] get <- {url}")

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", 200) or 200
                if existing and status == 200:
                    print(f"[{label}] server ignored Range, restart")
                    existing = 0
                mode = "ab" if existing and status == 206 else "wb"
                if mode == "wb" and part.exists():
                    part.unlink()
                    existing = 0

                cl = resp.headers.get("Content-Length")
                cl_i = int(cl) if cl and str(cl).isdigit() else 0
                full_size = (existing + cl_i) if status == 206 and cl_i else cl_i

                t0 = time.time()
                got = existing
                last_print = 0.0
                with open(part, mode) as f:
                    while True:
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        now = time.time()
                        if now - last_print >= 1.0:
                            speed = (got - existing) / max(now - t0, 0.001)
                            if full_size:
                                pct = got * 100.0 / full_size
                                print(
                                    f"\r[{label}] {pct:5.1f}% {human(got)}/{human(full_size)} "
                                    f"{human(int(speed))}/s   ",
                                    end="",
                                    flush=True,
                                )
                            else:
                                print(
                                    f"\r[{label}] {human(got)} {human(int(speed))}/s   ",
                                    end="",
                                    flush=True,
                                )
                            last_print = now
                print()

            size = part.stat().st_size
            if size < min_bytes:
                raise RuntimeError(f"too small ({size} B), likely error page")
            if expect_zip and not zipfile.is_zipfile(part):
                raise RuntimeError("not a valid zip")
            part.replace(dest)
            print(f"[{label}] saved {dest} ({human(dest.stat().st_size)})")
            return dest
        except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as e:
            last_err = e
            print(f"\n[{label}] mirror fail: {e}")
            if part.exists() and part.stat().st_size < 64_000:
                try:
                    part.unlink()
                except OSError:
                    pass
            continue

    raise RuntimeError(f"[{label}] all mirrors failed: {last_err}")
