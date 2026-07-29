"""Doctor routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from mozilla_manager.modules import doctor_svc

router = APIRouter()


@router.get("")
def doctor() -> dict[str, Any]:
    return doctor_svc.run()
