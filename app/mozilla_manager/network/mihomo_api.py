"""Mihomo external-controller helpers — switch node without restarting browser."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


def controller_base(mihomo_port: int) -> str:
    # written in config as port+1000
    return f"http://127.0.0.1:{int(mihomo_port) + 1000}"


def switch_proxy(mihomo_port: int, node_name: str, group: str = "PROXY", timeout: float = 5.0) -> dict[str, Any]:
    base = controller_base(mihomo_port)
    url = f"{base}/proxies/{quote(group, safe='')}"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.put(url, json={"name": node_name})
            if r.status_code >= 400:
                # try get groups
                return {"ok": False, "status": r.status_code, "body": r.text[:300], "url": url}
            return {"ok": True, "group": group, "node": node_name, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


def get_proxy_group(mihomo_port: int, group: str = "PROXY", timeout: float = 5.0) -> dict[str, Any]:
    base = controller_base(mihomo_port)
    url = f"{base}/proxies/{quote(group, safe='')}"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url)
            r.raise_for_status()
            return {"ok": True, "data": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_proxies(mihomo_port: int, timeout: float = 5.0) -> dict[str, Any]:
    base = controller_base(mihomo_port)
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{base}/proxies")
            r.raise_for_status()
            return {"ok": True, "data": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
