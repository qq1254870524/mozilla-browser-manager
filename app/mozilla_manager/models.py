from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EngineKind(str, Enum):
    CAMOUFOX = "camoufox"
    PLAYWRIGHT_CHROMIUM = "pw_chromium"


class ChromiumPatch(str, Enum):
    NONE = "none"
    PATCHRIGHT = "patchright"
    REBROWSER = "rebrowser"


class GeoLocation(BaseModel):
    latitude: float
    longitude: float
    accuracy: float = 50.0


class ProxyConfig(BaseModel):
    """One profile → one egress. Always browser-process scoped (never system proxy)."""

    mode: str = "none"  # none | socks5 | mihomo
    socks5: Optional[str] = None
    mihomo_port: Optional[int] = None
    node_name: Optional[str] = None
    # v2: proxy only applied to browser process (default True)
    browser_only: bool = True


class FingerprintConfig(BaseModel):
    """v2 fingerprint template baseline applied at launch."""

    template_id: str = "win11-chrome"
    platform: str = "Win32"  # navigator.platform
    oscpu: Optional[str] = "Windows NT 10.0; Win64; x64"
    user_agent: Optional[str] = None
    vendor: str = "Google Inc."
    renderer: str = "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)"
    vendor_webgl: str = "Google Inc. (NVIDIA)"
    fonts: list[str] = Field(
        default_factory=lambda: [
            "Arial",
            "Calibri",
            "Cambria",
            "Comic Sans MS",
            "Consolas",
            "Courier New",
            "Georgia",
            "Helvetica",
            "Impact",
            "Segoe UI",
            "Tahoma",
            "Times New Roman",
            "Trebuchet MS",
            "Verdana",
        ]
    )
    hardware_concurrency: int = 8
    device_memory: float = 8.0
    max_touch_points: int = 0
    color_depth: int = 24
    extra_init_script: Optional[str] = None


class EnvBinding(BaseModel):
    timezone_id: str = "UTC"
    locale: str = "en-US"
    languages: list[str] = Field(default_factory=lambda: ["en-US", "en"])
    geolocation: Optional[GeoLocation] = None
    user_agent: Optional[str] = None
    viewport_width: int = 1920
    viewport_height: int = 1080
    permissions: list[str] = Field(default_factory=lambda: ["geolocation"])
    # v2
    fingerprint: FingerprintConfig = Field(default_factory=FingerprintConfig)


class Profile(BaseModel):
    id: str
    name: str
    engine: EngineKind = EngineKind.PLAYWRIGHT_CHROMIUM
    chromium_patch: ChromiumPatch = ChromiumPatch.PATCHRIGHT
    user_data_dir: str
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    env: EnvBinding = Field(default_factory=EnvBinding)
    created_at: str = ""
    updated_at: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class LaunchResult(BaseModel):
    profile_id: str
    ok: bool
    pid: Optional[int] = None
    message: str = ""
    check_url: str = "https://browserleaks.com/ip"
