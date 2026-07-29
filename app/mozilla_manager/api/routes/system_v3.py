"""Extra system routes for v3: consistency, gc, matrix, audit, restore session."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from mozilla_manager import db
from mozilla_manager.engines.matrix import list_matrix, recommend_combo
from mozilla_manager.modules import profiles as profiles_mod
from mozilla_manager.modules import system as system_mod
from mozilla_manager.modules import subscriptions as subs_mod

router = APIRouter()


class GcIn(BaseModel):
    max_age_hours: float = 24.0
    dry_run: bool = False


class RestoreIn(BaseModel):
    headless: bool = False
    open_check: bool = False


@router.get("/consistency")
def consistency(repair: bool = False) -> dict[str, Any]:
    return system_mod.consistency(repair=repair)


@router.post("/gc")
def gc(body: GcIn | None = None) -> dict[str, Any]:
    body = body or GcIn()
    return system_mod.gc(max_age_hours=body.max_age_hours, dry_run=body.dry_run)


@router.get("/sandbox")
def sandbox() -> dict[str, Any]:
    return system_mod.sandbox_status()


@router.get("/matrix")
def matrix() -> list[dict[str, Any]]:
    return list_matrix()


@router.get("/matrix/recommend")
def matrix_rec(stealth: bool = True, firefox: bool = False) -> dict[str, Any]:
    return recommend_combo(stealth=stealth, firefox=firefox)


@router.get("/audit")
def audit(limit: int = 100, profile_id: str | None = None) -> list[dict[str, Any]]:
    return db.list_audit(limit=limit, profile_id=profile_id)


@router.post("/restore-last-session")
def restore_last(body: RestoreIn | None = None) -> dict[str, Any]:
    body = body or RestoreIn()
    return profiles_mod.restore_last_session(headless=body.headless, open_check=body.open_check)


@router.post("/save-last-session")
def save_last() -> dict[str, Any]:
    return profiles_mod.save_last_session_now()


@router.post("/subscriptions/refresh")
def sub_refresh(name: str = "default") -> dict[str, Any]:
    return subs_mod.refresh_sub(name)


@router.post("/subscriptions/refresh-due")
def sub_refresh_due(force: bool = False) -> list[dict[str, Any]]:
    return subs_mod.refresh_due(force=force)


@router.get("/compliance")
def compliance_audit() -> dict:
    from mozilla_manager.modules.compliance import audit
    return audit()


@router.post("/backfill-meta")
def backfill_meta(force_max_stealth: bool = False) -> dict:
    from mozilla_manager.modules.profiles import backfill_all_meta_defaults
    return backfill_all_meta_defaults(force_max_stealth=force_max_stealth)


@router.post("/restore-max-stealth")
def restore_max_stealth() -> dict:
    """恢复全部配置为最强反检测默认（捆绑 Chromium + 锁定视口 + stealth_v6 + humanize）。"""
    from mozilla_manager.modules.profiles import restore_max_stealth_all
    return restore_max_stealth_all()
