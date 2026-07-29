"""v7 batch profile creation with env/fingerprint drift."""
from __future__ import annotations

import random
from typing import Any

from mozilla_manager import db
from mozilla_manager.env_packs import binding_from_country, load_pack
from mozilla_manager.modules import profiles as profiles_mod

_VIEWPORTS = [
    (1920, 1080),
    (1920, 1200),
    (1680, 1050),
    (1600, 900),
    (1536, 864),
    (1440, 900),
    (1366, 768),
    (2560, 1440),
    (1280, 800),
    (1280, 720),
]

_FP_POOL = ["win11-chrome", "win11-chrome-zh", "win11-chrome-ja", "mac-chrome", "linux-chrome"]


def _drift_env(country: str, rng: random.Random) -> dict[str, Any]:
    pack = load_pack(country.upper())
    cities = list(pack.get("cities") or [{"name": country, "lat": 0.0, "lon": 0.0}])
    city = rng.choice(cities)
    # geo jitter ~ few km
    lat = float(city.get("lat") or 0) + rng.uniform(-0.08, 0.08)
    lon = float(city.get("lon") or 0) + rng.uniform(-0.08, 0.08)
    vw, vh = rng.choice(_VIEWPORTS)
    # language soft shuffle keep primary
    langs = list(pack.get("languages") or ["en-US", "en"])
    if len(langs) > 2 and rng.random() < 0.5:
        tail = langs[1:]
        rng.shuffle(tail)
        langs = [langs[0]] + tail
    fp = pack.get("fingerprint") or "win11-chrome"
    # occasional alternate fp still plausible
    if rng.random() < 0.25:
        fp = rng.choice([fp] + [x for x in _FP_POOL if x != fp][:2])
    return {
        "city": city.get("name"),
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "viewport": [vw, vh],
        "languages": langs,
        "locale": pack.get("locale"),
        "timezone_id": pack.get("timezone_id"),
        "fingerprint_id": fp,
    }


def batch_create(
    *,
    country: str,
    count: int = 5,
    name_prefix: str = "",
    engine: str = "pw_chromium",
    patch: str = "patchright",
    group: str = "",
    auto_port: bool = True,
    sub: str = "default",
    seed: int | None = None,
) -> dict[str, Any]:
    country = (country or "").upper()
    if not country:
        raise ValueError("country required")
    count = max(1, min(int(count), 100))
    rng = random.Random(seed if seed is not None else random.randint(1, 10**9))
    prefix = name_prefix or f"{country.lower()}-batch"
    created = []
    errors = []
    for i in range(1, count + 1):
        drift = _drift_env(country, rng)
        name = f"{prefix}-{i:02d}"
        try:
            prof = profiles_mod.create_profile(
                name=name,
                engine=engine,
                patch=patch,
                country=country,
                timezone_id=str(drift["timezone_id"] or ""),
                locale=str(drift["locale"] or ""),
                lat=float(drift["lat"]),
                lon=float(drift["lon"]),
                auto_port=auto_port,
                group=group or f"batch-{country}",
                remark=f"v7-batch city={drift['city']} vp={drift['viewport'][0]}x{drift['viewport'][1]}",
                fingerprint_id=str(drift["fingerprint_id"] or ""),
                sub=sub,
            )
            # apply viewport + languages drift onto env
            from mozilla_manager.store import ProfileStore
            from mozilla_manager.models import EnvBinding, GeoLocation

            store = ProfileStore()
            p = store.get(prof["id"])
            env = p.env.model_copy(deep=True)
            env.viewport_width = int(drift["viewport"][0])
            env.viewport_height = int(drift["viewport"][1])
            env.languages = list(drift["languages"])
            env.geolocation = GeoLocation(latitude=float(drift["lat"]), longitude=float(drift["lon"]), accuracy=rng.uniform(20, 80))
            meta = dict(p.meta)
            meta["batch"] = {"country": country, "city": drift["city"], "index": i}
            # force new stealth noise uniqueness already by profile id
            updated = store.update(p.id, env=env, meta=meta)
            # regenerate stealth to bind new viewport implicitly on next ensure
            try:
                from mozilla_manager.stealth import ensure_stealth_bundle

                ensure_stealth_bundle(updated)
            except Exception:
                pass
            created.append({"id": updated.id, "name": updated.name, "drift": drift})
        except Exception as e:
            errors.append({"index": i, "name": name, "error": str(e)})
    db.audit("batch_create", detail={"country": country, "count": count, "ok": len(created), "errors": len(errors)})
    return {
        "ok": len(errors) == 0,
        "country": country,
        "requested": count,
        "created": created,
        "errors": errors,
        "group": group or f"batch-{country}",
    }
