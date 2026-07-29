#!/usr/bin/env python3
"""Download mihomo into runtime/mihomo for *current* OS (ROOT only)."""
from __future__ import annotations

import sys
from pathlib import Path

# reuse installer implementation
sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_all_deps import install_mihomo, ensure_root_ok, layout  # type: ignore


def main() -> int:
    ensure_root_ok()
    layout()
    force = "--force" in sys.argv
    install_mihomo(force=force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
