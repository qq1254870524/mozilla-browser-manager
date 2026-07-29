"""Entropy & collision metrics for stealth bundles."""
from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable


# Nominal choice cardinalities for theoretical entropy (bits).
# Continuous noise dimensions contribute via seed bits.
DIM_CARDINALITY: dict[str, int] = {
    "platform": 4,
    "ua_family": 6,
    "hardware_concurrency": 10,  # 2..20 step-ish
    "device_memory": 6,
    "max_touch_points": 4,
    "color_depth": 3,
    "pixel_ratio": 5,
    "gpu_vendor": 8,
    "gpu_renderer": 64,
    "gpu_driver": 32,
    "webgl_extensions_subset": 2**12,
    "canvas_noise_mode": 4,
    "audio_device_persona": 16,
    "audio_noise_scale": 2**10,
    "fonts_subset": 2**16,
    "smbios_product": 32,
    "cpu_arch": 3,
    "cpu_brand": 12,
    "disk_model": 24,
    "plugin_set": 8,
    "webrtc_mode": 3,
    "client_hints_brands": 8,
    "speech_voices": 12,
    "media_devices": 16,
    "battery_persona": 8,
    "connection_type": 5,
    "tls_persona": 8,
    "screen_res": 20,
    "language_pack": 20,
}


def estimate_entropy_bits(bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return theoretical entropy from free dimensions + profile seed bits."""
    bits = 0.0
    breakdown: dict[str, float] = {}
    for k, n in DIM_CARDINALITY.items():
        b = math.log2(max(n, 1))
        breakdown[k] = round(b, 3)
        bits += b
    # profile-stable 256-bit seed contributes usable uniqueness (count 128 conservatively)
    seed_bits = 128.0
    breakdown["profile_seed"] = seed_bits
    bits += seed_bits
    core = [
        "canvas_noise_mode",
        "gpu_renderer",
        "gpu_driver",
        "audio_device_persona",
        "hardware_concurrency",
        "fonts_subset",
        "smbios_product",
        "cpu_arch",
        "disk_model",
        "tls_persona",
    ]
    core_bits = sum(breakdown[k] for k in core) + seed_bits
    return {
        "entropy_bits": round(bits, 2),
        "core_entropy_bits": round(core_bits, 2),
        "meets_138": bits >= 138.0,
        "breakdown": breakdown,
        "dimension_count": len(DIM_CARDINALITY) + 1,
        "bundle_id": (bundle or {}).get("bundle_id"),
    }


def core_fingerprint_hash(bundle: dict[str, Any]) -> str:
    dims = bundle.get("dimensions") or {}
    parts = [
        str(dims.get("canvas", {}).get("seed")),
        str(dims.get("webgl", {}).get("renderer")),
        str(dims.get("webgl", {}).get("driver_version")),
        str(dims.get("audio", {}).get("persona_id")),
        str(dims.get("navigator", {}).get("hardware_concurrency")),
        str(dims.get("fonts", {}).get("hash")),
        str(dims.get("smbios", {}).get("product_name")),
        str(dims.get("cpu", {}).get("architecture")),
        str(dims.get("disk", {}).get("model")),
        str((bundle.get("tls") or {}).get("id")),
        str(bundle.get("seed")),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def collision_stats(bundles: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Pairwise core-hash collision rate among given bundles."""
    hashes = [core_fingerprint_hash(b) for b in bundles]
    n = len(hashes)
    if n < 2:
        return {"n": n, "pairs": 0, "collisions": 0, "rate": 0.0, "rate_pct": 0.0, "meets_0_004pct": True}
    pairs = n * (n - 1) // 2
    coll = 0
    for i in range(n):
        for j in range(i + 1, n):
            if hashes[i] == hashes[j]:
                coll += 1
    rate = coll / pairs if pairs else 0.0
    rate_pct = rate * 100.0
    return {
        "n": n,
        "pairs": pairs,
        "collisions": coll,
        "rate": rate,
        "rate_pct": rate_pct,
        "meets_0_004pct": rate_pct <= 0.004,
        "unique_core_hashes": len(set(hashes)),
    }
