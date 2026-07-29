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


def mihomo_binary() -> Path:
    ensure_layout()
    name = "mihomo.exe" if platform.system() == "Windows" else "mihomo"
    return MIHOMO_DIR / name


def allocate_port(profile_id: str, base: int = 17800) -> int:
    """Stable-ish port from profile id hash in 17800-17999."""
    h = sum(ord(c) for c in profile_id)
    return base + (h % 200)




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
    if not data:
        sub_yaml = NODES_DIR / f"sub_{subscription_name}.yaml"
        if sub_yaml.exists():
            data = yaml.safe_load(sub_yaml.read_text(encoding="utf-8", errors="ignore")) or {}
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
        # Try hot-switch first without kill (keeps browser sockets if same port)
        try:
            switched = _apply_selected_node(port, node_name)
            if switched.get("ok"):
                # adopt unknown pid if possible
                return {
                    "ok": True,
                    "port": port,
                    "reused": True,
                    "orphan_reused": True,
                    "cfg": str(cfg),
                    "switched": switched,
                    "node": node_name,
                    "note": "orphan mihomo hot-switched; full restart skipped",
                }
        except Exception:
            pass
        stop_mihomo(port)
        time.sleep(0.25)

    log = safe_resolve(p("logs", f"mihomo-{port}.log"))
    f = open(log, "a", encoding="utf-8")
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        [str(bin_path), "-f", str(cfg)],
        cwd=str(MIHOMO_DIR),
        stdout=f,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    _PROCS[port] = proc
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
    if not alive:
        try:
            err = log.read_text(encoding="utf-8", errors="ignore")[-800:]
        except Exception:
            err = "process exited immediately; see log"
    switched = {}
    if alive and node_name:
        # external-controller comes up slightly after mixed-port
        for _ in range(8):
            switched = _apply_selected_node(port, node_name)
            if switched.get("ok"):
                break
            time.sleep(0.25)
    return {
        "ok": alive,
        "port": port,
        "pid": proc.pid,
        "cfg": str(cfg),
        "log": str(log),
        "error": err,
        "switched": switched,
        "node": node_name,
    }


def stop_mihomo(port: int) -> dict[str, Any]:
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
            r = stop_mihomo(port)
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
