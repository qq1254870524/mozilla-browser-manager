"""Execute RPA workflow steps against a profile browser context."""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mozilla_manager.paths import RPA_RUNS_DIR, LOG_DIR, ensure_layout, safe_resolve
from mozilla_manager.store import ProfileStore
from mozilla_manager.engines.sync_bridge import call_in_profile_thread

from .store import load_workflow


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_page(profile_id: str, *, headless: bool = True, start_if_needed: bool = True):
    """Reuse running chromium context or launch ephemeral."""
    from mozilla_manager.engines import chromium as chromium_mod

    run = getattr(chromium_mod, "_RUNS", {}).get(profile_id)
    if run and run.get("context"):
        ctx = run["context"]
        page = run.get("page") or (ctx.pages[0] if ctx.pages else ctx.new_page())
        return page, False, None

    if not start_if_needed:
        raise RuntimeError(f"profile {profile_id} not running")

    # launch via profiles module (non-blocking check page off)
    from mozilla_manager.modules import profiles as profiles_mod

    res = profiles_mod.launch(profile_id, headless=headless, open_check=False, skip_preflight=True, start_mihomo=True)
    if not res.get("ok"):
        raise RuntimeError(f"launch failed: {res}")
    run = getattr(chromium_mod, "_RUNS", {}).get(profile_id)
    if not run or not run.get("context"):
        raise RuntimeError("launch ok but no context")
    ctx = run["context"]
    page = run.get("page") or (ctx.pages[0] if ctx.pages else ctx.new_page())
    return page, True, None


def _run_step(page, step: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    action = step.get("action")
    t0 = time.perf_counter()
    out: dict[str, Any] = {"action": action, "ok": True}
    try:
        if action in ("goto", "open", "navigate"):
            url = step.get("url") or step.get("value")
            page.goto(str(url), wait_until=step.get("wait_until") or "domcontentloaded", timeout=int(step.get("timeout") or 60000))
            out["url"] = page.url
        elif action in ("click",):
            sel = step.get("selector") or step.get("css")
            page.click(sel, timeout=int(step.get("timeout") or 15000))
            out["selector"] = sel
        elif action in ("fill", "type", "input"):
            sel = step.get("selector") or step.get("css")
            val = step.get("value") if "value" in step else step.get("text", "")
            if action == "type":
                page.click(sel, timeout=int(step.get("timeout") or 15000))
                page.keyboard.type(str(val), delay=int(step.get("delay") or 20))
            else:
                page.fill(sel, str(val), timeout=int(step.get("timeout") or 15000))
            out["selector"] = sel
        elif action in ("press", "key"):
            page.keyboard.press(str(step.get("key") or step.get("value") or "Enter"))
        elif action in ("scroll",):
            dy = int(step.get("dy") or step.get("y") or 800)
            dx = int(step.get("dx") or step.get("x") or 0)
            page.mouse.wheel(dx, dy)
            out["dx"] = dx
            out["dy"] = dy
        elif action in ("wait", "sleep"):
            ms = int(step.get("ms") or step.get("timeout") or 1000)
            if step.get("selector"):
                page.wait_for_selector(step["selector"], timeout=ms)
            else:
                page.wait_for_timeout(ms)
            out["ms"] = ms
        elif action in ("screenshot", "shot"):
            name = step.get("name") or f"shot_{int(time.time())}.png"
            path = safe_resolve(run_dir / name)
            page.screenshot(path=str(path), full_page=bool(step.get("full_page")))
            out["path"] = str(path)
        elif action in ("evaluate", "js"):
            expr = step.get("script") or step.get("value") or step.get("js") or "() => document.title"
            # support function string
            if expr.strip().startswith("()") or expr.strip().startswith("async"):
                val = page.evaluate(expr)
            else:
                val = page.evaluate(f"() => ({expr})")
            out["result"] = val
        elif action in ("totp", "totp_fill", "2fa"):
            from mozilla_manager.modules import totp_svc

            aid = step.get("account_id") or step.get("totp_id")
            if not aid:
                raise ValueError("totp step needs account_id")
            info = totp_svc.fill_script(aid, selector=step.get("selector") or totp_svc.fill_script.__defaults__[0] if False else 'input[autocomplete="one-time-code"], input[name*="otp" i], input[name*="totp" i], input[id*="otp" i]')
            # simpler:
            info = totp_svc.code_for(aid)
            sel = step.get("selector") or 'input[autocomplete="one-time-code"], input[name*="otp" i], input[name*="totp" i], input[id*="otp" i]'
            page.fill(sel, info["code"], timeout=int(step.get("timeout") or 15000))
            out["totp_id"] = aid
            out["code_len"] = len(info["code"])
        elif action in ("select", "select_option"):
            page.select_option(step.get("selector"), step.get("value"))
        elif action in ("hover",):
            page.hover(step.get("selector"))
        elif action in ("reload",):
            page.reload(wait_until="domcontentloaded")
        else:
            raise ValueError(f"unknown action: {action}")
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
    out["ms"] = int((time.perf_counter() - t0) * 1000)
    return out


def run_workflow(
    wf_id: str,
    *,
    profile_id: str | None = None,
    headless: bool = True,
    stop_on_error: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_layout()
    wf = load_workflow(wf_id)
    pid = profile_id or wf.get("profile_id")
    if not pid:
        raise ValueError("profile_id required (arg or workflow.profile_id)")
    # validate profile exists
    ProfileStore().get(pid)

    run_id = f"{wf_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = safe_resolve(RPA_RUNS_DIR / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        return {"ok": True, "dry_run": True, "workflow": wf_id, "profile_id": pid, "steps": len(wf.get("steps") or [])}

    def _execute():
        page, launched, _ = _get_page(pid, headless=headless, start_if_needed=True)
        results = []
        ok = True
        for step in wf.get("steps") or []:
            r = _run_step(page, step, run_dir)
            results.append(r)
            if not r.get("ok"):
                ok = False
                if stop_on_error:
                    break
        return page, launched, results, ok

    page, launched, results, ok = call_in_profile_thread(pid, _execute, timeout=600.0)

    report = {
        "ok": ok,
        "run_id": run_id,
        "workflow_id": wf_id,
        "profile_id": pid,
        "launched_for_run": launched,
        "started_at": _now(),
        "steps": results,
        "run_dir": str(run_dir.relative_to(run_dir.parents[2])) if False else str(run_dir),
    }
    # relativize under ROOT
    try:
        from mozilla_manager.paths import ROOT

        report["run_dir"] = str(run_dir.relative_to(ROOT))
    except Exception:
        report["run_dir"] = str(run_dir)

    (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        log = safe_resolve(LOG_DIR / "rpa" / f"{run_id}.json")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    try:
        from mozilla_manager import db

        db.audit("rpa_run", pid, {"workflow": wf_id, "ok": ok, "run_id": run_id})
    except Exception:
        pass
    return report
