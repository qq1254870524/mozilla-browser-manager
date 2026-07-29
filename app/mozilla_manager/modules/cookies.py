"""v4 Cookie import / export / pre-launch inject (JSON | Base64 | storage_state)."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mozilla_manager import db
from mozilla_manager.paths import ROOT, ensure_layout, p, safe_resolve
from mozilla_manager.store import ProfileStore


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cookies_path(profile_id: str) -> Path:
    store = ProfileStore()
    prof = store.get(profile_id)
    d = safe_resolve(ROOT / prof.user_data_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / "cookies_inject.json"


def _normalize_cookie(c: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize various cookie formats to Playwright cookie dict."""
    if not isinstance(c, dict):
        return None
    name = c.get("name") or c.get("Name")
    value = c.get("value") if "value" in c else c.get("Value")
    if name is None or value is None:
        return None
    domain = c.get("domain") or c.get("Domain") or c.get("host") or ""
    path = c.get("path") or c.get("Path") or "/"
    out: dict[str, Any] = {
        "name": str(name),
        "value": str(value),
        "domain": str(domain) if domain else None,
        "path": str(path),
    }
    # expires
    exp = c.get("expires") or c.get("expirationDate") or c.get("Expiry") or c.get("expiration")
    if exp is not None:
        try:
            exp_f = float(exp)
            # chrome extension sometimes uses ms
            if exp_f > 1e12:
                exp_f = exp_f / 1000.0
            out["expires"] = exp_f
        except Exception:
            pass
    for src, dst in (
        ("httpOnly", "httpOnly"),
        ("HttpOnly", "httpOnly"),
        ("secure", "secure"),
        ("Secure", "secure"),
        ("sameSite", "sameSite"),
        ("SameSite", "sameSite"),
        ("url", "url"),
    ):
        if src in c and c[src] is not None:
            out[dst] = c[src]
    # sameSite normalize
    ss = out.get("sameSite")
    if isinstance(ss, str):
        s = ss.lower()
        if s in ("no_restriction", "none"):
            out["sameSite"] = "None"
        elif s in ("lax",):
            out["sameSite"] = "Lax"
        elif s in ("strict",):
            out["sameSite"] = "Strict"
        elif s in ("unspecified", ""):
            out.pop("sameSite", None)
    # Playwright needs either url or domain
    if not out.get("domain") and not out.get("url"):
        return None
    if out.get("domain") is None:
        out.pop("domain", None)
    return out


def parse_cookie_payload(raw: str | bytes | dict | list) -> dict[str, Any]:
    """Parse JSON / Base64 / storage_state / bare cookie list into storage_state-like dict."""
    data: Any
    if isinstance(raw, (dict, list)):
        data = raw
    else:
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="ignore").strip()
        else:
            text = str(raw).strip()
        # try base64
        try:
            pad = (-len(text.replace("\n", ""))) % 4
            dec = base64.b64decode(text.replace("\n", "").replace(" ", "") + ("=" * pad))
            maybe = dec.decode("utf-8", errors="ignore").strip()
            if maybe.startswith("{") or maybe.startswith("["):
                text = maybe
        except Exception:
            pass
        data = json.loads(text)

    cookies: list[dict[str, Any]] = []
    origins: list[dict[str, Any]] = []

    if isinstance(data, list):
        for c in data:
            n = _normalize_cookie(c)
            if n:
                cookies.append(n)
    elif isinstance(data, dict):
        if "cookies" in data:
            for c in data.get("cookies") or []:
                n = _normalize_cookie(c)
                if n:
                    cookies.append(n)
            origins = list(data.get("origins") or [])
        elif "cookie" in data and isinstance(data["cookie"], list):
            for c in data["cookie"]:
                n = _normalize_cookie(c)
                if n:
                    cookies.append(n)
        else:
            # single cookie object?
            n = _normalize_cookie(data)
            if n:
                cookies.append(n)
    else:
        raise ValueError("unsupported cookie payload type")

    return {"cookies": cookies, "origins": origins}


