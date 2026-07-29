/** Create-profile modal module. */
import { api, esc } from "../core/api.js";
import { toast } from "../core/toast.js";
import { seg, segVal, state } from "../core/state.js";
import { loadProfiles } from "./profiles.js";
import { loadGroups } from "./groups.js";
import { fillCreateLibSelect, loadProxies } from "./proxies.js";

const SOCKS_IDS = [
  "lab_socks_lib",
  "c_socks5_lib",
  "lab_socks_host",
  "c_socks_host",
  "lab_socks_port",
  "c_socks_port",
  "lab_socks_user",
  "c_socks_user",
  "lab_socks_pass",
  "c_socks_pass",
  "lab_socks_refresh",
  "c_socks_refresh",
];

const MIHOMO_IDS = [
  "lab_sub",
  "c_sub",
  "lab_node_filter",
  "c_node_filter_wrap",
  "lab_node",
  "c_node_wrap",
  "c_node",
  "c_node_count",
  "lab_port",
  "c_port_wrap",
];

/** Cache of nodes for current create-sub selection. */
let createNodes = [];
let createNodesSub = "";

function isMetaNode(n) {
  if (n?.info === true) return true;
  const name = String(n?.name || "");
  const keys = ["剩余流量", "套餐到期", "距离下次", "过期", "到期时间", "流量：", "重置剩余", "官网", "最新网址"];
  if (keys.some((k) => name.includes(k))) return true;
  const server = String(n?.server || "");
  if ((server === "127.0.0.1" || server === "localhost") && /流量|到期|重置|剩余|官网|通知/.test(name)) return true;
  return false;
}

export async function loadCountries() {
  const sel = document.getElementById("c_country");
  if (!sel || sel.dataset.loaded === "1") return;
  try {
    const packs = await api("/api/templates/packs");
    const cur = sel.value;
    const opts = ['<option value="">不使用</option>'].concat(
      (packs || []).map((x) => {
        const cc = x.country || x.id || "";
        return `<option value="${esc(cc)}">${esc(cc)} · ${esc(x.timezone_id || "")} · ${esc(x.locale || "")}</option>`;
      })
    );
    sel.innerHTML = opts.join("");
    sel.dataset.loaded = "1";
    if (cur) sel.value = cur;
  } catch (_) {}
}

export async function loadSubsForCreate() {
  const sel = document.getElementById("c_sub");
  if (!sel) return;
  const prev = sel.value;
  let active = "default";
  try {
    const a = await api("/api/subscriptions/active");
    active = a.active || "default";
  } catch (_) {}
  let subs = [];
  try {
    subs = await api("/api/subscriptions");
  } catch (_) {
    subs = [];
  }
  state.subs = subs || [];
  if (!subs?.length) {
    sel.innerHTML = `<option value="${esc(active)}">${esc(active)}</option>`;
  } else {
    sel.innerHTML = subs
      .map((s) => {
        const name = s.name || "";
        const n = s.node_count != null ? ` · ${s.node_count}节点` : "";
        const act = s.active || name === active ? " ★" : "";
        return `<option value="${esc(name)}">${esc(name)}${n}${act}</option>`;
      })
      .join("");
  }
  // prefer previous → active → first
  if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
  else if ([...sel.options].some((o) => o.value === active)) sel.value = active;
  else if (sel.options.length) sel.selectedIndex = 0;
}

export async function loadNodesForCreate(sub, { keepSelection = true } = {}) {
  const sel = document.getElementById("c_node");
  if (!sel) return;
  const name = (sub || document.getElementById("c_sub")?.value || "default").trim() || "default";
  const prev = keepSelection ? sel.value : "";
  sel.innerHTML = `<option value="">加载节点中…</option>`;
  try {
    const nodes = await api("/api/nodes?sub=" + encodeURIComponent(name));
    createNodes = Array.isArray(nodes) ? nodes : [];
    createNodesSub = name;
    state.nodes = createNodes;
  } catch (e) {
    createNodes = [];
    createNodesSub = name;
    sel.innerHTML = `<option value="">加载失败：${esc(e.message || e)}</option>`;
    return;
  }
  // country filter options
  const ccSel = document.getElementById("c_node_cc");
  if (ccSel) {
    const curCc = ccSel.value;
    const ccs = [
      ...new Set(
        createNodes
          .filter((n) => !isMetaNode(n))
          .map((n) => (n.country || "").toUpperCase())
          .filter(Boolean)
      ),
    ].sort();
    ccSel.innerHTML =
      '<option value="">全部国家</option>' +
      ccs.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
    if (curCc && ccs.includes(curCc)) ccSel.value = curCc;
  }
  renderNodeOptions(prev);
}

