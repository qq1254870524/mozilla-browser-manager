"""v10 reports: diagnose/watchdog/jobs/dashboard export JSON+HTML."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import REPORTS_DIR, LOG_DIR, ROOT, ensure_layout, safe_resolve
from mozilla_manager.modules import ops_svc, jobs_svc, watchdog_svc, notify_svc


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_ops_report() -> dict[str, Any]:
    ensure_layout()
    report = {
        "format": "mozilla-report-v10",
        "generated_at": _now(),
        "dashboard": ops_svc.dashboard(),
        "history": ops_svc.history(limit=50),
        "jobs": jobs_svc.list_jobs(limit=50),
        "watchdogs": watchdog_svc.list_watchdogs(),
        "watchdog_status": watchdog_svc.status(),
        "notices": notify_svc.list_notices(limit=50),
    }
    return report


def _html(report: dict[str, Any]) -> str:
    dash = report.get("dashboard") or {}
    rows = []
    for j in report.get("jobs") or []:
        rows.append(
            f"<tr><td>{html.escape(str(j.get('id')))}</td><td>{html.escape(str(j.get('kind')))}</td>"
            f"<td>{html.escape(str(j.get('status')))}</td><td>{html.escape(str(j.get('summary') or ''))}</td></tr>"
        )
    wd_rows = []
    for w in report.get("watchdogs") or []:
        wd_rows.append(
            f"<tr><td>{html.escape(str(w.get('id')))}</td><td>{html.escape(str(w.get('kind')))}</td>"
            f"<td>{html.escape(str(w.get('profile_id')))}</td><td>{html.escape(str(w.get('last_ok')))}</td></tr>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><title>Mozilla Report</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}}
card{{display:block;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:12px 0}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid #e2e8f0;padding:8px;text-align:left;font-size:13px}}
.muted{{color:#64748b}} h1{{margin:0 0 8px}}
</style></head><body>
<h1>Mozilla 运维报表</h1>
<div class="muted">{html.escape(report.get('generated_at',''))}</div>
<card>
  <b>Dashboard</b>
  <div>环境 {dash.get('profiles')} · 运行 {dash.get('running')} · 需重登 {dash.get('need_relogin')} · 锁定 {dash.get('locked')} · 通知未读 {dash.get('notices_unread')} · 模板 {dash.get('packs')}</div>
  <div class="muted">{html.escape(str(dash.get('version')))}</div>
</card>
<card><b>Jobs</b><table><tr><th>ID</th><th>Kind</th><th>Status</th><th>Summary</th></tr>{''.join(rows) or '<tr><td colspan=4>无</td></tr>'}</table></card>
<card><b>Watchdogs</b><table><tr><th>ID</th><th>Kind</th><th>Profile</th><th>Last OK</th></tr>{''.join(wd_rows) or '<tr><td colspan=4>无</td></tr>'}</table></card>
</body></html>"""


def export_ops_report() -> dict[str, Any]:
    ensure_layout()
    report = build_ops_report()
    slug = _now_slug()
    jpath = safe_resolve(REPORTS_DIR / f"ops_{slug}.json")
    hpath = safe_resolve(REPORTS_DIR / f"ops_{slug}.html")
    jpath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    hpath.write_text(_html(report), encoding="utf-8")
    # mirror log
    try:
        lp = safe_resolve(LOG_DIR / "reports" / f"ops_{slug}.json")
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(jpath.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass
    return {
        "ok": True,
        "json": str(jpath.relative_to(ROOT)),
        "html": str(hpath.relative_to(ROOT)),
        "generated_at": report["generated_at"],
    }
