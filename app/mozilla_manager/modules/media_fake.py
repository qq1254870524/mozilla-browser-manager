"""v7 virtual camera / microphone simulation for WebRTC pages (JS-level)."""
from __future__ import annotations

import json
from typing import Any


def virtual_media_init_script(
    *,
    enable_camera: bool = True,
    enable_mic: bool = True,
    camera_label: str = "Mozilla Virtual Camera",
    mic_label: str = "Mozilla Virtual Microphone",
    color: str = "#1d4ed8",
    tone_hz: float = 440.0,
) -> str:
    """Inject MediaDevices spoof: fake enumerateDevices + getUserMedia streams."""
    cfg = {
        "enable_camera": enable_camera,
        "enable_mic": enable_mic,
        "camera_label": camera_label,
        "mic_label": mic_label,
        "color": color,
        "tone_hz": tone_hz,
    }
    raw = json.dumps(cfg, ensure_ascii=False)
    return f"""
(() => {{
  const CFG = {raw};
  if (!navigator.mediaDevices) return;

  const origEnum = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
  navigator.mediaDevices.enumerateDevices = async function() {{
    let list = [];
    try {{ list = await origEnum(); }} catch (e) {{ list = []; }}
    const extra = [];
    if (CFG.enable_mic) {{
      extra.push({{
        deviceId: 'mozilla-virtual-mic',
        groupId: 'mozilla-virtual-group',
        kind: 'audioinput',
        label: CFG.mic_label,
        toJSON() {{ return this; }},
      }});
    }}
    if (CFG.enable_camera) {{
      extra.push({{
        deviceId: 'mozilla-virtual-cam',
        groupId: 'mozilla-virtual-group',
        kind: 'videoinput',
        label: CFG.camera_label,
        toJSON() {{ return this; }},
      }});
    }}
    // keep outputs if any
    return list.concat(extra);
  }};

  const origGUM = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async function(constraints) {{
    constraints = constraints || {{}};
    const wantAudio = !!(constraints.audio);
    const wantVideo = !!(constraints.video);
    // If real devices work, prefer real — but always ensure virtual fallback
    try {{
      return await origGUM(constraints);
    }} catch (e) {{
      // fall through to virtual
    }}
    const tracks = [];
    if (wantAudio && CFG.enable_mic) {{
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const dst = ctx.createMediaStreamDestination();
      const gain = ctx.createGain();
      gain.gain.value = 0.05;
      osc.frequency.value = CFG.tone_hz || 440;
      osc.connect(gain); gain.connect(dst); osc.start();
      const at = dst.stream.getAudioTracks()[0];
      try {{ Object.defineProperty(at, 'label', {{ get: () => CFG.mic_label }}); }} catch (e) {{}}
      tracks.push(at);
    }}
    if (wantVideo && CFG.enable_camera) {{
      const canvas = document.createElement('canvas');
      canvas.width = 640; canvas.height = 480;
      const c = canvas.getContext('2d');
      let frame = 0;
      const draw = () => {{
        frame++;
        c.fillStyle = CFG.color || '#1d4ed8';
        c.fillRect(0,0,canvas.width,canvas.height);
        c.fillStyle = '#fff';
        c.font = '28px sans-serif';
        c.fillText('Mozilla Virtual Cam', 40, 80);
        c.fillText(new Date().toLocaleTimeString(), 40, 130);
        c.beginPath();
        c.arc(320 + Math.sin(frame/20)*80, 280, 40, 0, Math.PI*2);
        c.fill();
        requestAnimationFrame(draw);
      }};
      draw();
      const stream = canvas.captureStream(15);
      const vt = stream.getVideoTracks()[0];
      try {{ Object.defineProperty(vt, 'label', {{ get: () => CFG.camera_label }}); }} catch (e) {{}}
      tracks.push(vt);
    }}
    if (!tracks.length) throw e || new Error('virtual media unavailable');
    const ms = new MediaStream(tracks);
    return ms;
  }};

  try {{
    Object.defineProperty(window, '__mozilla_virtual_media_v7', {{
      value: CFG, configurable: true,
    }});
  }} catch (e) {{}}
}})();
""".strip()


def apply_virtual_media_to_context(context: Any, meta: dict[str, Any] | None) -> bool:
    meta = meta or {}
    if not meta.get("virtual_media") and not meta.get("virtual_cam") and not meta.get("virtual_mic"):
        # default off unless enabled
        if not meta.get("enable_virtual_media"):
            return False
    enabled = bool(meta.get("enable_virtual_media") or meta.get("virtual_media") or meta.get("virtual_cam") or meta.get("virtual_mic"))
    if not enabled:
        return False
    script = virtual_media_init_script(
        enable_camera=bool(meta.get("virtual_cam", True)),
        enable_mic=bool(meta.get("virtual_mic", True)),
        camera_label=str(meta.get("virtual_cam_label") or "Mozilla Virtual Camera"),
        mic_label=str(meta.get("virtual_mic_label") or "Mozilla Virtual Microphone"),
        color=str(meta.get("virtual_cam_color") or "#1d4ed8"),
    )
    try:
        if context is not None and hasattr(context, "add_init_script"):
            context.add_init_script(script)
            return True
    except Exception:
        return False
    return False


def set_virtual_media(
    profile_id: str,
    *,
    enable: bool = True,
    camera: bool = True,
    mic: bool = True,
    cam_label: str = "",
    mic_label: str = "",
) -> dict[str, Any]:
    from mozilla_manager.store import ProfileStore
    from mozilla_manager import db

    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    meta["enable_virtual_media"] = enable
    meta["virtual_cam"] = camera
    meta["virtual_mic"] = mic
    if cam_label:
        meta["virtual_cam_label"] = cam_label
    if mic_label:
        meta["virtual_mic_label"] = mic_label
    store.update(profile_id, meta=meta)
    db.audit("virtual_media_set", profile_id, {"enable": enable, "camera": camera, "mic": mic})
    return {"ok": True, "profile_id": profile_id, "enable": enable, "camera": camera, "mic": mic}
