# Juego de Parqués — Multijugador LAN

## Archivos
- `main.py` — juego original, un solo jugador/pantalla (hotseat local). Sigue funcionando igual que antes.
- `juego_logica.py` — reglas del tablero, compartidas por servidor y cliente.
- `servidor.py` — el "árbitro": corre en UNA sola máquina de la red y valida cada jugada.
- `cliente.py` — lo que abre cada jugador para conectarse y jugar.

## Requisitos
```
pip install pygame
```
(el servidor no necesita pygame si lo corres en una máquina sin pantalla; si te da error al importarlo, instálalo igual, no estorba)

## Cómo jugar (hasta 4 jugadores en la misma red WiFi)

1. **Una sola persona** abre una terminal y corre el servidor:
   ```
   python servidor.py
   ```
   Va a imprimir algo como `IP de esta red: 192.168.1.23` — esa es la IP que le pasas a los demás.

2. **Cada jugador** (incluido quien montó el servidor, en otra terminal) corre:
   ```
   python cliente.py
   ```
   Le va a pedir:
   - IP del servidor (la del paso 1; si juegas en la misma máquina, deja "localhost")
   - Puerto (Enter para 5555)
   - Su nombre

3. El primero en conectarse es el **host**: cuando ya estén 2-4 conectados, verá un botón **"Iniciar partida"**.

4. A partir de ahí es el mismo juego de `main.py`: tirar dados, mover fichas — pero cada quien solo puede mover las suyas, y todos ven el tablero sincronizado en tiempo real.

## Reglas de movimiento
- **Salir de la base:** con **cualquier doble** (1-1, 2-2 ... 6-6). Cada dado del doble saca una ficha, y como siempre, con un doble vuelves a tirar.
- **Movimiento:** la ficha avanza **casilla por casilla** (un salto animado por cada punto del dado) hasta llegar al número. Las capturas, la entrada a la recta final y la meta se aplican al llegar a la casilla final.
- **Casillas con estrella dorada:** son seguras, ahí no te pueden capturar.

## Notas
- Si un jugador se desconecta, su turno se salta automáticamente y sus fichas quedan quietas en el tablero.
- El servidor valida todas las jugadas (nadie puede hacer trampa moviendo fichas ajenas o con dados que no le corresponden).
- Puerto por defecto: **5555**. Si está ocupado: `python servidor.py --puerto 6000` (y usar ese mismo puerto en los clientes).
