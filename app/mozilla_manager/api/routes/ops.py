from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mozilla_manager.modules import ops_svc

router = APIRouter()

class BulkDiagIn(BaseModel):
    profile_ids: list[str] = Field(default_factory=list)
    samples: int = 3
    async_job: bool = True

@router.get("/dashboard")
def dashboard() -> dict[str, Any]:
    return ops_svc.dashboard()

@router.get("/history")
def history(limit: int = 30) -> dict[str, Any]:
    return ops_svc.history(limit=limit)

@router.get("/profiles/{profile_id}/summary")
def summary(profile_id: str) -> dict[str, Any]:
    try:
        return ops_svc.profile_summary(profile_id)
    except KeyError:
        raise HTTPException(404, "profile not found")

@router.post("/bulk-diagnose")
def bulk_diagnose(body: BulkDiagIn | None = None) -> dict[str, Any]:
    body = body or BulkDiagIn()
    try:
        return ops_svc.bulk_diagnose(body.profile_ids or None, samples=body.samples, async_job=body.async_job)
    except Exception as e:
        raise HTTPException(400, str(e))
