"""
Lógica pura del Juego de Parqués (sin pygame, sin dibujo).

Este módulo lo usan TANTO el servidor (como árbitro/autoridad del juego)
COMO el cliente (para conocer las coordenadas del tablero y dibujar).

Toda la validación de reglas vive en GameState. El servidor es el único
que ejecuta estos métodos con apply=True; el cliente solo los usa
(si acaso) para saber qué es legal antes de mandarle el mensaje al
servidor, pero el servidor SIEMPRE vuelve a validar.
"""

# ----------------- DATOS DEL TABLERO (idénticos a main.py) -----------------

PATH = [
    (6,0), (6,1), (6,2), (6,3), (6,4), (6,5), # 0 - 5
    (5,6), (4,6), (3,6), (2,6), (1,6), (0,6), # 6 - 11
    (0,7), (0,8),                             # 12 - 13
    (1,8), (2,8), (3,8), (4,8), (5,8),        # 14 - 18
    (6,9), (6,10), (6,11), (6,12), (6,13), (6,14), # 19 - 24
    (7,14), (8,14),                           # 25 - 26
    (8,13), (8,12), (8,11), (8,10), (8,9),    # 27 - 31
    (9,8), (10,8), (11,8), (12,8), (13,8), (14,8), # 32 - 37
    (14,7), (14,6),                           # 38 - 39
    (13,6), (12,6), (11,6), (10,6), (9,6),    # 40 - 44
    (8,5), (8,4), (8,3), (8,2), (8,1), (8,0), # 45 - 50
    (7,0)                                     # 51
]

HOME_PATHS = {
    'red': [(7,1), (7,2), (7,3), (7,4), (7,5), (7,6)],
    'green': [(1,7), (2,7), (3,7), (4,7), (5,7), (6,7)],
    'yellow': [(7,13), (7,12), (7,11), (7,10), (7,9), (7,8)],
    'blue': [(13,7), (12,7), (11,7), (10,7), (9,7), (8,7)]
}

STARTS = {'red': 1, 'green': 14, 'yellow': 27, 'blue': 40}
END_POS = {'red': 0, 'green': 13, 'yellow': 26, 'blue': 39}
SAFE_SPACES = [1, 10, 14, 23, 27, 36, 40, 49]

BASE_COORDS = {
    'red': [(0,0), (0,1), (1,0), (1,1)],
    'green': [(0,9), (0,10), (1,9), (1,10)],
    'blue': [(9,0), (9,1), (10,0), (10,1)],
    'yellow': [(9,9), (9,10), (10,9), (10,10)]
}

COLORS_ORDER = ['red', 'green', 'yellow', 'blue']


def compute_steps(color, state, pos, die_val, doubles):
    """Casillas que recorre una ficha al usar un dado, una por una.

    Devuelve una lista de (estado, posición), una entrada por cada salto
    (la última es donde queda la ficha), o None si la jugada no es válida.
    `doubles` indica si en esta tirada salieron dos dados iguales: con
    cualquier doble se puede sacar una ficha de la base (cada dado saca una).
    """
    if state == 'base':
        return [('path', STARTS[color])] if doubles else None

    if state == 'path':
        end = END_POS[color]
        dist_to_end = 0 if pos == end else (end - pos) % 52
        if die_val <= dist_to_end:
            return [('path', (pos + k) % 52) for k in range(1, die_val + 1)]
        home_steps = die_val - dist_to_end
        if home_steps > 7:
            return None
        steps = [('path', (pos + k) % 52) for k in range(1, dist_to_end + 1)]
        steps += [('home', h) for h in range(min(home_steps, 6))]
        if home_steps == 7:
            steps.append(('done', 0))
        return steps

    if state == 'home':
        new_pos = pos + die_val
        if new_pos > 6:
            return None
        steps = [('home', p) for p in range(pos + 1, min(new_pos, 5) + 1)]
        if new_pos == 6:
            steps.append(('done', 0))
        return steps

    return None


class Token:
    def __init__(self, color, index):
        self.color = color
        self.index = index
        self.state = 'base'  # 'base', 'path', 'home', 'done'
        self.pos = -1

    def to_dict(self):
        return {"color": self.color, "index": self.index, "state": self.state, "pos": self.pos}

    @staticmethod
    def from_dict(d):
        t = Token(d["color"], d["index"])
        t.state = d["state"]
        t.pos = d["pos"]
        return t


