from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mozilla_manager import db
from mozilla_manager.store import ProfileStore

router = APIRouter()


class PrivacyIn(BaseModel):
    webrtc_mode: str = "disable"  # off|disable|spoof
    doh_mode: str = "secure"  # off|secure|automatic
    doh_template: Optional[str] = "https://cloudflare-dns.com/dns-query"
    doh_servers: Optional[list[str]] = None
    doh_force: bool = True
    geo_match_strict: Optional[bool] = None


@router.get("/profiles/{profile_id}")
def get_privacy(profile_id: str) -> dict[str, Any]:
    try:
        prof = ProfileStore().get(profile_id)
    except KeyError:
        raise HTTPException(404, "profile not found")
    meta = prof.meta or {}
    return {
        "profile_id": profile_id,
        "webrtc_mode": meta.get("webrtc_mode", "disable"),
        "doh_mode": meta.get("doh_mode", "secure"),
        "doh_template": meta.get("doh_template") or meta.get("doh_url") or "https://cloudflare-dns.com/dns-query",
        "doh_servers": meta.get("doh_servers"),
        "doh_force": meta.get("doh_force", True),
        "geo_match_strict": bool(meta.get("geo_match_strict") or meta.get("require_geo_match")),
        "tls_profile": meta.get("tls_profile"),
        "stealth_bundle_id": meta.get("stealth_bundle_id"),
    }


@router.post("/profiles/{profile_id}")
def set_privacy(profile_id: str, body: PrivacyIn) -> dict[str, Any]:
    store = ProfileStore()
    try:
        prof = store.get(profile_id)
    except KeyError:
        raise HTTPException(404, "profile not found")
    meta = dict(prof.meta)
    meta["webrtc_mode"] = body.webrtc_mode
    meta["doh_mode"] = body.doh_mode
    meta["doh_template"] = body.doh_template
    meta["doh_force"] = body.doh_force
    if body.doh_servers is not None:
        meta["doh_servers"] = list(body.doh_servers)
    if body.geo_match_strict is not None:
        meta["geo_match_strict"] = bool(body.geo_match_strict)
    updated = store.update(profile_id, meta=meta)
    db.audit("privacy_set", profile_id, body.model_dump())
    return {"ok": True, "profile_id": profile_id, "privacy": body.model_dump(), "meta_keys": list(updated.meta.keys())}
