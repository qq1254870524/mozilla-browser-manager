/** Profiles module — environment list + lifecycle actions. */
import { api, esc } from "../core/api.js";
import { toast } from "../core/toast.js";
import { state } from "../core/state.js";

export function proxyText(p) {
  if (!p) return "直连";
  if (p.mode === "socks5") return p.socks5 || "socks5";
  if (p.mode === "mihomo")
    return `mihomo:${p.mihomo_port || "-"}${p.node_name ? " / " + p.node_name : ""}`;
  return "直连";
}

function tagPills(p) {
  const tags = p.meta?.tags || [];
  const extra = [];
  if (p.meta?.locked || p.locked) {
    extra.push('<span class="pill" style="background:#fff7ed;color:#c2410c">锁定</span>');
  }
  if (p.meta?.need_relogin || p.need_relogin || tags.includes("需重登")) {
    extra.push('<span class="pill" style="background:#fef2f2;color:#b91c1c">需重登</span>');
  }
  const ar = p.auto_rebind_on_launch ?? p.meta?.auto_rebind_on_launch;
  if (ar === false) {
    extra.push('<span class="pill" style="background:#f8fafc;color:#64748b">重绑关</span>');
  } else {
    extra.push('<span class="pill" style="background:#ecfdf5;color:#047857" title="launch 按出口IP重绑 tz/locale/geo">自动重绑</span>');
  }
  const webrtc = p.privacy?.webrtc_mode || p.meta?.webrtc_mode || "disable";
  if (webrtc && webrtc !== "disable") {
    extra.push(`<span class="pill" style="background:#eef2ff;color:#4338ca">WebRTC:${esc(webrtc)}</span>`);
  }
  if (p.meta?.auto_cf || p.meta?.pass_cf) {
    extra.push('<span class="pill" style="background:#fef3c7;color:#b45309" title="启动自动过 CF/Turnstile">CF过盾</span>');
  }
  const shown = tags.filter((t) => t !== "需重登").slice(0, 4);
  return (
    extra.join(" ") +
    " " +
    shown.map((t) => `<span class="pill" style="background:#eff6ff;color:#1d4ed8">${esc(t)}</span>`).join(" ")
  );
}

