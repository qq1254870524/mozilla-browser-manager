"""v2 fingerprint templates — platform / fonts / WebGL baseline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import FingerprintConfig
from .paths import FINGERPRINTS_DIR, ensure_layout

# Built-in templates (seeded into data/fingerprints/)
DEFAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "win11-chrome": {
        "template_id": "win11-chrome",
        "platform": "Win32",
        "oscpu": "Windows NT 10.0; Win64; x64",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "vendor": "Google Inc.",
        "vendor_webgl": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "fonts": [
            "Arial", "Calibri", "Cambria", "Comic Sans MS", "Consolas",
            "Courier New", "Georgia", "Helvetica", "Impact", "Segoe UI",
            "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
            "Microsoft YaHei", "Segoe UI Emoji",
        ],
        "hardware_concurrency": 8,
        "device_memory": 8.0,
        "max_touch_points": 0,
        "color_depth": 24,
    },
    "win11-chrome-ja": {
        "template_id": "win11-chrome-ja",
        "platform": "Win32",
        "oscpu": "Windows NT 10.0; Win64; x64",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "vendor": "Google Inc.",
        "vendor_webgl": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "fonts": [
            "Arial", "Calibri", "Consolas", "Courier New", "Georgia",
            "Meiryo", "MS Gothic", "MS Mincho", "Segoe UI", "Tahoma",
            "Times New Roman", "Verdana", "Yu Gothic", "Yu Gothic UI",
        ],
        "hardware_concurrency": 8,
        "device_memory": 8.0,
        "max_touch_points": 0,
        "color_depth": 24,
    },
    "win11-chrome-zh": {
        "template_id": "win11-chrome-zh",
        "platform": "Win32",
        "oscpu": "Windows NT 10.0; Win64; x64",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "vendor": "Google Inc.",
        "vendor_webgl": "Google Inc. (NVIDIA)",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "fonts": [
            "Arial", "Calibri", "Consolas", "Courier New", "Georgia",
            "Microsoft YaHei", "Microsoft JhengHei", "SimSun", "SimHei",
            "Noto Sans SC", "Segoe UI", "Tahoma", "Times New Roman", "Verdana",
        ],
        "hardware_concurrency": 12,
        "device_memory": 16.0,
        "max_touch_points": 0,
        "color_depth": 24,
    },
    "mac-chrome": {
        "template_id": "mac-chrome",
        "platform": "MacIntel",
        "oscpu": "Intel Mac OS X 10_15_7",
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "vendor": "Google Inc.",
        "vendor_webgl": "Google Inc. (Apple)",
        "renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
        "fonts": [
            "Arial", "Helvetica", "Helvetica Neue", "Menlo", "Monaco",
            "SF Pro Text", "SF Pro Display", "Times New Roman", "Verdana",
            "PingFang SC", "Hiragino Sans",
        ],
        "hardware_concurrency": 8,
        "device_memory": 8.0,
        "max_touch_points": 0,
        "color_depth": 30,
    },
    "linux-chrome": {
        "template_id": "linux-chrome",
        "platform": "Linux x86_64",
        "oscpu": "Linux x86_64",
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "vendor": "Google Inc.",
        "vendor_webgl": "Google Inc. (NVIDIA Corporation)",
        "renderer": "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1660/PCIe/SSE2, OpenGL 4.5.0)",
        "fonts": [
            "Arial", "DejaVu Sans", "DejaVu Sans Mono", "Liberation Sans",
            "Noto Sans", "Noto Sans CJK SC", "Ubuntu", "FreeSans", "FreeMono",
        ],
        "hardware_concurrency": 8,
        "device_memory": 8.0,
        "max_touch_points": 0,
        "color_depth": 24,
    },
}


def seed_fingerprints(*, force: bool = False) -> list[str]:
    """Write default templates under data/fingerprints/."""
    ensure_layout()
    FINGERPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for tid, data in DEFAULT_TEMPLATES.items():
        path = FINGERPRINTS_DIR / f"{tid}.json"
        if force or not path.exists():
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(tid)
    return written


def list_fingerprints() -> list[dict[str, Any]]:
    seed_fingerprints()
    out: list[dict[str, Any]] = []
    for f in sorted(FINGERPRINTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append(
                {
                    "id": f.stem,
                    "platform": data.get("platform"),
                    "user_agent": data.get("user_agent"),
                    "vendor_webgl": data.get("vendor_webgl"),
                    "renderer": data.get("renderer"),
                    "hardware_concurrency": data.get("hardware_concurrency"),
                    "fonts_count": len(data.get("fonts") or []),
                }
            )
        except Exception as e:
            out.append({"id": f.stem, "error": str(e)})
    return out


def load_fingerprint(template_id: str = "win11-chrome") -> FingerprintConfig:
    seed_fingerprints()
    tid = (template_id or "win11-chrome").strip()
    path = FINGERPRINTS_DIR / f"{tid}.json"
    raw: dict[str, Any]
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    elif tid in DEFAULT_TEMPLATES:
        raw = DEFAULT_TEMPLATES[tid]
    else:
        # soft fallback
        raw = DEFAULT_TEMPLATES["win11-chrome"]
        raw = {**raw, "template_id": tid}
    raw.setdefault("template_id", tid)
    return FingerprintConfig.model_validate(raw)


def apply_init_script(fp: FingerprintConfig | dict[str, Any] | None) -> str:
    """Return JS injected via add_init_script to spoof platform/fonts/WebGL/HW."""
    if fp is None:
        return ""
    if isinstance(fp, dict):
        cfg = FingerprintConfig.model_validate(fp)
    else:
        cfg = fp

    fonts_json = json.dumps(list(cfg.fonts), ensure_ascii=False)
    platform = json.dumps(cfg.platform)
    oscpu = json.dumps(cfg.oscpu or "")
    vendor = json.dumps(cfg.vendor)
    vendor_webgl = json.dumps(cfg.vendor_webgl)
    renderer = json.dumps(cfg.renderer)
    ua = json.dumps(cfg.user_agent or "")
    hw = int(cfg.hardware_concurrency)
    mem = float(cfg.device_memory)
    touch = int(cfg.max_touch_points)
    depth = int(cfg.color_depth)
    extra = cfg.extra_init_script or ""

    js = f"""
