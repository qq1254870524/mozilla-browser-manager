"""Desktop client shell (native program) — Windows + Ubuntu.

Architecture:
  client (native process)
    ├── runtime   boot/stop modular FastAPI backend under ROOT
    ├── window    pywebview native frame (fallback: tk control center)
    ├── bridge    limited JS API exposed into embedded UI
    └── config    client.json under data/client/

The Web admin (ui/static js modules) is reused inside the native window.
Backend business stays in modules/ + api/routes/ (1:1).
"""

__version__ = "1.10.6-client"
