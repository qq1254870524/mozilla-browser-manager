from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from mozilla_manager.modules import tags_svc

router = APIRouter()

class TagsIn(BaseModel):
    tags: list[str] = Field(default_factory=list)

@router.get("")
def all_tags() -> dict[str, Any]:
    return tags_svc.list_all_tags()

@router.get("/filter/{tag}")
def filter_tag(tag: str) -> list[dict[str, Any]]:
    return tags_svc.filter_by_tag(tag)

@router.get("/profiles/{profile_id}")
def get_tags(profile_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "profile_id": profile_id, "tags": tags_svc.get_tags(profile_id)}
    except KeyError:
        raise HTTPException(404, "profile not found")

@router.put("/profiles/{profile_id}")
@router.post("/profiles/{profile_id}")
@router.post("/profiles/{profile_id}/set")
def set_tags(profile_id: str, body: TagsIn) -> dict[str, Any]:
    """Set full tag list. POST aliases for clients that avoid PUT."""
    try:
        return tags_svc.set_tags(profile_id, body.tags)
    except KeyError:
        raise HTTPException(404, "profile not found")

@router.post("/profiles/{profile_id}/add")
def add_tags(profile_id: str, body: TagsIn) -> dict[str, Any]:
    try:
        return tags_svc.add_tags(profile_id, body.tags)
    except KeyError:
        raise HTTPException(404, "profile not found")

@router.post("/profiles/{profile_id}/remove")
def remove_tags(profile_id: str, body: TagsIn) -> dict[str, Any]:
    try:
        return tags_svc.remove_tags(profile_id, body.tags)
    except KeyError:
        raise HTTPException(404, "profile not found")
