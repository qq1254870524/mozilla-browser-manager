from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from mozilla_manager.modules import lock_svc

router = APIRouter()

class LockIn(BaseModel):
    reason: str = "manual"
    owner: str = "ui"
    ttl_sec: int = 3600

@router.get("")
def list_locked() -> list[dict[str, Any]]:
    return lock_svc.list_locked()

@router.get("/profiles/{profile_id}")
def status(profile_id: str) -> dict[str, Any]:
    return lock_svc.is_locked(profile_id)

@router.post("/profiles/{profile_id}/lock")
def lock(profile_id: str, body: LockIn | None = None) -> dict[str, Any]:
    body = body or LockIn()
    try:
        r = lock_svc.lock(profile_id, reason=body.reason, owner=body.owner, ttl_sec=body.ttl_sec)
        if not r.get("ok"):
            raise HTTPException(409, r.get("error") or "locked")
        return r
    except KeyError:
        raise HTTPException(404, "profile not found")

@router.post("/profiles/{profile_id}/unlock")
def unlock(profile_id: str) -> dict[str, Any]:
    return lock_svc.unlock(profile_id)
