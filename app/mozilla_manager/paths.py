from __future__ import annotations

import os
from pathlib import Path

# =============================================================================
# ROOT lock — never write outside the current tree
#
# Canonical DEV tree (Ubuntu/WSL only place to develop):
#   /home/baoge/Mozilla
#   \\wsl.localhost\Ubuntu\home\baoge\Mozilla
#
# Windows RUNTIME copy (test/use only, filled by export_to_windows.sh):
#   C:\Users\zhang\Desktop\Mozilla
#
# ROOT is derived from this file's location, so:
#   - developing under /home/baoge/Mozilla  → ROOT = that tree
#   - running the Desktop copy on Windows  → ROOT = Desktop\Mozilla
# All project files must stay inside ROOT (see safe_resolve / ensure_layout).
# =============================================================================
ROOT = Path(__file__).resolve().parents[2]


class PathSandboxError(RuntimeError):
    pass


def ensure_layout() -> Path:
    """Create portable folders inside ROOT only."""
    for rel in (
        "data/profiles",
        "data/nodes",
        "data/exports",
        "data/exports/sessions",
        "data/exports/snapshots",
        "data/env_packs",
        "data/fingerprints",
        "logs",
        "tmp",
        "runtime/browsers",
        "runtime/mihomo",
        "runtime/patches",
        "runtime/extensions",
        "runtime/manifests",
        "runtime/cache",
        "runtime/nodes",
        "runtime/nodes/subs",
        "runtime/nodes/exports",
        "runtime/nodes/imports",
        "runtime/nodes/mihomo",
        "runtime/vendors",
        "data/rpa/workflows",
        "data/rpa/runs",
        "data/rpa/schedules",
        "data/totp",
        "data/exports/migrate",
        "data/media/virtual",
        "logs/rpa",
        "logs/diagnose",
        "data/jobs",
        "data/rpa/recordings",
        "logs/jobs",
        "data/notices",
        "data/watchdogs",
        "logs/watchdogs",
        "data/fleet",
        "data/fleet/inbox",
        "data/fleet/outbox",
        "data/reports",
        "data/vault",
        "data/backups",
        "logs/fleet",
        "logs/reports",
        "data/client",
        "data/proxies",
    ):
        (ROOT / rel).mkdir(parents=True, exist_ok=True)
    return ROOT


def p(*parts: str | Path) -> Path:
    return ROOT.joinpath(*[str(x) for x in parts])


def safe_resolve(path: Path | str) -> Path:
    """Resolve and guarantee the path stays under ROOT."""
    root = ROOT.resolve()
    target = Path(path)
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    if target != root and not str(target).startswith(str(root) + os.sep):
        raise PathSandboxError(f"path escapes Mozilla root: {target}")
    return target


def under_root(path: Path | str) -> bool:
    try:
        safe_resolve(path)
        return True
    except PathSandboxError:
        return False


PROFILE_DIR = lambda name: p("data", "profiles", name)  # noqa: E731
DB_PATH = p("data", "app.db")
NODES_DIR = p("data", "nodes")
LOG_DIR = p("logs")
TMP_DIR = p("tmp")
RUNTIME_DIR = p("runtime")
MIHOMO_DIR = p("runtime", "mihomo")
BROWSERS_DIR = p("runtime", "browsers")
PATCHES_DIR = p("runtime", "patches")
ENV_PACKS_DIR = p("data", "env_packs")
MANIFEST_PATH = p("runtime", "manifests", "current.json")
PROFILES_INDEX = p("data", "profiles.json")

FINGERPRINTS_DIR = p("data", "fingerprints")
SESSIONS_DIR = p("data", "exports", "sessions")

RUNTIME_NODES_DIR = p("runtime", "nodes")
RUNTIME_SUBS_DIR = p("runtime", "nodes", "subs")
RUNTIME_IMPORTS_DIR = p("runtime", "nodes", "imports")
TURNSTILE_VENDOR_DIR = p("runtime", "vendors", "turnstile-harvester1")

RPA_DIR = p("data", "rpa")
RPA_WORKFLOWS_DIR = p("data", "rpa", "workflows")
RPA_RUNS_DIR = p("data", "rpa", "runs")
RPA_SCHEDULES_DIR = p("data", "rpa", "schedules")
TOTP_DIR = p("data", "totp")
MIGRATE_DIR = p("data", "exports", "migrate")
VIRTUAL_MEDIA_DIR = p("data", "media", "virtual")

JOBS_DIR = p("data", "jobs")
RPA_RECORDINGS_DIR = p("data", "rpa", "recordings")

NOTICES_DIR = p("data", "notices")
WATCHDOGS_DIR = p("data", "watchdogs")

FLEET_DIR = p("data", "fleet")
FLEET_INBOX = p("data", "fleet", "inbox")
FLEET_OUTBOX = p("data", "fleet", "outbox")
REPORTS_DIR = p("data", "reports")
VAULT_DIR = p("data", "vault")
BACKUPS_DIR = p("data", "backups")

CLIENT_DIR = p("data", "client")
PROXIES_DIR = p("data", "proxies")
