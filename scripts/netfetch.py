#!/usr/bin/env python3
"""ROOT-locked multi-mirror HTTP downloader with:
  - parallel speed probe of ALL mirrors → pick fastest
  - multi-connection ranged download on best channel
  - HTTP Range resume (.part / .parts/)
  - auto-switch if a channel is too slow

Used by Chromium / Camoufox / mihomo fetchers.
"""
from __future__ import annotations

import os
import shutil
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 MozillaManager-NetFetch/2.1"


def human(n: float | int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if x < 1024 or unit == "GB":
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024.0
    return str(n)


def human_speed(bps: float) -> str:
    return f"{human(bps)}/s"


def _short(url: str, width: int = 72) -> str:
    if len(url) <= width:
        return url
    return url[: width - 3] + "..."


def github_mirrors(primary: str) -> list[str]:
    """Expand a GitHub (or any) URL into many CN-friendly mirror candidates."""
    clean = primary.strip()
    extras: list[str] = [clean]

    prefixes = [
        "https://ghfast.top/",
        "https://ghproxy.net/",
        "https://mirror.ghproxy.com/",
        "https://gh.ddlc.top/",
        "https://github.moeyy.xyz/",
        "https://gh-proxy.com/",
        "https://ghproxy.com/",
        "https://gh.api.99988866.xyz/",
        "https://wget.la/",
        "https://gh.llkk.cc/",
        "https://gh.tryxd.cn/",
        "https://ghpx.net/",
        "https://gitclone.com/",
        "https://slink.ltd/",
        "https://gh.nxnow.top/",
        "https://gh.zwy.me/",
    ]
    for p in prefixes:
        extras.append(p + clean)

    try:
        u = urlparse(clean)
        if u.netloc in ("github.com", "www.github.com"):
            path = u.path + (("?" + u.query) if u.query else "")
            extras.extend(
                [
                    f"https://kkgithub.com{path}",
                    f"https://bgithub.xyz{path}",
                    f"https://github.ur1.fun{path}",
                    f"https://gh.ddlc.top/https://github.com{path}",
                ]
            )
    except Exception:
        pass

    out: list[str] = []
    seen: set[str] = set()
    for u in extras:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def playwright_mirrors(rel_path: str) -> list[str]:
    rel = rel_path.lstrip("/")
    hosts = [
        "https://npmmirror.com/mirrors/playwright",
        "https://cdn.npmmirror.com/binaries/playwright",
        "https://cdn.playwright.dev",
        "https://playwright.azureedge.net",
        "https://playwright.download.prss.microsoft.com/dbazure/download/playwright",
        "https://cdn.playwright.dev/dbazure/download/playwright",
    ]
    return [f"{h}/{rel}" for h in hosts]


def probe_mirror(
    url: str,
    *,
    probe_bytes: int = 512 * 1024,
    timeout: float = 10.0,
) -> dict:
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Range": f"bytes=0-{probe_bytes - 1}",
    }
    t0 = time.time()
    got = 0
    err = None
    status = 0
    supports_range = False
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200) or 200
            supports_range = status == 206 or resp.headers.get("Accept-Ranges", "").lower() == "bytes"
            while got < probe_bytes:
                if time.time() - t0 > timeout:
                    break
                chunk = resp.read(min(65536, probe_bytes - got))
                if not chunk:
                    break
                got += len(chunk)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    elapsed = max(time.time() - t0, 0.001)
    speed = got / elapsed if got else 0.0
    ok = got >= max(32 * 1024, probe_bytes // 8) and err is None
    return {
        "url": url,
        "ok": ok,
        "bytes": got,
        "elapsed": elapsed,
        "speed": speed,
        "status": status,
        "supports_range": supports_range or status == 206,
        "error": err,
    }


def rank_mirrors(
    urls: Iterable[str],
    *,
    label: str = "download",
    probe_bytes: int = 512 * 1024,
    timeout: float = 10.0,
    workers: int = 16,
) -> list[dict]:
    url_list: list[str] = []
    seen: set[str] = set()
    for u in urls:
        u = (u or "").strip()
        if u and u not in seen:
            seen.add(u)
            url_list.append(u)
    if not url_list:
        return []

    print(f"[{label}] 测速中：并行探测 {len(url_list)} 条通道...")
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(url_list))) as ex:
        futs = {
            ex.submit(probe_mirror, u, probe_bytes=probe_bytes, timeout=timeout): u
            for u in url_list
        }
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                results.append(fut.result())
            except Exception as e:
                results.append(
                    {
                        "url": futs[fut],
                        "ok": False,
                        "bytes": 0,
                        "elapsed": 0,
                        "speed": 0.0,
                        "status": 0,
                        "supports_range": False,
                        "error": str(e),
                    }
                )
            print(f"\r[{label}] 测速进度 {done}/{len(url_list)}   ", end="", flush=True)
    print()

    results.sort(key=lambda r: (not r["ok"], -r["speed"]))
    print(f"[{label}] ——— 通道测速结果（快 → 慢）———")
    for i, r in enumerate(results, 1):
        if r["ok"]:
            rng = "Range✓" if r.get("supports_range") else "Range?"
            print(
                f"[{label}]  #{i:02d}  {human_speed(r['speed']):>12}  {rng}  "
                f"读{human(r['bytes']):>8}  {_short(r['url'])}"
            )
        else:
            err = (r.get("error") or "fail")[:55]
            print(f"[{label}]  #{i:02d}  {'FAIL':>12}  {err}  {_short(r['url'])}")
    ok_n = sum(1 for r in results if r["ok"])
    print(f"[{label}] 可用 {ok_n}/{len(results)}")
    if ok_n:
        best = next(r for r in results if r["ok"])
        print(f"[{label}] ★ 最快通道 {human_speed(best['speed'])}")
        print(f"[{label}]   {_short(best['url'], 100)}")
    return results


