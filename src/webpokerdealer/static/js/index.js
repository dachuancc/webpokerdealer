/* Landing page: create a table or join an existing one. */

const TOKEN_KEY = (code) => `wpd:token:${code}`;
const HOST_KEY = (code) => `wpd:host:${code}`;
const NAME_KEY = "wpd:name";

qs("#create-btn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const res = await fetch("/api/tables", { method: "POST" });
    if (!res.ok) throw new Error("创建失败");
    const data = await res.json();
    // Remember host control so the board page doesn't ask for the PIN again.
    localStorage.setItem(HOST_KEY(data.code), data.host_token);
    location.href = `/board/${data.code}`;
  } catch (err) {
    toast(err.message || "创建失败");
    button.disabled = false;
  }
});

qs("#join-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = qs("#join-code").value.trim().toUpperCase();
  const name = qs("#join-name").value.trim();
  if (!code || !name) return;
  const button = event.target.querySelector("button");
  button.disabled = true;
  try {
    const res = await fetch(`/api/tables/${encodeURIComponent(code)}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "加入失败");
    localStorage.setItem(TOKEN_KEY(data.code), data.token);
    localStorage.setItem(NAME_KEY, name);
    location.href = `/play/${data.code}`;
  } catch (err) {
    toast(err.message || "加入失败");
    button.disabled = false;
  }
});

// Prefill the last used nickname.
const savedName = localStorage.getItem(NAME_KEY);
if (savedName) qs("#join-name").value = savedName;
