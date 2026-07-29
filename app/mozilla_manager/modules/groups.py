"""Groups module: aggregate profile groups."""
from __future__ import annotations

from typing import Any

from mozilla_manager.store import ProfileStore


def list_groups() -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for p in ProfileStore().list():
        g = str(p.meta.get("group") or "未分组")
        counts[g] = counts.get(g, 0) + 1
    return [{"name": k, "count": v} for k, v in sorted(counts.items())]
