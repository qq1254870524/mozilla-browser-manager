"""System routes: health."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from mozilla_manager.modules import system as system_mod

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, Any]:
    return system_mod.health()
