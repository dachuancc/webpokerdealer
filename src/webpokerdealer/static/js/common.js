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

/* Tap/click any face-up card to show a big, readable copy of it.
 * Works on the board and on the player's phone. Click anywhere to dismiss. */
function initCardZoom() {
  const overlay = qs("#card-zoom");
  if (!overlay) return;
  document.addEventListener("click", (event) => {
    if (!overlay.hidden) {
      overlay.hidden = true;
      return;
    }
    const card = event.target.closest(".card");
    if (!card || card.classList.contains("card--empty") || card.classList.contains("card--back")) {
      return;
    }
    const big = card.cloneNode(true);
    big.classList.remove("card--sm", "card--xs", "card--lg");
    big.classList.add("card--xl");
    overlay.replaceChildren(big);
    overlay.hidden = false;
  });
}

initCardZoom();

function action(name, extra = {}) {
  return { type: "action", action: name, ...extra };
}

/* ------------------------------------------------------------------- sound */

/* Tiny WebAudio sound effects: no asset files, no build step. Browsers block
 * audio until a user gesture, so we unlock the context on any interaction; the
 * first sound may be dropped while the context resumes, so blip retries once. */
const sfx = (() => {
  const KEY = "wpd:sound";
  let ctx = null;
  let primed = false;

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
  /** Play a silent buffer inside the first user gesture.
   *
   * iOS/Safari won't merely honour resume(): it needs a sound to actually be
   * started during the gesture before it will allow later (server-driven)
   * sounds. A one-sample silent buffer is enough, and it is inaudible. */
  function prime() {
    const c = unlock();
    if (!c) return;
    preloadSamples();
    if (primed) return;
    primed = true;
    try {
      const buffer = c.createBuffer(1, 1, 22050);
      const src = c.createBufferSource();
      src.buffer = buffer;
      src.connect(c.destination);
      src.start(0);
    } catch (err) {
      /* nothing we can do; later sounds will just be silent on this device */
    }
  }
  let noiseBuffer = null;
  function noiseData(c) {
    if (noiseBuffer && noiseBuffer.sampleRate === c.sampleRate) return noiseBuffer;
    const len = Math.floor(c.sampleRate * 0.4);
    const buf = c.createBuffer(1, len, c.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i += 1) data[i] = Math.random() * 2 - 1;
    noiseBuffer = buf;
    return buf;
  }

  /** Run `build` once the context is running (retry once after resume). */
  function schedule(build, retried = false) {
    if (!enabled()) return;
    const c = unlock();
    if (!c) return;
    if (c.state !== "running") {
      c.resume().then(() => { if (!retried) schedule(build, true); }).catch(() => {});
      return;
    }
    build(c, c.currentTime);
  }

  /** A card flick: a very short band-passed noise burst whose filter sweeps
   * down, which reads as the "swish" of flipping/dealing a card. */
  function swish({ dur = 0.07, gain = 0.22, from = 3600, to = 1200, q = 0.9 } = {}) {
    schedule((c, t) => {
      const src = c.createBufferSource();
      src.buffer = noiseData(c);
      const band = c.createBiquadFilter();
      band.type = "bandpass";
      band.Q.value = q;
      band.frequency.setValueAtTime(from, t);
      band.frequency.exponentialRampToValueAtTime(Math.max(80, to), t + dur);
      const g = c.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(gain, t + 0.005);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      src.connect(band);
      band.connect(g);
      g.connect(c.destination);
      src.start(t);
      src.stop(t + dur + 0.02);
    });
  }

  /* Optional real recordings. Drop matching files into static/audio/ to replace
   * the synthesised sounds; anything missing keeps the synth fallback. */
  const SAMPLE_FILES = {
    deal: "/static/audio/deal.mp3",
    flip: "/static/audio/flip.mp3",
    reveal: "/static/audio/reveal.mp3",
  };
  const sampleBuffers = {};

  async function loadSample(name) {
    if (sampleBuffers[name]) return;
    const c = unlock();
    if (!c) return;
    try {
      const res = await fetch(SAMPLE_FILES[name]);
      if (!res.ok) return; // 404 -> keep using the synth fallback
      sampleBuffers[name] = await c.decodeAudioData(await res.arrayBuffer());
    } catch (err) {
      /* missing or broken file: fall back to the synthesised swish */
    }
  }

  function preloadSamples() {
    Object.keys(SAMPLE_FILES).forEach(loadSample);
  }

  /** Play a loaded sample; returns false when there is nothing to play. */
  function playSample(name, { gain = 0.6 } = {}) {
    const buffer = sampleBuffers[name];
    if (!buffer) return false;
    schedule((c, t) => {
      const src = c.createBufferSource();
      src.buffer = buffer;
      const g = c.createGain();
      g.gain.value = gain;
      src.connect(g);
      g.connect(c.destination);
      src.start(t);
    });
    return true;
  }

  return {
    enabled,
    setEnabled,
    unlock,
    prime,
    // Real recording if present, else a synthesised flick.
    deal() {
      if (!playSample("deal")) swish({ dur: 0.05, gain: 0.18, from: 5000, to: 1800, q: 1.2 });
    },
    flip() {
      if (!playSample("flip")) swish({ dur: 0.035, gain: 0.22, from: 6000, to: 2200, q: 1.4 });
    },
    reveal() {
      if (playSample("reveal")) return;
      swish({ dur: 0.035, gain: 0.22, from: 6000, to: 2200, q: 1.4 });
      setTimeout(() => swish({ dur: 0.045, gain: 0.2, from: 5200, to: 1800, q: 1.2 }), 110);
    },
  };
})();

// Unlock audio on the earliest interaction; try a few event types for safety.
["pointerdown", "touchstart", "keydown"].forEach((type) =>
  window.addEventListener(type, () => sfx.prime(), { passive: true })
);
