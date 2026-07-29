"""v7 built-in 2FA / TOTP authenticator (ROOT-locked, no external pyotp dep)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from mozilla_manager import db
from mozilla_manager.paths import TOTP_DIR, ensure_layout, safe_resolve

_STORE = lambda: safe_resolve(TOTP_DIR / "accounts.json")  # noqa: E731


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _b32_decode(secret: str) -> bytes:
    s = re.sub(r"\s+", "", secret or "").upper()
    s = s.replace(" ", "")
    pad = "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s + pad, casefold=True)


def totp_code(secret: str, *, digits: int = 6, period: int = 30, algo: str = "sha1", for_time: float | None = None) -> str:
    key = _b32_decode(secret)
    t = int((for_time if for_time is not None else time.time()) // period)
    msg = struct.pack(">Q", t)
    dig = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}.get((algo or "sha1").lower(), hashlib.sha1)
    h = hmac.new(key, msg, dig).digest()
    o = h[-1] & 0x0F
    code_int = struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def remaining_seconds(period: int = 30, for_time: float | None = None) -> int:
    t = for_time if for_time is not None else time.time()
    return int(period - (t % period))


def parse_otpauth(uri: str) -> dict[str, Any]:
    """Parse otpauth://totp/... URI."""
    u = urlparse(uri.strip())
    if u.scheme != "otpauth":
        raise ValueError("not an otpauth URI")
    label = unquote(u.path.lstrip("/"))
    q = parse_qs(u.query)
    secret = (q.get("secret") or [""])[0]
    if not secret:
        raise ValueError("otpauth missing secret")
    issuer = (q.get("issuer") or [""])[0]
    if ":" in label and not issuer:
        issuer, label = label.split(":", 1)
        label = label.strip()
    return {
        "type": (u.netloc or "totp").lower(),
        "label": label,
        "issuer": issuer,
        "secret": secret.replace(" ", "").upper(),
        "digits": int((q.get("digits") or ["6"])[0]),
        "period": int((q.get("period") or ["30"])[0]),
        "algorithm": ((q.get("algorithm") or ["SHA1"])[0]).lower(),
    }


def _load() -> list[dict[str, Any]]:
    ensure_layout()
    path = _STORE()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("accounts") or [])
    except Exception:
        return []


def _save(accounts: list[dict[str, Any]]) -> None:
    ensure_layout()
    path = _STORE()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"updated_at": _now(), "accounts": accounts, "redacted": False}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_accounts(*, profile_id: str | None = None, include_secret: bool = False) -> list[dict[str, Any]]:
    out = []
    for a in _load():
        if profile_id and a.get("profile_id") not in (None, "", profile_id):
            # also allow global (no profile) always
            if a.get("profile_id") and a.get("profile_id") != profile_id:
                continue
        item = dict(a)
        item["code"] = totp_code(a["secret"], digits=int(a.get("digits") or 6), period=int(a.get("period") or 30), algo=str(a.get("algorithm") or "sha1"))
        item["remaining"] = remaining_seconds(int(a.get("period") or 30))
        if not include_secret:
            item.pop("secret", None)
        out.append(item)
    return out


def add_account(
    *,
    name: str,
    secret: str = "",
    otpauth: str = "",
    issuer: str = "",
    profile_id: str = "",
    site: str = "",
    digits: int = 6,
    period: int = 30,
    algorithm: str = "sha1",
) -> dict[str, Any]:
    if otpauth:
        parsed = parse_otpauth(otpauth)
        secret = parsed["secret"]
        name = name or parsed.get("label") or "totp"
        issuer = issuer or parsed.get("issuer") or ""
        digits = int(parsed.get("digits") or digits)
        period = int(parsed.get("period") or period)
        algorithm = str(parsed.get("algorithm") or algorithm)
    if not secret:
        raise ValueError("secret or otpauth required")
    # validate
    code = totp_code(secret, digits=digits, period=period, algo=algorithm)
    accounts = _load()
    aid = hashlib_id(name, secret, profile_id)
    # upsert by id
    accounts = [a for a in accounts if a.get("id") != aid]
    row = {
        "id": aid,
        "name": name,
        "issuer": issuer,
        "site": site or issuer,
        "secret": secret.replace(" ", "").upper(),
        "digits": digits,
        "period": period,
        "algorithm": algorithm,
        "profile_id": profile_id or None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    accounts.append(row)
    _save(accounts)
    db.audit("totp_add", profile_id or None, {"id": aid, "name": name, "issuer": issuer})
    return {"ok": True, "id": aid, "code": code, "remaining": remaining_seconds(period), "name": name, "issuer": issuer}


def hashlib_id(name: str, secret: str, profile_id: str = "") -> str:
    import hashlib

    return hashlib.sha256(f"{profile_id}:{name}:{secret[:8]}".encode()).hexdigest()[:12]


def remove_account(account_id: str) -> dict[str, Any]:
    accounts = _load()
    n = len(accounts)
    accounts = [a for a in accounts if a.get("id") != account_id]
    _save(accounts)
    db.audit("totp_remove", detail={"id": account_id})
    return {"ok": True, "removed": n - len(accounts), "id": account_id}


def _find_account(account_id: str) -> dict[str, Any] | None:
    """Resolve by id first, then by exact name (case-insensitive)."""
    rows = _load()
    for a in rows:
        if a.get("id") == account_id:
            return a
    key = str(account_id or "").strip().lower()
    if not key:
        return None
    for a in rows:
        if str(a.get("name") or "").strip().lower() == key:
            return a
    return None


def code_for(account_id: str) -> dict[str, Any]:
    a = _find_account(account_id)
    if not a:
        raise KeyError(f"totp account not found: {account_id}")
    period = int(a.get("period") or 30)
    return {
        "ok": True,
        "id": a.get("id"),
        "name": a.get("name"),
        "issuer": a.get("issuer"),
        "code": totp_code(a["secret"], digits=int(a.get("digits") or 6), period=period, algo=str(a.get("algorithm") or "sha1")),
        "remaining": remaining_seconds(period),
    }


def fill_script(account_id: str, selector: str = 'input[autocomplete="one-time-code"], input[name*="otp" i], input[name*="totp" i], input[id*="otp" i]') -> dict[str, Any]:
    """Return code + suggested CSS selector for auto-fill."""
    c = code_for(account_id)
    c["selector"] = selector
    c["js"] = f"""(() => {{
  const sel = {json.dumps(selector)};
  const code = {json.dumps(c['code'])};
  const el = document.querySelector(sel);
  if (!el) return {{ok:false, error:'no input'}};
  const proto = HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (setter) setter.call(el, code); else el.value = code;
  el.dispatchEvent(new Event('input', {{bubbles:true}}));
  el.dispatchEvent(new Event('change', {{bubbles:true}}));
  return {{ok:true, value: el.value}};
}})()"""
    return c
