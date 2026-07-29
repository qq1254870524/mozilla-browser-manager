"""Per-profile stealth bundle — fixed noise, 24+ dimensions, TLS persona."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import FingerprintConfig, Profile
from ..paths import ROOT, ensure_layout, safe_resolve
from .entropy import core_fingerprint_hash, estimate_entropy_bits
from .seed import StableRNG, seed_hex
from .tls_ja import pick_tls_profile

# GPU / driver pools for deep spoof
_GPU_POOL = [
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)", "31.0.15.5123"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)", "31.0.15.4633"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)", "32.0.15.6094"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)", "32.0.15.6603"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)", "32.0.15.7242"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)", "31.0.24002.92"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 7600 Direct3D11 vs_5_0 ps_5_0, D3D11)", "32.0.11024.2"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)", "31.0.101.2125"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "31.0.101.5186"),
    ("Google Inc. (Apple)", "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)", "Metal-3.1"),
    ("Google Inc. (Apple)", "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)", "Metal-3.1"),
    ("Google Inc. (Apple)", "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)", "Metal-3.2"),
]

_SMBIOS_PRODUCTS = [
    ("Dell Inc.", "XPS 15 9530", "0A61"),
    ("Dell Inc.", "Inspiron 16 5630", "0B21"),
    ("Lenovo", "ThinkPad X1 Carbon Gen 11", "21HM"),
    ("Lenovo", "IdeaPad Pro 5", "83D4"),
    ("HP", "HP Pavilion 15", "8A14"),
    ("HP", "HP EliteBook 840 G10", "819B"),
    ("ASUS", "ASUS VivoBook 15", "X1504V"),
    ("ASUS", "ROG Zephyrus G14", "GA403U"),
    ("Acer", "Aspire 5", "A515-57"),
    ("Microsoft Corporation", "Surface Laptop 5", "Surface_Laptop_5"),
    ("Apple Inc.", "MacBookPro18,3", "Mac-1E7E29AD0135"),
    ("Apple Inc.", "Mac14,2", "Mac-A61BA98FE"),
]

_DISK_MODELS = [
    "NVMe Samsung SSD 980 1TB",
    "NVMe Samsung SSD 990 PRO 2TB",
    "NVMe WD_BLACK SN850X 1TB",
    "NVMe Crucial P5 Plus 1TB",
    "NVMe Kingston KC3000 1TB",
    "NVMe Intel SSDPEKNU512GZ",
    "SATA WDC WD10EZEX-08WN4A0",
    "NVMe Apple APPLE SSD AP0512Z",
    "NVMe Micron 2450 MTFDKBA512TFK",
    "NVMe SK hynix HFS512GEJ9X125N",
]

_CPU_BRANDS = [
    ("Intel", "Intel(R) Core(TM) i7-13700H", "x86"),
    ("Intel", "Intel(R) Core(TM) i5-1240P", "x86"),
    ("Intel", "Intel(R) Core(TM) i9-13900H", "x86"),
    ("AMD", "AMD Ryzen 7 7840HS", "x86"),
    ("AMD", "AMD Ryzen 5 7640HS", "x86"),
    ("AMD", "AMD Ryzen 9 7940HS", "x86"),
    ("Apple", "Apple M1", "arm"),
    ("Apple", "Apple M2", "arm"),
    ("Apple", "Apple M3", "arm"),
    ("Intel", "Intel(R) Core(TM) Ultra 7 155H", "x86"),
]

_AUDIO_PERSONAS = [
    {"id": "realtek-stereo", "label": "Speakers (Realtek(R) Audio)", "base_latency": 0.01, "sample_rate": 48000},
    {"id": "realtek-headphones", "label": "Headphones (Realtek(R) Audio)", "base_latency": 0.008, "sample_rate": 48000},
    {"id": "nvidia-hdmi", "label": "NVIDIA High Definition Audio", "base_latency": 0.012, "sample_rate": 48000},
    {"id": "usb-dac", "label": "USB Audio Device", "base_latency": 0.006, "sample_rate": 44100},
    {"id": "apple-speakers", "label": "MacBook Pro Speakers", "base_latency": 0.01, "sample_rate": 48000},
    {"id": "steelseries", "label": "SteelSeries Chat", "base_latency": 0.009, "sample_rate": 48000},
    {"id": "logitech-g", "label": "Logitech G PRO X", "base_latency": 0.007, "sample_rate": 48000},
    {"id": "bluetooth-a2dp", "label": "Bluetooth Audio", "base_latency": 0.05, "sample_rate": 44100},
]

_FONT_POOLS = {
    "Win32": [
        "Arial", "Calibri", "Cambria", "Candara", "Comic Sans MS", "Consolas", "Constantia",
        "Corbel", "Courier New", "Georgia", "Impact", "Lucida Console", "Lucida Sans Unicode",
        "Microsoft Sans Serif", "Palatino Linotype", "Segoe UI", "Segoe UI Emoji", "Tahoma",
        "Times New Roman", "Trebuchet MS", "Verdana", "Microsoft YaHei", "SimSun", "SimHei",
        "Microsoft JhengHei", "Yu Gothic", "Meiryo", "Malgun Gothic", "Gabriola", "Ink Free",
    ],
    "MacIntel": [
        "Arial", "Helvetica", "Helvetica Neue", "Menlo", "Monaco", "SF Pro Text", "SF Pro Display",
        "Times New Roman", "Verdana", "Geneva", "Lucida Grande", "PingFang SC", "Hiragino Sans",
        "Hiragino Sans GB", "Apple Color Emoji", "Avenir", "Futura", "Gill Sans", "Optima",
    ],
    "Linux x86_64": [
        "Arial", "DejaVu Sans", "DejaVu Sans Mono", "Liberation Sans", "Liberation Serif",
        "Noto Sans", "Noto Sans CJK SC", "Ubuntu", "FreeSans", "FreeMono", "Cantarell",
        "Source Code Pro", "Fira Sans", "Roboto",
    ],
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stealth_path(profile_id: str) -> Path:
    ensure_layout()
    return safe_resolve(ROOT / "data" / "profiles" / profile_id / "stealth.json")


def load_stealth_bundle(profile_id: str) -> dict[str, Any] | None:
    path = stealth_path(profile_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fonts_for(platform: str, rng: StableRNG, base_fonts: list[str] | None) -> dict[str, Any]:
    pool = list(_FONT_POOLS.get(platform) or _FONT_POOLS["Win32"])
    if base_fonts:
        # merge unique keep base order first
        for f in base_fonts:
            if f not in pool:
                pool.append(f)
    # drop 0-4 random optional fonts for uniqueness, keep >= 12
    drop_n = rng.randint(0, min(4, max(0, len(pool) - 12)))
    fonts = list(pool)
    for _ in range(drop_n):
        if len(fonts) <= 12:
            break
        fonts.pop(rng.randint(0, len(fonts) - 1))
    # maybe add 1-2 extra from pool already there — shuffle lightly
    if rng.random() < 0.4 and len(pool) > len(fonts):
        extra = rng.choice([f for f in pool if f not in fonts] or fonts)
        if extra not in fonts:
            fonts.append(extra)
    h = hashlib.sha256(",".join(fonts).encode()).hexdigest()[:16]
    return {"list": fonts, "hash": h, "count": len(fonts)}


def build_stealth_bundle(
    profile: Profile,
    *,
    tls_profile_id: str | None = None,
    force_new_noise: bool = False,
) -> dict[str, Any]:
    """Build a full v6 stealth bundle. Noise is profile-stable unless force_new_noise (uses salt bump)."""
    pid = profile.id
    salt = "mozilla-v6-stealth"
    existing = load_stealth_bundle(pid)
    if existing and not force_new_noise:
        # allow TLS override update without reshuffling noise
        if tls_profile_id and tls_profile_id != (existing.get("tls") or {}).get("id"):
            existing["tls"] = pick_tls_profile(
                platform=profile.env.fingerprint.platform,
                explicit=tls_profile_id,
                engine=str(profile.engine.value if hasattr(profile.engine, "value") else profile.engine),
            )
            existing["updated_at"] = _now()
            existing["entropy"] = estimate_entropy_bits(existing)
            existing["core_hash"] = core_fingerprint_hash(existing)
            _write(pid, existing)
        return existing

    if force_new_noise:
        # bump generation counter stored if any
        gen = int((existing or {}).get("generation") or 0) + 1
        salt = f"mozilla-v6-stealth:gen{gen}"
    else:
        gen = int((existing or {}).get("generation") or 1)

    rng = StableRNG(pid, salt=salt, stream="dims")
    fp: FingerprintConfig = profile.env.fingerprint or FingerprintConfig()
    platform = fp.platform or "Win32"

    # GPU deep
    gpu_vendor, gpu_renderer, gpu_driver = rng.choice(_GPU_POOL)
    # prefer template renderer if set and force_new not required — still pin driver via rng for uniqueness
    if fp.renderer and not force_new_noise and gen == 1:
        # blend: keep template renderer but attach stable driver from seed
        gpu_renderer = fp.renderer
        gpu_vendor = fp.vendor_webgl or gpu_vendor
        gpu_driver = rng.choice([x[2] for x in _GPU_POOL])

    smbios_mfr, smbios_product, smbios_sku = rng.choice(_SMBIOS_PRODUCTS)
    disk_model = rng.choice(_DISK_MODELS)
    cpu_vendor, cpu_brand, cpu_arch = rng.choice(_CPU_BRANDS)
    # align arch loosely with platform
    if "Mac" in platform or platform == "MacIntel":
        cpu_vendor, cpu_brand, cpu_arch = rng.choice([c for c in _CPU_BRANDS if c[0] == "Apple"] or _CPU_BRANDS)
        smbios_mfr, smbios_product, smbios_sku = rng.choice([s for s in _SMBIOS_PRODUCTS if s[0].startswith("Apple")] or _SMBIOS_PRODUCTS)
        gpu_vendor, gpu_renderer, gpu_driver = rng.choice([g for g in _GPU_POOL if "Apple" in g[0]] or _GPU_POOL)

    hw = int(fp.hardware_concurrency or 8)
    # slight persona jitter but fixed: pick from common set biased by template
    hw_choices = [4, 6, 8, 10, 12, 14, 16, 20]
    if hw in hw_choices:
        # pick nearby stable
        idx = hw_choices.index(hw)
        hw = hw_choices[max(0, min(len(hw_choices) - 1, idx + rng.randint(-1, 1)))]
    else:
        hw = rng.choice(hw_choices)

    mem_choices = [4.0, 8.0, 16.0, 32.0]
    mem = float(fp.device_memory or 8.0)
    if mem not in mem_choices:
        mem = rng.choice(mem_choices)
    else:
        mem = rng.choice(mem_choices) if rng.random() < 0.15 else mem

    audio = dict(rng.choice(_AUDIO_PERSONAS))
    audio["noise_scale"] = round(rng.uniform(0.00005, 0.0004), 8)
    audio["offset_bin"] = rng.randint(1, 64)
    audio["channel_count"] = rng.choice([2, 2, 2, 1])

    fonts = _fonts_for(platform, rng, list(fp.fonts or []))

    canvas = {
        "seed": rng.derive_int("canvas", 1, 2**31 - 1),
        "mode": rng.choice(["pixel", "pixel", "pixel", "aa"]),
        "r_bias": round(rng.uniform(-1.5, 1.5), 4),
        "g_bias": round(rng.uniform(-1.5, 1.5), 4),
        "b_bias": round(rng.uniform(-1.5, 1.5), 4),
        "a_noise": round(rng.uniform(0.0, 0.02), 5),
    }

    webgl = {
        "vendor": gpu_vendor,
        "renderer": gpu_renderer,
        "driver_version": gpu_driver,
        "unmasked_vendor": gpu_vendor,
        "unmasked_renderer": f"{gpu_renderer} /* {gpu_driver} */",
        "max_texture_size": rng.choice([8192, 16384, 16384]),
        "max_renderbuffer_size": rng.choice([8192, 16384]),
        "aliased_line_width_range": [1, rng.choice([1, 7, 10])],
        "aliased_point_size_range": [1, rng.choice([255, 1024])],
    }

    # v10.3 immersive/frameless → no titlebar chrome offset (outer≈inner)
    try:
        from mozilla_manager.engines.immersive import want_immersive, stealth_screen_offsets
        _imm = want_immersive(getattr(profile, "meta", None) or {})
        _off = stealth_screen_offsets(getattr(profile, "meta", None) or {})
    except Exception:
        _imm = False
        _off = {"avail_offset_y": 40, "toolbar": 40}
    screen = {
        "width": int(profile.env.viewport_width or 1920),
        "height": int(profile.env.viewport_height or 1080),
        "color_depth": int(fp.color_depth or 24),
        "pixel_ratio": round(rng.choice([1.0, 1.0, 1.25, 1.5, 2.0]), 2),
        "avail_offset_y": int(_off.get("avail_offset_y") if _imm else rng.choice([0, 0, 40, 48])),
    }

    client_rects = {
        "noise_x": round(rng.uniform(-0.02, 0.02), 5),
        "noise_y": round(rng.uniform(-0.02, 0.02), 5),
    }

    automation = {
        "hide_webdriver": True,
        "spoof_chrome_runtime": True,
        "spoof_permissions": True,
        "languages_override": list(profile.env.languages or ["en-US", "en"]),
        "plugins_profile": rng.choice(["chrome-pdf", "chrome-pdf-widevine", "minimal"]),
    }

    navigator = {
        "platform": platform,
        "oscpu": fp.oscpu,
        "vendor": fp.vendor or "Google Inc.",
        "user_agent": fp.user_agent or profile.env.user_agent,
        "hardware_concurrency": hw,
        "device_memory": mem,
        "max_touch_points": int(fp.max_touch_points or 0),
        "architecture": "x86" if cpu_arch == "x86" else "arm",
        "bitness": "64",
        "model": "",
        "ua_ch_platform": "Windows" if "Win" in platform else ("macOS" if "Mac" in platform else "Linux"),
        "ua_ch_platform_version": rng.choice(["15.0.0", "14.0.0", "13.0.0"]) if "Win" in platform else rng.choice(["14.0.0", "13.6.0", "12.0.0"]),
        "ua_ch_mobile": False,
    }

    smbios = {
        "manufacturer": smbios_mfr,
        "product_name": smbios_product,
        "sku": smbios_sku,
        "serial_hash": hashlib.sha256(f"{pid}:{smbios_sku}".encode()).hexdigest()[:12],
    }

    cpu = {
        "vendor": cpu_vendor,
        "brand": cpu_brand,
        "architecture": cpu_arch,
        "cores": hw,
        "threads": hw,
    }

    disk = {"model": disk_model, "kind": "NVMe" if "NVMe" in disk_model else "SATA"}

    media_devices = {
        "speaker_label": audio["label"],
        "mic_label": rng.choice(["Default - Microphone", "Microphone Array", "USB Microphone", "MacBook Pro Microphone"]),
        "cam_label": rng.choice(["Integrated Camera", "HD Webcam", "FaceTime HD Camera", "USB Camera"]),
        "device_id_salt": seed_hex(pid, salt=salt + ":media")[:16],
    }

    charging = bool(rng.choice([True, True, False]))
    battery = {
        "charging": charging,
        "level": round(rng.uniform(0.35, 0.98), 2),
        "charging_time": 0 if charging else None,
        "discharging_time": None if charging else rng.randint(3600, 20000),
    }

    connection = {
        "effectiveType": rng.choice(["4g", "4g", "3g", "wifi"]),
        "rtt": rng.choice([50, 75, 100, 150, 200]),
        "downlink": rng.choice([1.5, 5.0, 10.0, 10.0]),
        "saveData": False,
    }

    speech = {
        "voice_count_bias": rng.randint(0, 5),
        "default_lang": (profile.env.locale or "en-US"),
    }

    tls = pick_tls_profile(
        platform=platform,
        explicit=tls_profile_id or (profile.meta or {}).get("tls_profile"),
        engine=str(profile.engine.value if hasattr(profile.engine, "value") else profile.engine),
    )

    doh = {
        "mode": (profile.meta or {}).get("doh_mode") or "secure",
        "template": (profile.meta or {}).get("doh_template")
        or (profile.meta or {}).get("doh_url")
        or "https://cloudflare-dns.com/dns-query",
        "servers": list(
            (profile.meta or {}).get("doh_servers")
            or [
                "https://cloudflare-dns.com/dns-query",
                "https://dns.google/dns-query",
                "https://dns.alidns.com/dns-query",
            ]
        ),
        "force": True,
    }

    dimensions = {
        "navigator": navigator,
        "screen": screen,
        "webgl": webgl,
        "canvas": canvas,
        "audio": audio,
        "fonts": fonts,
        "smbios": smbios,
        "cpu": cpu,
        "disk": disk,
        "media_devices": media_devices,
        "battery": battery,
        "connection": connection,
        "speech": speech,
        "client_rects": client_rects,
        "automation": automation,
        # extra named dims to exceed 24
        "timezone": {"id": profile.env.timezone_id},
        "locale": {"id": profile.env.locale, "languages": list(profile.env.languages or [])},
        "webrtc": {"mode": (profile.meta or {}).get("webrtc_mode") or "disable"},
        "plugins": {"profile": automation["plugins_profile"]},
        "permissions": {"geolocation": True},
        "client_hints": {
            "architecture": navigator["architecture"],
            "bitness": navigator["bitness"],
            "platform": navigator["ua_ch_platform"],
            "platformVersion": navigator["ua_ch_platform_version"],
            "model": navigator["model"],
            "mobile": navigator["ua_ch_mobile"],
        },
        "outer_chrome": {"toolbar": 0 if _imm else screen["avail_offset_y"]},
        "pixel_ratio": {"value": screen["pixel_ratio"]},
        "touch": {"max": navigator["max_touch_points"]},
        "storage_quota_bias": rng.randint(0, 50),
    }

    dim_count = len(dimensions)
    bundle = {
        "version": 6,
        "profile_id": pid,
        "bundle_id": hashlib.sha256(f"{pid}:{salt}:{gen}".encode()).hexdigest()[:16],
        "generation": gen if force_new_noise else max(gen, 1),
        "seed": seed_hex(pid, salt=salt),
        "salt": salt,
        "created_at": (existing or {}).get("created_at") or _now(),
        "updated_at": _now(),
        "dimensions": dimensions,
        "tls": tls,
        "doh": doh,
        "fixed_noise": True,
        "redacted": False,
    }
    bundle["core_hash"] = core_fingerprint_hash(bundle)
    bundle["entropy"] = estimate_entropy_bits(bundle)
    bundle["dimension_count"] = dim_count
    bundle["meets"] = {
        "entropy_ge_138": bool(bundle["entropy"].get("meets_138")),
        "dimensions_ge_24": dim_count >= 24,
    }
    _write(pid, bundle)
    return bundle


def _write(profile_id: str, bundle: dict[str, Any]) -> Path:
    path = stealth_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ensure_stealth_bundle(
    profile: Profile,
    *,
    tls_profile_id: str | None = None,
    force_new_noise: bool = False,
) -> dict[str, Any]:
    return build_stealth_bundle(profile, tls_profile_id=tls_profile_id, force_new_noise=force_new_noise)


def summarize_bundle(bundle: dict[str, Any] | None) -> dict[str, Any]:
    if not bundle:
        return {"ok": False, "error": "no bundle"}
    dims = bundle.get("dimensions") or {}
    return {
        "ok": True,
        "profile_id": bundle.get("profile_id"),
        "bundle_id": bundle.get("bundle_id"),
        "generation": bundle.get("generation"),
        "dimension_count": bundle.get("dimension_count") or len(dims),
        "entropy_bits": (bundle.get("entropy") or {}).get("entropy_bits"),
        "core_entropy_bits": (bundle.get("entropy") or {}).get("core_entropy_bits"),
        "meets_138": (bundle.get("entropy") or {}).get("meets_138"),
        "core_hash": bundle.get("core_hash"),
        "tls": bundle.get("tls"),
        "doh": bundle.get("doh"),
        "webgl_renderer": (dims.get("webgl") or {}).get("renderer"),
        "gpu_driver": (dims.get("webgl") or {}).get("driver_version"),
        "hardware_concurrency": (dims.get("navigator") or {}).get("hardware_concurrency"),
        "audio_persona": (dims.get("audio") or {}).get("id"),
        "smbios": dims.get("smbios"),
        "cpu": dims.get("cpu"),
        "disk": dims.get("disk"),
        "fixed_noise": bundle.get("fixed_noise"),
        "path": f"data/profiles/{bundle.get('profile_id')}/stealth.json",
    }
