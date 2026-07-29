from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from mozilla_manager.network.diagnose import diagnose_profile

router = APIRouter()

@router.post("/profiles/{profile_id}")
def diagnose(profile_id: str, samples: int = 4) -> dict[str, Any]:
    try:
        return diagnose_profile(profile_id, samples=samples)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))