function filteredCreateNodes() {
  const q = (document.getElementById("c_node_q")?.value || "").trim().toLowerCase();
  const cc = (document.getElementById("c_node_cc")?.value || "").toUpperCase();
  const showInfo = !!document.getElementById("c_node_show_info")?.checked;
  return createNodes.filter((n) => {
    if (!showInfo && isMetaNode(n)) return false;
    if (cc && String(n.country || "").toUpperCase() !== cc) return false;
    if (!q) return true;
    const blob = `${n.name || ""} ${n.country || ""} ${n.server || ""} ${n.type || ""} ${n.port || ""}`.toLowerCase();
    return blob.includes(q);
  });
}

export function renderNodeOptions(preferValue) {
  const sel = document.getElementById("c_node");
  if (!sel) return;
  // always keep native single-line dropdown (never listbox)
  sel.removeAttribute("size");
  sel.classList.add("node-select-dropdown");
  const rows = filteredCreateNodes();
  // sort: favorites first, then by country, then name
  rows.sort((a, b) => {
    const fa = a.favorite ? 0 : 1;
    const fb = b.favorite ? 0 : 1;
    if (fa !== fb) return fa - fb;
    const ca = a.country || "ZZ";
    const cb = b.country || "ZZ";
    if (ca !== cb) return ca.localeCompare(cb);
    return String(a.name || "").localeCompare(String(b.name || ""));
  });
  const pref = preferValue != null ? preferValue : sel.value;
  if (!rows.length) {
    sel.innerHTML = `<option value="">— 无可用节点（请先导入订阅或调整筛选）—</option>`;
    const tip0 = document.getElementById("c_node_count");
    if (tip0) tip0.textContent = "无匹配节点";
    return;
  }
  const total = createNodes.length;
  const usable = createNodes.filter((n) => !isMetaNode(n)).length;
  const infoN = total - usable;

  // group by country for compact dropdown scanning
  const groups = new Map();
  for (const n of rows) {
    const g = (n.country || (isMetaNode(n) ? "信息" : "未分组")).toUpperCase();
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(n);
  }
  const optHtml = (n) => {
    const lat = n.latency_ms != null && n.latency_ms > 0 ? ` · ${n.latency_ms}ms` : "";
    const fav = n.favorite ? "★ " : "";
    const typ = n.type ? `${n.type} · ` : "";
    const info = isMetaNode(n) ? "[信息] " : "";
    const srv = n.server ? ` · ${n.server}` : "";
    const label = `${info}${fav}${typ}${n.name}${lat}${srv}`;
    return `<option value="${esc(n.name)}" data-country="${esc(n.country || "")}" data-server="${esc(n.server || "")}" data-info="${isMetaNode(n) ? "1" : "0"}">${esc(label)}</option>`;
  };
  let body = "";
  for (const [g, list] of groups) {
    body += `<optgroup label="${esc(g)} (${list.length})">` + list.map(optHtml).join("") + `</optgroup>`;
  }
  sel.innerHTML =
    `<option value="">— 请选择节点（可用 ${usable} / 全部 ${total}）—</option>` + body;
  if (pref && [...sel.options].some((o) => o.value === pref)) sel.value = pref;
  sel.title = `下拉选择 · 显示 ${rows.length} · 可用 ${usable} · 信息 ${infoN} · 全部 ${total} · 订阅 ${createNodesSub || "-"}`;
  const tip = document.getElementById("c_node_count");
  if (tip) tip.textContent = `下拉可选 ${rows.length} · 可用 ${usable} / 全部 ${total}（信息项 ${infoN}）· 上方可搜索/按国家筛选`;
}

async function onNodePicked() {
  const name = document.getElementById("c_node")?.value || "";
  updateCreateSummary();
  if (!name) return;
  try {
    const rec = await api("/api/templates/recommend-node", {
      method: "POST",
      body: JSON.stringify({ node_name: name, jitter: true }),
    });
    if (rec?.ok) {
      const c = document.getElementById("c_country");
      if (c && rec.country) {
        // ensure option exists
        if (![...c.options].some((o) => o.value === rec.country)) {
          const opt = document.createElement("option");
          opt.value = rec.country;
          opt.textContent = `${rec.country} · 推荐`;
          c.appendChild(opt);
        }
        c.value = rec.country;
      }
      toast(
        `节点 → ${rec.country || "?"} · ${rec.env?.timezone_id || rec.pack?.timezone_id || ""} · ${rec.env?.locale || rec.pack?.locale || ""}`
      );
      updateCreateSummary();
    }
  } catch (_) {
    /* non-fatal */
  }
}

