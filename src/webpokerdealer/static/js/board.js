/* Board device: the tablet in the middle of the table. Shows community cards,
 * the seats, and the controls for dealing / advancing streets / showdown. */

const code = document.body.dataset.code;
const connBadge = qs("#conn");
const communityEl = qs("#community");
const communityHint = qs("#community-hint");
const seatsEl = qs("#seats");
const startBtn = qs("#start-btn");
const nextBtn = qs("#next-btn");
const showdownBtn = qs("#showdown-btn");
const settingsPanel = qs("#settings");
const orderList = qs("#order-list");
const historyList = qs("#history-list");
const hostGate = qs("#host-gate");
const hostPinInput = qs("#host-pin");
const hostKey = `wpd:host:${code}`;

const NEXT_LABELS = {
  preflop: "发翻牌",
  flop: "发转牌",
  turn: "发河牌",
};

const LIVE_STREETS = ["preflop", "flop", "turn", "river"];

let socket = null;
let lastState = null;

/* ---------------------------------------------------------------- main view */

function renderCommunity(state) {
  const cards = state.community || [];
  renderCards(communityEl, cards, { size: "lg", slots: 5 });
  if (state.street === "waiting") {
    communityHint.textContent = "等待开局：请让玩家依次扫码入座";
  } else if (state.street === "showdown") {
    communityHint.textContent = "本局已摊牌";
  } else {
    communityHint.textContent = `已翻 ${cards.length} 张公共牌`;
  }
}

function renderSeats(state) {
  seatsEl.replaceChildren();
  const players = state.players || [];
  if (players.length === 0) {
    seatsEl.appendChild(el("p", "muted", "还没有玩家入座"));
    return;
  }
  players.forEach((player) => {
    const seat = el("div", "seat");
    seat.style.setProperty("--seat-color", seatColor(player.seat));
    if (!player.connected) seat.classList.add("seat--offline");
    if (player.folded) seat.classList.add("seat--folded");

    const head = el("div", "seat__head");
    head.appendChild(avatarEl(player.name, player.seat, { size: "sm" }));
    head.appendChild(el("span", "seat__name", player.name));
    const dot = el("span", `seat__dot${player.connected ? " seat__dot--on" : ""}`);
    head.appendChild(dot);
    seat.appendChild(head);

    const info = el("div", "seat__info");
    info.appendChild(el("span", "seat__no", `#${player.seat + 1}`));
    if (player.is_dealer) info.appendChild(el("span", "badge badge--dealer", "D"));
    if (player.is_small_blind) info.appendChild(el("span", "badge badge--sb", "SB"));
    if (player.is_big_blind) info.appendChild(el("span", "badge badge--bb", "BB"));
    seat.appendChild(info);

    const cards = el("div", "seat__cards");
    if (Array.isArray(player.hole)) {
      player.hole.forEach((card) => cards.appendChild(cardEl(card, { size: "sm" })));
    } else {
      for (let i = 0; i < (player.card_count || 0); i += 1) {
        cards.appendChild(cardEl(null, { faceDown: true, size: "sm" }));
      }
    }
    seat.appendChild(cards);

    const meta = el("div", "seat__meta");
    const bits = [];
    if (player.folded) bits.push("已弃牌");
    if (!player.connected) bits.push("离线");
    meta.textContent = bits.join(" · ");
    if (bits.length) seat.appendChild(meta);

    const remove = el("button", "btn small", "移出");
    remove.addEventListener("click", () => {
      if (confirm(`把「${player.name}」移出牌桌？`)) {
        socket.send(action("remove_player", { player_id: player.id }));
      }
    });
    seat.appendChild(remove);

    seatsEl.appendChild(seat);
  });
}

function renderControls(state) {
  const count = (state.players || []).length;
  const live = LIVE_STREETS.includes(state.street);

  startBtn.disabled = count < 2;
  startBtn.textContent = state.hand_number > 0 ? "开始下一局" : "开始本局";

  // The deal stops at the river; it never advances to showdown on its own.
  nextBtn.disabled = !["preflop", "flop", "turn"].includes(state.street);
  nextBtn.textContent = NEXT_LABELS[state.street] || "下一轮";

  showdownBtn.disabled = !live;
}

/** Play a sound only when the state actually changed (not on every broadcast). */
function detectSounds(prev, next) {
  if (next.hand_number > prev.hand_number) sfx.deal();
  if ((next.community || []).length > (prev.community || []).length) sfx.flip();
  if (prev.street !== "showdown" && next.street === "showdown") sfx.reveal();
}

function render(state) {
  if (lastState) detectSounds(lastState, state);
  lastState = state;
  qs("#board-code").textContent = state.code;
  qs("#street-label").textContent = state.street_label;
  qs("#seat-count").textContent =
    `座位 ${(state.players || []).length}/${state.seats}`;
  qs("#hand-number").textContent =
    state.hand_number > 0 ? `第 ${state.hand_number} 局` : "未开局";

  renderControls(state);
  renderCommunity(state);
  renderSeats(state);
  if (!settingsPanel.hidden) renderSettings(state);
}

