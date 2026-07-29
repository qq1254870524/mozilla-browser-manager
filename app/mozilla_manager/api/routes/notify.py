from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from mozilla_manager.modules import notify_svc

router = APIRouter()

class ReadIn(BaseModel):
    ids: list[str] = Field(default_factory=list)
    all: bool = False

class PushIn(BaseModel):
    kind: str = "custom"
    title: str
    level: str = "info"
    profile_id: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)

@router.get("")
def list_notices(limit: int = 50, unread_only: bool = False) -> dict[str, Any]:
    return notify_svc.list_notices(limit=limit, unread_only=unread_only)

@router.post("/read")
def mark_read(body: ReadIn) -> dict[str, Any]:
    return notify_svc.mark_read(body.ids or None, all_=body.all)

@router.post("/clear")
def clear(read_only: bool = True) -> dict[str, Any]:
    return notify_svc.clear(read_only=read_only)

@router.post("/push")
def push(body: PushIn) -> dict[str, Any]:
    return notify_svc.push(body.kind, body.title, level=body.level, profile_id=body.profile_id, detail=body.detail)
