/** v7/v8 toolbox UI */
import { api, esc } from "../core/api.js";
import { toast } from "../core/toast.js";

function msg(t) {
  const el = document.getElementById("toolsMsg");
  if (el) el.textContent = t;
}

export function bindToolsDom() {
  document.getElementById("btnBatchCreate")?.addEventListener("click", async () => {
    try {
      const body = {
        country: document.getElementById("batchCountry")?.value || "JP",
        count: Number(document.getElementById("batchCount")?.value || 3),
        name_prefix: document.getElementById("batchPrefix")?.value || "",
      };
      toast("批量创建中…");
      const r = await api("/api/batch/create", { method: "POST", body: JSON.stringify(body) });
      msg(`创建 ${r.created?.length || 0} / 请求 ${r.requested}`);
      toast(`批量完成 ${r.created?.length || 0}`);
    } catch (e) {
      toast(e.message, "err");
    }
  });

  document.getElementById("btnTotpAdd")?.addEventListener("click", async () => {
    try {
      const name = document.getElementById("totpName")?.value || "account";
      const secret = document.getElementById("totpSecret")?.value || "";
      const body = secret.startsWith("otpauth://") ? { name, otpauth: secret } : { name, secret };
      const r = await api("/api/totp/accounts", { method: "POST", body: JSON.stringify(body) });
      toast(`2FA 已添加 code=${r.code}`);
      await loadTotp();
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnTotpList")?.addEventListener("click", () => loadTotp().catch((e) => toast(e.message, "err")));

  document.getElementById("btnDiagnose")?.addEventListener("click", async () => {
    try {
      const id = document.getElementById("diagProfile")?.value.trim();
      if (!id) return toast("填写 profile_id", "err");
      toast("诊断中…");
      const r = await api(`/api/diagnose/profiles/${encodeURIComponent(id)}`, { method: "POST" });
      document.getElementById("diagOut").textContent = JSON.stringify(r.summary || r, null, 2);
      toast(r.ok ? "诊断通过" : "诊断有问题", r.ok ? undefined : "err");
    } catch (e) {
      toast(e.message, "err");
    }
  });

  document.getElementById("btnMigExport")?.addEventListener("click", async () => {
    try {
      const id = document.getElementById("migProfile")?.value.trim();
      if (!id) return toast("填写 profile_id", "err");
      const r = await api(`/api/transfer/profiles/${encodeURIComponent(id)}/export`, { method: "POST" });
      msg(`迁移包: ${r.path} (${r.bytes} bytes)`);
      toast("导出成功");
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnMigImport")?.addEventListener("click", async () => {
    try {
      const path = document.getElementById("migPath")?.value.trim();
      if (!path) return toast("填写 zip 路径", "err");
      const r = await api("/api/transfer/import", { method: "POST", body: JSON.stringify({ path }) });
      msg(`导入新环境 ${r.new_id} ← ${r.old_id}`);
      toast("导入成功");
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnCountries")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/templates/packs");
      const n = Array.isArray(r) ? r.length : r.count || 0;
      msg(`国家模板 ${n}`);
      toast(`国家模板 ${n}`);
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnVirtMedia")?.addEventListener("click", async () => {
    try {
      const id =
        document.getElementById("migProfile")?.value.trim() ||
        document.getElementById("diagProfile")?.value.trim();
      if (!id) return toast("填写 profile_id", "err");
      const r = await api(`/api/media/profiles/${encodeURIComponent(id)}`, {
        method: "POST",
        body: JSON.stringify({ enable: true, camera: true, mic: true }),
      });
      msg(`虚拟媒体已开启 ${r.profile_id}`);
      toast("虚拟摄像/麦克风已开启");
    } catch (e) {
      toast(e.message, "err");
    }
  });

  document.getElementById("btnRpaSaveDemo")?.addEventListener("click", async () => {
    try {
      const name = document.getElementById("rpaName")?.value || "demo-check";
      const profile_id = document.getElementById("rpaProfile")?.value.trim() || null;
      const body = {
        id: name,
        name,
        profile_id,
        steps: [
          { action: "goto", url: "https://example.com" },
          { action: "screenshot", name: "t.png" },
        ],
      };
      const r = await api("/api/rpa/workflows", { method: "POST", body: JSON.stringify(body) });
      document.getElementById("rpaOut").textContent = JSON.stringify(r, null, 2);
      toast("工作流已保存");
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnRpaList")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/rpa/workflows");
      document.getElementById("rpaOut").textContent = JSON.stringify(r, null, 2);
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnRpaRun")?.addEventListener("click", async () => {
    try {
      const name = document.getElementById("rpaName")?.value || "demo-check";
      const profile_id = document.getElementById("rpaProfile")?.value.trim() || null;
      const r = await api(`/api/rpa/workflows/${encodeURIComponent(name)}/run`, {
        method: "POST",
        body: JSON.stringify({ profile_id, dry_run: true }),
      });
      document.getElementById("rpaOut").textContent = JSON.stringify(r, null, 2);
      toast("dry-run ok");
    } catch (e) {
      toast(e.message, "err");
    }
  });

  // v8 recorder
  document.getElementById("btnRecStart")?.addEventListener("click", async () => {
    try {
      const id = document.getElementById("rpaProfile")?.value.trim();
      if (!id) return toast("填写 profile_id 且浏览器需运行中", "err");
      const r = await api(`/api/recorder/profiles/${encodeURIComponent(id)}/start`, { method: "POST" });
      document.getElementById("rpaOut").textContent = JSON.stringify(r, null, 2);
      toast("录制已开始 — 在浏览器里操作");
      if (window.__mmRecTimer) clearInterval(window.__mmRecTimer);
      window.__mmRecTimer = setInterval(async () => {
        try {
          const p = await api(`/api/recorder/profiles/${encodeURIComponent(id)}/poll`, { method: "POST" });
          document.getElementById("rpaOut").textContent = JSON.stringify(
            { count: p.count, events: (p.events || []).slice(-12) },
            null,
            2
          );
        } catch (_) {}
      }, 2000);
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnRecStop")?.addEventListener("click", async () => {
    try {
      const id = document.getElementById("rpaProfile")?.value.trim();
      if (!id) return toast("填写 profile_id", "err");
      if (window.__mmRecTimer) clearInterval(window.__mmRecTimer);
      const name = document.getElementById("rpaName")?.value || "";
      const r = await api(`/api/recorder/profiles/${encodeURIComponent(id)}/stop`, {
        method: "POST",
        body: JSON.stringify({ save_workflow: true, name }),
      });
      document.getElementById("rpaOut").textContent = JSON.stringify(r, null, 2);
      toast(`录制结束 steps=${(r.steps || []).length} wf=${r.workflow?.id || "-"}`);
    } catch (e) {
      toast(e.message, "err");
    }
  });

  document.getElementById("btnDash")?.addEventListener("click", () => loadDash().catch((e) => toast(e.message, "err")));
  document.getElementById("btnHistory")?.addEventListener("click", () => loadHistory().catch((e) => toast(e.message, "err")));
  document.getElementById("btnJobs")?.addEventListener("click", () => loadJobs().catch((e) => toast(e.message, "err")));
  document.getElementById("btnBulkDiagAll")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/ops/bulk-diagnose", {
        method: "POST",
        body: JSON.stringify({ profile_ids: [], samples: 3, async_job: true }),
      });
      msg(`全量诊断任务 ${r.id}`);
      toast("已提交 bulk-diagnose job");
    } catch (e) {
      toast(e.message, "err");
    }
  });

  // v9 notify / watchdog / audit / timeline
  document.getElementById("btnNotify")?.addEventListener("click", () => loadNotify().catch((e) => toast(e.message, "err")));
  document.getElementById("btnNotifyRead")?.addEventListener("click", async () => {
    try {
      await api("/api/notify/read", { method: "POST", body: JSON.stringify({ all: true }) });
      toast("通知已全部已读");
      await loadNotify();
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnWdAdd")?.addEventListener("click", async () => {
    try {
      const profile_id = document.getElementById("wdProfile")?.value.trim();
      if (!profile_id) return toast("填写 profile_id", "err");
      const kind = document.getElementById("wdKind")?.value || "login_check";
      const every = Number(document.getElementById("wdEvery")?.value || 60);
      const body = {
        kind,
        profile_id,
        every_minutes: every,
        enabled: true,
        params: kind === "diagnose" ? { auto_failover: true, samples: 2 } : { headless: true },
      };
      const r = await api("/api/watchdogs", { method: "POST", body: JSON.stringify(body) });
      msg(`巡检已添加 ${r.id} ${r.kind}`);
      toast("watchdog 已保存");
      await loadWd();
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnWdList")?.addEventListener("click", () => loadWd().catch((e) => toast(e.message, "err")));
  document.getElementById("btnWdTick")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/watchdogs/tick", { method: "POST" });
      document.getElementById("opsOut").textContent = JSON.stringify(r, null, 2);
      toast(`tick ran ${(r.ran || []).length}`);
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnAudit")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/audit?limit=30");
      document.getElementById("opsOut").textContent = JSON.stringify(r, null, 2);
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnTimeline")?.addEventListener("click", async () => {
    try {
      const id = document.getElementById("rpaProfile")?.value.trim();
      if (!id) return toast("填写 profile_id", "err");
      const r = await api(`/api/recorder/profiles/${encodeURIComponent(id)}/timeline`);
      document.getElementById("rpaOut").textContent = JSON.stringify(r, null, 2);
      toast(`时间线 events=${r.events} steps=${(r.steps||[]).length}`);
    } catch (e) {
      toast(e.message, "err");
    }
  });

  // v10 fleet / report / backup / vault / ws
  document.getElementById("btnFleetExport")?.addEventListener("click", async () => {
    try {
      toast("Fleet 导出中…");
      const r = await api("/api/fleet/export", { method: "POST", body: JSON.stringify({}) });
      msg(`Fleet: ${r.path} (${r.bytes} bytes)`);
      document.getElementById("opsOut").textContent = JSON.stringify(r.manifest || r, null, 2);
      toast("Fleet 导出完成");
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnFleetList")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/fleet/packs");
      document.getElementById("opsOut").textContent = JSON.stringify(r, null, 2);
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnFleetImport")?.addEventListener("click", async () => {
    try {
      const path = document.getElementById("fleetImportPath")?.value.trim();
      if (!path) return toast("填写 fleet zip 路径", "err");
      const r = await api("/api/fleet/import", { method: "POST", body: JSON.stringify({ path }) });
      document.getElementById("opsOut").textContent = JSON.stringify(r, null, 2);
      toast(r.ok ? "导入完成" : "导入有错误", r.ok ? undefined : "err");
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnReport")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/reports/ops", { method: "POST" });
      msg(`报表 ${r.html}`);
      document.getElementById("opsOut").textContent = JSON.stringify(r, null, 2);
      toast("报表已生成");
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnBackup")?.addEventListener("click", async () => {
    try {
      toast("备份中…");
      const r = await api("/api/backup", { method: "POST", body: JSON.stringify({ label: "ui" }) });
      msg(`备份 ${r.path}`);
      document.getElementById("opsOut").textContent = JSON.stringify(r, null, 2);
      toast("备份完成");
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnVaultList")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/vault");
      document.getElementById("opsOut").textContent = JSON.stringify(r, null, 2);
    } catch (e) {
      toast(e.message, "err");
    }
  });
  document.getElementById("btnVaultPut")?.addEventListener("click", async () => {
    try {
      const name = document.getElementById("vaultName")?.value.trim();
      const value = document.getElementById("vaultValue")?.value || "";
      if (!name || !value) return toast("填写密钥名和值", "err");
      const r = await api("/api/vault", { method: "POST", body: JSON.stringify({ name, value }) });
      toast("已存入保险库 " + r.name);
      document.getElementById("vaultValue").value = "";
    } catch (e) {
      toast(e.message, "err");
    }
  });

  // job progress websocket
  try {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/jobs`);
    const el = document.getElementById("wsJobsStatus");
    ws.onopen = () => { if (el) el.textContent = "WS:on"; };
    ws.onclose = () => { if (el) el.textContent = "WS:off"; };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "jobs" && el) {
          const run = (data.items || []).filter((x) => x.status === "running").length;
          el.textContent = `WS:jobs running=${run}`;
        }
      } catch (_) {}
    };
    window.__mmJobsWS = ws;
  } catch (_) {}
}

async function loadNotify() {
  const r = await api("/api/notify?limit=30");
  const el = document.getElementById("opsOut");
  if (el) el.textContent = JSON.stringify(r, null, 2);
  msg(`通知未读 ${r.unread}`);
  const b = document.getElementById("notifyBadge");
  if (b) b.textContent = r.unread ? `通知 ${r.unread}` : "通知";
}

async function loadWd() {
  const r = await api("/api/watchdogs");
  const st = await api("/api/watchdogs/status");
  const el = document.getElementById("opsOut");
  if (el) el.textContent = JSON.stringify({ status: st, items: r }, null, 2);
}

async function loadTotp() {
  const r = await api("/api/totp/accounts");
  const el = document.getElementById("totpOut");
  if (el) el.textContent = JSON.stringify(r, null, 2);
}

async function loadDash() {
  const r = await api("/api/ops/dashboard");
  const el = document.getElementById("opsOut");
  if (el) el.textContent = JSON.stringify(r, null, 2);
  msg(`仪表盘 环境${r.profiles} 运行${r.running}`);
}

async function loadHistory() {
  const r = await api("/api/ops/history?limit=20");
  const el = document.getElementById("opsOut");
  if (el) el.textContent = JSON.stringify(r, null, 2);
}

async function loadJobs() {
  const r = await api("/api/jobs?limit=20");
  const el = document.getElementById("opsOut");
  if (el) el.textContent = JSON.stringify(r, null, 2);
}
