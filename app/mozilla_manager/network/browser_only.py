"""Browser-only proxy routing.

Rule: never touch system proxy / never force manager HTTP(S)_PROXY.
Only the browser process receives Playwright/Camoufox `proxy=` injection.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from ..models import Profile, ProxyConfig

# Env vars that would make the *manager* process inherit a proxy
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "FTP_PROXY",
    "ftp_proxy",
)


def is_browser_only(proxy: ProxyConfig | None) -> bool:
    if proxy is None:
        return True
    return bool(getattr(proxy, "browser_only", True))


def strip_manager_proxy_env() -> dict[str, str]:
    """Remove proxy env from current process. Returns previous values for restore."""
    saved: dict[str, str] = {}
    for k in _PROXY_ENV_KEYS:
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    return saved


def restore_env(saved: dict[str, str]) -> None:
    for k, v in saved.items():
        os.environ[k] = v


@contextmanager
def browser_only_launch_env(profile: Profile | None = None) -> Iterator[dict[str, Any]]:
    """Context manager used around browser launch.

    - Strips manager-process proxy inheritance so only engine proxy applies
    - Never writes Windows/Linux system proxy settings
    - Optional Linux netns is documented but not auto-enabled (needs root)
    """
    enforce = True
    if profile is not None:
        enforce = is_browser_only(profile.proxy)
    saved: dict[str, str] = {}
    info: dict[str, Any] = {
        "browser_only": enforce,
        "stripped_keys": [],
        "system_proxy_touched": False,
        "netns": None,
        "note": "proxy applied only via engine proxy= argument",
    }
    try:
        if enforce:
            saved = strip_manager_proxy_env()
            info["stripped_keys"] = sorted(saved.keys())
        yield info
    finally:
        if saved:
            restore_env(saved)


def launch_proxy_policy(profile: Profile) -> dict[str, Any]:
    """Describe how proxy will be applied for this profile (for doctor/UI)."""
    p = profile.proxy
    return {
        "mode": p.mode,
        "browser_only": is_browser_only(p),
        "socks5": p.socks5,
        "mihomo_port": p.mihomo_port,
        "node_name": p.node_name,
        "applies_to": "browser_process_only",
        "system_proxy": "never",
        "manager_http_proxy": "stripped_during_launch" if is_browser_only(p) else "inherited",
    }
