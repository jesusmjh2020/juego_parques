"""
Cliente multijugador del Juego de Parqués (LAN).

Uso:
    python cliente.py

Te pide la IP del servidor (la que imprime servidor.py) y tu nombre,
te asigna un color y juegas contra los demás conectados en la red.
"""
import json
import math
import socket
import sys
import threading
import queue

import pygame

from juego_logica import PATH, HOME_PATHS, STARTS, SAFE_SPACES, BASE_COORDS, COLORS_ORDER

DEFAULT_PORT = 5555

pygame.init()

# El tamaño de celda se calcula según el espacio disponible, para que la
# ventana SIEMPRE quepa completa (incluyendo el botón de "Iniciar partida"
# y los dados). Además es redimensionable: apply_resize() reacomoda todo
# cuando el usuario arrastra el borde de la ventana.
try:
    screen_w, screen_h = pygame.display.get_desktop_sizes()[0]
except Exception:
    info = pygame.display.Info()
    screen_w, screen_h = info.current_w, info.current_h

GRID_SIZE = 15
TOP_MARGIN = 60         # espacio para "Eres: X" + título de turno
BOTTOM_UI = 220          # espacio para dados + botones (roll/pasar/iniciar)
SIDE_MARGIN = 60
MIN_CELL = 22
MAX_CELL = 56
MIN_WINDOW_W = 380
MIN_WINDOW_H = 520


