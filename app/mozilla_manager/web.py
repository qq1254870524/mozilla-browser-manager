"""Web entrypoint — thin wrapper over modular api.create_app()."""
from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1]
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from mozilla_manager.paths import ROOT
import os
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "runtime" / "cache"))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "runtime" / "browsers"))
os.environ.setdefault("XDG_CONFIG_HOME", str(ROOT / "runtime" / "xdg-config"))
os.environ.setdefault("XDG_DATA_HOME", str(ROOT / "runtime" / "xdg-data"))

from mozilla_manager.api import create_app

app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "mozilla_manager.web:app",
        host="127.0.0.1",
        port=17888,
        reload=False,
        app_dir=str(_APP_DIR),
    )


if __name__ == "__main__":
    main()
