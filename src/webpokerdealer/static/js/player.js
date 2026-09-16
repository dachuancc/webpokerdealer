/* Player device: shows only this player's hole cards plus public info. */

const code = document.body.dataset.code;
const tokenKey = `wpd:token:${code}`;
const joinView = qs("#join-view");
const playView = qs("#play-view");
const holeEl = qs("#hole");
const communityEl = qs("#community");
const hintEl = qs("#hand-hint");
const connBadge = qs("#conn");
const foldBtn = qs("#fold-btn");
const unfoldBtn = qs("#unfold-btn");

let socket = null;
let playerId = null;

function render(state) {
  const me = state.you;
  qs("#player-name").textContent = me ? me.name : "—";
  qs("#player-pos").textContent = me ? positionLabel(me) : "";
  qs("#street-label").textContent = state.street_label;

  const hole = (me && me.hole) || [];
  if (hole.length) {
    renderCards(holeEl, hole);
    hintEl.classList.toggle("you-folded", !!me.folded);
    hintEl.textContent = me.folded ? "你已弃牌" : "";
  } else {
    renderCards(holeEl, [], { slots: 2 });
    hintEl.classList.remove("you-folded");
    hintEl.textContent = state.street === "waiting" ? "等待开局…" : "等待发牌…";
  }

  renderCards(communityEl, state.community || [], { size: "sm", slots: 5 });

  const folded = !!(me && me.folded);
  const canFold = !["waiting", "showdown"].includes(state.street);
  foldBtn.disabled = !canFold || folded;
  unfoldBtn.hidden = !(canFold && folded);
}

function fallbackToJoin() {
  localStorage.removeItem(tokenKey);
  joinView.hidden = false;
  playView.hidden = true;
}

function startPlaying(token) {
  joinView.hidden = true;
  playView.hidden = false;
  socket = connectWS(`/ws/${code}?role=player&token=${encodeURIComponent(token)}`, {
    onState: (state) => {
      playerId = state.you ? state.you.id : playerId;
      render(state);
    },
    onError: (message) => {
      toast(message);
      if (message.includes("身份") || message.includes("牌桌")) {
        setTimeout(fallbackToJoin, 400);
      }
    },
    onStatus: (status) => setConn(connBadge, status),
  });
  foldBtn.addEventListener("click", () => socket.send(action("fold")));
  unfoldBtn.addEventListener("click", () => socket.send(action("unfold")));
}

qs("#join-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = qs("#join-name").value.trim();
  if (!name) return;
  const button = event.target.querySelector("button");
  button.disabled = true;
  try {
    const res = await fetch(`/api/tables/${encodeURIComponent(code)}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "入座失败");
    localStorage.setItem(tokenKey, data.token);
    localStorage.setItem("wpd:name", name);
    startPlaying(data.token);
  } catch (err) {
    toast(err.message || "入座失败");
    button.disabled = false;
  }
});

const existing = localStorage.getItem(tokenKey);
if (existing) {
  startPlaying(existing);
} else {
  const savedName = localStorage.getItem("wpd:name");
  if (savedName) qs("#join-name").value = savedName;
  fallbackToJoin();
}
