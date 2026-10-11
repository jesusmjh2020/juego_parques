"""
Servidor multijugador del Juego de Parqués (LAN).

Uso:
    python servidor.py                  # escucha en el puerto 5555
    python servidor.py --puerto 6000

Corre en cualquier máquina de la red (no necesita pygame ni pantalla).
Los jugadores se conectan con `cliente.py` a la IP de esta máquina.

Protocolo: cada mensaje es un JSON en una línea (terminada en '\n'),
sobre un socket TCP normal.

Mensajes cliente -> servidor:
    {"type": "join", "name": "Ana"}
    {"type": "start"}                                  (solo el primero en unirse, el "host")
    {"type": "roll"}
    {"type": "move", "token_index": 0}
    {"type": "pass"}

Mensajes servidor -> cliente:
    {"type": "welcome", "color": "red", "host": true}
    {"type": "state", ...}                              (el estado completo de GameState.to_dict())
    {"type": "error", "message": "..."}
    {"type": "full"}                                     (servidor lleno, se cierra la conexión)
"""
import argparse
import json
import random
import socket
import threading
import sys

from juego_logica import GameState, COLORS_ORDER

DEFAULT_PORT = 5555


def local_ip():
    """IP de esta máquina en la red local, para compartir con los demás jugadores."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


class ClientHandler(threading.Thread):
    def __init__(self, conn, addr, server):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.server = server
        self.color = None
        self.name = None
        self.is_host = False

    def send(self, obj):
        try:
            self.conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        except OSError:
            pass

    def run(self):
        buf = b""
        try:
            while True:
                chunk = self.conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    self.server.handle_message(self, msg)
        except (ConnectionResetError, OSError):
            pass
        finally:
            self.server.on_disconnect(self)


class ParquesServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.state = GameState()
        self.clients = []  # ClientHandler
        self.lock = threading.RLock()

    def broadcast_state(self):
        payload = {"type": "state", **self.state.to_dict()}
        with self.lock:
            for c in self.clients:
                c.send(payload)

    def handle_message(self, client, msg):
        mtype = msg.get("type")
        with self.lock:
            if mtype == "join":
                self._handle_join(client, msg)
            elif mtype == "start":
                self._handle_start(client)
            elif mtype == "roll":
                self._handle_roll(client)
            elif mtype == "move":
                self._handle_move(client, msg)
            elif mtype == "pass":
                self._handle_pass(client)

    def _handle_join(self, client, msg):
        if self.state.started:
            client.send({"type": "error", "message": "La partida ya empezó."})
            return
        taken = {c.color for c in self.clients}
        free = [c for c in COLORS_ORDER if c not in taken]
        if not free:
            client.send({"type": "full"})
            try:
                client.conn.close()
            except OSError:
                pass
            return
        client.color = free[0]
        client.name = msg.get("name") or client.color.capitalize()
        client.is_host = len(self.clients) == 0
        self.clients.append(client)
        self.state.connected[client.color] = True
        print(f"[+] {client.name} ({client.color}) se unió desde {client.addr[0]}")
        client.send({"type": "welcome", "color": client.color, "host": client.is_host})
        self.broadcast_state()

    def _handle_start(self, client):
        if self.state.started:
            return
        if not client.is_host:
            client.send({"type": "error", "message": "Solo el jugador que creó la partida puede iniciarla."})
            return
        if len(self.clients) < 2:
            client.send({"type": "error", "message": "Se necesitan al menos 2 jugadores para empezar."})
            return
        self.state.started = True
        self.state.current_turn = self.state.active_colors()[0]
        print("[i] Partida iniciada con:", ", ".join(c.color for c in self.clients))
        self.broadcast_state()

    def _handle_roll(self, client):
        if not self.state.started or client.color != self.state.current_turn:
            return
        d1, d2 = random.randint(1, 6), random.randint(1, 6)
        stuck = self.state.action_roll(client.color, d1, d2)
        self.broadcast_state()
        if stuck:
            # Deja ver los dados 1.3s antes de pasar el turno automáticamente
            # (igual que en la versión local de un solo jugador).
            color = client.color
            timer = threading.Timer(1.3, self._finish_stuck_turn, args=(color,))
            timer.daemon = True
            timer.start()

    def _finish_stuck_turn(self, color):
        with self.lock:
            self.state.finish_stuck_turn(color)
            self.broadcast_state()

    def _handle_move(self, client, msg):
        if not self.state.started:
            return
        idx = msg.get("token_index")
        if idx is None:
            return
        moved = self.state.action_move(client.color, client.color, idx)
        if not moved:
            client.send({"type": "error", "message": "Jugada no válida."})
        self.broadcast_state()

    def _handle_pass(self, client):
        if not self.state.started or client.color != self.state.current_turn:
            return
        self.state.action_pass(client.color)
        self.broadcast_state()

    def on_disconnect(self, client):
        with self.lock:
            if client in self.clients:
                self.clients.remove(client)
            if client.color:
                print(f"[-] {client.name} ({client.color}) se desconectó")
                self.state.connected[client.color] = False
                # si le tocaba a quien se fue, pasa el turno automáticamente
                if self.state.started and self.state.current_turn == client.color:
                    self.state.next_turn()
                self.broadcast_state()

    def serve_forever(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen()
        print("=" * 50)
        print("     SERVIDOR - JUEGO DE PARQUÉS (LAN)")
        print("=" * 50)
        print(f"Puerto: {self.port}")
        ip = local_ip()
        if ip:
            print(f"IP de esta red: {ip}   <- pásale esto a tus amigos")
        print("Esperando jugadores (máx. 4)... Ctrl+C para detener.\n")
        try:
            while True:
                conn, addr = sock.accept()
                handler = ClientHandler(conn, addr, self)
                handler.start()
        except KeyboardInterrupt:
            print("\nServidor detenido.")
        finally:
            sock.close()


def main():
    parser = argparse.ArgumentParser(description="Servidor multijugador del Juego de Parqués")
    parser.add_argument("--host", default="0.0.0.0", help="interfaz donde escuchar (por defecto todas)")
    parser.add_argument("--puerto", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    server = ParquesServer(args.host, args.puerto)
    try:
        server.serve_forever()
    except OSError as err:
        print(f"No se pudo abrir el puerto {args.puerto}: {err}")
        print("¿Ya hay otro servidor corriendo? Prueba con --puerto 5556")
        sys.exit(1)


if __name__ == "__main__":
    main()