def import_cookies(profile_id: str, payload: str | dict | list, *, merge: bool = True) -> dict[str, Any]:
    """Save cookies for pre-launch injection. merge=True unions by (name,domain,path)."""
    ensure_layout()
    store = ProfileStore()
    prof = store.get(profile_id)
    incoming = parse_cookie_payload(payload)
    path = _cookies_path(profile_id)
    existing: dict[str, Any] = {"cookies": [], "origins": []}
    if merge and path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {"cookies": [], "origins": []}

    def key(c: dict[str, Any]) -> tuple:
        return (c.get("name"), c.get("domain") or c.get("url"), c.get("path") or "/")

    merged: dict[tuple, dict[str, Any]] = {}
    for c in existing.get("cookies") or []:
        if isinstance(c, dict):
            merged[key(c)] = c
    for c in incoming.get("cookies") or []:
        merged[key(c)] = c

    # origins: replace same origin
    origins_map = {o.get("origin"): o for o in (existing.get("origins") or []) if isinstance(o, dict)}
    for o in incoming.get("origins") or []:
        if isinstance(o, dict) and o.get("origin"):
            origins_map[o["origin"]] = o

    state = {
        "cookies": list(merged.values()),
        "origins": list(origins_map.values()),
        "imported_at": _now(),
        "count": len(merged),
    }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # also mirror as restored_storage_state for engine inject path
    ud = safe_resolve(ROOT / prof.user_data_dir)
    (ud / "restored_storage_state.json").write_text(
        json.dumps({"cookies": state["cookies"], "origins": state["origins"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    db.audit("cookies_import", profile_id, {"count": state["count"], "merge": merge})
    return {"ok": True, "profile_id": profile_id, "count": state["count"], "path": str(path.relative_to(ROOT))}


def export_cookies(profile_id: str, *, fmt: str = "json", prefer_live: bool = True) -> dict[str, Any]:
    """Export cookies as JSON object or Base64 string. prefer live context if running."""
    state = None
    if prefer_live:
        state = _live_storage(profile_id)
    if state is None:
        path = _cookies_path(profile_id)
        if path.exists():
            state = json.loads(path.read_text(encoding="utf-8"))
        else:
            # try restored
            store = ProfileStore()
            prof = store.get(profile_id)
            alt = safe_resolve(ROOT / prof.user_data_dir) / "restored_storage_state.json"
            if alt.exists():
                state = json.loads(alt.read_text(encoding="utf-8"))
            else:
                state = {"cookies": [], "origins": []}
    # clean export (full values, 禁止脱敏)
    out = {
        "cookies": state.get("cookies") or [],
        "origins": state.get("origins") or [],
        "exported_at": _now(),
        "profile_id": profile_id,
        "redacted": False,
    }
    raw = json.dumps(out, ensure_ascii=False, indent=2)
    if fmt == "base64":
        b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        db.audit("cookies_export", profile_id, {"fmt": "base64", "count": len(out["cookies"])})
        return {"ok": True, "format": "base64", "data": b64, "count": len(out["cookies"])}
    # also write file under exports
    ensure_layout()
    dest = safe_resolve(p("data", "exports", "cookies", f"{profile_id}_{_now().replace(':', '')}.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(raw, encoding="utf-8")
    db.audit("cookies_export", profile_id, {"fmt": "json", "count": len(out["cookies"]), "path": str(dest.relative_to(ROOT))})
    return {"ok": True, "format": "json", "data": out, "path": str(dest.relative_to(ROOT)), "count": len(out["cookies"])}


def inject_cookies_to_context(context: Any, profile_id: str) -> dict[str, Any]:
    """Apply pending cookies/storage into a live Playwright context."""
    store = ProfileStore()
    prof = store.get(profile_id)
    ud = safe_resolve(ROOT / prof.user_data_dir)
    candidates = [ud / "restored_storage_state.json", ud / "cookies_inject.json"]
    state = None
    used = None
    for c in candidates:
        if c.exists():
            try:
                state = json.loads(c.read_text(encoding="utf-8"))
                used = str(c.name)
                break
            except Exception:
                continue
    if not state:
        return {"ok": False, "injected": 0, "message": "no cookie file"}
    cookies = []
    for c in state.get("cookies") or []:
        n = _normalize_cookie(c)
        if n:
            # drop null domain
            if n.get("domain") is None:
                n.pop("domain", None)
            cookies.append(n)
    injected = 0
    errors: list[str] = []
    if cookies and hasattr(context, "add_cookies"):
        try:
            context.add_cookies(cookies)
            injected = len(cookies)
        except Exception as e:
            # try one-by-one
            for c in cookies:
                try:
                    context.add_cookies([c])
                    injected += 1
                except Exception as e2:
                    errors.append(f"{c.get('name')}: {e2}")
    # origins localStorage via add_init_script is complex; storage_state origins
    # best-effort: if context has storage API later
    db.audit("cookies_inject", profile_id, {"injected": injected, "source": used, "errors": errors[:5]})
    return {"ok": True, "injected": injected, "source": used, "errors": errors[:10]}


def load_pending_storage_state(profile_id: str) -> dict[str, Any] | None:
    store = ProfileStore()
    prof = store.get(profile_id)
    ud = safe_resolve(ROOT / prof.user_data_dir)
    for name in ("restored_storage_state.json", "cookies_inject.json"):
        path = ud / name
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return {
                    "cookies": data.get("cookies") or [],
                    "origins": data.get("origins") or [],
                }
            except Exception:
                continue
    return None


def _live_storage(profile_id: str) -> dict[str, Any] | None:
    try:
        from mozilla_manager.engines.sync_bridge import call_in_profile_thread
        from mozilla_manager.engines import chromium as chromium_mod
        from mozilla_manager.engines import camoufox_engine as camoufox_mod

        def _read():
            run = getattr(chromium_mod, "_RUNS", {}).get(profile_id) or getattr(camoufox_mod, "_RUNS", {}).get(profile_id)
            if run and run.get("context") is not None and hasattr(run["context"], "storage_state"):
                return run["context"].storage_state()
            return None

        # Only route through browser thread when a worker exists / profile running.
        from mozilla_manager.runtime_registry import list_running
        if profile_id in (list_running() or {}):
            return call_in_profile_thread(profile_id, _read, timeout=30.0)
        return _read()
    except Exception:
        return None