export function renderProfiles() {
  const q = (document.getElementById("qProfile")?.value || "").toLowerCase();
  const eng = document.getElementById("filterEngine")?.value || "";
  const grp = document.getElementById("filterGroup")?.value || "";
  const tag = (document.getElementById("filterTag")?.value || "").toLowerCase();
  const onlyRelogin = document.getElementById("filterRelogin")?.checked;
  const body = document.getElementById("profileBody");
  if (!body) return;

  const rows = state.profiles.filter((p) => {
    if (eng && p.engine !== eng) return false;
    if (grp && (p.meta?.group || "未分组") !== grp) return false;
    const tags = (p.meta?.tags || []).map((x) => String(x).toLowerCase());
    if (tag && !tags.includes(tag) && !(p.meta?.expected_country || "").toLowerCase().includes(tag)) return false;
    if (onlyRelogin && !(p.meta?.need_relogin || tags.includes("需重登"))) return false;
    const blob = `${p.id} ${p.name} ${p.meta?.remark || ""} ${p.meta?.group || ""} ${p.meta?.expected_country || ""} ${tags.join(" ")}`.toLowerCase();
    return !q || blob.includes(q);
  });

  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="10"><div class="empty">暂无环境，点击「新建浏览器」开始</div></td></tr>`;
  } else {
    body.innerHTML = rows
      .map((p, idx) => {
        const checked = state.selected.has(p.id) ? "checked" : "";
        const st = p.running
          ? '<span class="pill run">运行中</span>'
          : '<span class="pill off">已停止</span>';
        const cc = p.meta?.expected_country || "";
        const fp = p.env?.fingerprint?.template_id || "";
        return `<tr>
        <td><input type="checkbox" ${checked} data-id="${esc(p.id)}" class="row-sel" /></td>
        <td class="mono">${idx + 1}</td>
        <td><b>${esc(p.name)}</b> ${tagPills(p)}<div class="mono" style="color:#94a3b8">${esc(p.id)}${cc ? " · " + esc(cc) : ""}${fp ? " · " + esc(fp) : ""}</div></td>
        <td>${st}</td>
        <td><span class="pill">${esc(p.engine)}</span> <span class="pill">${esc(p.chromium_patch)}</span></td>
        <td class="mono">${esc(proxyText(p.proxy))}</td>
        <td>${esc(p.env?.timezone_id || "")} / ${esc(p.env?.locale || "")}</td>
        <td>${esc(p.meta?.group || "未分组")}</td>
        <td class="mono">${esc(p.updated_at || "")}</td>
        <td class="actions">
          ${
            p.running
              ? `<button class="btn btn-ghost btn-sm" data-act="stop" data-id="${esc(p.id)}">停止</button>`
              : `<button class="btn btn-primary btn-sm" data-act="launch" data-id="${esc(p.id)}">打开</button>`
          }
          <button class="btn btn-ghost btn-sm" data-act="check" data-id="${esc(p.id)}">检测</button>
          <button class="btn btn-ghost btn-sm" data-act="diagnose" data-id="${esc(p.id)}" title="网络诊断">诊断</button>
          <button class="btn btn-ghost btn-sm" data-act="migrate" data-id="${esc(p.id)}" title="导出迁移包">迁移</button>
          <button class="btn btn-ghost btn-sm" data-act="backup" data-id="${esc(p.id)}">备份</button>
          <button class="btn btn-ghost btn-sm" data-act="tt" data-id="${esc(p.id)}">快照</button>
          <button class="btn btn-ghost btn-sm" data-act="proxy" data-id="${esc(p.id)}" title="更改代理/节点">改代理</button>
          <button class="btn btn-ghost btn-sm" data-act="failover" data-id="${esc(p.id)}">切节点</button>
          <button class="btn btn-ghost btn-sm" data-act="copy" data-id="${esc(p.id)}" title="复制摘要">复制</button>
          <button class="btn btn-ghost btn-sm" data-act="tag" data-id="${esc(p.id)}" title="加标签">标签</button>
          <button class="btn btn-ghost btn-sm" data-act="record" data-id="${esc(p.id)}" title="RPA录制">录制</button>
          <button class="btn btn-ghost btn-sm" data-act="rebind" data-id="${esc(p.id)}" title="按出口IP重绑 tz/locale/geo">重绑</button>
          <button class="btn btn-ghost btn-sm" data-act="autorebind" data-id="${esc(p.id)}" title="开关 launch 自动重绑">${(p.auto_rebind_on_launch ?? p.meta?.auto_rebind_on_launch) === false ? "开重绑" : "关重绑"}</button>
          <button class="btn btn-ghost btn-sm" data-act="privacy" data-id="${esc(p.id)}" title="WebRTC / DoH">隐私</button>
          <button class="btn btn-ghost btn-sm" data-act="cookie" data-id="${esc(p.id)}" title="Cookie 导入/导出">Cookie</button>
          <button class="btn btn-ghost btn-sm" data-act="lock" data-id="${esc(p.id)}" title="锁定/解锁">${p.meta?.locked || p.locked ? "解锁" : "锁定"}</button>
          <button class="btn btn-danger btn-sm" data-act="delete" data-id="${esc(p.id)}">删除</button>
        </td>
      </tr>`;
      })
      .join("");
  }
  const count = document.getElementById("profileCount");
  if (count) {
    const selVisible = rows.filter((p) => state.selected.has(p.id)).length;
    count.textContent = `总数 ${rows.length} / 全部 ${state.profiles.length} · 已选 ${state.selected.size}${selVisible !== state.selected.size ? ` (可见 ${selVisible})` : ""}`;
  }
  syncChkAllState(rows);
}

/** Currently visible filtered profile ids (same filters as render). */
export function visibleProfileIds() {
  const q = (document.getElementById("qProfile")?.value || "").toLowerCase();
  const eng = document.getElementById("filterEngine")?.value || "";
  const grp = document.getElementById("filterGroup")?.value || "";
  const tag = (document.getElementById("filterTag")?.value || "").toLowerCase();
  const onlyRelogin = document.getElementById("filterRelogin")?.checked;
  return state.profiles
    .filter((p) => {
      if (eng && p.engine !== eng) return false;
      if (grp && (p.meta?.group || "未分组") !== grp) return false;
      const tags = (p.meta?.tags || []).map((x) => String(x).toLowerCase());
      if (tag && !tags.includes(tag) && !(p.meta?.expected_country || "").toLowerCase().includes(tag)) return false;
      if (onlyRelogin && !(p.meta?.need_relogin || tags.includes("需重登"))) return false;
      const blob = `${p.id} ${p.name} ${p.meta?.remark || ""} ${p.meta?.group || ""} ${p.meta?.expected_country || ""} ${tags.join(" ")}`.toLowerCase();
      return !q || blob.includes(q);
    })
    .map((p) => p.id);
}

export function syncChkAllState(rows) {
  const chk = document.getElementById("chkAll");
  if (!chk) return;
  const list = rows || visibleProfileIds().map((id) => ({ id }));
  if (!list.length) {
    chk.checked = false;
    chk.indeterminate = false;
    return;
  }
  const n = list.filter((p) => state.selected.has(p.id || p)).length;
  chk.checked = n === list.length && n > 0;
  chk.indeterminate = n > 0 && n < list.length;
}

export function setSelectAll(checked) {
  const ids = visibleProfileIds();
  if (checked) ids.forEach((id) => state.selected.add(id));
  else ids.forEach((id) => state.selected.delete(id));
  renderProfiles();
}

export async function loadProfiles() {
  state.profiles = await api("/api/profiles");
  // drop selections for deleted profiles
  const alive = new Set(state.profiles.map((p) => p.id));
  for (const id of [...state.selected]) {
    if (!alive.has(id)) state.selected.delete(id);
  }
  const groups = [...new Set(state.profiles.map((p) => p.meta?.group || "未分组"))];
  const sel = document.getElementById("filterGroup");
  if (sel) {
    const cur = sel.value;
    sel.innerHTML =
      '<option value="">全部分组</option>' +
      groups.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join("");
    sel.value = cur;
  }
  // tags filter options
  try {
    const tr = await api("/api/tags");
    const tsel = document.getElementById("filterTag");
    if (tsel && tr.tags) {
      const cur = tsel.value;
      tsel.innerHTML =
        '<option value="">全部标签</option>' +
        tr.tags.map((x) => `<option value="${esc(x.tag)}">${esc(x.tag)} (${x.count})</option>`).join("");
      tsel.value = cur;
    }
  } catch (_) {}
  renderProfiles();
  // dashboard strip
  try {
    const d = await api("/api/ops/dashboard");
    const el = document.getElementById("dashStrip");
    if (el) {
      el.textContent = `环境 ${d.profiles} · 运行 ${d.running} · 需重登 ${d.need_relogin} · 锁定 ${d.locked||0} · 通知 ${d.notices_unread||0} · 模板 ${d.packs} · ${d.version}`;
    }
  } catch (_) {}
}

export async function launchProfile(id) {
  toast("启动中（含出口IP自动重绑）…");
  const r = await api("/api/profiles/" + id + "/launch", {
    method: "POST",
    body: JSON.stringify({ open_check: true }),
  });
  const rb = r.launch_rebind;
  const extra = rb
    ? ` · 重绑:${rb.rebound ? "是" : "否"}${rb.message ? " " + rb.message : ""}`
    : "";
  toast((r.message || "已启动") + extra, r.ok === false ? "err" : undefined);
  console.log("launch", r);
  await loadProfiles();
}

export async function stopProfile(id) {
  await api("/api/profiles/" + id + "/stop", { method: "POST", body: "{}" });
  toast("已停止");
  await loadProfiles();
}

export async function checkProfile(id) {
  const r = await api("/api/profiles/" + id + "/check");
  toast(
    (r.ok ? "检测通过: " : "检测问题: ") +
      JSON.stringify(r.egress || r.blocks || r.warnings || r).slice(0, 120),
    r.ok ? undefined : "err"
  );
}

export async function backupProfile(id) {
  let r;
  try {
    r = await api("/api/sessions/" + id + "/backup", { method: "POST", body: "{}" });
  } catch (_) {
    r = await api("/api/profiles/" + id + "/export", { method: "POST", body: "{}" });
  }
  toast("备份: " + (r.path || r.file || JSON.stringify(r).slice(0, 80)));
}

export async function deleteProfile(id) {
  if (!confirm("确认删除环境 " + id + " ?")) return;
  await api("/api/profiles/" + id + "?wipe=true", { method: "DELETE" });
  toast("已删除");
  await loadProfiles();
}

export async function bulkDelete() {
  const ids = [...state.selected];
  if (!ids.length) return toast("未选择", "err");
  if (!confirm(`删除选中 ${ids.length} 个？`)) return;
  for (const id of ids) {
    await api("/api/profiles/" + id + "?wipe=true", { method: "DELETE" });
  }
  state.selected.clear();
  toast("批量删除完成");
  await loadProfiles();
}

export async function bulkStop() {
  const ids = [...state.selected];
  if (!ids.length) return toast("未选择", "err");
  for (const id of ids) {
    try {
      await api("/api/profiles/" + id + "/stop", { method: "POST", body: "{}" });
    } catch (_) {}
  }
  toast("批量停止完成");
  await loadProfiles();
}

export async function bulkDiagnose() {
  const ids = [...state.selected];
  toast(ids.length ? `批量诊断 ${ids.length}…` : "全量诊断任务提交中…");
  const r = await api("/api/ops/bulk-diagnose", {
    method: "POST",
    body: JSON.stringify({ profile_ids: ids, samples: 3, async_job: true }),
  });
  toast(`任务已提交 ${r.id || ""}`);
}

export function bindProfileDom() {
  bindProxyModal();
  document.getElementById("qProfile")?.addEventListener("input", () => renderProfiles());
  document.getElementById("filterEngine")?.addEventListener("change", () => renderProfiles());
  document.getElementById("filterGroup")?.addEventListener("change", () => renderProfiles());
  document.getElementById("filterTag")?.addEventListener("change", () => renderProfiles());
  document.getElementById("filterRelogin")?.addEventListener("change", () => renderProfiles());

  document.getElementById("chkAll")?.addEventListener("change", (e) => {
    setSelectAll(!!e.target.checked);
  });

  document.getElementById("profileBody")?.addEventListener("change", (e) => {
    const t = e.target;
    if (t.classList?.contains("row-sel")) {
      if (t.checked) state.selected.add(t.dataset.id);
      else state.selected.delete(t.dataset.id);
      // update footer + header without full re-render of action buttons focus
      const count = document.getElementById("profileCount");
      const ids = visibleProfileIds();
      if (count) {
        const selVisible = ids.filter((id) => state.selected.has(id)).length;
        count.textContent = `总数 ${ids.length} / 全部 ${state.profiles.length} · 已选 ${state.selected.size}${selVisible !== state.selected.size ? ` (可见 ${selVisible})` : ""}`;
      }
      syncChkAllState(ids.map((id) => ({ id })));
    }
  });

  document.getElementById("profileBody")?.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const id = btn.dataset.id;
    const act = btn.dataset.act;
    try {
      if (act === "launch") await launchProfile(id);
      else if (act === "stop") await stopProfile(id);
      else if (act === "check") await checkProfile(id);
      else if (act === "backup") await backupProfile(id);
      else if (act === "delete") await deleteProfile(id);
      else if (act === "tt") {
        const r = await api("/api/timetravel/profiles/" + id, {
          method: "POST",
          body: JSON.stringify({ label: "ui-snap" }),
        });
        toast("快照 " + (r.ts || r.snapshot_id || r.path || "ok"));
      } else if (act === "proxy") {
        await openProxyEditor(id);
      } else if (act === "failover") {
        const r = await api("/api/failover/profiles/" + id + "/auto", { method: "POST", body: "{}" });
        toast((r.message || (r.ok ? "已切换" : "failover")), r.ok === false ? "err" : undefined);
      } else if (act === "diagnose") {
        toast("诊断中…");
        const r = await api(`/api/diagnose/profiles/${encodeURIComponent(id)}`, { method: "POST" });
        toast(r.ok ? "诊断通过" : "诊断异常", r.ok ? undefined : "err");
        console.log("diagnose", r);
      } else if (act === "migrate") {
        const r = await api(`/api/transfer/profiles/${encodeURIComponent(id)}/export`, { method: "POST" });
        toast("迁移包 " + (r.path || ""));
      } else if (act === "copy") {
        const r = await api(`/api/ops/profiles/${encodeURIComponent(id)}/summary`);
        const text = r.clipboard || id;
        try {
          await navigator.clipboard.writeText(text);
          toast("已复制: " + text.slice(0, 60));
        } catch {
          prompt("复制摘要", text);
        }
      } else if (act === "tag") {
        const raw = prompt("添加标签（逗号分隔）", "生产,店铺");
        if (raw == null) return;
        const tags = raw.split(",").map((x) => x.trim()).filter(Boolean);
        await api(`/api/tags/profiles/${encodeURIComponent(id)}/add`, {
          method: "POST",
          body: JSON.stringify({ tags }),
        });
        toast("标签已更新");
        await loadProfiles();
      } else if (act === "record") {
        // jump to tools with profile prefilled + try start
        const rp = document.getElementById("rpaProfile");
        if (rp) rp.value = id;
        const dp = document.getElementById("diagProfile");
        if (dp) dp.value = id;
        window.MM?.switchView?.("tools");
        toast("已填入工具箱，可点「开始录制」(需浏览器运行中)");
      } else if (act === "rebind") {
        toast("按出口 IP 重绑中…");
        const r = await api(`/api/health/profiles/${encodeURIComponent(id)}/rebind-env`, { method: "POST", body: "{}" });
        toast(r.message || (r.rebound ? "已重绑" : "未重绑"), r.ok === false ? "err" : undefined);
        console.log("rebind", r);
        await loadProfiles();
      } else if (act === "autorebind") {
        const cur = state.profiles.find((x) => x.id === id);
        const enabled = !((cur?.auto_rebind_on_launch ?? cur?.meta?.auto_rebind_on_launch) === false);
        const r = await api(`/api/health/profiles/${encodeURIComponent(id)}/auto-rebind`, {
          method: "POST",
          body: JSON.stringify({ enabled: !enabled }),
        });
        toast(r.auto_rebind_on_launch ? "已开启 launch 自动重绑" : "已关闭 launch 自动重绑");
        await loadProfiles();
      } else if (act === "privacy") {
        const cur = state.profiles.find((x) => x.id === id);
        const webrtc = prompt("WebRTC 模式: disable | spoof | off", cur?.privacy?.webrtc_mode || cur?.meta?.webrtc_mode || "disable");
        if (webrtc == null) return;
        const doh = prompt("DoH 模式: secure | off", cur?.privacy?.doh_mode || cur?.meta?.doh_mode || "secure");
        if (doh == null) return;
        const r = await api(`/api/privacy/profiles/${encodeURIComponent(id)}`, {
          method: "POST",
          body: JSON.stringify({ webrtc_mode: webrtc, doh_mode: doh }),
        });
        const pr = r.privacy || r;
        toast(`隐私已更新 WebRTC=${pr.webrtc_mode || webrtc} DoH=${pr.doh_mode || doh}`);
        await loadProfiles();
      } else if (act === "cookie") {
        const mode = prompt("Cookie: import / export", "export");
        if (mode == null) return;
        if (String(mode).toLowerCase().startsWith("ex")) {
          const r = await api(`/api/cookies/profiles/${encodeURIComponent(id)}/export`, {
            method: "POST",
            body: JSON.stringify({ fmt: "json" }),
          });
          const text = typeof r.data === "string" ? r.data : JSON.stringify(r.cookies || r.data || r, null, 2);
          try {
            await navigator.clipboard.writeText(text);
            toast("Cookie 已导出并复制 " + (r.count != null ? r.count + " 条" : ""));
          } catch {
            prompt("Cookie JSON", text.slice(0, 5000));
          }
          console.log("cookie-export", r);
        } else {
          const raw = prompt("粘贴 Cookie JSON 数组或 Base64", "[]");
          if (raw == null) return;
          const r = await api(`/api/cookies/profiles/${encodeURIComponent(id)}/import`, {
            method: "POST",
            body: JSON.stringify({ payload: raw, merge: true }),
          });
          toast(r.ok === false ? (r.message || "导入失败") : `已导入 ${r.count ?? r.imported ?? ""}`, r.ok === false ? "err" : undefined);
          console.log("cookie-import", r);
        }
      } else if (act === "lock") {
        const locked = !!(state.profiles.find((x) => x.id === id)?.meta?.locked || state.profiles.find((x) => x.id === id)?.locked);
        if (locked) {
          await api(`/api/locks/profiles/${encodeURIComponent(id)}/unlock`, { method: "POST" });
          toast("已解锁");
        } else {
          await api(`/api/locks/profiles/${encodeURIComponent(id)}/lock`, {
            method: "POST",
            body: JSON.stringify({ reason: "manual", owner: "ui", ttl_sec: 86400 }),
          });
          toast("已锁定");
        }
        await loadProfiles();
      }
    } catch (err) {
      toast(err.message || String(err), "err");
    }
  });

  document.getElementById("btnBulkStop")?.addEventListener("click", () => bulkStop().catch((e) => toast(e.message, "err")));
  document.getElementById("btnBulkDelete")?.addEventListener("click", () => bulkDelete().catch((e) => toast(e.message, "err")));
  document.getElementById("btnBulkDiagnose")?.addEventListener("click", () => bulkDiagnose().catch((e) => toast(e.message, "err")));
}

/* ---- change proxy modal ---- */
function _pxSeg(btn) {
  const wrap = btn?.closest(".seg");
  if (!wrap) return;
  wrap.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === btn));
  const mode = btn.dataset.v;
  const socks = document.getElementById("pxEditSocksBox");
  const mih = document.getElementById("pxEditMihomoBox");
  if (socks) socks.style.display = mode === "socks5" ? "" : "none";
  if (mih) mih.style.display = mode === "mihomo" ? "" : "none";
}

async function _loadPxSubs(prefer) {
  const sel = document.getElementById("pxEditSub");
  if (!sel) return;
  const subs = await api("/api/subscriptions").catch(() => state.subs || []);
  state.subs = subs;
  const cur = prefer || sel.value || "";
  sel.innerHTML =
    (subs || [])
      .map((s) => {
        const name = s.name || s;
        const n = s.node_count != null ? ` · ${s.node_count}` : "";
        return `<option value="${esc(name)}">${esc(name)}${n}</option>`;
      })
      .join("") || '<option value="default">default</option>';
  if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
}

async function _loadPxNodes(sub, prefer) {
  const sel = document.getElementById("pxEditNode");
  if (!sel) return;
  sel.innerHTML = '<option value="">加载中…</option>';
  try {
    const nodes = await api("/api/nodes?sub=" + encodeURIComponent(sub || "default"));
    const list = Array.isArray(nodes) ? nodes : [];
    const usable = list.filter((n) => !n.info);
    sel.innerHTML =
      '<option value="">— 请选择节点 —</option>' +
      usable
        .map((n) => {
          const lat = n.latency_ms ? ` · ${n.latency_ms}ms` : "";
          const cc = n.country ? `[${n.country}] ` : "";
          return `<option value="${esc(n.name)}">${cc}${esc(n.name)}${lat}</option>`;
        })
        .join("");
    if (prefer && [...sel.options].some((o) => o.value === prefer)) sel.value = prefer;
  } catch (e) {
    sel.innerHTML = `<option value="">加载失败 ${esc(e.message || e)}</option>`;
  }
}

export async function openProxyEditor(profileId) {
  const p = (state.profiles || []).find((x) => x.id === profileId);
  if (!p) return toast("环境不存在", "err");
  const modal = document.getElementById("proxyModal");
  if (!modal) return toast("缺少代理弹窗", "err");
  document.getElementById("pxEditProfileId").value = profileId;
  document.getElementById("pxEditProfileHint").textContent =
    `环境：${p.name || profileId} · ${profileId} · 当前 ${proxyText(p.proxy)}`;

  const mode = p.proxy?.mode || "none";
  const modeBtn =
    document.querySelector(`#pxEditMode button[data-v="${mode}"]`) ||
    document.querySelector('#pxEditMode button[data-v="none"]');
  if (modeBtn) _pxSeg(modeBtn);

  document.getElementById("pxEditSocks").value = p.proxy?.socks5 || "";
  document.getElementById("pxEditSocksPort").value = "1080";
  document.getElementById("pxEditSocksUser").value = "";
  document.getElementById("pxEditSocksPass").value = "";

  const sub = p.meta?.sub || "default";
  await _loadPxSubs(sub);
  await _loadPxNodes(sub, p.proxy?.node_name || "");
  document.getElementById("pxEditAutoPort").checked = true;
  document.getElementById("pxEditPort").value = p.proxy?.mihomo_port || 0;

  modal.classList.add("show");
}

