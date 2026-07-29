"""HTTP API package — one router per functional module."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from mozilla_manager.api.routes import (
    cookies,
    doctor,
    extensions,
    failover,
    groups,
    health,
    login_health,
    migrate,
    mihomo,
    nodes,
    privacy,
    profiles,
    proxies,
    sessions,
    subscriptions,
    system,
    system_v3,
    templates,
    timetravel,
    turnstile,
    stealth,
    rpa,
    totp,
    batch,
    diagnose,
    transfer,
    media,
    recorder,
    jobs,
    tags,
    ops,
    notify,
    locks,
    watchdogs,
    audit,
    fleet,
    vault,
    reports,
    backup,
)
from mozilla_manager.modules.system import boot

STATIC_DIR = Path(__file__).resolve().parents[1] / "ui" / "static"


def create_app() -> FastAPI:
    boot()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="Mozilla Browser Manager",
        version="1.10.6",
        description="ROOT-locked browser manager — v10 fleet/vault/reports/backup/ws + v9",
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(system.router, tags=["system"])
    app.include_router(system_v3.router, prefix="/api/system", tags=["system-v3"])
    app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"])
    app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
    app.include_router(proxies.router, prefix="/api/proxies", tags=["proxies"])
    app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["subscriptions"])
    app.include_router(mihomo.router, prefix="/api/mihomo", tags=["mihomo"])
    app.include_router(doctor.router, prefix="/api/doctor", tags=["doctor"])
    app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(nodes.router, prefix="/api/nodes", tags=["nodes"])
    app.include_router(health.router, prefix="/api/health", tags=["health"])
    app.include_router(extensions.router, prefix="/api/extensions", tags=["extensions"])
    app.include_router(cookies.router, prefix="/api/cookies", tags=["cookies"])
    app.include_router(login_health.router, prefix="/api/login-health", tags=["login-health"])
    app.include_router(timetravel.router, prefix="/api/timetravel", tags=["timetravel"])
    app.include_router(failover.router, prefix="/api/failover", tags=["failover"])
    app.include_router(privacy.router, prefix="/api/privacy", tags=["privacy"])
    app.include_router(migrate.router, prefix="/api/migrate", tags=["migrate"])
    app.include_router(turnstile.router, prefix="/api/turnstile", tags=["turnstile"])
    app.include_router(stealth.router, prefix="/api/stealth", tags=["stealth"])
    app.include_router(media.router, prefix="/api/media", tags=["media"])
    app.include_router(transfer.router, prefix="/api/transfer", tags=["transfer"])
    app.include_router(diagnose.router, prefix="/api/diagnose", tags=["diagnose"])
    app.include_router(batch.router, prefix="/api/batch", tags=["batch"])
    app.include_router(totp.router, prefix="/api/totp", tags=["totp"])
    app.include_router(rpa.router, prefix="/api/rpa", tags=["rpa"])
    app.include_router(recorder.router, prefix="/api/recorder", tags=["recorder"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(tags.router, prefix="/api/tags", tags=["tags"])
    app.include_router(ops.router, prefix="/api/ops", tags=["ops"])
    app.include_router(notify.router, prefix="/api/notify", tags=["notify"])
    app.include_router(locks.router, prefix="/api/locks", tags=["locks"])
    app.include_router(watchdogs.router, prefix="/api/watchdogs", tags=["watchdogs"])
    app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
    app.include_router(fleet.router, prefix="/api/fleet", tags=["fleet"])
    app.include_router(vault.router, prefix="/api/vault", tags=["vault"])
    app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
    app.include_router(backup.router, prefix="/api/backup", tags=["backup"])
    app.include_router(backup.router, prefix="/api/backups", tags=["backup"])  # alias
    from mozilla_manager.api.ws_hub import router as ws_router
    app.include_router(ws_router, tags=["ws"])
    app.include_router(subscriptions.nodes_router, prefix="/api/nodes-raw", tags=["subscriptions"])
    app.include_router(profiles.running_router, prefix="/api/running", tags=["profiles"])

    @app.get("/", response_class=HTMLResponse)
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return HTMLResponse("<h1>UI missing</h1>", status_code=500)
        return FileResponse(index_path)

    return app
