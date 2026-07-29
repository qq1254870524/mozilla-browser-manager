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
    mode: str = "secure",
    *,
    servers: list[str] | None = None,
    force: bool = True,
) -> list[str]:
    """Force DNS-over-HTTPS templates (Chromium). Supports multi-template list."""
    mode_l = (mode or "secure").lower()
    if mode_l in ("off", "none", ""):
        return []
    # v6 default: force secure DoH
    if force and mode_l not in ("secure", "automatic"):
        mode_l = "secure"
    tmpls: list[str] = []
    if doh_template:
        tmpls.append(str(doh_template).strip())
    for s in servers or []:
        s = str(s).strip()
        if s and s not in tmpls:
            tmpls.append(s)
    if not tmpls:
        tmpls = list(DEFAULT_DOH_SERVERS[:1])
    # Chromium accepts space-separated templates
    joined = " ".join(tmpls)
    args = [
        f"--dns-over-https-mode={mode_l}",
        f"--dns-over-https-templates={joined}",
    ]
    # Additional hardening: prefer DoH, disable insecure DNS fallback where possible
    if force:
        args += [
            "--disable-features=DnsOverHttpsUpgrade",  # keep explicit templates
        ]
    return args


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


def privacy_launch_args(meta: dict[str, Any] | None) -> list[str]:
    """Build Chromium args from profile.meta privacy + v6 DoH force."""
    meta = meta or {}
    args: list[str] = []
    args += webrtc_chromium_args(str(meta.get("webrtc_mode") or "disable"))
    doh = meta.get("doh")
    # v6: force DoH unless explicitly off
    force = meta.get("doh_force")
    if force is None:
        force = True
    if doh is False or str(meta.get("doh_mode") or "").lower() in ("off", "none"):
        return args
    servers = meta.get("doh_servers")
    if isinstance(servers, str):
        servers = [x.strip() for x in servers.split() if x.strip()]
    args += doh_chromium_args(
        meta.get("doh_template") or meta.get("doh_url"),
        mode=str(meta.get("doh_mode") or "secure"),
        servers=list(servers) if servers else None,
        force=bool(force),
    )
    return args


def privacy_init_script(meta: dict[str, Any] | None, proxy_ip: str | None = None) -> str:
    meta = meta or {}
    mode = str(meta.get("webrtc_mode") or "disable")
    return webrtc_init_script(mode, proxy_ip=proxy_ip or meta.get("last_proxy_ip"))
