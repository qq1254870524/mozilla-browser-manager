from __future__ import annotations

from urllib.parse import unquote, urlparse

from ..models import Profile


def _split_userinfo(userinfo: str) -> tuple[str, str]:
    """Split user:pass — password may contain ':'."""
    if not userinfo:
        return "", ""
    if ":" not in userinfo:
        return unquote(userinfo), ""
    user, pwd = userinfo.split(":", 1)
    return unquote(user), unquote(pwd)


def parse_proxy_server(raw: str) -> dict:
    """Parse socks5/http proxy URL without breaking on '#' in password.

    urlparse treats '#' as fragment, so passwords like Aa112211### must not
    rely on naive urlparse of an unencoded URL. We support:
      - already-percent-encoded URLs (from build_socks5_url)
      - socks5://user:pass@host:port (pass may contain # if we split manually)
      - host:port
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty proxy")
    scheme = "socks5"
    rest = s
    if "://" in s:
        scheme, rest = s.split("://", 1)
        scheme = (scheme or "socks5").lower()
    # strip accidental leading junk
    rest = rest.strip()
    # fragment cut only if it looks like URL fragment WITHOUT @ after — handle below
    user = pwd = ""
    hostport = rest
    if "@" in rest:
        # split from the RIGHT most @ (host cannot contain @)
        userinfo, hostport = rest.rsplit("@", 1)
        # if userinfo still has scheme leftovers — ignore
        # If password had unencoded '#', url may have been truncated by browsers;
        # for encoded '%23' urlparse path is fine via manual split.
        # Drop real fragment only on hostport side
        if "#" in hostport and hostport.count(":") == 1:
            # host:port#frag
            hostport = hostport.split("#", 1)[0]
        user, pwd = _split_userinfo(userinfo)
    else:
        if "#" in hostport:
            hostport = hostport.split("#", 1)[0]
    hostport = hostport.strip().rstrip("/")
    if hostport.startswith("["):
        # [ipv6]:port
        if "]" not in hostport:
            raise ValueError(f"bad ipv6 proxy: {raw}")
        host, _, port_s = hostport[1:].partition("]")
        port_s = port_s.lstrip(":")
    else:
        if ":" not in hostport:
            raise ValueError(f"proxy host:port required: {raw}")
        host, port_s = hostport.rsplit(":", 1)
    host = unquote(host.strip())
    try:
        port = int(port_s.strip())
    except Exception as e:
        raise ValueError(f"bad proxy port in {raw!r}: {e}") from e
    if not host or not port:
        raise ValueError(f"invalid proxy: {raw}")
    return {
        "scheme": scheme or "socks5",
        "host": host,
        "port": port,
        "username": user,
        "password": pwd,
    }


def playwright_proxy(profile: Profile) -> dict | None:
    """Build Playwright/Patchright/Camoufox proxy dict from profile.

    Always returns {server, username?, password?} with server as scheme://host:port
    (credentials as separate fields — required by Patchright; avoids # in pass).
    """
    px = profile.proxy
    if px.mode == "none":
        return None
    meta = getattr(profile, "meta", None) or {}
    if px.mode == "socks5" and px.socks5:
        try:
            parsed = parse_proxy_server(px.socks5 if "://" in px.socks5 else f"socks5://{px.socks5}")
        except Exception:
            # last resort: urlparse (works for properly percent-encoded URLs)
            raw = px.socks5 if "://" in px.socks5 else f"socks5://{px.socks5}"
            u = urlparse(raw)
            if not u.hostname or not u.port:
                return None
            parsed = {
                "scheme": (u.scheme or "socks5").lower(),
                "host": u.hostname,
                "port": int(u.port),
                "username": unquote(u.username) if u.username else "",
                "password": unquote(u.password) if u.password else "",
            }
        scheme = parsed["scheme"] if parsed["scheme"] in ("socks5", "socks5h", "http", "https") else "socks5"
        # Playwright recognizes socks5:// 
        if scheme == "socks5h":
            scheme = "socks5"
        server = f"{scheme}://{parsed['host']}:{parsed['port']}"
        out: dict = {"server": server}
        user = str(meta.get("socks5_username") or parsed.get("username") or "")
        pwd = str(meta.get("socks5_password") or parsed.get("password") or "")
        if user:
            out["username"] = user
        if pwd:
            out["password"] = pwd
        return out
    if px.mode == "mihomo" and px.mihomo_port:
        # HTTP on mixed-port is far more reliable for Chromium/Patchright than socks5
        # (socks5 + Playwright host-resolver-rules → intermittent ERR_PROXY_CONNECTION_FAILED).
        meta = getattr(profile, "meta", None) or {}
        proto = str(meta.get("mihomo_proxy_proto") or "http").lower().strip()
        if proto in ("socks5", "socks5h", "socks"):
            proto = "socks5"
        else:
            proto = "http"
        return {"server": f"{proto}://127.0.0.1:{int(px.mihomo_port)}"}
    return None
