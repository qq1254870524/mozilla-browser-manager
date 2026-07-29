"""v6 stealth service: bundle CRUD, entropy, net quality, launch hooks."""
from __future__ import annotations

from typing import Any

from mozilla_manager import db
from mozilla_manager.launch_gate import _proxy_url
from mozilla_manager.network.net_quality import run_net_quality
from mozilla_manager.stealth import (
    TLS_PROFILES,
    build_stealth_init_script,
    collision_stats,
    ensure_stealth_bundle,
    estimate_entropy_bits,
    load_stealth_bundle,
    summarize_bundle,
)
from mozilla_manager.stealth.bundle import build_stealth_bundle
from mozilla_manager.stealth.entropy import core_fingerprint_hash
from mozilla_manager.stealth.tls_ja import list_tls_profiles
from mozilla_manager.store import ProfileStore


def get_bundle(profile_id: str, *, ensure: bool = True) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    if ensure:
        b = ensure_stealth_bundle(prof)
    else:
        b = load_stealth_bundle(profile_id)
        if not b:
            return {"ok": False, "error": "no stealth bundle"}
    return {"ok": True, "summary": summarize_bundle(b), "bundle": b}


def regenerate(profile_id: str, *, tls_profile: str | None = None) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    b = build_stealth_bundle(prof, tls_profile_id=tls_profile, force_new_noise=True)
    # persist tls choice on meta
    if tls_profile:
        meta = dict(prof.meta)
        meta["tls_profile"] = tls_profile
        store.update(profile_id, meta=meta)
    db.audit("stealth_regenerate", profile_id, {"bundle_id": b.get("bundle_id"), "tls": (b.get("tls") or {}).get("id")})
    return {"ok": True, "summary": summarize_bundle(b)}


def set_tls(profile_id: str, tls_profile: str) -> dict[str, Any]:
    if tls_profile not in TLS_PROFILES:
        raise ValueError(f"unknown tls profile: {tls_profile}; choose from {list(TLS_PROFILES)}")
    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    meta["tls_profile"] = tls_profile
    store.update(profile_id, meta=meta)
    b = ensure_stealth_bundle(store.get(profile_id), tls_profile_id=tls_profile)
    db.audit("stealth_tls_set", profile_id, {"tls": tls_profile})
    return {"ok": True, "tls": b.get("tls"), "summary": summarize_bundle(b)}


def set_doh(
    profile_id: str,
    *,
    mode: str = "secure",
    template: str | None = None,
    servers: list[str] | None = None,
    force: bool = True,
) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    meta["doh_mode"] = mode
    meta["doh_force"] = force
    if template:
        meta["doh_template"] = template
    if servers is not None:
        meta["doh_servers"] = list(servers)
    store.update(profile_id, meta=meta)
    # refresh bundle doh section
    b = load_stealth_bundle(profile_id)
    if b:
        b["doh"] = {
            "mode": mode,
            "template": meta.get("doh_template") or "https://cloudflare-dns.com/dns-query",
            "servers": meta.get("doh_servers")
            or [
                "https://cloudflare-dns.com/dns-query",
                "https://dns.google/dns-query",
            ],
            "force": force,
        }
        from mozilla_manager.stealth.bundle import _write

        _write(profile_id, b)
    db.audit("stealth_doh_set", profile_id, {"mode": mode, "force": force, "template": template, "servers": servers})
    return {"ok": True, "doh": {"mode": mode, "template": meta.get("doh_template"), "servers": meta.get("doh_servers"), "force": force}}


def entropy_report(profile_id: str | None = None) -> dict[str, Any]:
    if profile_id:
        b = load_stealth_bundle(profile_id) or ensure_stealth_bundle(ProfileStore().get(profile_id))
        return {"ok": True, **estimate_entropy_bits(b), "core_hash": b.get("core_hash"), "dimension_count": b.get("dimension_count")}
    return {"ok": True, **estimate_entropy_bits(None)}


