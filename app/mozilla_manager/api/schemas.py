"""Shared request/response schemas for API routers."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CreateProfileIn(BaseModel):
    name: str
    engine: str = "pw_chromium"
    patch: str = "patchright"
    socks5: str = ""
    mihomo_port: int = 0
    sub: str = "default"
    country: str = ""
    timezone_id: str = ""
    locale: str = ""
    lat: float = 0.0
    lon: float = 0.0
    auto_port: bool = False
    group: str = ""
    remark: str = ""
    tabs: list[str] = Field(default_factory=list)
    node_name: str = ""
    fingerprint_id: str = ""
    browser_only: bool = True
    auto_cf: bool = False  # 启动时内置 Turnstile/CF 过盾
    cf_timeout: float = 45.0


class UpdateProfileIn(BaseModel):
    name: Optional[str] = None
    engine: Optional[str] = None
    chromium_patch: Optional[str] = None
    proxy: Optional[dict[str, Any]] = None
    env: Optional[dict[str, Any]] = None
    meta: Optional[dict[str, Any]] = None


class SetProxyIn(BaseModel):
    mode: str
    socks5: str = ""
    mihomo_port: int = 0
    node: str = ""
    node_name: str = ""  # alias accepted by UI / scripts
    sub: str = ""  # mihomo subscription name
    auto_port: bool = False
    browser_only: bool = True

    def resolved_node(self) -> str:
        return (self.node_name or self.node or "").strip()


class BindCountryIn(BaseModel):
    country: str


class LaunchIn(BaseModel):
    headless: bool = False
    open_check: bool = True
    skip_preflight: bool = False
    require_proxy: bool = False


class SubImportIn(BaseModel):
    url: str
    name: str = "default"
    proxy_url: str | None = None  # optional socks5/http for region-denied providers
    via_node: str | None = None  # optional: pull via existing mihomo node name
    via_sub: str = "default"


class MihomoStartIn(BaseModel):
    port: int
    sub: str = "default"
    node: str = ""
