/** Subscriptions + nodes module (v5 runtime/nodes). */
import { api, esc } from "../core/api.js";
import { toast } from "../core/toast.js";
import { state } from "../core/state.js";

async function refreshActivePill() {
  try {
    const a = await api("/api/subscriptions/active");
    const pill = document.getElementById("activeSubPill");
    if (pill) {
      pill.textContent = `active: ${a.active || "—"} · ${a.meta?.node_count ?? "?"} 节点`;
      pill.className = "pill ok";
    }
    const nameEl = document.getElementById("subName");
    if (nameEl && a.active && !nameEl.dataset.userEdited) {
      nameEl.value = a.active;
    }
    return a;
  } catch (e) {
    const pill = document.getElementById("activeSubPill");
    if (pill) {
      pill.textContent = "active: error";
      pill.className = "pill off";
    }
    return null;
  }
}

export async function loadSubs() {
  state.subs = await api("/api/subscriptions");
  await refreshActivePill();
  const box = document.getElementById("subCards");
  if (!box) return;
  const active = (await api("/api/subscriptions/active").catch(() => ({}))).active;
  box.innerHTML =
    state.subs
      .map((s) => {
        const isActive = s.active || s.name === active;
        return `<div class="card stat" style="${isActive ? "outline:2px solid #93c5fd" : ""}">
    <div class="l">订阅 ${esc(s.name)} ${isActive ? '<span class="pill run">当前</span>' : ""}</div>
    <div class="n">${s.node_count ?? "-"}</div>
    <div class="l">${esc(s.url_host || s.source || "")} · ${esc((s.imported_at || s.updated_at || "").slice(0, 19))}</div>
    <div class="l" style="margin-top:6px;word-break:break-all">${esc(s.path || "runtime/nodes/subs/" + s.name)}</div>
    <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">
      <button class="btn btn-primary btn-sm" data-switch="${esc(s.name)}" ${isActive ? "disabled" : ""}>切换为当前</button>
      <button class="btn btn-ghost btn-sm" data-export="${esc(s.name)}">导出</button>
      <button class="btn btn-ghost btn-sm" data-use-sub="${esc(s.name)}">查看节点</button>
      <button class="btn btn-danger btn-sm" data-del-sub="${esc(s.name)}">删除订阅</button>
    </div>
  </div>`;
      })
      .join("") || `<div class="empty">尚未导入订阅 · 节点库 runtime/nodes/subs/</div>`;
}

function isInfoNode(n) {
  if (n?.info === true) return true;
  const name = String(n?.name || "");
  const keys = ["剩余流量", "套餐到期", "距离下次", "过期", "到期时间", "流量：", "重置剩余", "官网", "最新网址"];
  if (keys.some((k) => name.includes(k))) return true;
  const server = String(n?.server || "");
  if ((server === "127.0.0.1" || server === "localhost") && /流量|到期|重置|剩余|官网|通知/.test(name)) return true;
  return false;
}

export function renderNodes() {
  const body = document.getElementById("nodeBody");
  if (!body) return;
  const q = (document.getElementById("nodeQ")?.value || "").trim().toLowerCase();
  const typ = (document.getElementById("nodeTypeFilter")?.value || "").toLowerCase();
  const showInfo = document.getElementById("nodeShowInfo")?.checked !== false;
  const all = state.nodes || [];
  const usable = all.filter((n) => !isInfoNode(n)).length;
  const infoN = all.length - usable;
  const rows = all.filter((n) => {
    if (!showInfo && isInfoNode(n)) return false;
    if (typ && String(n.type || "").toLowerCase() !== typ) return false;
    if (!q) return true;
    const blob = `${n.name || ""} ${n.type || ""} ${n.server || ""} ${n.country || ""} ${n.port || ""}`.toLowerCase();
    return blob.includes(q);
  });
  const bar = document.getElementById("nodeCountBar");
  if (bar) {
    const types = {};
    all.forEach((n) => {
      const k = n.type || "?";
      types[k] = (types[k] || 0) + 1;
    });
    const typeStr = Object.entries(types)
      .map(([k, v]) => `${k}:${v}`)
      .join(" · ");
    bar.textContent = `显示 ${rows.length} / 全部 ${all.length} · 可用 ${usable} · 信息 ${infoN}${typeStr ? " · " + typeStr : ""}`;
  }
  const hint = document.getElementById("nodeFooterHint");
  if (hint) {
    const sub = document.getElementById("subName")?.value || "default";
    hint.textContent = `订阅 ${sub} · 完整 ${all.length} 条已入库 runtime/nodes/subs/${sub}/nodes.json（非UI截断）`;
  }
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="7"><div class="empty">${all.length ? "无匹配节点（请清空筛选）" : "无节点，请先导入/更新订阅"}</div></td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map((n, i) => {
      const info = isInfoNode(n);
      return `<tr style="${info ? "opacity:.72" : ""}">
    <td class="mono">${(n.index != null ? n.index : i) + 1}</td>
    <td>${info ? '<span class="pill off">信息</span> ' : ""}${esc(n.name)}${n.favorite ? " ★" : ""}</td>
    <td><span class="pill">${esc(n.type)}</span></td>
    <td>${n.country ? `<span class="pill">${esc(n.country)}</span>` : "—"}</td>
    <td class="mono">${esc(n.server)}</td>
    <td>${esc(n.port)}${n.latency_ms != null ? ` · ${n.latency_ms}ms` : ""}</td>
    <td>
      <button class="btn btn-ghost btn-sm" data-node="${esc(n.name)}" ${info ? "disabled title=信息项不可作出口" : ""}>用于新建</button>
      <button class="btn btn-ghost btn-sm" data-fav="${esc(n.name)}">${n.favorite ? "取消收藏" : "收藏"}</button>
    </td>
  </tr>`;
    })
    .join("");
}

