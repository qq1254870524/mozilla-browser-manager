from __future__ import annotations

import os
import threading
from typing import Any

from ..fingerprints import apply_fingerprint_to_context
from ..network.anti_leak import privacy_init_script, privacy_launch_args
from ..modules import cookies as cookies_mod
from ..launch_gate import write_check_page
from ..models import ChromiumPatch, LaunchResult, Profile
from ..network.browser_only import browser_only_launch_env
from ..paths import BROWSERS_DIR, PATCHES_DIR, ROOT, ensure_layout
from ..runtime_registry import mark_started, mark_stopped
from ..store import ProfileStore
from .base import EngineLauncher
from .proxy_util import playwright_proxy
from .native_ux import (
    chromium_pointer_options,
    native_cursor_init_script,
    resolve_chromium_launch_binary,
    want_lock_viewport,
)
from .immersive import (
    apply_immersive_to_browser_pid,
    chromium_immersive_args,
    snapshot_http_tabs,
    want_immersive,
)

_RUNS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_STOPPING: set[str] = set()


def get_run(profile_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _RUNS.get(profile_id)


def _pid_alive(pid: int | None) -> bool:
    """Process liveness — Windows-safe (os.kill signal 0 is not always reliable)."""
    if not pid:
        return False
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    import os
    import sys

    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            PROCESS_QUERY_INFORMATION = 0x0400
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
            if handle:
                # Still running? GetExitCodeProcess == STILL_ACTIVE (259)
                exit_code = wintypes.DWORD()
                ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                kernel32.CloseHandle(handle)
                if ok and int(exit_code.value) == 259:
                    return True
                if ok and int(exit_code.value) != 259:
                    return False
                return True
            # OpenProcess failed — distinguish not-found vs access
            err = int(kernel32.GetLastError() or 0)
            # 5 = ACCESS_DENIED → exists; 87/87 param; 87 already; 87
            if err in (5,):
                return True
            return False
        except Exception:
            pass
        # fallback os.kill(0)
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _norm_ud(user_data_dir: str) -> str:
    try:
        from pathlib import Path
        import os
        return os.path.normcase(str(Path(user_data_dir).resolve()))
    except Exception:
        import os
        return os.path.normcase(str(user_data_dir))


def _cmdline_has_user_data(cmdline: str, ud_norm: str) -> bool:
    if not cmdline or not ud_norm:
        return False
    import os
    cl = os.path.normcase(str(cmdline))
    ud = os.path.normcase(str(ud_norm))
    cl_slash = cl.replace("\\", "/")
    ud_slash = ud.replace("\\", "/")
    if ud and ud in cl:
        return True
    if ud_slash and ud_slash in cl_slash:
        return True
    # profile id folder: data/profiles/<id>
    try:
        parts = [x for x in ud_slash.rstrip("/").split("/") if x]
        if len(parts) >= 2 and parts[-2].lower() == "profiles":
            marker = f"profiles/{parts[-1]}".lower()
            if marker in cl_slash:
                return True
    except Exception:
        pass
    return False


def _iter_windows_browser_procs() -> list[tuple[int, str]]:
    """Return (pid, commandline) for chrome/chromium/headless-shell only (not Edge WebView)."""
    import sys
    if not sys.platform.startswith("win"):
        return []
    out: list[tuple[int, str]] = []
    # 1) PowerShell CIM
    try:
        import subprocess
        ps = (
            "$names=@('chrome.exe','chromium.exe','chrome-headless-shell.exe','headless_shell.exe');"
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|"
            "Where-Object { $names -contains $_.Name -and $_.CommandLine }|"
            "ForEach-Object { '{0}`t{1}' -f $_.ProcessId, $_.CommandLine }"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            if "\t" in line:
                pid_s, cl = line.split("\t", 1)
            elif "`t" in line:
                pid_s, cl = line.split("`t", 1)
            else:
                continue
            try:
                pid = int(str(pid_s).strip())
            except Exception:
                continue
            low = (cl or "").lower()
            if "msedgewebview" in low:
                continue
            if pid > 0 and cl:
                out.append((pid, cl))
        if out:
            return out
    except Exception:
        pass
    # 2) WMIC fallback
    try:
        import subprocess
        for name in ("chrome.exe", "chromium.exe", "chrome-headless-shell.exe", "headless_shell.exe"):
            r = subprocess.run(
                ["wmic", "process", "where", f"name='{name}'", "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=8,
            )
            for line in (r.stdout or "").splitlines():
                if not line or ("ProcessId" in line and "CommandLine" in line):
                    continue
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                try:
                    pid = int(parts[-1].strip())
                except Exception:
                    continue
                cl = ",".join(parts[1:-1]).strip().strip('"')
                if "msedgewebview" in (cl or "").lower():
                    continue
                if pid > 0:
                    out.append((pid, cl))
    except Exception:
        pass
    return out


_PID_CACHE: dict[str, tuple[float, set[int]]] = {}
_PID_CACHE_LOCK = threading.Lock()


def _find_pids_for_user_data(user_data_dir: str | None) -> set[int]:
    if not user_data_dir:
        return set()
    ud = _norm_ud(user_data_dir)
    import time as _t
    now = _t.monotonic()
    with _PID_CACHE_LOCK:
        hit = _PID_CACHE.get(ud)
        if hit and (now - hit[0]) < 1.0:
            return set(hit[1])
    found: set[int] = set()
    import sys
    if sys.platform.startswith("win"):
        for pid, cl in _iter_windows_browser_procs():
            if _cmdline_has_user_data(cl, ud):
                found.add(int(pid))
        with _PID_CACHE_LOCK:
            _PID_CACHE[ud] = (_t.monotonic(), set(found))
        return found
    # Linux /proc
    try:
        from pathlib import Path
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                raw = (proc / "cmdline").read_bytes()
            except Exception:
                continue
            if not raw:
                continue
            parts = [x.decode("utf-8", "ignore") for x in raw.split(bytes([0])) if x]
            if not parts:
                continue
            exe = Path(parts[0]).name.lower()
            joined = " ".join(parts)
            if not any(tok in exe for tok in ("chrome", "chromium", "msedge", "camoufox", "firefox")):
                continue
            if _cmdline_has_user_data(joined, ud):
                found.add(int(proc.name))
    except Exception:
        pass
    with _PID_CACHE_LOCK:
        _PID_CACHE[ud] = (_t.monotonic(), set(found))
    return found


def _kill_profile_browser_procs(user_data_dir: str | None, extra_pids: set[int] | None = None) -> list[int]:
    """Force-kill browser process tree for this profile user-data-dir (Windows/Linux)."""
    import sys
    import subprocess
    pids = set(extra_pids or ())
    try:
        pids |= _find_pids_for_user_data(user_data_dir)
    except Exception:
        pass
    # invalidate pid cache so liveness flips quickly after kill/close
    try:
        if user_data_dir:
            udn = _norm_ud(user_data_dir)
            with _PID_CACHE_LOCK:
                _PID_CACHE.pop(udn, None)
    except Exception:
        pass
    killed: list[int] = []
    for pid in sorted(pids):
        if pid <= 0:
            continue
        try:
            if sys.platform.startswith("win"):
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
            else:
                import os, signal
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
            killed.append(int(pid))
        except Exception:
            pass
    return killed


def _user_data_browser_alive(user_data_dir: str | None) -> bool:
    """True if any chrome/chromium process still holds this user-data-dir."""
    try:
        return bool(_find_pids_for_user_data(user_data_dir))
    except Exception:
        return False


def _discover_browser_pid(user_data_dir: str | None) -> int | None:
    """Best-effort browser pid: SingletonLock (Linux) / process cmdline (Windows+Linux)."""
    if not user_data_dir:
        return None
    import os
    from pathlib import Path
    try:
        ud = str(Path(user_data_dir).resolve())
    except Exception:
        ud = str(user_data_dir)
    # Linux symlink SingletonLock → hostname-pid
    lock = Path(ud) / "SingletonLock"
    try:
        if lock.is_symlink():
            target = os.readlink(lock)
            if target and "-" in target:
                tail = target.rsplit("-", 1)[-1]
                if tail.isdigit() and _pid_alive(int(tail)):
                    return int(tail)
    except Exception:
        pass
    pids = _find_pids_for_user_data(ud)
    if not pids:
        return None
    # Prefer the smallest pid (usually the browser main process)
    return sorted(pids)[0]


def is_run_alive(run: dict[str, Any] | None) -> bool:
    """Thread-safe liveness: never touch Playwright objects cross-thread.

    Policy:
      - closed=True → dead
      - if ANY chrome/headless-shell still owns user-data-dir → alive
      - if known browser_pid alive → alive
      - launch grace (<=5s) ONLY when we never observed a pid yet
        (once pid was seen and is gone, do not keep UI 运行中)
      - otherwise 2 consecutive dead hits (~3s) → dead
    """
    if not run or run.get("closed"):
        return False
    ud = run.get("user_data")
    # Strong signal: process list by user-data-dir (chrome.exe / headless-shell)
    try:
        pids = _find_pids_for_user_data(ud)
        if pids:
            run["browser_pid"] = sorted(pids)[0]
            run["_dead_hits"] = 0
            run["_seen_pid"] = True
            return True
    except Exception:
        pass
    pid = run.get("browser_pid") or run.get("pid")
    if pid and _pid_alive(int(pid)):
        run["_dead_hits"] = 0
        run["_seen_pid"] = True
        return True
    # rediscover
    try:
        bp = _discover_browser_pid(ud)
        if bp and _pid_alive(int(bp)):
            run["browser_pid"] = bp
            run["_dead_hits"] = 0
            run["_seen_pid"] = True
            return True
    except Exception:
        pass
    # Launch grace: only if we never saw a browser pid (Windows spawn lag)
    try:
        import time as _t
        started = float(run.get("started_mono") or 0)
        seen = bool(run.get("_seen_pid") or run.get("browser_pid"))
        if (not seen) and started and (_t.monotonic() - started) < 5.0:
            return True
    except Exception:
        pass
    hits = int(run.get("_dead_hits") or 0) + 1
    run["_dead_hits"] = hits
    if hits < 2:
        return True
    return False


def live_profile_ids() -> set[str]:
    alive: set[str] = set()
    dead: list[str] = []
    with _LOCK:
        items = list(_RUNS.items())
    for pid, run in items:
        # refresh pid if missing
        if not run.get("browser_pid"):
            bp = _discover_browser_pid(run.get("user_data"))
            if bp:
                run["browser_pid"] = bp
        if is_run_alive(run):
            alive.add(pid)
        else:
            dead.append(pid)
    for pid in dead:
        # Finalize on the profile worker thread — never raw watchdog thread CDP calls.
        def _stop(p=pid):
            try:
                from mozilla_manager.engines.sync_bridge import call_in_profile_thread

                call_in_profile_thread(
                    p,
                    lambda: _finalize_stop(p, reason="reconcile_dead"),
                    timeout=60.0,
                )
            except Exception:
                try:
                    _finalize_stop(p, reason="reconcile_dead")
                except Exception:
                    with _LOCK:
                        _RUNS.pop(p, None)
                    try:
                        mark_stopped(p)
                    except Exception:
                        pass

        try:
            threading.Thread(target=_stop, name=f"mm-reap-{pid[:16]}", daemon=True).start()
        except Exception:
            _stop()
    return alive


def _finalize_stop(profile_id: str, *, reason: str = "stop") -> None:
    """Idempotent stop: pop run, close context/pw, mark registry, free mihomo/worker."""
    if profile_id in _STOPPING:
        # still ensure registry clean
        try:
            mark_stopped(profile_id)
        except Exception:
            pass
        return
    _STOPPING.add(profile_id)
    run = None
    try:
        with _LOCK:
            run = _RUNS.pop(profile_id, None)
        # remember tabs always (manual window close used to skip → empty session)
        if run:
            try:
                urls = list(run.get("saved_tabs") or [])
                if not urls:
                    ctx = run.get("context")
                    if ctx is not None:
                        try:
                            urls = snapshot_http_tabs(ctx)
                        except Exception:
                            urls = []
                            for page in getattr(ctx, "pages", []) or []:
                                try:
                                    u = page.url
                                    if u and str(u).startswith("http"):
                                        urls.append(u)
                                except Exception:
                                    pass
                if urls:
                    store = ProfileStore()
                    prof = store.get(profile_id)
                    meta = dict(prof.meta or {})
                    meta["tabs"] = urls
                    groups = [g for g in list(meta.get("tab_groups") or []) if g.get("name") != "last"]
                    groups.insert(0, {"name": "last", "urls": urls})
                    meta["tab_groups"] = groups[:20]
                    store.update(profile_id, meta=meta)
            except Exception:
                pass
        if run:
            try:
                ctx = run.get("context")
                if ctx is not None:
                    ctx.close()
            except Exception:
                pass
            try:
                pw = run.get("pw")
                if pw is not None:
                    pw.stop()
            except Exception:
                pass
        try:
            mark_stopped(profile_id)
        except Exception:
            pass
        # Always reap leftover chrome/chromium for this user-data-dir.
        # Symptom: user closes window → UI still 运行中 / chrome.exe zombie.
        try:
            extra = set()
            if run:
                for k in ("browser_pid", "pid"):
                    v = run.get(k)
                    if v:
                        try:
                            extra.add(int(v))
                        except Exception:
                            pass
                ud = run.get("user_data")
            else:
                ud = None
            if not ud:
                try:
                    ud = str(ProfileStore().abs_user_data(ProfileStore().get(profile_id)))
                except Exception:
                    ud = None
            _kill_profile_browser_procs(ud, extra_pids=extra)
        except Exception:
            pass
        # Stop mihomo whenever browser is actually gone (including reconcile_dead).
        # False-dead is mitigated by Windows user-data process scan in is_run_alive.
        try:
            from mozilla_manager.modules import mihomo_svc
            prof = ProfileStore().get(profile_id)
            port = getattr(prof.proxy, "mihomo_port", None)
            if port and getattr(prof.proxy, "mode", None) == "mihomo":
                # Only skip mihomo stop if a browser process for this profile is STILL alive
                still = False
                try:
                    ud2 = None
                    if run:
                        ud2 = run.get("user_data")
                    if not ud2:
                        ud2 = str(ProfileStore().abs_user_data(prof))
                    still = _user_data_browser_alive(ud2)
                except Exception:
                    still = False
                if not still:
                    mihomo_svc.stop(int(port), reason=f"finalize:{reason}", profile_id=profile_id)
        except Exception:
            pass
        try:
            from mozilla_manager.engines.sync_bridge import drop_worker
            drop_worker(profile_id)
        except Exception:
            pass
    finally:
        _STOPPING.discard(profile_id)


def _persist_tabs_now(profile_id: str, urls: list[str]) -> None:
    if not urls:
        return
    try:
        store = ProfileStore()
        prof = store.get(profile_id)
        meta = dict(prof.meta or {})
        meta["tabs"] = list(urls)
        groups = [g for g in list(meta.get("tab_groups") or []) if g.get("name") != "last"]
        groups.insert(0, {"name": "last", "urls": list(urls)})
        meta["tab_groups"] = groups[:20]
        store.update(profile_id, meta=meta)
    except Exception:
        pass


def _install_tab_autosave(profile_id: str, context: Any) -> None:
    """Debounced save of http(s) tabs so manual close never loses session.

    CRITICAL: snapshot_http_tabs touches Playwright page objects. Must run on the
    profile BrowserWorker thread. A raw threading.Timer calling page.url used to
    corrupt the CDP session → browser looks fine for one navigation then "offline".
    """
    timer_box: dict[str, Any] = {"t": None}
    lock = threading.Lock()
    inflight = {"on": False}

    def _flush_on_worker() -> None:
        try:
            urls = snapshot_http_tabs(context)
            with _LOCK:
                run = _RUNS.get(profile_id)
                if run is not None:
                    run["saved_tabs"] = urls
            _persist_tabs_now(profile_id, urls)
        except Exception:
            pass

    def _fire() -> None:
        with lock:
            timer_box["t"] = None
            if inflight["on"]:
                return
            inflight["on"] = True
        try:
            from mozilla_manager.engines.sync_bridge import call_in_profile_thread

            # Re-entrant if already on worker; otherwise post back.
            call_in_profile_thread(profile_id, _flush_on_worker, timeout=15.0)
        except Exception:
            pass
        finally:
            with lock:
                inflight["on"] = False

    def _schedule(_page: Any = None) -> None:
        with lock:
            old = timer_box.get("t")
            if old is not None:
                try:
                    old.cancel()
                except Exception:
                    pass
            tim = threading.Timer(1.5, _fire)
            tim.daemon = True
            timer_box["t"] = tim
            tim.start()

    def _on_page(page: Any) -> None:
        try:
            page.on("framenavigated", lambda frame: _schedule(page) if frame == page.main_frame else None)
            page.on("load", lambda: _schedule(page))
        except Exception:
            pass
        _schedule(page)

    try:
        context.on("page", _on_page)
    except Exception:
        pass
    try:
        for pg in list(getattr(context, "pages", []) or []):
            _on_page(pg)
    except Exception:
        pass



def _install_browser_death_poll(profile_id: str, user_data: str | None) -> None:
    """Poll OS processes so closing the window clears 运行中 even if context.on(close) misses."""
    def _loop() -> None:
        import time
        while True:
            time.sleep(1.5)
            with _LOCK:
                run = _RUNS.get(profile_id)
                if not run or run.get("closed") or profile_id in _STOPPING:
                    return
                ud = run.get("user_data") or user_data
            # refresh pid
            try:
                if not is_run_alive(run):
                    def _job() -> None:
                        try:
                            _finalize_stop(profile_id, reason="browser_process_dead")
                        except Exception:
                            try:
                                mark_stopped(profile_id)
                            except Exception:
                                pass
                    try:
                        from mozilla_manager.engines.sync_bridge import call_in_profile_thread
                        call_in_profile_thread(profile_id, _job, timeout=60.0)
                    except Exception:
                        threading.Thread(target=_job, name=f"mm-dead-{profile_id[:12]}", daemon=True).start()
                    return
                # keep pid fresh
                try:
                    bp = _discover_browser_pid(ud)
                    if bp:
                        with _LOCK:
                            r2 = _RUNS.get(profile_id)
                            if r2 is not None:
                                r2["browser_pid"] = bp
                except Exception:
                    pass
            except Exception:
                pass

    try:
        threading.Thread(target=_loop, name=f"mm-bwatch-{profile_id[:12]}", daemon=True).start()
    except Exception:
        pass


def _install_lifecycle_watch(profile_id: str, context: Any) -> None:
    """User closes browser → save tabs + flip panel to 已停止."""

    def _on_close() -> None:
        # Prefer last autosaved tabs — context may already be dying; avoid extra
        # cross-thread Playwright reads that can wedge the driver.
        urls: list[str] = []
        with _LOCK:
            run = _RUNS.get(profile_id)
            if run is not None:
                run["closed"] = True
                urls = list(run.get("saved_tabs") or [])
        if not urls:
            try:
                urls = snapshot_http_tabs(context)
            except Exception:
                urls = []
            if urls:
                with _LOCK:
                    run = _RUNS.get(profile_id)
                    if run is not None:
                        run["saved_tabs"] = urls
        if urls:
            _persist_tabs_now(profile_id, urls)
        try:
            mark_stopped(profile_id)
        except Exception:
            pass

        def _job() -> None:
            try:
                # Playwright close/stop MUST run on the profile worker thread.
                from mozilla_manager.engines.sync_bridge import call_in_profile_thread

                call_in_profile_thread(
                    profile_id,
                    lambda: _finalize_stop(profile_id, reason="context_close"),
                    timeout=60.0,
                )
            except Exception:
                try:
                    _finalize_stop(profile_id, reason="context_close")
                except Exception:
                    try:
                        mark_stopped(profile_id)
                    except Exception:
                        pass

        threading.Thread(target=_job, name=f"mm-stop-{profile_id[:16]}", daemon=True).start()

    try:
        context.on("close", lambda _=None: _on_close())
    except Exception:
        try:
            context.on("close", _on_close)
        except Exception:
            pass



def _is_http_url(url: str | None) -> bool:
    u = str(url or "").strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _page_looks_like_cf(page: Any) -> bool:
    """Fast CF challenge detect — strict to avoid false positives on normal sites."""
    try:
        url = str(getattr(page, "url", "") or "")
    except Exception:
        url = ""
    if not _is_http_url(url):
        return False
    low = url.lower()
    if "challenges.cloudflare.com" in low or "/cdn-cgi/challenge" in low or "/cdn-cgi/chl" in low:
        return True
    try:
        hit = page.evaluate(
            """() => {
  const t = (document.title || '').toLowerCase().trim();
  // title-only strong signals
  if (t === 'just a moment...' || t === 'just a moment' || t.startsWith('just a moment')) return true;
  if (t.includes('attention required') || t.includes('please wait') && t.includes('cloudflare')) return true;
  // DOM challenge markers (high confidence)
  if (document.querySelector('#challenge-form, #challenge-running, #cf-challenge-running, .cf-browser-verification, #cf-wrapper, .challenge-platform')) return true;
  if (document.querySelector('iframe[src*="challenges.cloudflare"], iframe[src*="/cdn-cgi/challenge"]')) return true;
  if (document.querySelector('input[name="cf-turnstile-response"], .cf-turnstile, div.cf-turnstile, [data-sitekey]')) return true;
  // body text — require challenge phrasing, NOT bare word "cloudflare" (too many false hits)
  const b = ((document.body && (document.body.innerText || '')) || '').slice(0, 1200).toLowerCase();
  if (/checking your browser before|verify you are human|enable javascript and cookies to continue|performing security verification|sorry, you have been blocked/i.test(b)) return true;
  return false;
}"""
        )
        return bool(hit)
    except Exception:
        return False


def _pass_cf_if_needed(page: Any, *, timeout: float = 45.0, harvest: bool = True) -> dict[str, Any]:
    """Detect+pass CF. Must run on the profile browser worker thread only."""
    from mozilla_manager.modules.turnstile import pass_cf_on_page, detect_cf

    try:
        url = str(getattr(page, "url", "") or "")
    except Exception:
        url = ""
    if not _is_http_url(url):
        return {"ok": True, "skipped": True, "reason": "non-http", "url": url}
    # Fast local heuristic first — avoid expensive harvester on normal pages
    looks = False
    try:
        looks = _page_looks_like_cf(page)
    except Exception:
        looks = False
    if not looks:
        try:
            det = detect_cf(page)
        except Exception:
            det = {"cf": False}
        if not det.get("cf"):
            return {"ok": True, "skipped": True, "reason": "no-cf", "url": url, "detect": det}
    try:
        # Cap wait so a stuck challenge cannot freeze the browser worker forever
        to = min(float(timeout or 45), 20.0)
        return pass_cf_on_page(page, timeout=to, harvest=harvest)
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


def _install_cf_watch(context: Any, profile: Profile) -> None:
    """Always-ready CF on navigations — thread-safe for Playwright Sync API.

    CRITICAL: never call page.* from threading.Timer / random threads.
    Playwright Sync is bound to the profile BrowserWorker thread; cross-thread
    CDP calls corrupt the session and look like "opened one page then offline".
    Delayed rechecks are posted back onto the same worker via sync_bridge.
    """
    meta = dict(profile.meta or {})
    enabled = True
    if "auto_cf" in meta or "pass_cf" in meta:
        enabled = bool(meta.get("auto_cf") or meta.get("pass_cf"))
    if meta.get("auto_cf") is False and meta.get("pass_cf") is not True:
        enabled = False
    if not enabled:
        return

    timeout = float(meta.get("cf_timeout") or 12)
    # Passive watch must NOT reset/harvest turnstile by default — reset() breaks
    # real challenges (freetaxusa etc.) and can look like total offline.
    harvest_default = meta.get("cf_harvest")
    if harvest_default is None:
        harvest_default = False
    profile_id = str(profile.id)
    seen_urls: set[str] = set()
    busy: set[int] = set()
    last_try: dict[int, float] = {}
    scheduled: set[str] = set()
    lock = threading.Lock()

    def _handle(page: Any, *, reason: str = "nav") -> None:
        import time as _time

        try:
            pid = id(page)
            now = _time.time()
            with lock:
                prev = float(last_try.get(pid) or 0)
                gap = 1.0 if reason.startswith("delay") else 2.0
                if now - prev < gap:
                    return
                if pid in busy:
                    return
                busy.add(pid)
                last_try[pid] = now
            try:
                # Delayed recheck: only spend time when page still looks like CF
                if reason.startswith("delay"):
                    try:
                        if not _page_looks_like_cf(page):
                            return
                    except Exception:
                        return
                else:
                    # Immediate path also prefers cheap heuristic before heavy detect
                    try:
                        url = str(getattr(page, "url", "") or "")
                    except Exception:
                        url = ""
                    if not _is_http_url(url):
                        return
                try:
                    cur = str(getattr(page, "url", "") or "")
                except Exception:
                    cur = ""
                # one passive attempt per URL path (ignore query noise partially)
                url_key = cur.split("#", 1)[0][:180]
                if url_key in seen_urls and not reason.startswith("delay"):
                    return
                if reason.startswith("delay") and url_key in seen_urls:
                    # delayed only if still looks like CF
                    pass
                else:
                    seen_urls.add(url_key)
                # cap set growth
                if len(seen_urls) > 40:
                    seen_urls.clear()
                    if url_key:
                        seen_urls.add(url_key)
                _pass_cf_if_needed(page, timeout=min(float(timeout), 12.0), harvest=bool(harvest_default))
            finally:
                with lock:
                    busy.discard(pid)
        except Exception:
            pass

    def _post_to_worker(page: Any, reason: str, delay: float) -> None:
        """Run CF check on the profile Playwright thread after delay."""
        key = f"{id(page)}:{reason}:{delay}"
        with lock:
            if key in scheduled:
                return
            scheduled.add(key)

        def _timer_fire(p=page, r=reason, k=key) -> None:
            try:
                from mozilla_manager.engines.sync_bridge import call_in_profile_thread

                def _job():
                    try:
                        _handle(p, reason=r)
                    finally:
                        with lock:
                            scheduled.discard(k)

                call_in_profile_thread(profile_id, _job, timeout=max(45.0, min(timeout, 20.0) + 15))
            except Exception:
                with lock:
                    scheduled.discard(k)

        try:
            tim = threading.Timer(float(delay), _timer_fire)
            tim.daemon = True
            tim.start()
        except Exception:
            with lock:
                scheduled.discard(key)

    def _handle_with_retries(page: Any) -> None:
        # immediate check only when already on worker during event pump / launch
        try:
            from mozilla_manager.engines.sync_bridge import get_worker
            import threading as _th

            w = get_worker(profile_id)
            on_worker = _th.current_thread() is getattr(w, "_thread", None)
        except Exception:
            on_worker = False
        if on_worker:
            _handle(page, reason="nav")
        else:
            _post_to_worker(page, reason="nav-post", delay=0.05)
        # late CF paint: re-check on SAME worker, not raw Timer thread
        for delay in (2.5,):
            _post_to_worker(page, reason=f"delay-{delay}", delay=delay)

    def _on_page(page: Any) -> None:
        try:
            # load only — framenavigated storms during CF challenges flooded the worker
            # and re-triggered turnstile logic mid-solve (breaks freetaxusa signup flow).
            page.on("load", lambda: _handle_with_retries(page))
        except Exception:
            pass
        try:
            _handle_with_retries(page)
        except Exception:
            pass

    try:
        context.on("page", _on_page)
    except Exception:
        pass
    try:
        for pg in list(getattr(context, "pages", []) or []):
            _on_page(pg)
    except Exception:
        pass


def _stable_chromium_args(
    extra: list[str] | None = None,
    *,
    meta: dict[str, Any] | None = None,
    headless: bool = False,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
) -> list[str]:
    """Chromium flags — default = max anti-detect.

    Max stealth (default):
      - window size locked to fingerprint viewport (screen/window match)
      - no --start-maximized (maximize desyncs outer size vs spoofed screen)
    Comfort opt-in (meta.stealth_level=comfort | native_window | lock_viewport=false):
      - free resize / optional maximize
    """
    meta = meta or {}
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
        # Remove "Chrome is being controlled by automated test software" infobar residue
        "--disable-infobars",
        "--disable-features=AutomationControlled,TranslateUI",
        # QUIC/HTTP3 over SOCKS5/mihomo is flaky → first page ok then subsequent navs fail
        "--disable-quic",
    ]
    try:
        for a in chromium_immersive_args(
            meta,
            headless=headless,
            width=viewport_width or (meta.get("viewport_width") if meta else None),
            height=viewport_height or (meta.get("viewport_height") if meta else None),
        ):
            if a not in args:
                args.append(a)
    except Exception:
        pass
    # Window geometry
    #  - lock_viewport: fixed --window-size matching FP (automation box)
    #  - free resize (default): maximize or user size; content reflows with window
    if not headless:
        lock = want_lock_viewport(meta)
        want_max = meta.get("window_maximized")
        if want_max is None:
            want_max = (not lock)
        if lock:
            try:
                w = int(
                    meta.get("window_width")
                    or viewport_width
                    or meta.get("viewport_width")
                    or 1920
                )
                h = int(
                    meta.get("window_height")
                    or viewport_height
                    or meta.get("viewport_height")
                    or 1080
                )
                args.append(f"--window-size={max(320, w)},{max(240, h)}")
            except Exception:
                args.append("--window-size=1920,1080")
        elif want_max:
            args.append("--start-maximized")
        elif meta.get("window_width") or meta.get("window_height") or viewport_width or viewport_height:
            try:
                w = int(meta.get("window_width") or viewport_width or meta.get("viewport_width") or 1280)
                h = int(meta.get("window_height") or viewport_height or meta.get("viewport_height") or 800)
                args.append(f"--window-size={max(320, w)},{max(240, h)}")
            except Exception:
                args.append("--start-maximized")
        else:
            # real-browser default: let Chromium pick a normal restored size / maximized
            args.append("--start-maximized")
    # WSL / Linux containers often need these to keep the window alive
    import platform as _plat
    if _plat.system() == "Linux":
        # On real desktop Linux with GPU, keep GPU; only force off under obvious container/WSL without display accel
        # Still keep no-sandbox for compatibility in many lab setups.
        args.append("--no-sandbox")
        if os.environ.get("MOZILLA_DISABLE_GPU") == "1" or os.environ.get("WSL_DISTRO_NAME"):
            # WSLg can use GPU; allow override. Default: do not disable GPU (looks blurry/boxed).
            if os.environ.get("MOZILLA_DISABLE_GPU") == "1":
                args.extend(["--disable-gpu", "--disable-software-rasterizer"])
    if extra:
        # de-dup while preserving order
        seen = set(args)
        for a in extra:
            if a not in seen:
                args.append(a)
                seen.add(a)
    # Chromium keeps only the LAST --disable-features=... ; merge them all
    feat_key = "--disable-features="
    feats: list[str] = []
    merged: list[str] = []
    for a in args:
        if a.startswith(feat_key):
            for part in a[len(feat_key):].split(","):
                part = part.strip()
                if part and part not in feats:
                    feats.append(part)
        else:
            merged.append(a)
    if feats:
        merged.append(feat_key + ",".join(feats))
    return merged


def _viewport_launch_options(env, meta: dict[str, Any] | None, *, headless: bool) -> dict[str, Any]:
    """Viewport kwargs for launch_persistent_context.

    Default (lock_viewport=false): **no fixed viewport** so HTML/CSS reflows when the
    user resizes the window (real-browser behavior).

    Opt-in lock (automation / fixed FP box): meta.lock_viewport=true | fixed_viewport=true.
    """
    meta = meta or {}
    lock = want_lock_viewport(meta)
    if lock:
        w = int(getattr(env, "viewport_width", None) or meta.get("viewport_width") or 1920)
        h = int(getattr(env, "viewport_height", None) or meta.get("viewport_height") or 1080)
        return {"viewport": {"width": max(320, w), "height": max(240, h)}, "no_viewport": False}
    # Explicit None + no_viewport: some Patchright builds still default 1280x720
    # if only no_viewport is set — that left a "boxed" non-reflowing content area.
    return {"no_viewport": True, "viewport": None}


def _clear_device_metrics_override(context: Any) -> None:
    """Drop CDP Emulation device metrics so layout tracks the real window size."""
    try:
        pages = list(getattr(context, "pages", []) or [])
    except Exception:
        pages = []
    for page in pages:
        try:
            sess = context.new_cdp_session(page)
            try:
                sess.send("Emulation.clearDeviceMetricsOverride")
            except Exception:
                pass
            try:
                sess.detach()
            except Exception:
                pass
        except Exception:
            continue


def _install_free_resize(context: Any, meta: dict[str, Any] | None) -> None:
    """Ensure every page keeps free-resize layout (no sticky Playwright viewport)."""
    if want_lock_viewport(meta):
        return

    def _on_page(page: Any) -> None:
        try:
            # If a prior session pinned viewport, clear it.
            try:
                # Playwright: setting viewport to None is not always exposed per-page;
                # CDP clear is the reliable path.
                sess = context.new_cdp_session(page)
                sess.send("Emulation.clearDeviceMetricsOverride")
                try:
                    sess.detach()
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

    try:
        context.on("page", _on_page)
    except Exception:
        pass
    try:
        for pg in list(getattr(context, "pages", []) or []):
            _on_page(pg)
    except Exception:
        pass




def _rebrowser_executable() -> str | None:
    """Resolve Chromium binary for rebrowser mode.

    Priority:
      1) custom binary under runtime/patches/rebrowser/
      2) chrome.path pointer (written by install)
      3) newest bundled chromium under runtime/browsers/
    Custom binary is optional — patches live in rebrowser-playwright driver.
    """
    for name in ("chrome", "chrome.exe", "chromium"):
        c = PATCHES_DIR / "rebrowser" / name
        if c.is_file() and c.stat().st_size > 0:
            return str(c.resolve())

    path_file = PATCHES_DIR / "rebrowser" / "chrome.path"
    if path_file.is_file():
        try:
            line = path_file.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            if line:
                p = Path(line)
                if not p.is_absolute():
                    p = (ROOT / line).resolve()
                if p.is_file():
                    return str(p)
        except Exception:
            pass

    if BROWSERS_DIR.exists():
        found: list[Path] = []
        for pattern in (
            "chromium-*/chrome-win64/chrome.exe",
            "chromium-*/chrome-win/chrome.exe",
            "chromium-*/chrome-linux64/chrome",
            "chromium-*/chrome-linux/chrome",
            "chromium-*/chrome-mac*/Chromium",
            "chromium-*/chrome-mac/Chromium",
        ):
            found.extend(BROWSERS_DIR.glob(pattern))
        found = [p for p in found if p.is_file()]

        def rev_key(p: Path) -> int:
            for part in p.parts:
                if part.startswith("chromium-"):
                    try:
                        return int(part.split("-", 1)[1])
                    except Exception:
                        return 0
            return 0

        if found:
            found.sort(key=rev_key, reverse=True)
            return str(found[0].resolve())
    return None



def _import_sync_playwright(patch: ChromiumPatch):
    """
    Free combo:
      none       -> playwright
      patchright -> patchright
      rebrowser  -> rebrowser-playwright (patched driver) falling back to playwright
                    + optional executable under runtime/patches/rebrowser/
    """
    if patch == ChromiumPatch.PATCHRIGHT:
        from patchright.sync_api import sync_playwright

        return sync_playwright, "patchright"
    if patch == ChromiumPatch.REBROWSER:
        try:
            from rebrowser_playwright.sync_api import sync_playwright  # type: ignore

            return sync_playwright, "rebrowser-playwright"
        except Exception:
            from playwright.sync_api import sync_playwright

            return sync_playwright, "playwright+rebrowser-fallback"
    from playwright.sync_api import sync_playwright

    return sync_playwright, "playwright"


class ChromiumLauncher(EngineLauncher):
    name = "chromium"

    def launch(self, profile: Profile, *, headless: bool = False, open_check: bool | None = None) -> LaunchResult:
        ensure_layout()
        store = ProfileStore()
        user_data = str(store.abs_user_data(profile))
        proxy = playwright_proxy(profile)
        env = profile.env
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR))

        sync_playwright, driver = _import_sync_playwright(profile.chromium_patch)
        executable = None
        if profile.chromium_patch == ChromiumPatch.PATCHRIGHT:
            # Force patchright driver (important for network)
            executable = None  # let patchright.sync_api handle browser binary
        if profile.chromium_patch == ChromiumPatch.REBROWSER:
            executable = _rebrowser_executable()
            if driver.endswith("fallback") and not executable:
                driver = "playwright (rebrowser package missing; using stock + patches source only)"

        with browser_only_launch_env(profile) as pol:
            pw = sync_playwright().start()
            try:
                try:
                    from mozilla_manager.modules.profiles import ensure_meta_defaults
                    meta0 = ensure_meta_defaults(dict(profile.meta or {}), persist=True, profile_id=profile.id)
                except Exception:
                    meta0 = dict(profile.meta or {})
                # 默认不打开检测页；需要时 meta.open_check=true
                if open_check is None:
                    if "open_check" in meta0:
                        open_check = bool(meta0.get("open_check"))
                    else:
                        open_check = False
                # 默认捆绑 Chromium（最强反检测）；系统 Chrome 仅 comfort / use_system_chrome
                bin_opts = resolve_chromium_launch_binary(meta0)
                browser_label = bin_opts.pop("_browser_label", None) or "bundled-chromium"
                launch_args: dict[str, Any] = dict(
                    user_data_dir=user_data,
                    headless=headless,
                    proxy=proxy,
                    locale=env.locale,
                    timezone_id=env.timezone_id,
                    args=_stable_chromium_args(
                        list(
                            privacy_launch_args(
                                meta0,
                                has_proxy=bool(proxy),
                                proxy_mode=str(getattr(profile.proxy, "mode", None) or ""),
                            )
                            or []
                        ),
                        meta=meta0,
                        headless=headless,
                        viewport_width=getattr(env, "viewport_width", None),
                        viewport_height=getattr(env, "viewport_height", None),
                    ),
                    # 默认 no_viewport：窗口缩放时页面内容自适应；lock_viewport=true 才钉死
                    **_viewport_launch_options(env, meta0, headless=headless),
                    # 隐藏自动化特征；只写一次，避免 keyword argument repeated
                    ignore_default_args=["--enable-automation"],
                    handle_sigint=False,
                    handle_sigterm=False,
                    handle_sighup=False,
                    **chromium_pointer_options(meta0),
                )
                # v3 profile-level extensions
                try:
                    from mozilla_manager.modules.extensions import resolve_extension_paths
                    ext_paths = resolve_extension_paths(profile.id)
                    if ext_paths:
                        # Chromium persistent context: args --load-extension=a,b and disable features
                        joined = ",".join(ext_paths)
                        launch_args.setdefault("args", [])
                        launch_args["args"] = list(launch_args["args"]) + [
                            f"--disable-extensions-except={joined}",
                            f"--load-extension={joined}",
                        ]
                        prev = list(launch_args.get("ignore_default_args") or [])
                        if "--disable-extensions" not in prev:
                            prev.append("--disable-extensions")
                        launch_args["ignore_default_args"] = prev
                except Exception:
                    pass
                # Belt-and-suspenders: also pass --proxy-server= so Chromium keeps egress
                # even if Playwright proxy wiring flakes after Network Service restart
                # (symptom: first page ok / click → all tabs ERR_PROXY_CONNECTION_FAILED).
                try:
                    if proxy and isinstance(proxy, dict) and proxy.get("server"):
                        ps = str(proxy.get("server"))
                        args_list = list(launch_args.get("args") or [])
                        args_list = [a for a in args_list if not str(a).startswith("--proxy-server=")]
                        args_list.append(f"--proxy-server={ps}")
                        launch_args["args"] = args_list
                except Exception:
                    pass
                # Binary priority: rebrowser custom > explicit path > (opt-in system Chrome) > bundled (max stealth)
                if executable:
                    launch_args["executable_path"] = executable
                    launch_args.pop("channel", None)
                else:
                    if bin_opts.get("executable_path"):
                        launch_args["executable_path"] = bin_opts["executable_path"]
                        launch_args.pop("channel", None)
                    elif bin_opts.get("channel"):
                        launch_args["channel"] = bin_opts["channel"]
                        launch_args.pop("executable_path", None)
                # Patchright default: use its managed bundled Chromium (strongest + patched)
                if profile.chromium_patch == ChromiumPatch.PATCHRIGHT:
                    if not launch_args.get("executable_path") and not launch_args.get("channel"):
                        launch_args.pop("executable_path", None)
                ua = env.user_agent or (env.fingerprint.user_agent if env.fingerprint else None)
                if ua:
                    launch_args["user_agent"] = ua
                if env.geolocation:
                    launch_args["geolocation"] = {
                        "latitude": env.geolocation.latitude,
                        "longitude": env.geolocation.longitude,
                        "accuracy": env.geolocation.accuracy,
                    }
                    launch_args["permissions"] = list(env.permissions)

                try:
                    context = pw.chromium.launch_persistent_context(**launch_args)
                except Exception as launch_err:
                    # 系统 Chrome 与驱动版本不匹配时回退到自带 Chromium
                    if launch_args.get("executable_path") or launch_args.get("channel"):
                        launch_args.pop("executable_path", None)
                        launch_args.pop("channel", None)
                        browser_label = f"bundled-fallback ({launch_err})"
                        context = pw.chromium.launch_persistent_context(**launch_args)
                    else:
                        raise
                # Native OS cursor (strip software/humanize overlays)
                try:
                    context.add_init_script(native_cursor_init_script())
                except Exception:
                    pass
                # v2 fingerprint init script (baseline)
                apply_fingerprint_to_context(context, env.fingerprint)
                # v6 stealth matrix (24+ dims, fixed noise, TLS persona marker)
                try:
                    from mozilla_manager.modules import stealth_svc
                    stealth_svc.apply_stealth_to_context(context, profile)
                except Exception:
                    pass
                try:
                    from mozilla_manager.modules import media_fake
                    media_fake.apply_virtual_media_to_context(context, profile.meta or {})
                except Exception:
                    pass
                # v4 WebRTC privacy init
                try:
                    ps = privacy_init_script(profile.meta or {})
                    if ps:
                        context.add_init_script(ps)
                except Exception:
                    pass
                page = context.pages[0] if context.pages else context.new_page()
                # Free-resize / native window: kill any sticky device-metrics box
                try:
                    if not want_lock_viewport(meta0):
                        _clear_device_metrics_override(context)
                        _install_free_resize(context, meta0)
                except Exception:
                    pass

                if env.languages:
                    page.set_extra_http_headers({"Accept-Language": ",".join(env.languages)})

                # v4 cookie pre-inject (秒登录)
                try:
                    cookies_mod.inject_cookies_to_context(context, profile.id)
                except Exception:
                    pass
                # legacy restored_storage_state path still supported inside inject

                # v4 restore remembered tabs / tab groups (skip if only check page)
                try:
                    tabs = list((profile.meta or {}).get("tabs") or [])
                    if not tabs:
                        # fallback last tab group
                        for g in list((profile.meta or {}).get("tab_groups") or []):
                            if g.get("name") == "last" and g.get("urls"):
                                tabs = list(g.get("urls") or [])
                                break
                    # open check page first optionally
                    if open_check:
                        uri = write_check_page(profile)
                        page.goto(uri, wait_until="domcontentloaded")
                    for i, url in enumerate(tabs):
                        if not url or not str(url).startswith("http"):
                            continue
                        pg = page if (i == 0 and not open_check) else context.new_page()
                        try:
                            pg.goto(str(url), wait_until="domcontentloaded", timeout=60000)
                        except Exception:
                            pass
                    if not tabs and not open_check:
                        # 原生手感：新标签空白页，而不是检测灰卡片
                        try:
                            page.goto("about:blank", wait_until="domcontentloaded")
                        except Exception:
                            pass
                except Exception:
                    if open_check:
                        try:
                            uri = write_check_page(profile)
                            page.goto(uri, wait_until="domcontentloaded")
                        except Exception:
                            pass

                # v5/v10.7 CF always-ready: skip file:// check page; watch navigations
                try:
                    _install_cf_watch(context, profile)
                    meta = profile.meta or {}
                    if meta.get("auto_cf") or meta.get("pass_cf"):
                        for pg in list(context.pages):
                            try:
                                _pass_cf_if_needed(
                                    pg,
                                    timeout=min(float(meta.get("cf_timeout") or 12), 12.0),
                                    harvest=False,
                                )
                            except Exception:
                                pass
                except Exception:
                    pass

                # discover browser pid (Windows: process cmdline; Linux: SingletonLock+/proc)
                bpid = _discover_browser_pid(user_data)
                if not bpid:
                    try:
                        import time as _t
                        for _ in range(6):
                            _t.sleep(0.25)
                            bpid = _discover_browser_pid(user_data)
                            if bpid:
                                break
                    except Exception:
                        bpid = None
                # v10.3: strip OS title bar (Windows) for immersive window
                immersive_info = {}
                try:
                    if bpid and want_immersive(meta0):
                        immersive_info = apply_immersive_to_browser_pid(bpid, meta0)
                        # retry once shortly after if pid just spawned
                        if not immersive_info.get("ok"):
                            import time as _t2
                            _t2.sleep(0.35)
                            bpid2 = _discover_browser_pid(user_data) or bpid
                            bpid = bpid2
                            immersive_info = apply_immersive_to_browser_pid(bpid, meta0)
                except Exception as _ie:
                    immersive_info = {"ok": False, "error": str(_ie)}
                with _LOCK:
                    import time as _tmono
                    _RUNS[profile.id] = {
                        "pw": pw,
                        "context": context,
                        "driver": driver,
                        "page": page,
                        "browser_only": pol,
                        "user_data": user_data,
                        "browser_pid": bpid,
                        "closed": False,
                        "immersive": bool(want_immersive(meta0)),
                        "saved_tabs": snapshot_http_tabs(context),
                        "started_mono": _tmono.monotonic(),
                        "_dead_hits": 0,
                        "_seen_pid": bool(bpid),
                    }
                mark_started(
                    profile.id,
                    {
                        "driver": driver,
                        "engine": "chromium",
                        "browser": browser_label or "bundled",
                        "user_data": profile.user_data_dir,
                        "browser_only": bool(pol.get("browser_only")),
                        "fingerprint": env.fingerprint.template_id if env.fingerprint else None,
                        "browser_pid": bpid,
                        "immersive": bool(want_immersive(meta0)),
                        "stealth_level": (meta0 or {}).get("stealth_level") or "max",
                    },
                )
                try:
                    _install_tab_autosave(profile.id, context)
                except Exception:
                    pass
                try:
                    _install_lifecycle_watch(profile.id, context)
                except Exception:
                    pass
                try:
                    _install_browser_death_poll(profile.id, user_data)
                except Exception:
                    pass
                # Launch-time network smoke: mixed-port must be up. Avoid long in-page
                # fetch (Windows headless + proxy can hang AbortController for tens of seconds).
                smoke: dict[str, Any] = {"ok": True}
                try:
                    if proxy and getattr(profile.proxy, "mode", None) == "mihomo":
                        import socket as _socket
                        port = int(getattr(profile.proxy, "mihomo_port", 0) or 0)
                        mixed_up = False
                        if port:
                            for _try in range(8):
                                try:
                                    s = _socket.socket(); s.settimeout(0.35)
                                    s.connect(("127.0.0.1", port)); s.close()
                                    mixed_up = True
                                    break
                                except Exception:
                                    try:
                                        s.close()
                                    except Exception:
                                        pass
                                    import time as _t3
                                    _t3.sleep(0.25)
                        if port and not mixed_up:
                            try:
                                from mozilla_manager.modules import mihomo_svc
                                sub = (profile.meta or {}).get("sub") or "default"
                                node = profile.proxy.node_name or ""
                                cfp = (profile.meta or {}).get("tls_client_fingerprint") or "chrome"
                                mihomo_svc.start(port, sub=sub, node=node or "", client_fingerprint=cfp)
                                import time as _t4
                                for _ in range(12):
                                    try:
                                        s = _socket.socket(); s.settimeout(0.3)
                                        s.connect(("127.0.0.1", port)); s.close()
                                        mixed_up = True
                                        break
                                    except Exception:
                                        try:
                                            s.close()
                                        except Exception:
                                            pass
                                        _t4.sleep(0.2)
                            except Exception as _re:
                                smoke = {"ok": False, "error": f"mihomo restart failed: {_re}"}
                        if port and not mixed_up and smoke.get("ok", True):
                            smoke = {"ok": False, "error": f"mihomo mixed-port {port} down at launch smoke"}
                        else:
                            smoke = {"ok": True, "mixed_port": mixed_up, "port": port}
                except Exception as _se:
                    smoke = {"ok": True, "soft": True, "error": f"smoke internal: {_se}"}  # never block on smoke internals
                if smoke.get("ok") is False and proxy and getattr(profile.proxy, "mode", None) == "mihomo":
                    err = str(smoke.get("error") or "")
                    if "mixed-port" in err and "down" in err:
                        try:
                            _finalize_stop(profile.id, reason="launch_smoke_fail")
                        except Exception:
                            pass
                        return LaunchResult(
                            profile_id=profile.id,
                            ok=False,
                            message=f"launch network smoke failed (proxy): {smoke.get('error')}",
                        )
                    try:
                        from mozilla_manager import db as _db
                        _db.audit("launch_smoke_soft_fail", profile.id, smoke)
                    except Exception:
                        pass
                    smoke["soft_fail"] = True
                    smoke["ok"] = True
                return LaunchResult(
                    profile_id=profile.id,
                    ok=True,
                    message=(
                        f"launched chromium via {driver}; fp={env.fingerprint.template_id if env.fingerprint else '-'}; "
                        f"browser_only={pol.get('browser_only')}; user_data={profile.user_data_dir}; smoke={smoke.get('ok')}"
                    ),
                )
            except Exception as e:
                try:
                    pw.stop()
                except Exception:
                    pass
                return LaunchResult(profile_id=profile.id, ok=False, message=str(e))

    def stop(self, profile_id: str) -> None:
        _finalize_stop(profile_id, reason="api_stop")
