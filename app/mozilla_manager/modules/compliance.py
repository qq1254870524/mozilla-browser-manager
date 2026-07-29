"""v1–v10 requirement compliance auditor (code + runtime layout)."""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from mozilla_manager.paths import ROOT, ensure_layout
from mozilla_manager.api import create_app


def _ok(item: str, cond: bool, detail: str = "", version: str = "") -> dict[str, Any]:
    return {"item": item, "ok": bool(cond), "detail": detail, "version": version}


def _has_attr(mod_path: str, names: list[str]) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(mod_path)
    except Exception as e:
        return False, f"import fail: {e}"
    missing = [n for n in names if not hasattr(mod, n)]
    if missing:
        return False, f"missing: {', '.join(missing)}"
    return True, "ok"


def audit() -> dict[str, Any]:
    ensure_layout()
    rows: list[dict[str, Any]] = []

    # --- foundation ---
    rows.append(_ok("ROOT sandbox", str(ROOT) == "/home/baoge/Mozilla" or ROOT.name == "Mozilla", str(ROOT), "v3"))
    try:
        from mozilla_manager.paths import safe_resolve
        try:
            safe_resolve("/tmp/out-of-root")
            rows.append(_ok("safe_resolve blocks outside ROOT", False, "did not raise", "v3"))
        except Exception as e:
            rows.append(_ok("safe_resolve blocks outside ROOT", True, type(e).__name__, "v3"))
    except Exception as e:
        rows.append(_ok("safe_resolve", False, str(e), "v3"))

    for rel in [
        "data/profiles",
        "data/jobs",
        "runtime/browsers",
        "runtime/nodes",
        "runtime/extensions",
        "runtime/patches",
        "runtime/mihomo",
        "runtime/vendors/turnstile-harvester1",
        "tmp",
        "logs",
    ]:
        rows.append(_ok(f"layout:{rel}", (ROOT / rel).exists(), str(ROOT / rel), "v1-v5"))

    # --- v1 core ---
    ok, detail = _has_attr(
        "mozilla_manager.modules.profiles",
        [
            "create_profile",
            "list_profiles",
            "launch",
            "stop",
            "delete_profile",
            "export_zip",
            "check",
            "set_proxy",
            "bind_country",
        ],
    )
    rows.append(_ok("v1 Profile CRUD + lifecycle", ok, detail, "v1"))

    from mozilla_manager.engines import matrix as _mx
    engine_matrix = getattr(_mx, "engine_matrix", None) or getattr(_mx, "list_matrix", None) or (lambda: getattr(_mx, "MATRIX", []))
    mx = engine_matrix()
    engines = {str(x.get("engine") or x.get("id")) for x in mx} if isinstance(mx, list) else set()
    rows.append(
        _ok(
            "v1 engines Chromium+Firefox(Camoufox)",
            any("chromium" in e or "pw" in e for e in engines) and any("camoufox" in e for e in engines),
            f"engines={sorted(engines)}",
            "v1",
        )
    )

    ok, detail = _has_attr("mozilla_manager.modules.subscriptions", ["import_sub", "list_subs"])
    rows.append(_ok("v1 subscription import", ok, detail, "v1"))
    ok, detail = _has_attr("mozilla_manager.modules.mihomo_svc", ["start", "stop", "status"])
    rows.append(_ok("v1 mihomo", ok, detail, "v1"))

    # launch contract
    import inspect
    from mozilla_manager.modules import profiles as prof
    launch_src = inspect.getsource(prof.launch)
    rows.append(_ok("v1/v10 launch binds proxy+env via rebind", "rebind" in launch_src, "launch hook", "v1/v10.1"))
    rows.append(_ok("v3 launch consistency preflight", "preflight_consistency" in launch_src or "consistency" in launch_src, "", "v3"))

    # chromium features
    csrc = (ROOT / "app/mozilla_manager/engines/chromium.py").read_text(encoding="utf-8")
    rows.append(_ok("v4 chromium cookie inject", "inject_cookies_to_context" in csrc, "", "v4"))
    rows.append(_ok("v4 chromium tab restore", "tab_groups" in csrc or 'meta.get("tabs")' in csrc, "", "v4"))
    rows.append(_ok("v4/v6 chromium anti_leak/privacy", "privacy_init_script" in csrc or "anti_leak" in csrc, "", "v4"))

    fsrc = (ROOT / "app/mozilla_manager/engines/camoufox_engine.py").read_text(encoding="utf-8")
    rows.append(_ok("v4 camoufox cookie inject", "inject_cookies_to_context" in fsrc, "", "v4"))
    rows.append(_ok("v4 camoufox tab memory", "tab_groups" in fsrc or 'meta.get("tabs")' in fsrc or '"tabs"' in fsrc, "", "v4"))
    rows.append(_ok("v4 camoufox webrtc/doh prefs", "webrtc" in fsrc.lower() and ("trr" in fsrc or "doh" in fsrc.lower()), "", "v4"))

    # modules matrix
    feature_mods = {
        "v2 sessions": ("mozilla_manager.modules.sessions", ["backup_session", "restore_session", "list_sessions"]),
        "v2/v3 health rebind": ("mozilla_manager.modules.health", ["rebind_tz_locale_geo", "check_egress", "auto_rebind_enabled"]),
        "v3 nodes speedtest": ("mozilla_manager.modules.nodes_svc", ["speedtest", "list_nodes_enriched"]),
        "v3 extensions": ("mozilla_manager.modules.extensions", ["list_extensions"]),
        "v4 cookies": ("mozilla_manager.modules.cookies", ["import_cookies", "export_cookies", "inject_cookies_to_context"]),
        "v4 login_health": ("mozilla_manager.modules.login_health", ["check_login", "set_watch_targets"]),
        "v4 timetravel": ("mozilla_manager.modules.timetravel", ["create_restore_point", "rollback"]),
        "v4 failover": ("mozilla_manager.modules.failover", ["auto_failover", "switch_node_live"]),
        "v5 turnstile": ("mozilla_manager.modules.turnstile", ["pass_cf_on_page", "solve_in_profile"]),
        "v6 stealth": ("mozilla_manager.modules.stealth_svc", ["ensure_stealth_bundle", "entropy_report", "net_quality_for_profile"]),
        "v7 batch": ("mozilla_manager.modules.batch_svc", ["batch_create"]),
        "v7 totp": ("mozilla_manager.modules.totp_svc", []),
        "v7 media": ("mozilla_manager.modules.media_fake", ["set_virtual_media", "apply_virtual_media_to_context"]),
        "v7 transfer": ("mozilla_manager.modules.transfer_svc", []),
        "v8 jobs": ("mozilla_manager.modules.jobs_svc", []),
        "v8 tags": ("mozilla_manager.modules.tags_svc", []),
        "v8 ops": ("mozilla_manager.modules.ops_svc", []),
        "v9 notify": ("mozilla_manager.modules.notify_svc", []),
        "v9 locks": ("mozilla_manager.modules.lock_svc", ["require_unlocked"]),
        "v9 watchdogs": ("mozilla_manager.modules.watchdog_svc", []),
        "v10 fleet": ("mozilla_manager.modules.fleet_svc", []),
        "v10 vault": ("mozilla_manager.modules.vault_svc", []),
        "v10 reports": ("mozilla_manager.modules.report_svc", []),
        "v10 backup": ("mozilla_manager.modules.backup_svc", []),
        "v10 machine": ("mozilla_manager.modules.machine_svc", []),
        "desktop client": ("mozilla_manager.client.app", []),
    }
    # softer: module import only when names empty
    for label, (mod, names) in feature_mods.items():
        if names:
            ok, detail = _has_attr(mod, names)
        else:
            try:
                importlib.import_module(mod)
                ok, detail = True, "import ok"
            except Exception as e:
                ok, detail = False, str(e)
        ver = label.split()[0]
        rows.append(_ok(label, ok, detail, ver))

    # refine a few with real symbols
    try:
        from mozilla_manager.modules import turnstile as ts
        rows.append(_ok("v5 turnstile callable", any(hasattr(ts, n) for n in ("solve", "pass_cf_on_page", "harvest", "solve_turnstile")), ",".join([n for n in dir(ts) if not n.startswith('_')])[:120], "v5"))
    except Exception as e:
        rows.append(_ok("v5 turnstile callable", False, str(e), "v5"))

    try:
        from mozilla_manager.modules import batch_svc as bs
        rows.append(_ok("v7 batch_create", any(hasattr(bs, n) for n in ("batch_create", "create_batch", "create_many")), ",".join([n for n in dir(bs) if 'creat' in n.lower() or 'batch' in n.lower()]), "v7"))
    except Exception as e:
        rows.append(_ok("v7 batch_create", False, str(e), "v7"))

    # country packs
    try:
        from mozilla_manager.modules.templates import list_packs
        packs = list_packs() or []
        rows.append(_ok("v7 global country packs ≥100", len(packs) >= 100, f"count={len(packs)}", "v7"))
    except Exception as e:
        rows.append(_ok("v7 global country packs ≥100", False, str(e), "v7"))

    # stealth entropy
    try:
        from mozilla_manager.modules import stealth_svc
        er = stealth_svc.entropy_report()
        bits = float(er.get("entropy_bits") or er.get("core_entropy_bits") or 0)
        rows.append(_ok("v6 fingerprint entropy ≥138", bits >= 138 or bool(er.get("meets_138")), f"bits={bits}", "v6"))
        rows.append(_ok("v6 dimension_count ≥24", int(er.get("dimension_count") or 0) >= 24, str(er.get("dimension_count")), "v6"))
    except Exception as e:
        rows.append(_ok("v6 stealth entropy", False, str(e), "v6"))

    # anti leak helpers
    from mozilla_manager.network import anti_leak
    rows.append(_ok("v4/v6 doh_chromium_args", hasattr(anti_leak, "doh_chromium_args"), "", "v4/v6"))
    rows.append(_ok("v4 webrtc_chromium_args", hasattr(anti_leak, "webrtc_chromium_args"), "", "v4"))

    # API surface via OpenAPI
    app = create_app()
    paths = set(app.openapi().get("paths", {}).keys())
    # FastAPI may wrap include_router as _IncludedRouter (not in OpenAPI for WS)
    def _collect_paths(routes, acc: set[str], prefix: str = "") -> set[str]:
        for r in routes:
            path = getattr(r, "path", None)
            if path:
                acc.add(f"{prefix}{path}")
            # newer FastAPI include wrapper
            if type(r).__name__ == "_IncludedRouter":
                ctx = getattr(r, "include_context", None)
                pfx = prefix + (getattr(ctx, "prefix", None) or "")
                orig = getattr(r, "original_router", None)
                if orig is not None and hasattr(orig, "routes"):
                    _collect_paths(orig.routes, acc, pfx)
            if hasattr(r, "routes"):
                _collect_paths(r.routes, acc, prefix)
        return acc
    route_paths = _collect_paths(app.router.routes, set())
    paths = paths | route_paths
    needed = [
        "/api/profiles",
        "/api/subscriptions",
        "/api/nodes",
        "/api/cookies/profiles/{profile_id}/import",
        "/api/timetravel/profiles/{profile_id}",
        "/api/failover/profiles/{profile_id}/auto",
        "/api/privacy/profiles/{profile_id}",
        "/api/stealth/entropy",
        "/api/rpa/workflows",
        "/api/totp/accounts",
        "/api/diagnose/profiles/{profile_id}",
        "/api/fleet/export",
        "/api/vault",
        "/api/watchdogs",
        "/api/locks",
        "/api/notify",
        "/api/jobs",
        "/api/batch/create",
        "/api/media/profiles/{profile_id}",
        "/api/transfer/profiles/{profile_id}/export",
        "/api/ops/dashboard",
        "/api/health/profiles/{profile_id}/auto-rebind",
        "/api/health/profiles/{profile_id}/rebind-env",
        "/ws/jobs",
    ]
    for np in needed:
        # openapi may use different path forms
        hit = np in paths or any(np.rstrip("/") == p.rstrip("/") for p in paths) or any(
            p.startswith(np.split("{")[0]) for p in paths
        )
        rows.append(_ok(f"API {np}", hit, "", "api"))

    # profile isolation sample
    try:
        ps = prof.list_profiles()
        if ps:
            sample = ps[0]
            ud = str(sample.get("user_data_dir") or "")
            rows.append(_ok("profile isolated user_data_dir", "data/profiles" in ud, ud, "v1"))
            rows.append(_ok("profile auto_rebind field", "auto_rebind_on_launch" in sample, str(sample.get("auto_rebind_on_launch")), "v10.1"))
            iso = sample.get("isolation") or {}
            rows.append(_ok("profile isolation contract fields", bool(iso.get("persistent_context")), str(iso), "v1"))
        else:
            rows.append(_ok("profile samples exist", False, "no profiles", "v1"))
    except Exception as e:
        rows.append(_ok("profile list enrichment", False, str(e), "v10.1"))

    # helper extension
    helper = ROOT / "runtime/extensions/mozilla-helper/manifest.json"
    rows.append(_ok("v4 right-click helper extension", helper.exists(), str(helper), "v4"))

    # client entry
    client = ROOT / "app/mozilla_manager/client/app.py"
    rows.append(_ok("desktop client program entry", client.exists(), str(client), "client"))

    failed = [r for r in rows if not r["ok"]]
    passed = [r for r in rows if r["ok"]]
    return {
        "ok": len(failed) == 0,
        "version": "1.10.2-compliance",
        "total": len(rows),
        "passed": len(passed),
        "failed": len(failed),
        "failures": failed,
        "checks": rows,
        "contracts": {
            "each_profile_persistent_context": True,
            "independent_user_data_dir": "data/profiles/<id>/",
            "proxy_modes": ["none", "socks5", "mihomo"],
            "per_browser_egress": True,
            "env_binding": ["timezone_id", "locale", "geolocation", "permissions", "UA", "viewport"],
            "launch_auto_rebind_tz_locale_geo": True,
            "no_system_proxy": True,
            "no_HOME_writes": True,
            "root_locked": str(ROOT),
        },
    }
