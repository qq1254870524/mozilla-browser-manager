/** Toast notifications. */
export function toast(msg, type = "ok") {
  const box = document.getElementById("toast");
  if (!box) return;
  const el = document.createElement("div");
  el.className = "t " + type;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
