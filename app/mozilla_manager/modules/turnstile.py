"""v5 Cloudflare Turnstile / CF 盾 — 内置 turnstile-harvester1.

Vendor: runtime/vendors/turnstile-harvester1
Source: https://github.com/qq1254870524/turnstile-harvester1
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Optional

from mozilla_manager import db
from mozilla_manager.paths import ROOT, TURNSTILE_VENDOR_DIR, ensure_layout, safe_resolve


def vendor_dir() -> Path:
    ensure_layout()
    return safe_resolve(TURNSTILE_VENDOR_DIR)


def ensure_vendor() -> dict[str, Any]:
    d = vendor_dir()
    ok = (d / "turnstile_harvester.py").exists()
    return {
        "ok": ok,
        "path": str(d.relative_to(ROOT)) if ok or d.exists() else str(TURNSTILE_VENDOR_DIR),
        "module": "turnstile_harvester.py",
        "repo": "https://github.com/qq1254870524/turnstile-harvester1",
    }


def _load_harvester():
    info = ensure_vendor()
    if not info["ok"]:
        raise FileNotFoundError(
            f"turnstile-harvester1 missing at {TURNSTILE_VENDOR_DIR}. "
            "Place vendor under runtime/vendors/turnstile-harvester1"
        )
    vdir = str(vendor_dir())
    if vdir not in sys.path:
        sys.path.insert(0, vdir)
    import turnstile_harvester as th  # type: ignore

    return th


class PlaywrightPageAdapter:
    """Adapt Playwright Page to harvester's DrissionPage-like surface (run_js/ele/url/title)."""

    def __init__(self, page: Any):
        self._page = page

    @property
    def url(self) -> str:
        try:
            return str(self._page.url or "")
        except Exception:
            return ""

    @property
    def title(self) -> str:
        try:
            return str(self._page.title() or "")
        except Exception:
            return ""

    def run_js(self, script: str, *args: Any) -> Any:
        script = str(script or "")
        # Playwright evaluate
        if args:
            # harvester inject uses arguments[0]
            wrapper = f"""(…args) => {{
  const arguments = args;
  {script}
}}"""
            # fix ellipsis for py
            wrapper = (
                "(...args) => {\n"
                "  const arguments = args;\n"
                f"{script}\n"
                "}"
            )
            try:
                return self._page.evaluate(wrapper, list(args))
            except Exception:
                # simpler single-arg form
                return self._page.evaluate(
                    f"(arg0) => {{ const arguments = [arg0]; {script} }}",
                    args[0],
                )
        # many scripts are bare statements with return
        body = script.strip()
        if body.startswith("return") or "return " in body[:40]:
            fn = f"() => {{ {body} }}"
        elif body.startswith("try") or "document." in body or "window." in body:
            fn = f"() => {{ {body} }}"
        else:
            fn = f"() => {{ {body} }}"
        return self._page.evaluate(fn)

    def ele(self, selector: str, timeout: float = 2):
        """Minimal element stub for click/parent/shadow interactions."""
        sel = selector
        # DrissionPage style @name=x
        if sel.startswith("@name="):
            name = sel.split("=", 1)[1]
            sel = f'input[name="{name}"]'
        try:
            loc = self._page.locator(sel).first
            if loc.count() == 0:
                return None
            return _ElementAdapter(loc, self._page)
        except Exception:
            return None


class _ElementAdapter:
    def __init__(self, locator: Any, page: Any):
        self._loc = locator
        self._page = page

    def parent(self):
        try:
            handle = self._loc.element_handle()
            if not handle:
                return None
            # return a thin wrapper around parent via JS evaluate
            return _ParentAdapter(self._page, self._loc)
        except Exception:
            return None

    def click(self):
        try:
            self._loc.click(timeout=2000)
        except Exception:
            pass


class _ParentAdapter:
    def __init__(self, page: Any, child_loc: Any):
        self._page = page
        self._child = child_loc
        self.shadow_root = self

    def ele(self, selector: str):
        # best-effort: find iframe near turnstile
        try:
            iframe = self._page.locator("iframe[src*='turnstile'], iframe[src*='challenges.cloudflare']").first
            if iframe.count() == 0:
                return None
            return _IframeAdapter(iframe)
        except Exception:
            return None


