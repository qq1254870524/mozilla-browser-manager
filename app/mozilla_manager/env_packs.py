"""Country env packs + node-name → country recommendation (v2)."""
from __future__ import annotations

import json
import random
import re
from typing import Any

from .models import EnvBinding, FingerprintConfig, GeoLocation
from .paths import ENV_PACKS_DIR, ensure_layout

# flag emoji / keywords → ISO country
FLAG_TO_CC: dict[str, str] = {
    "🇯🇵": "JP",
    "🇭🇰": "HK",
    "🇸🇬": "SG",
    "🇺🇸": "US",
    "🇬🇧": "GB",
    "🇩🇪": "DE",
    "🇹🇼": "TW",
    "🇰🇷": "KR",
    "🇫🇷": "FR",
    "🇨🇦": "CA",
    "🇦🇺": "AU",
    "🇳🇱": "NL",
    "🇷🇺": "RU",
    "🇮🇳": "IN",
    "🇧🇷": "BR",
    "🇹🇷": "TR",
    "🇲🇾": "MY",
    "🇹🇭": "TH",
    "🇻🇳": "VN",
    "🇵🇭": "PH",
    "🇮🇩": "ID",
    "🇲🇴": "MO",
    "🇨🇳": "CN",
    "🇮🇹": "IT",
    "🇪🇸": "ES",
    "🇨🇭": "CH",
    "🇸🇪": "SE",
    "🇵🇱": "PL",
    "🇦🇪": "AE",
    "🇦🇷": "AR",
    "🇲🇽": "MX",
}

KEYWORD_TO_CC: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"日本|tokyo|osaka|japan|\bjp\b", re.I), "JP"),
    (re.compile(r"香港|hong\s*kong|\bhk\b", re.I), "HK"),
    (re.compile(r"新加坡|singapore|\bsg\b", re.I), "SG"),
    (re.compile(r"台湾|taiwan|\btw\b", re.I), "TW"),
    (re.compile(r"韩国|korea|seoul|\bkr\b", re.I), "KR"),
    (re.compile(r"美国|united\s*states|\busa\b|\bus\b", re.I), "US"),
    (re.compile(r"英国|london|united\s*kingdom|\buk\b|\bgb\b", re.I), "GB"),
    (re.compile(r"德国|germany|berlin|frankfurt|\bde\b", re.I), "DE"),
    (re.compile(r"法国|france|paris|\bfr\b", re.I), "FR"),
    (re.compile(r"加拿大|canada|toronto|\bca\b", re.I), "CA"),
    (re.compile(r"澳洲|澳大利亚|australia|sydney|\bau\b", re.I), "AU"),
    (re.compile(r"荷兰|netherlands|amsterdam|\bnl\b", re.I), "NL"),
    (re.compile(r"土耳其|turkey|istanbul|\btr\b", re.I), "TR"),
    (re.compile(r"马来|malaysia|kuala|\bmy\b", re.I), "MY"),
    (re.compile(r"泰国|thailand|bangkok|\bth\b", re.I), "TH"),
    (re.compile(r"越南|vietnam|\bvn\b", re.I), "VN"),
    (re.compile(r"菲律宾|philippines|manila|\bph\b", re.I), "PH"),
    (re.compile(r"印尼|indonesia|jakarta|\bid\b", re.I), "ID"),
    (re.compile(r"阿联酋|dubai|uae|\bae\b", re.I), "AE"),
]

