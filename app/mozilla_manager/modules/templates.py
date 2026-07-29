"""v2 templates module: country packs + fingerprint list + node recommend/bind."""
from __future__ import annotations

from typing import Any

from mozilla_manager.env_packs import (
    binding_from_country,
    detect_country_from_node_name,
    list_packs,
    recommend_from_node,
    seed_packs,
)
from mozilla_manager.fingerprints import list_fingerprints, load_fingerprint, seed_fingerprints
from mozilla_manager.models import ProxyConfig
from mozilla_manager.network.mihomo import allocate_port
from mozilla_manager.store import ProfileStore


def packs() -> list[dict[str, Any]]:
    seed_packs()
    return list_packs()


def fingerprints() -> list[dict[str, Any]]:
    seed_fingerprints()
    return list_fingerprints()


def recommend_node(node_name: str, *, jitter: bool = True) -> dict[str, Any]:
    return recommend_from_node(node_name, jitter=jitter)


def bind_node_to_profile(
    profile_id: str,
    *,
    node_name: str,
    sub: str = "default",
    mihomo_port: int = 0,
    auto_port: bool = True,
    apply_env: bool = True,
    fingerprint_id: str = "",
    jitter: bool = True,
) -> dict[str, Any]:
    """Bind subscription node → proxy + auto country env + fingerprint."""
    store = ProfileStore()
    prof = store.get(profile_id)
    rec = recommend_from_node(node_name, jitter=jitter)
    cc = rec.get("country")

    port = mihomo_port
    if auto_port and not port:
        port = allocate_port(profile_id)
    proxy = ProxyConfig(
        mode="mihomo",
        mihomo_port=port or prof.proxy.mihomo_port,
        node_name=node_name,
        browser_only=True,
    )
    # keep sub name in meta; node_name is the selected proxy node title
    meta = dict(prof.meta)
    meta["sub"] = sub
    meta["bound_node"] = node_name
    if cc:
        meta["expected_country"] = cc

    patch: dict[str, Any] = {"proxy": proxy, "meta": meta}
    if apply_env and rec.get("ok"):
        from mozilla_manager.models import EnvBinding

        env = EnvBinding.model_validate(rec["env"])
        if fingerprint_id:
            fp = load_fingerprint(fingerprint_id)
            env.fingerprint = fp
            env.user_agent = fp.user_agent
        patch["env"] = env
    elif fingerprint_id:
        env = prof.env.model_copy(deep=True)
        fp = load_fingerprint(fingerprint_id)
        env.fingerprint = fp
        env.user_agent = fp.user_agent
        patch["env"] = env

    updated = store.update(profile_id, **patch)
    return {
        "ok": True,
        "profile": updated.model_dump(mode="json"),
        "recommend": rec,
        "proxy_port": proxy.mihomo_port,
    }


def set_fingerprint(profile_id: str, template_id: str) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    fp = load_fingerprint(template_id)
    env = prof.env.model_copy(deep=True)
    env.fingerprint = fp
    env.user_agent = fp.user_agent
    updated = store.update(profile_id, env=env)
    return updated.model_dump(mode="json")


def detect_node_country(node_name: str) -> dict[str, Any]:
    cc = detect_country_from_node_name(node_name)
    return {"node_name": node_name, "country": cc, "ok": cc is not None}
