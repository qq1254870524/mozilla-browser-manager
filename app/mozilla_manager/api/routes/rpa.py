from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mozilla_manager.rpa import store as wf_store
from mozilla_manager.rpa.runner import run_workflow
from mozilla_manager.rpa import scheduler as sched

router = APIRouter()

class WfIn(BaseModel):
    id: Optional[str] = None
    name: str = "workflow"
    profile_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)

class RunIn(BaseModel):
    profile_id: Optional[str] = None
    headless: bool = True
    stop_on_error: bool = True
    dry_run: bool = False

class SchedIn(BaseModel):
    id: str
    workflow_id: str
    profile_id: str
    every_minutes: Optional[int] = None
    daily_at: Optional[str] = None
    enabled: bool = True
    headless: bool = True

@router.get("/workflows")
def list_wf() -> list[dict[str, Any]]:
    return wf_store.list_workflows()

@router.get("/workflows/{wf_id}")
def get_wf(wf_id: str) -> dict[str, Any]:
    try:
        return wf_store.load_workflow(wf_id)
    except FileNotFoundError:
        raise HTTPException(404, "workflow not found")

@router.post("/workflows")
def save_wf(body: WfIn) -> dict[str, Any]:
    try:
        return wf_store.save_workflow(body.model_dump())
    except Exception as e:
        raise HTTPException(400, str(e))

@router.delete("/workflows/{wf_id}")
def del_wf(wf_id: str) -> dict[str, Any]:
    return wf_store.delete_workflow(wf_id)

@router.post("/workflows/{wf_id}/run")
def run_wf(wf_id: str, body: RunIn | None = None) -> dict[str, Any]:
    body = body or RunIn()
    try:
        return run_workflow(wf_id, profile_id=body.profile_id, headless=body.headless, stop_on_error=body.stop_on_error, dry_run=body.dry_run)
    except Exception as e:
        raise HTTPException(400, str(e))

@router.get("/schedules")
def list_sched() -> list[dict[str, Any]]:
    return sched.list_schedules()

@router.post("/schedules")
def upsert_sched(body: SchedIn) -> dict[str, Any]:
    return sched.upsert_schedule(
        schedule_id=body.id, workflow_id=body.workflow_id, profile_id=body.profile_id,
        every_minutes=body.every_minutes, daily_at=body.daily_at, enabled=body.enabled, headless=body.headless,
    )

@router.delete("/schedules/{schedule_id}")
def del_sched(schedule_id: str) -> dict[str, Any]:
    return sched.remove_schedule(schedule_id)

@router.post("/scheduler/tick")
def tick() -> dict[str, Any]:
    return {"ok": True, "ran": sched.tick_once()}

@router.post("/scheduler/start")
def start() -> dict[str, Any]:
    return sched.start_scheduler()
