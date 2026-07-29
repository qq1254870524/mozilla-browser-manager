"""v4/v6 WebRTC / DNS anti-leak helpers for browser launch."""
from __future__ import annotations

import json
from typing import Any


DEFAULT_DOH_SERVERS = [
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/dns-query",
    "https://dns.alidns.com/dns-query",
    "https://dns.quad9.net/dns-query",
]


def webrtc_chromium_args(mode: str = "disable") -> list[str]:
    """
    mode:
      off      — do nothing
      disable  — block non-proxied UDP + disable WebRTC where possible
      spoof    — force proxy-only IP handling (候选只走代理路径)
    """
    mode = (mode or "disable").lower()
    if mode in ("off", "none", ""):
        return []
    args = [
        "--enforce-webrtc-ip-permission-check",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    ]
    if mode == "disable":
        args += [
            "--disable-webrtc-hw-encoding",
            "--disable-webrtc-hw-decoding",
        ]
    return args


def doh_chromium_args(
    doh_template: str | None = None,
    mode: str = "automatic",
    *,
    servers: list[str] | None = None,
    force: bool = False,
) -> list[str]:
    """DNS-over-HTTPS templates (Chromium).

    IMPORTANT: mode=secure (DoH-only, no fallback) frequently causes *total*
    offline when combined with SOCKS5/mihomo — Chromium cannot bootstrap DNS.
    Default is automatic; secure-only only when explicitly requested AND no proxy.
    """
    mode_l = (mode or "automatic").lower()
    if mode_l in ("off", "none", "false", "disable", "proxy"):
        return []
    # Map aliases
    if mode_l in ("secure-only", "trr-only", "forced"):
        mode_l = "secure"
    if mode_l not in ("secure", "automatic", "off"):
        mode_l = "automatic"
    # force flag alone must NOT upgrade automatic → secure (that killed networking)
    if force and mode_l == "off":
        mode_l = "automatic"
    tmpls: list[str] = []
    if doh_template:
        tmpls.append(str(doh_template).strip())
    for s in servers or []:
        s = str(s).strip()
        if s and s not in tmpls:
            tmpls.append(s)
    if not tmpls:
        tmpls = list(DEFAULT_DOH_SERVERS[:3])
    joined = " ".join(tmpls)
    return [
        f"--dns-over-https-mode={mode_l}",
        f"--dns-over-https-templates={joined}",
    ]


def webrtc_init_script(mode: str = "disable", proxy_ip: str | None = None) -> str:
    """JS hardening for WebRTC. spoof mode tries to hide local candidates."""
    mode = (mode or "disable").lower()
    if mode in ("off", "none", ""):
        return ""
    proxy_ip_js = json.dumps(proxy_ip)
    if mode == "disable":
        return """
(() => {
  const block = () => { throw new Error('WebRTC disabled by Mozilla Manager'); };
  try {
    const noop = function() { return null; };
    window.RTCPeerConnection = noop;
    window.webkitRTCPeerConnection = noop;
    window.mozRTCPeerConnection = noop;
    if (window.RTCSessionDescription) {/* keep */}
  } catch (e) {}
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      navigator.mediaDevices.getUserMedia = () => Promise.reject(new Error('disabled'));
    }
  } catch (e) {}
})();
""".strip()
    # spoof: wrap RTCPeerConnection and filter host candidates / rewrite
    return f"""
(() => {{
  const proxyIp = {proxy_ip_js};
  const Orig = window.RTCPeerConnection || window.webkitRTCPeerConnection;
  if (!Orig) return;
  const Wrapped = function(config, constraints) {{
    try {{
      config = config || {{}};
      config.iceTransportPolicy = 'relay';
    }} catch (e) {{}}
    const pc = new Orig(config, constraints);
    const origAdd = pc.addEventListener.bind(pc);
    pc.addEventListener = function(type, listener, opts) {{
      if (type === 'icecandidate') {{
        const wrap = (ev) => {{
          try {{
            if (ev && ev.candidate && ev.candidate.candidate) {{
              const c = ev.candidate.candidate;
              if (/ typ host/.test(c) || /\\b(10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[0-1])\\.)/.test(c)) {{
                const fake = ev;
                try {{
                  Object.defineProperty(fake, 'candidate', {{ value: null }});
                }} catch (e) {{
                  return listener({{ candidate: null }});
                }}
                return listener(fake);
              }}
              if (proxyIp && / typ (srflx|host)/.test(c)) {{
                return listener({{ candidate: null }});
              }}
            }}
          }} catch (e) {{}}
          return listener(ev);
        }};
        return origAdd(type, wrap, opts);
      }}
      return origAdd(type, listener, opts);
    }};
    return pc;
  }};
  Wrapped.prototype = Orig.prototype;
  window.RTCPeerConnection = Wrapped;
  window.webkitRTCPeerConnection = Wrapped;
}})();
""".strip()


def privacy_launch_args(
    meta: dict[str, Any] | None,
    *,
    has_proxy: bool = False,
    proxy_mode: str | None = None,
) -> list[str]:
    """Build Chromium privacy args.

    Network-first policy:
      - WebRTC hardening always applied (does not break normal HTTPS)
      - When browser uses socks5/mihomo proxy: **do not** force DoH-only.
        DNS must go through the proxy path; secure-DoH bootstrap otherwise
        fails and the whole browser looks "offline".
      - Direct (no proxy): DoH automatic by default (not secure-only).
    """
    meta = meta or {}
    args: list[str] = []
    args += webrtc_chromium_args(str(meta.get("webrtc_mode") or "disable"))

    doh = meta.get("doh")
    mode = str(meta.get("doh_mode") or "automatic").lower()
    force = meta.get("doh_force")
    if force is None:
        force = False  # never imply secure-only

    # Explicit off
    if doh is False or mode in ("off", "none", "false", "disable"):
        return args

    proxied = bool(has_proxy) or str(proxy_mode or meta.get("proxy_mode") or "").lower() in (
        "socks5", "mihomo", "http", "https", "proxy",
    )
    # With proxy: skip browser DoH unless user explicitly demands secure/force_doh_with_proxy
    if proxied and not meta.get("force_doh_with_proxy"):
        if mode in ("secure", "secure-only", "trr-only", "forced"):
            # user asked secure but under proxy it breaks net — demote unless forced
            if not meta.get("doh_secure_with_proxy"):
                return args  # DNS via proxy = correct anti-leak for proxied profiles
        if mode in ("automatic", "auto", ""):
            return args

    servers = meta.get("doh_servers")
    if isinstance(servers, str):
        servers = [x.strip() for x in servers.split() if x.strip()]
    # Direct connection: prefer automatic (has fallback).
    # Legacy profiles have doh_mode=secure from old defaults — that caused total offline.
    # Only keep secure-only when user sets meta.doh_secure_ok=true.
    if mode in ("auto", ""):
        mode = "automatic"
    if mode in ("secure", "secure-only", "trr-only", "forced") and not meta.get("doh_secure_ok"):
        mode = "automatic"
    args += doh_chromium_args(
        meta.get("doh_template") or meta.get("doh_url"),
        mode=mode if mode in ("secure", "automatic") else "automatic",
        servers=list(servers) if servers else None,
        force=bool(force),
    )
    return args


def privacy_init_script(meta: dict[str, Any] | None, proxy_ip: str | None = None) -> str:
    meta = meta or {}
    mode = str(meta.get("webrtc_mode") or "disable")
    return webrtc_init_script(mode, proxy_ip=proxy_ip or meta.get("last_proxy_ip"))
