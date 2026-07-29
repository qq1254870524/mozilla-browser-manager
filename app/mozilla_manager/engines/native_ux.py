"""Native UX helpers: system cursor look + optional comfort Chrome.

Max anti-detect default: bundled Chromium + stealth_v6 + humanize; free window resize (no lock_viewport jank).
Comfort/native Chrome is opt-in via meta.use_system_chrome / stealth_level=comfort.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any


def native_cursor_init_script() -> str:
    """Keep OS native cursor. Lightweight — no permanent timers (was causing jank)."""
    return r"""
(() => {
  if (window.__MOZILLA_NATIVE_CURSOR__) return;
  window.__MOZILLA_NATIVE_CURSOR__ = true;

  const killOverlays = () => {
    try {
      const sels = [
        '#camoufox-cursor', '#cfx-cursor', '.camoufox-cursor', '.humanize-cursor',
        '[data-camoufox-cursor]', '[data-humanize-cursor]', 'div[id*="virtual-cursor"]',
        '#cursor', '.cursor-agent', '[class*="fake-cursor"]'
      ];
      for (const s of sels) {
        document.querySelectorAll(s).forEach((el) => { try { el.remove(); } catch (e) {} });
      }
    } catch (e) {}
  };

  const fixRootCursor = () => {
    try {
      for (const el of [document.documentElement, document.body]) {
        if (el && el.style && el.style.cursor === 'none') el.style.removeProperty('cursor');
      }
    } catch (e) {}
  };

  const run = () => { killOverlays(); fixRootCursor(); };
  run();
  try {
    document.addEventListener('DOMContentLoaded', run, { once: true });
    // short burst only — do NOT leave MutationObserver/setInterval forever
    let n = 0;
    const mo = new MutationObserver(() => {
      run();
      if (++n > 20) { try { mo.disconnect(); } catch (e) {} }
    });
    mo.observe(document.documentElement || document, { childList: true, subtree: true });
    setTimeout(() => { try { mo.disconnect(); } catch (e) {} }, 4000);
  } catch (e) {}
})();
"""


def chromium_pointer_options(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = meta or {}
    if meta.get("is_mobile") or meta.get("mobile"):
        return {"has_touch": True, "is_mobile": True}
    return {"has_touch": False, "is_mobile": False}


def camoufox_cursor_options(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Humanize movement OK; software cursor appearance always OFF unless explicitly requested."""
    meta = meta or {}
    opts: dict[str, Any] = {}
    # Default ON: humanize mouse *paths* (anti-detect), but never change cursor *look*
    if meta.get("humanize") is False:
        opts["humanize"] = False
    elif meta.get("humanize") is True or isinstance(meta.get("humanize"), (int, float)):
        opts["humanize"] = meta.get("humanize")
    else:
        opts["humanize"] = True  # default enable path humanize
    cfg = dict(meta.get("camoufox_config") or {})
    # Appearance: only show fake cursor if user explicitly asks
    explicit = meta.get("show_cursor", meta.get("showcursor", None))
    cfg["showcursor"] = bool(explicit) if explicit is not None else False
    opts["config"] = cfg
    return opts


def find_system_chrome() -> Path | None:
    """Locate real Google Chrome / Chromium (not Chrome for Testing)."""
    env = os.environ.get("MOZILLA_CHROME_PATH") or os.environ.get("CHROME_PATH")
    if env:
        p = Path(env)
        if p.is_file():
            return p
    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            Path(pf) / "Google/Chrome/Application/chrome.exe",
            Path(pf86) / "Google/Chrome/Application/chrome.exe",
            Path(local) / "Google/Chrome/Application/chrome.exe" if local else Path(),
            Path(pf) / "Chromium/Application/chrome.exe",
            Path(local) / "Chromium/Application/chrome.exe" if local else Path(),
            Path(pf) / "Microsoft/Edge/Application/msedge.exe",
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    else:
        for name in (
            "google-chrome-stable", "google-chrome", "chromium-browser", "chromium", "chrome",
        ):
            import shutil
            w = shutil.which(name)
            if w:
                candidates.append(Path(w))
        candidates.extend([
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/chromium"),
        ])
    for c in candidates:
        try:
            if c and c.is_file():
                return c
        except Exception:
            continue
    return None


def is_comfort_mode(meta: dict[str, Any] | None = None) -> bool:
    """Comfort/native UX mode (weaker stealth). Default is max anti-detect."""
    meta = meta or {}
    level = str(meta.get("stealth_level") or "max").strip().lower()
    if level in ("comfort", "native", "ux"):
        return True
    if meta.get("native_window") is True:
        return True
    return False


def want_lock_viewport(meta: dict[str, Any] | None = None) -> bool:
    """Whether to pin Playwright viewport (causes resize jank if True).

    Default False: native free-resize window (smooth drag). Screen/fingerprint
    still spoofed by stealth init scripts — real users also resize windows.
    Opt-in lock: meta.lock_viewport=true (automation / fixed FP box).
    """
    meta = meta or {}
    if "lock_viewport" in meta:
        return bool(meta.get("lock_viewport"))
    if meta.get("fixed_viewport") is True:
        return True
    # default free resize — lock was the main "一帧一帧" drag symptom
    return False


def resolve_chromium_launch_binary(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Chromium binary for launch.

    **Default = max anti-detect**: Playwright/Patchright *bundled* Chromium
    (version controlled, matches fingerprint / stealth patches).

    Comfort opt-in (weaker stealth, native title bar):
      meta.use_system_chrome=true | stealth_level=comfort | native_window=true

    Returns kwargs fragment: channel= and/or executable_path=
    meta.use_bundled_chromium=true / chrome_for_testing -> force bundled
    meta.chrome_path / executable_path -> explicit path
    """
    meta = meta or {}
    out: dict[str, Any] = {}
    # Force bundled (max stealth / controlled binary)
    if meta.get("use_bundled_chromium") is True or meta.get("chrome_for_testing"):
        out["_browser_label"] = "bundled-chromium"
        return out
    # Explicit path always wins
    explicit = meta.get("chrome_path") or meta.get("executable_path")
    if explicit:
        p = Path(str(explicit))
        if p.is_file():
            out["executable_path"] = str(p)
            out["_browser_label"] = p.name
            return out
    # System Chrome only when explicitly requested or comfort mode
    use_sys = meta.get("use_system_chrome")
    if use_sys is None:
        # default False for max stealth; comfort mode may prefer system chrome
        use_sys = bool(is_comfort_mode(meta)) and not bool(meta.get("use_bundled_chromium"))
    if use_sys:
        found = find_system_chrome()
        if found is not None:
            out["executable_path"] = str(found)
            out["_browser_label"] = found.name
            return out
        out["channel"] = "chrome"
        out["_browser_label"] = "channel:chrome"
        return out
    # Max stealth default: let driver use its bundled Chromium
    out["_browser_label"] = "bundled-chromium"
    return out