def compute_cell_size(avail_w, avail_h):
    h_budget = avail_h - TOP_MARGIN - BOTTOM_UI
    w_budget = avail_w - SIDE_MARGIN
    return max(MIN_CELL, min(MAX_CELL, h_budget // GRID_SIZE, w_budget // GRID_SIZE))


CELL_SIZE = compute_cell_size(screen_w - 60, screen_h - 120)
WIDTH = GRID_SIZE * CELL_SIZE + SIDE_MARGIN
HEIGHT = TOP_MARGIN + GRID_SIZE * CELL_SIZE + BOTTOM_UI
BOARD_OFFSET_X = (WIDTH - GRID_SIZE * CELL_SIZE) // 2
BOARD_OFFSET_Y = TOP_MARGIN

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Juego de Parqués - Multijugador")


def apply_resize(new_w, new_h):
    """Se llama al arrastrar el borde de la ventana: recalcula el tamaño
    de celda y vuelve a centrar el tablero en el nuevo espacio."""
    global WIDTH, HEIGHT, CELL_SIZE, BOARD_OFFSET_X, BOARD_OFFSET_Y, screen
    new_w = max(MIN_WINDOW_W, new_w)
    new_h = max(MIN_WINDOW_H, new_h)
    WIDTH, HEIGHT = new_w, new_h
    CELL_SIZE = compute_cell_size(WIDTH, HEIGHT)
    BOARD_OFFSET_X = (WIDTH - GRID_SIZE * CELL_SIZE) // 2
    extra_v = max(0, HEIGHT - TOP_MARGIN - GRID_SIZE * CELL_SIZE - BOTTOM_UI)
    BOARD_OFFSET_Y = TOP_MARGIN + extra_v // 2
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)


BG_COLOR = (15, 23, 42)
BOARD_BG = (30, 41, 59)
CELL_BG = (51, 65, 85)
CELL_BORDER = (71, 85, 105)
RED = (239, 68, 68)
GREEN = (34, 197, 94)
BLUE = (59, 130, 246)
YELLOW = (234, 179, 8)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (100, 116, 139)
SAFE_COLOR = (148, 163, 184)
SAFE_STAR_COLOR = (250, 204, 21)  # dorado para marcar bien las casillas de seguro
COLOR_MAP = {'red': RED, 'green': GREEN, 'yellow': YELLOW, 'blue': BLUE}

font = pygame.font.SysFont('Arial', 26, bold=True)
big_font = pygame.font.SysFont('Arial', 38, bold=True)
small_font = pygame.font.SysFont('Arial', 18, bold=True)


# ===================== RED =====================

class NetClient:
    def __init__(self):
        self.sock = None
        self.incoming = queue.Queue()
        self.connected = False

    def connect(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((host, port))
        self.sock.settimeout(None)
        self.connected = True
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        buf = b""
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        self.incoming.put(json.loads(line.decode("utf-8")))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        self.connected = False
        self.incoming.put({"type": "_disconnected"})

    def send(self, obj):
        if not self.connected:
            return
        try:
            self.sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        except OSError:
            self.connected = False


# ===================== DIBUJO DEL TABLERO =====================

def cell_px(r, c):
    return (BOARD_OFFSET_X + c * CELL_SIZE + CELL_SIZE // 2,
            BOARD_OFFSET_Y + r * CELL_SIZE + CELL_SIZE // 2)


def token_pixel_coords(t):
    if t["state"] == 'base':
        offset_row, offset_col = BASE_COORDS[t["color"]][t["index"]]
        x = BOARD_OFFSET_X + offset_col * CELL_SIZE + (CELL_SIZE if t["color"] in ['red', 'blue'] else 0) + (CELL_SIZE // 2)
        y = BOARD_OFFSET_Y + offset_row * CELL_SIZE + (CELL_SIZE if t["color"] in ['red', 'green'] else 0) + (CELL_SIZE // 2)
        if t["color"] in ['green', 'yellow']:
            x += CELL_SIZE * 2
        if t["color"] in ['blue', 'yellow']:
            y += CELL_SIZE * 2
        return (x, y)
    elif t["state"] == 'path':
        r, c = PATH[t["pos"]]
        return cell_px(r, c)
    elif t["state"] == 'home':
        r, c = HOME_PATHS[t["color"]][t["pos"]]
        return cell_px(r, c)
    elif t["state"] == 'done':
        r, c = HOME_PATHS[t["color"]][-1]
        offsets = [(-10, -10), (10, -10), (-10, 10), (10, 10)]
        ox, oy = offsets[t["index"]]
        x, y = cell_px(r, c)
        return (x + ox, y + oy)
    return (0, 0)


def draw_star(surface, center, outer_r, inner_r, color):
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = outer_r if i % 2 == 0 else inner_r
        x = center[0] + r * math.cos(angle)
        y = center[1] - r * math.sin(angle)
        points.append((x, y))
    pygame.draw.polygon(surface, color, points)
    pygame.draw.polygon(surface, (120, 90, 0), points, 1)


def draw_board_static():
    board_rect = pygame.Rect(BOARD_OFFSET_X, BOARD_OFFSET_Y, GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE)
    pygame.draw.rect(screen, BOARD_BG, board_rect)

    for c_name, c_val, br, bc in [('red', RED, 0, 0), ('green', GREEN, 0, 9), ('blue', BLUE, 9, 0), ('yellow', YELLOW, 9, 9)]:
        pygame.draw.rect(screen, c_val, pygame.Rect(BOARD_OFFSET_X + bc * CELL_SIZE, BOARD_OFFSET_Y + br * CELL_SIZE, 6 * CELL_SIZE, 6 * CELL_SIZE), border_radius=15)

    for i, (r, c) in enumerate(PATH):
        is_safe = i in SAFE_SPACES
        color = SAFE_COLOR if is_safe else CELL_BG
        cell_x = BOARD_OFFSET_X + c * CELL_SIZE
        cell_y = BOARD_OFFSET_Y + r * CELL_SIZE
        pygame.draw.rect(screen, color, pygame.Rect(cell_x, cell_y, CELL_SIZE, CELL_SIZE))
        pygame.draw.rect(screen, CELL_BORDER, pygame.Rect(cell_x, cell_y, CELL_SIZE, CELL_SIZE), 1)
        if is_safe:
            draw_star(screen, (cell_x + CELL_SIZE // 2, cell_y + CELL_SIZE // 2), CELL_SIZE * 0.32, CELL_SIZE * 0.14, SAFE_STAR_COLOR)

    for color, path in HOME_PATHS.items():
        c_val = COLOR_MAP[color]
        for r, c in path:
            pygame.draw.rect(screen, c_val, pygame.Rect(BOARD_OFFSET_X + c * CELL_SIZE, BOARD_OFFSET_Y + r * CELL_SIZE, CELL_SIZE, CELL_SIZE))
            pygame.draw.rect(screen, CELL_BORDER, pygame.Rect(BOARD_OFFSET_X + c * CELL_SIZE, BOARD_OFFSET_Y + r * CELL_SIZE, CELL_SIZE, CELL_SIZE), 1)

    center_rect = pygame.Rect(BOARD_OFFSET_X + 6 * CELL_SIZE, BOARD_OFFSET_Y + 6 * CELL_SIZE, 3 * CELL_SIZE, 3 * CELL_SIZE)
    pygame.draw.rect(screen, WHITE, center_rect)


HOP_FRAMES = 7  # cuadros por salto (a 30 fps, ~0.23 s por casilla)


def draw_token_circle(x, y, color_name, lift=0):
    radius = CELL_SIZE // 2 - 4
    if lift > 0:
        # sombra en el suelo para dar sensación de salto
        shadow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 70), (radius * 0.2, radius * 0.9, radius * 1.6, radius * 0.7))
        screen.blit(shadow, (x - radius, y - radius))
    pygame.draw.circle(screen, COLOR_MAP[color_name], (x, y - lift), radius)
    pygame.draw.circle(screen, WHITE, (x, y - lift), radius, 2)


def draw_tokens(tokens, moving=None):
    """`moving` = (color, index, x, y, lift) de la ficha que está saltando; se
    dibuja encima de las demás y las otras no la cuentan para apilarse."""
    skip = (moving[0], moving[1]) if moving else None
    visible = [t for t in tokens if (t["color"], t["index"]) != skip]

    spot_counts = {}
    for t in visible:
        if t["state"] in ['path', 'home']:
            key = (t["state"], t["pos"])
            spot_counts.setdefault(key, []).append(t)

    for t in visible:
        x, y = token_pixel_coords(t)
        if t["state"] in ['path', 'home']:
            key = (t["state"], t["pos"])
            group = spot_counts[key]
            if len(group) > 1:
                idx = group.index(t)
                offsets = [(-5, -5), (5, -5), (-5, 5), (5, 5)]
                x += offsets[idx % 4][0]
                y += offsets[idx % 4][1]
        draw_token_circle(x, y, t["color"])

    if moving:
        draw_token_circle(moving[2], moving[3], moving[0], lift=moving[4])


class MoveAnimator:
    """Reproduce en pantalla, salto por salto, las jugadas que manda el servidor.

    El servidor envía el estado ya final de cada jugada junto con `last_move`
    (el recorrido casilla por casilla). Aquí se guardan en una cola y se
    muestran en orden: mientras una ficha salta, el resto del tablero se ve
    como estaba antes; al terminar se pasa al estado real.
    """

    def __init__(self):
        self.shown = None      # fichas tal como se ven ahora (lista de dicts)
        self.last_seq = None
        self.queue = []        # [(last_move, fichas_después_de_la_jugada)]
        self.current = None    # {'move', 'after', 'hop', 'frame'}

    @property
    def busy(self):
        return self.current is not None or bool(self.queue)

    def feed(self, state):
        seq = state.get("move_seq", 0)
        if self.last_seq is None:
            self.last_seq = seq          # primer estado: se muestra tal cual, sin animar
        elif seq > self.last_seq and state.get("last_move"):
            self.queue.append((state["last_move"], state["tokens"]))
        self.last_seq = seq
        if not self.busy:
            self.shown = state["tokens"]

    def update(self):
        """Avanza un cuadro; llamar una vez por cuadro de dibujo."""
        if self.current is None and self.queue:
            move, after = self.queue.pop(0)
            self.current = {"move": move, "after": after, "hop": 0, "frame": 0}
        c = self.current
        if c is None:
            return
        c["frame"] += 1
        if c["frame"] >= HOP_FRAMES:
            c["frame"] = 0
            c["hop"] += 1
            if c["hop"] >= len(c["move"]["steps"]):
                self.shown = c["after"]
                self.current = None

    def moving_token(self):
        """(color, index, x, y, lift) de la ficha en pleno salto, o None."""
        c = self.current
        if c is None:
            return None
        move, hop = c["move"], c["hop"]
        prev_state, prev_pos = move["from"] if hop == 0 else move["steps"][hop - 1]
        next_state, next_pos = move["steps"][hop]
        base = {"color": move["color"], "index": move["index"]}
        x0, y0 = token_pixel_coords({**base, "state": prev_state, "pos": prev_pos})
        x1, y1 = token_pixel_coords({**base, "state": next_state, "pos": next_pos})
        p = c["frame"] / HOP_FRAMES
        lift = math.sin(math.pi * p) * CELL_SIZE * 0.35
        return (move["color"], move["index"], x0 + (x1 - x0) * p, y0 + (y1 - y0) * p, lift)


# ===================== PANTALLAS DE TEXTO (conectar / lobby) =====================

def text_input_screen(prompt, default=""):
    """Pantalla simple para escribir un texto (IP, nombre, puerto). Devuelve el string."""
    value = default
    clock = pygame.time.Clock()
    while True:
        screen.fill(BG_COLOR)
        title = big_font.render(prompt, True, WHITE)
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 80))
        box = pygame.Rect(WIDTH // 2 - 180, HEIGHT // 2 - 10, 360, 50)
        pygame.draw.rect(screen, CELL_BG, box, border_radius=8)
        pygame.draw.rect(screen, WHITE, box, 2, border_radius=8)
        txt = font.render(value, True, WHITE)
        screen.blit(txt, (box.x + 12, box.y + 10))
        hint = small_font.render("Enter para confirmar", True, GRAY)
        screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT // 2 + 60))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.VIDEORESIZE:
                apply_resize(event.w, event.h)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN and value.strip():
                    return value.strip()
                elif event.key == pygame.K_BACKSPACE:
                    value = value[:-1]
                elif event.unicode and len(value) < 30:
                    value += event.unicode
        clock.tick(30)


def message_screen(lines, wait_seconds=None, allow_click=False):
    clock = pygame.time.Clock()
    frames = 0
    while True:
        screen.fill(BG_COLOR)
        y = HEIGHT // 2 - (len(lines) * 40) // 2
        for line, color in lines:
            surf = font.render(line, True, color)
            screen.blit(surf, (WIDTH // 2 - surf.get_width() // 2, y))
            y += 44
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.VIDEORESIZE:
                apply_resize(event.w, event.h)
            elif allow_click and event.type == pygame.MOUSEBUTTONDOWN:
                return
        frames += 1
        if wait_seconds and frames > wait_seconds * 30:
            return
        clock.tick(30)


# ===================== JUEGO PRINCIPAL =====================

def run_game(net, my_color, is_host):
    clock = pygame.time.Clock()
    state = None
    animator = MoveAnimator()

    error_msg = ""
    error_timer = 0

    running = True
    while running:
        # Se recalculan cada cuadro con el WIDTH/HEIGHT actual, así siguen
        # bien ubicados aunque se haya redimensionado la ventana.
        start_rect = pygame.Rect(WIDTH // 2 - 130, HEIGHT - 60, 260, 40)
        roll_rect = pygame.Rect(WIDTH // 2 - 120, HEIGHT - 130, 240, 55)
        pass_rect = pygame.Rect(WIDTH // 2 - 120, HEIGHT - 60, 240, 30)
        # Procesar mensajes de red llegados desde el hilo de escucha
        try:
            while True:
                msg = net.incoming.get_nowait()
                mtype = msg.get("type")
                if mtype == "state":
                    state = msg
                    animator.feed(msg)
                elif mtype == "error":
                    error_msg = msg.get("message", "")
                    error_timer = 90
                elif mtype == "_disconnected":
                    message_screen([("Se perdió la conexión con el servidor.", RED)], wait_seconds=3)
                    pygame.quit()
                    sys.exit()
        except queue.Empty:
            pass

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                apply_resize(event.w, event.h)
            elif event.type == pygame.MOUSEBUTTONDOWN and state:
                pos = event.pos
                if not state["started"]:
                    if is_host and start_rect.collidepoint(pos):
                        net.send({"type": "start"})
                elif not state["winner"] and not animator.busy:
                    my_turn = state["current_turn"] == my_color
                    if my_turn and not state["has_rolled"] and roll_rect.collidepoint(pos):
                        net.send({"type": "roll"})
                    elif my_turn and state["has_rolled"] and state["remaining_moves"] and pass_rect.collidepoint(pos):
                        net.send({"type": "pass"})
                    elif my_turn and state["has_rolled"] and state["remaining_moves"]:
                        for t in animator.shown:
                            if t["color"] != my_color:
                                continue
                            tx, ty = token_pixel_coords(t)
                            if (tx - pos[0]) ** 2 + (ty - pos[1]) ** 2 < (CELL_SIZE // 2) ** 2:
                                net.send({"type": "move", "token_index": t["index"]})
                                break

        # -------- dibujo --------
        animator.update()
        screen.fill(BG_COLOR)
        header = font.render(f"Eres: {my_color.upper()}", True, COLOR_MAP[my_color])
        screen.blit(header, (20, 15))

        if state is None:
            wait_txt = big_font.render("Conectando...", True, WHITE)
            screen.blit(wait_txt, (WIDTH // 2 - wait_txt.get_width() // 2, HEIGHT // 2))
        elif not state["started"]:
            players = [c for c in COLORS_ORDER if state["connected"][c]]
            title = big_font.render("Esperando jugadores...", True, WHITE)
            screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 60))
            for i, c in enumerate(players):
                line = font.render(f"• {c.capitalize()}", True, COLOR_MAP[c])
                screen.blit(line, (WIDTH // 2 - 60, 130 + i * 36))
            if is_host:
                enabled = len(players) >= 2
                pygame.draw.rect(screen, BLUE if enabled else GRAY, start_rect, border_radius=10)
                t = font.render("Iniciar partida", True, WHITE)
                screen.blit(t, (start_rect.centerx - t.get_width() // 2, start_rect.centery - t.get_height() // 2))
            else:
                info = font.render("Esperando a que el host inicie...", True, GRAY)
                screen.blit(info, (WIDTH // 2 - info.get_width() // 2, HEIGHT - 80))
        else:
            draw_board_static()
            draw_tokens(animator.shown, animator.moving_token())

            if state["winner"]:
                win_title = big_font.render(f"¡{state['winner'].upper()} HA GANADO!", True, WHITE)
                screen.blit(win_title, (WIDTH // 2 - win_title.get_width() // 2, 40))
            else:
                cur = state["current_turn"]
                turn_txt = "Tu turno" if cur == my_color else f"Turno: {cur.upper()}"
                title = big_font.render(turn_txt, True, COLOR_MAP[cur])
                screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 40))

                my_turn = cur == my_color
                if my_turn and not state["has_rolled"] and not animator.busy:
                    pygame.draw.rect(screen, BLUE, roll_rect, border_radius=10)
                    t = font.render("Lanzar Dados", True, WHITE)
                    screen.blit(t, (roll_rect.centerx - t.get_width() // 2, roll_rect.centery - t.get_height() // 2))
                if my_turn and state["has_rolled"] and state["remaining_moves"] and not animator.busy:
                    pygame.draw.rect(screen, RED, pass_rect, border_radius=5)
                    t = small_font.render("Pasar turno", True, WHITE)
                    screen.blit(t, (pass_rect.centerx - t.get_width() // 2, pass_rect.centery - t.get_height() // 2))

                for i, val in enumerate(state["dice_values"]):
                    die_rect = pygame.Rect(WIDTH // 2 - 90 + (i * 100), HEIGHT - 210, 80, 80)
                    pygame.draw.rect(screen, WHITE, die_rect, border_radius=12)
                    if val > 0:
                        die_text = big_font.render(str(val), True, BLACK)
                        screen.blit(die_text, (die_rect.centerx - die_text.get_width() // 2, die_rect.centery - die_text.get_height() // 2))

                if state.get("last_event"):
                    ev = small_font.render(state["last_event"], True, YELLOW)
                    screen.blit(ev, (WIDTH // 2 - ev.get_width() // 2, HEIGHT - 235))

        if error_timer > 0:
            err = small_font.render(error_msg, True, RED)
            screen.blit(err, (WIDTH // 2 - err.get_width() // 2, HEIGHT - 260))
            error_timer -= 1

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit()


def main():
    host = text_input_screen("IP del servidor (Enter para localhost)", default="localhost")
    port_str = text_input_screen("Puerto (Enter para 5555)", default=str(DEFAULT_PORT))
    try:
        port = int(port_str)
    except ValueError:
        port = DEFAULT_PORT
    name = text_input_screen("Tu nombre")

    net = NetClient()
    try:
        net.connect(host, port)
    except OSError as e:
        message_screen([("No se pudo conectar al servidor:", RED), (str(e), WHITE)], allow_click=True)
        pygame.quit()
        sys.exit()

    net.send({"type": "join", "name": name})

    # Esperar el mensaje de bienvenida (color asignado) antes de arrancar el loop principal
    my_color = None
    is_host = False
    while my_color is None:
        try:
            msg = net.incoming.get(timeout=5)
        except queue.Empty:
            message_screen([("El servidor no respondió.", RED)], allow_click=True)
            pygame.quit()
            sys.exit()
        if msg.get("type") == "welcome":
            my_color = msg["color"]
            is_host = msg.get("host", False)
        elif msg.get("type") == "full":
            message_screen([("La partida ya tiene 4 jugadores.", RED)], allow_click=True)
            pygame.quit()
            sys.exit()
        elif msg.get("type") == "error":
            message_screen([(msg.get("message", "Error"), RED)], allow_click=True)
            pygame.quit()
            sys.exit()

    run_game(net, my_color, is_host)


if __name__ == "__main__":
    main()
