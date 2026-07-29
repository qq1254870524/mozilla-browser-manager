"""Session backup / restore API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mozilla_manager.modules import sessions as sessions_mod

router = APIRouter()


class BackupIn(BaseModel):
    label: str = ""
    include_user_data: bool = False


class RestoreIn(BaseModel):
    ts: str
    restore_user_data: bool = True


@router.get("")
def list_all(profile_id: str | None = None) -> list[dict[str, Any]]:
    return sessions_mod.list_sessions(profile_id)


@router.get("/{profile_id}")
def list_for_profile(profile_id: str) -> list[dict[str, Any]]:
    return sessions_mod.list_sessions(profile_id)


@router.post("/{profile_id}/backup")
def backup(profile_id: str, body: BackupIn | None = None) -> dict[str, Any]:
    body = body or BackupIn()
    try:
        return sessions_mod.backup_session(
            profile_id, label=body.label, include_user_data=body.include_user_data
        )
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{profile_id}/restore")
def restore(profile_id: str, body: RestoreIn) -> dict[str, Any]:
    try:
        return sessions_mod.restore_session(
            profile_id, body.ts, restore_user_data=body.restore_user_data
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")
    except Exception as e:
        raise HTTPException(400, str(e))
