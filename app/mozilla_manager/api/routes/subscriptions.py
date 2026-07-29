"""Subscriptions + nodes routes (v5 runtime/nodes)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from mozilla_manager.api.schemas import SubImportIn
from mozilla_manager.modules import subscriptions as subs_mod
from mozilla_manager.network import node_store
from mozilla_manager.paths import RUNTIME_IMPORTS_DIR, ensure_layout, safe_resolve

router = APIRouter()
nodes_router = APIRouter()


class SwitchIn(BaseModel):
    name: str
    update_profiles: bool = False


class ExportIn(BaseModel):
    name: Optional[str] = None
    fmt: str = "zip"  # zip|json|yaml|jsonl


class ImportFileIn(BaseModel):
    path: str
    name: str = "imported"


@router.get("")
def list_subs() -> list[dict[str, Any]]:
    return subs_mod.list_subs()


@router.get("/active")
def active() -> dict[str, Any]:
    return subs_mod.get_active()


@router.get("/runtime")
def runtime() -> dict[str, Any]:
    return subs_mod.runtime_status()


@router.post("/import")
def import_sub(body: SubImportIn) -> dict[str, Any]:
    try:
        return subs_mod.import_sub(
            body.url,
            body.name,
            proxy_url=getattr(body, "proxy_url", None),
            via_node=getattr(body, "via_node", None),
            via_sub=getattr(body, "via_sub", None) or "default",
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/switch")
def switch(body: SwitchIn) -> dict[str, Any]:
    try:
        return subs_mod.switch_sub(body.name, update_profiles=body.update_profiles)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/export")
def export_sub(body: ExportIn | None = None) -> dict[str, Any]:
    body = body or ExportIn()
    try:
        return subs_mod.export_sub(body.name, fmt=body.fmt)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/import-file")
def import_file(body: ImportFileIn) -> dict[str, Any]:
    try:
        return subs_mod.import_nodes_file(body.path, name=body.name)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/import-upload")
async def import_upload(
    file: UploadFile = File(...),
    name: str = Form(""),
) -> dict[str, Any]:
    """Browser file-picker upload → runtime/nodes/imports/ → import as subscription."""
    ensure_layout()
    raw_name = (file.filename or "upload.bin").strip() or "upload.bin"
    # keep extension, sanitize basename
    base = Path(raw_name).name
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", base)
    if not base or base in {".", ".."}:
        base = "upload.bin"
    stem = Path(base).stem
    sub_name = node_store._safe_name(name.strip() or stem or "imported")
    dest_dir = safe_resolve(RUNTIME_IMPORTS_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = safe_resolve(dest_dir / base)
    # avoid clobber: unique suffix
    if dest.exists():
        i = 1
        while True:
            cand = dest_dir / f"{Path(base).stem}_{i}{Path(base).suffix}"
            if not cand.exists():
                dest = safe_resolve(cand)
                break
            i += 1
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    dest.write_bytes(data)
    try:
        meta = subs_mod.import_nodes_file(str(dest), name=sub_name)
    except Exception as e:
        raise HTTPException(400, str(e))
    if isinstance(meta, dict):
        meta = dict(meta)
        try:
            from mozilla_manager.paths import ROOT

            meta["uploaded_path"] = str(dest.relative_to(ROOT))
        except Exception:
            meta["uploaded_path"] = str(dest)
        meta.setdefault("name", sub_name)
    return meta


@router.post("/refresh")
def refresh(name: str = "default") -> dict[str, Any]:
    try:
        return subs_mod.refresh_sub(name)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/refresh-due")
def refresh_due(force: bool = False) -> list[dict[str, Any]]:
    return subs_mod.refresh_due(force=force)


@router.delete("/{name}")
def delete_sub(name: str) -> dict[str, Any]:
    try:
        return subs_mod.delete_sub(name)
    except KeyError:
        raise HTTPException(404, f"subscription not found: {name}")
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{name}/delete")
def delete_sub_post(name: str) -> dict[str, Any]:
    """POST alias for clients that cannot send DELETE easily."""
    return delete_sub(name)


@nodes_router.get("")
def list_nodes(sub: str | None = None, full: bool = False) -> list[dict[str, Any]]:
    name = sub or subs_mod.get_active().get("active") or "default"
    if full:
        return subs_mod.list_sub_nodes_full(name)
    return subs_mod.list_sub_nodes(name)
