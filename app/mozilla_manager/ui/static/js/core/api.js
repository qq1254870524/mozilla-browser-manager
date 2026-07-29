/** HTTP client — single place for fetch + error unwrap. */
export async function api(path, opts = {}) {
  const optsOut = { ...opts };
  const headers = { ...(opts.headers || {}) };
  const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData;
  // Only force JSON content-type for non-FormData bodies; browser sets multipart boundary for FormData.
  if (!isForm && !headers["Content-Type"] && !headers["content-type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (isForm) {
    delete headers["Content-Type"];
    delete headers["content-type"];
  }
  optsOut.headers = headers;
  const res = await fetch(path, optsOut);
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data && data.detail !== undefined ? data.detail : res.statusText;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(msg);
  }
  return data;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
