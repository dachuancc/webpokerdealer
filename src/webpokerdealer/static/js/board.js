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
    if (!player.connected) seat.classList.add("seat--offline");
    if (player.folded) seat.classList.add("seat--folded");

    const head = el("div", "seat__head");
    const dot = el("span", `seat__dot${player.connected ? " seat__dot--on" : ""}`);
    head.appendChild(dot);
    head.appendChild(el("span", "seat__name", `${player.seat + 1}. ${player.name}`));
    if (player.is_dealer) head.appendChild(el("span", "badge badge--dealer", "D"));
    if (player.is_small_blind) head.appendChild(el("span", "badge badge--sb", "SB"));
    if (player.is_big_blind) head.appendChild(el("span", "badge badge--bb", "BB"));
    seat.appendChild(head);

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

function render(state) {
  lastState = state;
  qs("#board-code").textContent = state.code;
  qs("#street-label").textContent = state.street_label;
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
    row.appendChild(el("span", "order-row__name", `${index + 1}. ${player.name}`));
    row.appendChild(posBadges(player));

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
    const actions = el("span", "order-row__actions");
    actions.append(up, down);
    row.appendChild(actions);
    orderList.appendChild(row);
  });
}

function historyPlayerLine(player) {
  const line = el("div", "history-player");
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
  renderOrder(state);
  renderHistory(state);
}

function openSettings() {
  settingsPanel.hidden = false;
  if (lastState) renderSettings(lastState);
}
function closeSettings() {
  settingsPanel.hidden = true;
}

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

socket = connectWS(`/ws/${code}?role=board`, {
  onState: render,
  onError: (message, reason) => {
    toast(message);
    if (reason === "table_missing") fatalTableGone(message);
  },
  onStatus: (status) => setConn(connBadge, status),
});

startBtn.addEventListener("click", () => {
  const state = lastState || {};
  const live = LIVE_STREETS.includes(state.street);
  if (live && !confirm(`第 ${state.hand_number} 局尚未摊牌，直接开始下一局？（本局不会亮牌）`)) {
    return;
  }
  socket.send(action("start_hand"));
});
nextBtn.addEventListener("click", () => socket.send(action("next_street")));
showdownBtn.addEventListener("click", () => socket.send(action("showdown")));

qs("#settings-btn").addEventListener("click", openSettings);
qs("#settings-close").addEventListener("click", closeSettings);
settingsPanel.addEventListener("click", (event) => {
  if (event.target === settingsPanel) closeSettings();
});

qs("#reset-btn").addEventListener("click", () => {
  if (confirm("重置牌桌会清空所有玩家与牌局历史，确定吗？")) socket.send(action("reset"));
});
