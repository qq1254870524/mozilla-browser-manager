"""RPA interactive recorder — capture click/fill/nav on a running profile."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import RPA_RECORDINGS_DIR, ensure_layout, safe_resolve
from mozilla_manager.store import ProfileStore
from mozilla_manager.engines.sync_bridge import call_in_profile_thread

_LOCK = threading.Lock()
_STATE: dict[str, dict[str, Any]] = {}  # profile_id -> state

_INJECT = r"""
(() => {
  if (window.__mmRpaInstalled) return {ok:true, already:true};
  window.__mmRpaInstalled = true;
  window.__mmRpaQueue = window.__mmRpaQueue || [];
  const cssPath = (el) => {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let cur = el;
    for (let i = 0; cur && cur.nodeType === 1 && i < 5; i++) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift('#' + CSS.escape(cur.id)); break; }
      const name = cur.getAttribute('name');
      const testid = cur.getAttribute('data-testid');
      if (testid) part += `[data-testid="${testid}"]`;
      else if (name) part += `[name="${name}"]`;
      else if (cur.classList && cur.classList.length) {
        const c = [...cur.classList].slice(0,2).map(x => CSS.escape(x)).join('.');
        if (c) part += '.' + c;
      }
      const parent = cur.parentElement;
      if (parent) {
        const same = [...parent.children].filter(x => x.tagName === cur.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(cur)+1})`;
      }
      parts.unshift(part);
      cur = parent;
      if (cur && cur.id) { parts.unshift('#' + CSS.escape(cur.id)); break; }
    }
    return parts.join(' > ');
  };
  const push = (ev) => { try { window.__mmRpaQueue.push(Object.assign({ts: Date.now(), url: location.href}, ev)); } catch(_){} };
  push({action:'goto', url: location.href});
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t) return;
    push({action:'click', selector: cssPath(t), text: (t.innerText||t.value||'').toString().slice(0,80)});
  }, true);
  document.addEventListener('change', (e) => {
    const t = e.target;
    if (!t) return;
    const tag = (t.tagName||'').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      const typ = (t.type||'').toLowerCase();
      const val = (typ === 'password') ? '***' : String(t.value||'');
      push({action:'fill', selector: cssPath(t), value: val, input_type: typ});
    }
  }, true);
  document.addEventListener('submit', (e) => {
    const t = e.target;
    push({action:'click', selector: cssPath(t) + ' [type=submit]', text:'submit'});
  }, true);
  return {ok:true, installed:true};
})()
"""

_DRAIN = r"""
(() => {
  const q = window.__mmRpaQueue || [];
  window.__mmRpaQueue = [];
  return q;
})()
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rec_path(profile_id: str):
    ensure_layout()
    return safe_resolve(RPA_RECORDINGS_DIR / f"{profile_id}.json")


def _get_page(profile_id: str):
    """MUST be called on the profile browser thread."""
    from mozilla_manager.engines import chromium as chromium_mod
    from mozilla_manager.engines import camoufox_engine as camoufox_mod

    run = getattr(chromium_mod, "_RUNS", {}).get(profile_id)
    if not run or not run.get("context"):
        run = getattr(camoufox_mod, "_RUNS", {}).get(profile_id)
    if not run or not run.get("context"):
        raise RuntimeError(f"profile not running: {profile_id}")
    ctx = run["context"]
    page = run.get("page")
    if page is None:
        page = ctx.pages[0] if getattr(ctx, "pages", None) else None
        if page is None and hasattr(ctx, "new_page"):
            page = ctx.new_page()
        run["page"] = page
    if page is None:
        raise RuntimeError(f"no page for profile: {profile_id}")
    return page


def start_recording(profile_id: str) -> dict[str, Any]:
    ProfileStore().get(profile_id)

    def _do():
        page = _get_page(profile_id)
        info = page.evaluate(_INJECT)
        url = None
        try:
            url = page.url
        except Exception:
            url = None
        return info, url

    info, url = call_in_profile_thread(profile_id, _do, timeout=60.0)
    with _LOCK:
        st = {
            "profile_id": profile_id,
            "recording": True,
            "started_at": _now(),
            "events": [],
            "last_poll_at": None,
        }
        _STATE[profile_id] = st
    if url:
        st["events"].append({"action": "goto", "url": url, "ts": int(time.time() * 1000)})
    _persist(profile_id)
    return {"ok": True, "profile_id": profile_id, "recording": True, "inject": info, "started_at": st["started_at"]}


def poll_events(profile_id: str) -> dict[str, Any]:
    with _LOCK:
        st = _STATE.get(profile_id)
        if not st or not st.get("recording"):
            # try load disk
            path = _rec_path(profile_id)
            if path.exists():
                disk = json.loads(path.read_text(encoding="utf-8"))
                return {"ok": True, "recording": bool(disk.get("recording")), "events": disk.get("events") or [], "from": "disk"}
            return {"ok": False, "error": "not recording", "events": []}
    try:
        def _drain():
            page = _get_page(profile_id)
            return page.evaluate(_DRAIN) or []
        batch = call_in_profile_thread(profile_id, _drain, timeout=30.0)
    except Exception as e:
        return {"ok": False, "error": str(e), "events": st.get("events") or []}
    with _LOCK:
        st = _STATE.setdefault(profile_id, {"events": [], "recording": True, "profile_id": profile_id})
        for ev in batch:
            st["events"].append(ev)
        st["last_poll_at"] = _now()
        events = list(st["events"])
    _persist(profile_id)
    return {"ok": True, "recording": True, "added": len(batch), "events": events, "count": len(events)}


def stop_recording(profile_id: str, *, save_workflow: bool = True, name: str = "", workflow_id: str = "") -> dict[str, Any]:
    # final poll
    try:
        poll_events(profile_id)
    except Exception:
        pass
    with _LOCK:
        st = _STATE.get(profile_id) or {}
        events = list(st.get("events") or [])
        st["recording"] = False
        st["stopped_at"] = _now()
        _STATE[profile_id] = st
    steps = events_to_steps(events)
    out: dict[str, Any] = {
        "ok": True,
        "profile_id": profile_id,
        "recording": False,
        "events": len(events),
        "steps": steps,
        "stopped_at": st.get("stopped_at"),
    }
    wf = None
    if save_workflow and steps:
        from mozilla_manager.rpa import store as wf_store

        wid = workflow_id or f"rec-{profile_id[:8]}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        wf = wf_store.save_workflow(
            {
                "id": wid,
                "name": name or f"录制 {profile_id[:12]}",
                "profile_id": profile_id,
                "tags": ["recorded", "v8"],
                "steps": steps,
            }
        )
        out["workflow"] = {"id": wf.get("id"), "name": wf.get("name"), "steps": len(wf.get("steps") or [])}
    _persist(profile_id, extra={"steps": steps, "workflow_id": (wf or {}).get("id")})
    return out


def status(profile_id: str) -> dict[str, Any]:
    with _LOCK:
        st = _STATE.get(profile_id)
    if st:
        return {
            "ok": True,
            "profile_id": profile_id,
            "recording": bool(st.get("recording")),
            "events": len(st.get("events") or []),
            "started_at": st.get("started_at"),
            "last_poll_at": st.get("last_poll_at"),
        }
    path = _rec_path(profile_id)
    if path.exists():
        disk = json.loads(path.read_text(encoding="utf-8"))
        return {
            "ok": True,
            "profile_id": profile_id,
            "recording": bool(disk.get("recording")),
            "events": len(disk.get("events") or []),
            "from": "disk",
            "started_at": disk.get("started_at"),
        }
    return {"ok": True, "profile_id": profile_id, "recording": False, "events": 0}


def events_to_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    last_url = None
    last_fill_sel = None
    for ev in events or []:
        act = ev.get("action")
        if act == "goto":
            url = ev.get("url")
            if url and url != last_url and not str(url).startswith("about:"):
                steps.append({"action": "goto", "url": url})
                last_url = url
        elif act == "click":
            sel = ev.get("selector")
            if sel:
                steps.append({"action": "click", "selector": sel})
        elif act == "fill":
            sel = ev.get("selector")
            val = ev.get("value", "")
            if sel:
                # collapse repeated fills on same selector
                if last_fill_sel == sel and steps and steps[-1].get("action") == "fill":
                    steps[-1]["value"] = val
                else:
                    steps.append({"action": "fill", "selector": sel, "value": val})
                    last_fill_sel = sel
    # reindex
    for i, s in enumerate(steps):
        s["index"] = i
    return steps


def _persist(profile_id: str, extra: dict[str, Any] | None = None) -> None:
    with _LOCK:
        st = dict(_STATE.get(profile_id) or {})
    if extra:
        st.update(extra)
    st["profile_id"] = profile_id
    st["updated_at"] = _now()
    path = _rec_path(profile_id)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def timeline(profile_id: str) -> dict[str, Any]:
    """Return recording events as a UI-friendly timeline + derived steps."""
    st = status(profile_id)
    events: list[dict[str, Any]] = []
    with _LOCK:
        mem = _STATE.get(profile_id) or {}
        events = list(mem.get("events") or [])
    if not events:
        path = _rec_path(profile_id)
        if path.exists():
            try:
                disk = json.loads(path.read_text(encoding="utf-8"))
                events = list(disk.get("events") or [])
            except Exception:
                events = []
    steps = events_to_steps(events)
    tl = []
    for i, ev in enumerate(events):
        tl.append(
            {
                "i": i,
                "action": ev.get("action"),
                "selector": ev.get("selector"),
                "value": ev.get("value"),
                "url": ev.get("url"),
                "text": ev.get("text"),
                "ts": ev.get("ts"),
            }
        )
    return {
        "ok": True,
        "profile_id": profile_id,
        "recording": bool(st.get("recording")),
        "events": len(events),
        "timeline": tl,
        "steps": steps,
    }
