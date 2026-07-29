"""Desktop client entry — one program bootstraps API + native UI."""
from __future__ import annotations

# Windows cp936/gbk consoles blow up on emoji node names (🇺🇸…); force UTF-8 I/O.
try:
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
except Exception:
    pass

import argparse
import sys
from typing import Any

from mozilla_manager.client import __version__
from mozilla_manager.client.config import load_config, save_config, ClientConfig
from mozilla_manager.client.runtime import ServerRuntime
from mozilla_manager.paths import ROOT, ensure_layout


def _parse(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mozilla-client", description="Mozilla Manager 桌面客户端")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--no-window", action="store_true", help="只启动后端（仍由客户端进程托管）")
    p.add_argument("--tk", action="store_true", help="强制使用 tk 控制台壳")
    p.add_argument("--webview", action="store_true", help="强制 pywebview")
    p.add_argument("--allow-browser", action="store_true", help="无内嵌引擎时允许系统浏览器")
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    return p.parse_args(argv)


def build_config(ns: argparse.Namespace) -> ClientConfig:
    cfg = load_config()
    # persistent preferences only
    dirty = False
    if ns.host:
        cfg.host = ns.host
        dirty = True
    if ns.port:
        cfg.port = ns.port
        dirty = True
    if ns.width:
        cfg.width = ns.width
        dirty = True
    if ns.height:
        cfg.height = ns.height
        dirty = True
    if dirty:
        save_config(cfg)
    # ephemeral flags (do not persist)
    if ns.no_window:
        cfg.open_window = False
    if ns.allow_browser:
        cfg.allow_system_browser_fallback = True
    if ns.tk:
        cfg.extra = dict(cfg.extra or {})
        cfg.extra["force_tk"] = True
    if ns.webview:
        cfg.extra = dict(cfg.extra or {})
        cfg.extra["force_webview"] = True
    return cfg


def run_client(argv: list[str] | None = None) -> int:
    ensure_layout()
    ns = _parse(argv)
    cfg = build_config(ns)

    print(f"[mozilla-client] version={__version__}")
    print(f"[mozilla-client] ROOT={ROOT}")
    print(f"[mozilla-client] starting API {cfg.url()}")

    runtime = ServerRuntime(cfg)
    boot = runtime.start(block_ready=True)
    if not boot.get("ok"):
        print(f"[mozilla-client] backend failed: {boot.get('error')}", file=sys.stderr)
        return 2
    print(f"[mozilla-client] backend ready reused={boot.get('reused')} owned={boot.get('owned')} url={boot.get('url')}")
    healthy = runtime.wait_healthy(12.0)
    print(f"[mozilla-client] health={'ok' if healthy else 'degraded'}")

    # Close window / Ctrl+C / SIGTERM → stop API + browsers + mihomo + loops
    _shut_once = {"done": False}

    def _shutdown(reason: str = "close") -> None:
        if _shut_once["done"]:
            return
        _shut_once["done"] = True
        print(f"[mozilla-client] shutting down all Mozilla services ({reason})...")
        try:
            info = runtime.stop()
            print(f"[mozilla-client] shutdown done: {info}")
        except Exception as e:
            print(f"[mozilla-client] shutdown error: {e}", file=sys.stderr)

    import atexit
    import signal

    atexit.register(lambda: _shutdown("atexit"))

    def _sig_handler(signum, _frame):  # noqa: ANN001
        _shutdown(f"signal:{signum}")
        raise SystemExit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _sig_handler)
        except Exception:
            pass

    if not cfg.open_window:
        print("[mozilla-client] --no-window : server running in this process, Ctrl+C to stop ALL services")
        try:
            while True:
                import time

                time.sleep(1.0)
                if runtime.error:
                    print("server error", runtime.error)
                    _shutdown("server-error")
                    return 3
        except KeyboardInterrupt:
            _shutdown("keyboard")
            return 0

    # choose window engine
    force_tk = bool(cfg.extra.get("force_tk"))
    force_wv = bool(cfg.extra.get("force_webview"))

    result: dict[str, Any]
    if not force_tk:
        from mozilla_manager.client import window_webview

        if force_wv or window_webview.available():
            try:
                print("[mozilla-client] opening native window (pywebview)")
                result = window_webview.run(cfg, runtime, on_closed=lambda: _shutdown("window-closed"))
                print("[mozilla-client] window closed", result)
                _shutdown("window-closed")
                return 0
            except Exception as e:
                print(f"[mozilla-client] pywebview failed: {e}")

    from mozilla_manager.client import window_tk

    if window_tk.available():
        print("[mozilla-client] opening desktop control center (tk)")
        try:
            result = window_tk.run(cfg, runtime, on_closed=lambda: _shutdown("window-closed"))
            print("[mozilla-client] tk shell closed", result)
            _shutdown("window-closed")
            return 0
        except Exception as e:
            print(f"[mozilla-client] tk failed: {e}")

    # last resort: keep process alive with server; optional browser
    print("[mozilla-client] no GUI backend available (e.g. headless WSL).")
    print(f"[mozilla-client] API is running inside this program: {cfg.url()}")
    if cfg.allow_system_browser_fallback:
        import webbrowser

        webbrowser.open(cfg.url())
        print("[mozilla-client] system browser fallback opened")
    else:
        print("[mozilla-client] tip: on Windows/Ubuntu desktop, pywebview provides a real app window.")
        print("[mozilla-client] tip: pass --allow-browser to open system browser as fallback.")
    try:
        while True:
            import time

            time.sleep(1.0)
    except KeyboardInterrupt:
        _shutdown("keyboard")
    return 0


def main() -> None:
    raise SystemExit(run_client())