export function openCreate(opts = {}) {
  document.getElementById("createModal")?.classList.add("show");
  loadCountries().catch(() => {});
  loadProxies()
    .then(() => fillCreateLibSelect())
    .catch(() => fillCreateLibSelect());

  // preload subs + nodes for mihomo
  loadSubsForCreate()
    .then(() => loadNodesForCreate(document.getElementById("c_sub")?.value))
    .catch((e) => toast(e.message || String(e), "err"));

  // optional prefill from external (订阅页「用于新建」)
  if (opts.mode === "mihomo" || opts.node || opts.sub) {
    const modeBtn = document.querySelector('#c_proxy_mode button[data-v="mihomo"]');
    if (modeBtn) seg(modeBtn);
    if (opts.sub) {
      const s = document.getElementById("c_sub");
      if (s) s.value = opts.sub;
    }
  }
  if (opts.node) {
    // ensure loaded then select
    const applyNode = () => {
      const sel = document.getElementById("c_node");
      if (!sel) return;
      if (![...sel.options].some((o) => o.value === opts.node)) {
        const opt = document.createElement("option");
        opt.value = opts.node;
        opt.textContent = opts.node;
        sel.appendChild(opt);
      }
      sel.value = opts.node;
      onNodePicked();
    };
    loadNodesForCreate(opts.sub || document.getElementById("c_sub")?.value, { keepSelection: false })
      .then(applyNode)
      .catch(applyNode);
  }

  syncProxyFields();
  updateCreateSummary();
}

export function closeCreate() {
  document.getElementById("createModal")?.classList.remove("show");
}

export function syncProxyFields() {
  const mode = segVal("c_proxy_mode");
  const showSocks = mode === "socks5";
  const showM = mode === "mihomo";
  SOCKS_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = showSocks ? "" : "none";
  });
  MIHOMO_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = showM ? "" : "none";
  });
  // when switching to mihomo ensure nodes loaded
  if (showM && (!createNodes.length || createNodesSub !== (document.getElementById("c_sub")?.value || ""))) {
    loadNodesForCreate(document.getElementById("c_sub")?.value).catch(() => {});
  }
}

function buildSocks5Url() {
  const host = document.getElementById("c_socks_host")?.value.trim() || "";
  const port = document.getElementById("c_socks_port")?.value.trim() || "";
  const user = document.getElementById("c_socks_user")?.value.trim() || "";
  const pass = document.getElementById("c_socks_pass")?.value || "";
  if (!host || !port) return "";
  const enc = (s) => encodeURIComponent(s);
  if (user) return `socks5://${enc(user)}:${enc(pass)}@${host}:${port}`;
  return `socks5://${host}:${port}`;
}

function currentSocksSummary() {
  const host = document.getElementById("c_socks_host")?.value.trim() || "";
  const port = document.getElementById("c_socks_port")?.value.trim() || "";
  const user = document.getElementById("c_socks_user")?.value.trim() || "";
  if (!host) return "-";
  return user ? `${user}@${host}:${port || "?"}` : `${host}:${port || "?"}`;
}

export function updateCreateSummary() {
  const kv = document.getElementById("createSummary");
  if (!kv) return;
  const mode = segVal("c_proxy_mode");
  let proxyDetail = "直连";
  if (mode === "socks5") proxyDetail = currentSocksSummary();
  else if (mode === "mihomo") {
    const sub = document.getElementById("c_sub")?.value || "-";
    const node = document.getElementById("c_node")?.value || "未选节点";
    proxyDetail = `mihomo / ${sub} / ${node}`;
  }
  const rows = [
    ["名称", document.getElementById("c_name")?.value || "-"],
    ["引擎", segVal("c_engine")],
    ["补丁", segVal("c_patch")],
    ["国家", document.getElementById("c_country")?.value || "-"],
    ["代理", mode],
    ["出口", proxyDetail],
    ["分组", document.getElementById("c_group")?.value || "未分组"],
    ["节点", document.getElementById("c_node")?.value || "-"],
    ["CF过盾", document.getElementById("c_auto_cf")?.checked ? "开启" : "关闭"],
  ];
  kv.innerHTML = rows.map(([k, v]) => `<span>${esc(k)}</span><b>${esc(v)}</b>`).join("");
}

function onLibChange() {
  const sel = document.getElementById("c_socks5_lib");
  if (!sel || !sel.value) return;
  const opt = sel.selectedOptions?.[0];
  if (!opt) return;
  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.value = v ?? "";
  };
  set("c_socks_host", opt.dataset.host || "");
  set("c_socks_port", opt.dataset.port || "");
  set("c_socks_user", opt.dataset.user || "");
  set("c_socks_pass", opt.dataset.pass || "");
  set("c_socks_refresh", opt.dataset.refresh || "");
  set("c_socks5", opt.dataset.socks5 || "");
  updateCreateSummary();
}

