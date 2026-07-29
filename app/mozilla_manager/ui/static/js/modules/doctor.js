/** Doctor + mihomo status + v6 stealth panel. */
import { api, esc } from "../core/api.js";
import { toast } from "../core/toast.js";

export async function loadDoctor() {
  const report = await api("/api/doctor");
  const body = document.getElementById("doctorBody");
  if (body) {
    body.innerHTML = (report.checks || [])
      .map((c) => {
        const ok = c.ok;
        const level = c.level || (ok ? "ok" : "warn");
        const pill = ok
          ? '<span class="pill ok">OK</span>'
          : `<span class="pill">${esc(String(level).toUpperCase())}</span>`;
        return `<tr><td>${pill}</td><td>${esc(c.name)}</td><td class="mono">${esc(c.detail)}</td></tr>`;
      })
      .join("");
  }
  const badge = document.getElementById("healthBadge");
  if (badge) {
    badge.textContent = report.ok ? "Doctor PASS" : "Doctor 有警告";
    badge.style.background = report.ok ? "#ecfdf5" : "#fff7ed";
    badge.style.color = report.ok ? "#047857" : "#c2410c";
  }
  const st = await api("/api/mihomo/status");
  const cards = document.getElementById("mihomoCards");
  if (cards) {
    cards.innerHTML = `<div class="card stat"><div class="l">mihomo 实例</div><div class="n">${st.length}</div><div class="l mono">${esc(
      JSON.stringify(st)
    )}</div></div>`;
  }
  return report;
}

async function showEntropy() {
  const r = await api("/api/stealth/entropy");
  const box = document.getElementById("stealthPanel");
  if (box) {
    box.innerHTML = `<div class="card stat"><div class="l">v6 指纹熵</div><div class="n">${esc(
      String(r.entropy_bits)
    )} bit</div><div class="l">core ${esc(String(r.core_entropy_bits))} · dims ${esc(
      String(r.dimension_count)
    )} · ≥138 ${r.meets_138 ? "✓" : "✗"}</div></div>`;
  }
  toast(`熵值 ${r.entropy_bits} bit`);
}

async function showCollision() {
  toast("计算碰撞率…");
  const r = await api("/api/stealth/collision?limit=20");
  const box = document.getElementById("stealthPanel");
  if (box) {
    box.innerHTML = `<div class="card stat"><div class="l">核心维碰撞率</div><div class="n">${esc(
      String(r.rate_pct)
    )}%</div><div class="l">n=${r.n} pairs=${r.pairs} coll=${r.collisions} · ≤0.004% ${
      r.meets_0_004pct ? "✓" : "✗"
    }</div></div>`;
  }
  toast(`碰撞率 ${r.rate_pct}%`);
}

async function showTls() {
  const list = await api("/api/stealth/tls-profiles");
  const box = document.getElementById("stealthPanel");
  if (box) {
    box.innerHTML = (list || [])
      .map(
        (t) => `<div class="card stat"><div class="l">${esc(t.id)}</div><div class="n" style="font-size:16px">${esc(
          t.browser
        )}</div><div class="l mono">JA3 ${esc(t.ja3_label || "")}<br>JA4 ${esc(t.ja4_label || "")}<br>mihomo ${esc(
          t.mihomo_client_fingerprint || ""
        )}</div></div>`
      )
      .join("");
  }
  toast(`TLS 人格 ${list.length}`);
}

async function showCompliance() {
  toast("合规核对中…");
  const r = await api("/api/system/compliance");
  const box = document.getElementById("stealthPanel");
  const fails = r.failures || [];
  if (box) {
    box.innerHTML = `<div class="card stat"><div class="l">v1–v10 合规</div><div class="n">${r.passed}/${r.total}</div><div class="l">failed ${r.failed} · ${r.ok ? "全部满足" : "有缺口"}</div></div>` +
      (fails.length
        ? fails
            .slice(0, 12)
            .map(
              (f) =>
                `<div class="card stat"><div class="l" style="color:#b91c1c">FAIL ${esc(f.item)}</div><div class="l mono">${esc(
                  f.detail || ""
                )}</div></div>`
            )
            .join("")
        : `<div class="card stat"><div class="l">contracts</div><div class="l mono">${esc(
            JSON.stringify(r.contracts || {}, null, 0).slice(0, 500)
          )}</div></div>`);
  }
  // also dump into doctor table
  const body = document.getElementById("doctorBody");
  if (body && Array.isArray(r.checks)) {
    body.innerHTML = r.checks
      .map((c) => {
        const pill = c.ok
          ? '<span class="pill ok">OK</span>'
          : '<span class="pill" style="background:#fef2f2;color:#b91c1c">FAIL</span>';
        return `<tr><td>${pill}</td><td>${esc(c.item)} <span class="mono" style="color:#94a3b8">${esc(
          c.version || ""
        )}</span></td><td class="mono">${esc(c.detail || "")}</td></tr>`;
      })
      .join("");
  }
  toast(r.ok ? `合规通过 ${r.passed}/${r.total}` : `合规缺口 ${r.failed}`, r.ok ? undefined : "err");
  console.log("compliance", r);
}

export function bindDoctorDom() {
  document.getElementById("btnDoctorReload")?.addEventListener("click", () =>
    loadDoctor().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnStealthEntropy")?.addEventListener("click", () =>
    showEntropy().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnStealthCollision")?.addEventListener("click", () =>
    showCollision().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnTlsProfiles")?.addEventListener("click", () =>
    showTls().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnCompliance")?.addEventListener("click", () =>
    showCompliance().catch((e) => toast(e.message, "err"))
  );
  document.getElementById("btnBackfillMeta")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/system/backfill-meta", { method: "POST", body: "{}" });
      toast(`已回填 ${r.count || 0} 个环境默认 meta`);
    } catch (e) {
      toast(e.message, "err");
    }
  });
}