export async function loadNodes() {
  const name = document.getElementById("subName")?.value || "default";
  state.nodes = await api("/api/nodes?sub=" + encodeURIComponent(name));
  // fill type filter options dynamically
  const tf = document.getElementById("nodeTypeFilter");
  if (tf) {
    const cur = tf.value;
    const types = [...new Set((state.nodes || []).map((n) => n.type).filter(Boolean))].sort();
    tf.innerHTML =
      '<option value="">全部类型</option>' +
      types.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("");
    if (cur) tf.value = cur;
  }
  renderNodes();
}

export async function deleteSub(name) {
  if (!name) return toast("无订阅名", "err");
  if (!confirm(`确认删除订阅「${name}」？\n将删除 runtime/nodes/subs/${name} 下全部节点文件，不可恢复。`)) return;
  const r = await api("/api/subscriptions/" + encodeURIComponent(name) + "/delete", {
    method: "POST",
    body: "{}",
  });
  toast(`已删除 ${name}` + (r.active ? ` · 当前改为 ${r.active}` : " · 无剩余订阅"));
  const next = r.active || (Array.isArray(r.remaining) && r.remaining[0]) || "";
  const sn = document.getElementById("subName");
  if (sn && sn.value === name) sn.value = next;
  const px = document.getElementById("pxSubName");
  if (px && px.value === name) px.value = next;
  await loadSubs();
  await loadNodes();
}

export async function importSub() {
  const url = document.getElementById("subUrl")?.value.trim();
  const name = document.getElementById("subName")?.value.trim() || "default";
  if (!url) return toast("请填写订阅链接", "err");
  const meta = await api("/api/subscriptions/import", {
    method: "POST",
    body: JSON.stringify({ url, name }),
  });
  const st = meta.stats || {};
  const usable = meta.usable_count ?? st.usable;
  const info = meta.info_count ?? st.info;
  const types = meta.types || st.types || {};
  const typeStr = Object.entries(types).map(([k, v]) => `${k}:${v}`).join(",");
  const skipped = st.parse?.skipped || 0;
  toast(
    `导入 ${meta.node_count || 0} 条（可用 ${usable ?? "?"} · 信息 ${info ?? "?"}）` +
      (typeStr ? ` [${typeStr}]` : "") +
      (skipped ? ` · 跳过 ${skipped}` : "") +
      ` → runtime/nodes/subs/${name}`
  );
  await loadSubs();
  await loadNodes();
}

async function switchSub(name) {
  const r = await api("/api/subscriptions/switch", {
    method: "POST",
    body: JSON.stringify({ name, update_profiles: false }),
  });
  const nameEl = document.getElementById("subName");
  if (nameEl) nameEl.value = r.active || name;
  toast(`已切换当前订阅：${r.active}`);
  await loadSubs();
  await loadNodes();
}

async function exportSub(name, fmt) {
  const r = await api("/api/subscriptions/export", {
    method: "POST",
    body: JSON.stringify({ name, fmt: fmt || "zip" }),
  });
  toast(`导出 ${r.node_count || 0} 节点 → ${r.path}`);
  return r;
}

