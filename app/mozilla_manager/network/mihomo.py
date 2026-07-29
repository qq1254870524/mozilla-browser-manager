from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from ..paths import MIHOMO_DIR, NODES_DIR, ensure_layout, p, safe_resolve
from . import node_store

_PROCS: dict[int, subprocess.Popen] = {}  # port -> proc
_DEATH_WATCH_STARTED = False
_DEATH_WATCH_LOCK = __import__("threading").Lock()
_INTENTIONAL_STOPS: set[int] = set()  # ports we are actively stopping


def _audit_death(port: int, proc: "subprocess.Popen | None", extra: dict | None = None) -> None:
    """Log unexpected mihomo process exit (not via stop_mihomo)."""
    try:
        from mozilla_manager.paths import p as root_p, ensure_layout, safe_resolve
        ensure_layout()
        logp = safe_resolve(root_p("logs", "mihomo-death-audit.log"))
        import time as _time
        rc = None
        pid = None
        try:
            if proc is not None:
                pid = proc.pid
                rc = proc.poll()
        except Exception:
            pass
        line = {
            "t": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            "port": int(port),
            "pid": pid,
            "returncode": rc,
            "extra": extra or {},
        }
        with open(logp, "a", encoding="utf-8") as af:
            af.write(json.dumps(line, ensure_ascii=False) + "\n")
        try:
            from mozilla_manager import db
            db.audit("mihomo_unexpected_exit", None, line)
        except Exception:
            pass
    except Exception:
        pass


def _restart_mihomo_for_live_port(port: int) -> dict[str, Any]:
    """If a live browser profile still owns this port, bring mihomo back."""
    try:
        from mozilla_manager.store import ProfileStore
        from mozilla_manager.runtime_registry import list_running
    except Exception as e:
        return {"ok": False, "error": f"import: {e}"}
    try:
        running = list_running() or {}
    except Exception:
        running = {}
    store = ProfileStore()
    owner = None
    for pid in list(running.keys()):
        try:
            prof = store.get(pid)
        except Exception:
            continue
        if getattr(prof.proxy, "mode", None) != "mihomo":
            continue
        if int(getattr(prof.proxy, "mihomo_port", 0) or 0) != int(port):
            continue
        owner = prof
        break
    if owner is None:
        return {"ok": False, "error": "no live owner", "port": port}
    sub = (owner.meta or {}).get("sub") or "default"
    node = owner.proxy.node_name or ""
    cfp = (owner.meta or {}).get("tls_client_fingerprint") or "chrome"
    # clear intentional mark so start can proceed
    _INTENTIONAL_STOPS.discard(int(port))
    r = start_mihomo(int(port), subscription_name=sub, node_name=node, client_fingerprint=cfp)
    try:
        from mozilla_manager import db
        db.audit("mihomo_death_autorestart", owner.id, {"port": port, "result": r})
    except Exception:
        pass
    return {"ok": bool((r or {}).get("ok")), "port": port, "profile_id": owner.id, "start": r}


def _ensure_mihomo_death_watch(interval: float = 1.0) -> None:
    """Watch _PROCS for exits that did not go through stop_mihomo; auto-restart if needed."""
    global _DEATH_WATCH_STARTED
    with _DEATH_WATCH_LOCK:
        if _DEATH_WATCH_STARTED:
            return
        _DEATH_WATCH_STARTED = True

    def _loop() -> None:
        import time
        while True:
            try:
                for port, proc in list(_PROCS.items()):
                    try:
                        rc = proc.poll()
                    except Exception:
                        rc = None
                    if rc is None:
                        continue
                    # process exited
                    intentional = int(port) in _INTENTIONAL_STOPS
                    _PROCS.pop(port, None)
                    if intentional:
                        _INTENTIONAL_STOPS.discard(int(port))
                        continue
                    _audit_death(port, proc, {"note": "poll_nonzero_without_stop"})
                    try:
                        _restart_mihomo_for_live_port(int(port))
                    except Exception as e:
                        _audit_death(port, proc, {"restart_error": str(e)})
            except Exception:
                pass
            time.sleep(interval)

    import threading
    threading.Thread(target=_loop, name="mm-mihomo-death-watch", daemon=True).start()



