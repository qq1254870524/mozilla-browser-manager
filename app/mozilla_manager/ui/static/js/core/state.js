/** Shared app state (small, module-friendly). */
export const state = {
  view: "profiles",
  profiles: [],
  groups: [],
  proxies: [],
  socks5Lib: [],
  subs: [],
  nodes: [],
  selected: new Set(),
};

export function segVal(id) {
  const on = document.querySelector("#" + id + " button.on");
  return on ? on.dataset.v : "";
}

export function seg(btn) {
  const parent = btn.parentElement;
  [...parent.querySelectorAll("button")].forEach((b) => b.classList.remove("on"));
  btn.classList.add("on");
}

export function segPick(id, val) {
  document.querySelectorAll("#" + id + " button").forEach((b) => {
    b.classList.toggle("on", b.dataset.v === val);
  });
}

// expose for inline onclick in HTML shell
window.MMSeg = seg;
