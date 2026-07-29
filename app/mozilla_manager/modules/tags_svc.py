"""Profile tags (v8) — stored in profile.meta.tags list."""
from __future__ import annotations

from typing import Any

from mozilla_manager.store import ProfileStore


def _norm(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    seen = set()
    for t in tags or []:
        s = str(t).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def get_tags(profile_id: str) -> list[str]:
    prof = ProfileStore().get(profile_id)
    return list(prof.meta.get("tags") or [])


def set_tags(profile_id: str, tags: list[str]) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    meta["tags"] = _norm(tags)
    prof = store.update(profile_id, meta=meta)
    return {"ok": True, "profile_id": profile_id, "tags": list(prof.meta.get("tags") or [])}


def add_tags(profile_id: str, tags: list[str]) -> dict[str, Any]:
    cur = get_tags(profile_id)
    return set_tags(profile_id, cur + list(tags or []))


def remove_tags(profile_id: str, tags: list[str]) -> dict[str, Any]:
    drop = {str(t).strip().lower() for t in (tags or [])}
    cur = [t for t in get_tags(profile_id) if t.lower() not in drop]
    return set_tags(profile_id, cur)


def list_all_tags() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for p in ProfileStore().list():
        for t in p.meta.get("tags") or []:
            counts[t] = counts.get(t, 0) + 1
    items = [{"tag": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    return {"ok": True, "tags": items, "count": len(items)}


def filter_by_tag(tag: str) -> list[dict[str, Any]]:
    key = str(tag or "").strip().lower()
    rows = []
    for p in ProfileStore().list():
        tags = [str(t).lower() for t in (p.meta.get("tags") or [])]
        if key and key in tags:
            rows.append({"id": p.id, "name": p.name, "tags": list(p.meta.get("tags") or [])})
    return rows
