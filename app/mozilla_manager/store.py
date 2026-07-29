from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .models import ChromiumPatch, EngineKind, EnvBinding, Profile, ProxyConfig
from . import db
from .paths import ROOT, ensure_layout, p, safe_resolve


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-").lower()
    return s or uuid4().hex[:8]


class ProfileStore:
    """File-based profile registry fully inside /home/baoge/Mozilla/data."""

    def __init__(self) -> None:
        ensure_layout()
        self.index_path = p("data", "profiles.json")
        if not self.index_path.exists():
            self._write([])

    def _read(self) -> list[Profile]:
        raw = json.loads(self.index_path.read_text(encoding="utf-8") or "[]")
        return [Profile.model_validate(x) for x in raw]

    def _write(self, items: Iterable[Profile]) -> None:
        data = [x.model_dump(mode="json") for x in items]
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    def list(self) -> list[Profile]:
        return self._read()

    def get(self, profile_id: str) -> Profile:
        for x in self._read():
            if x.id == profile_id:
                return x
        raise KeyError(profile_id)

    def create(
        self,
        name: str,
        engine: EngineKind = EngineKind.PLAYWRIGHT_CHROMIUM,
        chromium_patch: ChromiumPatch = ChromiumPatch.PATCHRIGHT,
        proxy: ProxyConfig | None = None,
        env: EnvBinding | None = None,
    ) -> Profile:
        items = self._read()
        pid = f"{_slug(name)}-{uuid4().hex[:6]}"
        rel = f"data/profiles/{pid}"
        abs_dir = safe_resolve(ROOT / rel)
        abs_dir.mkdir(parents=True, exist_ok=True)
        # per-profile truth file
        prof = Profile(
            id=pid,
            name=name,
            engine=engine,
            chromium_patch=chromium_patch,
            user_data_dir=rel.replace("\\", "/"),
            proxy=proxy or ProxyConfig(),
            env=env or EnvBinding(),
            created_at=_now(),
            updated_at=_now(),
        )
        self._write_profile_file(prof)
        items.append(prof)
        self._write(items)
        try:
            db.init_db()
            db.upsert_profile_row(prof)
            db.audit("profile_create", prof.id, {"name": prof.name, "engine": prof.engine.value if hasattr(prof.engine, "value") else prof.engine})
        except Exception:
            pass
        return prof

    def _write_profile_file(self, prof: Profile) -> None:
        d = safe_resolve(ROOT / prof.user_data_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "profile.json").write_text(
            json.dumps(prof.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        readme = d / "README.txt"
        if not readme.exists():
            readme.write_text(
                f"Persistent user_data_dir for profile {prof.id}\n"
                f"ROOT-locked: must stay under Mozilla tree.\n",
                encoding="utf-8",
            )

    def update(self, profile_id: str, **patch: Any) -> Profile:
        items = self._read()
        out: list[Profile] = []
        found: Profile | None = None
        for x in items:
            if x.id != profile_id:
                out.append(x)
                continue
            data = x.model_dump()
            # nested pydantic models
            for k, v in patch.items():
                if hasattr(v, "model_dump"):
                    data[k] = v.model_dump(mode="json")
                else:
                    data[k] = v
            data["updated_at"] = _now()
            found = Profile.model_validate(data)
            out.append(found)
        if not found:
            raise KeyError(profile_id)
        self._write(out)
        self._write_profile_file(found)
        try:
            db.upsert_profile_row(found)
            db.audit("profile_update", found.id, {"keys": list(patch.keys())})
        except Exception:
            pass
        return found

    def delete(self, profile_id: str, wipe_files: bool = True) -> None:
        try:
            old = self.get(profile_id)
        except KeyError:
            old = None
        items = [x for x in self._read() if x.id != profile_id]
        self._write(items)
        try:
            db.delete_profile_row(profile_id)
            db.audit("profile_delete", profile_id, {"wipe": wipe_files})
        except Exception:
            pass
        if wipe_files and old:
            d = safe_resolve(ROOT / old.user_data_dir)
            if d.exists() and d != ROOT.resolve():
                shutil.rmtree(d, ignore_errors=True)

    def abs_user_data(self, prof: Profile) -> Path:
        path = safe_resolve(ROOT / prof.user_data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
