from __future__ import annotations
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from mozilla_manager.modules import totp_svc

router = APIRouter()

@router.get("")
def list_root(profile_id: str | None = None, secrets: bool = False) -> dict[str, Any]:
    """Alias of GET /accounts for clients that hit /api/totp."""
    return {"ok": True, "items": totp_svc.list_accounts(profile_id=profile_id, include_secret=secrets)}

class AddIn(BaseModel):
    name: str = ""
    secret: str = ""
    otpauth: str = ""
    issuer: str = ""
    profile_id: str = ""
    site: str = ""

@router.get("/accounts")
def list_acc(profile_id: str | None = None, secrets: bool = False) -> list[dict[str, Any]]:
    return totp_svc.list_accounts(profile_id=profile_id, include_secret=secrets)

@router.post("/accounts")
def add_acc(body: AddIn) -> dict[str, Any]:
    try:
        return totp_svc.add_account(name=body.name, secret=body.secret, otpauth=body.otpauth, issuer=body.issuer, profile_id=body.profile_id, site=body.site)
    except Exception as e:
        raise HTTPException(400, str(e))

@router.delete("/accounts/{account_id}")
def del_acc(account_id: str) -> dict[str, Any]:
    return totp_svc.remove_account(account_id)

@router.get("/accounts/{account_id}/code")
def code(account_id: str) -> dict[str, Any]:
    try:
        return totp_svc.code_for(account_id)
    except KeyError:
        raise HTTPException(404, "not found")

@router.get("/accounts/{account_id}/fill")
def fill(account_id: str, selector: str = "") -> dict[str, Any]:
    try:
        if selector:
            return totp_svc.fill_script(account_id, selector=selector)
        return totp_svc.fill_script(account_id)
    except KeyError:
        raise HTTPException(404, "not found")
