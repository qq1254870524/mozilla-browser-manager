"""JS bridge exposed to embedded Web UI (optional pywebview api)."""
from __future__ import annotations

from typing import Any

from mozilla_manager.paths import ROOT
from mozilla_manager.client import __version__ as CLIENT_VERSION


class ClientBridge:
    """Methods here become window.pywebview.api.* inside the page."""

    def __init__(self, runtime):
        self.runtime = runtime

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "client": CLIENT_VERSION, "root": str(ROOT)}

    def root(self) -> str:
        return str(ROOT)

    def server_url(self) -> str:
        return self.runtime.url

    def health(self) -> dict[str, Any]:
        try:
            from mozilla_manager.modules import system

            h = system.health()
            h["client"] = CLIENT_VERSION
            h["mode"] = "desktop-client"
            return h
        except Exception as e:
            return {"ok": False, "error": str(e)}
