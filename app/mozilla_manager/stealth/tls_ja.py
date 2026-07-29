"""TLS / JA3 / JA4 client profiles (metadata + mihomo client-fingerprint).

True in-browser JA3 rewriting requires a custom Chromium build. v6 provides:
1) Stable TLS *intent* per Profile (chrome/firefox/safari/edge + version)
2) Known JA3/JA4 *reference* strings for reporting & consistency checks
3) Mihomo/Clash-Meta `client-fingerprint` injection on outbound proxies
   so tunnel handshake matches the browser persona where protocol supports it.
"""
from __future__ import annotations

from typing import Any

# Reference values: illustrative stable labels used for persona binding.
# Real live JA3 depends on exact binary/OS; we bind a persona id and optional
# measured values stored on the profile after check-page probe.
TLS_PROFILES: dict[str, dict[str, Any]] = {
    "chrome-131-win": {
        "id": "chrome-131-win",
        "browser": "chrome",
        "version": "131",
        "os": "windows",
        "mihomo_client_fingerprint": "chrome",
        # Reference JA3/JA4 labels (persona tags — not claimed as live wire hashes)
        "ja3_label": "chrome-131-windows-standard",
        "ja4_label": "t13d1516h2_8daaf6152771_b0da82dd6624",
        "alpn": ["h2", "http/1.1"],
        "grease": True,
        "notes": "Default Chromium-like ClientHello persona",
    },
    "chrome-124-win": {
        "id": "chrome-124-win",
        "browser": "chrome",
        "version": "124",
        "os": "windows",
        "mihomo_client_fingerprint": "chrome",
        "ja3_label": "chrome-124-windows-standard",
        "ja4_label": "t13d1516h2_8daaf6152771_d41ae4817557",
        "alpn": ["h2", "http/1.1"],
        "grease": True,
    },
    "chrome-131-mac": {
        "id": "chrome-131-mac",
        "browser": "chrome",
        "version": "131",
        "os": "macos",
        "mihomo_client_fingerprint": "chrome",
        "ja3_label": "chrome-131-macos-standard",
        "ja4_label": "t13d1516h2_8daaf6152771_b6b141b2eas3",
        "alpn": ["h2", "http/1.1"],
        "grease": True,
    },
    "edge-131-win": {
        "id": "edge-131-win",
        "browser": "edge",
        "version": "131",
        "os": "windows",
        "mihomo_client_fingerprint": "edge",
        "ja3_label": "edge-131-windows-standard",
        "ja4_label": "t13d1516h2_8daaf6152771_edge131",
        "alpn": ["h2", "http/1.1"],
        "grease": True,
    },
    "firefox-128-win": {
        "id": "firefox-128-win",
        "browser": "firefox",
        "version": "128",
        "os": "windows",
        "mihomo_client_fingerprint": "firefox",
        "ja3_label": "firefox-128-windows-standard",
        "ja4_label": "t13d1715h2_5b57614c0b6e_5b9c5e3f1a2b",
        "alpn": ["h2", "http/1.1"],
        "grease": False,
    },
    "safari-17-mac": {
        "id": "safari-17-mac",
        "browser": "safari",
        "version": "17",
        "os": "macos",
        "mihomo_client_fingerprint": "safari",
        "ja3_label": "safari-17-macos-standard",
        "ja4_label": "t13d1514h2_safari17_mac",
        "alpn": ["h2", "http/1.1"],
        "grease": False,
    },
    "ios-17": {
        "id": "ios-17",
        "browser": "safari",
        "version": "17",
        "os": "ios",
        "mihomo_client_fingerprint": "ios",
        "ja3_label": "ios17-safari-standard",
        "ja4_label": "t13d1514h2_ios17",
        "alpn": ["h2", "http/1.1"],
        "grease": False,
    },
    "android-chrome": {
        "id": "android-chrome",
        "browser": "chrome",
        "version": "131",
        "os": "android",
        "mihomo_client_fingerprint": "android",
        "ja3_label": "android-chrome-standard",
        "ja4_label": "t13d1516h2_android_chrome",
        "alpn": ["h2", "http/1.1"],
        "grease": True,
    },
}


def pick_tls_profile(
    *,
    platform: str | None = None,
    explicit: str | None = None,
    engine: str | None = None,
) -> dict[str, Any]:
    if explicit and explicit in TLS_PROFILES:
        return dict(TLS_PROFILES[explicit])
    plat = (platform or "").lower()
    eng = (engine or "").lower()
    if "camoufox" in eng or "firefox" in eng:
        return dict(TLS_PROFILES["firefox-128-win"])
    if "mac" in plat:
        return dict(TLS_PROFILES["chrome-131-mac"])
    if "linux" in plat:
        # still chrome persona on linux hosts spoofing win is common; prefer win chrome
        return dict(TLS_PROFILES["chrome-131-win"])
    return dict(TLS_PROFILES["chrome-131-win"])


def apply_client_fingerprint_to_proxies(
    proxies: list[dict[str, Any]] | None,
    client_fp: str = "chrome",
) -> list[dict[str, Any]]:
    """Inject mihomo/Clash-Meta client-fingerprint into compatible outbounds."""
    out: list[dict[str, Any]] = []
    compatible = {"vless", "vmess", "trojan", "http", "socks5", "ss"}
    for px in proxies or []:
        if not isinstance(px, dict):
            continue
        item = dict(px)
        ptype = str(item.get("type") or "").lower()
        # skip info placeholders
        server = str(item.get("server") or "")
        if server in ("127.0.0.1", "0.0.0.0"):
            out.append(item)
            continue
        if ptype in compatible or ptype.startswith("hysteria") or ptype in ("tuic", "wireguard"):
            # only set if not already specified by subscription
            if not item.get("client-fingerprint"):
                item["client-fingerprint"] = client_fp
        out.append(item)
    return out


def list_tls_profiles() -> list[dict[str, Any]]:
    return [dict(v) for v in TLS_PROFILES.values()]