def collision_report(limit: int = 50) -> dict[str, Any]:
    store = ProfileStore()
    bundles = []
    for prof in store.list()[: max(2, limit)]:
        bundles.append(ensure_stealth_bundle(prof))
    # also synthesize extra virtual ids for statistical floor if few profiles
    if len(bundles) < 10:
        from mozilla_manager.models import Profile, EngineKind, EnvBinding
        from mozilla_manager.stealth.bundle import build_stealth_bundle

        for i in range(10 - len(bundles)):
            fake = Profile(
                id=f"synth-v6-{i:04d}",
                name=f"synth-{i}",
                engine=EngineKind.PLAYWRIGHT_CHROMIUM,
                user_data_dir=f"data/profiles/synth-v6-{i:04d}/user-data",
                env=EnvBinding(),
            )
            # build without writing? build writes — use temp under ROOT profiles is ok for synth? 
            # Avoid polluting: compute via build but we need no write — call dimensions only through ensure with force
            # Simpler: use seed-only synthetic hashes
            b = build_stealth_bundle(fake, force_new_noise=False)
            bundles.append(b)
    stats = collision_stats(bundles)
    # cleanup synth files
    try:
        from pathlib import Path
        from mozilla_manager.paths import ROOT
        import shutil

        for i in range(10):
            d = ROOT / "data" / "profiles" / f"synth-v6-{i:04d}"
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass
    return {"ok": True, **stats, "target_max_pct": 0.004}


def net_quality_for_profile(profile_id: str, *, samples: int = 5) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    proxy = _proxy_url(prof)
    report = run_net_quality(
        proxy,
        timezone_id=prof.env.timezone_id,
        locale=prof.env.locale,
        expected_country=(prof.meta or {}).get("expected_country"),
        languages=list(prof.env.languages or []),
        samples=samples,
    )
    db.audit("net_quality", profile_id, {"stability": (report.get("latency") or {}).get("stability"), "geo_ok": (report.get("geo") or {}).get("ok")})
    # persist on profile meta summary
    try:
        meta = dict(prof.meta)
        meta["last_net_quality"] = {
            "stability": (report.get("latency") or {}).get("stability"),
            "loss_pct": (report.get("latency") or {}).get("loss_pct"),
            "geo_ok": (report.get("geo") or {}).get("ok"),
            "geo_score": (report.get("geo") or {}).get("score"),
            "ip": (report.get("egress") or {}).get("ip"),
            "country": (report.get("egress") or {}).get("country"),
        }
        store.update(profile_id, meta=meta)
    except Exception:
        pass
    return report


def tls_profiles() -> list[dict[str, Any]]:
    return list_tls_profiles()


def init_script_for_profile(profile_id: str) -> str:
    store = ProfileStore()
    b = ensure_stealth_bundle(store.get(profile_id))
    return build_stealth_init_script(b)


def apply_stealth_to_context(context: Any, profile) -> dict[str, Any]:
    """Inject v6 stealth + return bundle summary."""
    b = ensure_stealth_bundle(profile)
    script = build_stealth_init_script(b)
    if script and context is not None:
        try:
            if hasattr(context, "add_init_script"):
                context.add_init_script(script)
        except Exception as e:
            return {"ok": False, "error": str(e), "summary": summarize_bundle(b)}
    return {"ok": True, "summary": summarize_bundle(b)}


