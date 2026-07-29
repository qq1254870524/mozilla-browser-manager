/** SOCKS5 proxy library + profile binding inventory. */
import { api, esc } from "../core/api.js";
import { toast } from "../core/toast.js";
import { state } from "../core/state.js";

let tab = "library"; // library | nodes | bindings
let selectedProxyIds = new Set();

function maskPass(s) {
  const t = String(s || "");
  if (!t) return "";
  if (t.length <= 2) return "**";
  return t.slice(0, 1) + "***" + t.slice(-1);
}

export async function loadProxies() {
  const [combined, lib] = await Promise.all([
    api("/api/proxies"),
    api("/api/proxies/socks5").catch(() => ({ items: [] })),
  ]);
  state.proxies = combined || [];
  state.socks5Lib = lib.items || [];
  renderProxies();
  fillCreateLibSelect();
}

export function fillCreateLibSelect() {
  const sel = document.getElementById("c_socks5_lib");
  if (!sel) return;
  const cur = sel.value;
  const items = state.socks5Lib || [];
  sel.innerHTML =
    '<option value="">— 手动填写 / 不选用 —</option>' +
    items
      .map(
        (it) =>
          `<option value="${esc(it.id)}" data-socks5="${esc(it.socks5 || "")}" data-host="${esc(it.host || "")}" data-port="${esc(it.port || "")}" data-user="${esc(it.username || "")}" data-pass="${esc(it.password || "")}" data-refresh="${esc(it.refresh_url || "")}">${esc(it.name || it.host)} · ${esc(it.host)}:${esc(it.port)}</option>`
      )
      .join("");
  if (cur) sel.value = cur;
}

function formValues() {
  return {
    name: document.getElementById("px_name")?.value.trim() || "",
    host: document.getElementById("px_host")?.value.trim() || "",
    port: Number(document.getElementById("px_port")?.value || 0),
    username: document.getElementById("px_user")?.value.trim() || "",
    password: document.getElementById("px_pass")?.value || "",
    refresh_url: document.getElementById("px_refresh")?.value.trim() || "",
    remark: document.getElementById("px_remark")?.value.trim() || "",
  };
}

function clearForm() {
  ["px_name", "px_host", "px_port", "px_user", "px_pass", "px_refresh", "px_remark"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = id === "px_port" ? "1080" : "";
  });
  const hid = document.getElementById("px_edit_id");
  if (hid) hid.value = "";
  const btn = document.getElementById("btnPxSave");
  if (btn) btn.textContent = "添加代理";
}

function fillForm(it) {
  const map = {
    px_edit_id: it.id || "",
    px_name: it.name || "",
    px_host: it.host || "",
    px_port: it.port || "",
    px_user: it.username || "",
    px_pass: it.password || "",
    px_refresh: it.refresh_url || "",
    px_remark: it.remark || "",
  };
  Object.entries(map).forEach(([id, v]) => {
    const el = document.getElementById(id);
    if (el) el.value = v;
  });
  const btn = document.getElementById("btnPxSave");
  if (btn) btn.textContent = "保存修改";
}

function isInfoNode(n) {
  if (n?.info === true) return true;
  const name = String(n?.name || "");
  const keys = ["剩余流量", "套餐到期", "距离下次", "过期", "到期时间", "流量：", "重置剩余"];
  if (keys.some((k) => name.includes(k))) return true;
  const server = String(n?.server || "");
  if ((server === "127.0.0.1" || server === "localhost") && /流量|到期|重置|剩余/.test(name)) return true;
  return false;
}

