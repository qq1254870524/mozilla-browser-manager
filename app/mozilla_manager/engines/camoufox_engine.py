from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from ..fingerprints import apply_fingerprint_to_context, apply_init_script
from ..launch_gate import write_check_page
from ..models import LaunchResult, Profile
from ..network.browser_only import browser_only_launch_env
from ..network.anti_leak import privacy_init_script
from ..paths import ROOT, ensure_layout
from ..runtime_registry import mark_started, mark_stopped
from ..store import ProfileStore
from .base import EngineLauncher
from .proxy_util import playwright_proxy
from .native_ux import camoufox_cursor_options, native_cursor_init_script, want_lock_viewport
from .immersive import (
    apply_immersive_to_browser_pid,
    camoufox_immersive_prefs,
    snapshot_http_tabs,
    want_immersive,
)

_RUNS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_STOPPING: set[str] = set()


def get_run(profile_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _RUNS.get(profile_id)


def is_run_alive(run: dict[str, Any] | None) -> bool:
    """Conservative liveness — mirror chromium (never false-dead → keep mihomo)."""
    if not run or run.get("closed"):
        return False
    try:
        import time as _t
        started = float(run.get("started_mono") or 0)
        if started and (_t.monotonic() - started) < 15.0:
            return True
    except Exception:
        pass
    try:
        from mozilla_manager.engines.chromium import _pid_alive, _discover_browser_pid
    except Exception:
        return True
    pid = run.get("browser_pid") or run.get("pid")
    if not pid:
        bp = _discover_browser_pid(run.get("user_data"))
        if bp:
            run["browser_pid"] = bp
            pid = bp
    if not pid:
        return True
    if _pid_alive(int(pid)):
        run["_dead_hits"] = 0
        return True
    bp = _discover_browser_pid(run.get("user_data"))
    if bp and _pid_alive(int(bp)):
        run["browser_pid"] = bp
        run["_dead_hits"] = 0
        return True
    hits = int(run.get("_dead_hits") or 0) + 1
    run["_dead_hits"] = hits
    return hits < 5


def live_profile_ids() -> set[str]:
    alive: set[str] = set()
    dead: list[str] = []
    with _LOCK:
        items = list(_RUNS.items())
    for pid, run in items:
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
    if profile_id in _STOPPING:
        try:
            mark_stopped(profile_id)
        except Exception:
            pass
        return
    _STOPPING.add(profile_id)
    try:
        with _LOCK:
            run = _RUNS.pop(profile_id, None)
        if run:
            try:
                urls = list(run.get("saved_tabs") or [])
                if not urls:
                    ctx = run.get("context")
                    if ctx is None:
                        try:
                            ctx = _context_from_cm(run.get("cm") or run.get("mgr"))
                        except Exception:
                            ctx = None
                    if ctx is not None:
                        urls = snapshot_http_tabs(ctx)
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
                mgr = run.get("mgr")
                if mgr is not None and hasattr(mgr, "__exit__"):
                    mgr.__exit__(None, None, None)
            except Exception:
                pass
            try:
                cm = run.get("cm")
                if cm is not None and hasattr(cm, "close"):
                    cm.close()
            except Exception:
                pass
            try:
                ctx = run.get("context")
                if ctx is not None and hasattr(ctx, "close"):
                    ctx.close()
            except Exception:
                pass
        try:
            mark_stopped(profile_id)
        except Exception:
            pass
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
    if context is None:
        return

    def _on_close() -> None:
        urls: list[str] = []
        try:
            urls = snapshot_http_tabs(context)
        except Exception:
            urls = []
        with _LOCK:
            run = _RUNS.get(profile_id)
            if run is not None:
                run["closed"] = True
                if urls:
                    run["saved_tabs"] = urls
                elif run.get("saved_tabs"):
                    urls = list(run.get("saved_tabs") or [])
        if urls:
            try:
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

        threading.Thread(target=_job, name=f"mm-cfox-stop-{profile_id[:16]}", daemon=True).start()

    try:
        context.on("close", lambda _=None: _on_close())
    except Exception:
        try:
            context.on("close", _on_close)
        except Exception:
            pass




def _ensure_camoufox_root_cache() -> None:
    """Force Camoufox install/cache under Mozilla ROOT (never ~/.cache)."""
    cache = ROOT / "runtime" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["XDG_CACHE_HOME"] = str(cache)


def _camoufox_install_dir() -> Path:
    _ensure_camoufox_root_cache()
    return ROOT / "runtime" / "cache" / "camoufox"


def _find_camoufox_binary() -> Path | None:
    """Filesystem-only discovery. Never call camoufox.pkgman (it may auto-download)."""
    root = _camoufox_install_dir()
    if not root.exists():
        return None
    # Prefer active_version from config.json
    cfg = root / "config.json"
    candidates: list[Path] = []
    if cfg.exists():
        try:
            import json
            data = json.loads(cfg.read_text(encoding="utf-8"))
            rel = data.get("active_version")
            if rel:
                candidates.append(root / str(rel))
        except Exception:
            pass
    # Scan versioned installs
    browsers = root / "browsers"
    if browsers.exists():
        for repo in sorted(browsers.iterdir()):
            if not repo.is_dir() or repo.name.startswith("."):
                continue
            for ver in sorted(repo.iterdir(), reverse=True):
                if ver.is_dir():
                    candidates.append(ver)
    # Legacy flat layout
    candidates.append(root)
    seen: set[str] = set()
    for base in candidates:
        try:
            key = str(base.resolve())
        except Exception:
            key = str(base)
        if key in seen:
            continue
        seen.add(key)
        for name in ("camoufox-bin", "camoufox.exe", "camoufox", "Camoufox"):
            bin_path = base / name
            if bin_path.is_file() and os.access(bin_path, os.X_OK):
                return bin_path
            # mac-style
            mac = base / "Camoufox.app" / "Contents" / "MacOS" / "camoufox"
            if mac.is_file():
                return mac
    return None


def _preflight_camoufox_binary() -> tuple[bool, str]:
    """Return (ok, detail). Must never trigger network download."""
    root = _camoufox_install_dir()
    binary = _find_camoufox_binary()
    if binary is None:
        return False, (
            f"camoufox browser binary missing under {root}/browsers. "
            "Install offline: place zip then run scripts/install_camoufox_local.sh "
            "or XDG_CACHE_HOME=$ROOT/runtime/cache python -m camoufox fetch"
        )
    # Ensure compatibility flag so pkgman does not wipe install on next import
    flag = root / ".0.5_FLAG"
    try:
        flag.touch(exist_ok=True)
    except Exception:
        pass
    return True, str(binary)


def _context_from_cm(cm: Any) -> Any:
    """Normalize Camoufox handle to a Playwright-like BrowserContext."""
    if cm is None:
        return None
    if hasattr(cm, "pages") and hasattr(cm, "new_page"):
        return cm
    if hasattr(cm, "contexts") and cm.contexts:
        return cm.contexts[0]
    return cm


def _firefox_privacy_prefs(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Map webrtc/doh meta → Firefox user prefs (Camoufox)."""
    meta = meta or {}
    prefs: dict[str, Any] = {
        # never touch system proxy; browser uses explicit proxy only
        "network.proxy.type": 0,  # overwritten by playwright proxy channel; keep direct as base
        "media.peerconnection.ice.default_address_only": True,
        "media.peerconnection.ice.no_host": True,
        "media.peerconnection.ice.proxy_only_if_behind_proxy": True,
    }
    mode = str(meta.get("webrtc_mode") or "disable").lower()
    if mode in ("disable", "block", "off"):
        prefs.update(
            {
                "media.peerconnection.enabled": False,
                "media.navigator.enabled": False,
            }
        )
    elif mode in ("spoof", "proxy", "proxy_only"):
        prefs.update(
            {
                "media.peerconnection.enabled": True,
                "media.peerconnection.ice.default_address_only": True,
                "media.peerconnection.ice.no_host": True,
                "media.peerconnection.ice.proxy_only": True,
            }
        )

    # DoH / TRR: mode 3 (TRR-only) kills networking behind SOCKS/mihomo.
    # Default: leave system/proxy DNS (mode 5 = off) unless user explicitly wants TRR
    # and is not using a browser proxy (caller may also pass meta._has_proxy).
    doh_mode = str(meta.get("doh_mode") or "automatic").lower()
    has_proxy = bool(meta.get("_has_proxy")) or str(meta.get("proxy_mode") or "").lower() in (
        "socks5", "mihomo", "http", "https",
    )
    if doh_mode not in ("off", "none", "false", "disable") and not (
        has_proxy and not meta.get("force_doh_with_proxy")
    ):
        tmpl = (
            meta.get("doh_template")
            or meta.get("doh_url")
            or (meta.get("doh_servers") or ["https://cloudflare-dns.com/dns-query"])[0]
        )
        # 2 = TRR first with fallback; NEVER 3 by default
        trr_mode = 2
        if doh_mode in ("secure", "secure-only", "trr-only") and meta.get("doh_secure_ok"):
            trr_mode = 3
        prefs.update(
            {
                "network.trr.mode": trr_mode,
                "network.trr.uri": str(tmpl),
                "network.trr.bootstrapAddress": "",
            }
        )
    else:
        # Explicitly disable TRR so DNS goes through the proxy channel
        prefs.setdefault("network.trr.mode", 5)
    return prefs


class CamoufoxLauncher(EngineLauncher):
    name = "camoufox"

    def launch(self, profile: Profile, *, headless: bool = False, open_check: bool | None = None) -> LaunchResult:
        ensure_layout()
        _ensure_camoufox_root_cache()
        store = ProfileStore()
        user_data = str(store.abs_user_data(profile))
        proxy = playwright_proxy(profile)
        env = profile.env
        try:
            from camoufox.sync_api import Camoufox
        except Exception as e:
            return LaunchResult(
                profile_id=profile.id,
                ok=False,
                message=f"camoufox not available: {e}. Run scripts/bootstrap_runtime.sh",
            )
        # Preflight: filesystem only — NEVER call pkgman.launch_path/camoufox_path
        # (those default download_if_missing=True and can block for 10+ minutes).
        ok_bin, bin_detail = _preflight_camoufox_binary()
        if not ok_bin:
            return LaunchResult(profile_id=profile.id, ok=False, message=bin_detail)

        with browser_only_launch_env(profile) as pol:
            try:
                meta0 = dict(profile.meta or {})
                if open_check is None:
                    open_check = bool(meta0["open_check"]) if "open_check" in meta0 else False
                meta_for_prefs = dict(profile.meta or {})
                meta_for_prefs["_has_proxy"] = bool(proxy)
                meta_for_prefs["proxy_mode"] = str(getattr(profile.proxy, "mode", "") or "")
                prefs = _firefox_privacy_prefs(meta_for_prefs)
                try:
                    prefs.update(camoufox_immersive_prefs(profile.meta or {}))
                except Exception:
                    pass
                # exclude default UBO download — keeps launch offline-friendly & ROOT-local.
                # Profile-level extensions are loaded separately via our runtime/extensions.
                exclude_addons = None
                try:
                    from camoufox import DefaultAddons
                    exclude_addons = list(DefaultAddons)  # exclude ALL defaults
                except Exception:
                    exclude_addons = None
                meta_pre = dict(profile.meta or {})
                # 最强反检测默认：锁定指纹视口 + 窗口尺寸一致
                # comfort: meta.stealth_level=comfort | lock_viewport=false | native_window=true
                lock_vp = want_lock_viewport(meta_pre)
                vp_w = int(getattr(env, "viewport_width", None) or meta_pre.get("viewport_width") or 1920)
                vp_h = int(getattr(env, "viewport_height", None) or meta_pre.get("viewport_height") or 1080)
                opts: dict[str, Any] = {
                    "headless": headless,
                    "persistent_context": True,
                    "user_data_dir": user_data,
                    "locale": env.locale,
                    "firefox_user_prefs": prefs,
                    "addons": [],
                }
                if lock_vp:
                    opts["viewport"] = {"width": max(320, vp_w), "height": max(240, vp_h)}
                    opts["no_viewport"] = False
                else:
                    opts["no_viewport"] = True
                # OS 指纹：优先 profile 绑定；否则按宿主系统
                try:
                    fp_os = None
                    try:
                        plat = (env.fingerprint.platform if env.fingerprint else "") or ""
                        if "Win" in plat:
                            fp_os = "windows"
                        elif "Mac" in plat:
                            fp_os = "macos"
                        elif "Linux" in plat:
                            fp_os = "linux"
                    except Exception:
                        fp_os = None
                    if fp_os:
                        opts["os"] = fp_os
                    else:
                        import platform as _plat
                        sys_os = _plat.system()
                        if sys_os == "Windows":
                            opts["os"] = "windows"
                        elif sys_os == "Darwin":
                            opts["os"] = "macos"
                        else:
                            opts["os"] = "linux"
                except Exception:
                    pass
                # 窗口尺寸：与指纹视口对齐（可 meta.window_width/height 覆盖）
                try:
                    ww = int(meta_pre.get("window_width") or vp_w)
                    wh = int(meta_pre.get("window_height") or vp_h)
                    if lock_vp or (meta_pre.get("window_width") and meta_pre.get("window_height")):
                        opts["window"] = (max(320, ww), max(240, wh))
                except Exception:
                    if lock_vp:
                        opts["window"] = (max(320, vp_w), max(240, vp_h))
                if exclude_addons is not None:
                    opts["exclude_addons"] = exclude_addons
                if env.timezone_id:
                    opts["timezone_id"] = env.timezone_id
                if proxy:
                    opts["proxy"] = proxy
                if env.geolocation:
                    opts["geolocation"] = {
                        "latitude": env.geolocation.latitude,
                        "longitude": env.geolocation.longitude,
                        "accuracy": env.geolocation.accuracy,
                    }
                    # permissions if supported
                    try:
                        opts["permissions"] = list(env.permissions or ["geolocation"])
                    except Exception:
                        pass
                ua = env.user_agent or (env.fingerprint.user_agent if env.fingerprint else None)
                if ua:
                    opts.setdefault("firefox_user_prefs", {})
                # geoip=True makes Camoufox fetch public IP (ipecho.net) via proxy — flaky under
                # some nodes/SSL. Default OFF; we already pass timezone/geolocation/locale ourselves.
                # Opt-in: meta.camoufox_geoip = true | "<ip>" 
                meta = profile.meta or {}
                geo_opt = meta.get("camoufox_geoip")
                if geo_opt is True:
                    opts["geoip"] = True
                elif isinstance(geo_opt, str) and geo_opt.strip():
                    opts["geoip"] = geo_opt.strip()
                # else: omit geoip

                # 拟人轨迹 humanize 默认 ON；软件假光标 showcursor 默认 OFF（系统鼠标外观）
                try:
                    meta_c = profile.meta or {}
                    for k, v in camoufox_cursor_options(meta_c).items():
                        if k == "config":
                            base_cfg = dict(opts.get("config") or {})
                            base_cfg.update(v or {})
                            opts["config"] = base_cfg
                        else:
                            opts[k] = v
                except Exception:
                    opts.setdefault("humanize", True)

                def _enter(launch_opts: dict[str, Any]):
                    b = Camoufox(**launch_opts)
                    context_mgr = b.__enter__()
                    return b, context_mgr

                try:
                    browser, cm = _enter(opts)
                except Exception as e1:
                    msg = str(e1)
                    # retry once without geoip / with geoip disabled if IP lookup failed
                    if "get IP address" in msg or "ipecho" in msg or "geoip" in msg.lower():
                        opts.pop("geoip", None)
                        try:
                            browser, cm = _enter(opts)
                        except Exception as e2:
                            return LaunchResult(profile_id=profile.id, ok=False, message=f"{e1} | retry: {e2}")
                    else:
                        return LaunchResult(profile_id=profile.id, ok=False, message=msg)
                ctx = _context_from_cm(cm)

                # Native OS cursor
                try:
                    if ctx is not None and hasattr(ctx, "add_init_script"):
                        ctx.add_init_script(native_cursor_init_script())
                except Exception:
                    pass
                # fingerprint init
                try:
                    apply_fingerprint_to_context(ctx, env.fingerprint)
                except Exception:
                    try:
                        script = apply_init_script(env.fingerprint)
                        if script and hasattr(ctx, "add_init_script"):
                            ctx.add_init_script(script)
                    except Exception:
                        pass
                try:
                    from mozilla_manager.modules import stealth_svc

                    stealth_svc.apply_stealth_to_context(ctx, profile)
                except Exception:
                    pass
                try:
                    from mozilla_manager.modules import media_fake

                    media_fake.apply_virtual_media_to_context(ctx, profile.meta or {})
                except Exception:
                    pass
                # WebRTC JS hardening (parity with Chromium)
                try:
                    ps = privacy_init_script(profile.meta or {})
                    if ps and hasattr(ctx, "add_init_script"):
                        ctx.add_init_script(ps)
                except Exception:
                    pass

                # pick first page
                page = None
                try:
                    if hasattr(ctx, "pages") and ctx.pages:
                        page = ctx.pages[0]
                    elif hasattr(ctx, "new_page"):
                        page = ctx.new_page()
                except Exception:
                    page = None

                if page is not None and env.languages:
                    try:
                        page.set_extra_http_headers({"Accept-Language": ",".join(env.languages)})
                    except Exception:
                        pass

                # v4 cookie pre-inject
                try:
                    from mozilla_manager.modules import cookies as cookies_mod

                    cookies_mod.inject_cookies_to_context(ctx, profile.id)
                except Exception:
                    pass

                # restore tabs / optional check page
                try:
                    tabs = list((profile.meta or {}).get("tabs") or [])
                    if not tabs:
                        # fallback last tab group
                        for g in list((profile.meta or {}).get("tab_groups") or []):
                            if g.get("name") == "last" and g.get("urls"):
                                tabs = list(g.get("urls") or [])
                                break
                    if open_check and page is not None:
                        uri = write_check_page(profile)
                        page.goto(uri, wait_until="domcontentloaded")
                    for i, url in enumerate(tabs):
                        if not url or not str(url).startswith("http"):
                            continue
                        if page is None:
                            break
                        pg = page if (i == 0 and not open_check) else (
                            ctx.new_page() if hasattr(ctx, "new_page") else page
                        )
                        try:
                            pg.goto(str(url), wait_until="domcontentloaded", timeout=60000)
                        except Exception:
                            pass
                except Exception:
                    if open_check and page is not None:
                        try:
                            uri = write_check_page(profile)
                            page.goto(uri, wait_until="domcontentloaded")
                        except Exception:
                            pass

                # CF always-ready (shared helpers with chromium)
                try:
                    from mozilla_manager.engines.chromium import _install_cf_watch, _pass_cf_if_needed
                    if ctx is not None:
                        _install_cf_watch(ctx, profile)
                    meta = profile.meta or {}
                    if meta.get("auto_cf") or meta.get("pass_cf"):
                        pages = list(getattr(ctx, "pages", []) or ([page] if page else []))
                        for pg in pages:
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

                try:
                    from mozilla_manager.engines.chromium import _discover_browser_pid
                    from mozilla_manager.paths import ROOT
                    bpid = _discover_browser_pid(str(ROOT / profile.user_data_dir))
                except Exception:
                    bpid = None
                meta_l = dict(profile.meta or {})
                try:
                    if bpid and want_immersive(meta_l):
                        apply_immersive_to_browser_pid(bpid, meta_l)
                except Exception:
                    pass
                saved = []
                try:
                    if ctx is not None:
                        saved = snapshot_http_tabs(ctx)
                except Exception:
                    saved = []
                with _LOCK:
                    _RUNS[profile.id] = {
                        "cm": cm,
                        "mgr": browser,
                        "context": ctx,
                        "page": page,
                        "browser_only": pol,
                        "user_data": str(ROOT / profile.user_data_dir) if profile.user_data_dir else None,
                        "browser_pid": bpid,
                        "closed": False,
                        "immersive": bool(want_immersive(meta_l)),
                        "saved_tabs": saved,
                    }
                mark_started(
                    profile.id,
                    {
                        "driver": "camoufox",
                        "engine": "camoufox",
                        "user_data": profile.user_data_dir,
                        "browser_only": bool(pol.get("browser_only")),
                        "fingerprint": env.fingerprint.template_id if env.fingerprint else None,
                        "browser_pid": bpid,
                        "immersive": bool(want_immersive(meta_l)),
                        "stealth_level": meta_l.get("stealth_level") or "max",
                    },
                )
                try:
                    _install_lifecycle_watch(profile.id, ctx)
                except Exception:
                    pass
                return LaunchResult(
                    profile_id=profile.id,
                    ok=True,
                    message=(
                        f"launched camoufox; fp={env.fingerprint.template_id if env.fingerprint else '-'}; "
                        f"browser_only={pol.get('browser_only')}; user_data={profile.user_data_dir}"
                    ),
                )
            except Exception as e:
                try:
                    browser.__exit__(None, None, None)  # type: ignore[name-defined]
                except Exception:
                    pass
                return LaunchResult(profile_id=profile.id, ok=False, message=str(e))

    def stop(self, profile_id: str) -> None:
        _finalize_stop(profile_id, reason="api_stop")


