"""v10 WebSocket job progress broadcaster (poll filesystem jobs)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mozilla_manager.modules import jobs_svc

router = APIRouter()


@router.websocket("/ws/jobs")
async def ws_jobs(ws: WebSocket) -> None:
    await ws.accept()
    last: dict[str, Any] = {}
    try:
        while True:
            try:
                rows = jobs_svc.list_jobs(limit=30)
                # compact payload
                payload = {
                    "type": "jobs",
                    "items": [
                        {
                            "id": r.get("id"),
                            "kind": r.get("kind"),
                            "status": r.get("status"),
                            "ok": r.get("ok"),
                            "summary": r.get("summary"),
                            "progress": r.get("progress"),
                        }
                        for r in rows
                    ],
                }
                sig = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                if sig != last.get("sig"):
                    await ws.send_json(payload)
                    last["sig"] = sig
            except Exception as e:
                await ws.send_json({"type": "error", "error": str(e)})
            # allow client ping messages without blocking long
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                raise
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass


@router.websocket("/ws/jobs/{job_id}")
async def ws_job_one(ws: WebSocket, job_id: str) -> None:
    await ws.accept()
    last = ""
    try:
        while True:
            try:
                j = jobs_svc.get_job(job_id)
                payload = {
                    "type": "job",
                    "id": job_id,
                    "status": j.get("status"),
                    "ok": j.get("ok"),
                    "summary": j.get("summary"),
                    "progress": j.get("progress"),
                    "error": j.get("error"),
                }
                sig = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                if sig != last:
                    await ws.send_json(payload)
                    last = sig
                    if j.get("status") in ("done", "error"):
                        await asyncio.sleep(0.5)
                        break
            except KeyError:
                await ws.send_json({"type": "error", "error": "not found", "id": job_id})
                break
            except Exception as e:
                await ws.send_json({"type": "error", "error": str(e)})
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                raise
            await asyncio.sleep(0.4)
    except WebSocketDisconnect:
        return
