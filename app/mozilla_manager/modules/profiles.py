"""Profiles module: browser environment CRUD + lifecycle."""
from __future__ import annotations

from typing import Any

from mozilla_manager.consistency import preflight_consistency
from mozilla_manager.env_packs import binding_from_country, recommend_from_node
from mozilla_manager import db
from mozilla_manager.engines import get_launcher
from mozilla_manager.fingerprints import load_fingerprint, seed_fingerprints
from mozilla_manager.launch_gate import preflight
from mozilla_manager.models import ChromiumPatch, EngineKind, EnvBinding, GeoLocation, ProxyConfig
from mozilla_manager.modules import mihomo_svc, sessions as sessions_mod
from mozilla_manager.network.browser_only import launch_proxy_policy
from mozilla_manager.network.mihomo import allocate_port
from mozilla_manager.runtime_registry import list_running
from mozilla_manager.snapshots import export_profile_zip, snapshot_profile
from mozilla_manager.store import ProfileStore



# ---- meta defaults / enrichment (v1–v10 contract) ----
_META_DEFAULTS = {
    "webrtc_mode": "disable",
    "doh_mode": "secure",
    "doh_template": "https://cloudflare-dns.com/dns-query",
    "doh_force": True,
    "doh_servers": [
        "https://cloudflare-dns.com/dns-query",
        "https://dns.google/dns-query",
        "https://dns.alidns.com/dns-query",
    ],
    "geo_match_strict": False,
    "stealth_v6": True,
    "auto_rebind_on_launch": True,
    "browser_only_hint": True,
}


def ensure_meta_defaults(meta: dict[str, Any] | None, *, persist: bool = False, profile_id: str | None = None) -> dict[str, Any]:
    """Fill missing privacy/rebind defaults for older profiles without wiping user values."""
    out = dict(meta or {})
    changed = False
    for k, v in _META_DEFAULTS.items():
        if k not in out:
            out[k] = v
            changed = True
    if "extensions" not in out:
        try:
            from mozilla_manager.modules.extensions import list_extensions
            ext_ids = [e["id"] for e in list_extensions()]
            if "mozilla-helper" in ext_ids:
                out["extensions"] = ["mozilla-helper"]
                changed = True
        except Exception:
            pass
    if persist and changed and profile_id:
        try:
            store = ProfileStore()
            store.update(profile_id, meta=out)
            db.upsert_profile_row(store.get(profile_id))
        except Exception:
            pass
    return out


def _enrich_profile_dict(d: dict[str, Any], *, persist_defaults: bool = False) -> dict[str, Any]:
    meta = ensure_meta_defaults(d.get("meta") or {}, persist=persist_defaults, profile_id=d.get("id"))
    d["meta"] = meta
    d["auto_rebind_on_launch"] = bool(meta.get("auto_rebind_on_launch", True))
    d["privacy"] = {
        "webrtc_mode": meta.get("webrtc_mode", "disable"),
        "doh_mode": meta.get("doh_mode", "secure"),
        "doh_template": meta.get("doh_template"),
        "doh_force": bool(meta.get("doh_force", True)),
    }
    d["last_launch_rebind"] = meta.get("last_launch_rebind")
    d["last_egress"] = meta.get("last_egress")
    d["need_relogin"] = bool(meta.get("need_relogin"))
    d["locked"] = bool(meta.get("locked"))
    # isolation contract surface
    d["isolation"] = {
        "user_data_dir": d.get("user_data_dir"),
        "persistent_context": True,
        "browser_only_proxy": bool((d.get("proxy") or {}).get("browser_only", True)),
        "independent_egress": bool(
            (d.get("proxy") or {}).get("mode") in ("mihomo", "socks5")
        ),
    }
    return d


def backfill_all_meta_defaults() -> dict[str, Any]:
    """One-shot: write missing privacy/rebind defaults into every profile.json."""
    store = ProfileStore()
    updated = []
    for p in store.list():
        before = dict(p.meta or {})
        after = ensure_meta_defaults(before)
        if after != before:
            store.update(p.id, meta=after)
            try:
                db.upsert_profile_row(store.get(p.id))
            except Exception:
                pass
            updated.append(p.id)
    return {"ok": True, "updated": updated, "count": len(updated)}


