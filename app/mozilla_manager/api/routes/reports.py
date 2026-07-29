from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from mozilla_manager.modules import report_svc

router = APIRouter()

@router.get("")
def list_or_latest() -> dict[str, Any]:
    """List existing ops reports (convenience for clients that GET /api/reports)."""
    try:
        from mozilla_manager.modules import report_svc
        if hasattr(report_svc, "list_reports"):
            return report_svc.list_reports()
    except Exception:
        pass
    # fallback: scan data/reports
    try:
        from mozilla_manager.paths import ROOT
        d = ROOT / "data" / "reports"
        items = []
        if d.exists():
            for f in sorted(d.glob("*"), reverse=True)[:50]:
                if f.is_file():
                    items.append({"name": f.name, "path": str(f.relative_to(ROOT)), "bytes": f.stat().st_size})
        return {"ok": True, "items": items}
    except Exception as e:
        return {"ok": False, "error": str(e), "items": []}

@router.post("/ops")
def export_ops() -> dict[str, Any]:
    try:
        return report_svc.export_ops_report()
    except Exception as e:
        raise HTTPException(400, str(e))
