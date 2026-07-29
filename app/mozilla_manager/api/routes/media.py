from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from mozilla_manager.modules import media_fake

router = APIRouter()

class MediaIn(BaseModel):
    enable: bool = True
    camera: bool = True
    mic: bool = True
    cam_label: str = ""
    mic_label: str = ""

@router.post("/profiles/{profile_id}")
def set_media(profile_id: str, body: MediaIn) -> dict[str, Any]:
    try:
        return media_fake.set_virtual_media(profile_id, enable=body.enable, camera=body.camera, mic=body.mic, cam_label=body.cam_label, mic_label=body.mic_label)
    except KeyError:
        raise HTTPException(404, "profile not found")
