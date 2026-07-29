"""v7 one-click network diagnostics: proxy / DNS / WebRTC leak / IP geo."""
from __future__ import annotations

import json
import socket
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from mozilla_manager.env_packs import detect_egress_country
from mozilla_manager.launch_gate import _proxy_url
from mozilla_manager.network.net_quality import run_net_quality
from mozilla_manager.paths import LOG_DIR, ensure_layout, safe_resolve
from mozilla_manager.store import ProfileStore


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_proxy_connectivity(proxy_url: str | None, timeout: float = 5.0) -> dict[str, Any]:
    """Probe proxy with multiple URL schemes / TLS modes (mihomo mixed-port friendly)."""
    if not proxy_url:
        return {"ok": False, "error": "no proxy configured", "proxy": None}
    t0 = time.perf_counter()
    # Expand mihomo mixed-port into socks5 + http candidates
    candidates = [proxy_url]
    if "127.0.0.1:" in proxy_url or "localhost:" in proxy_url:
        try:
            hostport = proxy_url.split("://", 1)[-1]
            port = int(hostport.rsplit(":", 1)[-1])
            for scheme in ("socks5", "http"):
                u = f"{scheme}://127.0.0.1:{port}"
                if u not in candidates:
                    candidates.append(u)
        except Exception:
            pass
    probes = (
        "https://cloudflare.com/cdn-cgi/trace",
        "https://1.1.1.1/cdn-cgi/trace",
        "http://1.1.1.1/cdn-cgi/trace",
    )
    errors: list[str] = []
    for proxy in candidates:
        for verify in (True, False):
            for url in probes:
                try:
                    with httpx.Client(
                        proxy=proxy,
                        timeout=timeout,
                        follow_redirects=True,
                        verify=verify,
                    ) as client:
                        r = client.get(url)
                        body = r.text
                        meta = dict(line.split("=", 1) for line in body.splitlines() if "=" in line)
                        ms = (time.perf_counter() - t0) * 1000
                        if r.status_code == 200 and (meta.get("ip") or meta.get("loc") or "ip=" in body):
                            return {
                                "ok": True,
                                "status": r.status_code,
                                "ms": round(ms, 1),
                                "ip": meta.get("ip"),
                                "loc": meta.get("loc"),
                                "proxy": proxy,
                                "probe": url,
                                "tls_verify": verify,
                            }
                        errors.append(f"{proxy} {url} status={r.status_code}")
                except Exception as e:
                    errors.append(f"{proxy} {url} verify={verify}: {e}")
                # hard cap ~12s total
                if (time.perf_counter() - t0) > 12:
                    break
            if (time.perf_counter() - t0) > 12:
                break
        if (time.perf_counter() - t0) > 12:
            break
    return {
        "ok": False,
        "error": " | ".join(errors[:6]) or "proxy probe failed",
        "ms": round((time.perf_counter() - t0) * 1000, 1),
        "proxy": proxy_url,
        "tried": candidates,
    }


def check_dns(hosts: list[str] | None = None, timeout: float = 3.0) -> dict[str, Any]:
    hosts = hosts or ["cloudflare.com", "google.com", "dns.google", "example.com"]
    rows = []
    ok_n = 0
    for h in hosts:
        t0 = time.perf_counter()
        try:
            infos = socket.getaddrinfo(h, 443, type=socket.SOCK_STREAM)
            addrs = sorted({i[4][0] for i in infos})
            ms = (time.perf_counter() - t0) * 1000
            rows.append({"host": h, "ok": True, "addrs": addrs[:5], "ms": round(ms, 1)})
            ok_n += 1
        except Exception as e:
            rows.append({"host": h, "ok": False, "error": str(e), "ms": round((time.perf_counter() - t0) * 1000, 1)})
    return {"ok": ok_n == len(hosts), "resolved": ok_n, "total": len(hosts), "items": rows}


