from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .env_packs import detect_egress_country
from .models import Profile
from .paths import ROOT, ensure_layout, safe_resolve
from .store import ProfileStore


def _proxy_url(profile: Profile) -> str | None:
    px = profile.proxy
    if px.mode == "socks5" and px.socks5:
        return px.socks5 if "://" in px.socks5 else f"socks5://{px.socks5}"
    if px.mode == "mihomo" and px.mihomo_port:
        return f"socks5://127.0.0.1:{px.mihomo_port}"
    return None


def preflight(profile: Profile, *, require_proxy: bool = False) -> dict[str, Any]:
    """Network/env preflight before launching browser."""
    ensure_layout()
    store = ProfileStore()
    report: dict[str, Any] = {
        "profile_id": profile.id,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ok": True,
        "blocks": [],
        "warnings": [],
        "egress": None,
        "env": profile.env.model_dump(mode="json"),
        "proxy": profile.proxy.model_dump(mode="json"),
    }

    # user_data path sandbox
    try:
        store.abs_user_data(profile)
    except Exception as e:
        report["ok"] = False
        report["blocks"].append(f"user_data_dir invalid: {e}")

    if require_proxy and profile.proxy.mode == "none":
        report["ok"] = False
        report["blocks"].append("proxy required but mode=none")

    proxy = _proxy_url(profile)
    if profile.proxy.mode in ("socks5", "mihomo"):
        if not proxy:
            report["ok"] = False
            report["blocks"].append("proxy mode set but endpoint missing")
        else:
            try:
                info = detect_egress_country(proxy, timeout=12.0)
                report["egress"] = {
                    k: info.get(k) for k in ("ip", "country", "city", "region", "timezone", "latitude", "longitude", "provider", "enriched_by")
                }
                # soft mismatch warning
                cc = (info.get("country") or "").upper()
                # if timezone hard-coded differently, warn only
                if info.get("timezone") and profile.env.timezone_id:
                    if str(info["timezone"]) != profile.env.timezone_id:
                        report["warnings"].append(
                            f"tz mismatch: egress={info['timezone']} profile={profile.env.timezone_id}"
                        )
                if cc and profile.meta.get("expected_country"):
                    if cc != str(profile.meta["expected_country"]).upper():
                        report["warnings"].append(
                            f"country mismatch: egress={cc} expected={profile.meta['expected_country']}"
                        )
                # v6: geo consistency vs timezone/locale (hard if meta.geo_match_strict)
                try:
                    from mozilla_manager.network.net_quality import geo_consistency
                    geo = geo_consistency(
                        egress=info,
                        timezone_id=profile.env.timezone_id,
                        locale=profile.env.locale,
                        expected_country=(profile.meta or {}).get("expected_country"),
                        languages=list(profile.env.languages or []),
                    )
                    report["geo_consistency"] = geo
                    strict = bool((profile.meta or {}).get("geo_match_strict") or (profile.meta or {}).get("require_geo_match"))
                    if not geo.get("ok"):
                        msg = "geo consistency fail: " + "; ".join(geo.get("issues") or [])
                        if strict:
                            report["ok"] = False
                            report["blocks"].append(msg)
                        else:
                            report["warnings"].append(msg)
                except Exception as ge:
                    report["warnings"].append(f"geo consistency error: {ge}")
            except Exception as e:
                msg = f"proxy egress check failed: {e}"
                if require_proxy:
                    report["ok"] = False
                    report["blocks"].append(msg)
                else:
                    report["warnings"].append(msg + " (use --require-proxy to hard-fail; or mihomo-start first)")

    # v6: always materialize stealth bundle at preflight
    try:
        from mozilla_manager.stealth import ensure_stealth_bundle, summarize_bundle
        b = ensure_stealth_bundle(profile)
        report["stealth"] = summarize_bundle(b)
    except Exception as se:
        report["warnings"].append(f"stealth bundle: {se}")

    # persist last_check
    try:
        path = safe_resolve(ROOT / profile.user_data_dir / "last_check.json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report


CHECK_PAGE_HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Mozilla 一键检测</title>
<style>
:root{--ok:#047857;--bad:#b91c1c;--warn:#b45309;--line:#e5e7eb;--muted:#64748b;--bg:#f8fafc}
*{box-sizing:border-box}
body{font-family:ui-sans-serif,system-ui,"PingFang SC","Microsoft YaHei",sans-serif;max-width:1100px;margin:20px auto;padding:0 14px 40px;background:var(--bg);color:#0f172a}
h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--muted);margin-bottom:14px;font-size:13px;line-height:1.5}
.grid{display:grid;grid-template-columns:1.1fr 1fr;gap:12px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.card h3{margin:0 0 10px;font-size:14px}
.row{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px dashed #eef2f7;font-size:13px}
.row:last-child{border-bottom:0}
.k{color:var(--muted);flex-shrink:0}
.v{font-weight:600;text-align:right;word-break:break-all}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700}
.ok{background:#ecfdf5;color:var(--ok)}
.bad{background:#fef2f2;color:var(--bad)}
.warn{background:#fffbeb;color:var(--warn)}
.muted{background:#f1f5f9;color:#475569}
#status{margin:8px 0 14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 12px;cursor:pointer;font-size:12px}
button.primary{background:#1d4ed8;color:#fff;border-color:#1d4ed8}
.score-wrap{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.score-ring{width:96px;height:96px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:conic-gradient(#94a3b8 0deg, #e2e8f0 0deg);position:relative;flex-shrink:0}
.score-ring > span{width:72px;height:72px;border-radius:50%;background:#0f172a;color:#fff;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800;box-shadow:inset 0 0 0 2px rgba(255,255,255,.08)}
.score-meta{flex:1;min-width:180px}
.bar{height:8px;background:#e2e8f0;border-radius:99px;overflow:hidden;margin:6px 0 10px}
.bar>i{display:block;height:100%;background:#3b82f6;width:0%;transition:width .25s}
.list{font-size:12px;line-height:1.6;color:#334155;max-height:220px;overflow:auto}
.list .ok{color:var(--ok)} .list .bad{color:var(--bad)} .list .warn{color:var(--warn)}
pre{background:#f1f5f9;padding:10px;border-radius:8px;overflow:auto;font-size:11px;margin:0;max-height:220px}
.hint{color:var(--muted);font-size:12px;margin-top:8px;line-height:1.45}
.subscore{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
.subscore .pill{font-weight:600}
</style></head><body>
<h1>Mozilla 一键检测页</h1>
<div class="sub">出口 IP / 城市时区 / 语言地理 / <b>健康度·伪装评分</b> · 本地可离线打基础分 · 网络项走当前浏览器代理</div>
<div id="status">
  <span class="pill muted" id="stPill">初始化…</span>
  <button class="primary" id="btnReIP">重新探测 IP</button>
  <button id="btnRescore">重算评分</button>
  <button id="btnCopy">复制报告</button>
</div>
<div class="grid">
  <div class="card">
    <h3>健康度 / 伪装评分</h3>
    <div class="score-wrap">
      <div class="score-ring" id="scoreRing"><span id="scoreNum">--</span></div>
      <div class="score-meta">
        <div class="row"><span class="k">综合得分</span><span class="v" id="scoreTotal">—</span></div>
        <div class="row"><span class="k">等级</span><span class="v" id="scoreGrade">—</span></div>
        <div class="row"><span class="k">自动化痕迹</span><span class="v" id="scoreAuto">—</span></div>
        <div class="row"><span class="k">IP 环境分</span><span class="v" id="scoreIP">—</span></div>
        <div class="bar"><i id="scoreBar"></i></div>
        <div class="subscore" id="scorePills"></div>
        <div class="hint">评分 = 自动化伪装 + 时区/语言一致 + 出口国家/城市/时区匹配。无外网时仍给出基础伪装分。</div>
      </div>
    </div>
    <div class="list" id="scoreDetail"></div>
  </div>
  <div class="card">
    <h3>出口 IP</h3>
    <div class="row"><span class="k">IP</span><span class="v" id="ip">…</span></div>
    <div class="row"><span class="k">国家</span><span class="v" id="country">…</span></div>
    <div class="row"><span class="k">城市</span><span class="v" id="city">…</span></div>
    <div class="row"><span class="k">地区</span><span class="v" id="region">…</span></div>
    <div class="row"><span class="k">网络时区</span><span class="v" id="net_tz">…</span></div>
    <div class="row"><span class="k">经纬度</span><span class="v" id="net_ll">…</span></div>
    <div class="row"><span class="k">探测源</span><span class="v" id="ip_src">…</span></div>
    <div class="hint" id="ip_err"></div>
  </div>
  <div class="card">
    <h3>浏览器环境（实际）</h3>
    <div class="row"><span class="k">时区</span><span class="v" id="tz">…</span></div>
    <div class="row"><span class="k">语言</span><span class="v" id="lang">…</span></div>
    <div class="row"><span class="k">languages</span><span class="v" id="langs">…</span></div>
    <div class="row"><span class="k">平台</span><span class="v" id="platform">…</span></div>
    <div class="row"><span class="k">UA</span><span class="v" id="ua">…</span></div>
    <div class="row"><span class="k">webdriver</span><span class="v" id="wd">…</span></div>
    <div class="row"><span class="k">hw / mem</span><span class="v" id="hw">…</span></div>
    <div class="row"><span class="k">屏幕</span><span class="v" id="screen">…</span></div>
  </div>
  <div class="card">
    <h3>配置期望 vs 实际</h3>
    <div class="row"><span class="k">期望时区</span><span class="v" id="exp_tz">…</span></div>
    <div class="row"><span class="k">期望语言</span><span class="v" id="exp_lang">…</span></div>
    <div class="row"><span class="k">期望国家</span><span class="v" id="exp_cc">…</span></div>
    <div class="row"><span class="k">代理</span><span class="v" id="proxy">…</span></div>
    <div class="row"><span class="k">节点</span><span class="v" id="node">…</span></div>
    <div class="row"><span class="k">纬度</span><span class="v" id="lat">…</span></div>
    <div class="row"><span class="k">经度</span><span class="v" id="lon">…</span></div>
    <div id="diff" class="list" style="margin-top:8px"></div>
  </div>
  <div class="card" style="grid-column:1/-1">
    <h3>原始 Profile 摘要</h3>
    <pre id="raw">{}</pre>
  </div>
</div>
<script>
const PROFILE = __PROFILE_JSON__;
const $ = (id) => document.getElementById(id);
const set = (id, v) => { const el = $(id); if (el) el.textContent = (v == null || v === '') ? '—' : String(v); };
const pill = (el, cls, text) => { if (!el) return; el.className = 'pill ' + cls; el.textContent = text; };
const safe = (fn, fb) => { try { return fn(); } catch (e) { return fb; } };

function proxyText(p) {
  if (!p || p.mode === 'none') return '直连';
  if (p.mode === 'socks5') return p.socks5 || 'socks5';
  return 'mihomo:' + (p.mihomo_port || '-') + (p.node_name ? ' / ' + p.node_name : '');
}

function collectLocal() {
  const tz = safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone, '—');
  const lang = navigator.language || '';
  const langs = [...(navigator.languages || [])].join(', ');
  const wd = navigator.webdriver;
  const ua = navigator.userAgent || '';
  const platform = navigator.platform || (navigator.userAgentData && navigator.userAgentData.platform) || '';
  const hw = (navigator.hardwareConcurrency || '?') + ' / ' + (navigator.deviceMemory || '?') + 'GB';
  const screen = (window.screen && window.screen.width || '?') + 'x' + (window.screen && window.screen.height || '?') + ' @' + (window.devicePixelRatio || 1);
  const hasChrome = typeof window.chrome !== 'undefined';
  const plugins = navigator.plugins ? navigator.plugins.length : 0;
  const languagesOk = (navigator.languages || []).length > 0;
  set('tz', tz); set('lang', lang); set('langs', langs); set('platform', platform);
  set('ua', ua); set('wd', String(wd)); set('hw', hw); set('screen', screen);
  return {
    tz, lang, langs, platform, ua, webdriver: wd, hw, screen, hasChrome, plugins, languagesOk,
    maxTouch: navigator.maxTouchPoints || 0,
    vendor: navigator.vendor || '',
    pdfViewer: navigator.pdfViewerEnabled,
  };
}

function expected() {
  const env = (PROFILE && PROFILE.env) || {};
  const meta = (PROFILE && PROFILE.meta) || {};
  const proxy = (PROFILE && PROFILE.proxy) || {};
  set('exp_tz', env.timezone_id || '—');
  set('exp_lang', env.locale || '—');
  set('exp_cc', meta.expected_country || '—');
  set('proxy', proxyText(proxy));
  set('node', proxy.node_name || meta.bound_node || '—');
  const g = env.geolocation || {};
  set('lat', g.latitude); set('lon', g.longitude);
  return { env, meta, proxy };
}

function fillIP(info) {
  if (!info) {
    set('ip', '—'); set('country', '—'); set('city', '—'); set('region', '—');
    set('net_tz', '—'); set('net_ll', '—'); set('ip_src', '—');
    return;
  }
  set('ip', info.ip);
  set('country', info.country || '—');
  set('city', info.city || '—');
  set('region', info.region || '—');
  set('net_tz', info.timezone || '—');
  const ll = (info.latitude != null && info.longitude != null)
    ? (Number(info.latitude).toFixed(4) + ', ' + Number(info.longitude).toFixed(4))
    : '—';
  set('net_ll', ll);
  set('ip_src', info.src || info.provider || '—');
}

function scoreAll(local, ipinfo) {
  try {
    const exp = expected();
    const items = [];
    let score = 100;
    let ipScore = 100;
    const add = (ok, w, title, detail, bucket) => {
      if (ok === true) items.push({lvl:'ok', title, detail});
      else if (ok === 'warn') {
        score -= w; if (bucket === 'ip') ipScore -= w;
        items.push({lvl:'warn', title, detail});
      } else {
        score -= w; if (bucket === 'ip') ipScore -= w;
        items.push({lvl:'bad', title, detail});
      }
    };

    if (!local) local = {};
    if (local.webdriver) add(false, 25, 'navigator.webdriver = true', '强自动化特征');
    else add(true, 0, 'webdriver 未暴露', '通过');
    if (/HeadlessChrome/i.test(local.ua || '')) add(false, 20, 'UA 含 HeadlessChrome', local.ua);
    else add(true, 0, 'UA 非 headless', '通过');
    if (!local.hasChrome && /Chrome\//.test(local.ua || '')) add('warn', 8, 'window.chrome 缺失', 'Chromium 伪装不完整');
    else add(true, 0, 'chrome 对象', local.hasChrome ? '存在' : 'N/A');
    if (!local.plugins && /Windows|Mac|Linux/.test(local.platform || '')) add('warn', 5, 'plugins 为空', '可能像自动化');
    else add(true, 0, 'plugins', String(local.plugins));
    if (!local.languagesOk) add(false, 6, 'languages 空', ''); else add(true, 0, 'languages', local.langs);

    const etz = exp.env.timezone_id;
    if (etz && local.tz && etz !== local.tz) add(false, 12, '时区不匹配', etz + ' → ' + local.tz);
    else if (etz) add(true, 0, '时区匹配', local.tz);
    const eloc = exp.env.locale;
    if (eloc && local.lang && !(local.lang === eloc || local.lang.startsWith(String(eloc).split('-')[0])))
      add('warn', 8, '语言不完全匹配', eloc + ' → ' + local.lang);
    else if (eloc) add(true, 0, '语言匹配', local.lang);

    const ecc = String((exp.meta.expected_country || '')).toUpperCase();
    const icc = String((ipinfo && (ipinfo.country || '') || '')).toUpperCase().slice(0, 2);
    if (ipinfo && ipinfo.ip) {
      add(true, 0, '出口 IP 可达', ipinfo.ip + (icc ? ' · ' + icc : ''), 'ip');
      if (ipinfo.city) add(true, 0, '出口城市', ipinfo.city + (ipinfo.region ? ' / ' + ipinfo.region : ''), 'ip');
      else add('warn', 4, '出口城市缺失', '探测源未返回 city', 'ip');
      if (ipinfo.timezone) add(true, 0, '出口网络时区', ipinfo.timezone, 'ip');
      else add('warn', 4, '出口网络时区缺失', '探测源未返回 timezone', 'ip');
      if (ecc && icc && ecc !== icc) add(false, 15, '出口国家 ≠ 期望', ecc + ' → ' + icc, 'ip');
      else if (ecc && icc) add(true, 0, '出口国家匹配', icc, 'ip');
      if (ipinfo.timezone && etz && ipinfo.timezone !== etz)
        add('warn', 6, '网络时区 ≠ 浏览器时区', ipinfo.timezone + ' / ' + local.tz, 'ip');
      else if (ipinfo.timezone && local.tz && ipinfo.timezone === local.tz)
        add(true, 0, '网络时区 = 浏览器时区', local.tz, 'ip');
    } else {
      add('warn', 10, '出口 IP 未探测到', '可能代理未通或纯离线', 'ip');
    }

    if (exp.proxy.mode === 'mihomo' || exp.proxy.mode === 'socks5') {
      if (!ipinfo || !ipinfo.ip) add('warn', 8, '已配置代理但无出口 IP', proxyText(exp.proxy), 'ip');
      else add(true, 0, '代理模式', proxyText(exp.proxy));
    }
    if (exp.meta.auto_cf || exp.meta.pass_cf) add(true, 0, 'CF 过盾待命', 'auto_cf 已开启');

    score = Math.max(0, Math.min(100, Math.round(score)));
    ipScore = Math.max(0, Math.min(100, Math.round(ipScore)));
    let grade = '差', cls = 'bad', color = '#ef4444';
    if (score >= 85) { grade = '优'; cls = 'ok'; color = '#10b981'; }
    else if (score >= 70) { grade = '良'; cls = 'ok'; color = '#34d399'; }
    else if (score >= 50) { grade = '中'; cls = 'warn'; color = '#f59e0b'; }

    set('scoreTotal', score + ' / 100');
    set('scoreGrade', grade);
    set('scoreAuto', local.webdriver ? '高风险' : '低');
    set('scoreIP', ipScore + ' / 100');
    const bar = $('scoreBar');
    if (bar) { bar.style.width = score + '%'; bar.style.background = color; }
    const ring = $('scoreRing');
    if (ring) ring.style.background = 'conic-gradient(' + color + ' ' + (score * 3.6) + 'deg, #e2e8f0 0deg)';
    const num = $('scoreNum');
    if (num) num.textContent = String(score);
    const pills = $('scorePills');
    if (pills) {
      pills.innerHTML =
        '<span class="pill ' + cls + '">综合 ' + score + '</span>' +
        '<span class="pill muted">IP环境 ' + ipScore + '</span>' +
        '<span class="pill ' + (local.webdriver ? 'bad' : 'ok') + '">自动化 ' + (local.webdriver ? '高' : '低') + '</span>' +
        (ipinfo && ipinfo.city ? '<span class="pill ok">城市 ' + ipinfo.city + '</span>' : '<span class="pill warn">城市缺失</span>') +
        (ipinfo && ipinfo.timezone ? '<span class="pill ok">时区 ' + ipinfo.timezone + '</span>' : '<span class="pill warn">时区缺失</span>');
    }
    const detail = $('scoreDetail');
    if (detail) {
      detail.innerHTML = items.map(it =>
        '<div class="' + it.lvl + '">• <b>' + it.title + '</b> — ' + (it.detail || '') + '</div>'
      ).join('');
    }
    pill($('stPill'), cls, '评分 ' + score + ' · ' + grade + (ipinfo && ipinfo.city ? ' · ' + ipinfo.city : ''));
    window.__SCORE__ = { score, grade, ipScore, items, local, ipinfo };
    return window.__SCORE__;
  } catch (e) {
    pill($('stPill'), 'bad', '评分脚本错误');
    set('scoreTotal', '错误');
    set('scoreNum', '!');
    $('scoreDetail') && ($('scoreDetail').textContent = String(e && e.message || e));
    console.error(e);
    return null;
  }
}

async function tryFetch(url, ms) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms || 8000);
  try {
    const r = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
    const text = await r.text();
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return { ok: true, text, status: r.status };
  } finally {
    clearTimeout(t);
  }
}

function parseMaybeJson(text) {
  try { return JSON.parse(text); } catch { return null; }
}

async function probeIP() {
  set('ip', '…'); set('country', '…'); set('city', '…'); set('region', '…');
  set('net_tz', '…'); set('net_ll', '…'); set('ip_src', '…');
  $('ip_err').textContent = '';
  let info = null;
  const errors = [];

  const sources = [
    {
      name: 'ip.sb',
      run: async () => {
        const j = parseMaybeJson((await tryFetch('https://api.ip.sb/geoip', 8000)).text);
        if (!j || !j.ip) throw new Error('empty');
        return { ip: j.ip, country: j.country_code || j.country, city: j.city, region: j.region, timezone: j.timezone, latitude: j.latitude, longitude: j.longitude, src: 'ip.sb' };
      }
    },
    {
      name: 'ipwho.is',
      run: async () => {
        const j = parseMaybeJson((await tryFetch('https://ipwho.is/', 8000)).text);
        if (!j || j.success === false) throw new Error((j && j.message) || 'fail');
        const tz = (j.timezone && j.timezone.id) ? j.timezone.id : j.timezone;
        return { ip: j.ip, country: j.country_code || j.country, city: j.city, region: j.region, timezone: tz, latitude: j.latitude, longitude: j.longitude, src: 'ipwho.is' };
      }
    },
    {
      name: 'ip-api',
      run: async () => {
        const j = parseMaybeJson((await tryFetch('http://ip-api.com/json/?fields=status,message,country,countryCode,regionName,city,lat,lon,timezone,query', 8000)).text);
        if (!j || j.status !== 'success') throw new Error((j && j.message) || 'fail');
        return { ip: j.query, country: j.countryCode || j.country, city: j.city, region: j.regionName, timezone: j.timezone, latitude: j.lat, longitude: j.lon, src: 'ip-api' };
      }
    },
    {
      name: 'ipinfo',
      run: async () => {
        const j = parseMaybeJson((await tryFetch('https://ipinfo.io/json', 8000)).text);
        if (!j || j.error || j.status === 429) throw new Error((j && j.error && (j.error.message || j.error.title)) || 'rate');
        const loc = String(j.loc || ',').split(',');
        return { ip: j.ip, country: j.country, city: j.city, region: j.region, timezone: j.timezone, latitude: loc[0] ? Number(loc[0]) : null, longitude: loc[1] ? Number(loc[1]) : null, src: 'ipinfo.io' };
      }
    },
    {
      name: 'ipify+cf',
      run: async () => {
        const ip = (await tryFetch('https://api.ipify.org', 6000)).text.trim();
        const tr = (await tryFetch('https://cloudflare.com/cdn-cgi/trace', 6000)).text;
        const meta = {};
        tr.split(String.fromCharCode(10)).forEach(line => { const i = line.indexOf('='); if (i > 0) meta[line.slice(0,i)] = line.slice(i+1); });
        // note: real newlines in page; fix below outside raw carefully
        return { ip: ip || meta.ip, country: meta.loc, city: null, region: null, timezone: null, src: 'ipify+cf' };
      }
    }
  ];

  for (const s of sources) {
    try {
      info = await s.run();
      if (info && info.ip) break;
    } catch (e) {
      errors.push(s.name + ':' + (e && e.message || e));
    }
  }

  // enrich city/tz if thin result
  if (info && info.ip && (!info.city || !info.timezone)) {
    const enrichers = [
      async () => {
        const j = parseMaybeJson((await tryFetch('http://ip-api.com/json/' + encodeURIComponent(info.ip) + '?fields=status,message,country,countryCode,regionName,city,lat,lon,timezone,query', 7000)).text);
        if (!j || j.status !== 'success') throw new Error('fail');
        return { city: j.city, region: j.regionName, timezone: j.timezone, country: j.countryCode || j.country, latitude: j.lat, longitude: j.lon, src_extra: 'ip-api' };
      },
      async () => {
        const j = parseMaybeJson((await tryFetch('https://ipwho.is/' + encodeURIComponent(info.ip), 7000)).text);
        if (!j || j.success === false) throw new Error('fail');
        const tz = (j.timezone && j.timezone.id) ? j.timezone.id : j.timezone;
        return { city: j.city, region: j.region, timezone: tz, country: j.country_code || j.country, latitude: j.latitude, longitude: j.longitude, src_extra: 'ipwho' };
      },
      async () => {
        const j = parseMaybeJson((await tryFetch('https://api.ip.sb/geoip/' + encodeURIComponent(info.ip), 7000)).text);
        if (!j) throw new Error('fail');
        return { city: j.city, region: j.region, timezone: j.timezone, country: j.country_code || j.country, latitude: j.latitude, longitude: j.longitude, src_extra: 'ip.sb' };
      }
    ];
    for (const en of enrichers) {
      try {
        const extra = await en();
        info = Object.assign({}, info, {
          city: info.city || extra.city,
          region: info.region || extra.region,
          timezone: info.timezone || extra.timezone,
          country: info.country || extra.country,
          latitude: info.latitude != null ? info.latitude : extra.latitude,
          longitude: info.longitude != null ? info.longitude : extra.longitude,
          src: (info.src || '') + '+enrich:' + extra.src_extra
        });
        if (info.city && info.timezone) break;
      } catch (e) {
        errors.push('enrich:' + (e && e.message || e));
      }
    }
  }

  if (info && info.ip) {
    fillIP(info);
  } else {
    const seed = (PROFILE && PROFILE.seed_egress) || null;
    if (seed && seed.ip) {
      info = {
        ip: seed.ip,
        country: seed.country,
        city: seed.city,
        region: seed.region,
        timezone: seed.timezone,
        latitude: seed.latitude,
        longitude: seed.longitude,
        src: 'preflight-seed'
      };
      fillIP(info);
      $('ip_err').textContent = '实时探测失败，已用启动前 preflight：' + errors.join(' | ');
    } else {
      fillIP(null);
      set('ip', '探测失败');
      $('ip_err').textContent = errors.join(' | ') || '无可用探测源';
    }
  }
  try {
    const notes = (PROFILE && PROFILE.notes) || [];
    if (notes.length) $('ip_err').textContent += (($('ip_err').textContent ? ' | ' : '') + notes[0]);
  } catch (_) {}
  window.__IPINFO__ = info;
  return info;
}

function bindGeo() {
  if (!navigator.geolocation) { set('lat', 'API unavailable'); return; }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      set('lat', pos.coords.latitude.toFixed(5));
      set('lon', pos.coords.longitude.toFixed(5));
    },
    (err) => { /* keep expected coords */ $('ip_err').textContent += (($('ip_err').textContent ? ' | ' : '') + 'geo:' + (err.message || err)); },
    { timeout: 6000, maximumAge: 60000, enableHighAccuracy: false }
  );
}

async function main() {
  try {
    $('raw').textContent = JSON.stringify(PROFILE, null, 2);
    const local = collectLocal();
    expected();
    // seed first so city/tz show immediately
    if (PROFILE && PROFILE.seed_egress && PROFILE.seed_egress.ip) {
      fillIP(Object.assign({ src: 'preflight-seed' }, PROFILE.seed_egress));
      scoreAll(local, Object.assign({ src: 'preflight-seed' }, PROFILE.seed_egress));
    } else {
      scoreAll(local, null);
    }
    pill($('stPill'), 'muted', '探测出口中…');
    const ip = await probeIP();
    scoreAll(local, ip || (PROFILE && PROFILE.seed_egress) || null);
    bindGeo();
  } catch (e) {
    pill($('stPill'), 'bad', '页面脚本错误');
    $('ip_err').textContent = String(e && e.message || e);
    try { scoreAll(collectLocal(), null); } catch (_) {}
    console.error(e);
  }
}

$('btnReIP').onclick = async () => {
  const local = collectLocal();
  const ip = await probeIP();
  scoreAll(local, ip || null);
};
$('btnRescore').onclick = () => scoreAll(collectLocal(), window.__IPINFO__ || (PROFILE && PROFILE.seed_egress) || null);
$('btnCopy').onclick = async () => {
  const rep = { profile: PROFILE, score: window.__SCORE__, ip: window.__IPINFO__, at: new Date().toISOString() };
  const text = JSON.stringify(rep, null, 2);
  try { await navigator.clipboard.writeText(text); pill($('stPill'), 'ok', '已复制报告'); }
  catch { prompt('复制报告', text); }
};
main();
</script>
</body></html>
"""


def write_check_page(profile: Profile) -> str:
    """Write a local check HTML under profile dir; return file:// URL."""
    d = safe_resolve(ROOT / profile.user_data_dir)
    d.mkdir(parents=True, exist_ok=True)

    seed_egress = None
    # prefer last_check.json (written by preflight)
    try:
        lc = safe_resolve(ROOT / profile.user_data_dir / "last_check.json")
        if lc.is_file():
            data = json.loads(lc.read_text(encoding="utf-8"))
            eg = data.get("egress") if isinstance(data, dict) else None
            if isinstance(eg, dict) and (eg.get("ip") or eg.get("country")):
                seed_egress = {
                    k: eg.get(k)
                    for k in (
                        "ip",
                        "country",
                        "city",
                        "region",
                        "timezone",
                        "latitude",
                        "longitude",
                        "provider",
                    )
                }
                seed_egress["src"] = "last_check"
    except Exception:
        seed_egress = None
    if not seed_egress:
        le = (profile.meta or {}).get("last_egress")
        if isinstance(le, dict) and (le.get("ip") or le.get("country")):
            seed_egress = {
                k: le.get(k)
                for k in ("ip", "country", "city", "region", "timezone", "latitude", "longitude")
            }
            seed_egress["src"] = "meta.last_egress"

    payload = {
        "id": profile.id,
        "name": profile.name,
        "engine": getattr(profile.engine, "value", profile.engine),
        "patch": getattr(profile.chromium_patch, "value", profile.chromium_patch),
        "proxy": profile.proxy.model_dump(mode="json"),
        "env": profile.env.model_dump(mode="json"),
        "meta": {
            k: profile.meta.get(k)
            for k in (
                "expected_country",
                "bound_node",
                "sub",
                "auto_cf",
                "pass_cf",
                "cf_timeout",
                "group",
                "auto_rebind_on_launch",
                "webrtc_mode",
                "doh_mode",
            )
            if k in (profile.meta or {})
        },
        "seed_egress": seed_egress,
        "notes": [
            "住宅/动态节点同一名称也可能换 IP",
            "城市/时区来自完整 Geo 探测源；仅 CF trace 时会二次 enrichment",
        ],
    }
    dumped = json.dumps(payload, ensure_ascii=False)
    dumped = dumped.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = CHECK_PAGE_HTML.replace("__PROFILE_JSON__", dumped)
    # Fix the deliberately broken newline split in ipify+cf parser for raw string safety:
    # In template we used split('\\n') which becomes split('\n') literally wrong in raw?
    # CHECK_PAGE_HTML is raw triple quotes; we wrote split('\\n') which is backslash-n two chars.
    # Convert to real JS split on newline:
    html = html.replace("tr.split('\\\\n')", "tr.split('\\n')")
    html = html.replace("tr.split('\\\\n')", "tr.split('\\n')")
    # our source has: tr.split('\\n') inside the r""" ... """ which is the characters \ n
    # In the Python raw string r"""... tr.split('\\n') ..."""  -> content is tr.split('\n') with escaped backslash?
    # Actually in r""" tr.split('\\n') """ the content is: tr.split('\\n')  i.e. backslash backslash n? 
    # In raw strings, \\ is \ + \ , and \n is backslash + n (two chars). So '\\n' in raw is \ \ n? 
    # Let's be explicit after write.
    path = d / "check.html"
    path.write_text(html, encoding="utf-8")
    return path.resolve().as_uri()

