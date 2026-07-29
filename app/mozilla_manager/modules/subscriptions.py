"""Subscriptions module: import/list/refresh/switch/export + runtime/nodes store."""
from __future__ import annotations

from typing import Any

from mozilla_manager import db
from mozilla_manager.network import node_store
from mozilla_manager.network.subscription import (
    import_subscription,
    list_nodes,
    list_nodes_raw,
    list_subscriptions,
    refresh_due_subscriptions,
    refresh_subscription,
)
from mozilla_manager.store import ProfileStore


def import_sub(
    url: str,
    name: str = "default",
    *,
    proxy_url: str | None = None,
    via_node: str | None = None,
    via_sub: str = "default",
) -> dict[str, Any]:
    """Import subscription. Optionally download through proxy or a known mihomo node."""
    tmp_port = None
    effective_proxy = proxy_url
    if via_node and not effective_proxy:
        from mozilla_manager.network.mihomo import start_mihomo, stop_mihomo, allocate_port
        import time as _t
        tmp_port = allocate_port(f"subimport-{name}", base=17600)
        start_mihomo(tmp_port, subscription_name=via_sub or "default", node_name=via_node)
        effective_proxy = f"http://127.0.0.1:{tmp_port}"
        _t.sleep(1.2)
    try:
        meta = import_subscription(url, name=name, proxy_url=effective_proxy)
    finally:
        if tmp_port is not None:
            try:
                from mozilla_manager.network.mihomo import stop_mihomo
                stop_mihomo(tmp_port)
            except Exception:
                pass
    try:
        node_store.set_active(name)
        meta["active"] = node_store.get_active()
    except Exception:
        pass
    if effective_proxy:
        meta["downloaded_via_proxy"] = effective_proxy
    if via_node:
        meta["downloaded_via_node"] = via_node
    return meta


def list_subs() -> list[dict[str, Any]]:
    try:
        node_store.migrate_legacy_to_runtime()
    except Exception:
        pass
    return list_subscriptions()


def list_sub_nodes(sub: str = "default") -> list[dict[str, Any]]:
    return list_nodes(sub or node_store.get_active())


def list_sub_nodes_full(sub: str = "default") -> list[dict[str, Any]]:
    return list_nodes_raw(sub or node_store.get_active())


def refresh_sub(name: str = "default") -> dict[str, Any]:
    return refresh_subscription(name)


def refresh_due(force: bool = False) -> list[dict[str, Any]]:
    return refresh_due_subscriptions(force=force)


def get_active() -> dict[str, Any]:
    name = node_store.get_active()
    meta = node_store.load_sub_meta(name) or {"name": name}
    return {"ok": True, "active": name, "meta": meta}


def switch_sub(name: str, *, update_profiles: bool = False) -> dict[str, Any]:
    """切换当前订阅（节点库 active）."""
    res = node_store.set_active(name)
    updated = []
    if update_profiles:
        store = ProfileStore()
        for prof in store.list():
            meta = dict(prof.meta)
            if meta.get("sub") == name:
                continue
            # only update profiles that track "use active" or empty? 
            # user asked 可以切换订阅 — update those with flag or all mihomo
            if prof.proxy.mode == "mihomo" and (meta.get("follow_active_sub") or meta.get("sub") in (None, "", "default")):
                meta["sub"] = name
                store.update(prof.id, meta=meta)
                updated.append(prof.id)
    db.audit("sub_switch", detail={"active": name, "profiles": updated})
    res["updated_profiles"] = updated
    return res


def export_sub(name: str | None = None, fmt: str = "zip") -> dict[str, Any]:
    return node_store.export_subscription(name, fmt=fmt)


def import_nodes_file(path: str, name: str = "imported") -> dict[str, Any]:
    meta = node_store.import_nodes_file(path, name=name)
    node_store.set_active(name)
    db.audit("sub_import_file", detail={"name": name, "path": path})
    return meta


def runtime_status() -> dict[str, Any]:
    return {
        "active": node_store.get_active(),
        "subs": node_store.list_sub_names(),
        "root": "runtime/nodes",
        "detail": node_store.list_subscriptions_detail(),
    }


def delete_sub(name: str) -> dict[str, Any]:
    """Delete subscription from node library."""
    res = node_store.delete_subscription(name)
    try:
        db.audit("sub_delete", detail={"name": name, "active": res.get("active")})
    except Exception:
        pass
    return res
