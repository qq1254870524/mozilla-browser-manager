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
from ..paths import BROWSERS_DIR, PATCHES_DIR, ensure_layout
from ..runtime_registry import mark_started, mark_stopped
from ..store import ProfileStore
from .base import EngineLauncher
from .proxy_util import playwright_proxy

_RUNS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_STOPPING: set[str] = set()


def get_run(profile_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _RUNS.get(profile_id)


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        import os
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _discover_browser_pid(user_data_dir: str | None) -> int | None:
    """Best-effort browser pid from SingletonLock or /proc cmdline (only browser processes)."""
    if not user_data_dir:
        return None
    import os
    from pathlib import Path
    try:
        ud = str(Path(user_data_dir).resolve())
    except Exception:
        ud = str(user_data_dir)
    lock = Path(ud) / "SingletonLock"
    try:
        if lock.is_symlink():
            target = os.readlink(lock)
            if target and "-" in target:
                tail = target.rsplit("-", 1)[-1]
                if tail.isdigit():
                    return int(tail)
    except Exception:
        pass
    try:
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
            joined = " ".join(parts).lower()
            if not any(tok in exe or tok in joined[:120] for tok in ("chrome", "chromium", "msedge", "camoufox", "firefox")):
                continue
            if ud.lower() not in joined:
                continue
            return int(proc.name)
    except Exception:
        pass
    return None


def is_run_alive(run: dict[str, Any] | None) -> bool:
    """Thread-safe liveness: never touch Playwright objects cross-thread."""
    if not run or run.get("closed"):
        return False
    pid = run.get("browser_pid") or run.get("pid")
    if pid:
        return _pid_alive(int(pid))
    # if no pid yet, treat in-memory non-closed run as alive (close event will clear)
    return True


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
        try:
            _finalize_stop(pid, reason="reconcile_dead")
        except Exception:
            with _LOCK:
                _RUNS.pop(pid, None)
            try:
                mark_stopped(pid)
            except Exception:
                pass
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
        # best-effort remember tabs if context still up
        if run and reason != "context_close":
            try:
                ctx = run.get("context")
                urls = []
                if ctx is not None:
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
        # tear down dedicated mihomo for this profile
        try:
            from mozilla_manager.modules import mihomo_svc
            prof = ProfileStore().get(profile_id)
            port = getattr(prof.proxy, "mihomo_port", None)
            if port and getattr(prof.proxy, "mode", None) == "mihomo":
                mihomo_svc.stop(int(port))
        except Exception:
            pass
        try:
            from mozilla_manager.engines.sync_bridge import drop_worker
            drop_worker(profile_id)
        except Exception:
            pass
    finally:
        _STOPPING.discard(profile_id)


def _install_lifecycle_watch(profile_id: str, context: Any) -> None:
    """When user closes the real browser window, panel must flip to 已停止."""

    def _on_close() -> None:
        # flip flags immediately so UI reconcile sees stopped even before cleanup finishes
        with _LOCK:
            run = _RUNS.get(profile_id)
            if run is not None:
                run["closed"] = True
        try:
            mark_stopped(profile_id)
        except Exception:
            pass

        def _job() -> None:
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
    """Fast non-blocking CF challenge detect."""
    try:
        url = str(getattr(page, "url", "") or "")
    except Exception:
        url = ""
    if not _is_http_url(url):
        return False
    low = url.lower()
    if "challenges.cloudflare.com" in low or "/cdn-cgi/challenge" in low:
        return True
    try:
        hit = page.evaluate(
            """() => {
  const t = (document.title || '').toLowerCase();
  if (t.includes('just a moment') || t.includes('attention required') || t.includes('cloudflare')) return true;
  if (document.querySelector('#challenge-form, #challenge-running, #cf-challenge-running, .cf-browser-verification')) return true;
  if (document.querySelector('iframe[src*="challenges.cloudflare"], iframe[src*="turnstile"]')) return true;
  if (document.querySelector('input[name="cf-turnstile-response"], .cf-turnstile, [data-sitekey]')) return true;
  const b = (document.body && (document.body.innerText || '')) || '';
  if (/checking your browser|enable javascript and cookies|cloudflare/i.test(b.slice(0, 800))) return true;
  return false;
}"""
        )
        return bool(hit)
    except Exception:
        return False


def _pass_cf_if_needed(page: Any, *, timeout: float = 45.0, harvest: bool = True) -> dict[str, Any]:
    from mozilla_manager.modules.turnstile import pass_cf_on_page, detect_cf

    try:
        url = str(getattr(page, "url", "") or "")
    except Exception:
        url = ""
    if not _is_http_url(url):
        return {"ok": True, "skipped": True, "reason": "non-http", "url": url}
    try:
        det = detect_cf(page)
    except Exception:
        det = {"cf": _page_looks_like_cf(page)}
    if not det.get("cf") and not _page_looks_like_cf(page):
        return {"ok": True, "skipped": True, "reason": "no-cf", "url": url, "detect": det}
    try:
        return pass_cf_on_page(page, timeout=timeout, harvest=harvest)
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


def _install_cf_watch(context: Any, profile: Profile) -> None:
    """Always-ready CF: on every http(s) navigation, detect then pass."""
    meta = profile.meta or {}
    if not (meta.get("auto_cf") or meta.get("pass_cf")):
        return
    timeout = float(meta.get("cf_timeout") or 45)
    # de-dupe concurrent handlers per page
    busy: set[int] = set()

    def _handle(page: Any) -> None:
        try:
            pid = id(page)
            if pid in busy:
                return
            busy.add(pid)
            try:
                _pass_cf_if_needed(page, timeout=timeout, harvest=True)
            finally:
                busy.discard(pid)
        except Exception:
            pass

    def _on_page(page: Any) -> None:
        try:
            page.on("load", lambda: _handle(page))
            page.on("framenavigated", lambda frame: _handle(page) if frame == page.main_frame else None)
        except Exception:
            pass
        # also check current document once
        try:
            _handle(page)
        except Exception:
            pass

    try:
        context.on("page", _on_page)
    except Exception:
        pass
    # attach to existing pages
    try:
        for pg in list(getattr(context, "pages", []) or []):
            _on_page(pg)
    except Exception:
        pass


def _stable_chromium_args(extra: list[str] | None = None) -> list[str]:
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
    ]
    # WSL / Linux containers often need these to keep the window alive
    import platform as _plat
    if _plat.system() == "Linux":
        args.extend(["--no-sandbox", "--disable-gpu", "--disable-software-rasterizer"])
    if extra:
        args.extend(extra)
    return args




