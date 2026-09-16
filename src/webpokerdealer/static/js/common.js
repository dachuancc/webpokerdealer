/* Shared helpers for all pages. No build step: plain browser globals. */

function qs(selector, root = document) {
  return root.querySelector(selector);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

/** Build a card element from a card dict (or a face-down / empty slot). */
function cardEl(card, { faceDown = false, size = "" } = {}) {
  const classes = ["card"];
  if (size) classes.push(`card--${size}`);
  if (faceDown) {
    classes.push("card--back");
    return el("div", classes.join(" "));
  }
  if (!card) {
    classes.push("card--empty");
    return el("div", classes.join(" "));
  }
  if (card.red) classes.push("card--red");
  const node = el("div", classes.join(" "));
  node.appendChild(el("span", "card__rank", card.label));
  node.appendChild(el("span", "card__suit", card.symbol));
  node.title = card.code;
  return node;
}

/** Render an array of cards into a container, padding with empty slots.
 * Newly appended cards (beyond what was already shown) animate in. */
function renderCards(container, cards, { size = "", slots = null, animate = true } = {}) {
  const prevCount = container.querySelectorAll(".card:not(.card--empty)").length;
  container.replaceChildren();
  (cards || []).forEach((card, index) => {
    const node = cardEl(card, { size });
    if (animate && index >= prevCount) {
      node.classList.add("card--deal");
      node.style.animationDelay = `${Math.min(index - prevCount, 4) * 70}ms`;
    }
    container.appendChild(node);
  });
  if (slots !== null) {
    for (let i = (cards || []).length; i < slots; i += 1) {
      container.appendChild(cardEl(null, { size }));
    }
  }
}

function toast(message, ms = 2200) {
  const node = qs("#toast");
  if (!node) return;
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { node.hidden = true; }, ms);
}

function setConn(node, status) {
  if (!node) return;
  const map = {
    open: ["已连接", "badge badge--ok"],
    connecting: ["连接中…", "badge badge--warn"],
    closed: ["已断开", "badge badge--warn"],
  };
  const [text, cls] = map[status] || map.connecting;
  node.textContent = text;
  node.className = cls;
}

/**
 * Open a WebSocket and wire it to callbacks, reconnecting with backoff.
 * `path` is e.g. `/ws/AB3K?role=board`.
 */
function connectWS(path, { onState, onError, onNotice, onOpen, onStatus } = {}) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let attempt = 0;
  let socket = null;
  let closedByUser = false;
  let reconnectTimer = null;

  // Exactly one reconnect per drop. Without the guard a single failure can be
  // scheduled twice (browsers fire `error` *and* then `close`), which snowballs.
  function scheduleReconnect() {
    if (closedByUser || reconnectTimer) return;
    attempt += 1;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      open();
    }, Math.min(1000 * attempt, 5000));
  }

  function open() {
    if (closedByUser) return;
    if (onStatus) onStatus("connecting");
    const ws = new WebSocket(`${proto}://${location.host}${path}`);
    socket = ws;

    ws.addEventListener("open", () => {
      if (ws !== socket) return; // stale socket from a previous attempt
      attempt = 0;
      if (onStatus) onStatus("open");
      if (onOpen) onOpen();
    });

    ws.addEventListener("message", (event) => {
      if (ws !== socket) return;
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg.type === "state" && onState) onState(msg.state, msg.role);
      else if (msg.type === "error" && onError) onError(msg.message, msg.reason);
      else if (msg.type === "notice" && onNotice) onNotice(msg);
    });

    // A failed handshake fires `error` and then `close`; let `close` own the
    // reconnect so we never schedule it twice for the same socket.
    ws.addEventListener("error", () => {});

    ws.addEventListener("close", () => {
      if (ws !== socket) return;
      if (onStatus) onStatus("closed");
      scheduleReconnect();
    });
  }

  open();

  return {
    send(message) {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message));
        return true;
      }
      return false;
    },
    close() {
      closedByUser = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (socket) socket.close();
    },
  };
}

/* Seat identity: a stable colour per seat + an initials avatar, so the same
 * player is recognisable on the board and on their own phone. */
const SEAT_COLORS = [
  "#e8c46a", // gold
  "#6ab0e8", // sky
  "#e88a6a", // coral
  "#7fd67f", // green
  "#b58ce8", // violet
  "#e86ab0", // pink
  "#5fd0c8", // teal
  "#f0a35e", // amber
  "#a8c0ff", // periwinkle
];

function seatColor(seat) {
  const n = SEAT_COLORS.length;
  return SEAT_COLORS[((seat % n) + n) % n];
}

function avatarEl(name, seat, { size = "md" } = {}) {
  const trimmed = (name || "?").trim();
  const initial = trimmed ? Array.from(trimmed)[0] : "?";
  const node = el("span", `avatar avatar--${size}`, initial);
  node.style.setProperty("--seat-color", seatColor(seat));
  return node;
}

function positionLabel(player) {
  const parts = [];
  if (player.is_dealer) parts.push("D");
  if (player.is_small_blind) parts.push("SB");
  if (player.is_big_blind) parts.push("BB");
  return parts.join(" / ");
}

function action(name, extra = {}) {
  return { type: "action", action: name, ...extra };
}

/* ------------------------------------------------------------------- sound */

/* Tiny WebAudio sound effects: no asset files, no build step. Browsers block
 * audio until a user gesture, so we unlock the context on the first pointerdown
 * and every sound on the board follows a tap anyway. */
const sfx = (() => {
  const KEY = "wpd:sound";
  let ctx = null;

  function enabled() {
    return localStorage.getItem(KEY) !== "0";
  }
  function setEnabled(value) {
    localStorage.setItem(KEY, value ? "1" : "0");
  }
  function unlock() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }
  function blip({ freq, type = "triangle", dur = 0.09, gain = 0.06, dropTo = 0 }) {
    if (!enabled()) return;
    const c = unlock();
    if (!c) return;
    const t = c.currentTime;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (dropTo) osc.frequency.exponentialRampToValueAtTime(dropTo, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g);
    g.connect(c.destination);
    osc.start(t);
    osc.stop(t + dur + 0.02);
  }

  return {
    enabled,
    setEnabled,
    unlock,
    deal() { blip({ freq: 540, dropTo: 300, dur: 0.1, gain: 0.05 }); },
    flip() { blip({ freq: 320, type: "square", dur: 0.07, gain: 0.04 }); },
    reveal() {
      blip({ freq: 700, dur: 0.1, gain: 0.05 });
      setTimeout(() => blip({ freq: 1000, dur: 0.12, gain: 0.05 }), 90);
    },
  };
})();

// Unlock the audio context on the first interaction so later sounds can play.
window.addEventListener("pointerdown", () => sfx.unlock(), { once: true });
