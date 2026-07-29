"""v3 SQLite index: status, node binding, audit. profile.json remains truth source."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .paths import DB_PATH, ensure_layout, safe_resolve

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path() -> Path:
    ensure_layout()
    return safe_resolve(DB_PATH)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    with _LOCK:
        conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  engine TEXT,
  chromium_patch TEXT,
  user_data_dir TEXT NOT NULL,
  proxy_mode TEXT,
  mihomo_port INTEGER,
  node_name TEXT,
  country TEXT,
  timezone_id TEXT,
  locale TEXT,
  fingerprint_id TEXT,
  group_name TEXT,
  status TEXT DEFAULT 'stopped',  -- stopped|running|error
  last_launch_at TEXT,
  last_stop_at TEXT,
  last_ip TEXT,
  last_egress_country TEXT,
  created_at TEXT,
  updated_at TEXT,
  meta_json TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  profile_id TEXT,
  action TEXT NOT NULL,
  detail_json TEXT
);

CREATE TABLE IF NOT EXISTS run_state (
  profile_id TEXT PRIMARY KEY,
  running INTEGER DEFAULT 0,
  driver TEXT,
  pid INTEGER,
  started_at TEXT,
  extra_json TEXT
);

CREATE TABLE IF NOT EXISTS node_favorites (
  sub TEXT NOT NULL,
  node_name TEXT NOT NULL,
  note TEXT,
  created_at TEXT,
  PRIMARY KEY (sub, node_name)
);

CREATE TABLE IF NOT EXISTS node_latency (
  sub TEXT NOT NULL,
  node_name TEXT NOT NULL,
  latency_ms INTEGER,
  ok INTEGER,
  checked_at TEXT,
  error TEXT,
  PRIMARY KEY (sub, node_name)
);

CREATE TABLE IF NOT EXISTS subscriptions (
  name TEXT PRIMARY KEY,
  url TEXT,
  url_host TEXT,
  node_count INTEGER,
  source TEXT,
  imported_at TEXT,
  last_update_at TEXT,
  last_update_ok INTEGER,
  update_interval_min INTEGER DEFAULT 360,
  meta_json TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status);
CREATE INDEX IF NOT EXISTS idx_profiles_country ON profiles(country);
CREATE INDEX IF NOT EXISTS idx_profiles_node ON profiles(node_name);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);
CREATE INDEX IF NOT EXISTS idx_latency_ms ON node_latency(latency_ms);
"""


def init_db() -> Path:
    with connect() as conn:
        conn.executescript(SCHEMA)
    return db_path()


def audit(action: str, profile_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log(at, profile_id, action, detail_json) VALUES (?,?,?,?)",
            (_now(), profile_id, action, json.dumps(detail or {}, ensure_ascii=False)),
        )


def list_audit(limit: int = 100, profile_id: str | None = None) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        if profile_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE profile_id=? ORDER BY id DESC LIMIT ?",
                (profile_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d.pop("detail_json") or "{}")
        except Exception:
            d["detail"] = {}
        out.append(d)
    return out


def upsert_profile_row(prof: Any) -> None:
    """Sync Profile model into SQLite index (not the truth source)."""
    init_db()
    data = prof.model_dump(mode="json") if hasattr(prof, "model_dump") else dict(prof)
    proxy = data.get("proxy") or {}
    env = data.get("env") or {}
    meta = data.get("meta") or {}
    fp = env.get("fingerprint") or {}
    pid = data["id"]
    with connect() as conn:
        existing = conn.execute("SELECT status, last_ip, last_egress_country, last_launch_at, last_stop_at FROM profiles WHERE id=?", (pid,)).fetchone()
        status = existing["status"] if existing else "stopped"
        last_ip = existing["last_ip"] if existing else None
        last_cc = existing["last_egress_country"] if existing else None
        last_launch = existing["last_launch_at"] if existing else None
        last_stop = existing["last_stop_at"] if existing else None
        conn.execute(
            """
            INSERT INTO profiles(
              id, name, engine, chromium_patch, user_data_dir,
              proxy_mode, mihomo_port, node_name, country, timezone_id, locale,
              fingerprint_id, group_name, status,
              last_launch_at, last_stop_at, last_ip, last_egress_country,
              created_at, updated_at, meta_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              engine=excluded.engine,
              chromium_patch=excluded.chromium_patch,
              user_data_dir=excluded.user_data_dir,
              proxy_mode=excluded.proxy_mode,
              mihomo_port=excluded.mihomo_port,
              node_name=excluded.node_name,
              country=excluded.country,
              timezone_id=excluded.timezone_id,
              locale=excluded.locale,
              fingerprint_id=excluded.fingerprint_id,
              group_name=excluded.group_name,
              updated_at=excluded.updated_at,
              meta_json=excluded.meta_json
            """,
            (
                pid,
                data.get("name"),
                data.get("engine"),
                data.get("chromium_patch"),
                data.get("user_data_dir"),
                proxy.get("mode"),
                proxy.get("mihomo_port"),
                proxy.get("node_name"),
                meta.get("expected_country"),
                env.get("timezone_id"),
                env.get("locale"),
                fp.get("template_id"),
                meta.get("group") or "",
                status,
                last_launch,
                last_stop,
                last_ip,
                last_cc,
                data.get("created_at"),
                data.get("updated_at"),
                json.dumps(meta, ensure_ascii=False),
            ),
        )


