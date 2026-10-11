import pygame
import sys
import random
import array
import math

from juego_logica import compute_steps  # reglas de movimiento compartidas con el servidor

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)

# ----- GENERADOR DE SONIDOS SINTÉTICOS -----
def generate_sound(frequency, duration, volume=0.1):
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    buf = array.array('h')
    for i in range(n_samples):
        t = float(i) / sample_rate
        if int(t * frequency * 2) % 2 == 0:
            buf.append(int(32767 * volume))
        else:
            buf.append(-int(32767 * volume))
    return pygame.mixer.Sound(buffer=buf)

# Crear sonidos
snd_roll = generate_sound(600, 0.05, 0.05)
snd_move = generate_sound(400, 0.1, 0.1)
snd_capture = generate_sound(150, 0.3, 0.2)
snd_win = generate_sound(800, 0.5, 0.2)
snd_error = generate_sound(100, 0.1, 0.1)

# Configuraciones de la ventana: el tamaño de celda se calcula según el
# tamaño disponible, para que SIEMPRE quepa completa (incluyendo los
# botones de abajo). Además la ventana es redimensionable (arrastrando
# el borde) y el tablero se reacomoda solo -> apply_resize().
try:
    screen_w, screen_h = pygame.display.get_desktop_sizes()[0]
except Exception:
    info = pygame.display.Info()
    screen_w, screen_h = info.current_w, info.current_h

GRID_SIZE = 15
TOP_MARGIN = 50        # espacio para el título "Turno: ..."
BOTTOM_UI = 230         # espacio para dados + botones
SIDE_MARGIN = 60        # aire a los costados del tablero
MIN_CELL = 22
MAX_CELL = 56
MIN_WINDOW_W = 380
MIN_WINDOW_H = 520


