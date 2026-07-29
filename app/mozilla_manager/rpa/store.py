from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import RPA_WORKFLOWS_DIR, ensure_layout, safe_resolve


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "wf").strip()) or "wf"


def list_workflows() -> list[dict[str, Any]]:
    ensure_layout()
    out = []
    for f in sorted(RPA_WORKFLOWS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": data.get("id") or f.stem,
                    "name": data.get("name") or f.stem,
                    "steps": len(data.get("steps") or []),
                    "updated_at": data.get("updated_at"),
                    "profile_id": data.get("profile_id"),
                    "tags": data.get("tags") or [],
                }
            )
        except Exception as e:
            out.append({"id": f.stem, "error": str(e)})
    return out


def load_workflow(wf_id: str) -> dict[str, Any]:
    path = safe_resolve(RPA_WORKFLOWS_DIR / f"{_safe(wf_id)}.json")
    if not path.exists():
        raise FileNotFoundError(f"workflow not found: {wf_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_workflow(data: dict[str, Any]) -> dict[str, Any]:
    ensure_layout()
    wf_id = _safe(str(data.get("id") or data.get("name") or "wf"))
    steps = data.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")
    # normalize steps
    norm = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            raise ValueError(f"step {i} must be object")
        action = str(s.get("action") or s.get("type") or "").lower()
        if not action:
            raise ValueError(f"step {i} missing action")
        norm.append({**s, "action": action, "index": i})
    doc = {
        "id": wf_id,
        "name": data.get("name") or wf_id,
        "profile_id": data.get("profile_id"),
        "tags": data.get("tags") or [],
        "steps": norm,
        "created_at": data.get("created_at") or _now(),
        "updated_at": _now(),
        "version": 7,
        "redacted": False,
    }
    path = safe_resolve(RPA_WORKFLOWS_DIR / f"{wf_id}.json")
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def delete_workflow(wf_id: str) -> dict[str, Any]:
    path = safe_resolve(RPA_WORKFLOWS_DIR / f"{_safe(wf_id)}.json")
    if path.exists():
        path.unlink()
        return {"ok": True, "deleted": wf_id}
    return {"ok": False, "error": "not found"}