(() => {{
  const platform = {platform};
  const oscpu = {oscpu};
  const vendor = {vendor};
  const vendorWebgl = {vendor_webgl};
  const renderer = {renderer};
  const ua = {ua};
  const fonts = {fonts_json};
  const hw = {hw};
  const mem = {mem};
  const touch = {touch};
  const depth = {depth};

  const redefine = (obj, prop, value) => {{
    try {{
      Object.defineProperty(obj, prop, {{
        get: () => value,
        configurable: true,
      }});
    }} catch (e) {{}}
  }};

  try {{
    redefine(Navigator.prototype, 'platform', platform);
    redefine(Navigator.prototype, 'vendor', vendor);
    redefine(Navigator.prototype, 'hardwareConcurrency', hw);
    redefine(Navigator.prototype, 'deviceMemory', mem);
    redefine(Navigator.prototype, 'maxTouchPoints', touch);
    if (ua) redefine(Navigator.prototype, 'userAgent', ua);
    if (oscpu) {{
      try {{ redefine(Navigator.prototype, 'oscpu', oscpu); }} catch (e) {{}}
    }}
  }} catch (e) {{}}

  try {{
    redefine(Screen.prototype, 'colorDepth', depth);
    redefine(Screen.prototype, 'pixelDepth', depth);
  }} catch (e) {{}}

  // WebGL vendor/renderer
  const patchGetParameter = (proto) => {{
    if (!proto || !proto.getParameter) return;
    const original = proto.getParameter;
    proto.getParameter = function(param) {{
      const UNMASKED_VENDOR_WEBGL = 0x9245;
      const UNMASKED_RENDERER_WEBGL = 0x9246;
      if (param === UNMASKED_VENDOR_WEBGL) return vendorWebgl;
      if (param === UNMASKED_RENDERER_WEBGL) return renderer;
      return original.apply(this, arguments);
    }};
  }};
  try {{
    if (typeof WebGLRenderingContext !== 'undefined') patchGetParameter(WebGLRenderingContext.prototype);
    if (typeof WebGL2RenderingContext !== 'undefined') patchGetParameter(WebGL2RenderingContext.prototype);
  }} catch (e) {{}}

  // Minimal font presence hint via document.fonts.check when available
  try {{
    if (document.fonts && document.fonts.check) {{
      const orig = document.fonts.check.bind(document.fonts);
      document.fonts.check = function(font, text) {{
        try {{
          const family = String(font || '').replace(/["']/g, '');
          for (const f of fonts) {{
            if (family.includes(f)) return true;
          }}
        }} catch (e) {{}}
        return orig(font, text);
      }};
    }}
  }} catch (e) {{}}

  // soft webdriver hide
  try {{ redefine(Navigator.prototype, 'webdriver', undefined); }} catch (e) {{}}

  {extra}
}})();
""".strip()
    return js


def apply_fingerprint_to_context(context: Any, fp: FingerprintConfig | None) -> None:
    """Inject init script into a Playwright/Camoufox-like context if possible."""
    if not fp or not context:
        return
    script = apply_init_script(fp)
    if not script:
        return
    try:
        if hasattr(context, "add_init_script"):
            context.add_init_script(script)
            return
    except Exception:
        pass
    # some wrappers expose pages only
    try:
        pages = getattr(context, "pages", None) or []
        for page in pages:
            if hasattr(page, "add_init_script"):
                page.add_init_script(script)
    except Exception:
        pass
