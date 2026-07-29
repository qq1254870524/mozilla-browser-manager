/** Groups module. */
import { api, esc } from "../core/api.js";
import { state } from "../core/state.js";

export function renderGroups() {
  const body = document.getElementById("groupBody");
  if (!body) return;
  const rows = state.groups.length
    ? state.groups
    : [{ name: "未分组", count: state.profiles.length }];
  body.innerHTML = rows
    .map(
      (g) => `<tr>
    <td>${esc(g.name)}</td><td>${g.count}</td>
    <td><button class="btn btn-ghost btn-sm" data-group="${esc(g.name)}">查看</button></td>
  </tr>`
    )
    .join("");
}

export async function loadGroups() {
  state.groups = await api("/api/groups");
  renderGroups();
}

export function bindGroupsDom(switchView) {
  const body = document.getElementById("groupBody");
  if (!body || body.dataset.bound) return;
  body.dataset.bound = "1";
  body.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-group]");
    if (!btn) return;
    const sel = document.getElementById("filterGroup");
    if (sel) sel.value = btn.dataset.group;
    switchView("profiles");
  });
}
