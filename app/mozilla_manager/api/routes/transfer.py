from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from mozilla_manager.modules import transfer_svc

router = APIRouter()

class ImportIn(BaseModel):
    path: str
    new_name: str = ""
    keep_id: bool = False

@router.post("/profiles/{profile_id}/export")
def export_pack(profile_id: str) -> dict[str, Any]:
    try:
        return transfer_svc.export_migrate_pack(profile_id)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/import")
def import_pack(body: ImportIn) -> dict[str, Any]:
    try:
        return transfer_svc.import_migrate_pack(body.path, new_name=body.new_name, keep_id=body.keep_id)
    except Exception as e:
        raise HTTPException(400, str(e))
