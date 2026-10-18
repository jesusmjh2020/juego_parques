
const $ = (id) => document.getElementById(id);

const s = io();

let me = null;
let st = null;

const cs = {
  red: "#ef4444",
  green: "#22c55e",
  yellow: "#eab308",
  blue: "#3b82f6"
};

const names = {
  red: "Rojo",
  green: "Verde",
  yellow: "Amarillo",
  blue: "Azul"
};

const conn = $("conn");
const entry = $("entry");
const game = $("game");
const nameInput = $("name");
const join = $("join");
const start = $("start");
const roll = $("roll");
const pass = $("pass");
const notice = $("notice");
const who = $("who");
const status = $("status");
const players = $("players");
const dice = $("dice");
const tokens = $("tokens");

s.on("connect", () => {
  if (conn) conn.textContent = "Conectado";
});

s.on("disconnect", () => {
  if (conn) conn.textContent = "Desconectado";
});

s.on("connect_error", () => {
  if (conn) conn.textContent = "Error de conexión";
  if (notice) {
    notice.textContent =
      "No se pudo conectar al servidor. Recarga la página.";
  }
});

s.on("joined", (p) => {
  me = p;

  if (entry) entry.hidden = true;
  if (game) game.hidden = false;

  render();
});

s.on("state", (data) => {
  st = data;
  render();
});

s.on("notice", (message) => {
  if (notice) notice.textContent = message;
});

// BOTÓN ENTRAR
if (join) {
  join.addEventListener("click", () => {
    const playerName = nameInput
      ? nameInput.value.trim()
      : "";

    if (!playerName) {
      if (notice) notice.textContent = "Escribe tu nombre.";
      if (nameInput) nameInput.focus();
      return;
    }

    if (!s.connected) {
      if (notice) {
        notice.textContent =
          "Conectando con el servidor. Espera unos segundos.";
      }
      return;
    }

    if (notice) notice.textContent = "Entrando a la partida...";

    s.emit("join", { name: playerName });
  });
}

// Permite entrar pulsando Enter en el teclado
if (nameInput) {
  nameInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && join) {
      join.click();
    }
  });
}

// BOTONES DEL JUEGO
if (start) {
  start.addEventListener("click", () => s.emit("start"));
}

if (roll) {
  roll.addEventListener("click", () => s.emit("roll"));
}

if (pass) {
  pass.addEventListener("click", () => s.emit("pass"));
}

function render() {
  if (!st || !me) return;

  if (who) {
    who.textContent =
      `Tu jugador: ${me.name} (${names[me.color] || me.color})`;
  }

  const connected = Object.values(st.connected || {});
  const active = connected.filter(Boolean).length;

  if (status) {
    if (st.winner) {
      status.textContent = `¡Ganó ${names[st.winner] || st.winner}!`;
    } else if (!st.started) {
      status.textContent =
        `Esperando jugadores (${active}/4). Comparte el enlace.`;
    } else {
      status.textContent =
        `Turno de ${names[st.current_turn] || st.current_turn}` +
        (st.current_turn === me.color ? " — te toca" : "");
    }
  }

  if (players) {
    players.innerHTML = (st.players || []).map((p) => `
      <div class="player">
        <span class="dot" style="background:${cs[p.color] || "#888"}"></span>
        ${esc(p.name)}${p.host ? " · anfitrión" : ""}
      </div>
    `).join("");
  }

  if (dice) {
    dice.textContent =
      st.dice_values && st.dice_values.length
        ? st.dice_values.join(" 🎲 ")
        : "🎲 🎲";
  }

  if (start) {
    start.hidden = !(me.host && !st.started);
    start.disabled = active < 2;
  }

  const myTurn =
    st.started &&
    st.current_turn === me.color &&
    !st.winner;

  if (roll) {
    roll.disabled = !(myTurn && !st.has_rolled);
  }

  if (pass) {
    pass.disabled = !(myTurn && st.has_rolled);
  }

  if (tokens) {
    tokens.innerHTML = (st.tokens || [])
      .filter((t) => t.color === me.color)
      .map((t) => `
        <button
          class="token"
          style="border-color:${cs[t.color] || "#888"}"
          ${!myTurn || !st.has_rolled ? "disabled" : ""}
          data-index="${t.index}">
          Ficha ${t.index + 1}<br>
          ${stateName(t.state, t.pos)}
        </button>
      `).join("");

    tokens.querySelectorAll("[data-index]").forEach((button) => {
      button.addEventListener("click", () => {
        s.emit("move", {
          index: Number(button.dataset.index)
        });
      });
    });
  }
}

function stateName(state, position) {
  if (state === "base") return "En la base";
  if (state === "done") return "Llegó a la meta";
  if (state === "home") return "Carril final " + position;
  return "Casilla " + position;
}

function esc(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}