def list_profiles() -> list[dict[str, Any]]:
    running = list_running()
    out = []
    for p in ProfileStore().list():
        d = p.model_dump(mode="json")
        d["running"] = p.id in running
        d["run_info"] = running.get(p.id)
        out.append(_enrich_profile_dict(d, persist_defaults=False))
    return out


def get_profile(profile_id: str) -> dict[str, Any]:
    p = ProfileStore().get(profile_id)
    d = p.model_dump(mode="json")
    running = list_running()
    d["running"] = profile_id in running
    d["run_info"] = running.get(profile_id)
    d["proxy_policy"] = launch_proxy_policy(p)
    # persist missing defaults once so older profiles pick up v4–v10 contract
    d = _enrich_profile_dict(d, persist_defaults=True)
    return d


def create_profile(
    *,
    name: str,
    engine: str = "pw_chromium",
    patch: str = "patchright",
    socks5: str = "",
    mihomo_port: int = 0,
    sub: str = "default",
    country: str = "",
    timezone_id: str = "",
    locale: str = "",
    lat: float = 0.0,
    lon: float = 0.0,
    auto_port: bool = False,
    group: str = "",
    remark: str = "",
    tabs: list[str] | None = None,
    node_name: str = "",
    fingerprint_id: str = "",
    browser_only: bool = True,
    auto_cf: bool = False,
    cf_timeout: float = 45.0,
    **_extra: Any,
) -> dict[str, Any]:
    seed_fingerprints()
    store = ProfileStore()

    # v2: node_name → auto country env
    rec = None
    if node_name and not country:
        rec = recommend_from_node(node_name)
        if rec.get("ok"):
            country = rec["country"]

    if country:
        env = binding_from_country(country)
    else:
        env = EnvBinding(
            timezone_id=timezone_id or "UTC",
            locale=locale or "en-US",
            languages=[locale or "en-US", "en"],
            geolocation=GeoLocation(latitude=lat, longitude=lon) if lat or lon else None,
        )
    if timezone_id:
        env.timezone_id = timezone_id
    if locale:
        env.locale = locale
        env.languages = [locale, locale.split("-")[0], "en-US"]
    if lat or lon:
        env.geolocation = GeoLocation(latitude=lat, longitude=lon)
    if fingerprint_id:
        fp = load_fingerprint(fingerprint_id)
        env.fingerprint = fp
        env.user_agent = fp.user_agent

    proxy = ProxyConfig(mode="none", browser_only=browser_only)
    if socks5:
        proxy = ProxyConfig(mode="socks5", socks5=socks5, browser_only=browser_only)
    elif mihomo_port or auto_port or node_name:
        port = mihomo_port
        if auto_port and not port:
            # allocate after create needs id — temp 0 then update
            port = 0
        proxy = ProxyConfig(
            mode="mihomo",
            mihomo_port=port or None,
            node_name=node_name or None,  # never treat subscription name as node
            browser_only=browser_only,
        )

    prof = store.create(
        name=name,
        engine=EngineKind(engine),
        chromium_patch=ChromiumPatch(patch),
        proxy=proxy,
        env=env,
    )
    meta = dict(prof.meta)
    if group:
        meta["group"] = group
    if remark:
        meta["remark"] = remark
    if tabs:
        meta["tabs"] = tabs
    if country:
        meta["expected_country"] = country.upper()
    if sub:
        meta["sub"] = sub
    if node_name:
        meta["bound_node"] = node_name
    if rec:
        meta["node_recommend"] = {"country": rec.get("country"), "ok": rec.get("ok")}
    # v4 defaults
    meta.setdefault("webrtc_mode", "disable")
    meta.setdefault("doh_mode", "secure")
    meta.setdefault("doh_template", "https://cloudflare-dns.com/dns-query")
    meta.setdefault("doh_force", True)
    meta.setdefault("doh_servers", [
        "https://cloudflare-dns.com/dns-query",
        "https://dns.google/dns-query",
        "https://dns.alidns.com/dns-query",
    ])
    meta.setdefault("geo_match_strict", False)  # set True to hard-block launch on geo mismatch
    meta.setdefault("stealth_v6", True)
    meta.setdefault("auto_rebind_on_launch", True)
    # v5 CF / Turnstile — integrated in browser launch (engines read meta.auto_cf)
    meta["auto_cf"] = bool(auto_cf)
    meta["pass_cf"] = bool(auto_cf)
    meta["cf_timeout"] = float(cf_timeout or 45.0)
    meta["cf_engine"] = "turnstile-harvester1"
    try:
        from mozilla_manager.modules.extensions import list_extensions
        ext_ids = [e["id"] for e in list_extensions()]
        if "mozilla-helper" in ext_ids:
            ex = list(meta.get("extensions") or [])
            if "mozilla-helper" not in ex:
                ex.append("mozilla-helper")
            meta["extensions"] = ex
    except Exception:
        pass

    # auto allocate mihomo port now that we have id
    proxy_update = None
    if proxy.mode == "mihomo" and (auto_port or not proxy.mihomo_port):
        port = allocate_port(prof.id)
        proxy_update = ProxyConfig(
            mode="mihomo",
            mihomo_port=port,
            node_name=proxy.node_name,
            browser_only=browser_only,
        )

    patch_kwargs: dict[str, Any] = {"meta": meta}
    if proxy_update:
        patch_kwargs["proxy"] = proxy_update
    prof = store.update(prof.id, **patch_kwargs)
    # v6: materialize fixed stealth bundle at create
    try:
        from mozilla_manager.stealth import ensure_stealth_bundle, summarize_bundle
        b = ensure_stealth_bundle(prof)
        meta2 = dict(prof.meta)
        meta2["stealth_bundle_id"] = b.get("bundle_id")
        meta2["stealth_core_hash"] = b.get("core_hash")
        prof = store.update(prof.id, meta=meta2)
        dumped = prof.model_dump(mode="json")
        dumped["stealth"] = summarize_bundle(b)
        return dumped
    except Exception:
        return prof.model_dump(mode="json")


