from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mozilla_manager.modules import fleet_svc, machine_svc

router = APIRouter()

class ExportIn(BaseModel):
    profile_ids: list[str] = Field(default_factory=list)
    include_profile_data: bool = False
    include_nodes: bool = True
    include_rpa: bool = True
    include_totp: bool = True
    include_watchdogs: bool = True
    name: str = ""

class ImportIn(BaseModel):
    path: str
    import_totp: bool = False
    import_profiles_data: bool = True
    import_nodes: bool = True
    import_rpa: bool = True
    import_watchdogs: bool = True

class MachineNameIn(BaseModel):
    name: str

@router.get("/machine")
def machine() -> dict[str, Any]:
    return machine_svc.get_machine()

@router.post("/machine/name")
def machine_name(body: MachineNameIn) -> dict[str, Any]:
    return machine_svc.set_name(body.name)

@router.get("/packs")
def packs() -> dict[str, Any]:
    return fleet_svc.list_fleet_packs()

@router.post("/export")
def export_pack(body: ExportIn | None = None) -> dict[str, Any]:
    body = body or ExportIn()
    try:
        return fleet_svc.export_fleet_pack(
            include_profiles=body.profile_ids or None,
            include_profile_data=body.include_profile_data or bool(body.profile_ids),
            include_nodes=body.include_nodes,
            include_rpa=body.include_rpa,
            include_totp=body.include_totp,
            include_watchdogs=body.include_watchdogs,
            name=body.name,
        )
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/import")
def import_pack(body: ImportIn) -> dict[str, Any]:
    try:
        return fleet_svc.import_fleet_pack(
            body.path,
            import_totp=body.import_totp,
            import_profiles_data=body.import_profiles_data,
            import_nodes=body.import_nodes,
            import_rpa=body.import_rpa,
            import_watchdogs=body.import_watchdogs,
        )
    except Exception as e:
        raise HTTPException(400, str(e))