/* ------------------------------------------------------------- settings panel */

function posBadges(player) {
  const wrap = el("span", "pos-badges");
  if (player.is_dealer) wrap.appendChild(el("span", "badge badge--dealer", "D"));
  if (player.is_small_blind) wrap.appendChild(el("span", "badge badge--sb", "SB"));
  if (player.is_big_blind) wrap.appendChild(el("span", "badge badge--bb", "BB"));
  return wrap;
}

function renderOrder(state) {
  orderList.replaceChildren();
  const players = state.players || [];
  if (players.length === 0) {
    orderList.appendChild(el("p", "muted small", "还没有玩家入座"));
    return;
  }
  players.forEach((player, index) => {
    const row = el("div", "order-row");
    row.style.setProperty("--seat-color", seatColor(player.seat));
    row.appendChild(avatarEl(player.name, player.seat, { size: "xs" }));
    row.appendChild(el("span", "order-row__name", `${index + 1}. ${player.name}`));
    row.appendChild(posBadges(player));

    const actions = el("span", "order-row__actions");
    const dealer = el("button", "btn small", player.is_dealer ? "庄" : "设庄");
    dealer.title = "把庄家位（D）设为此玩家";
    dealer.disabled = player.is_dealer;
    dealer.addEventListener("click", () =>
      socket.send(action("set_dealer", { player_id: player.id }))
    );
    const up = el("button", "btn small", "↑");
    up.disabled = index === 0;
    up.addEventListener("click", () =>
      socket.send(action("move_player", { player_id: player.id, direction: "up" }))
    );
    const down = el("button", "btn small", "↓");
    down.disabled = index === players.length - 1;
    down.addEventListener("click", () =>
      socket.send(action("move_player", { player_id: player.id, direction: "down" }))
    );
    actions.append(dealer, up, down);
    row.appendChild(actions);
    orderList.appendChild(row);
  });
}

function historyPlayerLine(player) {
  const line = el("div", "history-player");
  line.style.setProperty("--seat-color", seatColor(player.seat));
  line.appendChild(avatarEl(player.name, player.seat, { size: "xs" }));
  const name = el("span", "history-player__name", player.name);
  if (player.folded) name.classList.add("history-player__name--folded");
  line.appendChild(name);
  line.appendChild(posBadges(player));

  const cards = el("span", "history-player__cards");
  if (Array.isArray(player.hole)) {
    player.hole.forEach((card) => cards.appendChild(cardEl(card, { size: "xs" })));
  } else if (player.folded) {
    cards.appendChild(el("span", "muted small", "已弃牌"));
  } else {
    cards.appendChild(el("span", "muted small", "未亮牌"));
  }
  line.appendChild(cards);
  return line;
}

function renderHistory(state) {
  historyList.replaceChildren();
  const history = state.history || [];
  if (history.length === 0) {
    historyList.appendChild(el("p", "muted small", "还没有已结束的牌局"));
    return;
  }
  // Newest first so the just-finished hand is on top at showdown.
  history.slice().reverse().forEach((record) => {
    const item = el("div", "history-item");
    const head = el("div", "history-item__head");
    head.appendChild(el("strong", "", `第 ${record.hand_number} 局`));
    head.appendChild(
      el("span", "badge badge--street", record.showdown ? "摊牌" : record.street_label)
    );
    item.appendChild(head);

    if ((record.community || []).length) {
      const community = el("div", "history-item__community");
      record.community.forEach((card) => community.appendChild(cardEl(card, { size: "xs" })));
      item.appendChild(community);
    }
    (record.players || []).forEach((player) => item.appendChild(historyPlayerLine(player)));
    historyList.appendChild(item);
  });
}

function renderSettings(state) {
  renderPin(state);
  renderOrder(state);
  renderHistory(state);
}

let pinVisible = false;

function renderPin(state) {
  const view = qs("#host-pin-view");
  const toggle = qs("#host-pin-toggle");
  if (pinVisible && state.pin) {
    view.textContent = state.pin;
    toggle.textContent = "隐藏 PIN";
  } else {
    view.textContent = "••••";
    toggle.textContent = "查看 PIN";
  }
}

qs("#host-pin-toggle").addEventListener("click", () => {
  pinVisible = !pinVisible;
  if (lastState) renderPin(lastState);
});

function openSettings() {
  settingsPanel.hidden = false;
  if (lastState) renderSettings(lastState);
}
function closeSettings() {
  settingsPanel.hidden = true;
  pinVisible = false; // hide again next time the panel opens
}

/* --------------------------------------------------------------- board alert */

function showBoardAlert(message) {
  qs("#board-alert-text").textContent = message;
  qs("#board-alert").hidden = false;
}

qs("#board-alert-close").addEventListener("click", () => {
  qs("#board-alert").hidden = true;
});

/* ------------------------------------------------------- host authentication */