def _head_size(url: str, timeout: float = 15.0) -> tuple[int, bool]:
    """Return (size, range_ok). size=0 if unknown."""
    # Try ranged probe first
    try:
        req = Request(
            url,
            headers={"User-Agent": UA, "Range": "bytes=0-0"},
            method="GET",
        )
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200) or 200
            if status == 206:
                cr = resp.headers.get("Content-Range", "")
                # bytes 0-0/12345
                if "/" in cr:
                    total = cr.split("/")[-1]
                    if total.isdigit():
                        resp.read(16)
                        return int(total), True
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit():
                return int(cl), status == 206
    except Exception:
        pass
    try:
        req = Request(url, headers={"User-Agent": UA}, method="HEAD")
        with urlopen(req, timeout=timeout) as resp:
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit():
                ar = resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                return int(cl), ar
    except Exception:
        pass
    return 0, False


def _fetch_range_to_file(
    url: str,
    start: int,
    end: int,
    out: Path,
    *,
    timeout: int = 60,
    label: str = "part",
) -> int:
    """Download inclusive byte range [start, end] into out (resume if partial)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = out.stat().st_size if out.exists() else 0
    expect = end - start + 1
    if existing >= expect:
        return expect
    # resume within this slice
    cur = start + existing
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Range": f"bytes={cur}-{end}",
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200) or 200
        mode = "ab"
        if status == 200:
            # server ignored range — cannot multi; signal caller
            raise RuntimeError("server ignored range for multi-connection")
        with open(out, mode) as f:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    got = out.stat().st_size
    if got < expect:
        raise RuntimeError(f"{label} incomplete {got}/{expect}")
    return got


def download_multi(
    url: str,
    dest: Path,
    *,
    total_size: int,
    connections: int = 8,
    timeout: int = 60,
    label: str = "download",
    min_bytes: int = 1_000_000,
    expect_zip: bool = False,
) -> Path:
    """Multi-connection ranged download with per-slice resume."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    parts_dir = dest.with_suffix(dest.suffix + ".parts")
    parts_dir.mkdir(parents=True, exist_ok=True)

    connections = max(2, min(connections, 16))
    # split
    chunk = total_size // connections
    ranges = []
    for i in range(connections):
        start = i * chunk
        end = (total_size - 1) if i == connections - 1 else (start + chunk - 1)
        ranges.append((i, start, end))

    print(
        f"[{label}] 多线程下载 ×{connections}  总大小 {human(total_size)}  <- {_short(url, 80)}"
    )

    def work(item: tuple[int, int, int]) -> tuple[int, int]:
        i, start, end = item
        part_file = parts_dir / f"{i:02d}.slice"
        n = _fetch_range_to_file(url, start, end, part_file, timeout=timeout, label=f"slice{i}")
        return i, n

    t0 = time.time()
    done_bytes = 0
    # pre-count existing
    for i, start, end in ranges:
        pf = parts_dir / f"{i:02d}.slice"
        if pf.exists():
            done_bytes += min(pf.stat().st_size, end - start + 1)

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=connections) as ex:
        futs = [ex.submit(work, item) for item in ranges]
        finished = 0
        for fut in as_completed(futs):
            try:
                i, n = fut.result()
                finished += 1
                # recompute total done
                got = 0
                for j, start, end in ranges:
                    pf = parts_dir / f"{j:02d}.slice"
                    if pf.exists():
                        got += min(pf.stat().st_size, end - start + 1)
                speed = got / max(time.time() - t0, 0.001)
                pct = got * 100.0 / total_size
                print(
                    f"\r[{label}] 分片 {finished}/{connections}  {pct:5.1f}% "
                    f"{human(got)}/{human(total_size)}  {human_speed(speed)}   ",
                    end="",
                    flush=True,
                )
            except Exception as e:
                errors.append(str(e))
    print()
    if errors:
        raise RuntimeError(f"multi-download errors: {errors[:3]}")

    # merge
    tmp_out = dest.with_suffix(dest.suffix + ".merging")
    with open(tmp_out, "wb") as out:
        for i, start, end in ranges:
            pf = parts_dir / f"{i:02d}.slice"
            expect = end - start + 1
            with open(pf, "rb") as inp:
                data = inp.read()
            if len(data) < expect:
                raise RuntimeError(f"slice {i} short {len(data)}/{expect}")
            out.write(data[:expect])
    size = tmp_out.stat().st_size
    if size < min_bytes:
        raise RuntimeError(f"merged too small {size}")
    if size != total_size:
        # allow slight? no — must match
        if abs(size - total_size) > 0:
            raise RuntimeError(f"size mismatch merged={size} total={total_size}")
    if expect_zip and not zipfile.is_zipfile(tmp_out):
        raise RuntimeError("merged file is not a valid zip")
    tmp_out.replace(dest)
    # cleanup parts
    try:
        shutil.rmtree(parts_dir)
    except OSError:
        pass
    print(f"[{label}] 多线程完成 {dest} ({human(dest.stat().st_size)})")
    return dest


