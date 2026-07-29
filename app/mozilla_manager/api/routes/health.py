from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mozilla_manager.modules import health as health_mod

router = APIRouter()


class RebindIn(BaseModel):
    only_if_mismatch: bool = True


class IpRecommendIn(BaseModel):
    proxy_url: str | None = None


@router.get("/profiles/{profile_id}/egress")
def egress(profile_id: str) -> dict[str, Any]:
    try:
        return health_mod.check_egress(profile_id)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/rebind")
def rebind(profile_id: str, body: RebindIn | None = None) -> dict[str, Any]:
    body = body or RebindIn()
    try:
        return health_mod.rebind_from_egress(profile_id, only_if_mismatch=body.only_if_mismatch)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/recommend-ip")
def recommend_ip(body: IpRecommendIn | None = None) -> dict[str, Any]:
    body = body or IpRecommendIn()
    return health_mod.recommend_from_ip(body.proxy_url)


class AutoRebindIn(BaseModel):
    enabled: bool = True


@router.get("/profiles/{profile_id}/auto-rebind")
def auto_rebind_status(profile_id: str) -> dict[str, Any]:
    try:
        from mozilla_manager.store import ProfileStore
        prof = ProfileStore().get(profile_id)
        return {
            "ok": True,
            "profile_id": profile_id,
            "auto_rebind_on_launch": health_mod.auto_rebind_enabled(prof),
            "last_launch_rebind": (prof.meta or {}).get("last_launch_rebind"),
            "last_egress": (prof.meta or {}).get("last_egress"),
        }
    except KeyError:
        raise HTTPException(404, "profile not found")


@router.post("/profiles/{profile_id}/auto-rebind")
def auto_rebind(profile_id: str, body: AutoRebindIn | None = None) -> dict[str, Any]:
    body = body or AutoRebindIn()
    try:
        return health_mod.set_auto_rebind(profile_id, enabled=body.enabled)
    except KeyError:
        raise HTTPException(404, "profile not found")


@router.post("/profiles/{profile_id}/rebind-env")
def rebind_env(profile_id: str) -> dict[str, Any]:
    """Always refresh tz/locale/geo from current egress IP."""
    try:
        return health_mod.rebind_tz_locale_geo(profile_id, only_if_mismatch=False)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))