async function importFile() {
  const fileInput = document.getElementById("subImportFile");
  const file = fileInput?.files?.[0];
  const name = document.getElementById("subImportName")?.value.trim() || "";
  const path = document.getElementById("subImportPath")?.value.trim();

  // Prefer browser file picker upload
  if (file) {
    const fd = new FormData();
    fd.append("file", file, file.name);
    fd.append("name", name || file.name.replace(/\.[^.]+$/, "") || "imported");
    const meta = await api("/api/subscriptions/import-upload", { method: "POST", body: fd });
    toast(`本地导入：${meta.node_count ?? meta.usable_count ?? meta.name ?? name ?? file.name}`);
    const nameEl = document.getElementById("subName");
    if (nameEl) nameEl.value = meta.name || name || file.name;
    const label = document.getElementById("subImportFileLabel");
    if (label) label.textContent = `已导入 ${file.name}`;
    if (fileInput) fileInput.value = "";
    await loadSubs();
    await loadNodes();
    return;
  }

  // Fallback: ROOT-relative path (scripts / advanced)
  if (!path) return toast("请先点「选择文件」挑选本地订阅文件", "err");
  const meta = await api("/api/subscriptions/import-file", {
    method: "POST",
    body: JSON.stringify({ path, name: name || "imported" }),
  });
  toast(`本地导入：${meta.node_count || meta.name || name}`);
  const nameEl = document.getElementById("subName");
  if (nameEl) nameEl.value = meta.name || name;
  await loadSubs();
  await loadNodes();
}

async function refreshCurrent() {
  const name = document.getElementById("subName")?.value.trim() || "default";
  toast("正在更新订阅…");
  const r = await api("/api/subscriptions/refresh?name=" + encodeURIComponent(name), { method: "POST" });
  if (r.ok) toast(`更新成功 ${r.meta?.node_count ?? ""} 节点`);
  else toast(`更新失败，已保留旧表：${r.error || ""}`, "err");
  await loadSubs();
  await loadNodes();
}

async function cfVendor() {
  const r = await api("/api/turnstile/vendor");
  const st = document.getElementById("cfStatus");
  if (st) st.textContent = r.ok ? `vendor OK · ${r.path}` : "vendor missing";
  toast(r.ok ? `CF vendor: ${r.path}` : "turnstile vendor 缺失", r.ok ? undefined : "err");
}

async function cfSolve() {
  const url = document.getElementById("cfUrl")?.value.trim();
  let profileId = document.getElementById("cfProfileId")?.value.trim();
  if (!url) return toast("填写 CF 目标 URL", "err");
  if (!profileId) {
    // pick first profile if any
    try {
      const profiles = await api("/api/profiles");
      const list = Array.isArray(profiles) ? profiles : profiles.items || profiles.profiles || [];
      profileId = list[0]?.id || list[0]?.profile_id || "ephemeral";
    } catch {
      profileId = "ephemeral";
    }
  }
  toast("正在过 CF 盾…");
  const st = document.getElementById("cfStatus");
  if (st) st.textContent = "solving…";
  try {
    const r = await api(`/api/turnstile/profiles/${encodeURIComponent(profileId)}/solve`, {
      method: "POST",
      body: JSON.stringify({ url, headless: true, timeout: 60, harvest: true }),
    });
    const ok = r.ok || r.wait?.ok || r.harvest?.ok;
    if (st) {
      st.textContent = ok
        ? `OK token_len=${r.harvest?.token_len || 0}`
        : `fail ${r.harvest_error || r.wait?.ok === false ? "cf-wait" : ""}`;
      st.className = ok ? "pill ok" : "pill off";
    }
    toast(ok ? `CF 通过 · token ${r.harvest?.token_len || 0}` : `CF 未完全通过`, ok ? undefined : "err");
  } catch (e) {
    if (st) {
      st.textContent = e.message || "error";
      st.className = "pill off";
    }
    throw e;
  }
}

