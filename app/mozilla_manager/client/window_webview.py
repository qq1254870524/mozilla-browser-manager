"""Native window via pywebview — real desktop program frame."""
from __future__ import annotations

from typing import Any

from mozilla_manager.client.bridge import ClientBridge
from mozilla_manager.client.config import ClientConfig


def available() -> bool:
    try:
        import webview  # noqa: F401

        return True
    except Exception:
        return False


def run(cfg: ClientConfig, runtime, *, on_closed=None) -> dict[str, Any]:
    import webview

    bridge = ClientBridge(runtime)
    window = webview.create_window(
        cfg.title,
        url=cfg.url(),
        width=cfg.width,
        height=cfg.height,
        min_size=(cfg.min_width, cfg.min_height),
        confirm_close=False,
        js_api=bridge,
    )

    def _closed():
        if on_closed:
            on_closed()

    try:
        window.events.closed += _closed  # type: ignore
    except Exception:
        pass

    # gui can be 'gtk','qt','edgechromium','cef',... — let library choose
    webview.start(debug=False)
    return {"ok": True, "engine": "pywebview"}