export async function loadProxyNodes() {
  const name = document.getElementById("pxSubName")?.value || document.getElementById("subName")?.value || "default";
  // sync name fields
  const sn = document.getElementById("subName");
  if (sn && document.getElementById("pxSubName")?.value) sn.value = document.getElementById("pxSubName").value;
  let active = {};
  try {
    active = await api("/api/subscriptions/active");
  } catch (_) {}
  const pill = document.getElementById("pxActiveSubPill");
  if (pill) pill.textContent = `active: ${active.active || "—"} · ${active.meta?.node_count ?? "?"}节点`;

  state.subs = await api("/api/subscriptions").catch(() => state.subs || []);
  const box = document.getElementById("pxSubCards");
  if (box) {
    const act = active.active;
    box.innerHTML =
      (state.subs || [])
        .map((s) => {
          const isActive = s.active || s.name === act;
          return `<div class="card stat" style="${isActive ? "outline:2px solid #93c5fd" : ""}">
      <div class="l">订阅 ${esc(s.name)} ${isActive ? '<span class="pill run">当前</span>' : ""}</div>
      <div class="n">${s.node_count ?? "-"}</div>
      <div class="l">${esc(s.url_host || s.source || "")}</div>
      <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn btn-primary btn-sm" data-px-switch="${esc(s.name)}" ${isActive ? "disabled" : ""}>切换</button>
        <button class="btn btn-ghost btn-sm" data-px-view="${esc(s.name)}">查看</button>
        <button class="btn btn-danger btn-sm" data-del-sub="${esc(s.name)}">删除</button>
      </div>
    </div>`;
        })
        .join("") || `<div class="empty">暂无订阅，请导入</div>`;
  }

  state.nodes = await api("/api/nodes?sub=" + encodeURIComponent(name));
  const tf = document.getElementById("pxNodeType");
  if (tf) {
    const cur = tf.value;
    const types = [...new Set((state.nodes || []).map((n) => n.type).filter(Boolean))].sort();
    tf.innerHTML = '<option value="">全部类型</option>' + types.map((x) => `<option value="${esc(x)}">${esc(x)}</option>`).join("");
    if (cur) tf.value = cur;
  }
  renderProxyNodes();
}

export function renderProxyNodes() {
  const body = document.getElementById("pxNodeBody");
  if (!body) return;
  const q = (document.getElementById("pxNodeQ")?.value || "").toLowerCase();
  const typ = (document.getElementById("pxNodeType")?.value || "").toLowerCase();
  const all = state.nodes || [];
  const rows = all.filter((n) => {
    if (isInfoNode(n)) return false;
    if (typ && String(n.type || "").toLowerCase() !== typ) return false;
    if (!q) return true;
    return `${n.name} ${n.server} ${n.country} ${n.type}`.toLowerCase().includes(q);
  });
  const bar = document.getElementById("pxNodeCount");
  if (bar) bar.textContent = `显示 ${rows.length} / 全部 ${all.length} · 可用 ${all.filter((n) => !isInfoNode(n)).length}`;
  body.innerHTML =
    rows
      .map(
        (n, i) => `<tr>
      <td class="mono">${i + 1}</td>
      <td>${esc(n.name)}${n.favorite ? " ★" : ""}</td>
      <td><span class="pill">${esc(n.type)}</span></td>
      <td>${n.country ? `<span class="pill">${esc(n.country)}</span>` : "—"}</td>
      <td class="mono">${esc(n.server)}</td>
      <td>
        <button class="btn btn-primary btn-sm" data-px-use-node="${esc(n.name)}">用于新建</button>
      </td>
    </tr>`
      )
      .join("") || `<tr><td colspan="6"><div class="empty">无节点</div></td></tr>`;
}

