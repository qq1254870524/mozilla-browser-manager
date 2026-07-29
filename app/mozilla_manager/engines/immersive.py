"""v10.3 沉浸式浏览器：轻量去标题装饰，保留可流畅缩放。

默认开启（meta.immersive=true）。关闭：
  meta.immersive=false | meta.title_bar=true | meta.frameless=false | stealth_level=comfort

性能约束（重要）：
  - 绝不能去掉 WS_THICKFRAME，否则 Windows 拖拽缩放会「一帧一帧」卡死
  - 默认不做激进无边框；仅弱化标题栏装饰
  - meta.immersive_hard=true 才启用更激进去边框（可能影响缩放手感）
"""
from __future__ import annotations

import platform
import threading
import time
from typing import Any


def want_immersive(meta: dict[str, Any] | None = None) -> bool:
    meta = meta or {}
    if meta.get("title_bar") is True:
        return False
    if meta.get("frameless") is False:
        return False
    if meta.get("immersive") is False:
        return False
    if meta.get("immersive") is True or meta.get("frameless") is True:
        return True
    level = str(meta.get("stealth_level") or "max").strip().lower()
    if level in ("comfort", "native", "ux"):
        return False
    return True


def want_hard_frameless(meta: dict[str, Any] | None = None) -> bool:
    """Aggressive no-border (can jank resize). Off by default."""
    meta = meta or {}
    return bool(meta.get("immersive_hard") or meta.get("hard_frameless"))


def chromium_immersive_args(
    meta: dict[str, Any] | None = None,
    *,
    headless: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> list[str]:
    if headless or not want_immersive(meta):
        return []
    meta = meta or {}
    # Keep light — avoid flags that hurt compositor/resize smoothness
    args = [
        "--disable-features=TranslateUI,TabHoverCardImages",
        "--no-default-browser-check",
        "--no-first-run",
    ]
    if meta.get("immersive_app"):
        start = str(meta.get("immersive_app_url") or "about:blank").strip() or "about:blank"
        args.append(f"--app={start}")
    # Do NOT force duplicate window-size here when geometry is handled elsewhere
    if meta.get("window_x") is not None and meta.get("window_y") is not None:
        try:
            args.append(f"--window-position={int(meta['window_x'])},{int(meta['window_y'])}")
        except Exception:
            pass
    return args


def camoufox_immersive_prefs(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    if not want_immersive(meta):
        return {}
    return {
        "browser.tabs.inTitlebar": 1,
        "browser.tabs.drawInTitlebar": True,
        "browser.uidensity": 1,
        "browser.toolbars.bookmarks.visibility": "never",
    }


def stealth_screen_offsets(meta: dict[str, Any] | None = None) -> dict[str, int]:
    if want_immersive(meta) and want_hard_frameless(meta):
        return {"toolbar": 0, "avail_offset_y": 0, "frame_border": 0}
    # Normal window chrome offsets (realistic)
    return {"toolbar": 40, "avail_offset_y": 40, "frame_border": 8}


def _windows_enum_hwnds_for_pid(pid: int) -> list[int]:
    import ctypes

    user32 = ctypes.windll.user32
    found: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @WNDENUMPROC
    def _cb(hwnd, _lparam):  # type: ignore
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            proc = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
            if int(proc.value) == int(pid):
                found.append(int(hwnd))
        except Exception:
            pass
        return True

    user32.EnumWindows(_cb, 0)
    return found


def strip_titlebar_windows(pid: int, *, hard: bool = False) -> dict[str, Any]:
    """Win32 window chrome tweak.

    soft (default): keep WS_THICKFRAME so resize stays buttery.
    hard: remove thick frame too (legacy immersive_hard — may stutter on drag-resize).
    """
    if platform.system() != "Windows":
        return {"ok": False, "reason": "not-windows"}
    try:
        import ctypes
        from ctypes import wintypes
    except Exception as e:
        return {"ok": False, "reason": str(e)}

    user32 = ctypes.windll.user32
    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_SYSMENU = 0x00080000
    WS_BORDER = 0x00800000
    WS_DLGFRAME = 0x00400000
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_FRAMECHANGED = 0x0020

    is_64 = ctypes.sizeof(ctypes.c_void_p) == 8
    get_long = user32.GetWindowLongPtrW if is_64 else user32.GetWindowLongW
    set_long = user32.SetWindowLongPtrW if is_64 else user32.SetWindowLongW

    try:
        hwnds = _windows_enum_hwnds_for_pid(int(pid))
    except Exception as e:
        return {"ok": False, "reason": f"enum:{e}"}

    changed = []
    for hwnd in hwnds:
        try:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = int(rect.right - rect.left)
            h = int(rect.bottom - rect.top)
            if w < 400 or h < 300:
                continue
            style = int(get_long(hwnd, GWL_STYLE))
            if hard:
                # legacy aggressive — user opt-in only
                mask = (
                    WS_CAPTION
                    | WS_THICKFRAME
                    | WS_MINIMIZEBOX
                    | WS_MAXIMIZEBOX
                    | WS_SYSMENU
                    | WS_BORDER
                    | WS_DLGFRAME
                )
            else:
                # soft: only drop pure caption bit if present; ALWAYS keep thickframe
                # Removing SYSMENU alone can look odd; just clear DLGFRAME-ish caption chrome lightly
                # Practical approach: do NOT change style for soft mode (avoid jank).
                # Immersive soft = Chromium/Camoufox prefs only.
                continue
            new_style = style & ~mask
            if new_style == style:
                continue
            set_long(hwnd, GWL_STYLE, new_style)
            user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
            )
            changed.append({"hwnd": int(hwnd), "w": w, "h": h, "hard": hard})
        except Exception:
            continue
    return {"ok": bool(changed), "pid": int(pid), "windows": changed, "count": len(changed), "hard": hard}


def apply_immersive_to_browser_pid(
    pid: int | None,
    meta: dict[str, Any] | None = None,
    *,
    retries: int = 3,
    delay_sec: float = 0.3,
) -> dict[str, Any]:
    if not want_immersive(meta):
        return {"ok": False, "skipped": True, "reason": "immersive-off"}
    if not pid:
        return {"ok": False, "reason": "no-pid"}
    if platform.system() != "Windows":
        return {"ok": False, "skipped": True, "reason": f"os={platform.system()}"}

    hard = want_hard_frameless(meta)
    if not hard:
        # soft immersive: no Win32 style mutation (prevents resize stutter)
        return {"ok": True, "skipped": True, "reason": "soft-no-win32", "pid": int(pid)}

    last: dict[str, Any] = {"ok": False}

    def _run() -> None:
        nonlocal last
        for _ in range(max(1, retries)):
            last = strip_titlebar_windows(int(pid), hard=True)
            if last.get("ok"):
                return
            time.sleep(delay_sec)

    threading.Thread(target=_run, name=f"mm-immersive-{pid}", daemon=True).start()
    return {"ok": True, "scheduled": True, "pid": int(pid), "hard": True}


def snapshot_http_tabs(context: Any) -> list[str]:
    urls: list[str] = []
    try:
        pages = list(getattr(context, "pages", []) or [])
    except Exception:
        pages = []
    for page in pages:
        try:
            u = str(getattr(page, "url", "") or "")
            if u.startswith("http://") or u.startswith("https://"):
                if u not in urls:
                    urls.append(u)
        except Exception:
            continue
    return urls
