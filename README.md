# Juego de Parquess — adaptación web

## Render (Web Service)
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn --worker-class gthread --threads 100 --bind 0.0.0.0:$PORT app:app`
- Runtime: Python 3

La versión web conserva el módulo de reglas `juego_logica.py` y usa Flask-SocketIO. Para que varios jugadores compartan la misma sala, usa una sola instancia del servicio.