function requirePin(message) {
  if (message) toast(message);
  if (socket) socket.close();
  hostGate.hidden = false;
  hostPinInput.value = "";
  hostPinInput.focus();
}

qs("#host-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const pin = hostPinInput.value.trim();
  if (!pin) return;
  const button = event.target.querySelector("button");
  button.disabled = true;
  try {
    const res = await fetch(`/api/tables/${encodeURIComponent(code)}/host`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "PIN 不正确");
    localStorage.setItem(hostKey, data.host_token);
    hostGate.hidden = true;
    connectBoard(data.host_token);
  } catch (err) {
    toast(err.message || "PIN 不正确");
    hostPinInput.select();
  } finally {
    button.disabled = false;
  }
});

/* --------------------------------------------------------------- connection */

function fatalTableGone(message) {
  if (socket) socket.close();
  connBadge.textContent = "牌桌已失效";
  connBadge.className = "badge badge--warn";
  startBtn.disabled = true;
  nextBtn.disabled = true;
  showdownBtn.disabled = true;
  seatsEl.replaceChildren(el("p", "muted", `${message} 请回首页重新创建牌桌。`));
}

function connectBoard(token) {
  socket = connectWS(
    `/ws/${code}?role=board&token=${encodeURIComponent(token)}`,
    {
      onState: render,
      onNotice: (msg) => {
        const text = msg.message || "有另一台设备打开了公牌桌";
        showBoardAlert(text);
        toast(text);
      },
      onError: (message, reason) => {
        if (reason === "table_missing") fatalTableGone(message);
        else if (reason === "bad_host") {
          // Stored token is stale (e.g. table was recreated): ask for the PIN.
          localStorage.removeItem(hostKey);
          requirePin(message);
        } else toast(message);
      },
      onStatus: (status) => setConn(connBadge, status),
    }
  );
}

const savedHostToken = localStorage.getItem(hostKey);
if (savedHostToken) connectBoard(savedHostToken);
else requirePin();

startBtn.addEventListener("click", () => socket.send(action("start_hand")));
nextBtn.addEventListener("click", () => socket.send(action("next_street")));
showdownBtn.addEventListener("click", () => socket.send(action("showdown")));

qs("#settings-btn").addEventListener("click", openSettings);
qs("#settings-close").addEventListener("click", closeSettings);
settingsPanel.addEventListener("click", (event) => {
  if (event.target === settingsPanel) closeSettings();
});

const COMMUNITY_SIZE_KEY = "wpd:community-size";
const DEFAULT_COMMUNITY_SIZE = 112;
const COMMUNITY_MIN = 64;
const COMMUNITY_MAX = 400;
const communitySizeInput = qs("#community-size");
const communitySizeValue = qs("#community-size-value");

/** The biggest card that still fits five across the felt on this screen. */
function communityCardLimit() {
  const felt = qs(".felt");
  if (!felt || felt.clientWidth === 0) return COMMUNITY_MAX;
  const style = getComputedStyle(felt);
  const padding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
  const gap = 12; // .community gap
  const perCard = Math.floor((felt.clientWidth - padding - gap * 4) / 5);
  return Math.max(COMMUNITY_MIN, Math.min(COMMUNITY_MAX, perCard));
}

function applyCommunitySize(px) {
  const limit = communityCardLimit();
  const value = Math.max(COMMUNITY_MIN, Math.min(px, limit));
  communitySizeInput.max = String(limit);
  communitySizeInput.value = String(value);
  communitySizeValue.textContent = `${value}px`;
  document.body.style.setProperty("--community-w", `${value}px`);
}

function initCommunitySize() {
  const saved = parseInt(localStorage.getItem(COMMUNITY_SIZE_KEY) || "", 10);
  applyCommunitySize(Number.isFinite(saved) ? saved : DEFAULT_COMMUNITY_SIZE);
  communitySizeInput.addEventListener("input", () => {
    const value = parseInt(communitySizeInput.value, 10);
    applyCommunitySize(value);
    localStorage.setItem(COMMUNITY_SIZE_KEY, String(value));
  });
  window.addEventListener("resize", () => {
    applyCommunitySize(parseInt(communitySizeInput.value, 10) || DEFAULT_COMMUNITY_SIZE);
  });
}

qs("#community-size-max").addEventListener("click", () => {
  applyCommunitySize(COMMUNITY_MAX);
  localStorage.setItem(COMMUNITY_SIZE_KEY, communitySizeInput.value);
});

const soundToggle = qs("#sound-toggle");
soundToggle.checked = sfx.enabled();
soundToggle.addEventListener("change", () => sfx.setEnabled(soundToggle.checked));
qs("#sound-test").addEventListener("click", () => {
  sfx.unlock();
  sfx.reveal();
});

initCommunitySize();

qs("#reset-btn").addEventListener("click", () => {
  if (confirm("重置牌桌会清空所有玩家与牌局历史，确定吗？")) socket.send(action("reset"));
});
