from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter
from mozilla_manager import db

router = APIRouter()

@router.get("")
def list_audit(limit: int = 100, profile_id: Optional[str] = None) -> list[dict[str, Any]]:
    return db.list_audit(limit=limit, profile_id=profile_id)