def _rebrowser_executable() -> str | None:
    """Optional custom chromium binary under runtime/patches/rebrowser/."""
    candidates = [
        PATCHES_DIR / "rebrowser" / "chrome",
        PATCHES_DIR / "rebrowser" / "chrome.exe",
        PATCHES_DIR / "rebrowser" / "chromium",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
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

    def launch(self, profile: Profile, *, headless: bool = False, open_check: bool = True) -> LaunchResult:
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
                launch_args: dict[str, Any] = dict(
                    user_data_dir=user_data,
                    headless=headless,
                    proxy=proxy,
                    locale=env.locale,
                    timezone_id=env.timezone_id,
                    args=_stable_chromium_args(list(privacy_launch_args(profile.meta or {}) or [])),
                    viewport={"width": env.viewport_width or 1280, "height": env.viewport_height or 720},
                    # 隐藏自动化特征；只写一次，避免 keyword argument repeated
                    ignore_default_args=["--enable-automation"],
                    handle_sigint=False,
                    handle_sigterm=False,
                    handle_sighup=False,
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
                if executable:
                    launch_args["executable_path"] = executable
                # Patchright / pw_chromium network fix
                if profile.chromium_patch == ChromiumPatch.PATCHRIGHT:
                    # Force playwright-managed browser for patchright
                    if "executable_path" not in launch_args:
                        launch_args["executable_path"] = None  # let sync_playwright handle it
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

                context = pw.chromium.launch_persistent_context(**launch_args)
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
                                    timeout=float(meta.get("cf_timeout") or 45),
                                    harvest=True,
                                )
                            except Exception:
                                pass
                except Exception:
                    pass

                # discover browser pid (SingletonLock may appear slightly after launch)
                bpid = _discover_browser_pid(user_data)
                if not bpid:
                    try:
                        import time as _t
                        _t.sleep(0.15)
                        bpid = _discover_browser_pid(user_data)
                    except Exception:
                        bpid = None
                with _LOCK:
                    _RUNS[profile.id] = {
                        "pw": pw,
                        "context": context,
                        "driver": driver,
                        "page": page,
                        "browser_only": pol,
                        "user_data": user_data,
                        "browser_pid": bpid,
                        "closed": False,
                    }
                mark_started(
                    profile.id,
                    {
                        "driver": driver,
                        "engine": "chromium",
                        "user_data": profile.user_data_dir,
                        "browser_only": bool(pol.get("browser_only")),
                        "fingerprint": env.fingerprint.template_id if env.fingerprint else None,
                        "browser_pid": bpid,
                    },
                )
                try:
                    _install_lifecycle_watch(profile.id, context)
                except Exception:
                    pass
                return LaunchResult(
                    profile_id=profile.id,
                    ok=True,
                    message=(
                        f"launched chromium via {driver}; fp={env.fingerprint.template_id if env.fingerprint else '-'}; "
                        f"browser_only={pol.get('browser_only')}; user_data={profile.user_data_dir}"
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
