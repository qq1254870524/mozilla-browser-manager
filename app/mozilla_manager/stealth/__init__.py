"""v6 stealth / fingerprint matrix (ROOT-locked).

- Profile-stable noise seed (no cross-profile correlation)
- 24+ dimension spoof init script
- TLS/JA3/JA4 profile metadata + mihomo client-fingerprint
- Entropy / collision reporting
"""
from .bundle import (
    ensure_stealth_bundle,
    load_stealth_bundle,
    stealth_path,
    summarize_bundle,
)
from .entropy import estimate_entropy_bits, collision_stats
from .init_script import build_stealth_init_script
from .tls_ja import TLS_PROFILES, apply_client_fingerprint_to_proxies, pick_tls_profile

__all__ = [
    "ensure_stealth_bundle",
    "load_stealth_bundle",
    "stealth_path",
    "summarize_bundle",
    "estimate_entropy_bits",
    "collision_stats",
    "build_stealth_init_script",
    "TLS_PROFILES",
    "apply_client_fingerprint_to_proxies",
    "pick_tls_profile",
]
