/* Player device: shows only this player's hole cards plus public info. */

const code = document.body.dataset.code;
const tokenKey = `wpd:token:${code}`;
const CONFIRM_FOLD_KEY = "wpd:confirm-fold";
const joinView = qs("#join-view");
const playView = qs("#play-view");
const holeEl = qs("#hole");
const communityEl = qs("#community");
const hintEl = qs("#hand-hint");
const connBadge = qs("#conn");
const foldBtn = qs("#fold-btn");
const unfoldBtn = qs("#unfold-btn");
const settingsPanel = qs("#settings");
const confirmFoldBox = qs("#confirm-fold");

let socket = null;
let playerId = null;

/* ------------------------------------------------------------------ settings */

function confirmFoldEnabled() {
  return localStorage.getItem(CONFIRM_FOLD_KEY) !== "0";
}

confirmFoldBox.checked = confirmFoldEnabled();
confirmFoldBox.addEventListener("change", () => {
  localStorage.setItem(CONFIRM_FOLD_KEY, confirmFoldBox.checked ? "1" : "0");
});
qs("#settings-btn").addEventListener("click", () => {
  confirmFoldBox.checked = confirmFoldEnabled();
  settingsPanel.hidden = false;
});
qs("#settings-close").addEventListener("click", () => {
  settingsPanel.hidden = true;
});
settingsPanel.addEventListener("click", (event) => {
  if (event.target === settingsPanel) settingsPanel.hidden = true;
});

/* ---------------------------------------------------------------- main view */

function render(state) {
  const me = state.you;
  const avatarSlot = qs("#player-avatar");
  if (me) {
    avatarSlot.replaceChildren(avatarEl(me.name, me.seat, { size: "md" }));
    document.body.style.setProperty("--seat-color", seatColor(me.seat));
  } else {
    avatarSlot.replaceChildren();
  }
  qs("#player-name").textContent = me ? me.name : "—";
  qs("#player-pos").textContent = me ? positionLabel(me) : "";
  qs("#street-label").textContent = state.street_label;
  qs("#hand-number").textContent =
    state.hand_number > 0 ? `第 ${state.hand_number} 局` : "未开局";

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
    onError: (message, reason) => {
      toast(message);
      if (reason === "bad_token" || reason === "table_missing") {
        // The server rejected this connection for good; stop reconnecting and
        // let the player join again instead of looping forever.
        if (socket) socket.close();
        setTimeout(fallbackToJoin, 400);
      }
    },
    onStatus: (status) => setConn(connBadge, status),
  });
}

foldBtn.addEventListener("click", () => {
  if (confirmFoldEnabled() && !confirm("确定要弃牌吗？")) return;
  if (socket) socket.send(action("fold"));
});
unfoldBtn.addEventListener("click", () => {
  if (socket) socket.send(action("unfold"));
});

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