DEFAULT_PACKS: dict[str, dict[str, Any]] = {
    "DE": {
        "timezone_id": "Europe/Berlin",
        "locale": "de-DE",
        "languages": ["de-DE", "de", "en-US", "en"],
        "cities": [
            {"name": "Berlin", "lat": 52.52, "lon": 13.405},
            {"name": "Munich", "lat": 48.137, "lon": 11.576},
            {"name": "Frankfurt", "lat": 50.110, "lon": 8.682},
        ],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "US": {
        "timezone_id": "America/New_York",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "cities": [
            {"name": "New York", "lat": 40.7128, "lon": -74.0060},
            {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
            {"name": "Chicago", "lat": 41.8781, "lon": -87.6298},
        ],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "JP": {
        "timezone_id": "Asia/Tokyo",
        "locale": "ja-JP",
        "languages": ["ja-JP", "ja", "en-US"],
        "cities": [
            {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
            {"name": "Osaka", "lat": 34.6937, "lon": 135.5023},
        ],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome-ja",
    },
    "GB": {
        "timezone_id": "Europe/London",
        "locale": "en-GB",
        "languages": ["en-GB", "en"],
        "cities": [{"name": "London", "lat": 51.5074, "lon": -0.1278}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "HK": {
        "timezone_id": "Asia/Hong_Kong",
        "locale": "zh-HK",
        "languages": ["zh-HK", "zh", "en-US", "en"],
        "cities": [{"name": "Hong Kong", "lat": 22.3193, "lon": 114.1694}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome-zh",
    },
    "SG": {
        "timezone_id": "Asia/Singapore",
        "locale": "en-SG",
        "languages": ["en-SG", "en", "zh-CN"],
        "cities": [{"name": "Singapore", "lat": 1.3521, "lon": 103.8198}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "TW": {
        "timezone_id": "Asia/Taipei",
        "locale": "zh-TW",
        "languages": ["zh-TW", "zh", "en-US"],
        "cities": [{"name": "Taipei", "lat": 25.0330, "lon": 121.5654}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome-zh",
    },
    "KR": {
        "timezone_id": "Asia/Seoul",
        "locale": "ko-KR",
        "languages": ["ko-KR", "ko", "en-US"],
        "cities": [{"name": "Seoul", "lat": 37.5665, "lon": 126.9780}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "FR": {
        "timezone_id": "Europe/Paris",
        "locale": "fr-FR",
        "languages": ["fr-FR", "fr", "en-US"],
        "cities": [{"name": "Paris", "lat": 48.8566, "lon": 2.3522}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "CA": {
        "timezone_id": "America/Toronto",
        "locale": "en-CA",
        "languages": ["en-CA", "en", "fr-CA"],
        "cities": [
            {"name": "Toronto", "lat": 43.6532, "lon": -79.3832},
            {"name": "Vancouver", "lat": 49.2827, "lon": -123.1207},
        ],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "AU": {
        "timezone_id": "Australia/Sydney",
        "locale": "en-AU",
        "languages": ["en-AU", "en"],
        "cities": [{"name": "Sydney", "lat": -33.8688, "lon": 151.2093}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "NL": {
        "timezone_id": "Europe/Amsterdam",
        "locale": "nl-NL",
        "languages": ["nl-NL", "nl", "en-US"],
        "cities": [{"name": "Amsterdam", "lat": 52.3676, "lon": 4.9041}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "TR": {
        "timezone_id": "Europe/Istanbul",
        "locale": "tr-TR",
        "languages": ["tr-TR", "tr", "en-US"],
        "cities": [{"name": "Istanbul", "lat": 41.0082, "lon": 28.9784}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "MY": {
        "timezone_id": "Asia/Kuala_Lumpur",
        "locale": "ms-MY",
        "languages": ["ms-MY", "en-US", "zh-CN"],
        "cities": [{"name": "Kuala Lumpur", "lat": 3.1390, "lon": 101.6869}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "TH": {
        "timezone_id": "Asia/Bangkok",
        "locale": "th-TH",
        "languages": ["th-TH", "th", "en-US"],
        "cities": [{"name": "Bangkok", "lat": 13.7563, "lon": 100.5018}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "VN": {
        "timezone_id": "Asia/Ho_Chi_Minh",
        "locale": "vi-VN",
        "languages": ["vi-VN", "vi", "en-US"],
        "cities": [{"name": "Ho Chi Minh", "lat": 10.8231, "lon": 106.6297}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "PH": {
        "timezone_id": "Asia/Manila",
        "locale": "en-PH",
        "languages": ["en-PH", "en", "fil"],
        "cities": [{"name": "Manila", "lat": 14.5995, "lon": 120.9842}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "ID": {
        "timezone_id": "Asia/Jakarta",
        "locale": "id-ID",
        "languages": ["id-ID", "id", "en-US"],
        "cities": [{"name": "Jakarta", "lat": -6.2088, "lon": 106.8456}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "AE": {
        "timezone_id": "Asia/Dubai",
        "locale": "ar-AE",
        "languages": ["ar-AE", "ar", "en-US"],
        "cities": [{"name": "Dubai", "lat": 25.2048, "lon": 55.2708}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome",
    },
    "MO": {
        "timezone_id": "Asia/Macau",
        "locale": "zh-MO",
        "languages": ["zh-MO", "zh", "pt-MO", "en-US"],
        "cities": [{"name": "Macau", "lat": 22.1987, "lon": 113.5439}],
        "viewport": [1920, 1080],
        "fingerprint": "win11-chrome-zh",
    },
}


def _merged_default_packs() -> dict[str, dict]:
    """v7: core + global country templates."""
    try:
        from .env_packs_global import GLOBAL_PACKS
        merged = dict(DEFAULT_PACKS)
        for k, v in GLOBAL_PACKS.items():
            if k not in merged:
                merged[k] = v
        return merged
    except Exception:
        return dict(DEFAULT_PACKS)


def seed_packs(*, force: bool = False) -> None:
    ensure_layout()
    for code, pack in _merged_default_packs().items():
        path = ENV_PACKS_DIR / f"{code}.json"
        if force or not path.exists():
            path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
            continue
        # merge missing keys (e.g. fingerprint) without clobbering user edits
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
            continue
        changed = False
        for k, v in pack.items():
            if k not in existing:
                existing[k] = v
                changed = True
        if changed:
            path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def list_packs() -> list[dict[str, Any]]:
    seed_packs()
    out = []
    for f in sorted(ENV_PACKS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({"country": f.stem.upper(), **{k: data.get(k) for k in ("timezone_id", "locale", "fingerprint")}})
        except Exception:
            out.append({"country": f.stem.upper(), "error": "invalid"})
    return out


def load_pack(country: str) -> dict[str, Any]:
    seed_packs()
    code = country.upper().strip()
    path = ENV_PACKS_DIR / f"{code}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    packs = _merged_default_packs()
    if code in packs:
        return packs[code]
    raise KeyError(f"no env pack for country={country}")


def detect_country_from_node_name(name: str) -> str | None:
    """Parse subscription node title → ISO country code."""
    if not name:
        return None
    for flag, cc in FLAG_TO_CC.items():
        if flag in name:
            return cc
    # regional indicator symbols decoded already as flag emoji above
    for pat, cc in KEYWORD_TO_CC:
        if pat.search(name):
            return cc
    return None


def binding_from_country(country: str, *, jitter: bool = True) -> EnvBinding:
    """Build EnvBinding from country pack.

    v3 anti-uniformity when jitter=True:
      - city pick + geo noise
      - accuracy noise
      - viewport from common resolutions
      - hardware_concurrency slight variance
      - languages order stable but Accept-Language quality noise via extra meta
    """
    from .fingerprints import load_fingerprint  # local import avoid cycle

    pack = load_pack(country)
    city = random.choice(pack["cities"]) if pack.get("cities") else {"lat": 0.0, "lon": 0.0}
    lat, lon = float(city["lat"]), float(city["lon"])
    accuracy = 50.0
    vw, vh = pack.get("viewport") or [1920, 1080]
    if jitter:
        lat += random.uniform(-0.04, 0.04)
        lon += random.uniform(-0.04, 0.04)
        accuracy = float(random.choice([20, 30, 40, 50, 65, 80, 100]))
        vw, vh = random.choice(
            [
                [1920, 1080],
                [1366, 768],
                [1536, 864],
                [1440, 900],
                [2560, 1440],
                [1280, 720],
                [1600, 900],
            ]
        )
    fp_id = pack.get("fingerprint") or "win11-chrome"
    try:
        fp = load_fingerprint(fp_id)
    except Exception:
        fp = FingerprintConfig(template_id=fp_id)
    if jitter:
        # slight HW variance (still realistic)
        base_hw = int(fp.hardware_concurrency or 8)
        fp.hardware_concurrency = max(2, base_hw + random.choice([-2, -1, 0, 0, 1, 2]))
        fp.device_memory = float(random.choice([4, 8, 8, 16, 16, 32]))
    languages = list(pack.get("languages") or [pack["locale"]])
    if jitter and len(languages) > 1 and random.random() < 0.3:
        # occasionally drop last fallback to vary Accept-Language
        languages = languages[:-1] or languages
    return EnvBinding(
        timezone_id=pack["timezone_id"],
        locale=pack["locale"],
        languages=languages,
        geolocation=GeoLocation(latitude=lat, longitude=lon, accuracy=accuracy),
        viewport_width=int(vw),
        viewport_height=int(vh),
        permissions=["geolocation"],
        user_agent=fp.user_agent,
        fingerprint=fp,
    )


def recommend_from_node(node_name: str, *, jitter: bool = True) -> dict[str, Any]:
    """v2: node title → country pack + EnvBinding."""
    cc = detect_country_from_node_name(node_name)
    if not cc:
        return {
            "ok": False,
            "node_name": node_name,
            "country": None,
            "message": "cannot detect country from node name",
        }
    try:
        env = binding_from_country(cc, jitter=jitter)
    except KeyError:
        return {
            "ok": False,
            "node_name": node_name,
            "country": cc,
            "message": f"no env pack for detected country={cc}",
        }
    return {
        "ok": True,
        "node_name": node_name,
        "country": cc,
        "env": env.model_dump(mode="json"),
        "pack": {k: load_pack(cc).get(k) for k in ("timezone_id", "locale", "languages", "fingerprint")},
    }


def detect_egress_country(
    proxy_url: str | None = None,
    *,
    timeout: float = 12.0,
    overall_timeout: float | None = None,
) -> dict[str, Any]:
    """Best-effort IP/country/city/timezone detect via multiple public APIs (through optional proxy).

    Prefer full-geo providers (city + timezone). Cloudflare trace is only a fast IP/country fallback,
    then we try to enrich city/timezone when missing.
    """
    import time
    import httpx

    budget = float(overall_timeout if overall_timeout is not None else timeout)
    t0 = time.monotonic()

    def _remaining() -> float:
        return max(0.0, budget - (time.monotonic() - t0))

    errors: list[str] = []

    def _client(verify: bool = True, req_timeout: float | None = None):
        to = min(float(timeout), float(req_timeout if req_timeout is not None else timeout), max(0.2, _remaining()))
        return httpx.Client(
            proxy=proxy_url,
            timeout=to,
            follow_redirects=True,
            verify=verify,
            headers={"User-Agent": "Mozilla/5.0 (MozillaManager/1.10.10)"},
        )

    def _norm(out: dict[str, Any]) -> dict[str, Any]:
        if not out:
            return out
        cc = out.get("country")
        if isinstance(cc, str) and len(cc) > 2 and cc.isalpha() is False:
            # keep as-is; callers use ISO mostly
            pass
        # normalize empty strings to None for city/tz
        for k in ("city", "timezone", "region"):
            if out.get(k) == "":
                out[k] = None
        return out

    def _from_ip_sb(client) -> dict[str, Any] | None:
        r = client.get("https://api.ip.sb/geoip")
        r.raise_for_status()
        data = r.json()
        return _norm({
            "ip": data.get("ip"),
            "country": data.get("country_code") or data.get("country"),
            "city": data.get("city"),
            "region": data.get("region") or data.get("region_code"),
            "timezone": data.get("timezone"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "raw": data,
            "provider": "ip.sb",
        })

    def _from_ipwho(client) -> dict[str, Any] | None:
        r = client.get("https://ipwho.is/")
        r.raise_for_status()
        data = r.json()
        if data.get("success") is False:
            raise RuntimeError(str(data.get("message") or "ipwho failed"))
        return _norm({
            "ip": data.get("ip"),
            "country": data.get("country_code") or data.get("country"),
            "city": data.get("city"),
            "region": data.get("region") or data.get("region_code"),
            "timezone": (data.get("timezone") or {}).get("id") if isinstance(data.get("timezone"), dict) else data.get("timezone"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "raw": data,
            "provider": "ipwho.is",
        })

    def _from_ip_api(client) -> dict[str, Any] | None:
        # free endpoint is HTTP only
        r = client.get(
            "http://ip-api.com/json/?fields=status,message,country,countryCode,regionName,city,lat,lon,timezone,query"
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "success":
            raise RuntimeError(str(data.get("message") or "ip-api failed"))
        return _norm({
            "ip": data.get("query"),
            "country": data.get("countryCode") or data.get("country"),
            "city": data.get("city"),
            "region": data.get("regionName"),
            "timezone": data.get("timezone"),
            "latitude": data.get("lat"),
            "longitude": data.get("lon"),
            "raw": data,
            "provider": "ip-api",
        })

    def _from_ipinfo(client) -> dict[str, Any] | None:
        r = client.get("https://ipinfo.io/json")
        r.raise_for_status()
        data = r.json()
        if data.get("error") or data.get("status") == 429:
            raise RuntimeError(str((data.get("error") or {}).get("message") or data.get("error") or "ipinfo error"))
        loc = (data.get("loc") or ",").split(",")
        return _norm({
            "ip": data.get("ip"),
            "country": data.get("country"),
            "city": data.get("city"),
            "region": data.get("region"),
            "timezone": data.get("timezone"),
            "latitude": float(loc[0]) if loc and loc[0] else None,
            "longitude": float(loc[1]) if len(loc) > 1 and loc[1] else None,
            "raw": data,
            "provider": "ipinfo",
        })

    def _from_ipapi_co(client) -> dict[str, Any] | None:
        r = client.get("https://ipapi.co/json/")
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(str(data.get("reason") or data.get("error")))
        return _norm({
            "ip": data.get("ip"),
            "country": data.get("country_code") or data.get("country"),
            "city": data.get("city"),
            "region": data.get("region"),
            "timezone": data.get("timezone"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "raw": data,
            "provider": "ipapi.co",
        })

    def _from_cf_trace(client) -> dict[str, Any] | None:
        tr = client.get("https://cloudflare.com/cdn-cgi/trace").text
        meta = dict(line.split("=", 1) for line in tr.splitlines() if "=" in line)
        if not meta.get("ip") and not meta.get("loc"):
            raise RuntimeError("empty cf trace")
        return _norm({
            "ip": meta.get("ip"),
            "country": meta.get("loc"),
            "city": None,
            "timezone": None,
            "latitude": None,
            "longitude": None,
            "raw": meta,
            "provider": "cloudflare-trace",
        })

    def _from_ipify_and_cf(client) -> dict[str, Any] | None:
        ip = client.get("https://api.ipify.org").text.strip()
        tr = client.get("https://1.1.1.1/cdn-cgi/trace").text
        meta = dict(line.split("=", 1) for line in tr.splitlines() if "=" in line)
        return _norm({
            "ip": ip or meta.get("ip"),
            "country": meta.get("loc"),
            "city": None,
            "timezone": None,
            "latitude": None,
            "longitude": None,
            "raw": {"ipify": ip, "cf": meta},
            "provider": "ipify+cf",
        })

    def _enrich(client, base: dict[str, Any]) -> dict[str, Any]:
        """Fill city/timezone/lat/lon when a fast provider only returned IP/country."""
        if base.get("city") and base.get("timezone"):
            return base
        ip = base.get("ip")
        enrichers = []
        if ip:
            enrichers.extend(
                [
                    (
                        "ip-api-ip",
                        f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,lat,lon,timezone,query",
                    ),
                    ("ipwho-ip", f"https://ipwho.is/{ip}"),
                    ("ip.sb-ip", f"https://api.ip.sb/geoip/{ip}"),
                ]
            )
        enrichers.extend(
            [
                ("ip-api", "http://ip-api.com/json/?fields=status,message,country,countryCode,regionName,city,lat,lon,timezone,query"),
                ("ipwho", "https://ipwho.is/"),
                ("ip.sb", "https://api.ip.sb/geoip"),
            ]
        )
        for name, url in enrichers:
            if _remaining() <= 0.25:
                break
            try:
                r = client.get(url)
                r.raise_for_status()
                data = r.json()
                city = tz = region = lat = lon = cc = None
                if "ip-api" in name:
                    if data.get("status") != "success":
                        raise RuntimeError(data.get("message") or "fail")
                    city, tz, region = data.get("city"), data.get("timezone"), data.get("regionName")
                    lat, lon = data.get("lat"), data.get("lon")
                    cc = data.get("countryCode") or data.get("country")
                    ip2 = data.get("query")
                elif "ipwho" in name:
                    if data.get("success") is False:
                        raise RuntimeError(data.get("message") or "fail")
                    city = data.get("city")
                    tz_obj = data.get("timezone")
                    tz = tz_obj.get("id") if isinstance(tz_obj, dict) else tz_obj
                    region = data.get("region") or data.get("region_code")
                    lat, lon = data.get("latitude"), data.get("longitude")
                    cc = data.get("country_code") or data.get("country")
                    ip2 = data.get("ip")
                else:  # ip.sb
                    city = data.get("city")
                    tz = data.get("timezone")
                    region = data.get("region")
                    lat, lon = data.get("latitude"), data.get("longitude")
                    cc = data.get("country_code") or data.get("country")
                    ip2 = data.get("ip")
                if city or tz:
                    base = dict(base)
                    base["city"] = base.get("city") or city
                    base["timezone"] = base.get("timezone") or tz
                    base["region"] = base.get("region") or region
                    base["latitude"] = base.get("latitude") if base.get("latitude") is not None else lat
                    base["longitude"] = base.get("longitude") if base.get("longitude") is not None else lon
                    base["country"] = base.get("country") or cc
                    if not base.get("ip") and ip2:
                        base["ip"] = ip2
                    base["enriched_by"] = name
                    base["raw_enrich"] = data
                    return _norm(base)
            except Exception as e:
                errors.append(f"enrich:{name}:{e}")
        return base

    # Full geo first, CF only as last-resort IP/country then enrich.
    full_providers = (_from_ip_sb, _from_ipwho, _from_ip_api, _from_ipinfo, _from_ipapi_co)
    thin_providers = (_from_cf_trace, _from_ipify_and_cf)

    for verify in (True, False):
        if _remaining() <= 0.15:
            break
        with _client(verify=verify) as client:
            for prov in full_providers:
                if _remaining() <= 0.15:
                    errors.append("overall_timeout")
                    break
                try:
                    out = prov(client)
                    if out and (out.get("ip") or out.get("country")):
                        if not (out.get("city") and out.get("timezone")):
                            out = _enrich(client, out)
                        if not verify:
                            out["tls_verify"] = False
                        out["elapsed_budget_left"] = round(_remaining(), 3)
                        return out
                except Exception as e:
                    errors.append(f"{prov.__name__}(verify={verify}): {e}")
            for prov in thin_providers:
                if _remaining() <= 0.15:
                    break
                try:
                    out = prov(client)
                    if out and (out.get("ip") or out.get("country")):
                        out = _enrich(client, out)
                        if not verify:
                            out["tls_verify"] = False
                        out["elapsed_budget_left"] = round(_remaining(), 3)
                        return out
                except Exception as e:
                    errors.append(f"{prov.__name__}(verify={verify}): {e}")
    raise RuntimeError("; ".join(errors[:12]) or "egress detect failed")