def check_webrtc_policy(meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = meta or {}
    mode = str(meta.get("webrtc_mode") or "disable")
    return {
        "ok": mode in ("disable", "spoof"),
        "webrtc_mode": mode,
        "recommendation": "disable or spoof",
        "leak_risk": "low" if mode in ("disable", "spoof") else "high",
        "note": "Browser WebRTC hard-block/spoof applied at launch via anti_leak",
    }


def check_ip_geo(proxy_url: str | None) -> dict[str, Any]:
    # Try socks then http for mihomo mixed-port; keep overall budget tight.
    candidates = [proxy_url] if proxy_url else [None]
    if proxy_url and ("127.0.0.1:" in proxy_url or "localhost:" in proxy_url):
        try:
            port = int(proxy_url.rsplit(":", 1)[-1])
            for scheme in ("socks5", "http"):
                u = f"{scheme}://127.0.0.1:{port}"
                if u not in candidates:
                    candidates.append(u)
        except Exception:
            pass
    errors: list[str] = []
    for proxy in candidates:
        try:
            info = detect_egress_country(proxy, timeout=4.0, overall_timeout=10.0)
            return {
                "ok": True,
                "ip": info.get("ip"),
                "country": info.get("country"),
                "city": info.get("city"),
                "timezone": info.get("timezone"),
                "latitude": info.get("latitude"),
                "longitude": info.get("longitude"),
                "provider": info.get("provider"),
                "proxy": proxy,
            }
        except Exception as e:
            errors.append(f"{proxy}: {e}")
    return {"ok": False, "error": " | ".join(errors[:4]) or "geo failed"}


def diagnose_profile(profile_id: str, *, samples: int = 4) -> dict[str, Any]:
    ensure_layout()
    prof = ProfileStore().get(profile_id)
    proxy = _proxy_url(prof)
    proxy_r = check_proxy_connectivity(proxy)
    dns_r = check_dns()
    webrtc_r = check_webrtc_policy(prof.meta)
    geo_r = check_ip_geo(proxy)
    quality = run_net_quality(
        proxy,
        timezone_id=prof.env.timezone_id,
        locale=prof.env.locale,
        expected_country=(prof.meta or {}).get("expected_country"),
        languages=list(prof.env.languages or []),
        samples=samples,
        probe_egress=False,  # already have geo_r
    )
    # merge geo into quality view
    quality["egress"] = {k: geo_r.get(k) for k in ("ip", "country", "city", "timezone", "latitude", "longitude", "error")}
    from mozilla_manager.network.net_quality import geo_consistency

    quality["geo"] = geo_consistency(
        egress=geo_r if geo_r.get("ok") else {},
        timezone_id=prof.env.timezone_id,
        locale=prof.env.locale,
        expected_country=(prof.meta or {}).get("expected_country"),
        languages=list(prof.env.languages or []),
    )

    overall_ok = bool(dns_r.get("ok")) and bool(webrtc_r.get("ok")) and (bool(proxy_r.get("ok")) if proxy else True)
    report = {
        "ok": overall_ok,
        "profile_id": profile_id,
        "at": _now(),
        "proxy": proxy_r,
        "dns": dns_r,
        "webrtc": webrtc_r,
        "ip_geo": geo_r,
        "quality": quality,
        "summary": {
            "proxy_ok": proxy_r.get("ok"),
            "dns_ok": dns_r.get("ok"),
            "webrtc_ok": webrtc_r.get("ok"),
            "geo_ok": geo_r.get("ok"),
            "stability": (quality.get("latency") or {}).get("stability"),
            "loss_pct": (quality.get("latency") or {}).get("loss_pct"),
            "geo_score": (quality.get("geo") or {}).get("score"),
        },
    }
    path = safe_resolve(LOG_DIR / "diagnose" / f"{profile_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["log"] = str(path)
    try:
        from mozilla_manager import db

        db.audit("diagnose", profile_id, report["summary"])
    except Exception:
        pass
    return report
