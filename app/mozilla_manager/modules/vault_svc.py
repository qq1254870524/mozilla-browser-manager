"""v10 local secrets vault (stdlib). Not for high-security HSM use — lab/local only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any

from mozilla_manager.paths import VAULT_DIR, ensure_layout, safe_resolve

_MAGIC = b"MMV10"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _key_path():
    ensure_layout()
    return safe_resolve(VAULT_DIR / "master.key")


def _vault_path():
    ensure_layout()
    return safe_resolve(VAULT_DIR / "vault.json")


def _master_key() -> bytes:
    path = _key_path()
    if path.exists():
        raw = path.read_bytes().strip()
        if len(raw) >= 32:
            return raw[:32]
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return key


def _derive(key: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", key, salt, 120000, dklen=32)


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream))


def _encrypt(plain: str, key: bytes) -> str:
    raw = plain.encode("utf-8")
    salt = secrets.token_bytes(16)
    dk = _derive(key, salt)
    # keystream
    blocks = []
    counter = 0
    while len(b"".join(blocks)) < len(raw):
        blocks.append(hashlib.sha256(dk + counter.to_bytes(8, "big")).digest())
        counter += 1
    stream = b"".join(blocks)[: len(raw)]
    ct = _xor(raw, stream)
    mac = hmac.new(dk, salt + ct, hashlib.sha256).digest()
    blob = _MAGIC + salt + mac + ct
    return base64.urlsafe_b64encode(blob).decode("ascii")


def _decrypt(token: str, key: bytes) -> str:
    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    if not blob.startswith(_MAGIC):
        raise ValueError("invalid vault token")
    salt = blob[5:21]
    mac = blob[21:53]
    ct = blob[53:]
    dk = _derive(key, salt)
    expect = hmac.new(dk, salt + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expect):
        raise ValueError("vault MAC mismatch")
    blocks = []
    counter = 0
    while len(b"".join(blocks)) < len(ct):
        blocks.append(hashlib.sha256(dk + counter.to_bytes(8, "big")).digest())
        counter += 1
    stream = b"".join(blocks)[: len(ct)]
    return _xor(ct, stream).decode("utf-8")


def _load() -> dict[str, Any]:
    path = _vault_path()
    if not path.exists():
        return {"items": {}, "updated_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    data["updated_at"] = _now()
    _vault_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(_vault_path(), 0o600)
    except Exception:
        pass


def put(name: str, value: str, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    key = _master_key()
    data = _load()
    items = data.setdefault("items", {})
    items[name] = {
        "name": name,
        "cipher": _encrypt(value, key),
        "meta": meta or {},
        "updated_at": _now(),
        "created_at": (items.get(name) or {}).get("created_at") or _now(),
    }
    _save(data)
    return {"ok": True, "name": name, "updated_at": items[name]["updated_at"]}


def get(name: str, *, reveal: bool = False) -> dict[str, Any]:
    data = _load()
    item = (data.get("items") or {}).get(name)
    if not item:
        raise KeyError(name)
    out = {
        "ok": True,
        "name": name,
        "meta": item.get("meta") or {},
        "updated_at": item.get("updated_at"),
        "created_at": item.get("created_at"),
        "has_value": True,
    }
    if reveal:
        out["value"] = _decrypt(item["cipher"], _master_key())
    return out


def list_secrets() -> dict[str, Any]:
    data = _load()
    rows = []
    for name, item in sorted((data.get("items") or {}).items()):
        rows.append(
            {
                "name": name,
                "meta": item.get("meta") or {},
                "updated_at": item.get("updated_at"),
                "created_at": item.get("created_at"),
            }
        )
    return {"ok": True, "items": rows, "count": len(rows)}


def delete(name: str) -> dict[str, Any]:
    data = _load()
    items = data.get("items") or {}
    existed = name in items
    items.pop(name, None)
    data["items"] = items
    _save(data)
    return {"ok": True, "removed": int(existed), "name": name}
