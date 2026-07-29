"""v3 health: egress IP check, auto rebind env pack, IP→template recommend."""
from __future__ import annotations

from typing import Any

from mozilla_manager import db
from mozilla_manager.env_packs import binding_from_country, detect_egress_country
from mozilla_manager.models import ProxyConfig
from mozilla_manager.store import ProfileStore


def _proxy_url_for_profile(prof) -> str | None:
    p = prof.proxy
    if p.mode == "socks5" and p.socks5:
        s = p.socks5
        if s.startswith("socks"):
            return s
        return f"socks5://{s}"
    if p.mode == "mihomo" and p.mihomo_port:
        # mixed-port accepts http & socks5; prefer socks5 to match browser path
        return f"socks5://127.0.0.1:{p.mihomo_port}"
    return None


def _proxy_url_candidates(prof) -> list[str]:
    """Try socks5 first then http on mihomo mixed-port (some nodes break SOCKS TLS)."""
    p = prof.proxy
    out: list[str] = []
    base = _proxy_url_for_profile(prof)
    if base:
        out.append(base)
    if p.mode == "mihomo" and p.mihomo_port:
        http = f"http://127.0.0.1:{p.mihomo_port}"
        if http not in out:
            out.append(http)
        socks = f"socks5://127.0.0.1:{p.mihomo_port}"
        if socks not in out:
            out.append(socks)
    return out


def check_egress(
    profile_id: str,
    *,
    overall_timeout: float = 15.0,
    retries: int = 2,
    retry_delay: float = 0.6,
) -> dict[str, Any]:
    """Detect egress via profile proxy.

    Right after mihomo start the mixed-port can accept TCP but still fail TLS for a
    short window — retry a couple times within the overall budget.
    """
    import time
    store = ProfileStore()
    prof = store.get(profile_id)
    candidates = _proxy_url_candidates(prof) or [None]
    errors: list[str] = []
    info = None
    proxy = candidates[0] if candidates else None
    deadline = time.monotonic() + max(3.0, float(overall_timeout))
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        if time.monotonic() >= deadline:
            errors.append("overall_timeout")
            break
        for proxy in candidates:
            left = deadline - time.monotonic()
            if left <= 0.2:
                errors.append("overall_timeout")
                break
            try:
                # keep each try short so retries fit the budget
                per = min(4.0, max(1.5, left / max(1, len(candidates))))
                info = detect_egress_country(proxy, timeout=per, overall_timeout=min(left, per * 2))
                break
            except Exception as e:
                errors.append(f"try{attempt}:{proxy}: {e}")
        if info is not None:
            break
        # backoff before next full candidate sweep (mihomo dialer warm-up)
        left = deadline - time.monotonic()
        if attempt + 1 < attempts and left > retry_delay + 0.5:
            time.sleep(min(retry_delay, left / 3))
    if info is None:
        return {"ok": False, "profile_id": profile_id, "error": " | ".join(errors[-8:]), "proxy": proxy, "tried": candidates}
    ip = info.get("ip")
    cc = (info.get("country") or "").upper() or None
    db.update_egress(profile_id, ip, cc)
    expected = (prof.meta or {}).get("expected_country")
    mismatch = bool(expected and cc and str(expected).upper() != cc)
    db.audit(
        "health_egress",
        profile_id,
        {"ip": ip, "country": cc, "expected": expected, "mismatch": mismatch},
    )
    return {
        "ok": True,
        "profile_id": profile_id,
        "proxy": proxy,
        "egress": info,
        "expected_country": expected,
        "mismatch": mismatch,
    }



def rebind_from_egress(profile_id: str, *, only_if_mismatch: bool = True) -> dict[str, Any]:
    """IP 变更/归属变化后自动重绑环境包（整包 country pack）。"""
    return rebind_tz_locale_geo(
        profile_id,
        only_if_mismatch=only_if_mismatch,
        full_pack_on_country_change=True,
        always_refresh_geo=True,
    )


