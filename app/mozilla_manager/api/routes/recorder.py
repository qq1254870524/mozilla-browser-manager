from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mozilla_manager.rpa import recorder

router = APIRouter()

class StopIn(BaseModel):
    save_workflow: bool = True
    name: str = ""
    workflow_id: str = ""

@router.post("/profiles/{profile_id}/start")
def start(profile_id: str) -> dict[str, Any]:
    try:
        return recorder.start_recording(profile_id)
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/profiles/{profile_id}/poll")
def poll(profile_id: str) -> dict[str, Any]:
    try:
        return recorder.poll_events(profile_id)
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/profiles/{profile_id}/stop")
def stop(profile_id: str, body: StopIn | None = None) -> dict[str, Any]:
    body = body or StopIn()
    try:
        return recorder.stop_recording(profile_id, save_workflow=body.save_workflow, name=body.name, workflow_id=body.workflow_id)
    except Exception as e:
        raise HTTPException(400, str(e))

@router.get("/profiles/{profile_id}")
def status(profile_id: str) -> dict[str, Any]:
    return recorder.status(profile_id)

@router.get("/profiles/{profile_id}/timeline")
def timeline(profile_id: str) -> dict[str, Any]:
    return recorder.timeline(profile_id)