def mihomo_binary() -> Path:
    ensure_layout()
    name = "mihomo.exe" if platform.system() == "Windows" else "mihomo"
    return MIHOMO_DIR / name


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    """True if we can bind TCP on host:port (port is free)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.25) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def allocate_port(profile_id: str, base: int = 17800) -> int:
    """Pick a free mixed-port in [base, base+200).

    Prefer stable hash slot when free; otherwise scan for the first free port.
    NEVER return a port already bound by another process (CC2/other mihomo) —
    that caused Mixed-port bind failure while start() still looked "ok", and the
    browser hit net::ERR_PROXY_CONNECTION_FAILED / total offline.
    """
    import socket
    h = sum(ord(c) for c in (profile_id or "x"))
    preferred = base + (h % 200)
    candidates = [preferred] + [base + ((h + i) % 200) for i in range(1, 200)]
    # also avoid external-controller (+1000) and dns (+2000) collisions roughly
    for port in candidates:
        if port < 1024 or port > 60000:
            continue
        # mixed + controller + dns must be free-ish
        if not _port_free(port):
            continue
        if not _port_free(port + 1000):
            continue
        if not _port_free(port + 2000):
            continue
        return int(port)
    # last resort: ephemeral bind
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port




def _sanitize_config(data: dict[str, Any], port: int, node_name: str | None = None) -> dict[str, Any]:
    """Make subscription YAML runnable without external geodata downloads."""
    proxies = [x for x in (data.get("proxies") or []) if isinstance(x, dict) and x.get("name")]

    def _is_placeholder(x: dict[str, Any]) -> bool:
        srv = str(x.get("server") or "")
        name = str(x.get("name") or "")
        if srv in ("127.0.0.1", "0.0.0.0", "localhost") or srv.startswith("127."):
            return True
        # common subscription info lines that are not real egress
        low = name.lower()
        info_keys = ("剩余流量", "距离下次", "套餐到期", "官网", "更新", "expire", "traffic", "流量", "到期")
        if any(k.lower() in low for k in info_keys):
            return True
        return False

    real = [x for x in proxies if not _is_placeholder(x)]
    placeholders = [x for x in proxies if _is_placeholder(x)]
    proxies = real + placeholders
    pnames = [x["name"] for x in real] or [x["name"] for x in proxies]
    real_set = set(pnames)

    def _order_group_proxies(ps: list[Any]) -> list[Any]:
        """Real nodes first; drop pure junk defaults to 127.0.0.1 placeholders when real exist."""
        seen: set[str] = set()
        ordered: list[Any] = []
        # preferred selected node first
        if node_name and node_name not in ("default", None, "") and node_name in real_set:
            ordered.append(node_name)
            seen.add(node_name)
        # keep existing non-placeholder names that are real or group refs
        for x in ps or []:
            if not isinstance(x, str) or x in seen:
                continue
            # skip DIRECT/REJECT reordering later
            if x in real_set:
                ordered.append(x)
                seen.add(x)
        for x in ps or []:
            if not isinstance(x, str) or x in seen:
                continue
            # keep group names / DIRECT / REJECT
            ordered.append(x)
            seen.add(x)
        # ensure all real nodes available in select lists when original was sparse
        for n in pnames:
            if n not in seen:
                ordered.append(n)
                seen.add(n)
        if "DIRECT" not in seen:
            ordered.append("DIRECT")
        return ordered or (pnames[:1] + ["DIRECT"] if pnames else ["DIRECT"])

    groups_in = data.get("proxy-groups") or []
    groups: list[dict[str, Any]] = []
    for g in groups_in:
        if not isinstance(g, dict) or not g.get("name"):
            continue
        g2 = dict(g)
        if g2.get("type") in ("url-test", "fallback", "load-balance"):
            g2["type"] = "select"
            g2.pop("url", None)
            g2.pop("interval", None)
            g2.pop("tolerance", None)
        if isinstance(g2.get("proxies"), list):
            g2["proxies"] = _order_group_proxies(list(g2["proxies"]))
        groups.append(g2)

    gnames = {g["name"] for g in groups}
    if "PROXY" not in gnames:
        groups.insert(
            0,
            {
                "name": "PROXY",
                "type": "select",
                "proxies": _order_group_proxies(list(pnames)),
            },
        )
    else:
        # force selected node to head of PROXY
        if node_name and node_name not in ("default", None, ""):
            for g in groups:
                if g.get("name") == "PROXY" and isinstance(g.get("proxies"), list):
                    g["proxies"] = _order_group_proxies(list(g["proxies"]))
                    break

    out: dict[str, Any] = {
        "mixed-port": port,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "ipv6": False,  # dual-stack often stalls via flaky nodes; v4-first is stabler for browser
        "find-process-mode": "off",
        "external-controller": f"127.0.0.1:{port + 1000}",
        "secret": "",
        # Keep long-lived browser sockets from being killed on brief upstream blips
        "tcp-concurrent": True,
        "global-client-fingerprint": "chrome",
        "profile": {"store-selected": True, "store-fake-ip": True},
        "dns": {
            "enable": True,
            "listen": f"127.0.0.1:{port + 2000}",
            # redir-host avoids fake-ip surprises for tools probing mihomo DNS;
            # browser via SOCKS still does its own resolve unless socks remote-dns.
            "enhanced-mode": "redir-host",
            "nameserver": ["8.8.8.8", "1.1.1.1", "208.67.222.222"],
            "fallback": ["1.0.0.1", "8.8.4.4"],
            "fallback-filter": {"geoip": True, "geoip-code": "CN", "ipcidr": ["240.0.0.0/4"]},
        },
        "proxies": proxies,
        "proxy-groups": groups,
        "rules": ["MATCH,PROXY"],
    }
    return out


def write_profile_config(port: int, subscription_name: str = "default", node_name: str | None = None, client_fingerprint: str | None = None) -> Path:
    ensure_layout()
    # v5: prefer runtime/nodes; keep data/nodes for process pid/cfg mirror
    cfg_path = safe_resolve(NODES_DIR / f"mihomo-{port}.yaml")
    # also mirror under runtime/nodes/mihomo
    try:
        rt = safe_resolve(p("runtime", "nodes", "mihomo"))
        rt.mkdir(parents=True, exist_ok=True)
    except Exception:
        rt = None

    data = node_store.load_clash(subscription_name)
    # Empty "default" (or missing sub) used to produce DIRECT-only configs while UI
    # still showed nodes — fall back to active subscription with real proxies.
    def _proxy_count(d):
        try:
            return len([x for x in (d or {}).get("proxies") or [] if isinstance(x, dict) and x.get("name")])
        except Exception:
            return 0

    if not data or _proxy_count(data) == 0:
        sub_yaml = NODES_DIR / f"sub_{subscription_name}.yaml"
        if sub_yaml.exists():
            try:
                data = yaml.safe_load(sub_yaml.read_text(encoding="utf-8", errors="ignore")) or {}
            except Exception:
                data = data or {}
    if (not data or _proxy_count(data) == 0) and subscription_name not in ("", None):
        try:
            active = node_store.get_active()
            if active and active != subscription_name:
                data = node_store.load_clash(active) or data
        except Exception:
            pass
    if not isinstance(data, dict) or not data or _proxy_count(data) == 0:
        # last resort: any sub with proxies
        try:
            for name in node_store.list_sub_names() or []:
                cand = node_store.load_clash(name)
                if _proxy_count(cand) > 0:
                    data = cand
                    break
        except Exception:
            pass
    if not isinstance(data, dict) or not data:
        data = {
            "proxies": [],
            "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": ["DIRECT"]}],
            "rules": ["MATCH,DIRECT"],
        }

    data = _sanitize_config(data, port, node_name=node_name)
    # v6 TLS persona → mihomo client-fingerprint on outbounds
    try:
        from mozilla_manager.stealth.tls_ja import apply_client_fingerprint_to_proxies
        cfp = client_fingerprint or "chrome"
        proxies = data.get("proxies") or []
        data["proxies"] = apply_client_fingerprint_to_proxies(proxies, cfp)
    except Exception:
        pass
    if node_name:
        data["_mozilla_selected_node"] = node_name

    cfg_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    cfg_path.write_text(cfg_text, encoding="utf-8")
    try:
        rt_cfg = safe_resolve(p("runtime", "nodes", "mihomo", f"mihomo-{port}.yaml"))
        rt_cfg.parent.mkdir(parents=True, exist_ok=True)
        rt_cfg.write_text(cfg_text, encoding="utf-8")
    except Exception:
        pass
    return cfg_path


def _apply_selected_node(port: int, node_name: str | None) -> dict[str, Any]:
    """Force PROXY (and common group aliases) onto selected node via external-controller."""
    if not node_name or node_name in ("default",):
        return {"ok": True, "skipped": True}
    try:
        from . import mihomo_api
    except Exception as e:
        return {"ok": False, "error": f"mihomo_api import: {e}"}
    results = []
    # try PROXY first, then a few common CN aliases
    for group in ("PROXY", "节点选择", "Proxy", "🚀 节点选择", "全局"):
        r = mihomo_api.switch_proxy(port, node_name, group=group)
        results.append({"group": group, **r})
        if r.get("ok"):
            break
    ok = any(x.get("ok") for x in results)
    # also read back current selection
    cur = mihomo_api.get_proxy_group(port, "PROXY")
    now = None
    try:
        now = (cur.get("data") or {}).get("now")
    except Exception:
        now = None
    return {"ok": ok, "node": node_name, "now": now, "attempts": results, "note": "住宅/动态节点出口 IP 可能每次不同，属正常"}


def start_mihomo(port: int, subscription_name: str = "default", node_name: str | None = None, client_fingerprint: str | None = None) -> dict[str, Any]:
    bin_path = mihomo_binary()
    if not bin_path.exists():
        return {"ok": False, "error": f"mihomo binary missing: {bin_path}"}

    # Always rewrite config so node selection / sub changes take effect even on reuse.
    cfg = write_profile_config(
        port,
        subscription_name=subscription_name,
        node_name=node_name,
        client_fingerprint=client_fingerprint,
    )

    # Reuse live process if we already own it — still switch node via API.
    if port in _PROCS and _PROCS[port].poll() is None:
        switched = _apply_selected_node(port, node_name)
        return {
            "ok": True,
            "port": port,
            "reused": True,
            "pid": _PROCS[port].pid,
            "cfg": str(cfg),
            "switched": switched,
            "node": node_name,
            "note": "reused mihomo; config rewritten + switch_proxy applied (residential IP may rotate)",
        }

    # If port is occupied by an orphan mihomo (server restarted / stop missed), reclaim it.
    import socket
    sock = socket.socket()
    sock.settimeout(0.2)
    occupied = False
    try:
        sock.connect(("127.0.0.1", port))
        occupied = True
    except Exception:
        occupied = False
    finally:
        try:
            sock.close()
        except Exception:
            pass
    if occupied:
        # Only reuse if THIS port is our mihomo (pid file / cmdline marker). Foreign
        # listeners (other apps on 178xx) must NOT be treated as success — browser
        # would speak SOCKS to the wrong process → ERR_PROXY_CONNECTION_FAILED.
        ours = False
        try:
            for item in list_live_mihomo_processes():
                if int(item.get("port") or 0) == int(port):
                    ours = True
                    break
        except Exception:
            ours = False
        if not ours:
            pid_file = NODES_DIR / f"mihomo-{port}.pid"
            if pid_file.exists():
                try:
                    # pid file alone is weak; still try stop our recorded pid only
                    ours = True
                except Exception:
                    pass
        if ours:
            try:
                switched = _apply_selected_node(port, node_name)
                if switched.get("ok") or _port_listening(port):
                    return {
                        "ok": True,
                        "port": port,
                        "reused": True,
                        "orphan_reused": True,
                        "cfg": str(cfg),
                        "switched": switched,
                        "node": node_name,
                        "note": "our mihomo hot-switched/reused",
                    }
            except Exception:
                pass
            stop_mihomo(port, reason="start_reclaim_our_occupied")
            time.sleep(0.35)
        else:
            # Port held by foreign process — caller should allocate a free port.
            return {
                "ok": False,
                "port": port,
                "error": f"port {port} occupied by foreign process (not Mozilla mihomo). re-allocate.",
                "foreign_port": True,
            }

    log = safe_resolve(p("logs", f"mihomo-{port}.log"))
    f = open(log, "a", encoding="utf-8")
    popen_kwargs: dict[str, Any] = {
        "cwd": str(MIHOMO_DIR),
        "stdout": f,
        "stderr": subprocess.STDOUT,
    }
    if platform.system() == "Windows":
        # Independent process group so client/console signals do not kill egress.
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        # New session: survive parent SIGHUP / shell exit (WSL/dev & nohup tests).
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        [str(bin_path), "-f", str(cfg)],
        **popen_kwargs,
    )
    _PROCS[port] = proc
    try:
        _ensure_mihomo_death_watch()
    except Exception:
        pass
    pid_file = safe_resolve(NODES_DIR / f"mihomo-{port}.pid")
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    for _ in range(12):
        time.sleep(0.3)
        if proc.poll() is not None:
            break
        s = socket.socket()
        s.settimeout(0.2)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            break
        except Exception:
            try:
                s.close()
            except Exception:
                pass
    alive = proc.poll() is None
    err = None
    mixed_up = False
    if not alive:
        try:
            err = log.read_text(encoding="utf-8", errors="ignore")[-800:]
        except Exception:
            err = "process exited immediately; see log"
    else:
        # CRITICAL: process can be alive while Mixed-port failed ("address already in use").
        for _ in range(15):
            if _port_listening(port):
                mixed_up = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.2)
        if not mixed_up:
            try:
                tail = log.read_text(encoding="utf-8", errors="ignore")[-1200:]
            except Exception:
                tail = ""
            err = (
                f"mihomo process up but mixed-port {port} not listening "
                f"(bind failure or conflict). log_tail={tail[-400:]}"
            )
            # kill useless process so we do not leak "half-alive" cores
            try:
                stop_mihomo(port, reason="start_mixed_port_dead")
            except Exception:
                pass
            alive = False
    switched = {}
    if alive and mixed_up and node_name:
        # external-controller comes up slightly after mixed-port
        for _ in range(8):
            switched = _apply_selected_node(port, node_name)
            if switched.get("ok"):
                break
            time.sleep(0.25)
    return {
        "ok": bool(alive and mixed_up),
        "port": port,
        "pid": proc.pid if proc is not None else None,
        "cfg": str(cfg),
        "log": str(log),
        "error": err,
        "switched": switched,
        "node": node_name,
        "mixed_port_up": mixed_up,
    }


def stop_mihomo(port: int, *, reason: str = "unspecified", profile_id: str | None = None) -> dict[str, Any]:
    """Stop mihomo for port. Always log caller reason — critical for offline debugging."""
    try:
        _INTENTIONAL_STOPS.add(int(port))
    except Exception:
        pass
    try:
        from mozilla_manager.paths import p as root_p, ensure_layout, safe_resolve
        ensure_layout()
        logp = safe_resolve(root_p("logs", "mihomo-stop-audit.log"))
        import traceback, time as _time
        with open(logp, "a", encoding="utf-8") as af:
            af.write(
                f"\n[{_time.strftime('%Y-%m-%dT%H:%M:%S')}] port={port} reason={reason} profile={profile_id}\n"
            )
            af.write("".join(traceback.format_stack(limit=10)))
    except Exception:
        pass
    try:
        from mozilla_manager import db
        db.audit("mihomo_stop", profile_id, {"port": int(port), "reason": str(reason)})
    except Exception:
        pass
    proc = _PROCS.pop(port, None)
    pid_file = NODES_DIR / f"mihomo-{port}.pid"
    pids: set[int] = set()
    if proc and proc.poll() is None:
        pids.add(proc.pid)
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if pid_file.exists():
        try:
            pids.add(int(pid_file.read_text().strip()))
        except Exception:
            pass
    # also scan /proc for any mihomo using this port config (multi-instance orphans)
    try:
        marker = f"mihomo-{int(port)}.yaml"
        proc_root = Path("/proc")
        if proc_root.exists():
            for ent in proc_root.iterdir():
                if not ent.name.isdigit():
                    continue
                try:
                    cmd = Path(f"/proc/{ent.name}/cmdline").read_text(errors="ignore").replace("\x00", " ")
                except Exception:
                    continue
                if marker in cmd and "mihomo" in cmd and "Mozilla" in cmd:
                    pids.add(int(ent.name))
    except Exception:
        pass
    try:
        for item in list_live_mihomo_processes():
            if int(item.get("port") or 0) == int(port) and item.get("pid"):
                pids.add(int(item["pid"]))
    except Exception:
        pass
    for pid in list(pids):
        if not pid:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    time.sleep(0.25)
    for pid in list(pids):
        if not pid:
            continue
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    if pid_file.exists():
        try:
            pid_file.unlink()
        except Exception:
            pass
    return {"ok": True, "port": port, "pid": next(iter(pids), None), "pids": sorted(pids)}


def status_mihomo() -> list[dict[str, Any]]:
    out = []
    for port, proc in list(_PROCS.items()):
        out.append({"port": port, "pid": proc.pid, "alive": proc.poll() is None})
    # also pid files
    for f in NODES_DIR.glob("mihomo-*.pid"):
        try:
            port = int(f.stem.split("-")[1])
        except Exception:
            continue
        if any(x["port"] == port for x in out):
            continue
        pid = int(f.read_text().strip() or 0)
        alive = False
        if pid:
            try:
                os.kill(pid, 0)
                alive = True
            except Exception:
                alive = False
        out.append({"port": port, "pid": pid, "alive": alive})
    return out


def _pid_cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_text(errors="ignore").replace("\x00", " ")
    except Exception:
        return ""


def list_live_mihomo_processes() -> list[dict[str, Any]]:
    """Discover Mozilla-owned mihomo processes via /proc (Linux) + pid files.

    Returns one entry per (port, pid). Multiple processes on the same port are listed separately.
    """
    bin_path = str(mihomo_binary().resolve())
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    def _add(port: int, pid: int, source: str, alive: bool | None = None, cmd: str = "") -> None:
        if not port:
            return
        key = (int(port), int(pid or 0))
        if key in seen and pid:
            return
        if alive is None:
            alive = False
            if pid:
                try:
                    os.kill(pid, 0)
                    alive = True
                except Exception:
                    alive = False
        if not cmd and pid and alive:
            cmd = _pid_cmdline(pid)
        rows.append({"port": int(port), "pid": int(pid or 0), "alive": bool(alive), "source": source, "cmd": (cmd or "")[:240]})
        if pid:
            seen.add(key)

    for f in NODES_DIR.glob("mihomo-*.pid"):
        try:
            port = int(f.stem.split("-")[1])
            pid = int(f.read_text().strip() or 0)
        except Exception:
            continue
        _add(port, pid, "pidfile")

    proc_root = Path("/proc")
    if proc_root.exists():
        for ent in proc_root.iterdir():
            if not ent.name.isdigit():
                continue
            pid = int(ent.name)
            cmd = _pid_cmdline(pid)
            if not cmd:
                continue
            if "mihomo" not in cmd:
                continue
            # only Mozilla tree
            if "Mozilla" not in cmd and str(MIHOMO_DIR) not in cmd:
                continue
            if bin_path not in cmd and "runtime/mihomo/mihomo" not in cmd and str(MIHOMO_DIR / "mihomo") not in cmd:
                # still allow if cfg path is under Mozilla
                if "/home/baoge/Mozilla/" not in cmd and "Mozilla/data/nodes" not in cmd:
                    continue
            port = None
            for token in cmd.split():
                name = Path(token).name
                if name.startswith("mihomo-") and name.endswith(".yaml"):
                    try:
                        port = int(name[len("mihomo-") : -len(".yaml")])
                    except Exception:
                        port = None
            if port is None:
                continue
            _add(port, pid, "proc", alive=True, cmd=cmd)

    for port, proc in list(_PROCS.items()):
        alive = proc.poll() is None
        _add(int(port), int(proc.pid), "memory", alive=alive)

    rows.sort(key=lambda x: (x.get("port") or 0, x.get("pid") or 0))
    return rows


def cleanup_orphan_mihomo(*, keep_ports: set[int] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Stop mihomo instances whose mixed-port is not in keep_ports.

    keep_ports defaults to ports used by currently running profiles (runtime registry).
    Always safe: never touches non-Mozilla mihomo binaries.
    """
    keep = set(keep_ports or [])
    if keep_ports is None:
        try:
            from mozilla_manager.runtime_registry import list_running
            from mozilla_manager.store import ProfileStore

            running = list_running() or {}
            store = ProfileStore()
            for pid in running.keys():
                try:
                    prof = store.get(pid)
                    port = getattr(prof.proxy, "mihomo_port", None)
                    if port:
                        keep.add(int(port))
                except Exception:
                    continue
        except Exception:
            pass

    live = list_live_mihomo_processes()
    stopped: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    ports_to_stop: set[int] = set()
    for item in live:
        port = int(item.get("port") or 0)
        if not port:
            continue
        if port in keep:
            kept.append(item)
            continue
        if not item.get("alive"):
            if not dry_run:
                pf = NODES_DIR / f"mihomo-{port}.pid"
                try:
                    if pf.exists():
                        pf.unlink()
                except Exception:
                    pass
            stopped.append({**item, "action": "stale-pid-cleaned" if not dry_run else "would-clean-stale"})
            continue
        ports_to_stop.add(port)
        if dry_run:
            stopped.append({**item, "action": "would-stop"})
        else:
            stopped.append({**item, "action": "queued-stop"})

    if not dry_run:
        for port in sorted(ports_to_stop):
            r = stop_mihomo(port, reason="cleanup_orphan")
            # force-kill any remaining pids on this port
            for item in list_live_mihomo_processes():
                if int(item.get("port") or 0) != port:
                    continue
                pid = int(item.get("pid") or 0)
                if not pid:
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
            for row in stopped:
                if int(row.get("port") or 0) == port and row.get("action") == "queued-stop":
                    row["action"] = "stopped"
                    row["stop"] = r

    return {
        "ok": True,
        "dry_run": dry_run,
        "keep_ports": sorted(keep),
        "kept": kept,
        "stopped": stopped,
        "stopped_count": len([x for x in stopped if x.get("action") in ("stopped", "would-stop", "queued-stop")]),
        "live_before": len([x for x in live if x.get("alive")]),
    }
