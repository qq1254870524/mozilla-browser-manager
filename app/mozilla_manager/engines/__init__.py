from __future__ import annotations

from ..models import EngineKind, Profile
from .base import EngineLauncher
from .camoufox_engine import CamoufoxLauncher
from .chromium import ChromiumLauncher


def get_launcher(profile: Profile) -> EngineLauncher:
    if profile.engine == EngineKind.CAMOUFOX:
        return CamoufoxLauncher()
    return ChromiumLauncher()
