from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mozilla_manager.modules import watchdog_svc

router = APIRouter()

class WdIn(BaseModel):
    id: Optional[str] = None
    kind: str = "login_check"
    profile_id: str
    every_minutes: Optional[int] = 60
    daily_at: Optional[str] = None
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)

@router.get("")
def list_wd() -> list[dict[str, Any]]:
    return watchdog_svc.list_watchdogs()

@router.get("/status")
def status() -> dict[str, Any]:
    return watchdog_svc.status()

@router.post("")
def upsert(body: WdIn) -> dict[str, Any]:
    return watchdog_svc.upsert(
        watchdog_id=body.id,
        kind=body.kind,
        profile_id=body.profile_id,
        every_minutes=body.every_minutes,
        daily_at=body.daily_at,
        enabled=body.enabled,
        params=body.params,
    )

@router.delete("/{watchdog_id}")
def remove(watchdog_id: str) -> dict[str, Any]:
    return watchdog_svc.remove(watchdog_id)

@router.post("/tick")
def tick() -> dict[str, Any]:
    return {"ok": True, "ran": watchdog_svc.tick_once()}

@router.post("/start")
def start() -> dict[str, Any]:
    return watchdog_svc.start_watchdog_loop()
