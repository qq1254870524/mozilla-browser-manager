from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from mozilla_manager.modules import failover as fo

router = APIRouter()


class SwitchIn(BaseModel):
    node_name: str | None = None
    node: str | None = None  # alias for UI/CLI convenience
    rebind_env: bool = True
    # when both node fields empty: pick next same-country candidate automatically
    auto: bool = True

    def resolved_node(self) -> str:
        return (self.node_name or self.node or "").strip()


class AutoIn(BaseModel):
    check_ip: bool = True
    rebind_env: bool = True


@router.get("/profiles/{profile_id}/candidates")
def candidates(profile_id: str, country: str | None = None) -> dict[str, Any]:
    try:
        nodes = fo.candidate_nodes(profile_id, country=country)
        return {"profile_id": profile_id, "count": len(nodes), "nodes": nodes}
    except KeyError:
        raise HTTPException(404, "profile not found")


@router.post("/profiles/{profile_id}/switch")
def switch(profile_id: str, body: SwitchIn | None = None) -> dict[str, Any]:
    body = body or SwitchIn()
    try:
        node = body.resolved_node()
        if not node:
            if not body.auto:
                raise HTTPException(400, "node_name or node required (or auto=true)")
            cands = fo.candidate_nodes(profile_id)
            if not cands:
                raise HTTPException(400, "no candidate nodes")
            node = str(cands[0].get("name") or "")
            if not node:
                raise HTTPException(400, "candidate missing name")
        return fo.switch_node_live(profile_id, node, rebind_env=body.rebind_env)
    except HTTPException:
        raise
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/profiles/{profile_id}/auto")
def auto(profile_id: str, body: AutoIn | None = None) -> dict[str, Any]:
    body = body or AutoIn()
    try:
        return fo.auto_failover(profile_id, check_ip=body.check_ip, rebind_env=body.rebind_env)
    except KeyError:
        raise HTTPException(404, "profile not found")
    except Exception as e:
        raise HTTPException(400, str(e))
