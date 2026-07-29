"""v3 nodes: favorites, latency test, group by country."""
from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from mozilla_manager import db
from mozilla_manager.env_packs import detect_country_from_node_name, recommend_from_node
from mozilla_manager.network.subscription import list_nodes


def list_nodes_enriched(sub: str = "default") -> list[dict[str, Any]]:
    nodes = list_nodes(sub)
    favs = {(f["sub"], f["node_name"]) for f in db.favorites_list(sub)}
    lats = {r["node_name"]: r for r in db.latency_list(sub)}
    out = []
    for n in nodes:
        name = n.get("name") or ""
        cc = detect_country_from_node_name(name)
        lat = lats.get(name) or {}
        out.append(
            {
                **n,
                "country": cc,
                "favorite": (sub, name) in favs,
                "latency_ms": lat.get("latency_ms"),
                "latency_ok": bool(lat.get("ok")) if lat else None,
                "latency_checked_at": lat.get("checked_at"),
            }
        )
    return out


def group_by_country(sub: str = "default") -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for n in list_nodes_enriched(sub):
        cc = n.get("country") or "ZZ"
        groups.setdefault(cc, []).append(n)
    # sort each group by latency
    for cc, items in groups.items():
        items.sort(
            key=lambda x: (
                0 if x.get("latency_ok") else 1,
                x.get("latency_ms") if x.get("latency_ms") is not None else 10**9,
            )
        )
    return dict(sorted(groups.items(), key=lambda kv: kv[0]))


def favorite_add(sub: str, node_name: str, note: str = "") -> dict[str, Any]:
    db.favorite_add(sub, node_name, note=note)
    db.audit("node_favorite_add", detail={"sub": sub, "node": node_name})
    return {"ok": True, "sub": sub, "node_name": node_name}


def favorite_remove(sub: str, node_name: str) -> dict[str, Any]:
    db.favorite_remove(sub, node_name)
    db.audit("node_favorite_remove", detail={"sub": sub, "node": node_name})
    return {"ok": True, "sub": sub, "node_name": node_name}


def favorites(sub: str | None = None) -> list[dict[str, Any]]:
    return db.favorites_list(sub)


def _tcp_ping(host: str, port: int, timeout: float = 3.0) -> tuple[bool, int | None, str]:
    if not host or not port:
        return False, None, "missing host/port"
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            ms = int((time.perf_counter() - t0) * 1000)
            return True, ms, ""
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return False, ms, str(e)


def speedtest(sub: str = "default", *, limit: int = 0, workers: int = 16) -> dict[str, Any]:
    """TCP connect latency to node server:port (not full proxy handshake)."""
    nodes = list_nodes(sub)
    if limit and limit > 0:
        nodes = nodes[:limit]
    results: list[dict[str, Any]] = []

    def one(n: dict[str, Any]) -> dict[str, Any]:
        name = n.get("name") or ""
        ok, ms, err = _tcp_ping(str(n.get("server") or ""), int(n.get("port") or 0))
        db.latency_upsert(sub, name, ms, ok, error=err)
        return {
            "name": name,
            "server": n.get("server"),
            "port": n.get("port"),
            "ok": ok,
            "latency_ms": ms,
            "error": err,
            "country": detect_country_from_node_name(name),
        }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(one, n) for n in nodes]
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"ok": False, "error": str(e)})
    results.sort(key=lambda x: (0 if x.get("ok") else 1, x.get("latency_ms") or 10**9))
    db.audit("node_speedtest", detail={"sub": sub, "count": len(results)})
    return {"ok": True, "sub": sub, "count": len(results), "results": results}


def select_node_recommend(node_name: str, *, jitter: bool = True) -> dict[str, Any]:
    """选节点 → 自动套用 tz/locale/geo 模板."""
    return recommend_from_node(node_name, jitter=jitter)


def preferred_by_country(sub: str = "default", country: str | None = None, *, limit: int = 20) -> dict[str, Any]:
    """按国家/地区测速排序优选节点."""
    groups = group_by_country(sub)
    if country:
        cc = country.upper()
        items = groups.get(cc) or []
        return {"sub": sub, "country": cc, "nodes": items[:limit]}
    # all countries best node
    best = []
    for cc, items in groups.items():
        if not items:
            continue
        best.append({"country": cc, "best": items[0], "count": len(items), "top": items[: min(5, limit)]})
    best.sort(key=lambda x: (0 if (x["best"] or {}).get("latency_ok") else 1, (x["best"] or {}).get("latency_ms") or 10**9))
    return {"sub": sub, "countries": best}
