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

  function open() {
    if (onStatus) onStatus("connecting");
    socket = new WebSocket(`${proto}://${location.host}${path}`);

    socket.addEventListener("open", () => {
      attempt = 0;
      if (onStatus) onStatus("open");
      if (onOpen) onOpen();
    });

    socket.addEventListener("message", (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg.type === "state" && onState) onState(msg.state, msg.role);
      else if (msg.type === "error" && onError) onError(msg.message);
    });

    socket.addEventListener("close", () => {
      if (onStatus) onStatus("closed");
      if (closedByUser) return;
      attempt += 1;
      setTimeout(open, Math.min(1000 * attempt, 5000));
    });

    socket.addEventListener("error", () => socket.close());
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