def _download_single(
    url: str,
    dest: Path,
    part: Path,
    *,
    min_bytes: int,
    timeout: int,
    label: str,
    expect_zip: bool,
    slow_speed_bps: float,
    slow_grace_sec: float,
    allow_switch: bool,
) -> Path | str:
    """Returns Path on success, 'slow' to switch, raises on hard fail."""
    existing = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
        print(f"[{label}] 单线程续传 {human(existing)} <- {_short(url, 90)}")
    else:
        print(f"[{label}] 单线程下载 <- {_short(url, 90)}")

    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200) or 200
        if existing and status == 200:
            print(f"[{label}] 服务端不支持 Range，重新开始")
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
        win_t0 = t0
        win_got0 = got

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
                            f"{human_speed(speed)}   ",
                            end="",
                            flush=True,
                        )
                    else:
                        print(
                            f"\r[{label}] {human(got)} {human_speed(speed)}   ",
                            end="",
                            flush=True,
                        )
                    last_print = now

                if allow_switch and now - win_t0 >= slow_grace_sec:
                    inst = (got - win_got0) / max(now - win_t0, 0.001)
                    remain = (full_size - got) if full_size else 10**12
                    if inst < slow_speed_bps and remain > 5 * 1024 * 1024:
                        print(
                            f"\n[{label}] 通道过慢 {human_speed(inst)}，切换并续传..."
                        )
                        return "slow"
                    win_t0 = now
                    win_got0 = got
        print()

    size = part.stat().st_size
    if size < min_bytes:
        raise RuntimeError(f"too small ({size} B)")
    if expect_zip and not zipfile.is_zipfile(part):
        raise RuntimeError("not a valid zip")
    part.replace(dest)
    print(f"[{label}] 完成 {dest} ({human(dest.stat().st_size)})")
    return dest