def compute_cell_size(avail_w, avail_h):
    h_budget = avail_h - TOP_MARGIN - BOTTOM_UI
    w_budget = avail_w - SIDE_MARGIN
    return max(MIN_CELL, min(MAX_CELL, h_budget // GRID_SIZE, w_budget // GRID_SIZE))


# Tamaño inicial: el más grande que quepa en la pantalla (con aire para
# la barra de tareas / barra de título del sistema operativo).
CELL_SIZE = compute_cell_size(screen_w - 60, screen_h - 120)
WIDTH = GRID_SIZE * CELL_SIZE + SIDE_MARGIN
HEIGHT = TOP_MARGIN + GRID_SIZE * CELL_SIZE + BOTTOM_UI
BOARD_OFFSET_X = (WIDTH - (GRID_SIZE * CELL_SIZE)) // 2
BOARD_OFFSET_Y = TOP_MARGIN

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Juego de Parqués - Avanzado + Sonidos")


def apply_resize(new_w, new_h):
    """Se llama cuando el usuario arrastra el borde de la ventana: recalcula
    el tamaño de celda y vuelve a centrar el tablero en el nuevo espacio."""
    global WIDTH, HEIGHT, CELL_SIZE, BOARD_OFFSET_X, BOARD_OFFSET_Y, screen
    new_w = max(MIN_WINDOW_W, new_w)
    new_h = max(MIN_WINDOW_H, new_h)
    WIDTH, HEIGHT = new_w, new_h
    CELL_SIZE = compute_cell_size(WIDTH, HEIGHT)
    BOARD_OFFSET_X = (WIDTH - GRID_SIZE * CELL_SIZE) // 2
    extra_v = max(0, HEIGHT - TOP_MARGIN - GRID_SIZE * CELL_SIZE - BOTTOM_UI)
    BOARD_OFFSET_Y = TOP_MARGIN + extra_v // 2
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)


# Colores
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
SAFE_COLOR = (148, 163, 184)
SAFE_STAR_COLOR = (250, 204, 21)  # dorado para marcar bien las casillas de seguro

font = pygame.font.SysFont('Arial', 28, bold=True)
big_font = pygame.font.SysFont('Arial', 40, bold=True)
small_font = pygame.font.SysFont('Arial', 20, bold=True)

# ----------------- LOGICA DEL TABLERO -----------------
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

class Token:
    def __init__(self, color, index):
        self.color = color
        self.index = index
        self.state = 'base' # 'base', 'path', 'home', 'done'
        self.pos = -1
        
    def get_pixel_coords(self, state=None, pos=None):
        # Con state/pos se calcula dónde se dibujaría la ficha en OTRA casilla
        # (lo usa la animación para los saltos intermedios).
        state = self.state if state is None else state
        pos = self.pos if pos is None else pos
        if state == 'base':
            offset_row, offset_col = BASE_COORDS[self.color][self.index]
            x = BOARD_OFFSET_X + offset_col * CELL_SIZE + (CELL_SIZE if self.color in ['red','blue'] else 0) + (CELL_SIZE//2)
            y = BOARD_OFFSET_Y + offset_row * CELL_SIZE + (CELL_SIZE if self.color in ['red','green'] else 0) + (CELL_SIZE//2)
            if self.color in ['green', 'yellow']: x += CELL_SIZE * 2
            if self.color in ['blue', 'yellow']: y += CELL_SIZE * 2
            return (x, y)
        elif state == 'path':
            r, c = PATH[pos]
            return (BOARD_OFFSET_X + c * CELL_SIZE + CELL_SIZE//2, BOARD_OFFSET_Y + r * CELL_SIZE + CELL_SIZE//2)
        elif state == 'home':
            r, c = HOME_PATHS[self.color][pos]
            return (BOARD_OFFSET_X + c * CELL_SIZE + CELL_SIZE//2, BOARD_OFFSET_Y + r * CELL_SIZE + CELL_SIZE//2)
        elif state == 'done':
            r, c = HOME_PATHS[self.color][-1]
            offsets = [(-10,-10), (10,-10), (-10,10), (10,10)]
            ox, oy = offsets[self.index]
            return (BOARD_OFFSET_X + c * CELL_SIZE + CELL_SIZE//2 + ox, BOARD_OFFSET_Y + r * CELL_SIZE + CELL_SIZE//2 + oy)
        return (0, 0)

tokens = []
for color in ['red', 'green', 'yellow', 'blue']:
    for i in range(4):
        tokens.append(Token(color, i))

dice_values = [0, 0]
remaining_moves = []
dice_rolling = False
roll_frames = 0
current_turn = 'red'
colors_order = ['red', 'green', 'yellow', 'blue']
has_rolled = False

auto_pass_frames = 0

# Animación de movimiento: la ficha salta casilla por casilla.
# anim = {'token', 'steps', 'die_index', 'hop', 'frame'} mientras hay una ficha en movimiento.
anim = None
HOP_FRAMES = 7  # cuadros por salto (a 30 fps, ~0.23 s por casilla)

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
        pygame.draw.rect(screen, c_val, pygame.Rect(BOARD_OFFSET_X + bc*CELL_SIZE, BOARD_OFFSET_Y + br*CELL_SIZE, 6*CELL_SIZE, 6*CELL_SIZE), border_radius=15)
        
    for i, (r, c) in enumerate(PATH):
        color = CELL_BG
        is_safe = i in SAFE_SPACES
        if is_safe: color = SAFE_COLOR
        cell_x = BOARD_OFFSET_X + c*CELL_SIZE
        cell_y = BOARD_OFFSET_Y + r*CELL_SIZE
        pygame.draw.rect(screen, color, pygame.Rect(cell_x, cell_y, CELL_SIZE, CELL_SIZE))
        pygame.draw.rect(screen, CELL_BORDER, pygame.Rect(cell_x, cell_y, CELL_SIZE, CELL_SIZE), 1)
        if is_safe:
            draw_star(screen, (cell_x + CELL_SIZE//2, cell_y + CELL_SIZE//2), CELL_SIZE*0.32, CELL_SIZE*0.14, SAFE_STAR_COLOR)

    for color, path in HOME_PATHS.items():
        c_val = {'red':RED, 'green':GREEN, 'yellow':YELLOW, 'blue':BLUE}[color]
        for r, c in path:
            pygame.draw.rect(screen, c_val, pygame.Rect(BOARD_OFFSET_X + c*CELL_SIZE, BOARD_OFFSET_Y + r*CELL_SIZE, CELL_SIZE, CELL_SIZE))
            pygame.draw.rect(screen, CELL_BORDER, pygame.Rect(BOARD_OFFSET_X + c*CELL_SIZE, BOARD_OFFSET_Y + r*CELL_SIZE, CELL_SIZE, CELL_SIZE), 1)
            
    center_rect = pygame.Rect(BOARD_OFFSET_X + 6*CELL_SIZE, BOARD_OFFSET_Y + 6*CELL_SIZE, 3*CELL_SIZE, 3*CELL_SIZE)
    pygame.draw.rect(screen, WHITE, center_rect)

def animated_token_position():
    """(x, y, altura_del_salto) de la ficha que se está moviendo, o None."""
    if anim is None:
        return None
    t = anim['token']
    steps = anim['steps']
    hop = anim['hop']
    if hop == 0:
        x0, y0 = t.get_pixel_coords()
    else:
        x0, y0 = t.get_pixel_coords(*steps[hop - 1])
    x1, y1 = t.get_pixel_coords(*steps[hop])
    p = anim['frame'] / HOP_FRAMES
    lift = math.sin(math.pi * p) * CELL_SIZE * 0.35
    return (x0 + (x1 - x0) * p, y0 + (y1 - y0) * p, lift)

def draw_token_circle(x, y, color_name, lift=0):
    c_val = {'red':RED, 'green':GREEN, 'yellow':YELLOW, 'blue':BLUE}[color_name]
    radius = CELL_SIZE // 2 - 4
    if lift > 0:
        # sombra en el suelo para dar sensación de salto
        shadow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 70), (radius * 0.2, radius * 0.9, radius * 1.6, radius * 0.7))
        screen.blit(shadow, (x - radius, y - radius))
    pygame.draw.circle(screen, c_val, (x, y - lift), radius)
    pygame.draw.circle(screen, WHITE, (x, y - lift), radius, 2)

def draw_tokens():
    moving = anim['token'] if anim is not None else None
    spot_counts = {}
    for t in tokens:
        if t is moving:
            continue
        if t.state in ['path', 'home']:
            key = (t.state, t.pos)
            if key not in spot_counts: spot_counts[key] = []
            spot_counts[key].append(t)

    for t in tokens:
        if t is moving:
            continue
        x, y = t.get_pixel_coords()
        if t.state in ['path', 'home']:
            key = (t.state, t.pos)
            count = len(spot_counts[key])
            if count > 1:
                idx = spot_counts[key].index(t)
                offsets = [(-5,-5), (5,-5), (-5,5), (5,5)]
                x += offsets[idx % 4][0]
                y += offsets[idx % 4][1]

        draw_token_circle(x, y, t.color)

    # La ficha en movimiento se dibuja al final para que quede por encima de las demás
    pos = animated_token_position()
    if pos is not None:
        draw_token_circle(pos[0], pos[1], moving.color, lift=pos[2])

def capture_at(pos_index, exempt_color):
    if pos_index in SAFE_SPACES: return False
    captured = False
    for t in tokens:
        if t.state == 'path' and t.pos == pos_index and t.color != exempt_color:
            t.state = 'base'
            t.pos = -1
            captured = True
    if captured:
        snd_capture.play()
    return captured

def is_double_roll():
    return dice_values[0] == dice_values[1] and dice_values[0] != 0

def steps_for(token, die_val):
    """Casillas que recorrería la ficha con este dado (None si no puede moverse).
    Con cualquier doble se puede sacar una ficha de la base."""
    return compute_steps(token.color, token.state, token.pos, die_val, is_double_roll())

def apply_final_position(token, steps):
    """Deja la ficha en su casilla final; aquí se aplican capturas y llegada a la meta."""
    token.state, token.pos = steps[-1]
    if token.state == 'path':
        capture_at(token.pos, token.color)
    elif token.state == 'done':
        snd_win.play()

def try_move_token(token, die_val, apply=True):
    steps = steps_for(token, die_val)
    if not steps:
        return False
    if apply:
        apply_final_position(token, steps)
    return True

def has_valid_moves():
    for token in tokens:
        if token.color == current_turn:
            for d in remaining_moves:
                if try_move_token(token, d, apply=False):
                    return True
    return False

def handle_token_click(pos):
    """Inicia la animación de la ficha clicada; la jugada se aplica al terminar de saltar."""
    global anim
    if anim is not None or not has_rolled or len(remaining_moves) == 0: return False

    for token in tokens:
        if token.color == current_turn:
            tx, ty = token.get_pixel_coords()
            if (tx - pos[0])**2 + (ty - pos[1])**2 < (CELL_SIZE//2)**2:
                for i, d in enumerate(remaining_moves):
                    steps = steps_for(token, d)
                    if steps:
                        anim = {'token': token, 'steps': steps, 'die_index': i, 'hop': 0, 'frame': 0}
                        return True
                snd_error.play()
                return True
    return False

def update_animation():
    """Avanza un cuadro la animación; al llegar a cada casilla suena un toque,
    y al llegar a la última se aplica la jugada."""
    global anim
    if anim is None: return
    anim['frame'] += 1
    if anim['frame'] >= HOP_FRAMES:
        anim['frame'] = 0
        anim['hop'] += 1
        snd_move.play()
        if anim['hop'] >= len(anim['steps']):
            finish_animation()

def finish_animation():
    global anim
    token, steps, die_index = anim['token'], anim['steps'], anim['die_index']
    anim = None
    apply_final_position(token, steps)
    remaining_moves.pop(die_index)
    # Si el jugador metió su última ficha, se queda el turno para mostrar "HA GANADO"
    if not all_done(token.color):
        check_turn_end()

def check_turn_end():
    global current_turn, has_rolled, remaining_moves, dice_values
    if len(remaining_moves) == 0:
        if dice_values[0] == dice_values[1] and dice_values[0] != 0:
            has_rolled = False
            dice_values = [0, 0]
        else:
            next_turn()

def next_turn():
    global current_turn, has_rolled, remaining_moves, dice_values, auto_pass_frames
    idx = colors_order.index(current_turn)
    current_turn = colors_order[(idx + 1) % 4]
    has_rolled = False
    remaining_moves = []
    dice_values = [0, 0]
    auto_pass_frames = 0

def all_done(color):
    return all(t.state == 'done' for t in tokens if t.color == color)

def main():
    global dice_values, remaining_moves, dice_rolling, roll_frames, current_turn, has_rolled, auto_pass_frames
    clock = pygame.time.Clock()
    running = True

    while running:
        # Los botones se recalculan cada cuadro con el WIDTH/HEIGHT actual,
        # así siempre quedan bien ubicados aunque se haya redimensionado la ventana.
        btn_rect = pygame.Rect(WIDTH // 2 - 120, HEIGHT - 120, 240, 60)
        pass_rect = pygame.Rect(WIDTH // 2 - 120, HEIGHT - 40, 240, 30)

        update_animation()
        screen.fill(BG_COLOR)
        draw_board_static()
        draw_tokens()
        
        if all_done(current_turn):
            win_title = big_font.render(f"¡{current_turn.upper()} HA GANADO!", True, WHITE)
            screen.blit(win_title, (WIDTH // 2 - win_title.get_width() // 2, 10))
        else:
            title = big_font.render(f"Turno: {current_turn.upper()}", True, {'red':RED,'green':GREEN,'yellow':YELLOW,'blue':BLUE}[current_turn])
            screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 10))
            
            if not has_rolled:
                pygame.draw.rect(screen, BLUE, btn_rect, border_radius=10)
                btn_text = font.render("Lanzar Dados", True, WHITE)
                screen.blit(btn_text, (btn_rect.centerx - btn_text.get_width() // 2, btn_rect.centery - btn_text.get_height() // 2))
            
            if has_rolled and len(remaining_moves) > 0:
                pygame.draw.rect(screen, RED, pass_rect, border_radius=5)
                pass_text = small_font.render("Siguiente Jugador", True, WHITE)
                screen.blit(pass_text, (pass_rect.centerx - pass_text.get_width() // 2, pass_rect.centery - pass_text.get_height() // 2))
            
            for i, val in enumerate(dice_values):
                die_rect = pygame.Rect(WIDTH // 2 - 90 + (i * 100), HEIGHT - 220, 80, 80)
                pygame.draw.rect(screen, WHITE, die_rect, border_radius=12)
                if val > 0 or dice_rolling:
                    display_val = random.randint(1, 6) if dice_rolling else val
                    die_text = big_font.render(str(display_val), True, BLACK)
                    screen.blit(die_text, (die_rect.centerx - die_text.get_width() // 2, die_rect.centery - die_text.get_height() // 2))

            if dice_rolling:
                if roll_frames % 5 == 0: snd_roll.play()
                roll_frames += 1
                if roll_frames > 20:
                    dice_rolling = False
                    d1, d2 = random.randint(1, 6), random.randint(1, 6)
                    dice_values = [d1, d2]
                    remaining_moves = [d1, d2]
                    has_rolled = True
                    auto_pass_frames = 0
            
            if has_rolled and len(remaining_moves) > 0 and not dice_rolling and anim is None:
                if not has_valid_moves():
                    auto_pass_frames += 1
                    # Esperar 1.5 segundos (45 frames) antes de pasar automáticamente
                    if auto_pass_frames > 45:
                        remaining_moves = []
                        check_turn_end()
                else:
                    auto_pass_frames = 0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                apply_resize(event.w, event.h)
            elif event.type == pygame.MOUSEBUTTONDOWN and not all_done(current_turn):
                if not has_rolled and btn_rect.collidepoint(event.pos) and not dice_rolling:
                    dice_rolling = True
                    roll_frames = 0
                elif has_rolled and anim is None and pass_rect.collidepoint(event.pos):
                    next_turn()
                elif has_rolled and not dice_rolling:
                    handle_token_click(event.pos)

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
