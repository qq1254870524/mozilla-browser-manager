/**
 * App shell — navigation only. Feature logic lives in js/modules/*.
 */
import { api } from "./api.js";
import { toast } from "./toast.js";
import { state } from "./state.js";
import { loadProfiles, bindProfileDom, renderProfiles } from "../modules/profiles.js";
import { loadGroups, bindGroupsDom, renderGroups } from "../modules/groups.js";
import { loadProxies, bindProxiesDom } from "../modules/proxies.js";
import { loadSubs, loadNodes, bindSubsDom } from "../modules/subscriptions.js";
import { loadDoctor, bindDoctorDom } from "../modules/doctor.js";
import { bindToolsDom } from "../modules/tools.js";
import {
  openCreate,
  bindCreateModal,
  syncProxyFields,
  updateCreateSummary,
} from "../modules/create_modal.js";

const TITLES = {
  profiles: "环境管理",
  groups: "分组管理",
  proxies: "代理管理",
  subs: "订阅 / 节点",
  doctor: "系统诊断",
  tools: "v10 工具箱",
};

export function switchView(name) {
  state.view = name;
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.view === name);
  });
  ["profiles", "groups", "proxies", "subs", "doctor", "tools"].forEach((v) => {
    const el = document.getElementById("view-" + v);
    if (el) el.style.display = v === name ? "" : "none";
  });
  const title = document.getElementById("pageTitle");
  if (title) title.textContent = TITLES[name] || name;

  if (name === "groups") renderGroups();
  if (name === "proxies") loadProxies().catch((e) => toast(e.message, "err"));
  if (name === "subs") {
    loadSubs().catch((e) => toast(e.message, "err"));
    loadNodes().catch((e) => toast(e.message, "err"));
  }
  if (name === "doctor") loadDoctor().catch((e) => toast(e.message, "err"));
  if (name === "profiles") renderProfiles();
}

async function refreshAll() {
  await Promise.all([loadProfiles(), loadGroups(), loadDoctor().catch(() => {})]);
  toast("已刷新");
}

async function init() {
  setInterval(() => {
    const c = document.getElementById("clock");
    if (c) c.textContent = new Date().toLocaleString();
  }, 1000);

  // auto-reconcile running state (browser closed outside panel)
  setInterval(() => {
    loadProfiles().catch(() => {});
  }, 4000); // mm-run-poll

  // nav
  document.querySelectorAll(".nav-item[data-view]").forEach((el) => {
    el.addEventListener("click", () => switchView(el.dataset.view));
  });
  document.getElementById("btnRefresh")?.addEventListener("click", () =>
    refreshAll().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnDoctorReload")?.addEventListener("click", () =>
    loadDoctor().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnGoSubs")?.addEventListener("click", () => switchView("subs"));
  const sideBtn = document.getElementById("btnSideToggle");
  const side = document.querySelector(".sidebar");
  const syncSideBtn = () => {
    if (sideBtn) sideBtn.style.display = window.innerWidth <= 960 ? "" : "none";
    if (window.innerWidth > 960) side?.classList.remove("open");
  };
  sideBtn?.addEventListener("click", () => side?.classList.toggle("open"));
  document.querySelectorAll(".nav-item[data-view]").forEach((el) => {
    el.addEventListener("click", () => {
      if (window.innerWidth <= 960) side?.classList.remove("open");
    });
  });
  window.addEventListener("resize", syncSideBtn);
  syncSideBtn();

  bindProfileDom();
  bindProxiesDom();
  bindGroupsDom(switchView);
  bindCreateModal();
  bindSubsDom(openCreate, syncProxyFields, updateCreateSummary);
  bindDoctorDom();
  bindToolsDom();

  document.getElementById("notifyBadge")?.addEventListener("click", () => {
    switchView("tools");
    document.getElementById("btnNotify")?.click();
  });

  try {
    await api("/api/health");
    const b = document.getElementById("healthBadge");
    if (b) b.textContent = "ROOT OK";
  } catch {
    const b = document.getElementById("healthBadge");
    if (b) b.textContent = "API 离线";
  }

  await loadProfiles();
  await loadGroups();

  // desktop client deep-link: /?view=tools|profiles|...
  try {
    const sp = new URLSearchParams(location.search);
    const v = sp.get("view");
    if (v) switchView(v);
  } catch (_) {}
  try {
    const d = await api("/api/ops/dashboard");
    const el = document.getElementById("dashStrip");
    if (el) el.textContent = `环境 ${d.profiles} · 运行 ${d.running} · 需重登 ${d.need_relogin} · 锁定 ${d.locked||0} · 通知 ${d.notices_unread||0} · 模板 ${d.packs} · ${d.machine_name||''} · ${d.version}`;
    const b = document.getElementById("healthBadge");
    if (b) b.textContent = d.version || "ROOT OK";
    const nb = document.getElementById("notifyBadge");
    if (nb) nb.textContent = d.notices_unread ? `通知 ${d.notices_unread}` : "通知";
  } catch (_) {}
  try {
    await loadDoctor();
  } catch (_) {}
}

init();

// debug hook
window.MM = { switchView, refreshAll, state };