def download_resume(
    urls: Iterable[str],
    dest: Path,
    *,
    min_bytes: int = 1_000_000,
    timeout: int = 60,
    label: str = "download",
    expect_zip: bool = False,
    rank: bool = True,
    probe_bytes: int = 512 * 1024,
    slow_speed_bps: float = 120 * 1024,
    slow_grace_sec: float = 15.0,
    max_switches: int = 10,
    connections: int = 8,
    multi_min_size: int = 20 * 1024 * 1024,
) -> Path:
    """Rank all mirrors, use fastest; multi-thread if Range supported & large."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    if dest.is_file() and dest.stat().st_size >= min_bytes:
        if expect_zip and not zipfile.is_zipfile(dest):
            dest.unlink(missing_ok=True)
        else:
            print(f"[{label}] already have {dest} ({human(dest.stat().st_size)})")
            return dest

    url_list: list[str] = []
    seen: set[str] = set()
    for u in urls:
        u = (u or "").strip()
        if u and u not in seen:
            seen.add(u)
            url_list.append(u)
    if not url_list:
        raise RuntimeError(f"[{label}] no urls")

    ranked_meta: dict[str, dict] = {}
    if rank and len(url_list) > 1:
        ranked = rank_mirrors(
            url_list,
            label=label,
            probe_bytes=probe_bytes,
            timeout=min(12.0, float(timeout)),
        )
        ordered = [r["url"] for r in ranked if r["ok"]]
        ordered += [r["url"] for r in ranked if not r["ok"]]
        for u in url_list:
            if u not in ordered:
                ordered.append(u)
        url_list = ordered
        ranked_meta = {r["url"]: r for r in ranked}
    else:
        print(f"[{label}] 按给定顺序尝试 {len(url_list)} 条")

    last_err: Exception | None = None
    switches = 0

    for idx, url in enumerate(url_list, 1):
        if switches > max_switches:
            break
        try:
            # Prefer multi-connection on large files when range works
            meta = ranked_meta.get(url) or {}
            size, range_ok = _head_size(url, timeout=15)
            if not size and meta.get("supports_range"):
                range_ok = True
            use_multi = (
                connections > 1
                and range_ok
                and size >= multi_min_size
                and not part.exists()  # single-thread .part resume path separate
            )
            # If we already have single-thread partial, continue single-thread
            if part.exists() and part.stat().st_size > 0:
                use_multi = False

            if use_multi:
                print(
                    f"[{label}] [{idx}/{len(url_list)}] 选用最快通道 + {connections} 线程"
                )
                try:
                    return download_multi(
                        url,
                        dest,
                        total_size=size,
                        connections=connections,
                        timeout=timeout,
                        label=label,
                        min_bytes=min_bytes,
                        expect_zip=expect_zip,
                    )
                except Exception as e:
                    print(f"[{label}] 多线程失败，改单线程续传: {e}")
                    # fall through single

            allow_switch = idx < len(url_list)
            result = _download_single(
                url,
                dest,
                part,
                min_bytes=min_bytes,
                timeout=timeout,
                label=label,
                expect_zip=expect_zip,
                slow_speed_bps=slow_speed_bps,
                slow_grace_sec=slow_grace_sec,
                allow_switch=allow_switch,
            )
            if result == "slow":
                switches += 1
                last_err = RuntimeError("too slow")
                continue
            return result  # Path
        except (HTTPError, URLError, TimeoutError, RuntimeError, OSError) as e:
            last_err = e
            print(f"\n[{label}] 通道失败: {e}")
            if part.exists() and part.stat().st_size < 64_000:
                try:
                    part.unlink()
                except OSError:
                    pass
            switches += 1
            continue

    raise RuntimeError(f"[{label}] 全部通道失败: {last_err}")


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Probe/download with mirror ranking")
    ap.add_argument("url")
    ap.add_argument("--probe-only", action="store_true")
    ap.add_argument("--github", action="store_true")
    ap.add_argument("-o", "--output", default="")
    ap.add_argument("-x", "--connections", type=int, default=8)
    args = ap.parse_args()
    urls = github_mirrors(args.url) if args.github else [args.url]
    if args.probe_only:
        rows = rank_mirrors(urls, label="probe")
        print(
            json.dumps(
                [
                    {k: r[k] for k in ("url", "ok", "speed", "bytes", "supports_range", "error")}
                    for r in rows
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        out = Path(args.output or "netfetch-out.bin")
        download_resume(
            urls,
            out,
            min_bytes=1000,
            label="netfetch",
            rank=True,
            connections=args.connections,
        )
