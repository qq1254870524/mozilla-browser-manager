"""Templates API: country packs, fingerprints, node recommend/bind."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from mozilla_manager.modules import templates as templates_mod

router = APIRouter()


class RecommendIn(BaseModel):
    node_name: str = ""
    node: str = ""  # alias accepted by clients/e2e
    jitter: bool = True

    @model_validator(mode="after")
    def _alias_node(self):
        name = (self.node_name or self.node or "").strip()
        if not name:
            raise ValueError("node_name (or node) is required")
        self.node_name = name
        return self


class BindNodeIn(BaseModel):
    node_name: str = ""
    node: str = ""
    sub: str = "default"
    mihomo_port: int = 0
    auto_port: bool = True
    apply_env: bool = True
    fingerprint_id: str = ""
    jitter: bool = True

    @model_validator(mode="after")
    def _alias_node(self):
        name = (self.node_name or self.node or "").strip()
        if not name:
            raise ValueError("node_name (or node) is required")
        self.node_name = name
        return self


class SetFingerprintIn(BaseModel):
    template_id: str = Field(..., min_length=1)


@router.get("/packs")
def packs() -> list[dict[str, Any]]:
    return templates_mod.packs()


@router.get("/fingerprints")
def fingerprints() -> list[dict[str, Any]]:
    return templates_mod.fingerprints()


@router.post("/recommend-node")
def recommend_node(body: RecommendIn) -> dict[str, Any]:
    return templates_mod.recommend_node(body.node_name, jitter=body.jitter)


@router.get("/detect-country")
def detect_country(node_name: str) -> dict[str, Any]:
    return templates_mod.detect_node_country(node_name)


@router.post("/profiles/{profile_id}/bind-node")
def bind_node(profile_id: str, body: BindNodeIn) -> dict[str, Any]:
    try:
        return templates_mod.bind_node_to_profile(profile_id, **body.model_dump())
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/fingerprint")
def set_fingerprint(profile_id: str, body: SetFingerprintIn) -> dict[str, Any]:
    try:
        return templates_mod.set_fingerprint(profile_id, body.template_id)
    except KeyError:
        raise HTTPException(404, f"profile not found: {profile_id}")
    except Exception as e:
        raise HTTPException(400, str(e))
