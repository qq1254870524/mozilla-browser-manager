from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import yaml

from .. import db
from ..paths import NODES_DIR, ensure_layout, safe_resolve
from . import node_store


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _is_info_proxy(px: dict[str, Any]) -> bool:
    """Subscription banner / traffic / expiry placeholders (not real egress)."""
    name = str(px.get("name") or "")
    server = str(px.get("server") or "")
    keys = ("剩余流量", "套餐到期", "距离下次", "过期时间", "到期时间", "流量：", "重置剩余", "官网", "最新网址", "纯流量")
    if any(k in name for k in keys):
        return True
    if server in ("127.0.0.1", "0.0.0.0", "localhost") and any(k in name for k in ("流量", "到期", "重置", "剩余", "官网", "通知")):
        return True
    return False


def summarize_proxies(proxies: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter
    types = Counter()
    info = 0
    real = 0
    for px in proxies:
        if not isinstance(px, dict):
            continue
        types[str(px.get("type") or "?")] += 1
        if _is_info_proxy(px):
            info += 1
        else:
            real += 1
    return {
        "total": len(proxies),
        "usable": real,
        "info": info,
        "types": dict(types),
    }



def _b64decode(text: str) -> str:
    s = text.strip().replace("\n", "").replace("\r", "").replace(" ", "")
    pad = (-len(s)) % 4
    try:
        return base64.urlsafe_b64decode(s + ("=" * pad)).decode("utf-8", errors="ignore")
    except Exception:
        try:
            return base64.b64decode(s + ("=" * pad)).decode("utf-8", errors="ignore")
        except Exception:
            return ""


def _parse_ss(uri: str) -> dict[str, Any] | None:
    # ss://base64(method:pass@host:port)#name  OR ss://base64(method:pass)@host:port#name
    try:
        raw = uri[5:]
        name = ""
        if "#" in raw:
            raw, name = raw.split("#", 1)
            name = unquote(name)
        if "@" in raw and not raw.startswith("@"):
            userinfo, hostport = raw.rsplit("@", 1)
            # userinfo may be base64
            if ":" not in userinfo:
                userinfo = _b64decode(userinfo)
            method, password = userinfo.split(":", 1)
            host, port = hostport.rsplit(":", 1)
        else:
            decoded = _b64decode(raw)
            # method:password@host:port
            userinfo, hostport = decoded.rsplit("@", 1)
            method, password = userinfo.split(":", 1)
            host, port = hostport.rsplit(":", 1)
        return {
            "name": name or f"ss-{host}-{port}",
            "type": "ss",
            "server": host,
            "port": int(port),
            "cipher": method,
            "password": password,
        }
    except Exception:
        return None


def _parse_ssr(uri: str) -> dict[str, Any] | None:
    # ssr not fully supported by mihomo the same way; skip lightly
    return None


def _parse_vmess(uri: str) -> dict[str, Any] | None:
    try:
        raw = uri[8:]
        if "#" in raw:
            raw = raw.split("#", 1)[0]
        data = json.loads(_b64decode(raw) or raw)
        net = data.get("net") or "tcp"
        tls = data.get("tls") or ""
        node: dict[str, Any] = {
            "name": data.get("ps") or f"vmess-{data.get('add')}",
            "type": "vmess",
            "server": data.get("add"),
            "port": int(data.get("port") or 0),
            "uuid": data.get("id"),
            "alterId": int(data.get("aid") or 0),
            "cipher": data.get("scy") or "auto",
            "network": net,
        }
        if tls:
            node["tls"] = True
            if data.get("sni"):
                node["servername"] = data["sni"]
        if net == "ws":
            node["ws-opts"] = {
                "path": data.get("path") or "/",
                "headers": {"Host": data.get("host") or data.get("add") or ""},
            }
        elif net == "h2":
            node["h2-opts"] = {"host": [data.get("host") or data.get("add")], "path": data.get("path") or "/"}
        elif net == "grpc":
            node["grpc-opts"] = {"grpc-service-name": data.get("path") or ""}
        return node
    except Exception:
        return None


def _parse_vless(uri: str) -> dict[str, Any] | None:
    try:
        u = urlparse(uri)
        name = unquote(u.fragment or f"vless-{u.hostname}")
        q = parse_qs(u.query)
        def q1(k: str, default: str = "") -> str:
            return (q.get(k) or [default])[0]
        node: dict[str, Any] = {
            "name": name,
            "type": "vless",
            "server": u.hostname,
            "port": int(u.port or 0),
            "uuid": unquote(u.username or ""),
            "network": q1("type", "tcp"),
            "tls": q1("security") in ("tls", "reality"),
            "udp": True,
        }
        if q1("security") == "reality":
            node["reality-opts"] = {
                "public-key": q1("pbk"),
                "short-id": q1("sid"),
            }
            node["client-fingerprint"] = q1("fp", "chrome")
            node["servername"] = q1("sni")
        elif node["tls"]:
            node["servername"] = q1("sni")
            node["client-fingerprint"] = q1("fp", "chrome")
        if q1("flow"):
            node["flow"] = q1("flow")
        net = node["network"]
        if net == "ws":
            node["ws-opts"] = {"path": q1("path", "/"), "headers": {"Host": q1("host") or u.hostname or ""}}
        elif net == "grpc":
            node["grpc-opts"] = {"grpc-service-name": q1("serviceName") or q1("path")}
        return node
    except Exception:
        return None


def _parse_trojan(uri: str) -> dict[str, Any] | None:
    try:
        u = urlparse(uri)
        name = unquote(u.fragment or f"trojan-{u.hostname}")
        q = parse_qs(u.query)
        def q1(k: str, default: str = "") -> str:
            return (q.get(k) or [default])[0]
        node: dict[str, Any] = {
            "name": name,
            "type": "trojan",
            "server": u.hostname,
            "port": int(u.port or 0),
            "password": unquote(u.username or ""),
            "udp": True,
            "sni": q1("sni") or u.hostname,
        }
        if q1("type") == "ws":
            node["network"] = "ws"
            node["ws-opts"] = {"path": q1("path", "/"), "headers": {"Host": q1("host") or u.hostname or ""}}
        return node
    except Exception:
        return None


def _parse_hysteria2(uri: str) -> dict[str, Any] | None:
    try:
        # hysteria2://password@host:port?sni=...#name
        u = urlparse(uri.replace("hy2://", "hysteria2://"))
        name = unquote(u.fragment or f"hy2-{u.hostname}")
        q = parse_qs(u.query)
        def q1(k: str, default: str = "") -> str:
            return (q.get(k) or [default])[0]
        return {
            "name": name,
            "type": "hysteria2",
            "server": u.hostname,
            "port": int(u.port or 0),
            "password": unquote(u.username or ""),
            "sni": q1("sni") or u.hostname,
            "skip-cert-verify": q1("insecure") in ("1", "true", "True"),
        }
    except Exception:
        return None


def _parse_tuic(uri: str) -> dict[str, Any] | None:
    try:
        u = urlparse(uri)
        name = unquote(u.fragment or f"tuic-{u.hostname}")
        q = parse_qs(u.query)
        def q1(k: str, default: str = "") -> str:
            return (q.get(k) or [default])[0]
        # tuic://uuid:password@host:port?…  or tuic://uuid@host:port?password=
        user = unquote(u.username or "")
        password = unquote(u.password or "") or q1("password")
        node: dict[str, Any] = {
            "name": name,
            "type": "tuic",
            "server": u.hostname,
            "port": int(u.port or 0),
            "uuid": user,
            "password": password,
            "udp": True,
        }
        if q1("sni"):
            node["sni"] = q1("sni")
        if q1("congestion_control") or q1("congestion-controller"):
            node["congestion-controller"] = q1("congestion_control") or q1("congestion-controller")
        if q1("alpn"):
            node["alpn"] = [x.strip() for x in q1("alpn").split(",") if x.strip()]
        return node
    except Exception:
        return None


def parse_share_links(text: str, *, return_stats: bool = False):
    """Parse share-link subscription body into mihomo proxies.

    Supported: ss / vmess / vless / trojan / hysteria2 / hy2 / tuic
    Unsupported lines are counted in stats.skipped (ssr/wireguard/unknown).
    """
    proxies: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped: list[dict[str, Any]] = []
    raw_lines = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw_lines += 1
        node = None
        kind = ""
        if line.startswith("ss://"):
            kind, node = "ss", _parse_ss(line)
        elif line.startswith("vmess://"):
            kind, node = "vmess", _parse_vmess(line)
        elif line.startswith("vless://"):
            kind, node = "vless", _parse_vless(line)
        elif line.startswith("trojan://"):
            kind, node = "trojan", _parse_trojan(line)
        elif line.startswith("hysteria2://") or line.startswith("hy2://"):
            kind, node = "hysteria2", _parse_hysteria2(line)
        elif line.startswith("tuic://"):
            kind, node = "tuic", _parse_tuic(line)
        elif line.startswith("ssr://"):
            kind, node = "ssr", None  # not mapped
            skipped.append({"proto": "ssr", "line": line[:160], "reason": "ssr not mapped to mihomo"})
            continue
        elif line.startswith("wireguard://") or line.startswith("wg://"):
            skipped.append({"proto": "wireguard", "line": line[:160], "reason": "wireguard share-link not mapped"})
            continue
        else:
            # non-uri noise
            if "://" in line:
                proto = line.split("://", 1)[0][:20]
                skipped.append({"proto": proto, "line": line[:160], "reason": "unsupported proto"})
            else:
                skipped.append({"proto": "?", "line": line[:160], "reason": "not a share link"})
            continue
        if not node or not node.get("server"):
            skipped.append({"proto": kind or "?", "line": line[:160], "reason": "parse failed"})
            continue
        base = str(node["name"])
        name = base
        i = 2
        while name in seen:
            name = f"{base}-{i}"
            i += 1
        node["name"] = name
        seen.add(name)
        proxies.append(node)
    if return_stats:
        stats = summarize_proxies(proxies)
        stats.update({"raw_lines": raw_lines, "parsed": len(proxies), "skipped": len(skipped), "skipped_samples": skipped[:20]})
        return proxies, stats
    return proxies


def _build_mihomo_config(proxies: list[dict[str, Any]]) -> dict[str, Any]:
    names = [p["name"] for p in proxies] or ["DIRECT"]
    return {
        "mixed-port": 0,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "ipv6": True,
        "proxies": proxies,
        "proxy-groups": [
            {"name": "PROXY", "type": "select", "proxies": names + (["DIRECT"] if "DIRECT" not in names else [])},
            {
                "name": "AUTO",
                "type": "url-test",
                "proxies": names if proxies else ["DIRECT"],
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
            },
        ],
        "rules": [
            "GEOIP,CN,DIRECT",
            "MATCH,PROXY",
        ],
    }


def import_subscription(
    url: str,
    name: str = "default",
    timeout: float = 60.0,
    proxy_url: str | None = None,
) -> dict[str, Any]:
    """Download subscription (YAML/base64 share-links) into data/nodes/ only.

    proxy_url: optional http/socks5 proxy for download (useful when provider does region deny).
    """
    ensure_layout()
    safe_name = node_store._safe_name(name)
    raw_path = safe_resolve(NODES_DIR / f"sub_{safe_name}.raw")
    meta_path = safe_resolve(NODES_DIR / f"sub_{safe_name}.json")
    yaml_path = safe_resolve(NODES_DIR / f"sub_{safe_name}.yaml")

    headers = {
        "User-Agent": "ClashMetaForAndroid/2.11.1",
        "Accept": "*/*",
    }
    uas = [
        "ClashMetaForAndroid/2.11.1",
        "clash-verge/1.7.7",
        "ClashForWindows/0.20.39",
        "v2rayN/6.23",
    ]
    last_err: Exception | None = None
    content: bytes | None = None
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers, proxy=proxy_url) as client:
        for ua in uas:
            try:
                r = client.get(url, headers={**headers, "User-Agent": ua})
                if r.status_code in (403, 429, 401):
                    body = (r.text or "")[:240]
                    last_err = httpx.HTTPStatusError(
                        f"HTTP {r.status_code} from subscription provider"
                        + (f" via proxy {proxy_url}" if proxy_url else "")
                        + f": {body}",
                        request=r.request,
                        response=r,
                    )
                    # try next UA
                    continue
                r.raise_for_status()
                content = r.content
                break
            except Exception as e:
                last_err = e
                continue
    if content is None:
        hint = ""
        msg = str(last_err or "download failed")
        if "region has been denied" in msg.lower() or "403" in msg:
            hint = (
                " | 供应商按地区拒绝（The region has been denied）。"
                "直连/部分机房 IP 会被拦；可换住宅节点出口后再导入，或让供应商加白名单。"
            )
        if "401" in msg:
            hint += " | HTTP 401 通常是 token 无效/过期/权限不足，请核对订阅链接。"
        raise RuntimeError(msg + hint)

    raw_path.write_bytes(content)
    text = content.decode("utf-8", errors="ignore").strip()

    parsed: Any = None
    try:
        parsed = yaml.safe_load(text)
    except Exception:
        parsed = None

    node_count = 0
    source = "yaml"

    if isinstance(parsed, dict) and (parsed.get("proxies") or parsed.get("proxy-groups")):
        node_count = len(parsed.get("proxies") or [])
        source = "clash-yaml"
    else:
        # base64 subscription of share links
        decoded = _b64decode(text)
        body = decoded if decoded and ("://" in decoded or "\n" in decoded) else text
        proxies = parse_share_links(body)
        if not proxies and "://" in text:
            proxies = parse_share_links(text)
        parsed = _build_mihomo_config(proxies)
        node_count = len(proxies)
        source = "share-links"

    # backup previous yaml (legacy path)
    if yaml_path.exists():
        bak = yaml_path.with_suffix(f".yaml.bak_{_now().replace(':', '')}")
        bak.write_bytes(yaml_path.read_bytes())

    # always keep original provider bytes on legacy raw path
    raw_bytes = content if isinstance(content, (bytes, bytearray)) else str(content).encode("utf-8", errors="ignore")
    raw_path.write_bytes(raw_bytes)
    # v5: primary store under runtime/nodes/subs/<name>/
    if not isinstance(parsed, dict):
        parsed = _build_mihomo_config([])
    # parse stats for share-links path
    parse_stats: dict[str, Any] = {}
    if source == "share-links":
        # recompute with stats (parsed already built)
        try:
            decoded = _b64decode(text)
            body = decoded if decoded and ("://" in decoded or "\n" in decoded) else text
            _px, parse_stats = parse_share_links(body, return_stats=True)
            if not _px and "://" in text:
                _px, parse_stats = parse_share_links(text, return_stats=True)
        except Exception as e:
            parse_stats = {"error": str(e)}
    proxies_list = [x for x in (parsed.get("proxies") or []) if isinstance(x, dict)] if isinstance(parsed, dict) else []
    summary = summarize_proxies(proxies_list)
    if parse_stats:
        summary["parse"] = parse_stats

    meta = node_store.save_subscription_bundle(
        safe_name,
        url=url,
        parsed=parsed,
        raw_bytes=raw_bytes,
        source=source,
        node_count=node_count,
    )
    # keep legacy paths in meta for compatibility
    meta["raw"] = str(raw_path)
    meta["yaml"] = str(yaml_path)
    meta["bytes"] = len(content) if isinstance(content, (bytes, bytearray)) else raw_path.stat().st_size
    meta["stats"] = summary
    meta["usable_count"] = summary.get("usable")
    meta["info_count"] = summary.get("info")
    meta["types"] = summary.get("types")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    # also merge stats into runtime meta.json
    try:
        runtime_meta = node_store.load_sub_meta(safe_name) or {}
        runtime_meta.update({"stats": summary, "usable_count": summary.get("usable"), "info_count": summary.get("info"), "types": summary.get("types")})
        from mozilla_manager.network.node_store import sub_dir
        (sub_dir(safe_name) / "meta.json").write_text(json.dumps(runtime_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        meta.update(runtime_meta)
    except Exception:
        pass
    try:
        db.upsert_subscription(meta, ok=True)
        db.audit("sub_import", detail={"name": safe_name, "node_count": node_count, "usable": summary.get("usable"), "runtime_nodes": True})
    except Exception:
        pass
    return meta


def refresh_subscription(name: str = "default", *, timeout: float = 60.0) -> dict[str, Any]:
    """Re-fetch by saved URL. On failure keep previous yaml/meta (失败保留旧表)."""
    ensure_layout()
    safe_name = node_store._safe_name(name)
    meta_path = safe_resolve(NODES_DIR / f"sub_{safe_name}.json")
    yaml_path = safe_resolve(NODES_DIR / f"sub_{safe_name}.yaml")
    runtime_dir = node_store.sub_dir(safe_name)
    old_meta = node_store.load_sub_meta(safe_name) or {}
    if not old_meta and meta_path.exists():
        try:
            old_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"ok": False, "error": f"meta corrupt: {e}"}
    if not old_meta:
        return {"ok": False, "error": f"no subscription meta for {safe_name}"}
    url = old_meta.get("url")
    if not url or str(url).startswith("file://"):
        return {"ok": False, "error": "meta has no refreshable url"}
    # snapshot old for restore (legacy + runtime)
    old_yaml = yaml_path.read_bytes() if yaml_path.exists() else None
    old_meta_bytes = meta_path.read_bytes() if meta_path.exists() else None
    runtime_snap: dict[str, bytes] = {}
    for fname in ("meta.json", "clash.yaml", "nodes.json", "nodes.jsonl", "raw.bin", "raw.txt"):
        fp = runtime_dir / fname
        if fp.exists():
            try:
                runtime_snap[fname] = fp.read_bytes()
            except Exception:
                pass
    try:
        new_meta = import_subscription(url, name=safe_name, timeout=timeout)
        new_meta["refreshed_from"] = "schedule_or_manual"
        return {"ok": True, "meta": new_meta, "kept_old": False}
    except Exception as e:
        # restore old
        try:
            if old_yaml is not None:
                yaml_path.write_bytes(old_yaml)
            if old_meta_bytes is not None:
                meta_path.write_bytes(old_meta_bytes)
            for fname, blob in runtime_snap.items():
                (runtime_dir / fname).write_bytes(blob)
        except Exception:
            pass
        try:
            db.upsert_subscription(old_meta, ok=False)
            db.audit("sub_refresh_fail", detail={"name": safe_name, "error": str(e)})
        except Exception:
            pass
        return {"ok": False, "error": str(e), "kept_old": True, "meta": old_meta}


def refresh_due_subscriptions(*, force: bool = False) -> list[dict[str, Any]]:
    """Refresh subs whose update_interval elapsed (default 360 min)."""
    from datetime import datetime, timezone, timedelta

    results = []
    for row in db.list_subscription_rows() or []:
        name = row.get("name")
        # fallback to file metas
        pass
    # also from files
    for meta in list_subscriptions():
        name = meta.get("name") or "default"
        interval = int(meta.get("update_interval_min") or 360)
        last = meta.get("imported_at") or meta.get("last_update_at") or ""
        due = force
        if not due and last:
            try:
                # accept Z
                ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
                due = datetime.now(timezone.utc) - ts > timedelta(minutes=interval)
            except Exception:
                due = True
        elif not last:
            due = True
        if due:
            results.append(refresh_subscription(name))
        else:
            results.append({"ok": True, "skipped": True, "name": name, "reason": "not_due"})
    return results


def list_nodes_raw(subscription_name: str = "default") -> list[dict[str, Any]]:
    """Full proxy dicts (no desensitization) for export/speed internals."""
    ensure_layout()
    safe_name = node_store._safe_name(subscription_name)
    nodes = node_store.load_nodes_full(safe_name)
    if nodes:
        return nodes
    yaml_path = NODES_DIR / f"sub_{safe_name}.yaml"
    if not yaml_path.exists():
        return []
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8", errors="ignore")) or {}
    except Exception:
        return []
    return [p for p in (data.get("proxies") or []) if isinstance(p, dict)]


def list_subscriptions() -> list[dict[str, Any]]:
    ensure_layout()
    try:
        node_store.migrate_legacy_to_runtime()
    except Exception:
        pass
    detail = node_store.list_subscriptions_detail()
    if detail:
        return detail
    out = []
    for f in sorted(NODES_DIR.glob("sub_*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            out.append({"name": f.stem, "error": "invalid json"})
    return out


def list_nodes(subscription_name: str = "default") -> list[dict[str, Any]]:
    ensure_layout()
    safe_name = node_store._safe_name(subscription_name)
    proxies = node_store.load_nodes_full(safe_name)
    if not proxies:
        yaml_path = NODES_DIR / f"sub_{safe_name}.yaml"
        if yaml_path.exists():
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8", errors="ignore")) or {}
                proxies = [x for x in (data.get("proxies") or []) if isinstance(x, dict)]
            except Exception:
                proxies = []
    out = []
    for i, px in enumerate(proxies):
        out.append(
            {
                "index": i,
                "name": px.get("name"),
                "type": px.get("type"),
                "server": px.get("server"),
                "port": px.get("port"),
                # v5: expose extra non-secret fields; full dump via export
                "udp": px.get("udp"),
                "network": px.get("network") or px.get("net"),
                "info": _is_info_proxy(px),
            }
        )
    return out
