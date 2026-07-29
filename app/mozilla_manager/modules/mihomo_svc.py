"""Mihomo service module: local process control (wraps network.mihomo)."""
from __future__ import annotations

from typing import Any

from mozilla_manager.network.mihomo import (
    allocate_port as _allocate_port,
    cleanup_orphan_mihomo,
    list_live_mihomo_processes,
    start_mihomo,
    status_mihomo,
    stop_mihomo,
)


def allocate_port(profile_id: str, base: int = 17800) -> int:
    return _allocate_port(profile_id, base=base)


def start(
    port: int,
    sub: str = "default",
    node: str = "",
    client_fingerprint: str | None = None,
) -> dict[str, Any]:
    return start_mihomo(
        port,
        subscription_name=sub,
        node_name=node or None,
        client_fingerprint=client_fingerprint,
    )


def stop(port: int) -> dict[str, Any]:
    return stop_mihomo(port)


def status() -> list[dict[str, Any]]:
    return status_mihomo()


def live() -> list[dict[str, Any]]:
    return list_live_mihomo_processes()


def cleanup_orphans(keep_ports: list[int] | None = None, dry_run: bool = False) -> dict[str, Any]:
    keep = set(int(x) for x in keep_ports) if keep_ports is not None else None
    return cleanup_orphan_mihomo(keep_ports=keep, dry_run=dry_run)
