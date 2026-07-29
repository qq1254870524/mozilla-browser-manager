"""Groups routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from mozilla_manager.modules import groups as groups_mod

router = APIRouter()


@router.get("")
def list_groups() -> list[dict[str, Any]]:
    return groups_mod.list_groups()
