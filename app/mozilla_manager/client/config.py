"""Client config — always under Mozilla ROOT."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from mozilla_manager.paths import ROOT, ensure_layout, p, safe_resolve


@dataclass
class ClientConfig:
    host: str = "127.0.0.1"
    port: int = 17888
    title: str = "Mozilla 浏览器管理器"
    width: int = 1440
    height: int = 920
    min_width: int = 1100
    min_height: int = 700
    # auto open native window after server ready
    open_window: bool = True
    # if webview unavailable, open system browser as last resort (still started via client process)
    allow_system_browser_fallback: bool = False
    # show tk control center when webview missing
    tk_shell: bool = True
    # server
    server_timeout_sec: float = 30.0
    reload: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"


def config_path():
    ensure_layout()
    d = safe_resolve(p("data", "client"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "client.json"


def load_config() -> ClientConfig:
    path = config_path()
    if not path.exists():
        cfg = ClientConfig()
        save_config(cfg)
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ClientConfig()
    known = {f.name for f in ClientConfig.__dataclass_fields__.values()}  # type: ignore
    data = {k: v for k, v in raw.items() if k in known}
    return ClientConfig(**data)


def save_config(cfg: ClientConfig) -> None:
    path = config_path()
    path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
