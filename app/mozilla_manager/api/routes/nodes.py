"""Nodes API: list enriched, favorites, speedtest, country groups."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mozilla_manager.modules import nodes_svc
from mozilla_manager.network import node_store

router = APIRouter()


class FavIn(BaseModel):
    sub: str = "default"
    node_name: str
    note: str = ""


class SpeedIn(BaseModel):
    sub: str = "default"
    limit: int = 0
    workers: int = 16


@router.get("")
def list_nodes(sub: str | None = None) -> list[dict[str, Any]]:
    return nodes_svc.list_nodes_enriched(sub or node_store.get_active())


@router.get("/groups")
def groups(sub: str | None = None) -> dict[str, Any]:
    name = sub or node_store.get_active()
    g = nodes_svc.group_by_country(name)
    return {"sub": name, "countries": list(g.keys()), "groups": g}


@router.get("/favorites")
def favorites(sub: str | None = None) -> list[dict[str, Any]]:
    return nodes_svc.favorites(sub)


@router.post("/favorites")
def fav_add(body: FavIn) -> dict[str, Any]:
    return nodes_svc.favorite_add(body.sub, body.node_name, note=body.note)


@router.delete("/favorites")
def fav_del(sub: str, node_name: str) -> dict[str, Any]:
    return nodes_svc.favorite_remove(sub, node_name)


@router.post("/speedtest")
def speedtest(body: SpeedIn | None = None) -> dict[str, Any]:
    body = body or SpeedIn()
    return nodes_svc.speedtest(body.sub, limit=body.limit, workers=body.workers)


@router.get("/recommend")
def recommend(node_name: str) -> dict[str, Any]:
    return nodes_svc.select_node_recommend(node_name)


@router.get("/preferred")
def preferred(sub: str = "default", country: str | None = None, limit: int = 20) -> dict[str, Any]:
    return nodes_svc.preferred_by_country(sub, country=country, limit=limit)