def update_profile(profile_id: str, **patch: Any) -> dict[str, Any]:
    store = ProfileStore()
    # normalize nested models if plain dicts
    if "proxy" in patch and isinstance(patch["proxy"], dict):
        patch["proxy"] = ProxyConfig.model_validate(patch["proxy"])
    if "env" in patch and isinstance(patch["env"], dict):
        patch["env"] = EnvBinding.model_validate(patch["env"])
    if "engine" in patch and isinstance(patch["engine"], str):
        patch["engine"] = EngineKind(patch["engine"])
    if "chromium_patch" in patch and isinstance(patch["chromium_patch"], str):
        patch["chromium_patch"] = ChromiumPatch(patch["chromium_patch"])
    return store.update(profile_id, **patch).model_dump(mode="json")


def delete_profile(profile_id: str, wipe: bool = True) -> None:
    from mozilla_manager.modules.lock_svc import require_unlocked
    require_unlocked(profile_id)
    # stop if running
    try:
        stop(profile_id)
    except Exception:
        pass
    ProfileStore().delete(profile_id, wipe_files=wipe)


def set_proxy(
    profile_id: str,
    *,
    mode: str,
    socks5: str = "",
    mihomo_port: int = 0,
    node: str = "",
    auto_port: bool = False,
    browser_only: bool = True,
    sub: str = "",
) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    port = mihomo_port
    if mode == "mihomo" and (auto_port or not port):
        port = allocate_port(profile_id)
    proxy = ProxyConfig(
        mode=mode,
        socks5=socks5 or None,
        mihomo_port=port or None,
        node_name=node or None,
        browser_only=browser_only,
    )
    meta = dict(prof.meta or {})
    if mode == "mihomo":
        if node:
            meta["bound_node"] = node
        if sub:
            meta["sub"] = sub
    elif mode == "socks5":
        meta.pop("bound_node", None)
    else:
        meta.pop("bound_node", None)
    return store.update(profile_id, proxy=proxy, meta=meta).model_dump(mode="json")