export function bindSubsDom(openCreate, syncProxyFields, updateCreateSummary) {
  document.getElementById("btnImportSub")?.addEventListener("click", () =>
    importSub().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnLoadNodes")?.addEventListener("click", () =>
    loadNodes().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("nodeQ")?.addEventListener("input", () => renderNodes());
  document.getElementById("nodeTypeFilter")?.addEventListener("change", () => renderNodes());
  document.getElementById("nodeShowInfo")?.addEventListener("change", () => renderNodes());
  document.getElementById("btnRefreshSub")?.addEventListener("click", () =>
    refreshCurrent().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnPickImportFile")?.addEventListener("click", () => {
    document.getElementById("subImportFile")?.click();
  });
  document.getElementById("subImportFile")?.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    const label = document.getElementById("subImportFileLabel");
    if (label) label.textContent = f ? f.name : "未选择文件";
    // auto-fill import name from filename if empty / default
    const nameEl = document.getElementById("subImportName");
    if (f && nameEl && !nameEl.value.trim()) {
      nameEl.value = f.name.replace(/\.[^.]+$/, "");
    }
  });
  document.getElementById("btnImportFile")?.addEventListener("click", () =>
    importFile().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnExportSub")?.addEventListener("click", () => {
    const name = document.getElementById("subName")?.value || "default";
    const fmt = document.getElementById("exportFmt")?.value || "zip";
    exportSub(name, fmt).catch((e) => toast(e.message, "err"));
  });
  document.getElementById("btnTurnstileVendor")?.addEventListener("click", () =>
    cfVendor().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnCfSolve")?.addEventListener("click", () =>
    cfSolve().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("subName")?.addEventListener("input", () => {
    const el = document.getElementById("subName");
    if (el) el.dataset.userEdited = "1";
  });

  // sub cards: switch / export / view / delete
  const cards = document.getElementById("subCards");
  if (cards && !cards.dataset.bound) {
    cards.dataset.bound = "1";
    cards.addEventListener("click", async (e) => {
      const sw = e.target.closest("[data-switch]");
      if (sw) {
        try {
          await switchSub(sw.dataset.switch);
        } catch (err) {
          toast(err.message, "err");
        }
        return;
      }
      const ex = e.target.closest("[data-export]");
      if (ex) {
        const fmt = document.getElementById("exportFmt")?.value || "zip";
        exportSub(ex.dataset.export, fmt).catch((err) => toast(err.message, "err"));
        return;
      }
      const use = e.target.closest("[data-use-sub]");
      if (use) {
        const nameEl = document.getElementById("subName");
        if (nameEl) {
          nameEl.value = use.dataset.useSub;
          nameEl.dataset.userEdited = "1";
        }
        loadNodes().catch((err) => toast(err.message, "err"));
        return;
      }
      const del = e.target.closest("[data-del-sub]");
      if (del) {
        deleteSub(del.dataset.delSub).catch((err) => toast(err.message, "err"));
      }
    });
  }

  document.getElementById("btnNodeGroups")?.addEventListener("click", async () => {
    try {
      const sub = document.getElementById("subName")?.value || "default";
      const r = await api("/api/nodes/groups?sub=" + encodeURIComponent(sub));
      const countries = (r.countries || Object.keys(r.groups || {}) || []).join(", ");
      toast(`国家分组: ${countries || "无"}`);
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnSpeedtest")?.addEventListener("click", async () => {
    try {
      const sub = document.getElementById("subName")?.value || "default";
      toast("测速中…");
      const r = await api("/api/nodes/speedtest", {
        method: "POST",
        body: JSON.stringify({ sub, limit: 30 }),
      });
      toast(`测速完成 ${r.count || 0} 节点`);
      await loadNodes();
    } catch (e) {
      toast(e.message, "err");
    }
  });

  const body = document.getElementById("nodeBody");
  if (body && !body.dataset.bound) {
    body.dataset.bound = "1";
    body.addEventListener("click", async (e) => {
      const favBtn = e.target.closest("[data-fav]");
      if (favBtn) {
        const name = favBtn.dataset.fav;
        const sub = document.getElementById("subName")?.value || "default";
        try {
          const nodes = state.nodes || [];
          const cur = nodes.find((x) => x.name === name);
          if (cur?.favorite) {
            await api(
              `/api/nodes/favorites?sub=${encodeURIComponent(sub)}&node_name=${encodeURIComponent(name)}`,
              { method: "DELETE" }
            );
            toast("已取消收藏");
          } else {
            await api("/api/nodes/favorites", {
              method: "POST",
              body: JSON.stringify({ sub, node_name: name }),
            });
            toast("已收藏 " + name);
          }
          await loadNodes();
        } catch (err) {
          toast(err.message, "err");
        }
        return;
      }
      const btn = e.target.closest("[data-node]");
      if (!btn) return;
      const name = btn.dataset.node;
      const sub = document.getElementById("subName")?.value || "default";
      // open create modal with mihomo + subscription + node dropdown preselected
      openCreate({ mode: "mihomo", sub, node: name });
      const remark = document.getElementById("c_remark");
      if (remark && !remark.value) remark.value = "node=" + name;
      const auto = document.getElementById("c_auto_port");
      if (auto) auto.checked = true;
    });
  }
}
