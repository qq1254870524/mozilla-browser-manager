"""Proxies routes: bindings inventory + SOCKS5 library."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mozilla_manager.modules import proxies as proxies_mod

router = APIRouter()


class Socks5In(BaseModel):
    name: str = ""
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    refresh_url: str = ""
    remark: str = ""
    socks5: str = ""  # optional full URL alternative


class Socks5Patch(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    refresh_url: Optional[str] = None
    remark: Optional[str] = None
    socks5: Optional[str] = None


class BatchIn(BaseModel):
    text: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)


class IdsIn(BaseModel):
    ids: list[str] = Field(default_factory=list)


@router.get("")
def list_proxies() -> list[dict[str, Any]]:
    return proxies_mod.list_proxies()


@router.get("/socks5")
def list_socks5() -> dict[str, Any]:
    items = proxies_mod.list_socks5()
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/socks5")
def add_socks5(body: Socks5In) -> dict[str, Any]:
    try:
        payload = body.model_dump()
        if body.socks5 and not body.host:
            parsed = proxies_mod.parse_socks5_url(body.socks5)
            payload.update(parsed)
        return proxies_mod.add_socks5(payload)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/socks5/batch")
def batch_socks5(body: BatchIn) -> dict[str, Any]:
    try:
        return proxies_mod.batch_add_socks5(text=body.text, items=body.items)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.patch("/socks5/{proxy_id}")
def patch_socks5(proxy_id: str, body: Socks5Patch) -> dict[str, Any]:
    try:
        return proxies_mod.update_socks5(proxy_id, body.model_dump(exclude_unset=True))
    except KeyError:
        raise HTTPException(404, "proxy not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/socks5/{proxy_id}")
def delete_socks5(proxy_id: str) -> dict[str, Any]:
    try:
        return proxies_mod.delete_socks5(proxy_id)
    except KeyError:
        raise HTTPException(404, "proxy not found")


@router.post("/socks5/delete-batch")
def delete_batch(body: IdsIn) -> dict[str, Any]:
    return proxies_mod.delete_socks5_many(body.ids)


@router.post("/socks5/{proxy_id}/refresh-ip")
def refresh_ip(proxy_id: str) -> dict[str, Any]:
    try:
        return proxies_mod.refresh_ip(proxy_id)
    except KeyError:
        raise HTTPException(404, "proxy not found")
    except Exception as e:
        raise HTTPException(400, str(e))