export function renderProxies() {
  const body = document.getElementById("proxyBody");
  const count = document.getElementById("proxyCount");

  // tab buttons
  document.querySelectorAll("#proxyTabs .tab").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === tab);
  });
  const libPane = document.getElementById("proxyLibPane");
  const nodesPane = document.getElementById("proxyNodesPane");
  const tablePane = document.getElementById("proxyTablePane");
  if (libPane) libPane.style.display = tab === "library" ? "" : "none";
  if (nodesPane) nodesPane.style.display = tab === "nodes" ? "" : "none";
  if (tablePane) tablePane.style.display = tab === "nodes" ? "none" : "";

  if (tab === "nodes") {
    loadProxyNodes().catch((e) => toast(e.message, "err"));
    return;
  }

  if (!body) return;

  if (tab === "library") {
    const items = state.socks5Lib || [];
    if (count) count.textContent = `SOCKS5 库 ${items.length}`;
    if (!items.length) {
      body.innerHTML = `<tr><td colspan="9"><div class="empty">暂无 SOCKS5 代理，上方表单添加或批量导入</div></td></tr>`;
      return;
    }
    body.innerHTML = items
      .map((it, i) => {
        const checked = selectedProxyIds.has(it.id) ? "checked" : "";
        const refOk =
          it.last_refresh_ok === true
            ? '<span class="pill run">刷新OK</span>'
            : it.last_refresh_ok === false
              ? '<span class="pill off">刷新失败</span>'
              : "";
        return `<tr>
          <td><input type="checkbox" class="px-sel" data-id="${esc(it.id)}" ${checked} /></td>
          <td class="mono">${i + 1}</td>
          <td><b>${esc(it.name || "")}</b><div class="mono" style="color:#94a3b8">${esc(it.id)}</div></td>
          <td class="mono">${esc(it.host)}:${esc(it.port)}</td>
          <td class="mono">${esc(it.username || "-")}</td>
          <td class="mono" title="${esc(it.password || "")}">${esc(maskPass(it.password))}</td>
          <td class="mono" title="${esc(it.refresh_url || "")}">${it.refresh_url ? esc(String(it.refresh_url).slice(0, 40)) + (String(it.refresh_url).length > 40 ? "…" : "") : "—"} ${refOk}</td>
          <td>${esc(it.remark || "")}</td>
          <td class="actions">
            <button class="btn btn-primary btn-sm" data-px="use" data-id="${esc(it.id)}">选用</button>
            <button class="btn btn-ghost btn-sm" data-px="refresh" data-id="${esc(it.id)}" ${it.refresh_url ? "" : "disabled"}>刷新IP</button>
            <button class="btn btn-ghost btn-sm" data-px="edit" data-id="${esc(it.id)}">编辑</button>
            <button class="btn btn-danger btn-sm" data-px="del" data-id="${esc(it.id)}">删除</button>
          </td>
        </tr>`;
      })
      .join("");
  } else {
    const items = (state.proxies || []).filter((x) => x.source === "binding" || x.source === "library");
    if (count) count.textContent = `绑定视图 ${items.length}`;
    if (!items.length) {
      body.innerHTML = `<tr><td colspan="9"><div class="empty">暂无代理绑定</div></td></tr>`;
      return;
    }
    body.innerHTML = items
      .map((it, i) => {
        const profs = (it.profiles || []).slice(0, 6).map((x) => esc(x)).join(", ");
        const more = (it.profiles || []).length > 6 ? "…" : "";
        return `<tr>
          <td></td>
          <td class="mono">${i + 1}</td>
          <td><b>${esc(it.info || it.name || it.id)}</b><div class="mono" style="color:#94a3b8">${esc(it.source || "")} · ${esc(it.id)}</div></td>
          <td class="mono" colspan="2">${esc(it.mode || "")}</td>
          <td class="mono" colspan="2">${esc(it.socks5 || it.node_name || "—")}</td>
          <td>${it.count || 0}</td>
          <td class="mono">${profs}${more}</td>
        </tr>`;
      })
      .join("");
  }

  const all = document.getElementById("pxChkAll");
  if (all && tab === "library") {
    const boxes = [...document.querySelectorAll("#proxyBody .px-sel")];
    const n = boxes.filter((b) => b.checked).length;
    all.checked = boxes.length > 0 && n === boxes.length;
    all.indeterminate = n > 0 && n < boxes.length;
  }
}

