from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from mozilla_manager.modules import backup_svc

router = APIRouter()

class SchedIn(BaseModel):
    every_hours: float = 24.0
    enabled: bool = True
    keep: int = 10

class BackupIn(BaseModel):
    label: str = ""

@router.get("")
def list_backups() -> dict[str, Any]:
    return backup_svc.list_backups()

@router.post("")
def create(body: BackupIn | None = None) -> dict[str, Any]:
    body = body or BackupIn()
    try:
        return backup_svc.create_backup(label=body.label)
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/schedule")
def schedule(body: SchedIn) -> dict[str, Any]:
    return backup_svc.configure_schedule(every_hours=body.every_hours, enabled=body.enabled, keep=body.keep)
