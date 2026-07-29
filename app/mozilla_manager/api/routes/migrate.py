"""Migrate a URL/tab into another profile's remembered tabs (and optional open)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mozilla_manager import db
from mozilla_manager.store import ProfileStore

router = APIRouter()


class MigrateIn(BaseModel):
    url: str
    target_profile_id: str
    open_now: bool = False


@router.post("")
def migrate(body: MigrateIn) -> dict[str, Any]:
    store = ProfileStore()
    try:
        target = store.get(body.target_profile_id)
    except KeyError:
        raise HTTPException(404, f"target not found: {body.target_profile_id}")
    meta = dict(target.meta)
    tabs = list(meta.get("tabs") or [])
    if body.url not in tabs:
        tabs.append(body.url)
    meta["tabs"] = tabs
    store.update(body.target_profile_id, meta=meta)
    db.audit("tab_migrate", body.target_profile_id, {"url": body.url})
    opened = None
    if body.open_now:
        try:
            from mozilla_manager.engines import chromium as chromium_mod

            run = getattr(chromium_mod, "_RUNS", {}).get(body.target_profile_id)
            if run and run.get("context"):
                page = run["context"].new_page()
                page.goto(body.url, wait_until="domcontentloaded")
                opened = True
            else:
                opened = False
        except Exception as e:
            opened = str(e)
    return {"ok": True, "target": body.target_profile_id, "tabs": tabs, "opened": opened}