def bind_country(profile_id: str, country: str) -> dict[str, Any]:
    store = ProfileStore()
    env = binding_from_country(country)
    meta = dict(store.get(profile_id).meta)
    meta["expected_country"] = country.upper()
    return store.update(profile_id, env=env, meta=meta).model_dump(mode="json")


def launch(
    profile_id: str,
    *,
    headless: bool = False,
    open_check: bool = True,
    skip_preflight: bool = False,
    require_proxy: bool = False,
    start_mihomo: bool = False,
) -> dict[str, Any]:
    from mozilla_manager.modules.lock_svc import require_unlocked
    require_unlocked(profile_id)
    store = ProfileStore()
    prof = store.get(profile_id)

    if start_mihomo or prof.proxy.mode == "mihomo":
        port = prof.proxy.mihomo_port or allocate_port(profile_id)
        if not prof.proxy.mihomo_port:
            prof = store.update(
                profile_id,
                proxy=ProxyConfig(
                    mode="mihomo",
                    mihomo_port=port,
                    node_name=prof.proxy.node_name,
                    browser_only=prof.proxy.browser_only,
                ),
            )
        sub = (prof.meta or {}).get("sub") or "default"
        # v6: TLS persona client-fingerprint for mihomo outbounds
        cfp = None
        try:
            from mozilla_manager.stealth import ensure_stealth_bundle
            b = ensure_stealth_bundle(prof)
            cfp = (b.get("tls") or {}).get("mihomo_client_fingerprint") or "chrome"
        except Exception:
            cfp = (prof.meta or {}).get("tls_client_fingerprint") or "chrome"
        started = mihomo_svc.start(port, sub=sub, node=prof.proxy.node_name or "", client_fingerprint=cfp)
        # Warm mixed-port briefly so launch-time egress/rebind does not race a half-open listener.
        try:
            import socket, time as _t
            if (started or {}).get("ok", True):
                for _ in range(8):
                    s = socket.socket()
                    s.settimeout(0.25)
                    try:
                        s.connect(("127.0.0.1", int(port)))
                        s.close()
                        _t.sleep(0.15)  # allow outbound dialer init
                        break
                    except Exception:
                        try:
                            s.close()
                        except Exception:
                            pass
                        _t.sleep(0.2)
        except Exception:
            pass

    # v10.1: 每次 launch 按当前出口 IP 自动重绑 tz/locale/geo（可 meta.auto_rebind_on_launch=false 关闭）
    rebind_info = None
    try:
        from mozilla_manager.modules import health as health_mod
        prof = store.get(profile_id)  # refresh after possible mihomo port write
        if health_mod.auto_rebind_enabled(prof) and prof.proxy.mode in ("socks5", "mihomo"):
            rebind_info = health_mod.rebind_tz_locale_geo(
                profile_id,
                only_if_mismatch=False,
                full_pack_on_country_change=True,
                always_refresh_geo=True,
            )
            prof = store.get(profile_id)
        elif health_mod.auto_rebind_enabled(prof) and prof.proxy.mode == "none":
            rebind_info = {
                "ok": True,
                "rebound": False,
                "message": "auto_rebind skipped: proxy mode=none (no egress IP)",
            }
    except Exception as e:
        rebind_info = {"ok": False, "rebound": False, "error": str(e)}

    # v3: DB ↔ dir consistency before launch
    cons = preflight_consistency(profile_id, repair=True)
    if not cons.get("ok"):
        return {"ok": False, "profile_id": profile_id, "message": "consistency blocked", "consistency": cons}

    if not skip_preflight:
        report = preflight(prof, require_proxy=require_proxy)
        if not report.get("ok"):
            return {"ok": False, "profile_id": profile_id, "message": "launch gate blocked", "preflight": report, "consistency": cons}

    launcher = get_launcher(prof)
    # Camoufox/Playwright sync API needs a dedicated per-profile thread
    # (cannot share pool threads: loop stays alive after chromium launch).
    from mozilla_manager.engines.sync_bridge import call_in_profile_thread

    result = call_in_profile_thread(
        profile_id,
        lambda: launcher.launch(prof, headless=headless, open_check=open_check),
        timeout=300.0,
    )
    d = result.model_dump(mode="json")
    d["proxy_policy"] = launch_proxy_policy(prof)
    if rebind_info is not None:
        d["launch_rebind"] = {
            "ok": rebind_info.get("ok"),
            "rebound": rebind_info.get("rebound"),
            "message": rebind_info.get("message") or rebind_info.get("error"),
            "egress": rebind_info.get("egress"),
            "env": rebind_info.get("env"),
            "country_changed": rebind_info.get("country_changed"),
        }
    return d


