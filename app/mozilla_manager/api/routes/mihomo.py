"""Mihomo process routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mozilla_manager.api.schemas import MihomoStartIn
from mozilla_manager.modules import mihomo_svc

router = APIRouter()


class CleanupIn(BaseModel):
    keep_ports: list[int] | None = None
    dry_run: bool = False


@router.get("/status")
def status() -> list[dict[str, Any]]:
    return mihomo_svc.status()


@router.get("/live")
def live() -> list[dict[str, Any]]:
    return mihomo_svc.live()


@router.post("/start")
def start(body: MihomoStartIn) -> dict[str, Any]:
    try:
        return mihomo_svc.start(body.port, body.sub, body.node)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/stop")
def stop(port: int) -> dict[str, Any]:
    try:
        return mihomo_svc.stop(port)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/cleanup-orphans")
def cleanup_orphans(body: CleanupIn | None = None) -> dict[str, Any]:
    body = body or CleanupIn()
    try:
        return mihomo_svc.cleanup_orphans(keep_ports=body.keep_ports, dry_run=body.dry_run)
    except Exception as e:
        raise HTTPException(400, str(e))
