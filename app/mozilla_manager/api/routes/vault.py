from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mozilla_manager.modules import vault_svc

router = APIRouter()

class PutIn(BaseModel):
    name: str
    value: str
    meta: dict[str, Any] = Field(default_factory=dict)

@router.get("")
def list_secrets() -> dict[str, Any]:
    return vault_svc.list_secrets()

@router.get("/{name}")
def get_secret(name: str, reveal: bool = False) -> dict[str, Any]:
    try:
        return vault_svc.get(name, reveal=reveal)
    except KeyError:
        raise HTTPException(404, "secret not found")
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("")
def put_secret(body: PutIn) -> dict[str, Any]:
    return vault_svc.put(body.name, body.value, meta=body.meta)

@router.delete("/{name}")
def del_secret(name: str) -> dict[str, Any]:
    return vault_svc.delete(name)
