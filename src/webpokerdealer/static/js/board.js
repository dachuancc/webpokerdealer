/* Board device: the tablet in the middle of the table. Shows community cards,
 * the seats, and the controls for dealing / advancing streets. */

const code = document.body.dataset.code;
const connBadge = qs("#conn");
const communityEl = qs("#community");
const communityHint = qs("#community-hint");
const seatsEl = qs("#seats");
const startBtn = qs("#start-btn");
const nextBtn = qs("#next-btn");

const NEXT_LABELS = {
  preflop: "发翻牌",
  flop: "发转牌",
  turn: "发河牌",
  river: "摊牌",
};

let socket = null;

function renderCommunity(state) {
  const cards = state.community || [];
  renderCards(communityEl, cards, { size: "lg", slots: 5 });
  if (state.street === "waiting") {
    communityHint.textContent = "等待开局：请让玩家依次扫码入座";
  } else if (state.street === "showdown") {
    communityHint.textContent = "本局结束";
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

function render(state) {
  qs("#board-code").textContent = state.code;
  qs("#street-label").textContent = state.street_label;
  qs("#hand-number").textContent = state.hand_number > 0 ? `第 ${state.hand_number} 局` : "未开局";

  const count = (state.players || []).length;
  const canStart = (state.street === "waiting" || state.street === "showdown") && count >= 2;
  startBtn.disabled = !canStart;
  startBtn.textContent = state.street === "showdown" ? "开始下一局" : "开始本局";

  const canNext = !["waiting", "showdown"].includes(state.street);
  nextBtn.disabled = !canNext;
  nextBtn.textContent = NEXT_LABELS[state.street] || "下一轮";

  renderCommunity(state);
  renderSeats(state);
}

function fatalTableGone(message) {
  if (socket) socket.close();
  connBadge.textContent = "牌桌已失效";
  connBadge.className = "badge badge--warn";
  startBtn.disabled = true;
  nextBtn.disabled = true;
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

startBtn.addEventListener("click", () => socket.send(action("start_hand")));
nextBtn.addEventListener("click", () => socket.send(action("next_street")));
qs("#reset-btn").addEventListener("click", () => {
  if (confirm("重置牌桌会清空所有玩家，确定吗？")) socket.send(action("reset"));
});
