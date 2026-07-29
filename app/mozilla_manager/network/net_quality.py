"""v6 network quality: packet loss / stability / geo consistency (ROOT-locked)."""
from __future__ import annotations

import statistics
import time
from typing import Any

import httpx

from ..env_packs import DEFAULT_PACKS, detect_egress_country
from ..paths import LOG_DIR, ensure_layout, safe_resolve

# Common public echo endpoints for latency sampling (HTTPS only).
_PROBES = [
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://1.1.1.1/cdn-cgi/trace",
    "https://dns.google/",
]


def sample_latency(
    proxy_url: str | None = None,
    *,
    samples: int = 5,
    timeout: float = 4.0,
) -> dict[str, Any]:
    """Measure RTT samples through optional proxy; infer loss & stability."""
    ensure_layout()
    samples = max(3, min(int(samples), 20))
    rtts: list[float] = []
    errors = 0
    details = []
    with httpx.Client(timeout=timeout, follow_redirects=True, proxy=proxy_url, verify=True) as client:
        for i in range(samples):
            url = _PROBES[i % len(_PROBES)]
            t0 = time.perf_counter()
            try:
                r = client.get(url, headers={"User-Agent": "MozillaManagerNetQuality/1.0"})
                ms = (time.perf_counter() - t0) * 1000.0
                ok = r.status_code < 500
                if ok:
                    rtts.append(ms)
                else:
                    errors += 1
                details.append({"url": url, "ok": ok, "ms": round(ms, 1), "status": r.status_code})
            except Exception as e:
                errors += 1
                ms = (time.perf_counter() - t0) * 1000.0
                details.append({"url": url, "ok": False, "ms": round(ms, 1), "error": str(e)[:160]})
    total = samples
    loss_rate = errors / total if total else 1.0
    stability = "unknown"
    jitter = None
    avg = None
    p95 = None
    if rtts:
        avg = statistics.mean(rtts)
        jitter = statistics.pstdev(rtts) if len(rtts) > 1 else 0.0
        sr = sorted(rtts)
        p95 = sr[min(len(sr) - 1, int(len(sr) * 0.95))]
        # stability heuristic
        if loss_rate <= 0.05 and jitter is not None and jitter < 40 and avg < 400:
            stability = "good"
        elif loss_rate <= 0.2 and jitter is not None and jitter < 120:
            stability = "fair"
        else:
            stability = "poor"
    else:
        stability = "down"

    return {
        "ok": bool(rtts),
        "samples": samples,
        "success": len(rtts),
        "errors": errors,
        "loss_rate": round(loss_rate, 4),
        "loss_pct": round(loss_rate * 100.0, 2),
        "rtt_ms_avg": round(avg, 1) if avg is not None else None,
        "rtt_ms_p95": round(p95, 1) if p95 is not None else None,
        "jitter_ms": round(jitter, 1) if jitter is not None else None,
        "stability": stability,
        "proxy": proxy_url,
        "details": details,
    }


# locale prefix -> expected country set (soft)
_LOCALE_COUNTRY = {
    "ja": {"JP"},
    "zh-tw": {"TW"},
    "zh-hk": {"HK"},
    "zh": {"CN", "TW", "HK", "SG"},
    "ko": {"KR"},
    "de": {"DE", "AT", "CH"},
    "fr": {"FR", "BE", "CH", "CA"},
    "en-gb": {"GB"},
    "en-us": {"US"},
    "en-au": {"AU"},
    "en-ca": {"CA"},
    "en": {"US", "GB", "AU", "CA", "NZ", "IE", "SG"},
    "id": {"ID"},
    "th": {"TH"},
    "vi": {"VN"},
    "es": {"ES", "MX", "AR", "CO", "CL"},
    "pt-br": {"BR"},
    "pt": {"PT", "BR"},
    "ru": {"RU"},
    "tr": {"TR"},
    "ar": {"AE", "SA", "EG"},
}


