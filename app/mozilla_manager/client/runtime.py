"""Backend runtime supervisor — starts modular FastAPI inside client process."""
from __future__ import annotations

import os
import socket
import threading
import time
from typing import Any

from mozilla_manager.paths import ROOT, BROWSERS_DIR, ensure_layout
from mozilla_manager.client.config import ClientConfig


class ServerRuntime:
    def __init__(self, cfg: ClientConfig):
        self.cfg = cfg
        self._thread: threading.Thread | None = None
        self._server = None
        self._started = threading.Event()
        self._error: str | None = None
        self._stopping = False
        # True only when THIS client process started the uvicorn server.
        self._owned_server = False
        self._full_shutdown_done = False

    @property
    def url(self) -> str:
        return self.cfg.url()

    @property
    def ready(self) -> bool:
        return self._started.is_set() and self._error is None

    @property
    def error(self) -> str | None:
        return self._error

    def is_port_open(self) -> bool:
        try:
            with socket.create_connection((self.cfg.host, self.cfg.port), timeout=0.5):
                return True
        except OSError:
            return False

    def _prepare_env(self) -> None:
        ensure_layout()
        os.environ.setdefault("PYTHONPATH", str(ROOT / "app"))
        import sys

        app_dir = str(ROOT / "app")
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR))
        os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "runtime" / "cache"))
        os.environ.setdefault("MOZILLA_MANAGER_ROOT", str(ROOT))
        # Never route local API via system/user HTTP proxy
        os.environ["NO_PROXY"] = "127.0.0.1,localhost," + os.environ.get("NO_PROXY", "")
        os.environ["no_proxy"] = os.environ["NO_PROXY"]

    def start(self, *, block_ready: bool = True) -> dict[str, Any]:
        if self.ready or self.is_port_open():
            # already serving (maybe previous serve) — do not claim ownership
            self._started.set()
            self._owned_server = False
            return {"ok": True, "url": self.url, "reused": True}

        self._prepare_env()

        def _run() -> None:
            try:
                import uvicorn
                from mozilla_manager.api import create_app

                app = create_app()
                config = uvicorn.Config(
                    app,
                    host=self.cfg.host,
                    port=self.cfg.port,
                    log_level="info",
                    reload=False,
                    access_log=False,
                )
                self._server = uvicorn.Server(config)
                self._started.set()
                self._server.run()
            except Exception as e:
                self._error = str(e)
                self._started.set()

        self._owned_server = True
        self._thread = threading.Thread(target=_run, name="mozilla-api", daemon=True)
        self._thread.start()

        if not block_ready:
            return {"ok": True, "url": self.url, "reused": False, "async": True, "owned": True}

        deadline = time.time() + float(self.cfg.server_timeout_sec)
        while time.time() < deadline:
            if self._error:
                return {"ok": False, "error": self._error, "url": self.url}
            if self.is_port_open():
                # Prefer real /api/health — bare port-open can race a dying previous process
                # or hit before routes are bound, which looked like mass 404s in matrix tests.
                try:
                    import urllib.request
                    req = urllib.request.Request(self.url + "api/health")
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(req, timeout=1.0) as r:
                        if r.status == 200:
                            return {"ok": True, "url": self.url, "reused": False, "owned": True}
                except Exception:
                    pass
            time.sleep(0.1)
        return {"ok": False, "error": "server start timeout", "url": self.url}

    def wait_healthy(self, timeout: float = 15.0) -> bool:
        import urllib.request

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(self.url + "api/health", timeout=1.0) as r:
                    if r.status == 200:
                        return True
            except Exception:
                time.sleep(0.2)
        return False

    def shutdown_all_services(self) -> dict[str, Any]:
        """Stop browsers / mihomo / loops under ROOT. Safe to call multiple times."""
        if self._full_shutdown_done:
            return {"ok": True, "already": True}
        self._full_shutdown_done = True
        try:
            from mozilla_manager.modules.system import shutdown_all

            return shutdown_all(stop_browsers=True, stop_mihomo=True)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop(self) -> dict[str, Any]:
        """Close client: stop API (if owned) + all Mozilla child services."""
        self._stopping = True
        result: dict[str, Any] = {"ok": True, "owned_server": self._owned_server}

        # Always tear down browsers/mihomo/loops, even if API was reused.
        result["services"] = self.shutdown_all_services()

        srv = self._server
        if self._owned_server and srv is not None:
            try:
                srv.should_exit = True
            except Exception as e:
                result["server_stop_error"] = str(e)
            # wait briefly for uvicorn thread to exit
            th = self._thread
            if th and th.is_alive():
                th.join(timeout=3.0)
            result["server_stopped"] = True
        else:
            # Reused external server: try graceful HTTP stop if available; otherwise leave note.
            # We still stopped child services above. External uvicorn may remain — caller can kill.
            result["server_stopped"] = False
            result["note"] = "API was external/reused; child services stopped"
        return result
