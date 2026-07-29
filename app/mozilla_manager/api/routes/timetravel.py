from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mozilla_manager.modules import timetravel as tt

router = APIRouter()


class CreateIn(BaseModel):
    label: str = ""
    include_user_data: bool = False


class RollbackIn(BaseModel):
    ts: str
    restore_user_data: bool = False


@router.get("/profiles/{profile_id}")
def list_points(profile_id: str) -> list[dict[str, Any]]:
    return tt.list_points(profile_id)


@router.post("/profiles/{profile_id}")
def create_point(profile_id: str, body: CreateIn | None = None) -> dict[str, Any]:
    body = body or CreateIn()
    try:
        return tt.create_restore_point(profile_id, label=body.label, include_user_data=body.include_user_data)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/rollback")
def rollback(profile_id: str, body: RollbackIn) -> dict[str, Any]:
    try:
        return tt.rollback(profile_id, body.ts, restore_user_data=body.restore_user_data)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))
