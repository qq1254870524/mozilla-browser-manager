"""Proxies module: profile-bound inventory + SOCKS5 proxy library (CRUD/batch/refresh)."""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from mozilla_manager.paths import PROXIES_DIR, ensure_layout, safe_resolve
from mozilla_manager.store import ProfileStore

STORE_FILE = "socks5_store.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store_path() -> Path:
    ensure_layout()
    return safe_resolve(PROXIES_DIR / STORE_FILE)


def _load() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        return list(items or [])
    except Exception:
        return []


def _save(items: list[dict[str, Any]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"updated_at": _now(), "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_socks5_url(
    host: str,
    port: int | str,
    username: str | None = None,
    password: str | None = None,
) -> str:
    host = (host or "").strip()
    port_i = int(port)
    user = (username or "").strip()
    pwd = (password or "").strip()
    if user:
        auth = f"{quote(user, safe='')}:{quote(pwd, safe='')}@"
    else:
        auth = ""
    return f"socks5://{auth}{host}:{port_i}"


def parse_socks5_url(url: str) -> dict[str, Any]:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("empty socks5 url")
    try:
        from mozilla_manager.engines.proxy_util import parse_proxy_server
        parsed = parse_proxy_server(raw if "://" in raw else f"socks5://{raw}")
        host = parsed["host"]
        port = int(parsed["port"])
        user = parsed.get("username") or ""
        pwd = parsed.get("password") or ""
        return {
            "host": host,
            "port": port,
            "username": user,
            "password": pwd,
            "socks5": build_socks5_url(host, port, user, pwd),
        }
    except Exception:
        if "://" not in raw:
            raw = "socks5://" + raw
        u = urlparse(raw)
        if not u.hostname or u.port is None:
            raise ValueError(f"invalid socks5 url: {url}")
        return {
            "host": u.hostname,
            "port": int(u.port),
            "username": u.username or "",
            "password": u.password or "",
            "socks5": build_socks5_url(u.hostname, int(u.port), u.username, u.password),
        }


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    host = str(item.get("host") or "").strip()
    port = int(item.get("port") or 0)
    if not host or not port:
        # try from socks5 url
        if item.get("socks5"):
            parsed = parse_socks5_url(str(item["socks5"]))
            host = parsed["host"]
            port = parsed["port"]
            item.setdefault("username", parsed.get("username") or "")
            item.setdefault("password", parsed.get("password") or "")
        else:
            raise ValueError("host and port required")
    username = str(item.get("username") or item.get("user") or "").strip()
    password = str(item.get("password") or item.get("pass") or "").strip()
    name = str(item.get("name") or "").strip() or f"{host}:{port}"
    refresh_url = str(item.get("refresh_url") or item.get("ip_refresh_url") or item.get("refresh") or "").strip()
    socks5 = build_socks5_url(host, port, username, password)
    out = {
        "id": str(item.get("id") or uuid.uuid4().hex[:12]),
        "name": name,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "refresh_url": refresh_url,
        "socks5": socks5,
        "remark": str(item.get("remark") or "").strip(),
        "created_at": item.get("created_at") or _now(),
        "updated_at": _now(),
        "last_refresh_at": item.get("last_refresh_at"),
        "last_refresh_ok": item.get("last_refresh_ok"),
        "last_refresh_detail": item.get("last_refresh_detail"),
    }
    return out


def list_socks5() -> list[dict[str, Any]]:
    return _load()


def get_socks5(proxy_id: str) -> dict[str, Any]:
    for it in _load():
        if it.get("id") == proxy_id:
            return it
    raise KeyError(proxy_id)


def add_socks5(item: dict[str, Any]) -> dict[str, Any]:
    items = _load()
    row = _normalize_item(item)
    # dedupe by host:port:user
    key = f"{row['host']}:{row['port']}:{row['username']}"
    for i, old in enumerate(items):
        okey = f"{old.get('host')}:{old.get('port')}:{old.get('username') or ''}"
        if okey == key:
            row["id"] = old.get("id") or row["id"]
            row["created_at"] = old.get("created_at") or row["created_at"]
            items[i] = row
            _save(items)
            return {"ok": True, "item": row, "updated": True}
    items.append(row)
    _save(items)
    return {"ok": True, "item": row, "updated": False}


def update_socks5(proxy_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    items = _load()
    for i, old in enumerate(items):
        if old.get("id") != proxy_id:
            continue
        merged = dict(old)
        merged.update({k: v for k, v in patch.items() if v is not None})
        merged["id"] = proxy_id
        row = _normalize_item(merged)
        row["created_at"] = old.get("created_at") or row["created_at"]
        items[i] = row
        _save(items)
        return {"ok": True, "item": row}
    raise KeyError(proxy_id)


def delete_socks5(proxy_id: str) -> dict[str, Any]:
    items = _load()
    n = len(items)
    items = [x for x in items if x.get("id") != proxy_id]
    if len(items) == n:
        raise KeyError(proxy_id)
    _save(items)
    return {"ok": True, "id": proxy_id, "deleted": True}


def delete_socks5_many(ids: list[str]) -> dict[str, Any]:
    want = set(ids or [])
    items = _load()
    keep = [x for x in items if x.get("id") not in want]
    _save(keep)
    return {"ok": True, "deleted": len(items) - len(keep)}


_LINE_SPLIT = re.compile(r"[\r\n]+")


def parse_batch_lines(text: str) -> list[dict[str, Any]]:
    """Parse multi-line SOCKS5 definitions.

    Supported per line:
      host:port
      host:port:user:pass
      host:port:user:pass:https://refresh
      host|port|user|pass|refresh_url
      socks5://user:pass@host:port
      socks5://user:pass@host:port|https://refresh
      name,host,port,user,pass,refresh_url
    Lines starting with # are comments.
    """
    out: list[dict[str, Any]] = []
    for raw in _LINE_SPLIT.split(text or ""):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        item: dict[str, Any] = {}
        refresh = ""
        # pipe form
        if "|" in line and "://" not in line.split("|")[0]:
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 2 and parts[0] and parts[1].isdigit():
                item = {
                    "host": parts[0],
                    "port": int(parts[1]),
                    "username": parts[2] if len(parts) > 2 else "",
                    "password": parts[3] if len(parts) > 3 else "",
                    "refresh_url": parts[4] if len(parts) > 4 else "",
                }
                out.append(_normalize_item(item))
                continue
        # csv form name,host,port,...
        if line.count(",") >= 2 and not line.lower().startswith("socks5://"):
            parts = [x.strip() for x in line.split(",")]
            # host,port,... or name,host,port,...
            if len(parts) >= 2 and parts[1].isdigit():
                item = {
                    "name": parts[0],
                    "host": parts[1],
                    "port": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else int(parts[1]) if parts[1].isdigit() else 0,
                }
                # ambiguous — prefer host,port,user,pass
            if re.match(r"^[^,]+,\d+", line):
                parts = [x.strip() for x in line.split(",")]
                item = {
                    "host": parts[0],
                    "port": int(parts[1]),
                    "username": parts[2] if len(parts) > 2 else "",
                    "password": parts[3] if len(parts) > 3 else "",
                    "refresh_url": parts[4] if len(parts) > 4 else "",
                }
                out.append(_normalize_item(item))
                continue
            if len(parts) >= 3 and parts[2].isdigit():
                item = {
                    "name": parts[0],
                    "host": parts[1],
                    "port": int(parts[2]),
                    "username": parts[3] if len(parts) > 3 else "",
                    "password": parts[4] if len(parts) > 4 else "",
                    "refresh_url": parts[5] if len(parts) > 5 else "",
                }
                out.append(_normalize_item(item))
                continue
        # url + optional refresh after space or |
        if "socks5://" in line.lower() or line.lower().startswith("socks5:"):
            main, *rest = re.split(r"[|\s]+", line, maxsplit=1)
            if rest:
                refresh = rest[0].strip()
            parsed = parse_socks5_url(main)
            parsed["refresh_url"] = refresh
            out.append(_normalize_item(parsed))
            continue
        # host:port:user:pass[:refresh]
        # refresh url may contain ':' — if http(s) appears, split carefully
        if "://" in line:
            # host:port:user:pass:https://...
            m = re.match(
                r"^(?P<host>[^:]+):(?P<port>\d+)(?::(?P<user>[^:]*):(?P<pwd>.*?))?:(?P<ref>https?://\S+)$",
                line,
            )
            if m:
                item = {
                    "host": m.group("host"),
                    "port": int(m.group("port")),
                    "username": m.group("user") or "",
                    "password": m.group("pwd") or "",
                    "refresh_url": m.group("ref"),
                }
                out.append(_normalize_item(item))
                continue
        parts = line.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            host = parts[0]
            port = int(parts[1])
            user = parts[2] if len(parts) > 2 else ""
            # password may contain colons? take rest until refresh detection
            if len(parts) == 3:
                pwd = ""
                # host:port:user  (no pass)
            elif len(parts) >= 4:
                pwd = parts[3]
                extra = parts[4:]
                if extra:
                    maybe = ":".join(extra)
                    if maybe.startswith("http://") or maybe.startswith("https://"):
                        refresh = maybe
                    else:
                        # password had colons
                        pwd = ":".join(parts[3:])
                        if "http://" in pwd or "https://" in pwd:
                            # split password and refresh
                            idx = pwd.find("http://")
                            if idx < 0:
                                idx = pwd.find("https://")
                            if idx >= 0:
                                refresh = pwd[idx:]
                                pwd = pwd[:idx].rstrip(":")
            else:
                pwd = ""
            item = {
                "host": host,
                "port": port,
                "username": user,
                "password": pwd if len(parts) >= 4 else "",
                "refresh_url": refresh,
            }
            # fix user-only case host:port:user
            if len(parts) == 3:
                item["username"] = parts[2]
                item["password"] = ""
            out.append(_normalize_item(item))
            continue
        raise ValueError(f"unrecognized proxy line: {line}")
    return out


def batch_add_socks5(text: str = "", items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    errors: list[str] = []
    if text:
        try:
            parsed.extend(parse_batch_lines(text))
        except Exception as e:
            # try line by line to collect partial
            for raw in _LINE_SPLIT.split(text or ""):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    parsed.extend(parse_batch_lines(line))
                except Exception as e2:
                    errors.append(f"{line[:80]} -> {e2}")
    for it in items or []:
        try:
            parsed.append(_normalize_item(it))
        except Exception as e:
            errors.append(str(e))
    added = 0
    updated = 0
    results = []
    for it in parsed:
        r = add_socks5(it)
        results.append(r.get("item"))
        if r.get("updated"):
            updated += 1
        else:
            added += 1
    return {
        "ok": True,
        "added": added,
        "updated": updated,
        "total": len(_load()),
        "items": results,
        "errors": errors,
    }


def refresh_ip(proxy_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Hit provider refresh URL to rotate exit IP. Does not change system proxy."""
    items = _load()
    row = None
    idx = -1
    for i, it in enumerate(items):
        if it.get("id") == proxy_id:
            row = it
            idx = i
            break
    if not row:
        raise KeyError(proxy_id)
    url = (row.get("refresh_url") or "").strip()
    if not url:
        return {"ok": False, "id": proxy_id, "error": "no refresh_url configured"}
    detail: dict[str, Any] = {"url": url}
    ok = False
    try:
        req = Request(url, method="GET", headers={"User-Agent": "MozillaManager/1.10.2"})
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read(2000).decode("utf-8", "replace")
            detail["status"] = getattr(resp, "status", None) or resp.getcode()
            detail["body"] = body[:500]
            ok = 200 <= int(detail["status"]) < 400
    except Exception as e:
        detail["error"] = str(e)
        ok = False
    row = dict(row)
    row["last_refresh_at"] = _now()
    row["last_refresh_ok"] = ok
    row["last_refresh_detail"] = detail
    row["updated_at"] = _now()
    items[idx] = row
    _save(items)
    # small settle delay for providers that need it
    if ok:
        time.sleep(0.2)
    return {"ok": ok, "id": proxy_id, "item": row, "detail": detail}


def list_proxies() -> list[dict[str, Any]]:
    """Combined view: saved SOCKS5 library + live profile bindings."""
    saved = []
    for it in list_socks5():
        saved.append(
            {
                "id": it["id"],
                "source": "library",
                "info": f"{it.get('name')} · {it.get('host')}:{it.get('port')}",
                "mode": "socks5",
                "socks5": it.get("socks5"),
                "host": it.get("host"),
                "port": it.get("port"),
                "username": it.get("username"),
                "password": it.get("password"),
                "refresh_url": it.get("refresh_url"),
                "remark": it.get("remark"),
                "last_refresh_at": it.get("last_refresh_at"),
                "last_refresh_ok": it.get("last_refresh_ok"),
                "profiles": [],
                "count": 0,
            }
        )
    # map socks url -> library id for association
    by_url = {s["socks5"]: s for s in saved if s.get("socks5")}
    by_hostport = {f"{s['host']}:{s['port']}": s for s in saved}

    buckets: dict[str, dict[str, Any]] = {}
    for p in ProfileStore().list():
        px = p.proxy
        if px.mode == "none":
            key = "direct"
            info = "No Proxy (本地直连)"
            mode = "none"
            socks5 = None
        elif px.mode == "socks5":
            key = f"socks5:{px.socks5}"
            info = px.socks5 or ""
            mode = "socks5"
            socks5 = px.socks5
        else:
            key = f"mihomo:{px.mihomo_port}:{px.node_name or ''}"
            info = f"mihomo mixed://127.0.0.1:{px.mihomo_port} node={px.node_name or '-'}"
            mode = "mihomo"
            socks5 = None
        if key not in buckets:
            buckets[key] = {
                "id": key,
                "source": "binding",
                "info": info,
                "mode": mode,
                "socks5": socks5,
                "mihomo_port": px.mihomo_port if mode == "mihomo" else None,
                "node_name": px.node_name if mode == "mihomo" else None,
                "profiles": [],
                "count": 0,
                "library_id": None,
            }
        buckets[key]["profiles"].append(p.id)
        buckets[key]["count"] += 1
        if socks5:
            lib = by_url.get(socks5)
            if not lib:
                try:
                    parsed = parse_socks5_url(socks5)
                    lib = by_hostport.get(f"{parsed['host']}:{parsed['port']}")
                except Exception:
                    lib = None
            if lib:
                lib["profiles"].append(p.id)
                lib["count"] += 1
                buckets[key]["library_id"] = lib["id"]

    # library first, then unbound bindings
    out = list(saved)
    for b in buckets.values():
        if b["mode"] == "socks5" and b.get("library_id"):
            continue  # already represented via library row counts
        out.append(b)
    return out
