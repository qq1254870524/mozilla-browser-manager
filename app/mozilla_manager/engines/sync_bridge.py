"""Run Playwright/Camoufox sync APIs safely from FastAPI/asyncio.

Playwright Sync API starts a greenlet + asyncio loop on the *calling thread* and
keeps that loop running for the life of the browser. Reusing a ThreadPool worker
for a second engine therefore hits:

  "It looks like you are using Playwright Sync API inside the asyncio loop"

Fix: every profile gets a dedicated long-lived thread. launch/stop/rpc all run
on that same thread.
"""
from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_LOCK = threading.Lock()
# profile_id -> Worker
_WORKERS: dict[str, "BrowserWorker"] = {}
# for one-shot jobs not tied to a profile (rare)
_ONE_SHOT_TIMEOUT = 300.0


class BrowserWorker:
    def __init__(self, key: str):
        self.key = key
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name=f"mm-browser-{key[:24]}", daemon=True)
        self._started = threading.Event()
        self._closed = False
        self._thread.start()
        self._started.wait(timeout=5)

    def _loop(self) -> None:
        self._started.set()
        while True:
            item = self._q.get()
            if item is None:
                break
            fn, out_q = item
            try:
                result = fn()
                out_q.put(("ok", result))
            except BaseException as e:
                out_q.put(("err", e, traceback.format_exc()))

    def call(self, fn: Callable[[], T], *, timeout: float | None = 300.0) -> T:
        if self._closed:
            raise RuntimeError(f"browser worker closed: {self.key}")
        # Re-entrant: already on this worker thread (e.g. RPA launch nesting).
        if threading.current_thread() is self._thread:
            return fn()
        out_q: queue.Queue = queue.Queue()
        self._q.put((fn, out_q))
        kind, *rest = out_q.get(timeout=timeout)
        if kind == "ok":
            return rest[0]  # type: ignore[return-value]
        err = rest[0]
        raise err

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._q.put(None)
        self._thread.join(timeout=5)


def get_worker(profile_id: str) -> BrowserWorker:
    with _LOCK:
        w = _WORKERS.get(profile_id)
        if w is None or w._closed or not w._thread.is_alive():
            w = BrowserWorker(profile_id)
            _WORKERS[profile_id] = w
        return w


def drop_worker(profile_id: str) -> None:
    with _LOCK:
        w = _WORKERS.pop(profile_id, None)
    if w is not None:
        try:
            w.close()
        except Exception:
            pass


def call_in_profile_thread(profile_id: str, fn: Callable[[], T], *, timeout: float | None = 300.0) -> T:
    return get_worker(profile_id).call(fn, timeout=timeout)


def call_sync(fn: Callable[[], T], *, timeout: float | None = 300.0, profile_id: str | None = None) -> T:
    """Back-compat. Prefer call_in_profile_thread when profile_id is known.

    One-shot path uses a fresh dedicated thread (never a shared pool) so a
    still-running Playwright loop cannot be reused by the next engine.
    """
    if profile_id:
        return call_in_profile_thread(profile_id, fn, timeout=timeout)

    result: dict[str, Any] = {}
    done = threading.Event()

    def runner() -> None:
        try:
            result["value"] = fn()
        except BaseException as e:
            result["error"] = e
            result["tb"] = traceback.format_exc()
        finally:
            done.set()

    t = threading.Thread(target=runner, name="mm-browser-oneshot", daemon=True)
    t.start()
    if not done.wait(timeout=timeout or _ONE_SHOT_TIMEOUT):
        raise TimeoutError("browser sync call timed out")
    if "error" in result:
        raise result["error"]
    return result["value"]