async function saveProxy() {
  const editId = document.getElementById("px_edit_id")?.value || "";
  const payload = formValues();
  if (!payload.host || !payload.port) return toast("请填写主机和端口", "err");
  if (editId) {
    await api("/api/proxies/socks5/" + encodeURIComponent(editId), {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    toast("已更新");
  } else {
    await api("/api/proxies/socks5", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    toast("已添加");
  }
  clearForm();
  await loadProxies();
}

async function batchImport() {
  const text = document.getElementById("px_batch")?.value || "";
  if (!text.trim()) return toast("粘贴批量内容", "err");
  const r = await api("/api/proxies/socks5/batch", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  const errN = (r.errors || []).length;
  toast(`批量完成 +${r.added || 0} 更新${r.updated || 0}${errN ? " 错误" + errN : ""}`, errN ? "err" : undefined);
  if (r.errors?.length) console.warn("proxy batch errors", r.errors);
  document.getElementById("px_batch").value = "";
  await loadProxies();
}

async function deleteOne(id) {
  if (!confirm("删除该 SOCKS5 代理？")) return;
  await api("/api/proxies/socks5/" + encodeURIComponent(id), { method: "DELETE" });
  selectedProxyIds.delete(id);
  toast("已删除");
  await loadProxies();
}

async function deleteSelected() {
  const ids = [...selectedProxyIds];
  if (!ids.length) return toast("未选择", "err");
  if (!confirm(`删除选中 ${ids.length} 条？`)) return;
  await api("/api/proxies/socks5/delete-batch", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
  selectedProxyIds.clear();
  toast("批量删除完成");
  await loadProxies();
}

async function refreshIp(id) {
  toast("刷新 IP…");
  const r = await api(`/api/proxies/socks5/${encodeURIComponent(id)}/refresh-ip`, { method: "POST" });
  toast(r.ok ? "刷新成功" : r.error || r.detail?.error || "刷新失败", r.ok ? undefined : "err");
  await loadProxies();
}

function useInCreate(id) {
  const it = (state.socks5Lib || []).find((x) => x.id === id);
  if (!it) return toast("未找到", "err");
  window.MM?.switchView?.("profiles");
  window.MMOpenCreate?.();
  // wait modal paint
  setTimeout(() => {
    const modeBtn = document.querySelector('#c_proxy_mode button[data-v="socks5"]');
    if (modeBtn) window.MMSeg?.(modeBtn);
    // trigger sync
    document.querySelectorAll("#c_proxy_mode button").forEach((b) => b.classList.toggle("on", b.dataset.v === "socks5"));
    import("./create_modal.js").then((m) => {
      m.syncProxyFields();
      const sel = document.getElementById("c_socks5_lib");
      if (sel) {
        sel.value = id;
        sel.dispatchEvent(new Event("change"));
      } else {
        applySocksFields(it);
      }
      m.updateCreateSummary();
    });
  }, 50);
  toast("已填入新建环境: " + (it.name || it.host));
}

function applySocksFields(it) {
  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.value = v ?? "";
  };
  set("c_socks_host", it.host || "");
  set("c_socks_port", it.port || "");
  set("c_socks_user", it.username || "");
  set("c_socks_pass", it.password || "");
  set("c_socks_refresh", it.refresh_url || "");
  // keep legacy url field if present
  set("c_socks5", it.socks5 || "");
}

export function bindProxiesDom() {
  document.querySelectorAll("#proxyTabs .tab").forEach((t) => {
    t.addEventListener("click", () => {
      tab = t.dataset.tab || "library";
      renderProxies();
    });
  });

  document.getElementById("btnPxSave")?.addEventListener("click", () =>
    saveProxy().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnPxClear")?.addEventListener("click", clearForm);
  document.getElementById("btnPxBatch")?.addEventListener("click", () =>
    batchImport().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnPxReload")?.addEventListener("click", () =>
    loadProxies().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnPxDelSel")?.addEventListener("click", () =>
    deleteSelected().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnGoSubs")?.addEventListener("click", () => window.MM?.switchView?.("subs"));
  document.getElementById("btnOpenFullSubs")?.addEventListener("click", () => window.MM?.switchView?.("subs"));

  document.getElementById("btnPxImportSub")?.addEventListener("click", async () => {
    try {
      const url = document.getElementById("pxSubUrl")?.value.trim() || document.getElementById("subUrl")?.value.trim();
      const name = document.getElementById("pxSubName")?.value.trim() || "default";
      if (!url) return toast("请填写订阅链接", "err");
      // mirror into main sub fields
      const u = document.getElementById("subUrl"); if (u) u.value = url;
      const n = document.getElementById("subName"); if (n) n.value = name;
      const meta = await api("/api/subscriptions/import", { method: "POST", body: JSON.stringify({ url, name }) });
      toast(`导入 ${meta.node_count || 0} 节点（可用 ${meta.usable_count ?? "?"}）`);
      await loadProxyNodes();
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnPxRefreshSub")?.addEventListener("click", async () => {
    try {
      const name = document.getElementById("pxSubName")?.value.trim() || "default";
      const r = await api("/api/subscriptions/refresh?name=" + encodeURIComponent(name), { method: "POST" });
      toast(`已更新 ${r.meta?.node_count ?? r.node_count ?? ""}`);
      await loadProxyNodes();
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnPxLoadNodes")?.addEventListener("click", () =>
    loadProxyNodes().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("pxNodeQ")?.addEventListener("input", () => renderProxyNodes());
  document.getElementById("pxNodeType")?.addEventListener("change", () => renderProxyNodes());

  document.getElementById("pxSubCards")?.addEventListener("click", async (e) => {
    const sw = e.target.closest("[data-px-switch]");
    const view = e.target.closest("[data-px-view]");
    const del = e.target.closest("[data-del-sub]");
    try {
      if (sw) {
        const name = sw.dataset.pxSwitch;
        await api("/api/subscriptions/switch", { method: "POST", body: JSON.stringify({ name }) });
        const el = document.getElementById("pxSubName"); if (el) el.value = name;
        const sn = document.getElementById("subName"); if (sn) sn.value = name;
        toast("已切换 " + name);
        await loadProxyNodes();
      } else if (view) {
        const name = view.dataset.pxView;
        const el = document.getElementById("pxSubName"); if (el) el.value = name;
        await loadProxyNodes();
      } else if (del) {
        const name = del.dataset.delSub;
        if (!confirm(`删除订阅「${name}」？将移除 runtime/nodes/subs/${name} 全部节点文件`)) return;
        await api("/api/subscriptions/" + encodeURIComponent(name) + "/delete", { method: "POST", body: "{}" });
        toast("已删除订阅 " + name);
        await loadProxyNodes();
      }
    } catch (err) {
      toast(err.message || String(err), "err");
    }
  });

  document.getElementById("pxNodeBody")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-px-use-node]");
    if (!btn) return;
    const name = btn.dataset.pxUseNode;
    const sub = document.getElementById("pxSubName")?.value || "default";
    window.MMOpenCreate?.({ mode: "mihomo", sub, node: name });
  });

  document.getElementById("pxChkAll")?.addEventListener("change", (e) => {
    const on = !!e.target.checked;
    (state.socks5Lib || []).forEach((it) => {
      if (on) selectedProxyIds.add(it.id);
      else selectedProxyIds.delete(it.id);
    });
    renderProxies();
  });

  document.getElementById("proxyBody")?.addEventListener("change", (e) => {
    const t = e.target;
    if (t.classList?.contains("px-sel")) {
      if (t.checked) selectedProxyIds.add(t.dataset.id);
      else selectedProxyIds.delete(t.dataset.id);
      const all = document.getElementById("pxChkAll");
      const boxes = [...document.querySelectorAll("#proxyBody .px-sel")];
      const n = boxes.filter((b) => b.checked).length;
      if (all) {
        all.checked = boxes.length > 0 && n === boxes.length;
        all.indeterminate = n > 0 && n < boxes.length;
      }
    }
  });

  document.getElementById("proxyBody")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-px]");
    if (!btn) return;
    const id = btn.dataset.id;
    const act = btn.dataset.px;
    const run = async () => {
      if (act === "del") await deleteOne(id);
      else if (act === "refresh") await refreshIp(id);
      else if (act === "edit") {
        const it = (state.socks5Lib || []).find((x) => x.id === id);
        if (it) {
          fillForm(it);
          document.getElementById("px_host")?.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      } else if (act === "use") useInCreate(id);
    };
    run().catch((err) => toast(err.message || String(err), "err"));
  });
}

// expose apply for create modal
window.MMApplySocks = applySocksFields;
