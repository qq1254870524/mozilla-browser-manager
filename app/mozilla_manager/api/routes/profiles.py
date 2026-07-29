"""Profiles routes — env CRUD + lifecycle."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mozilla_manager.api.schemas import (
    BindCountryIn,
    CreateProfileIn,
    LaunchIn,
    SetProxyIn,
    UpdateProfileIn,
)
from mozilla_manager.modules import profiles as profiles_mod

router = APIRouter()
running_router = APIRouter()


@router.get("")
def list_profiles() -> list[dict[str, Any]]:
    return profiles_mod.list_profiles()


@router.get("/{profile_id}")
def get_profile(profile_id: str) -> dict[str, Any]:
    try:
        return profiles_mod.get_profile(profile_id)
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")


@router.post("")
def create_profile(body: CreateProfileIn) -> dict[str, Any]:
    try:
        return profiles_mod.create_profile(**body.model_dump())
    except Exception as e:
        raise HTTPException(400, str(e))


@router.patch("/{profile_id}")
def update_profile(profile_id: str, body: UpdateProfileIn) -> dict[str, Any]:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return profiles_mod.update_profile(profile_id, **patch)
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/{profile_id}")
def delete_profile(profile_id: str, wipe: bool = True) -> dict[str, Any]:
    try:
        profiles_mod.delete_profile(profile_id, wipe=wipe)
        return {"ok": True, "id": profile_id}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{profile_id}/proxy")
def set_proxy(profile_id: str, body: SetProxyIn) -> dict[str, Any]:
    try:
        payload = body.model_dump()
        # normalize aliases: API historically used `node`, UI/scripts send `node_name`
        payload["node"] = body.resolved_node()
        payload.pop("node_name", None)
        return profiles_mod.set_proxy(profile_id, **payload)
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")


@router.post("/{profile_id}/bind-country")
def bind_country(profile_id: str, body: BindCountryIn) -> dict[str, Any]:
    try:
        return profiles_mod.bind_country(profile_id, body.country)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{profile_id}/launch")
def launch(profile_id: str, body: LaunchIn | None = None) -> dict[str, Any]:
    body = body or LaunchIn()
    try:
        result = profiles_mod.launch(profile_id, **body.model_dump())
        if not result.get("ok"):
            raise HTTPException(400, result)
        return result
    except HTTPException:
        raise
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{profile_id}/stop")
def stop(profile_id: str) -> dict[str, Any]:
    return profiles_mod.stop(profile_id)


@router.get("/{profile_id}/check")
def check(profile_id: str, require_proxy: bool = False) -> dict[str, Any]:
    try:
        return profiles_mod.check(profile_id, require_proxy=require_proxy)
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")


@router.post("/{profile_id}/export")
def export_zip(profile_id: str) -> dict[str, Any]:
    try:
        return profiles_mod.export_zip(profile_id)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{profile_id}/snapshot")
def snapshot(profile_id: str, label: str = "") -> dict[str, Any]:
    try:
        return profiles_mod.snapshot(profile_id, label=label)
    except Exception as e:
        raise HTTPException(400, str(e))


@running_router.get("")
def running() -> dict[str, Any]:
    return profiles_mod.running()


@router.post("/{profile_id}/export-incremental")
def export_incremental(profile_id: str) -> dict[str, Any]:
    try:
        from mozilla_manager.snapshots import export_profile_zip_incremental
        path = export_profile_zip_incremental(profile_id)
        return {"ok": True, "path": str(path), "incremental": True}
    except Exception as e:
        raise HTTPException(400, str(e))


# ---- extensions alias (canonical under /api/extensions/profiles/{id}) ----
class _ExtIn(BaseModel):
    extensions: list[str] = Field(default_factory=list)
    ids: list[str] = Field(default_factory=list)


@router.get("/{profile_id}/extensions")
def profile_extensions_alias(profile_id: str) -> dict[str, Any]:
    from mozilla_manager.modules import extensions as ext_mod
    try:
        return {"profile_id": profile_id, "extensions": ext_mod.profile_extensions(profile_id)}
    except KeyError:
        raise HTTPException(404, "profile not found")


@router.post("/{profile_id}/extensions")
def set_profile_extensions_alias(profile_id: str, body: _ExtIn) -> dict[str, Any]:
    from mozilla_manager.modules import extensions as ext_mod
    try:
        ext_ids = list(body.extensions or []) or list(body.ids or [])
        return ext_mod.set_profile_extensions(profile_id, ext_ids)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))

