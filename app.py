import os, random, threading
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from juego_logica import GameState, COLORS_ORDER
app=Flask(__name__); app.config['SECRET_KEY']=os.environ.get('SECRET_KEY','parques-web-demo')
socketio=SocketIO(app,cors_allowed_origins='*',async_mode='threading'); game=GameState(); players={}; lock=threading.RLock()
def snapshot():
 d=game.to_dict(); d['players']=[dict(sid=sid,**p) for sid,p in players.items()]; return d
def broadcast(): socketio.emit('state',snapshot())
@app.get('/')
def index(): return render_template('index.html')
@socketio.on('join')
def join(data):
 sid=request.sid; name=(data.get('name') or 'Jugador').strip()[:24] or 'Jugador'
 with lock:
  if sid in players: emit('joined',players[sid]); return
  free=[c for c in COLORS_ORDER if c not in [p['color'] for p in players.values()]]
  if game.started or not free: emit('notice','La sala ya comenzó o está llena (máximo 4).'); return
  p={'name':name,'color':free[0],'host':len(players)==0}; players[sid]=p; game.connected[p['color']]=True; emit('joined',p); broadcast()
@socketio.on('start')
def start():
 with lock:
  p=players.get(request.sid)
  if not p or not p['host']: emit('notice','Solo el anfitrión puede iniciar.'); return
  if len(players)<2: emit('notice','Necesitan al menos 2 jugadores.'); return
  game.started=True; game.current_turn=game.active_colors()[0]; game.last_event='Partida iniciada'; broadcast()
@socketio.on('roll')
def roll():
 with lock:
  p=players.get(request.sid)
  if not p or not game.started or p['color']!=game.current_turn or game.has_rolled or game.winner:return
  stuck=game.action_roll(p['color'],random.randint(1,6),random.randint(1,6)); broadcast()
  if stuck:
   color=p['color']
   def later():
    socketio.sleep(1.5)
    with lock: game.finish_stuck_turn(color); broadcast()
   socketio.start_background_task(later)
@socketio.on('move')
def move(data):
 with lock:
  p=players.get(request.sid)
  if not p:return
  try: i=int(data.get('index'))
  except: return
  if not game.action_move(p['color'],p['color'],i): emit('notice','No puedes mover esa ficha con los dados actuales.')
  broadcast()
@socketio.on('pass')
def passed():
 with lock:
  p=players.get(request.sid)
  if p: game.action_pass(p['color']); broadcast()
@socketio.on('disconnect')
def disconnect():
 with lock:
  p=players.pop(request.sid,None)
  if p: game.connected[p['color']]=False; broadcast()
if __name__=='__main__': socketio.run(app,host='0.0.0.0',port=int(os.environ.get('PORT',10000)))
