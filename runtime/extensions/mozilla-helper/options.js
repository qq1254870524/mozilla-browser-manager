chrome.storage.local.get(["apiBase", "profileId"]).then((r) => {
  document.getElementById("apiBase").value = r.apiBase || "http://127.0.0.1:17888";
  document.getElementById("profileId").value = r.profileId || "";
});
document.getElementById("save").onclick = async () => {
  const apiBase = document.getElementById("apiBase").value.trim();
  const profileId = document.getElementById("profileId").value.trim();
  await chrome.storage.local.set({ apiBase, profileId });
  document.getElementById("msg").textContent = "已保存";
};