def stop(profile_id: str) -> dict[str, Any]:
    store = ProfileStore()
    mihomo_stopped = None
    try:
        prof = store.get(profile_id)
        from mozilla_manager.engines.sync_bridge import call_in_profile_thread, drop_worker

        launcher = get_launcher(prof)
        try:
            call_in_profile_thread(profile_id, lambda: launcher.stop(profile_id), timeout=60.0)
        finally:
            drop_worker(profile_id)
        # Always tear down per-profile mihomo so ports/processes do not leak.
        try:
            port = getattr(prof.proxy, "mihomo_port", None)
            if port and getattr(prof.proxy, "mode", None) == "mihomo":
                mihomo_stopped = mihomo_svc.stop(int(port))
        except Exception as e:
            mihomo_stopped = {"ok": False, "error": str(e)}
    except KeyError:
        # still clear registry
        from mozilla_manager.runtime_registry import mark_stopped

        mark_stopped(profile_id)
    return {"ok": True, "id": profile_id, "stopped": True, "mihomo": mihomo_stopped}


def check(profile_id: str, require_proxy: bool = False) -> dict[str, Any]:
    prof = ProfileStore().get(profile_id)
    return preflight(prof, require_proxy=require_proxy)


def export_zip(profile_id: str) -> dict[str, Any]:
    path = export_profile_zip(profile_id)
    return {"ok": True, "path": str(path)}


def snapshot(profile_id: str, label: str = "") -> dict[str, Any]:
    path = snapshot_profile(profile_id, note=label)
    return {"ok": True, "path": str(path), "label": label}


def running() -> dict[str, Any]:
    return list_running()


# ---- v2 session wrappers ----
def session_backup(profile_id: str, label: str = "", include_user_data: bool = False) -> dict[str, Any]:
    return sessions_mod.backup_session(profile_id, label=label, include_user_data=include_user_data)


def session_restore(profile_id: str, ts: str, restore_user_data: bool = True) -> dict[str, Any]:
    return sessions_mod.restore_session(profile_id, ts, restore_user_data=restore_user_data)


def session_list(profile_id: str | None = None) -> list[dict[str, Any]]:
    return sessions_mod.list_sessions(profile_id)


def restore_last_session(*, headless: bool = False, open_check: bool = True) -> dict[str, Any]:
    """开机不必自启；手动调用以恢复上次仍标记为运行的会话。"""
    ids = db.list_last_running()
    results = []
    for pid in ids:
        try:
            results.append(launch(pid, headless=headless, open_check=open_check, skip_preflight=False))
        except Exception as e:
            results.append({"ok": False, "profile_id": pid, "message": str(e)})
    db.audit("restore_last_session", detail={"ids": ids, "count": len(results)})
    return {"ok": True, "requested": ids, "results": results}


def save_last_session_now() -> dict[str, Any]:
    ids = list(list_running().keys())
    db.save_last_session(ids)
    return {"ok": True, "ids": ids}


def engine_matrix() -> list[dict[str, Any]]:
    from mozilla_manager.engines.matrix import list_matrix
    return list_matrix()


def consistency_check(repair: bool = False) -> dict[str, Any]:
    from mozilla_manager.consistency import check_consistency
    return check_consistency(repair=repair)


def export_incremental(profile_id: str) -> dict[str, Any]:
    from mozilla_manager.snapshots import export_profile_zip_incremental
    path = export_profile_zip_incremental(profile_id)
    return {"ok": True, "path": str(path), "incremental": True}
