from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mozilla_manager.modules import extensions as ext_mod

router = APIRouter()


class SetExtIn(BaseModel):
    extensions: list[str] = Field(default_factory=list)
    ids: list[str] = Field(default_factory=list)  # alias used by UI/CLI


class InstallIn(BaseModel):
    src: str
    ext_id: str | None = None


@router.get("")
def list_ext() -> list[dict[str, Any]]:
    return ext_mod.list_extensions()


@router.get("/profiles/{profile_id}")
def profile_ext(profile_id: str) -> dict[str, Any]:
    try:
        return {"profile_id": profile_id, "extensions": ext_mod.profile_extensions(profile_id)}
    except KeyError:
        raise HTTPException(404, "profile not found")


@router.post("/profiles/{profile_id}")
def set_ext(profile_id: str, body: SetExtIn) -> dict[str, Any]:
    try:
        ext_ids = list(body.extensions or []) or list(body.ids or [])
        return ext_mod.set_profile_extensions(profile_id, ext_ids)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/install")
def install(body: InstallIn) -> dict[str, Any]:
    try:
        return ext_mod.install_extension_dir(body.src, body.ext_id)
    except Exception as e:
        raise HTTPException(400, str(e))
