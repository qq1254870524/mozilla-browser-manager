const API = "http://127.0.0.1:17888";

async function getCfg() {
  const r = await chrome.storage.local.get(["profileId", "apiBase"]);
  return { profileId: r.profileId || "", apiBase: r.apiBase || API };
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "mm_root", title: "Mozilla Manager", contexts: ["page", "action"] });
    chrome.contextMenus.create({ id: "mm_switch_node", parentId: "mm_root", title: "切换当前 Profile 代理节点…", contexts: ["page", "action"] });
    chrome.contextMenus.create({ id: "mm_failover", parentId: "mm_root", title: "节点故障自动切换（同国）", contexts: ["page", "action"] });
    chrome.contextMenus.create({ id: "mm_migrate", parentId: "mm_root", title: "将此页迁移至其他 Profile…", contexts: ["page", "action"] });
    chrome.contextMenus.create({ id: "mm_snapshot", parentId: "mm_root", title: "创建时间旅行还原点", contexts: ["page", "action"] });
  });
});

async function api(path, opts = {}) {
  const cfg = await getCfg();
  const res = await fetch((cfg.apiBase || API) + path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const cfg = await getCfg();
  try {
    if (info.menuItemId === "mm_failover") {
      if (!cfg.profileId) return chrome.notifications?.create?.({ type: "basic", title: "Mozilla", message: "请先在扩展选项填写 profileId", iconUrl: "" });
      const r = await api(`/api/failover/profiles/${encodeURIComponent(cfg.profileId)}/auto`, { method: "POST", body: {} });
      console.log("failover", r);
      return;
    }
    if (info.menuItemId === "mm_snapshot") {
      if (!cfg.profileId) return;
      await api(`/api/timetravel/profiles/${encodeURIComponent(cfg.profileId)}`, { method: "POST", body: { label: "context-menu" } });
      return;
    }
    if (info.menuItemId === "mm_switch_node") {
      if (!cfg.profileId) return;
      // open options-like prompt via new tab to manager UI nodes
      chrome.tabs.create({ url: (cfg.apiBase || API) + "/#subs" });
      return;
    }
    if (info.menuItemId === "mm_migrate") {
      if (!tab?.url) return;
      // stash URL for migrate; manager UI can complete
      await chrome.storage.local.set({ migrateUrl: tab.url });
      chrome.tabs.create({ url: (cfg.apiBase || API) + "/?migrate=" + encodeURIComponent(tab.url) });
      return;
    }
  } catch (e) {
    console.error(e);
  }
});