async function saveProxyEditor() {
  const id = document.getElementById("pxEditProfileId")?.value;
  if (!id) return;
  const modeBtn = document.querySelector("#pxEditMode button.on");
  const mode = modeBtn?.dataset.v || "none";
  const body = {
    mode,
    browser_only: true,
    auto_port: true,
    socks5: "",
    node: "",
    node_name: "",
    mihomo_port: 0,
  };

  if (mode === "socks5") {
    let socks = document.getElementById("pxEditSocks")?.value.trim() || "";
    const port = document.getElementById("pxEditSocksPort")?.value.trim() || "1080";
    const user = document.getElementById("pxEditSocksUser")?.value.trim() || "";
    const pw = document.getElementById("pxEditSocksPass")?.value || "";
    if (!socks) return toast("请填写 SOCKS5 主机或 URL", "err");
    if (!/^socks5[h]?:\/\//i.test(socks) && !socks.includes("://")) {
      const auth = user ? `${encodeURIComponent(user)}:${encodeURIComponent(pw)}@` : "";
      socks = `socks5://${auth}${socks}:${port}`;
    }
    body.socks5 = socks;
  } else if (mode === "mihomo") {
    const node = document.getElementById("pxEditNode")?.value || "";
    if (!node) return toast("请选择节点", "err");
    body.node = node;
    body.node_name = node;
    body.sub = document.getElementById("pxEditSub")?.value || "default";
    body.auto_port = !!document.getElementById("pxEditAutoPort")?.checked;
    body.mihomo_port = Number(document.getElementById("pxEditPort")?.value || 0);
  }

  const r = await api("/api/profiles/" + encodeURIComponent(id) + "/proxy", {
    method: "POST",
    body: JSON.stringify(body),
  });
  document.getElementById("proxyModal")?.classList.remove("show");
  toast("代理已更新：" + proxyText(r.proxy || body));
  await loadProfiles();
}

function bindProxyModal() {
  const modal = document.getElementById("proxyModal");
  if (!modal || modal.dataset.bound) return;
  modal.dataset.bound = "1";
  document.getElementById("pxEditMode")?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-v]");
    if (btn) _pxSeg(btn);
  });
  document.getElementById("pxEditSub")?.addEventListener("change", () => {
    _loadPxNodes(document.getElementById("pxEditSub").value, "");
  });
  document.getElementById("btnCloseProxyModal")?.addEventListener("click", () =>
    modal.classList.remove("show")
  );
  document.getElementById("btnCancelProxy")?.addEventListener("click", () =>
    modal.classList.remove("show")
  );
  document.getElementById("btnSaveProxy")?.addEventListener("click", () =>
    saveProxyEditor().catch((e) => toast(e.message, "err"))
  );
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("show");
  });
}