def _locale_countries(locale: str) -> set[str]:
    loc = (locale or "").lower().replace("_", "-")
    if loc in _LOCALE_COUNTRY:
        return set(_LOCALE_COUNTRY[loc])
    prefix = loc.split("-")[0]
    if loc in _LOCALE_COUNTRY:
        return set(_LOCALE_COUNTRY[loc])
    # try full then prefix
    for k, v in _LOCALE_COUNTRY.items():
        if loc.startswith(k):
            return set(v)
    return set(_LOCALE_COUNTRY.get(prefix) or [])


def geo_consistency(
    *,
    egress: dict[str, Any] | None,
    timezone_id: str | None,
    locale: str | None,
    expected_country: str | None = None,
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """Check exit IP geo vs profile timezone/locale/expected_country."""
    egress = egress or {}
    ip_cc = (egress.get("country") or "").upper()
    ip_tz = egress.get("timezone") or ""
    issues: list[str] = []
    score = 100

    if expected_country:
        exp = str(expected_country).upper()
        if ip_cc and ip_cc != exp:
            issues.append(f"country mismatch: egress={ip_cc} expected={exp}")
            score -= 40
    elif ip_cc and timezone_id:
        # infer countries that commonly use this tz
        # reverse COUNTRY_TZ loosely
        tz_countries = {
            cc for cc, pack in DEFAULT_PACKS.items()
            if isinstance(pack, dict) and pack.get("timezone_id") == timezone_id
        }
        if tz_countries and ip_cc not in tz_countries:
            # soft: also accept if tz string equals
            if ip_tz and ip_tz != timezone_id:
                issues.append(f"tz/country weak mismatch: ip_cc={ip_cc} profile_tz={timezone_id} ip_tz={ip_tz}")
                score -= 25

    if timezone_id and ip_tz and str(ip_tz) != str(timezone_id):
        issues.append(f"timezone mismatch: egress={ip_tz} profile={timezone_id}")
        score -= 30

    loc_set = _locale_countries(locale or "")
    if languages:
        for lang in languages:
            loc_set |= _locale_countries(lang)
    if ip_cc and loc_set and ip_cc not in loc_set:
        issues.append(f"locale/country mismatch: egress={ip_cc} locale={locale} allow={sorted(loc_set)}")
        score -= 20

    score = max(0, score)
    ok = score >= 70 and not any("country mismatch" in x for x in issues)
    return {
        "ok": ok,
        "score": score,
        "issues": issues,
        "egress_country": ip_cc or None,
        "egress_timezone": ip_tz or None,
        "profile_timezone": timezone_id,
        "profile_locale": locale,
        "expected_country": (expected_country or "").upper() or None,
    }


def run_net_quality(
    proxy_url: str | None,
    *,
    timezone_id: str | None = None,
    locale: str | None = None,
    expected_country: str | None = None,
    languages: list[str] | None = None,
    samples: int = 5,
    probe_egress: bool = True,
) -> dict[str, Any]:
    """Combined quality report: latency/loss/stability + geo consistency."""
    lat = sample_latency(proxy_url, samples=samples)
    egress = None
    if probe_egress:
        try:
            egress = detect_egress_country(proxy_url, timeout=12.0) if proxy_url else detect_egress_country(None, timeout=8.0)
        except Exception as e:
            egress = {"error": str(e)}
    geo = geo_consistency(
        egress=egress if isinstance(egress, dict) else {},
        timezone_id=timezone_id,
        locale=locale,
        expected_country=expected_country,
        languages=languages,
    )
    report = {
        "ok": bool(lat.get("ok")) and bool(geo.get("ok")),
        "latency": lat,
        "geo": geo,
        "egress": {
            k: (egress or {}).get(k)
            for k in ("ip", "country", "city", "timezone", "latitude", "longitude", "error")
        }
        if egress
        else None,
        "proxy": proxy_url,
    }
    try:
        path = safe_resolve(LOG_DIR / "net_quality_last.json")
        import json

        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report
