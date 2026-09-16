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

/** Render an array of cards into a container, padding with empty slots. */
function renderCards(container, cards, { size = "", slots = null } = {}) {
  container.replaceChildren();
  (cards || []).forEach((card) => container.appendChild(cardEl(card, { size })));
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
function connectWS(path, { onState, onError, onOpen, onStatus } = {}) {
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