class GameState:
    """Estado autoritativo de una partida. El servidor es el único que
    debe llamar a los métodos que cambian el estado; el cliente solo lee."""

    def __init__(self):
        self.tokens = [Token(c, i) for c in COLORS_ORDER for i in range(4)]
        self.connected = {c: False for c in COLORS_ORDER}  # color -> ¿hay jugador humano?
        self.current_turn = 'red'
        self.dice_values = [0, 0]
        self.remaining_moves = []
        self.has_rolled = False
        self.started = False
        self.winner = None
        self.last_event = ""  # texto corto para mostrar en el cliente ("Sin jugadas, pasa turno", etc.)
        self.move_seq = 0      # cuenta jugadas; los clientes lo usan para saber cuándo animar
        self.last_move = None  # {"seq", "color", "index", "from", "steps", "captured"}

    # ---------- utilidades de turno ----------

    def active_colors(self):
        return [c for c in COLORS_ORDER if self.connected[c]]

    def next_connected_color(self, from_color):
        if not self.active_colors():
            return from_color
        idx = COLORS_ORDER.index(from_color)
        for step in range(1, 5):
            cand = COLORS_ORDER[(idx + step) % 4]
            if self.connected[cand]:
                return cand
        return from_color

    def tokens_of(self, color):
        return [t for t in self.tokens if t.color == color]

    def all_done(self, color):
        return all(t.state == 'done' for t in self.tokens_of(color))

    # ---------- reglas de movimiento (idénticas a main.py) ----------

    def is_double(self):
        return self.dice_values[0] == self.dice_values[1] and self.dice_values[0] != 0

    def capture_at(self, pos_index, exempt_color):
        """Devuelve la lista de fichas que mandó de vuelta a la base."""
        captured = []
        if pos_index in SAFE_SPACES:
            return captured
        for t in self.tokens:
            if t.state == 'path' and t.pos == pos_index and t.color != exempt_color:
                t.state = 'base'
                t.pos = -1
                captured.append({"color": t.color, "index": t.index})
        return captured

    def steps_for(self, token, die_val):
        return compute_steps(token.color, token.state, token.pos, die_val, self.is_double())

    def try_move_token(self, token, die_val, apply=True):
        steps = self.steps_for(token, die_val)
        if not steps:
            return False
        if apply:
            self.apply_steps(token, steps)
        return True

    def apply_steps(self, token, steps):
        """Deja la ficha en la última casilla del recorrido y aplica capturas."""
        token.state, token.pos = steps[-1]
        if token.state == 'path':
            return self.capture_at(token.pos, token.color)
        return []

    def has_valid_moves(self):
        for token in self.tokens_of(self.current_turn):
            for d in self.remaining_moves:
                if self.try_move_token(token, d, apply=False):
                    return True
        return False

    def next_turn(self):
        self.current_turn = self.next_connected_color(self.current_turn)
        self.has_rolled = False
        self.remaining_moves = []
        self.dice_values = [0, 0]

    def check_turn_end(self):
        if len(self.remaining_moves) == 0:
            if self.dice_values[0] == self.dice_values[1] and self.dice_values[0] != 0:
                # dobles: tira otra vez el mismo jugador
                self.has_rolled = False
                self.dice_values = [0, 0]
            else:
                self.next_turn()

    def check_winner(self):
        if self.all_done(self.current_turn):
            self.winner = self.current_turn

    # ---------- acciones que llegan por red ----------

    def action_roll(self, color, d1, d2):
        """El servidor ya tiró los dados (d1,d2) con random; aquí solo se aplica.
        Devuelve True si no hay ninguna jugada posible (el servidor debe
        esperar un momento mostrando los dados y luego llamar a
        finish_stuck_turn para pasar el turno)."""
        if self.winner or color != self.current_turn or self.has_rolled:
            return False
        self.dice_values = [d1, d2]
        self.remaining_moves = [d1, d2]
        self.has_rolled = True
        self.last_event = ""
        if not self.has_valid_moves():
            self.last_event = "Sin jugadas posibles: turno pasa."
            return True
        return False

    def finish_stuck_turn(self, color):
        """Pasa el turno tras una tirada sin jugadas posibles, solo si el
        estado no cambió mientras tanto (nadie pudo mover, pero por las
        dudas se valida)."""
        if self.winner or color != self.current_turn or not self.has_rolled:
            return
        self.remaining_moves = []
        self.check_turn_end()

    def action_move(self, color, token_color, token_index):
        if self.winner or color != self.current_turn or not self.has_rolled:
            return False
        if color != token_color:
            return False
        token = next((t for t in self.tokens if t.color == token_color and t.index == token_index), None)
        if token is None:
            return False
        for i, d in enumerate(self.remaining_moves):
            steps = self.steps_for(token, d)
            if steps:
                origin = [token.state, token.pos]
                captured = self.apply_steps(token, steps)
                self.move_seq += 1
                self.last_move = {
                    "seq": self.move_seq,
                    "color": token.color,
                    "index": token.index,
                    "from": origin,
                    "steps": [list(s) for s in steps],
                    "captured": captured,
                }
                self.remaining_moves.pop(i)
                self.last_event = ""
                self.check_winner()
                if not self.winner:
                    self.check_turn_end()
                return True
        return False

    def action_pass(self, color):
        if self.winner or color != self.current_turn or not self.has_rolled:
            return
        self.next_turn()

    # ---------- serialización para mandar por la red ----------

    def to_dict(self):
        return {
            "tokens": [t.to_dict() for t in self.tokens],
            "connected": self.connected,
            "current_turn": self.current_turn,
            "dice_values": self.dice_values,
            "remaining_moves": self.remaining_moves,
            "has_rolled": self.has_rolled,
            "started": self.started,
            "winner": self.winner,
            "last_event": self.last_event,
            "move_seq": self.move_seq,
            "last_move": self.last_move,
        }

    def load_dict(self, d):
        self.tokens = [Token.from_dict(td) for td in d["tokens"]]
        self.connected = d["connected"]
        self.current_turn = d["current_turn"]
        self.dice_values = d["dice_values"]
        self.remaining_moves = d["remaining_moves"]
        self.has_rolled = d["has_rolled"]
        self.started = d["started"]
        self.winner = d["winner"]
        self.last_event = d.get("last_event", "")
        self.move_seq = d.get("move_seq", 0)
        self.last_move = d.get("last_move")
