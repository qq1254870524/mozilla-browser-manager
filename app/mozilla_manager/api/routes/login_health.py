from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mozilla_manager.modules import login_health as lh

router = APIRouter()


class WatchIn(BaseModel):
    urls: list[str] = Field(default_factory=list)
    interval_hours: float = 24.0


class CheckIn(BaseModel):
    urls: list[str] | None = None
    headless: bool = True


@router.get("/profiles/{profile_id}")
def get_watch(profile_id: str) -> dict[str, Any]:
    try:
        return {"profile_id": profile_id, "watch": lh.get_watch(profile_id)}
    except KeyError:
        raise HTTPException(404, "profile not found")


@router.post("/profiles/{profile_id}/watch")
def set_watch(profile_id: str, body: WatchIn) -> dict[str, Any]:
    try:
        return lh.set_watch_targets(profile_id, body.urls, interval_hours=body.interval_hours)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/check")
def check(profile_id: str, body: CheckIn | None = None) -> dict[str, Any]:
    body = body or CheckIn()
    try:
        return lh.check_login(profile_id, urls=body.urls, headless=body.headless)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/check-due")
def check_due(force: bool = False) -> list[dict[str, Any]]:
    return lh.check_due(force=force)