export async function submitCreate() {
  const name = document.getElementById("c_name")?.value.trim();
  if (!name) return toast("请填写名称", "err");
  const mode = segVal("c_proxy_mode");
  const tabs = (document.getElementById("c_tabs")?.value || "")
    .split(/\n+/)
    .map((s) => s.trim())
    .filter(Boolean);

  let socks5 = "";
  if (mode === "socks5") {
    socks5 = buildSocks5Url();
    if (!socks5) return toast("请填写 SOCKS5 主机和端口", "err");
    const host = document.getElementById("c_socks_host")?.value.trim() || "";
    const port = Number(document.getElementById("c_socks_port")?.value || 0);
    const username = document.getElementById("c_socks_user")?.value.trim() || "";
    const password = document.getElementById("c_socks_pass")?.value || "";
    const refresh_url = document.getElementById("c_socks_refresh")?.value.trim() || "";
    try {
      await api("/api/proxies/socks5", {
        method: "POST",
        body: JSON.stringify({
          name: name + "-proxy",
          host,
          port,
          username,
          password,
          refresh_url,
          socks5,
        }),
      });
    } catch (_) {}
  }

  const nodeName = mode === "mihomo" ? document.getElementById("c_node")?.value || "" : "";
  if (mode === "mihomo" && !nodeName) {
    return toast("请从下拉列表选择订阅节点", "err");
  }

  const body = {
    name,
    engine: segVal("c_engine"),
    patch: segVal("c_patch"),
    country: document.getElementById("c_country")?.value || "",
    group: document.getElementById("c_group")?.value.trim() || "",
    remark: document.getElementById("c_remark")?.value.trim() || "",
    tabs,
    socks5: mode === "socks5" ? socks5 : "",
    sub: document.getElementById("c_sub")?.value.trim() || "default",
    mihomo_port:
      mode === "mihomo" && !document.getElementById("c_auto_port")?.checked
        ? Number(document.getElementById("c_port")?.value || 0)
        : 0,
    auto_port: mode === "mihomo" && !!document.getElementById("c_auto_port")?.checked,
    node_name: nodeName,
    node: nodeName, // alias
    fingerprint_id: document.getElementById("c_fp")?.value || "",
    browser_only: true,
    auto_cf: !!document.getElementById("c_auto_cf")?.checked,
    cf_timeout: Number(document.getElementById("c_cf_timeout")?.value || 45),
  };
  // for mihomo without explicit port, still create with auto_port/node
  if (mode === "mihomo") {
    body.auto_port = body.auto_port || !body.mihomo_port;
  }

  const p = await api("/api/profiles", { method: "POST", body: JSON.stringify(body) });
  toast("已创建 " + p.id + (nodeName ? " · " + nodeName : ""));
  closeCreate();
  await loadProfiles();
  await loadGroups();
  try {
    await loadProxies();
  } catch (_) {}
}

export function bindCreateModal() {
  document.getElementById("btnOpenCreate")?.addEventListener("click", () => openCreate());
  document.getElementById("btnOpenCreate2")?.addEventListener("click", () => openCreate());
  document.getElementById("btnCloseCreate")?.addEventListener("click", closeCreate);
  document.getElementById("btnCancelCreate")?.addEventListener("click", closeCreate);
  document.getElementById("btnSubmitCreate")?.addEventListener("click", () =>
    submitCreate().catch((e) => toast(e.message, "err"))
  );

  document.querySelectorAll(".seg").forEach((segEl) => {
    segEl.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-v]");
      if (!btn) return;
      seg(btn);
      if (segEl.id === "c_proxy_mode") syncProxyFields();
      updateCreateSummary();
    });
  });

  document.getElementById("c_socks5_lib")?.addEventListener("change", onLibChange);

  document.getElementById("c_sub")?.addEventListener("change", () => {
    loadNodesForCreate(document.getElementById("c_sub")?.value, { keepSelection: false })
      .then(() => updateCreateSummary())
      .catch((e) => toast(e.message, "err"));
  });
  document.getElementById("c_node")?.addEventListener("change", () => onNodePicked());
  document.getElementById("c_node_q")?.addEventListener("input", () => {
    renderNodeOptions();
    updateCreateSummary();
  });
  document.getElementById("c_node_cc")?.addEventListener("change", () => {
    renderNodeOptions();
    updateCreateSummary();
  });
  document.getElementById("c_node_show_info")?.addEventListener("change", () => {
    renderNodeOptions();
    updateCreateSummary();
  });

  document.addEventListener("input", (e) => {
    const ids = [
      "c_name",
      "c_group",
      "c_country",
      "c_socks5",
      "c_socks_host",
      "c_socks_port",
      "c_socks_user",
      "c_sub",
      "c_port",
      "c_node",
    ];
    if (ids.includes(e.target.id)) updateCreateSummary();
  });
  document.addEventListener("change", (e) => {
    if (["c_sub", "c_node", "c_country", "c_auto_cf", "c_cf_timeout"].includes(e.target.id)) updateCreateSummary();
  });

  window.MMOpenCreate = openCreate;
}
