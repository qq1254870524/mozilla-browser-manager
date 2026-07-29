from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from mozilla_manager.modules import jobs_svc

router = APIRouter()

@router.get("")
def list_jobs(limit: int = 50, kind: Optional[str] = None) -> list[dict[str, Any]]:
    return jobs_svc.list_jobs(limit=limit, kind=kind)

@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return jobs_svc.get_job(job_id)
    except KeyError:
        raise HTTPException(404, "job not found")
