"""v6 stealth / TLS / net-quality API."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mozilla_manager.modules import stealth_svc

router = APIRouter()


class TlsIn(BaseModel):
    tls_profile: str


class DohIn(BaseModel):
    mode: str = "secure"
    template: Optional[str] = "https://cloudflare-dns.com/dns-query"
    servers: Optional[list[str]] = None
    force: bool = True


class RegenIn(BaseModel):
    tls_profile: Optional[str] = None


@router.get("/tls-profiles")
def tls_profiles() -> list[dict[str, Any]]:
    return stealth_svc.tls_profiles()


@router.get("/entropy")
def entropy(profile_id: str | None = None) -> dict[str, Any]:
    return stealth_svc.entropy_report(profile_id)


@router.get("/collision")
def collision(limit: int = 30) -> dict[str, Any]:
    return stealth_svc.collision_report(limit=limit)


@router.get("/profiles/{profile_id}")
def get_bundle(profile_id: str, full: bool = False) -> dict[str, Any]:
    try:
        r = stealth_svc.get_bundle(profile_id, ensure=True)
    except KeyError:
        raise HTTPException(404, "profile not found")
    if not full:
        r.pop("bundle", None)
    return r


@router.post("/profiles/{profile_id}/regenerate")
def regen(profile_id: str, body: RegenIn | None = None) -> dict[str, Any]:
    body = body or RegenIn()
    try:
        return stealth_svc.regenerate(profile_id, tls_profile=body.tls_profile)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/tls")
def set_tls(profile_id: str, body: TlsIn) -> dict[str, Any]:
    try:
        return stealth_svc.set_tls(profile_id, body.tls_profile)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/doh")
def set_doh(profile_id: str, body: DohIn) -> dict[str, Any]:
    try:
        return stealth_svc.set_doh(
            profile_id,
            mode=body.mode,
            template=body.template,
            servers=body.servers,
            force=body.force,
        )
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/net-quality")
def net_quality(profile_id: str, samples: int = 5) -> dict[str, Any]:
    try:
        return stealth_svc.net_quality_for_profile(profile_id, samples=samples)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/probe")
def probe(profile_id: str, fetch_egress: bool = True) -> dict[str, Any]:
    """Live in-page camouflage probe (webdriver/tz/locale/ua/webgl/automation...)."""
    try:
        return stealth_svc.live_probe(profile_id, fetch_egress=fetch_egress)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/restore-max-stealth")
def restore_max_stealth() -> dict[str, Any]:
    """一键恢复全部环境为最强反检测默认。"""
    from mozilla_manager.modules.profiles import restore_max_stealth_all
    return restore_max_stealth_all()