_LIVE_PROBE_JS = r"""() => {
  const out = {};
  const safe = (fn, d=null) => { try { return fn(); } catch(e) { return d; } };
  out.webdriver = safe(() => navigator.webdriver);
  out.languages = safe(() => [...(navigator.languages || [])]);
  out.language = safe(() => navigator.language);
  out.platform = safe(() => navigator.platform);
  out.userAgent = safe(() => navigator.userAgent);
  out.hardwareConcurrency = safe(() => navigator.hardwareConcurrency);
  out.deviceMemory = safe(() => navigator.deviceMemory);
  out.maxTouchPoints = safe(() => navigator.maxTouchPoints);
  out.vendor = safe(() => navigator.vendor);
  out.plugins_len = safe(() => navigator.plugins?.length);
  out.mimeTypes_len = safe(() => navigator.mimeTypes?.length);
  out.has_chrome = safe(() => typeof window.chrome !== 'undefined');
  out.chrome_runtime = safe(() => typeof window.chrome !== 'undefined' && !!window.chrome.runtime);
  out.timezone = safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  out.timezoneOffset = safe(() => new Date().getTimezoneOffset());
  out.screen = safe(() => ({w: screen.width, h: screen.height, aw: screen.availWidth, ah: screen.availHeight, cd: screen.colorDepth, pr: window.devicePixelRatio}));
  out.inner = safe(() => ({w: window.innerWidth, h: window.innerHeight}));
  out.outer = safe(() => ({w: window.outerWidth, h: window.outerHeight}));
  out.webgl = safe(() => {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!gl) return null;
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    return {
      vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
      renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    };
  });
  out.canvas_hash = safe(() => {
    const c = document.createElement('canvas');
    c.width = 240; c.height = 60;
    const ctx = c.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillStyle = '#f60';
    ctx.fillRect(0,0,100,50);
    ctx.fillStyle = '#069';
    ctx.fillText('mm-stealth-probe', 2, 15);
    const data = c.toDataURL();
    let h = 0;
    for (let i = 0; i < data.length; i++) h = ((h<<5)-h) + data.charCodeAt(i) | 0;
    return {len: data.length, hash: h};
  });
  out.webrtc = safe(() => ({
    hasRTCPeerConnection: typeof RTCPeerConnection !== 'undefined',
    hasRTCDataChannel: typeof RTCDataChannel !== 'undefined',
  }));
  out.automation = {
    cdc: safe(() => Object.keys(window).filter(k => /cdc_|__playwright|__pw_|__selenium|__webdriver|callPhantom|_phantom|domAutomation/.test(k))),
    document_webdriver: safe(() => document.documentElement.getAttribute('webdriver')),
    navigator_webdriver_value: out.webdriver,
  };
  out.geo_permission_probe = safe(() => typeof navigator.geolocation !== 'undefined');
  out.userAgentData = safe(() => {
    const uad = navigator.userAgentData;
    if (!uad) return null;
    return {brands: uad.brands, mobile: uad.mobile, platform: uad.platform};
  });
  return out;
}"""


