"""Doctor module: environment self-check."""
from __future__ import annotations

from typing import Any

from mozilla_manager.doctor import run_doctor


def run() -> dict[str, Any]:
    return run_doctor()
