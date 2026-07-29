from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mozilla_manager.modules import batch_svc

router = APIRouter()

class BatchIn(BaseModel):
    country: str
    count: int = 5
    name_prefix: str = ""
    engine: str = "pw_chromium"
    patch: str = "patchright"
    group: str = ""
    auto_port: bool = True
    sub: str = "default"
    seed: Optional[int] = None

@router.post("/create")
def batch_create(body: BatchIn) -> dict[str, Any]:
    try:
        return batch_svc.batch_create(**body.model_dump())
    except Exception as e:
        raise HTTPException(400, str(e))
