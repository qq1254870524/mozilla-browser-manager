"""v3 anti-detect engine matrix: Camoufox / Playwright × Patchright / rebrowser / none."""
from __future__ import annotations

from typing import Any

from ..models import ChromiumPatch, EngineKind, Profile
from ..paths import BROWSERS_DIR, PATCHES_DIR, ROOT


MATRIX: list[dict[str, Any]] = [
    {
        "id": "camoufox",
        "engine": EngineKind.CAMOUFOX.value,
        "patch": None,
        "label": "Camoufox (Firefox anti-detect)",
        "repo": "https://github.com/daijro/camoufox",
        "notes": "Firefox-based; fingerprint via camoufox + init script",
    },
    {
        "id": "pw_chromium+patchright",
        "engine": EngineKind.PLAYWRIGHT_CHROMIUM.value,
        "patch": ChromiumPatch.PATCHRIGHT.value,
        "label": "Chromium + Patchright",
        "repo": "https://github.com/Kaliiiiiiiiii-Vinyzu/patchright",
        "notes": "Recommended default Chromium combo",
    },
    {
        "id": "pw_chromium+rebrowser",
        "engine": EngineKind.PLAYWRIGHT_CHROMIUM.value,
        "patch": ChromiumPatch.REBROWSER.value,
        "label": "Chromium + rebrowser-playwright",
        "repo": "https://github.com/rebrowser/rebrowser-patches",
        "notes": "rebrowser-playwright package + optional custom binary",
    },
    {
        "id": "pw_chromium+none",
        "engine": EngineKind.PLAYWRIGHT_CHROMIUM.value,
        "patch": ChromiumPatch.NONE.value,
        "label": "Chromium stock Playwright",
        "repo": "https://github.com/microsoft/playwright",
        "notes": "No anti-detect patches",
    },
]


def list_matrix() -> list[dict[str, Any]]:
    out = []
    for row in MATRIX:
        status = probe_combo(row["engine"], row.get("patch"))
        out.append({**row, **status})
    return out


def probe_combo(engine: str, patch: str | None = None) -> dict[str, Any]:
    ok = True
    details: list[str] = []
    if engine == EngineKind.CAMOUFOX.value:
        try:
            import camoufox  # noqa: F401

            details.append("camoufox import ok")
        except Exception as e:
            ok = False
            details.append(f"camoufox missing: {e}")
        cache = ROOT / "runtime" / "cache" / "camoufox" / "browsers"
        details.append(f"camoufox_cache_exists={cache.exists()}")
    else:
        try:
            import playwright  # noqa: F401

            details.append("playwright import ok")
        except Exception as e:
            ok = False
            details.append(f"playwright missing: {e}")
        details.append(f"browsers_dir={BROWSERS_DIR.exists()}")
        if patch == ChromiumPatch.PATCHRIGHT.value:
            try:
                import patchright  # noqa: F401

                details.append("patchright import ok")
            except Exception as e:
                ok = False
                details.append(f"patchright missing: {e}")
        if patch == ChromiumPatch.REBROWSER.value:
            try:
                import rebrowser_playwright  # noqa: F401

                details.append("rebrowser_playwright import ok")
            except Exception as e:
                details.append(f"rebrowser_playwright optional missing: {e}")
            src = PATCHES_DIR / "rebrowser-patches"
            details.append(f"rebrowser_patches_source={src.exists()}")
    return {"available": ok, "details": details}


def recommend_combo(*, stealth: bool = True, firefox: bool = False) -> dict[str, Any]:
    if firefox:
        return next(x for x in MATRIX if x["id"] == "camoufox")
    if stealth:
        return next(x for x in MATRIX if x["id"] == "pw_chromium+patchright")
    return next(x for x in MATRIX if x["id"] == "pw_chromium+none")


def apply_combo_to_profile(profile: Profile, combo_id: str) -> Profile:
    row = next((x for x in MATRIX if x["id"] == combo_id), None)
    if not row:
        raise KeyError(f"unknown combo: {combo_id}")
    profile.engine = EngineKind(row["engine"])
    if row.get("patch"):
        profile.chromium_patch = ChromiumPatch(row["patch"])
    return profile
