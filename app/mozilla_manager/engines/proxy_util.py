from __future__ import annotations

from urllib.parse import urlparse

from ..models import Profile


def playwright_proxy(profile: Profile) -> dict | None:
    """Build Playwright/Patchright proxy dict from profile."""
    px = profile.proxy
    if px.mode == "none":
        return None
    if px.mode == "socks5" and px.socks5:
        u = urlparse(px.socks5 if "://" in px.socks5 else f"socks5://{px.socks5}")
        server = f"socks5://{u.hostname}:{u.port}"
        out = {"server": server}
        if u.username:
            out["username"] = u.username
        if u.password:
            out["password"] = u.password
        return out
    if px.mode == "mihomo" and px.mihomo_port:
        return {"server": f"socks5://127.0.0.1:{px.mihomo_port}"}
    return None
