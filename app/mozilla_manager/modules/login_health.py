"""v4 登录态健康巡检：静默访问目标站，失效则打「需重登」标签."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from mozilla_manager import db
from mozilla_manager.modules import cookies as cookies_mod
from mozilla_manager.paths import ROOT, ensure_layout, safe_resolve
from mozilla_manager.store import ProfileStore


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_watch_targets(profile_id: str, urls: list[str], *, interval_hours: float = 24.0) -> dict[str, Any]:
    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    meta["login_watch"] = {
        "urls": [u for u in urls if u],
        "interval_hours": interval_hours,
        "updated_at": _now(),
    }
    # clear stale tag only if reconfigured
    store.update(profile_id, meta=meta)
    db.audit("login_watch_set", profile_id, meta["login_watch"])
    return {"ok": True, "profile_id": profile_id, "watch": meta["login_watch"]}


def get_watch(profile_id: str) -> dict[str, Any]:
    prof = ProfileStore().get(profile_id)
    return (prof.meta or {}).get("login_watch") or {"urls": [], "interval_hours": 24}


def _mark(profile_id: str, need_relogin: bool, detail: dict[str, Any]) -> None:
    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    tags = list(meta.get("tags") or [])
    if need_relogin:
        if "需重登" not in tags:
            tags.append("需重登")
        meta["need_relogin"] = True
        meta["need_relogin_at"] = _now()
        meta["need_relogin_detail"] = detail
    else:
        tags = [t for t in tags if t != "需重登"]
        meta["need_relogin"] = False
        meta["last_login_ok_at"] = _now()
        meta.pop("need_relogin_detail", None)
    meta["tags"] = tags
    meta["last_login_check"] = {"at": _now(), **detail}
    store.update(profile_id, meta=meta)
    db.upsert_profile_row(store.get(profile_id))


def check_login(profile_id: str, *, urls: list[str] | None = None, headless: bool = True) -> dict[str, Any]:
    """静默打开目标 URL，用已保存 cookies 判断是否仍登录.

    启发式：
      - HTTP 最终落到 login/signin/auth → 失效
      - 页面含 password 输入且 URL 像登录页 → 失效
      - 否则视为可能有效
    """
    store = ProfileStore()
    prof = store.get(profile_id)
    watch = get_watch(profile_id)
    targets = urls or list(watch.get("urls") or [])
    if not targets:
        # fallback meta.tabs first http
        targets = [t for t in (prof.meta or {}).get("tabs") or [] if str(t).startswith("http")][:3]
    if not targets:
        return {"ok": False, "message": "no watch urls configured", "profile_id": profile_id}

    state = cookies_mod.load_pending_storage_state(profile_id) or cookies_mod._live_storage(profile_id)
    results: list[dict[str, Any]] = []
    need = False

    # prefer live page if running
    live_ctx = None
    try:
        from mozilla_manager.engines import chromium as chromium_mod

        run = getattr(chromium_mod, "_RUNS", {}).get(profile_id)
        if run:
            live_ctx = run.get("context")
    except Exception:
        live_ctx = None

    def eval_page(page, url: str) -> dict[str, Any]:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        final = page.url
        title = ""
        try:
            title = page.title()
        except Exception:
            pass
        low = (final or "").lower()
        login_hint = any(k in low for k in ("/login", "/signin", "/sign-in", "/auth", "/account/login", "passport"))
        has_pwd = False
        try:
            has_pwd = page.locator('input[type="password"]').count() > 0
        except Exception:
            pass
        # cookie presence for domain
        host = urlparse(url).hostname or ""
        cookie_hit = 0
        try:
            for c in page.context.cookies():
                dom = (c.get("domain") or "").lstrip(".")
                if host.endswith(dom) or dom.endswith(host):
                    cookie_hit += 1
        except Exception:
            pass
        expired = login_hint or (has_pwd and login_hint)
        # softer: login path definitely expired
        if login_hint:
            expired = True
        return {
            "url": url,
            "final_url": final,
            "title": title,
            "login_hint": login_hint,
            "has_password_field": has_pwd,
            "cookie_hit": cookie_hit,
            "expired": expired,
        }

    if live_ctx is not None:
        page = live_ctx.new_page()
        try:
            for u in targets:
                try:
                    results.append(eval_page(page, u))
                except Exception as e:
                    results.append({"url": u, "error": str(e), "expired": True})
        finally:
            try:
                page.close()
            except Exception:
                pass
    else:
        # ephemeral context with cookies only (no full profile lock)
        os_environ_ok = True
        try:
            import os
            from mozilla_manager.paths import BROWSERS_DIR

            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR))
            try:
                from patchright.sync_api import sync_playwright
            except Exception:
                from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            try:
                browser = pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
                ctx_kwargs: dict[str, Any] = {}
                if state:
                    # can't pass storage_state file easily without write; use add_cookies after
                    pass
                context = browser.new_context()
                if state and state.get("cookies"):
                    try:
                        norm = []
                        for c in state["cookies"]:
                            n = cookies_mod._normalize_cookie(c)
                            if n:
                                if n.get("domain") is None:
                                    n.pop("domain", None)
                                norm.append(n)
                        if norm:
                            context.add_cookies(norm)
                    except Exception:
                        pass
                page = context.new_page()
                for u in targets:
                    try:
                        results.append(eval_page(page, u))
                    except Exception as e:
                        results.append({"url": u, "error": str(e), "expired": True})
                context.close()
                browser.close()
            finally:
                pw.stop()
        except Exception as e:
            return {"ok": False, "profile_id": profile_id, "error": str(e), "results": results}

    need = any(r.get("expired") for r in results) or any(r.get("error") for r in results)
    # if all have cookie_hit and none expired → ok
    if results and all((not r.get("expired") and not r.get("error")) for r in results):
        need = False
    detail = {"results": results, "need_relogin": need}
    _mark(profile_id, need, detail)
    db.audit("login_health_check", profile_id, detail)
    # notification file under logs
    ensure_layout()
    note = {
        "profile_id": profile_id,
        "at": _now(),
        "need_relogin": need,
        "results": results,
    }
    npath = safe_resolve(ROOT / "logs" / f"login_health_{profile_id}.json")
    npath.write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "profile_id": profile_id, "need_relogin": need, "results": results, "notify": str(npath.relative_to(ROOT))}


def check_due(*, force: bool = False) -> list[dict[str, Any]]:
    """Run checks for profiles whose interval elapsed."""
    from datetime import datetime, timedelta

    out = []
    for prof in ProfileStore().list():
        watch = (prof.meta or {}).get("login_watch") or {}
        urls = watch.get("urls") or []
        if not urls:
            continue
        interval = float(watch.get("interval_hours") or 24)
        last = ((prof.meta or {}).get("last_login_check") or {}).get("at") or ""
        due = force
        if not due and last:
            try:
                ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
                due = datetime.now(timezone.utc) - ts > timedelta(hours=interval)
            except Exception:
                due = True
        elif not last:
            due = True
        if due:
            out.append(check_login(prof.id, urls=urls))
        else:
            out.append({"ok": True, "skipped": True, "profile_id": prof.id})
    return out
