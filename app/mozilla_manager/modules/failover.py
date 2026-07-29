"""v4 节点故障自动切换：同国候补池，不重启浏览器，立即重绑环境包."""
from __future__ import annotations

from typing import Any

from mozilla_manager import db
from mozilla_manager.env_packs import binding_from_country, detect_country_from_node_name
from mozilla_manager.modules.health import check_egress
from mozilla_manager.modules.nodes_svc import list_nodes_enriched
from mozilla_manager.network.mihomo_api import switch_proxy
from mozilla_manager.store import ProfileStore


def candidate_nodes(profile_id: str, *, sub: str | None = None, country: str | None = None) -> list[dict[str, Any]]:
    store = ProfileStore()
    prof = store.get(profile_id)
    sub_name = sub or (prof.meta or {}).get("sub") or "default"
    cc = (country or (prof.meta or {}).get("expected_country") or "").upper()
    current = prof.proxy.node_name
    nodes = list_nodes_enriched(sub_name)
    # filter same country, exclude current, prefer latency ok
    out = []
    for n in nodes:
        name = n.get("name") or ""
        if not name or name == current:
            continue
        ncc = (n.get("country") or detect_country_from_node_name(name) or "").upper()
        if cc and ncc and ncc != cc:
            continue
        # skip traffic placeholders
        if "剩余" in name or "流量" in name or "过期" in name:
            continue
        srv = str(n.get("server") or "")
        if srv.startswith("127.") or srv in ("0.0.0.0", "localhost"):
            continue
        out.append(n)
    out.sort(
        key=lambda x: (
            0 if x.get("latency_ok") else 1,
            x.get("latency_ms") if x.get("latency_ms") is not None else 10**9,
        )
    )
    return out


def switch_node_live(
    profile_id: str,
    node_name: str,
    *,
    rebind_env: bool = True,
    sub: str | None = None,
) -> dict[str, Any]:
    """切换 mihomo 选中节点（浏览器不重启）+ 可选重绑环境包."""
    store = ProfileStore()
    prof = store.get(profile_id)
    if prof.proxy.mode != "mihomo" or not prof.proxy.mihomo_port:
        return {"ok": False, "message": "profile not on mihomo mode with port"}
    sw = switch_proxy(int(prof.proxy.mihomo_port), node_name)
    if not sw.get("ok"):
        return {"ok": False, "switch": sw, "message": "mihomo switch failed"}

    meta = dict(prof.meta)
    meta["bound_node"] = node_name
    cc = detect_country_from_node_name(node_name)
    patch: dict[str, Any] = {
        "proxy": prof.proxy.model_copy(update={"node_name": node_name}),
        "meta": meta,
    }
    if cc:
        meta["expected_country"] = cc
        if rebind_env:
            patch["env"] = binding_from_country(cc, jitter=True)
    patch["meta"] = meta
    updated = store.update(profile_id, **patch)
    db.upsert_profile_row(updated)
    db.audit("node_switch_live", profile_id, {"node": node_name, "country": cc, "rebind": rebind_env})
    return {"ok": True, "profile": updated.model_dump(mode="json"), "switch": sw, "country": cc}


def auto_failover(
    profile_id: str,
    *,
    check_ip: bool = True,
    rebind_env: bool = True,
) -> dict[str, Any]:
    """检测当前节点不通或 IP 归属突变 → 同国候补切换（不重启浏览器）."""
    store = ProfileStore()
    prof = store.get(profile_id)
    expected = (prof.meta or {}).get("expected_country")
    current = prof.proxy.node_name
    reason = None
    egress = None

    if check_ip and prof.proxy.mode == "mihomo" and prof.proxy.mihomo_port:
        egress = check_egress(profile_id)
        if not egress.get("ok"):
            reason = f"egress_failed: {egress.get('error')}"
        else:
            cc = ((egress.get("egress") or {}).get("country") or "").upper()
            if expected and cc and cc != str(expected).upper():
                reason = f"country_mismatch: {cc} != {expected}"
            # soft: also treat missing ip as fail
            if not (egress.get("egress") or {}).get("ip"):
                reason = reason or "no_ip"
    else:
        # without check, still allow forced pool rotate by caller
        reason = "manual_or_skip_check"

    if check_ip and reason is None:
        return {
            "ok": True,
            "failover": False,
            "message": "current node healthy",
            "egress": egress,
            "current": current,
        }

    cands = candidate_nodes(profile_id, country=expected)
    if not cands:
        return {
            "ok": False,
            "failover": False,
            "message": "no candidate nodes in same country",
            "reason": reason,
            "expected": expected,
        }

    errors = []
    for n in cands[:8]:
        name = n["name"]
        res = switch_node_live(profile_id, name, rebind_env=rebind_env)
        if not res.get("ok"):
            errors.append({"node": name, "error": res})
            continue
        # verify egress if possible
        if check_ip:
            eg2 = check_egress(profile_id)
            cc2 = ((eg2.get("egress") or {}).get("country") or "").upper()
            if eg2.get("ok") and (not expected or cc2 == str(expected).upper()):
                db.audit(
                    "node_failover",
                    profile_id,
                    {"from": current, "to": name, "reason": reason, "egress": eg2.get("egress")},
                )
                return {
                    "ok": True,
                    "failover": True,
                    "from": current,
                    "to": name,
                    "reason": reason,
                    "egress": eg2,
                    "profile": res.get("profile"),
                }
            errors.append({"node": name, "egress": eg2})
            continue
        return {
            "ok": True,
            "failover": True,
            "from": current,
            "to": name,
            "reason": reason,
            "profile": res.get("profile"),
        }

    return {
        "ok": False,
        "failover": False,
        "reason": reason,
        "message": "all candidates failed",
        "errors": errors[:5],
    }