class _IframeAdapter:
    def __init__(self, locator: Any):
        self._loc = locator

    def click(self):
        try:
            self._loc.click(timeout=2000)
        except Exception:
            try:
                self._loc.focus()
            except Exception:
                pass


def adapt_page(page: Any) -> PlaywrightPageAdapter:
    if isinstance(page, PlaywrightPageAdapter):
        return page
    return PlaywrightPageAdapter(page)


def detect_cf(page: Any) -> dict[str, Any]:
    """Quick detect whether current document is CF challenge / Turnstile host page."""
    real = page._page if isinstance(page, PlaywrightPageAdapter) else page
    try:
        url = str(getattr(real, "url", "") or "")
    except Exception:
        url = ""
    if not str(url).lower().startswith(("http://", "https://")):
        return {"cf": False, "reason": "non-http", "url": url}
    low = url.lower()
    if "challenges.cloudflare.com" in low or "/cdn-cgi/challenge" in low:
        return {"cf": True, "reason": "url", "url": url}
    try:
        info = real.evaluate(
            """() => {
  const out = { title: document.title || '', hasTurnstile: false, hasChallenge: false, textHit: false };
  out.hasTurnstile = !!(document.querySelector('input[name="cf-turnstile-response"], .cf-turnstile, div.cf-turnstile, iframe[src*="challenges.cloudflare"], iframe[src*="/cdn-cgi/challenge"]'));
  // data-sitekey alone is too broad (many non-CF widgets). Require CF-ish context.
  if (!out.hasTurnstile) {
    const sk = document.querySelector('[data-sitekey]');
    if (sk && (sk.className || '').toLowerCase().includes('turnstile')) out.hasTurnstile = true;
    if (sk && sk.closest && sk.closest('.cf-turnstile, .cf-challenge, #challenge-form')) out.hasTurnstile = true;
  }
  out.hasChallenge = !!(document.querySelector('#challenge-form, #challenge-running, #cf-challenge-running, .cf-browser-verification, .challenge-platform, #cf-wrapper'));
  const t = (out.title || '').toLowerCase().trim();
  // NEVER match bare "cloudflare" in title — false positives freeze worker & break net
  if (t === 'just a moment...' || t === 'just a moment' || t.startsWith('just a moment')) out.textHit = true;
  if (t.includes('attention required') && t.includes('cloudflare')) out.textHit = true;
  const b = ((document.body && document.body.innerText) || '').slice(0, 1200).toLowerCase();
  if (/checking your browser before|verify you are human|enable javascript and cookies to continue|performing security verification|sorry, you have been blocked/i.test(b)) out.textHit = true;
  return out;
}"""
        )
    except Exception as e:
        return {"cf": False, "error": str(e), "url": url}
    cf = bool(info.get("hasTurnstile") or info.get("hasChallenge") or info.get("textHit"))
    return {"cf": cf, "url": url, **(info if isinstance(info, dict) else {"info": info})}


def wait_cf(page: Any, timeout: float = 45.0, log: Optional[Callable[[str], None]] = None) -> dict[str, Any]:
    real = page._page if isinstance(page, PlaywrightPageAdapter) else page
    try:
        url = str(getattr(real, "url", "") or "")
    except Exception:
        url = ""
    if not str(url).lower().startswith(("http://", "https://")):
        return {"ok": True, "passed": True, "skipped": True, "reason": "non-http", "url": url}
    # If clearly not CF, don't burn full timeout
    try:
        det = detect_cf(page)
        if not det.get("cf"):
            return {"ok": True, "passed": True, "skipped": True, "reason": "no-cf", "detect": det, "url": url}
    except Exception:
        det = {}
    th = _load_harvester()
    adapter = adapt_page(page)
    ok = th.wait_cloudflare_passthrough(adapter, timeout=timeout, log=log or (lambda *_: None))
    db.audit("turnstile_wait_cf", detail={"ok": ok, "timeout": timeout, "url": url})
    return {"ok": ok, "passed": ok, "url": url, "detect": det}


