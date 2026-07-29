"""Tk desktop control-center shell (fallback when pywebview GUI backend missing).

Still a native program window — not "just open a webpage".
Provides modular status + actions; can open embedded UI instructions / optional browser.
"""
from __future__ import annotations

import threading
import webbrowser
from typing import Any, Callable

from mozilla_manager.client.config import ClientConfig
from mozilla_manager.paths import ROOT


def available() -> bool:
    try:
        import tkinter  # noqa: F401

        return True
    except Exception:
        return False


def run(cfg: ClientConfig, runtime, *, on_closed: Callable[[], None] | None = None) -> dict[str, Any]:
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title(cfg.title + " · 客户端")
    root.geometry(f"{min(cfg.width, 1100)}x{min(cfg.height, 720)}")
    root.minsize(900, 600)

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    main = ttk.Frame(root, padding=12)
    main.pack(fill=tk.BOTH, expand=True)

    header = ttk.Frame(main)
    header.pack(fill=tk.X)
    ttk.Label(header, text="Mozilla 浏览器管理器", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
    status_var = tk.StringVar(value="启动中…")
    ttk.Label(header, textvariable=status_var, foreground="#334155").pack(side=tk.RIGHT)

    ttk.Separator(main).pack(fill=tk.X, pady=8)

    # modular panels
    paned = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
    paned.pack(fill=tk.BOTH, expand=True)

    left = ttk.Frame(paned, padding=8)
    right = ttk.Frame(paned, padding=8)
    paned.add(left, weight=1)
    paned.add(right, weight=2)

    ttk.Label(left, text="功能模块", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
    modules = [
        ("环境管理", "profiles"),
        ("分组", "groups"),
        ("代理", "proxies"),
        ("订阅/节点", "subs"),
        ("系统诊断", "doctor"),
        ("工具箱 v10", "tools"),
    ]
    mod_list = tk.Listbox(left, height=16, exportselection=False)
    for name, _ in modules:
        mod_list.insert(tk.END, name)
    mod_list.pack(fill=tk.BOTH, expand=True, pady=6)
    mod_list.selection_set(0)

    info = tk.Text(right, height=20, wrap=tk.WORD, bg="#f8fafc", relief=tk.FLAT)
    info.pack(fill=tk.BOTH, expand=True)

    def write_info(text: str) -> None:
        info.delete("1.0", tk.END)
        info.insert(tk.END, text)

    def refresh_health() -> None:
        try:
            import urllib.request

            with urllib.request.urlopen(cfg.url() + "api/health", timeout=2) as r:
                body = r.read().decode("utf-8", errors="replace")
            status_var.set("后端在线 · " + cfg.url())
            write_info(
                f"ROOT: {ROOT}\n"
                f"API: {cfg.url()}\n"
                f"Health: {body}\n\n"
                "左侧选择模块后点「打开管理台」。\n"
                "完整 AdsPower 风格界面在内嵌/系统窗口中加载 Web 模块化前端：\n"
                "  ui/static/js/modules/*  ↔  api/routes/*  ↔  modules/*\n"
            )
        except Exception as e:
            status_var.set("后端未就绪")
            write_info(f"健康检查失败: {e}\nURL={cfg.url()}")

    def open_console() -> None:
        # Prefer pywebview secondary window if possible
        try:
            import webview

            idx = mod_list.curselection()
            view = modules[idx[0]][1] if idx else "profiles"
            url = cfg.url() + f"?view={view}"
            webview.create_window(cfg.title, url, width=cfg.width, height=cfg.height)
            # if loop not running, start; if already, just create
            try:
                webview.start()
            except Exception:
                # already started or backend missing — fall through
                if cfg.allow_system_browser_fallback:
                    webbrowser.open(url)
                else:
                    messagebox.showinfo(
                        "管理台",
                        f"请在已支持 GUI 的环境使用 pywebview 内嵌窗口。\n也可临时开启 allow_system_browser_fallback。\n\n{url}",
                    )
            return
        except Exception:
            pass
        url = cfg.url()
        if cfg.allow_system_browser_fallback:
            webbrowser.open(url)
        else:
            messagebox.showinfo(
                "管理台地址",
                f"桌面内嵌引擎不可用（常见于无显示的 WSL）。\n"
                f"后端已由本客户端进程拉起：\n{url}\n\n"
                f"在 Windows / 有桌面的 Ubuntu 上会直接打开原生窗口。\n"
                f"也可在 data/client/client.json 设置 allow_system_browser_fallback=true",
            )

    btns = ttk.Frame(main)
    btns.pack(fill=tk.X, pady=8)
    ttk.Button(btns, text="刷新状态", command=refresh_health).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="打开管理台", command=open_console).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="复制 API 地址", command=lambda: root.clipboard_clear() or root.clipboard_append(cfg.url())).pack(
        side=tk.LEFT, padx=4
    )

    def on_close() -> None:
        if on_closed:
            on_closed()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    # delayed health
    root.after(400, refresh_health)
    root.after(1500, refresh_health)

    root.mainloop()
    return {"ok": True, "engine": "tk-shell"}