def rebind_tz_locale_geo(
    profile_id: str,
    *,
    only_if_mismatch: bool = False,
    full_pack_on_country_change: bool = True,
    always_refresh_geo: bool = True,
    jitter_when_no_coords: bool = True,
) -> dict[str, Any]:
    """按当前出口 IP 重绑 timezone_id / locale / geolocation（launch 默认路径）。

    - 能读到出口 timezone/lat/lon 时优先用真实值
    - locale/languages 来自国家模板
    - 国家变化时可套用整包（viewport/fingerprint 等）；同国则只改 tz/locale/geo，避免指纹乱跳
    """
    from datetime import datetime, timezone

    from mozilla_manager.models import EnvBinding, GeoLocation

    store = ProfileStore()
    prof = store.get(profile_id)
    # launch rebind needs a bit more patience right after mihomo start
    checked = check_egress(profile_id, overall_timeout=18.0, retries=3, retry_delay=0.7)
    if not checked.get("ok"):
        return {**checked, "rebound": False}
    eg = checked.get("egress") or {}
    cc = (eg.get("country") or "").upper() or None
    if not cc:
        return {**checked, "rebound": False, "message": "no country from egress"}

    expected = (prof.meta or {}).get("expected_country")
    same_cc = bool(expected and str(expected).upper() == cc)
    if only_if_mismatch and same_cc:
        # still allow geo/tz refresh below if always_refresh — only_if_mismatch means skip FULL no-op only when caller wants
        # For classic health-rebind -- only_if_mismatch True and same country: historical behavior was no rebind.
        # Launch path passes only_if_mismatch=False.
        return {**checked, "rebound": False, "message": "country matches, no rebind"}

    old_env = prof.env
    country_changed = not same_cc

    # base from pack
    try:
        pack_env = binding_from_country(cc, jitter=jitter_when_no_coords)
    except Exception as e:
        return {**checked, "rebound": False, "message": f"no env pack for {cc}: {e}"}

    # timezone: egress first
    tz = eg.get("timezone") or pack_env.timezone_id or old_env.timezone_id
    locale = pack_env.locale
    languages = list(pack_env.languages or old_env.languages or [])

    # geo: egress coords first
    lat = eg.get("latitude")
    lon = eg.get("longitude")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except Exception:
        lat = lon = None

    if lat is not None and lon is not None:
        geo = GeoLocation(latitude=lat, longitude=lon, accuracy=float(eg.get("accuracy") or 50.0))
    elif always_refresh_geo:
        geo = pack_env.geolocation or old_env.geolocation
    else:
        geo = old_env.geolocation or pack_env.geolocation

    if country_changed and full_pack_on_country_change:
        # full pack but overlay live tz/geo
        env = EnvBinding(
            timezone_id=str(tz),
            locale=locale,
            languages=languages,
            geolocation=geo,
            user_agent=pack_env.user_agent or old_env.user_agent,
            viewport_width=pack_env.viewport_width,
            viewport_height=pack_env.viewport_height,
            permissions=list(pack_env.permissions or old_env.permissions or ["geolocation"]),
            fingerprint=pack_env.fingerprint or old_env.fingerprint,
        )
    else:
        # same country / soft refresh: only tz locale geo (+ languages)
        env = EnvBinding(
            timezone_id=str(tz),
            locale=locale,
            languages=languages or list(old_env.languages or []),
            geolocation=geo,
            user_agent=old_env.user_agent,
            viewport_width=old_env.viewport_width,
            viewport_height=old_env.viewport_height,
            permissions=list(old_env.permissions or ["geolocation"]),
            fingerprint=old_env.fingerprint,
        )

    meta = dict(prof.meta or {})
    meta["expected_country"] = cc
    meta["last_egress"] = {
        "ip": eg.get("ip"),
        "country": cc,
        "city": eg.get("city"),
        "timezone": eg.get("timezone"),
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    meta["last_launch_rebind"] = {
        "from_country": expected,
        "to_country": cc,
        "timezone_id": env.timezone_id,
        "locale": env.locale,
        "geolocation": env.geolocation.model_dump() if env.geolocation else None,
        "ip": eg.get("ip"),
        "country_changed": country_changed,
        "at": meta["last_egress"]["at"],
    }
    updated = store.update(profile_id, env=env, meta=meta)
    db.upsert_profile_row(updated)
    db.audit("health_rebind", profile_id, meta["last_launch_rebind"])
    return {
        **checked,
        "rebound": True,
        "country_changed": country_changed,
        "env": env.model_dump(mode="json"),
        "profile_id": profile_id,
        "message": f"rebound tz/locale/geo to {cc} ({env.timezone_id}/{env.locale})",
    }


def set_auto_rebind(profile_id: str, enabled: bool = True) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta or {})
    meta["auto_rebind_on_launch"] = bool(enabled)
    updated = store.update(profile_id, meta=meta)
    db.upsert_profile_row(updated)
    db.audit("auto_rebind_set", profile_id, {"enabled": enabled})
    return {"ok": True, "profile_id": profile_id, "auto_rebind_on_launch": bool(enabled)}


def auto_rebind_enabled(prof) -> bool:
    meta = prof.meta or {}
    if "auto_rebind_on_launch" in meta:
        return bool(meta.get("auto_rebind_on_launch"))
    # default ON — 每次 launch 按出口 IP 重绑 tz/locale/geo
    return True


def recommend_from_ip(proxy_url: str | None = None) -> dict[str, Any]:
    """从出口 IP 反推推荐模板."""
    try:
        info = detect_egress_country(proxy_url)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    cc = (info.get("country") or "").upper()
    if not cc:
        return {"ok": False, "egress": info, "message": "no country"}
    try:
        env = binding_from_country(cc, jitter=True)
    except KeyError:
        return {"ok": False, "egress": info, "country": cc, "message": f"no pack for {cc}"}
    return {
        "ok": True,
        "country": cc,
        "egress": info,
        "env": env.model_dump(mode="json"),
    }