def harvest_token(page: Any, log: Optional[Callable[[str], None]] = None, max_rounds: int = 20) -> dict[str, Any]:
    th = _load_harvester()
    adapter = adapt_page(page)
    # always try wait first lightly
    try:
        th.wait_cloudflare_passthrough(adapter, timeout=8, log=log)
    except Exception:
        pass
    token = th.get_turnstile_token(adapter, log=log or print, max_rounds=max_rounds)
    # inject via playwright-friendly path
    injected = inject_token(page, token)
    db.audit("turnstile_harvest", detail={"token_len": len(token), "injected": injected})
    return {"ok": True, "token": token, "token_len": len(token), "injected": injected, "redacted": False}


def inject_token(page: Any, token: str) -> bool:
    token = str(token or "").strip()
    if not token:
        return False
    # Prefer direct Playwright evaluate (more reliable than arguments[] shim)
    try:
        real = page._page if isinstance(page, PlaywrightPageAdapter) else page
        ok = real.evaluate(
            """(token) => {
  const input = document.querySelector('input[name="cf-turnstile-response"]');
  if (!input) return false;
  const proto = HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (setter) setter.call(input, token); else input.value = token;
  input.dispatchEvent(new Event('input', {bubbles:true}));
  input.dispatchEvent(new Event('change', {bubbles:true}));
  return String(input.value||'').length >= 80;
}""",
            token,
        )
        return bool(ok)
    except Exception:
        try:
            th = _load_harvester()
            return bool(th.inject_turnstile_value(adapt_page(page), token))
        except Exception:
            return False


def pass_cf_on_page(page: Any, *, timeout: float = 12.0, harvest: bool = False) -> dict[str, Any]:
    """High-level: detect CF → wait interstitial → optional token harvest.

    Always-ready design: non-http / no-challenge pages return immediately.
    """
    det = detect_cf(page)
    out: dict[str, Any] = {"detect": det}
    if det.get("reason") == "non-http" or (not det.get("cf") and det.get("reason") != "url"):
        # still allow explicit harvest if turnstile widget present was false
        if not det.get("cf"):
            out["ok"] = True
            out["skipped"] = True
            out["reason"] = det.get("reason") or "no-cf"
            return out
    w = wait_cf(page, timeout=timeout)
    out["wait"] = w
    if harvest and det.get("cf"):
        try:
            # only harvest when challenge/widget likely present
            out["harvest"] = harvest_token(page)
            out["ok"] = bool(w.get("ok")) or bool(out["harvest"].get("ok"))
        except Exception as e:
            out["harvest_error"] = str(e)
            out["ok"] = bool(w.get("ok"))
    else:
        out["ok"] = bool(w.get("ok"))
    return out


def solve_in_profile(
    profile_id: str,
    url: str,
    *,
    headless: bool = False,
    timeout: float = 60.0,
    harvest: bool = True,
) -> dict[str, Any]:
    """Open URL inside running profile context, or ephemeral browser, and pass CF."""
    page = None
    owns = False
    try:
        from mozilla_manager.engines import chromium as chromium_mod

        run = getattr(chromium_mod, "_RUNS", {}).get(profile_id)
        if run and run.get("context"):
            page = run["context"].new_page()
        else:
            # ephemeral browser (profile optional — allow "ephemeral"/missing)
            import os
            from mozilla_manager.paths import BROWSERS_DIR

            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR))
            if profile_id and profile_id not in ("ephemeral", "-", "none"):
                try:
                    from mozilla_manager.store import ProfileStore
                    ProfileStore().get(profile_id)  # validate exists when given
                except Exception:
                    # still allow ephemeral launch
                    pass
            try:
                from patchright.sync_api import sync_playwright
            except Exception:
                from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            owns = True
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()
            # stash for cleanup
            solve_in_profile._ephemeral = (pw, browser, context)  # type: ignore
        page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
        result = pass_cf_on_page(page, timeout=timeout, harvest=harvest)
        result["url"] = url
        result["final_url"] = page.url
        result["profile_id"] = profile_id
        return result
    finally:
        if owns:
            try:
                pw, browser, context = solve_in_profile._ephemeral  # type: ignore
                context.close()
                browser.close()
                pw.stop()
            except Exception:
                pass
