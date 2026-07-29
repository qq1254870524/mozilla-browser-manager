from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mozilla_manager.modules import turnstile as ts

router = APIRouter()


class SolveIn(BaseModel):
    url: str
    headless: bool = False
    timeout: float = 60.0
    harvest: bool = True


@router.get("/vendor")
def vendor() -> dict[str, Any]:
    return ts.ensure_vendor()


@router.post("/profiles/{profile_id}/solve")
def solve(profile_id: str, body: SolveIn) -> dict[str, Any]:
    try:
        return ts.solve_in_profile(
            profile_id,
            body.url,
            headless=body.headless,
            timeout=body.timeout,
            harvest=body.harvest,
        )
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))