def live_probe(profile_id: str, *, fetch_egress: bool = True) -> dict[str, Any]:
    """Evaluate anti-detect signals inside a *running* profile browser context."""
    from mozilla_manager.engines.sync_bridge import call_in_profile_thread
    from mozilla_manager.engines import chromium as chromium_mod
    from mozilla_manager.engines import camoufox_engine as camoufox_mod
    from mozilla_manager.runtime_registry import list_running

    store = ProfileStore()
    prof = store.get(profile_id)
    if profile_id not in (list_running() or {}):
        return {"ok": False, "error": "profile not running", "profile_id": profile_id}

    def _do():
        run = getattr(chromium_mod, "_RUNS", {}).get(profile_id) or getattr(camoufox_mod, "_RUNS", {}).get(profile_id)
        if not run or not run.get("context"):
            raise RuntimeError("no live browser context in engine registry")
        ctx = run["context"]
        page = run.get("page")
        if page is None:
            pages = list(getattr(ctx, "pages", []) or [])
            page = pages[0] if pages else (ctx.new_page() if hasattr(ctx, "new_page") else None)
            run["page"] = page
        if page is None:
            raise RuntimeError("no page")
        try:
            page.goto("about:blank", wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        probe = page.evaluate(_LIVE_PROBE_JS)
        egress = None
        if fetch_egress:
            try:
                egress = page.evaluate(
                    """async () => {
                      try {
                        const r = await fetch('https://cloudflare.com/cdn-cgi/trace', {cache:'no-store'});
                        const t = await r.text();
                        const o = {};
                        t.trim().split('\\n').forEach(l => { const i=l.indexOf('='); if(i>0) o[l.slice(0,i)]=l.slice(i+1); });
                        return o;
                      } catch (e) { return {error: String(e)}; }
                    }"""
                )
            except Exception as e:
                egress = {"error": str(e)}
        return {"probe": probe, "egress": egress}

    raw = call_in_profile_thread(profile_id, _do, timeout=90.0)
    probe = raw.get("probe") or {}
    expected_tz = prof.env.timezone_id if prof.env else None
    expected_locale = prof.env.locale if prof.env else None
    checks = []

    def add(name: str, ok: bool, detail: Any = None, critical: bool = False):
        checks.append({"name": name, "ok": bool(ok), "critical": critical, "detail": detail})

    wd = probe.get("webdriver")
    add("webdriver_false", wd is False or wd is None, {"webdriver": wd}, True)
    cdc = (probe.get("automation") or {}).get("cdc") or []
    add("no_automation_globals", len(cdc) == 0, {"keys": cdc}, True)
    doc_wd = (probe.get("automation") or {}).get("document_webdriver")
    add("no_document_webdriver_attr", not doc_wd, {"attr": doc_wd}, True)
    got_tz = probe.get("timezone")
    add("timezone_match", (not expected_tz) or got_tz == expected_tz, {"expected": expected_tz, "got": got_tz}, True)
    got_lang = probe.get("language")
    langs = probe.get("languages") or []
    loc_ok = True
    if expected_locale:
        loc_ok = (
            got_lang == expected_locale
            or expected_locale in langs
            or (expected_locale.split("-")[0] == (got_lang or "").split("-")[0])
        )
    add("locale_match", loc_ok, {"expected": expected_locale, "language": got_lang, "languages": langs}, True)
    ua = probe.get("userAgent") or ""
    add("ua_present", len(ua) > 20, {"ua": ua[:140]}, True)
    add("ua_not_headless_token", "Headless" not in ua, {"ua": ua[:140]}, True)
    add("platform_set", bool(probe.get("platform")), {"platform": probe.get("platform")})
    webgl = probe.get("webgl") or {}
    add("webgl_present", bool(webgl.get("vendor") or webgl.get("renderer")), webgl)
    ch = probe.get("canvas_hash") or {}
    add("canvas_value", ch.get("hash") is not None, ch)
    hc = probe.get("hardwareConcurrency")
    add("hw_concurrency_sane", isinstance(hc, int) and 1 <= hc <= 128, {"hardwareConcurrency": hc})
    engine = str(getattr(prof.engine, "value", prof.engine))
    if engine in ("pw_chromium", "chromium"):
        add("has_window_chrome", probe.get("has_chrome") is True, {"has_chrome": probe.get("has_chrome")})
    egress = raw.get("egress") or {}
    exp_cc = (prof.meta or {}).get("expected_country")
    loc = (egress or {}).get("loc")
    if exp_cc and loc:
        add("egress_country_match", str(loc).upper() == str(exp_cc).upper(), {"expected": exp_cc, "loc": loc, "ip": egress.get("ip")}, True)
    elif fetch_egress:
        add("egress_fetched", bool(egress.get("ip")), egress)

    crit = [c for c in checks if c["critical"]]
    soft = [c for c in checks if not c["critical"]]
    ok = all(c["ok"] for c in crit)
    db.audit(
        "stealth_live_probe",
        profile_id,
        {"ok": ok, "critical_passed": sum(1 for c in crit if c["ok"]), "critical_total": len(crit)},
    )
    return {
        "ok": ok,
        "profile_id": profile_id,
        "engine": engine,
        "patch": str(getattr(prof.chromium_patch, "value", prof.chromium_patch)),
        "expected": {
            "timezone_id": expected_tz,
            "locale": expected_locale,
            "country": exp_cc,
            "ua": prof.env.user_agent if prof.env else None,
            "fingerprint": (prof.env.fingerprint.template_id if prof.env and prof.env.fingerprint else None),
        },
        "probe": probe,
        "egress": egress,
        "score": {
            "ok": ok,
            "critical_passed": sum(1 for c in crit if c["ok"]),
            "critical_total": len(crit),
            "soft_passed": sum(1 for c in soft if c["ok"]),
            "soft_total": len(soft),
            "checks": checks,
            "failed": [c["name"] for c in checks if not c["ok"]],
        },
    }
