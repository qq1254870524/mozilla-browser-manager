"""Build Playwright add_init_script payload from stealth bundle."""
from __future__ import annotations

import json
from typing import Any


def build_stealth_init_script(bundle: dict[str, Any] | None) -> str:
    if not bundle:
        return ""
    dims = bundle.get("dimensions") or {}
    # Pass full dimensions as JSON — script applies hooks.
    payload = {
        "seed": bundle.get("seed"),
        "bundle_id": bundle.get("bundle_id"),
        "dimensions": dims,
        "tls": bundle.get("tls") or {},
    }
    raw = json.dumps(payload, ensure_ascii=False)
    # careful: embed as JSON.parse of string
    return f"""
(() => {{
  const CFG = {raw};
  const D = CFG.dimensions || {{}};
  const N = D.navigator || {{}};
  const S = D.screen || {{}};
  const W = D.webgl || {{}};
  const C = D.canvas || {{}};
  const A = D.audio || {{}};
  const F = D.fonts || {{}};
  const CR = D.client_rects || {{}};
  const AUTO = D.automation || {{}};
  const MD = D.media_devices || {{}};
  const BAT = D.battery || {{}};
  const CONN = D.connection || {{}};
  const CH = D.client_hints || {{}};
  const fonts = F.list || [];

  const redefine = (obj, prop, value) => {{
    try {{
      Object.defineProperty(obj, prop, {{ get: () => value, configurable: true }});
    }} catch (e) {{}}
  }};
  const redefineFn = (obj, prop, fn) => {{
    try {{
      Object.defineProperty(obj, prop, {{ get: fn, configurable: true }});
    }} catch (e) {{}}
  }};

  // -------- navigator core --------
  try {{
    if (N.platform) redefine(Navigator.prototype, 'platform', N.platform);
    if (N.vendor) redefine(Navigator.prototype, 'vendor', N.vendor);
    if (N.user_agent) redefine(Navigator.prototype, 'userAgent', N.user_agent);
    if (N.oscpu) {{ try {{ redefine(Navigator.prototype, 'oscpu', N.oscpu); }} catch (e) {{}} }}
    if (N.hardware_concurrency != null) redefine(Navigator.prototype, 'hardwareConcurrency', N.hardware_concurrency|0);
    if (N.device_memory != null) redefine(Navigator.prototype, 'deviceMemory', N.device_memory);
    if (N.max_touch_points != null) redefine(Navigator.prototype, 'maxTouchPoints', N.max_touch_points|0);
    if (AUTO.languages_override && AUTO.languages_override.length) {{
      redefine(Navigator.prototype, 'language', AUTO.languages_override[0]);
      redefine(Navigator.prototype, 'languages', Object.freeze([...AUTO.languages_override]));
    }}
  }} catch (e) {{}}

  // -------- hide webdriver / automation --------
  try {{
    if (AUTO.hide_webdriver !== false) {{
      try {{ redefine(Navigator.prototype, 'webdriver', false); }} catch (e) {{
        try {{ redefine(Navigator.prototype, 'webdriver', undefined); }} catch (e2) {{}}
      }}
      try {{ delete Navigator.prototype.webdriver; }} catch (e) {{}}
      try {{
        const desc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
        if (!desc || desc.get) redefine(Navigator.prototype, 'webdriver', undefined);
      }} catch (e) {{}}
    }}
  }} catch (e) {{}}

  // chrome.runtime stub noise (headless/automation leak)
  try {{
    if (AUTO.spoof_chrome_runtime !== false) {{
      window.chrome = window.chrome || {{}};
      if (!window.chrome.runtime) {{
        window.chrome.runtime = {{
          id: undefined,
          connect: function() {{ return {{ onMessage: {{ addListener: function(){{}} }}, postMessage: function(){{}} }}; }},
          sendMessage: function() {{}},
        }};
      }}
      // common headless leaks
      try {{ redefine(Navigator.prototype, 'plugins', Navigator.prototype.plugins); }} catch (e) {{}}
    }}
  }} catch (e) {{}}

  // -------- plugins / mimeTypes minimal chrome-like --------
  try {{
    const mkPlugin = (name, filename, desc) => {{
      const p = {{ name, filename, description: desc, length: 1 }};
      p[0] = {{ type: 'application/pdf', suffixes: 'pdf', description: desc, enabledPlugin: p }};
      return p;
    }};
    const pluginsArr = [
      mkPlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      mkPlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      mkPlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
    ];
    if ((AUTO.plugins_profile || '') === 'chrome-pdf-widevine') {{
      pluginsArr.push(mkPlugin('Widevine Content Decryption Module', 'widevinecdmadapter.plugin', 'Enables Widevine licenses for playback of HTML audio/video content.'));
    }}
    const pluginArray = Object.create(PluginArray.prototype);
    pluginsArr.forEach((p, i) => {{ pluginArray[i] = p; }});
    redefine(Navigator.prototype, 'plugins', pluginArray);
    redefine(pluginArray, 'length', pluginsArr.length);
    pluginArray.item = function(i) {{ return this[i] || null; }};
    pluginArray.namedItem = function(n) {{ return pluginsArr.find(x => x.name === n) || null; }};
    pluginArray.refresh = function() {{}};
  }} catch (e) {{}}

  // -------- screen --------
  try {{
    if (S.color_depth != null) {{
      redefine(Screen.prototype, 'colorDepth', S.color_depth|0);
      redefine(Screen.prototype, 'pixelDepth', S.color_depth|0);
    }}
    if (S.width) redefine(Screen.prototype, 'width', S.width|0);
    if (S.height) redefine(Screen.prototype, 'height', S.height|0);
    if (S.width) redefine(Screen.prototype, 'availWidth', S.width|0);
    if (S.height) {{
      const off = (S.avail_offset_y|0) || 0;
      redefine(Screen.prototype, 'availHeight', Math.max(0, (S.height|0) - off));
    }}
    if (S.pixel_ratio) redefine(window, 'devicePixelRatio', S.pixel_ratio);
  }} catch (e) {{}}

  // -------- User-Agent Client Hints --------
  try {{
    if (navigator.userAgentData && CH) {{
      const brands = [
        {{ brand: 'Chromium', version: '131' }},
        {{ brand: 'Google Chrome', version: '131' }},
        {{ brand: 'Not_A Brand', version: '24' }},
      ];
      const uaData = {{
        brands,
        mobile: !!CH.mobile,
        platform: CH.platform || 'Windows',
        getHighEntropyValues: async (hints) => {{
          const out = {{
            architecture: CH.architecture || 'x86',
            bitness: CH.bitness || '64',
            model: CH.model || '',
            platform: CH.platform || 'Windows',
            platformVersion: CH.platformVersion || '15.0.0',
            uaFullVersion: '131.0.6778.86',
            fullVersionList: brands.map(b => ({{ brand: b.brand, version: b.version + '.0.6778.86' }})),
            wow64: false,
          }};
          return out;
        }},
        toJSON: function() {{ return {{ brands, mobile: this.mobile, platform: this.platform }}; }},
      }};
      redefine(Navigator.prototype, 'userAgentData', uaData);
    }}
  }} catch (e) {{}}

  // -------- WebGL vendor/renderer/driver depth --------
  try {{
    const patchGetParameter = (proto) => {{
      if (!proto || !proto.getParameter) return;
      const original = proto.getParameter;
      proto.getParameter = function(param) {{
        const UNMASKED_VENDOR_WEBGL = 0x9245;
        const UNMASKED_RENDERER_WEBGL = 0x9246;
        const MAX_TEXTURE_SIZE = 0x0D33;
        const MAX_RENDERBUFFER_SIZE = 0x84E8;
        const ALIASED_LINE_WIDTH_RANGE = 0x846E;
        const ALIASED_POINT_SIZE_RANGE = 0x846D;
        if (param === UNMASKED_VENDOR_WEBGL) return W.unmasked_vendor || W.vendor;
        if (param === UNMASKED_RENDERER_WEBGL) return W.unmasked_renderer || W.renderer;
        if (param === MAX_TEXTURE_SIZE && W.max_texture_size) return W.max_texture_size;
        if (param === MAX_RENDERBUFFER_SIZE && W.max_renderbuffer_size) return W.max_renderbuffer_size;
        if (param === ALIASED_LINE_WIDTH_RANGE && W.aliased_line_width_range)
          return new Float32Array(W.aliased_line_width_range);
        if (param === ALIASED_POINT_SIZE_RANGE && W.aliased_point_size_range)
          return new Float32Array(W.aliased_point_size_range);
        return original.apply(this, arguments);
      }};
    }};
    if (typeof WebGLRenderingContext !== 'undefined') patchGetParameter(WebGLRenderingContext.prototype);
    if (typeof WebGL2RenderingContext !== 'undefined') patchGetParameter(WebGL2RenderingContext.prototype);
  }} catch (e) {{}}

  // -------- Canvas noise (profile-fixed) --------
  try {{
    const seed = (C.seed|0) || 1;
    const rB = C.r_bias || 0, gB = C.g_bias || 0, bB = C.b_bias || 0;
    const noisePx = (img) => {{
      try {{
        const data = img.data;
        for (let i = 0; i < data.length; i += 4) {{
          // deterministic tiny noise from seed + index
          const t = ((seed ^ i) * 2654435761) >>> 0;
          const n = ((t & 255) / 255 - 0.5);
          data[i] = Math.max(0, Math.min(255, data[i] + rB + n));
          data[i+1] = Math.max(0, Math.min(255, data[i+1] + gB + n * 0.7));
          data[i+2] = Math.max(0, Math.min(255, data[i+2] + bB + n * 0.5));
        }}
      }} catch (e) {{}}
      return img;
    }};
    const hook = (proto, name) => {{
      if (!proto || !proto[name]) return;
      const orig = proto[name];
      proto[name] = function() {{
        if (name === 'getImageData') {{
          const img = orig.apply(this, arguments);
          return noisePx(img);
        }}
        // toDataURL / toBlob: shift one pixel style via getImageData path
        try {{
          const ctx = this;
          if (ctx && ctx.getImageData && ctx.putImageData && ctx.canvas) {{
            const w = ctx.canvas.width|0, h = ctx.canvas.height|0;
            if (w > 0 && h > 0 && w * h < 8000 * 8000) {{
              const img = ctx.getImageData(0, 0, Math.min(w, 64), Math.min(h, 64));
              noisePx(img);
              ctx.putImageData(img, 0, 0);
            }}
          }}
        }} catch (e) {{}}
        return orig.apply(this, arguments);
      }};
    }};
    if (typeof CanvasRenderingContext2D !== 'undefined') {{
      hook(CanvasRenderingContext2D.prototype, 'getImageData');
      const cproto = HTMLCanvasElement && HTMLCanvasElement.prototype;
      if (cproto) {{
        hook(cproto, 'toDataURL');
        hook(cproto, 'toBlob');
      }}
    }}
  }} catch (e) {{}}

  // -------- AudioContext noise / device persona --------
  try {{
    const scale = A.noise_scale || 0.0001;
    const offBin = A.offset_bin || 1;
    const wrap = (Orig) => {{
      if (!Orig) return Orig;
      const Wrapped = function(...args) {{
        const ctx = new Orig(...args);
        try {{
          const orCreate = ctx.createAnalyser.bind(ctx);
          ctx.createAnalyser = function() {{
            const node = orCreate();
            return node;
          }};
          const orBuf = ctx.createBuffer.bind(ctx);
          ctx.createBuffer = function(ch, len, rate) {{
            const buf = orBuf(ch, len, rate);
            try {{
              for (let c = 0; c < buf.numberOfChannels; c++) {{
                const data = buf.getChannelData(c);
                for (let i = 0; i < data.length; i++) {{
                  const t = ((offBin * 131 + i + c * 17) * 2654435761) >>> 0;
                  data[i] = data[i] + (((t & 1023) / 1023) - 0.5) * scale;
                }}
              }}
            }} catch (e) {{}}
            return buf;
          }};
          try {{
            redefine(AudioContext.prototype, 'baseLatency', A.base_latency || ctx.baseLatency);
            redefine(OfflineAudioContext.prototype, 'baseLatency', A.base_latency || 0.01);
          }} catch (e) {{}}
          try {{
            if (A.sample_rate) redefineFn(Object.getPrototypeOf(ctx), 'sampleRate', () => A.sample_rate);
          }} catch (e) {{}}
        }} catch (e) {{}}
        return ctx;
      }};
      Wrapped.prototype = Orig.prototype;
      try {{ Object.defineProperty(Wrapped, 'name', {{ value: Orig.name }}); }} catch (e) {{}}
      return Wrapped;
    }};
    if (typeof AudioContext !== 'undefined') {{
      window.AudioContext = wrap(window.AudioContext);
    }}
    if (typeof OfflineAudioContext !== 'undefined') {{
      const OrigO = window.OfflineAudioContext;
      window.OfflineAudioContext = function(ch, len, rate) {{
        const ctx = new OrigO(ch, len, rate);
        try {{
          const orStart = ctx.startRendering.bind(ctx);
          ctx.startRendering = function() {{
            return orStart().then((buf) => {{
              try {{
                for (let c = 0; c < buf.numberOfChannels; c++) {{
                  const data = buf.getChannelData(c);
                  for (let i = 0; i < Math.min(data.length, 256); i++) {{
                    const t = ((offBin * 31 + i) * 2654435761) >>> 0;
                    data[i] = data[i] + (((t & 255) / 255) - 0.5) * scale * 2;
                  }}
                }}
              }} catch (e) {{}}
              return buf;
            }});
          }};
        }} catch (e) {{}}
        return ctx;
      }};
      window.OfflineAudioContext.prototype = OrigO.prototype;
    }}
  }} catch (e) {{}}

  // -------- fonts.check soft hint --------
  try {{
    if (document.fonts && document.fonts.check && fonts.length) {{
      const orig = document.fonts.check.bind(document.fonts);
      document.fonts.check = function(font, text) {{
        try {{
          const family = String(font || '').replace(/["']/g, '');
          for (const f of fonts) {{
            if (family.includes(f)) return true;
          }}
        }} catch (e) {{}}
        return orig(font, text);
      }};
    }}
  }} catch (e) {{}}

  // -------- client rects micro-noise --------
  try {{
    const nx = CR.noise_x || 0, ny = CR.noise_y || 0;
    if (nx || ny) {{
      const hookRect = (proto, name) => {{
        if (!proto || !proto[name]) return;
        const orig = proto[name];
        proto[name] = function() {{
          const r = orig.apply(this, arguments);
          try {{
            const mod = (v, n) => v + n;
            if (r && typeof r.x === 'number') {{
              return DOMRect.fromRect({{
                x: mod(r.x, nx), y: mod(r.y, ny),
                width: r.width, height: r.height
              }});
            }}
          }} catch (e) {{}}
          return r;
        }};
      }};
      hookRect(Element.prototype, 'getBoundingClientRect');
    }}
  }} catch (e) {{}}

  // -------- mediaDevices labels (enumerate) --------
  try {{
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
      const orig = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
      navigator.mediaDevices.enumerateDevices = async function() {{
        const list = await orig();
        try {{
          return list.map((d, i) => {{
            const copy = {{
              deviceId: d.deviceId,
              groupId: d.groupId,
              kind: d.kind,
              label: d.label,
              toJSON: function() {{ return this; }},
            }};
            if (!copy.label) {{
              if (copy.kind === 'audiooutput') copy.label = MD.speaker_label || 'Speakers';
              if (copy.kind === 'audioinput') copy.label = MD.mic_label || 'Microphone';
              if (copy.kind === 'videoinput') copy.label = MD.cam_label || 'Camera';
            }}
            return copy;
          }});
        }} catch (e) {{ return list; }}
      }};
    }}
  }} catch (e) {{}}

  // -------- battery --------
  try {{
    if (navigator.getBattery) {{
      navigator.getBattery = async function() {{
        return {{
          charging: !!BAT.charging,
          chargingTime: BAT.charging_time == null ? Infinity : BAT.charging_time,
          dischargingTime: BAT.discharging_time == null ? Infinity : BAT.discharging_time,
          level: BAT.level == null ? 0.82 : BAT.level,
          addEventListener: function() {{}},
          removeEventListener: function() {{}},
          onchargingchange: null,
          onlevelchange: null,
        }};
      }};
    }}
  }} catch (e) {{}}

  // -------- network information --------
  try {{
    if (navigator.connection || navigator.mozConnection || navigator.webkitConnection) {{
      const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (c && CONN) {{
        try {{ redefine(c, 'effectiveType', CONN.effectiveType || c.effectiveType); }} catch (e) {{}}
        try {{ redefine(c, 'rtt', CONN.rtt || c.rtt); }} catch (e) {{}}
        try {{ redefine(c, 'downlink', CONN.downlink || c.downlink); }} catch (e) {{}}
        try {{ redefine(c, 'saveData', !!CONN.saveData); }} catch (e) {{}}
      }}
    }}
  }} catch (e) {{}}

  // expose debug marker (non-enumerable)
  try {{
    Object.defineProperty(window, '__mozilla_stealth_v6', {{
      value: {{ bundle_id: CFG.bundle_id, tls: (CFG.tls||{{}}).id, dims: Object.keys(D).length }},
      configurable: true,
    }});
  }} catch (e) {{}}
}})();
""".strip()