def delete_profile_row(profile_id: str) -> None:
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        conn.execute("DELETE FROM run_state WHERE profile_id=?", (profile_id,))


def set_run_state(
    profile_id: str,
    *,
    running: bool,
    driver: str | None = None,
    pid: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    init_db()
    with connect() as conn:
        if running:
            conn.execute(
                """
                INSERT INTO run_state(profile_id, running, driver, pid, started_at, extra_json)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(profile_id) DO UPDATE SET
                  running=1, driver=excluded.driver, pid=excluded.pid,
                  started_at=excluded.started_at, extra_json=excluded.extra_json
                """,
                (
                    profile_id,
                    1,
                    driver,
                    pid,
                    _now(),
                    json.dumps(extra or {}, ensure_ascii=False),
                ),
            )
            conn.execute(
                "UPDATE profiles SET status='running', last_launch_at=? WHERE id=?",
                (_now(), profile_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO run_state(profile_id, running, driver, pid, started_at, extra_json)
                VALUES (?,0,NULL,NULL,NULL,NULL)
                ON CONFLICT(profile_id) DO UPDATE SET running=0, driver=NULL, pid=NULL
                """,
                (profile_id,),
            )
            conn.execute(
                "UPDATE profiles SET status='stopped', last_stop_at=? WHERE id=?",
                (_now(), profile_id),
            )


def update_egress(profile_id: str, ip: str | None, country: str | None) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            "UPDATE profiles SET last_ip=?, last_egress_country=? WHERE id=?",
            (ip, country, profile_id),
        )


def get_profile_row(profile_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
    return dict(row) if row else None


def list_profile_rows() -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM profiles ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def list_last_running() -> list[str]:
    """Profiles that were running at last shutdown — for restore-last-session."""
    init_db()
    with connect() as conn:
        # prefer explicit setting
        row = conn.execute("SELECT value_json FROM settings WHERE key='last_session'").fetchone()
        if row:
            try:
                data = json.loads(row["value_json"] or "[]")
                if isinstance(data, list):
                    return [str(x) for x in data]
            except Exception:
                pass
        rows = conn.execute("SELECT profile_id FROM run_state WHERE running=1").fetchall()
    return [r["profile_id"] for r in rows]


def save_last_session(profile_ids: list[str]) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value_json) VALUES ('last_session', ?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json
            """,
            (json.dumps(profile_ids, ensure_ascii=False),),
        )


def favorite_add(sub: str, node_name: str, note: str = "") -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO node_favorites(sub, node_name, note, created_at)
            VALUES (?,?,?,?)
            ON CONFLICT(sub, node_name) DO UPDATE SET note=excluded.note
            """,
            (sub, node_name, note, _now()),
        )


def favorite_remove(sub: str, node_name: str) -> None:
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM node_favorites WHERE sub=? AND node_name=?", (sub, node_name))


def favorites_list(sub: str | None = None) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        if sub:
            rows = conn.execute(
                "SELECT * FROM node_favorites WHERE sub=? ORDER BY created_at DESC", (sub,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM node_favorites ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def latency_upsert(sub: str, node_name: str, latency_ms: int | None, ok: bool, error: str = "") -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO node_latency(sub, node_name, latency_ms, ok, checked_at, error)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(sub, node_name) DO UPDATE SET
              latency_ms=excluded.latency_ms, ok=excluded.ok,
              checked_at=excluded.checked_at, error=excluded.error
            """,
            (sub, node_name, latency_ms, 1 if ok else 0, _now(), error),
        )


def latency_list(sub: str = "default") -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM node_latency WHERE sub=? ORDER BY CASE WHEN ok=1 THEN 0 ELSE 1 END, latency_ms ASC",
            (sub,),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_subscription(meta: dict[str, Any], *, ok: bool = True) -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO subscriptions(name, url, url_host, node_count, source, imported_at,
              last_update_at, last_update_ok, update_interval_min, meta_json)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
              url=excluded.url, url_host=excluded.url_host, node_count=excluded.node_count,
              source=excluded.source, last_update_at=excluded.last_update_at,
              last_update_ok=excluded.last_update_ok, meta_json=excluded.meta_json,
              imported_at=COALESCE(subscriptions.imported_at, excluded.imported_at)
            """,
            (
                meta.get("name"),
                meta.get("url"),
                meta.get("url_host"),
                meta.get("node_count"),
                meta.get("source"),
                meta.get("imported_at"),
                _now(),
                1 if ok else 0,
                meta.get("update_interval_min", 360),
                json.dumps(meta, ensure_ascii=False),
            ),
        )


def delete_subscription_row(name: str) -> None:
    """Remove subscription index row (filesystem delete is separate)."""
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM subscriptions WHERE name=?", (name,))
        conn.execute("DELETE FROM node_latency WHERE sub=?", (name,))


def list_subscription_rows() -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM subscriptions ORDER BY name").fetchall()
    return [dict(r) for r in rows]
