from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mozilla_manager.modules import cookies as cookies_mod

router = APIRouter()


class ImportIn(BaseModel):
    payload: Any = None  # str JSON/Base64 or object/list
    cookies: Any = None  # alias used by clients
    merge: bool = True

    def resolved_payload(self) -> Any:
        if self.payload is not None:
            return self.payload
        if self.cookies is not None:
            return self.cookies
        raise ValueError("payload or cookies required")


class ExportIn(BaseModel):
    fmt: str = "json"  # json|base64
    prefer_live: bool = True


@router.post("/profiles/{profile_id}/import")
def import_cookies(profile_id: str, body: ImportIn) -> dict[str, Any]:
    try:
        return cookies_mod.import_cookies(profile_id, body.resolved_payload(), merge=body.merge)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/export")
def export_cookies(profile_id: str, body: ExportIn | None = None) -> dict[str, Any]:
    body = body or ExportIn()
    try:
        return cookies_mod.export_cookies(profile_id, fmt=body.fmt, prefer_live=body.prefer_live)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))
