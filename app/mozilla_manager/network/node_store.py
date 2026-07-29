"""v5 local node library under runtime/nodes (ROOT-locked).

Layout:
  runtime/nodes/
    active.json                 # {"name": "default"}
    subs/<name>/
      meta.json                 # url, counts, times (no secret redaction of nodes)
      raw.bin / raw.txt
      clash.yaml                # full clash/mihomo config
      nodes.json                # proxies array full dump
      share_links.txt           # optional share-link export
    exports/sub_<name>_<ts>.zip
    mihomo/mihomo-<port>.yaml   # optional runtime cfgs (also mirrored data/nodes)
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from ..paths import (
    NODES_DIR,
    ROOT,
    RUNTIME_NODES_DIR,
    RUNTIME_SUBS_DIR,
    ensure_layout,
    p,
    safe_resolve,
)

ACTIVE_PATH = lambda: safe_resolve(RUNTIME_NODES_DIR / "active.json")  # noqa: E731


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_name(name: str) -> str:
    """Filesystem-safe subscription name.

    Keeps Unicode letters (incl. CJK), digits, `. _ -`, converts whitespace to `_`.
    Strips path separators / Windows-forbidden chars so Chinese names no longer
    collapse to `-`.
    """
    s = (name or "default").strip()
    # path / control / Windows reserved
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._-") or "default"
    if s in {".", ".."} or ".." in s:
        return "default"
    # hard length cap for path safety
    return s[:120]


def sub_path(name: str) -> Path:
    """Path to subs/<name> without creating it."""
    ensure_layout()
    return safe_resolve(RUNTIME_SUBS_DIR / _safe_name(name))


def sub_dir(name: str, *, create: bool = True) -> Path:
    """Subscription directory. create=True for writes; use create=False for reads/deletes."""
    d = sub_path(name)
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _deleted_marker_dir() -> Path:
    d = safe_resolve(RUNTIME_NODES_DIR / ".deleted_subs")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_deleted(name: str) -> bool:
    name = _safe_name(name)
    return (_deleted_marker_dir() / name).exists()


def _mark_deleted(name: str) -> None:
    name = _safe_name(name)
    marker = _deleted_marker_dir() / name
    marker.write_text(
        json.dumps({"name": name, "deleted_at": _now()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _clear_deleted_marker(name: str) -> None:
    name = _safe_name(name)
    marker = _deleted_marker_dir() / name
    if marker.exists():
        try:
            marker.unlink()
        except Exception:
            pass


def _archive_loose_sources() -> list[str]:
    """Move one-shot loose runtime/nodes dumps so they cannot resurrect default."""
    archived: list[str] = []
    arc = safe_resolve(RUNTIME_NODES_DIR / "imports" / "archived_loose")
    arc.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for fname in ("nodes.json", "subscription_raw.yaml", "subscription_raw.bin"):
        src = RUNTIME_NODES_DIR / fname
        if not src.exists() or not src.is_file():
            continue
        dest = arc / f"{ts}_{fname}"
        try:
            shutil.move(str(src), str(dest))
            archived.append(str(dest.relative_to(ROOT)))
        except Exception:
            try:
                # fallback copy+unlink
                dest.write_bytes(src.read_bytes())
                src.unlink()
                archived.append(str(dest.relative_to(ROOT)))
            except Exception:
                pass
    return archived


def get_active() -> str:
    ensure_layout()
    path = ACTIVE_PATH()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = _safe_name(str(data.get("name") or "default"))
            # if pointer is stale (deleted), fall through to real subs
            if name in list_sub_names():
                return name
        except Exception:
            pass
    # fallback first sub or default label (may not exist on disk)
    subs = list_sub_names()
    return subs[0] if subs else "default"


def set_active(name: str) -> dict[str, Any]:
    ensure_layout()
    name = _safe_name(name)
    if not (RUNTIME_SUBS_DIR / name).exists() and not (NODES_DIR / f"sub_{name}.yaml").exists():
        # allow setting even before import? require exists
        if name != "default":
            raise FileNotFoundError(f"subscription not found: {name}")
    ACTIVE_PATH().write_text(json.dumps({"name": name, "switched_at": _now()}, ensure_ascii=False, indent=2), encoding="utf-8")
    # compatibility mirror pointer
    try:
        (RUNTIME_NODES_DIR / "selected.json").write_text(
            json.dumps({"name": name, "at": _now()}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    return {"ok": True, "active": name, "at": _now()}


def list_sub_names() -> list[str]:
    ensure_layout()
    names = set()
    if RUNTIME_SUBS_DIR.exists():
        for d in RUNTIME_SUBS_DIR.iterdir():
            if d.is_dir() and (
                (d / "meta.json").exists()
                or (d / "clash.yaml").exists()
                or (d / "nodes.json").exists()
            ):
                names.add(d.name)
    # legacy data/nodes
    for f in NODES_DIR.glob("sub_*.json"):
        names.add(f.stem[4:] if f.stem.startswith("sub_") else f.stem)
    for f in NODES_DIR.glob("sub_*.yaml"):
        names.add(f.stem[4:] if f.stem.startswith("sub_") else f.stem)
    return sorted(names)



def delete_subscription(name: str, *, allow_active: bool = True) -> dict[str, Any]:
    """Delete a subscription bundle under runtime/nodes/subs/<name> + legacy mirrors.

    If deleting the active sub, switch to another remaining sub (or clear active).
    Writes a tombstone under runtime/nodes/.deleted_subs/<name> so migrate cannot
    resurrect it from loose runtime/nodes/nodes.json dumps.
    """
    ensure_layout()
    name = _safe_name(name)
    if not name:
        raise ValueError("empty subscription name")
    d = sub_path(name)  # do NOT mkdir
    existed = (
        d.exists()
        or (NODES_DIR / f"sub_{name}.json").exists()
        or (NODES_DIR / f"sub_{name}.yaml").exists()
        or (NODES_DIR / f"sub_{name}.raw").exists()
    )
    if not existed:
        # still plant tombstone so migrate won't recreate
        _mark_deleted(name)
        raise KeyError(f"subscription not found: {name}")

    was_active = get_active() == name
    # remove runtime dir
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    # legacy mirrors
    for pat in (f"sub_{name}.json", f"sub_{name}.yaml", f"sub_{name}.raw"):
        fp = NODES_DIR / pat
        if fp.exists():
            try:
                fp.unlink()
            except Exception:
                pass
    # bak files
    for fp in NODES_DIR.glob(f"sub_{name}.yaml.bak_*"):
        try:
            fp.unlink()
        except Exception:
            pass

    # Loose dumps historically re-import as "default" on every list_subs().
    # When deleting default (or any last copy), archive them so delete sticks.
    archived_loose: list[str] = []
    if name == "default":
        archived_loose = _archive_loose_sources()

    # SQLite index
    try:
        from mozilla_manager import db as _db
        _db.delete_subscription_row(name)
    except Exception:
        pass

    _mark_deleted(name)

    new_active = None
    remain = [n for n in list_sub_names() if n != name]
    if was_active:
        if remain:
            new_active = remain[0]
            set_active(new_active)
        else:
            try:
                if ACTIVE_PATH().exists():
                    ACTIVE_PATH().unlink()
            except Exception:
                pass
            try:
                sel = RUNTIME_NODES_DIR / "selected.json"
                if sel.exists():
                    sel.unlink()
            except Exception:
                pass
            new_active = None
    else:
        # if active pointer is stale / missing, keep current
        try:
            new_active = get_active() if remain else None
            if new_active and new_active not in remain:
                if remain:
                    new_active = remain[0]
                    set_active(new_active)
                else:
                    new_active = None
        except Exception:
            new_active = remain[0] if remain else None

    return {
        "ok": True,
        "deleted": name,
        "was_active": was_active,
        "active": new_active,
        "remaining": list_sub_names(),
        "archived_loose": archived_loose,
    }



def save_subscription_bundle(
    name: str,
    *,
    url: str,
    parsed: dict[str, Any],
    raw_bytes: bytes,
    source: str,
    node_count: int,
) -> dict[str, Any]:
    """Persist full subscription under runtime/nodes/subs/<name>/ + legacy data/nodes mirror."""
    ensure_layout()
    name = _safe_name(name)
    _clear_deleted_marker(name)  # re-import overrides prior delete
    d = sub_dir(name, create=True)
    proxies = [x for x in (parsed.get("proxies") or []) if isinstance(x, dict)]

    # files — full, 禁止脱敏
    (d / "raw.bin").write_bytes(raw_bytes)
    try:
        (d / "raw.txt").write_text(raw_bytes.decode("utf-8", errors="ignore"), encoding="utf-8")
    except Exception:
        pass
    clash_text = yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False)
    (d / "clash.yaml").write_text(clash_text, encoding="utf-8")
    (d / "nodes.json").write_text(json.dumps(proxies, ensure_ascii=False, indent=2), encoding="utf-8")

    # share links best-effort export (name + type + server only is NOT enough — keep full JSON lines)
    lines = []
    for px in proxies:
        # store as JSON line for lossless roundtrip (share URI reconstruction is lossy)
        lines.append(json.dumps(px, ensure_ascii=False))
    (d / "nodes.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    meta = {
        "name": name,
        "url": url,
        "url_host": urlparse(url).hostname if url else None,
        "imported_at": _now(),
        "updated_at": _now(),
        "node_count": node_count or len(proxies),
        "source": source,
        "path": str(d.relative_to(ROOT)),
        "files": {
            "clash": "clash.yaml",
            "nodes": "nodes.json",
            "raw": "raw.bin",
            "jsonl": "nodes.jsonl",
        },
        "redacted": False,
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # legacy mirror for older mihomo path
    NODES_DIR.mkdir(parents=True, exist_ok=True)
    (NODES_DIR / f"sub_{name}.yaml").write_text(clash_text, encoding="utf-8")
    (NODES_DIR / f"sub_{name}.raw").write_bytes(raw_bytes)
    (NODES_DIR / f"sub_{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # also flat runtime/nodes convenience
    try:
        (RUNTIME_NODES_DIR / "nodes.json").write_text(
            json.dumps({"active": get_active(), "name": name, "nodes": proxies, "at": _now()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass

    # if no active, set this
    if not ACTIVE_PATH().exists():
        set_active(name)
    return meta


def load_sub_meta(name: str | None = None) -> dict[str, Any] | None:
    name = _safe_name(name or get_active())
    path = sub_dir(name, create=False) / "meta.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"name": name, "error": "invalid meta"}
    legacy = NODES_DIR / f"sub_{name}.json"
    if legacy.exists():
        try:
            return json.loads(legacy.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def load_clash(name: str | None = None) -> dict[str, Any]:
    name = _safe_name(name or get_active())
    for path in (sub_dir(name, create=False) / "clash.yaml", NODES_DIR / f"sub_{name}.yaml"):
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or {}
            if isinstance(data, dict):
                return data
    return {}


def clash_yaml_path(name: str | None = None) -> Path | None:
    name = _safe_name(name or get_active())
    p1 = sub_dir(name, create=False) / "clash.yaml"
    if p1.exists():
        return p1
    p2 = NODES_DIR / f"sub_{name}.yaml"
    if p2.exists():
        return p2
    return None


def load_nodes_full(name: str | None = None) -> list[dict[str, Any]]:
    """Full proxy dicts — no desensitization."""
    name = _safe_name(name or get_active())
    nj = sub_dir(name, create=False) / "nodes.json"
    if nj.exists():
        try:
            data = json.loads(nj.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception:
            pass
    data = load_clash(name)
    return [x for x in (data.get("proxies") or []) if isinstance(x, dict)]


def list_subscriptions_detail() -> list[dict[str, Any]]:
    active = get_active()
    out = []
    for name in list_sub_names():
        meta = load_sub_meta(name) or {"name": name}
        meta = dict(meta)
        meta["active"] = name == active
        meta["node_count"] = meta.get("node_count") or len(load_nodes_full(name))
        out.append(meta)
    return out


def export_subscription(
    name: str | None = None,
    *,
    fmt: str = "zip",
) -> dict[str, Any]:
    """Export all nodes of a subscription. fmt: zip|json|yaml|jsonl"""
    ensure_layout()
    name = _safe_name(name or get_active())
    d = sub_dir(name)
    # ensure materialize from legacy if needed
    if not (d / "clash.yaml").exists():
        legacy = NODES_DIR / f"sub_{name}.yaml"
        if legacy.exists():
            data = yaml.safe_load(legacy.read_text(encoding="utf-8", errors="ignore")) or {}
            raw = (NODES_DIR / f"sub_{name}.raw").read_bytes() if (NODES_DIR / f"sub_{name}.raw").exists() else b""
            save_subscription_bundle(
                name,
                url=(load_sub_meta(name) or {}).get("url") or "",
                parsed=data if isinstance(data, dict) else {},
                raw_bytes=raw,
                source="legacy-migrate",
                node_count=len((data or {}).get("proxies") or []) if isinstance(data, dict) else 0,
            )
    exports = safe_resolve(RUNTIME_NODES_DIR / "exports")
    exports.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    nodes = load_nodes_full(name)
    meta = load_sub_meta(name) or {"name": name}

    if fmt == "json":
        out = safe_resolve(exports / f"sub_{name}_{ts}.json")
        out.write_text(
            json.dumps({"meta": meta, "nodes": nodes, "redacted": False}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"ok": True, "format": "json", "path": str(out.relative_to(ROOT)), "node_count": len(nodes)}
    if fmt == "yaml":
        out = safe_resolve(exports / f"sub_{name}_{ts}.yaml")
        src = d / "clash.yaml"
        if src.exists():
            shutil.copy2(src, out)
        else:
            out.write_text(yaml.safe_dump({"proxies": nodes}, allow_unicode=True), encoding="utf-8")
        return {"ok": True, "format": "yaml", "path": str(out.relative_to(ROOT)), "node_count": len(nodes)}
    if fmt == "jsonl":
        out = safe_resolve(exports / f"sub_{name}_{ts}.jsonl")
        out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in nodes) + "\n", encoding="utf-8")
        return {"ok": True, "format": "jsonl", "path": str(out.relative_to(ROOT)), "node_count": len(nodes)}

    # zip full bundle
    out = safe_resolve(exports / f"sub_{name}_{ts}.zip")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("_export_manifest.json", json.dumps({"name": name, "meta": meta, "redacted": False, "at": ts}, ensure_ascii=False, indent=2))
        for fname in ("meta.json", "clash.yaml", "nodes.json", "nodes.jsonl", "raw.bin", "raw.txt"):
            fp = d / fname
            if fp.exists():
                zf.write(fp, arcname=fname)
        zf.writestr("nodes.full.json", json.dumps(nodes, ensure_ascii=False, indent=2))
    return {"ok": True, "format": "zip", "path": str(out.relative_to(ROOT)), "node_count": len(nodes), "redacted": False}


def import_nodes_file(path: str | Path, name: str = "imported") -> dict[str, Any]:
    """Import nodes from local json/yaml/jsonl/zip under ROOT."""
    ensure_layout()
    src = safe_resolve(path)
    name = _safe_name(name)
    raw = b""
    parsed: dict[str, Any] = {"proxies": []}
    source = "file"

    if src.suffix.lower() == ".zip":
        import tempfile
        from ..paths import TMP_DIR
        tdir = safe_resolve(TMP_DIR / f"import_{name}")
        if tdir.exists():
            shutil.rmtree(tdir, ignore_errors=True)
        tdir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(tdir)
        for cand in ("clash.yaml", "nodes.full.json", "nodes.json"):
            f = tdir / cand
            if f.exists():
                if cand.endswith(".yaml"):
                    parsed = yaml.safe_load(f.read_text(encoding="utf-8", errors="ignore")) or {}
                    raw = f.read_bytes()
                    source = "zip-yaml"
                else:
                    nodes = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(nodes, dict) and "nodes" in nodes:
                        nodes = nodes["nodes"]
                    parsed = {"proxies": nodes, "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": [n.get("name") for n in nodes if n.get("name")] + ["DIRECT"]}], "rules": ["MATCH,PROXY"]}
                    raw = f.read_bytes()
                    source = "zip-json"
                break
    elif src.suffix.lower() in (".yaml", ".yml"):
        raw = src.read_bytes()
        parsed = yaml.safe_load(src.read_text(encoding="utf-8", errors="ignore")) or {}
        source = "yaml"
    elif src.suffix.lower() == ".jsonl":
        nodes = []
        for line in src.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            nodes.append(json.loads(line))
        parsed = {"proxies": nodes, "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": [n.get("name") for n in nodes if n.get("name")] + ["DIRECT"]}], "rules": ["MATCH,PROXY"]}
        raw = src.read_bytes()
        source = "jsonl"
    elif src.suffix.lower() == ".json":
        raw = src.read_bytes()
        data = json.loads(src.read_text(encoding="utf-8"))
        if isinstance(data, list):
            nodes = data
        else:
            nodes = data.get("nodes") or data.get("proxies") or []
        parsed = data if isinstance(data, dict) and data.get("proxies") else {
            "proxies": nodes,
            "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": [n.get("name") for n in nodes if isinstance(n, dict) and n.get("name")] + ["DIRECT"]}],
            "rules": ["MATCH,PROXY"],
        }
        source = "json"
    else:
        raise ValueError(f"unsupported import format: {src.suffix}")

    if not isinstance(parsed, dict):
        raise ValueError("parsed subscription is not a mapping")
    node_count = len([x for x in (parsed.get("proxies") or []) if isinstance(x, dict)])
    meta = save_subscription_bundle(
        name,
        url=f"file://{src.relative_to(ROOT) if str(src).startswith(str(ROOT)) else src.name}",
        parsed=parsed,
        raw_bytes=raw or b"{}",
        source=source,
        node_count=node_count,
    )
    return meta


def migrate_legacy_to_runtime() -> dict[str, Any]:
    """Copy data/nodes/sub_* into runtime/nodes/subs/ (one-shot; respects delete tombstones)."""
    ensure_layout()
    migrated = []
    archived_loose: list[str] = []
    for yml in NODES_DIR.glob("sub_*.yaml"):
        name = yml.stem[4:] if yml.stem.startswith("sub_") else yml.stem
        name = _safe_name(name)
        if _is_deleted(name):
            continue
        if (sub_dir(name, create=False) / "clash.yaml").exists():
            continue
        data = yaml.safe_load(yml.read_text(encoding="utf-8", errors="ignore")) or {}
        raw_p = NODES_DIR / f"sub_{name}.raw"
        raw = raw_p.read_bytes() if raw_p.exists() else yml.read_bytes()
        meta_p = NODES_DIR / f"sub_{name}.json"
        url = ""
        if meta_p.exists():
            try:
                url = json.loads(meta_p.read_text(encoding="utf-8")).get("url") or ""
            except Exception:
                pass
        meta = save_subscription_bundle(
            name,
            url=url,
            parsed=data if isinstance(data, dict) else {},
            raw_bytes=raw,
            source="legacy-migrate",
            node_count=len((data or {}).get("proxies") or []) if isinstance(data, dict) else 0,
        )
        migrated.append(meta["name"])
    # loose files under runtime/nodes/ (older tooling dumps)
    loose_yaml = RUNTIME_NODES_DIR / "subscription_raw.yaml"
    loose_json = RUNTIME_NODES_DIR / "nodes.json"
    loose_bin = RUNTIME_NODES_DIR / "subscription_raw.bin"
    if (
        "default" not in migrated
        and not _is_deleted("default")
        and not (sub_dir("default", create=False) / "clash.yaml").exists()
    ):
        if loose_yaml.exists() or loose_json.exists():
            data: dict[str, Any] = {}
            raw = b""
            if loose_yaml.exists():
                try:
                    data = yaml.safe_load(loose_yaml.read_text(encoding="utf-8", errors="ignore")) or {}
                except Exception:
                    data = {}
                raw = loose_yaml.read_bytes()
            elif loose_json.exists():
                try:
                    nodes = json.loads(loose_json.read_text(encoding="utf-8"))
                    if isinstance(nodes, dict) and "nodes" in nodes:
                        nodes = nodes["nodes"]
                    if not isinstance(nodes, list):
                        nodes = []
                    data = {
                        "proxies": nodes,
                        "proxy-groups": [
                            {
                                "name": "PROXY",
                                "type": "select",
                                "proxies": [n.get("name") for n in nodes if isinstance(n, dict) and n.get("name")]
                                + ["DIRECT"],
                            }
                        ],
                        "rules": ["MATCH,PROXY"],
                    }
                    raw = loose_json.read_bytes()
                except Exception:
                    data = {"proxies": []}
            if loose_bin.exists() and not raw:
                raw = loose_bin.read_bytes()
            if isinstance(data, dict) and (data.get("proxies") or data.get("proxy-groups")):
                meta = save_subscription_bundle(
                    "default",
                    url="",
                    parsed=data,
                    raw_bytes=raw or b"{}",
                    source="runtime-loose-migrate",
                    node_count=len([x for x in (data.get("proxies") or []) if isinstance(x, dict)]),
                )
                migrated.append(meta["name"])
                # Critical: archive loose dumps so list_subs() cannot resurrect default after user deletes it
                archived_loose = _archive_loose_sources()

    if migrated and not ACTIVE_PATH().exists():
        set_active(migrated[0])
    # ensure active always points to something real
    try:
        get_active()
        if not ACTIVE_PATH().exists() and list_sub_names():
            set_active(list_sub_names()[0])
    except Exception:
        pass
    return {"ok": True, "migrated": migrated, "archived_loose": archived_loose, "active": get_active()}
