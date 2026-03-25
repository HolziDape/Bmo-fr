"""
BMO Web Interface (v3 — Mobile-optimiert)
==========================================
Starten mit: python bmo_web.py
Dann im Browser (Handy oder PC): http://<tailscale-ip>:5000

Voraussetzung: bmo_core.py muss laufen (http://localhost:6000)
"""

import sys
import os
import logging
import subprocess

# ── LOGGING ────────────────────────────────────────────────────────────────
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bmo_web.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("BMO-Web")

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests as req
import psutil
import datetime

app  = Flask(__name__)
CORS(app)

PORT     = 5000
CORE_URL = "http://localhost:6000"

# ── VERBINDUNGSCHECK ───────────────────────────────────────────────
def core_available():
    try:
        r = req.get(f"{CORE_URL}/ping", timeout=2)
        return r.status_code == 200
    except:
        return False

# ── HTML SEITE ─────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>BMO</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  :root {
    --green: #2b8773;
    --green-dark: #1f6458;
    --bg: #1a1a2e;
    --bg2: #16213e;
    --bg3: #0f1628;
    --border: #2b3a5c;
    --text: #eee;
    --text2: #aaa;
  }
  html, body {
    height: 100%;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    overflow: hidden;
  }
  /* ── LAYOUT ── */
  .app {
    display: flex;
    flex-direction: column;
    height: 100dvh;
  }
  /* ── HEADER ── */
  header {
    background: var(--green);
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }
  header h1 { font-size: 20px; font-weight: 700; }
  header .sub { font-size: 12px; opacity: 0.8; }
  .dot {
    width: 9px; height: 9px;
    border-radius: 50%;
    background: #4ade80;
    animation: pulse 2s infinite;
    flex-shrink: 0;
  }
  .dot.off { background: #ef4444; animation: none; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  /* ── QUICK BUTTONS ── */
  .quick-btns {
    display: flex;
    gap: 8px;
    padding: 10px 12px;
    overflow-x: auto;
    flex-shrink: 0;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    scrollbar-width: none;
  }
  .quick-btns::-webkit-scrollbar { display: none; }
  .qbtn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 10px 14px;
    cursor: pointer;
    flex-shrink: 0;
    min-width: 70px;
    transition: background .15s, transform .1s;
    color: var(--text);
    font-size: 11px;
    font-weight: 500;
    user-select: none;
  }
  .qbtn:active { transform: scale(.93); background: var(--border); }
  .qbtn .icon { font-size: 22px; line-height: 1; }
  .qbtn.green { border-color: var(--green); }
  .qbtn.green .icon { filter: hue-rotate(0deg); }
  .qbtn.red { border-color: #ef4444; color: #ef4444; }
  .qbtn.orange { border-color: #f97316; color: #f97316; }
  .qbtn.purple { border-color: #a855f7; color: #a855f7; }

  /* ── CHAT ── */
  .chat {
    flex: 1;
    overflow-y: auto;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    overscroll-behavior: contain;
  }
  .msg {
    max-width: 82%;
    padding: 10px 13px;
    border-radius: 18px;
    font-size: 15px;
    line-height: 1.45;
    animation: fadeIn .2s ease;
    word-break: break-word;
  }
  @keyframes fadeIn { from{opacity:0;transform:translateY(5px)} to{opacity:1} }
  .msg.user  { align-self: flex-end; background: var(--green); border-bottom-right-radius: 4px; }
  .msg.bmo   { align-self: flex-start; background: var(--bg2); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
  .msg.bmo audio { margin-top: 8px; width: 100%; border-radius: 8px; }
  .msg.sys   { align-self: center; background: transparent; color: var(--text2); font-size: 12px; padding: 2px 8px; }

  /* ── TYPING ── */
  .typing {
    align-self: flex-start;
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 18px;
    border-bottom-left-radius: 4px;
    padding: 12px 16px;
    display: none;
  }
  .typing span {
    display: inline-block;
    width: 7px; height: 7px;
    background: var(--green);
    border-radius: 50%;
    margin: 0 2px;
    animation: bounce 1.2s infinite;
  }
  .typing span:nth-child(2){animation-delay:.2s}
  .typing span:nth-child(3){animation-delay:.4s}
  @keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}

  /* ── INPUT ── */
  .input-area {
    padding: 10px 12px;
    padding-bottom: max(10px, env(safe-area-inset-bottom));
    background: var(--bg2);
    border-top: 1px solid var(--border);
    display: flex;
    gap: 8px;
    align-items: flex-end;
    flex-shrink: 0;
  }
  textarea {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 10px 15px;
    color: var(--text);
    font-size: 16px;
    resize: none;
    max-height: 100px;
    outline: none;
    font-family: inherit;
    line-height: 1.4;
  }
  textarea:focus { border-color: var(--green); }
  .ibtn {
    border: none;
    border-radius: 50%;
    width: 44px; height: 44px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    font-size: 18px;
    transition: transform .1s;
  }
  .ibtn:active { transform: scale(.9); }
  #sendBtn { background: var(--green); color: #fff; }
  #sendBtn:disabled { opacity: .4; }
  #micBtn { background: #1e3a5f; color: #fff; }
  #micBtn.rec { background: #dc2626; animation: pulse .8s infinite; }

  /* ── OVERLAY (Stats, Confirm) ── */
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.7);
    display: flex;
    align-items: flex-end;
    justify-content: center;
    z-index: 100;
    opacity: 0;
    pointer-events: none;
    transition: opacity .2s;
  }
  .overlay.show { opacity: 1; pointer-events: all; }
  .sheet {
    background: var(--bg2);
    border-radius: 20px 20px 0 0;
    padding: 20px 16px;
    padding-bottom: max(20px, env(safe-area-inset-bottom));
    width: 100%;
    max-width: 600px;
    transform: translateY(100%);
    transition: transform .25s cubic-bezier(.32,1,.23,1);
    max-height: 85dvh;
    overflow-y: auto;
  }
  .overlay.show .sheet { transform: translateY(0); }
  .sheet-handle {
    width: 40px; height: 4px;
    background: var(--border);
    border-radius: 2px;
    margin: 0 auto 16px;
  }
  .sheet h2 { font-size: 18px; font-weight: 600; margin-bottom: 16px; }

  /* ── STATS GRID ── */
  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 16px;
  }
  .stat-card {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px;
  }
  .stat-card .val { font-size: 26px; font-weight: 700; color: var(--green); }
  .stat-card .lbl { font-size: 12px; color: var(--text2); margin-top: 2px; }
  .stat-card .bar {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    margin-top: 8px;
    overflow: hidden;
  }
  .stat-card .bar-fill {
    height: 100%;
    background: var(--green);
    border-radius: 2px;
    transition: width .5s;
  }
  .stat-card .bar-fill.warn { background: #f97316; }
  .stat-card .bar-fill.crit { background: #ef4444; }

  /* ── CONFIRM SHEET ── */
  .confirm-btns { display: flex; gap: 10px; margin-top: 8px; }
  .confirm-btns button {
    flex: 1;
    padding: 14px;
    border: none;
    border-radius: 14px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .15s;
  }
  .confirm-btns button:active { opacity: .7; }
  .btn-cancel { background: var(--bg3); color: var(--text); border: 1px solid var(--border) !important; }
  .btn-confirm { background: #ef4444; color: #fff; }

  /* ── JUMPSCARE ── */
  #jumpscare {
    position: fixed;
    inset: 0;
    background: #000;
    z-index: 200;
    display: none;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }
  #jumpscare.show { display: flex; }
  #jumpscare img { max-width: 100%; max-height: 100%; object-fit: contain; }
</style>
</head>
<body>
<div class="app">

  <!-- HEADER -->
  <header>
    <div class="dot" id="coreDot"></div>
    <div>
      <h1>BMO</h1>
      <span class="sub" id="coreStatus">Verbinde...</span>
    </div>
  </header>

  <!-- QUICK BUTTONS -->
  <div class="quick-btns">
    <button class="qbtn green" onclick="showStats()">
      <span class="icon">📊</span>Stats
    </button>
    <button class="qbtn purple" onclick="showSpotify()">
      <span class="icon">🎵</span>Spotify
    </button>
    <button class="qbtn orange" onclick="confirmShutdown()">
      <span class="icon">⏻</span>Shutdown
    </button>
    <button class="qbtn red" onclick="triggerJumpscare()">
      <span class="icon">👻</span>Jumpscare
    </button>
  </div>

  <!-- CHAT -->
  <div class="chat" id="chat">
    <div class="msg sys">BMO ist bereit 👾</div>
  </div>
  <div class="typing" id="typing">
    <span></span><span></span><span></span>
  </div>

  <!-- INPUT -->
  <div class="input-area">
    <textarea id="input" placeholder="Schreib BMO was..." rows="1"></textarea>
    <button class="ibtn" id="micBtn">🎤</button>
    <button class="ibtn" id="sendBtn">➤</button>
  </div>
</div>

<!-- STATS OVERLAY -->
<div class="overlay" id="statsOverlay" onclick="closeOverlay('statsOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>System Stats</h2>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="val" id="sCpu">--</div>
        <div class="lbl">CPU %</div>
        <div class="bar"><div class="bar-fill" id="sCpuBar" style="width:0%"></div></div>
      </div>
      <div class="stat-card">
        <div class="val" id="sRam">--</div>
        <div class="lbl">RAM %</div>
        <div class="bar"><div class="bar-fill" id="sRamBar" style="width:0%"></div></div>
      </div>
      <div class="stat-card">
        <div class="val" id="sTime">--</div>
        <div class="lbl">Uhrzeit</div>
      </div>
    </div>
    <button onclick="closeOverlay('statsOverlay')"
      style="width:100%;padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:16px;cursor:pointer;">
      Schließen
    </button>
  </div>
</div>

<!-- SHUTDOWN CONFIRM OVERLAY -->
<div class="overlay" id="shutdownOverlay" onclick="closeOverlay('shutdownOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>⏻ PC ausschalten?</h2>
    <p style="color:var(--text2);font-size:14px;margin-bottom:16px;">Der PC wird sofort heruntergefahren.</p>
    <div class="confirm-btns">
      <button class="btn-cancel" onclick="closeOverlay('shutdownOverlay')">Abbrechen</button>
      <button class="btn-confirm" onclick="doShutdown()">Ausschalten</button>
    </div>
  </div>
</div>

<!-- SPOTIFY OVERLAY -->
<div class="overlay" id="spotifyOverlay" onclick="closeOverlay('spotifyOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>🎵 Spotify</h2>

    <!-- Steuerung Buttons -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px;">
      <button onclick="spPlaylist()" style="padding:14px;background:var(--green);border:none;border-radius:14px;color:#fff;font-size:15px;font-weight:600;cursor:pointer;">▶ Playlist</button>
      <button onclick="spPause()" style="padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:15px;font-weight:600;cursor:pointer;">⏸ Pause</button>
      <button onclick="spResume()" style="padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:15px;font-weight:600;cursor:pointer;">▶ Weiter</button>
      <button onclick="spSkip()" style="padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:15px;font-weight:600;cursor:pointer;">⏭ Skip</button>
    </div>

    <!-- Lautstärke -->
    <div style="margin-bottom:20px;">
      <div style="font-size:13px;color:var(--text2);margin-bottom:10px;">🔊 Lautstärke</div>
      <div style="display:flex;align-items:center;gap:12px;">
        <span style="font-size:18px;">🔈</span>
        <input type="range" id="volSlider" min="0" max="100" value="50"
          style="flex:1;accent-color:var(--green);height:6px;cursor:pointer;"
          oninput="document.getElementById('volLabel').textContent=this.value+'%'"
          onchange="setVolume(this.value)">
        <span style="font-size:18px;">🔊</span>
      </div>
      <div style="text-align:center;margin-top:8px;font-size:22px;font-weight:700;color:var(--green)" id="volLabel">50%</div>
    </div>

    <button onclick="closeOverlay('spotifyOverlay')"
      style="width:100%;padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:16px;cursor:pointer;">
      Schließen
    </button>
  </div>
</div>



<script>
const chat   = document.getElementById('chat');
const input  = document.getElementById('input');
const sendBtn= document.getElementById('sendBtn');
const micBtn = document.getElementById('micBtn');
const typing = document.getElementById('typing');

// ── STATUS ──────────────────────────────────────────────────────
async function updateStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('coreDot').classList.remove('off');
    document.getElementById('coreStatus').textContent = 'Online · ' + d.time;

    // Stats overlay Werte
    const cpu = d.cpu || 0, ram = d.ram || 0;
    document.getElementById('sCpu').textContent  = cpu + '%';
    document.getElementById('sRam').textContent  = ram + '%';
    document.getElementById('sTime').textContent = d.time || '--';

    // Balken
    const cpuBar = document.getElementById('sCpuBar');
    cpuBar.style.width = cpu + '%';
    cpuBar.className = 'bar-fill' + (cpu > 90 ? ' crit' : cpu > 70 ? ' warn' : '');
    const ramBar = document.getElementById('sRamBar');
    ramBar.style.width = ram + '%';
    ramBar.className = 'bar-fill' + (ram > 90 ? ' crit' : ram > 70 ? ' warn' : '');
  } catch(e) {
    document.getElementById('coreDot').classList.add('off');
    document.getElementById('coreStatus').textContent = 'Core offline';
  }
}
updateStatus();
setInterval(updateStatus, 5000);

// ── OVERLAY ─────────────────────────────────────────────────────
function showStats()   { updateStatus(); document.getElementById('statsOverlay').classList.add('show'); }
function confirmShutdown() { document.getElementById('shutdownOverlay').classList.add('show'); }
function closeOverlay(id)  { document.getElementById(id).classList.remove('show'); }

// ── QUICK ACTIONS ────────────────────────────────────────────────
async function quickAction(msg) {
  closeOverlay('shutdownOverlay');
  addMsg(msg, 'user');
  setTyping(true);
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message: msg})
    });
    const d = await r.json();
    setTyping(false);
    addMsg(d.response, 'bmo', d.audio);
  } catch(e) {
    setTyping(false);
    addMsg('Verbindungsfehler 😢', 'sys');
  }
}

function doShutdown() { quickAction('schalte den PC aus'); }

// ── JUMPSCARE ────────────────────────────────────────────────────
async function triggerJumpscare() {
  try {
    await fetch('/api/jumpscare', {method: 'POST'});
    addMsg('👻 BOO!', 'sys');
  } catch(e) {
    addMsg('Jumpscare fehlgeschlagen 😢', 'sys');
  }
}

// ── SPOTIFY OVERLAY ─────────────────────────────────────────────
async function showSpotify() {
  try {
    const r = await fetch('/api/spotify/volume');
    const d = await r.json();
    if (d.volume !== null && d.volume !== undefined) {
      document.getElementById('volSlider').value = d.volume;
      document.getElementById('volLabel').textContent = d.volume + '%';
    }
  } catch(e) {}
  document.getElementById('spotifyOverlay').classList.add('show');
}

async function setVolume(val) {
  try {
    await fetch('/api/spotify/volume', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({level: parseInt(val)})
    });
  } catch(e) {}
}

async function spPlaylist() {
  try {
    const r = await fetch('/api/spotify/playlist', {method:'POST'});
    const d = await r.json();
    addMsg(d.response, 'bmo');
  } catch(e) { addMsg('Fehler 😢', 'sys'); }
}

async function spPause() {
  try {
    const r = await fetch('/api/chat', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:'pause'})
    });
    const d = await r.json();
    addMsg(d.response, 'bmo');
  } catch(e) {}
}

async function spResume() {
  try {
    const r = await fetch('/api/chat', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:'weiter'})
    });
    const d = await r.json();
    addMsg(d.response, 'bmo');
  } catch(e) {}
}

async function spSkip() {
  try {
    const r = await fetch('/api/chat', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:'nächstes Lied'})
    });
    const d = await r.json();
    addMsg(d.response, 'bmo');
  } catch(e) {}
}

// ── CHAT ─────────────────────────────────────────────────────────
function addMsg(text, role, audioB64=null) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  if (audioB64) {
    const audio = document.createElement('audio');
    audio.controls = true;
    audio.src = 'data:audio/wav;base64,' + audioB64;
    div.appendChild(audio);
    setTimeout(() => audio.play(), 100);
  }
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function setTyping(show) {
  typing.style.display = show ? 'flex' : 'none';
  chat.scrollTop = chat.scrollHeight;
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';
  sendBtn.disabled = true;
  addMsg(text, 'user');
  setTyping(true);
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message: text})
    });
    const d = await r.json();
    setTyping(false);
    addMsg(d.response, 'bmo', d.audio || null);
  } catch(e) {
    setTyping(false);
    addMsg('Verbindungsfehler 😢', 'sys');
  }
  sendBtn.disabled = false;
  input.focus();
}

sendBtn.addEventListener('click', send);
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 100) + 'px';
});

// ── MIKROFON ─────────────────────────────────────────────────────
let mediaRecorder, audioChunks = [], recording = false;
micBtn.addEventListener('click', async () => {
  if (!recording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];
      mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
      mediaRecorder.onstop = async () => {
        const blob = new Blob(audioChunks, {type:'audio/webm'});
        const reader = new FileReader();
        reader.onload = async () => {
          const b64 = reader.result.split(',')[1];
          setTyping(true);
          try {
            const r = await fetch('/api/voice', {
              method: 'POST',
              headers: {'Content-Type':'application/json'},
              body: JSON.stringify({audio: b64})
            });
            const d = await r.json();
            setTyping(false);
            if (d.transcript) addMsg(d.transcript, 'user');
            addMsg(d.response, 'bmo', d.audio || null);
          } catch(e) {
            setTyping(false);
            addMsg('Sprachfehler 😢', 'sys');
          }
        };
        reader.readAsDataURL(blob);
        stream.getTracks().forEach(t => t.stop());
      };
      mediaRecorder.start();
      recording = true;
      micBtn.classList.add('rec');
      micBtn.textContent = '⏹';
    } catch(e) { alert('Mikrofon verweigert!'); }
  } else {
    mediaRecorder.stop();
    recording = false;
    micBtn.classList.remove('rec');
    micBtn.textContent = '🎤';
  }
});
</script>
</body>
</html>
"""

# ── ROUTES ────────────────────────────────────────────────────────
@app.route('/')
def index():
    return HTML

@app.route('/api/status')
def status():
    try:
        r = req.get(f"{CORE_URL}/status", timeout=2)
        return jsonify(r.json())
    except:
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory().percent
        time = datetime.datetime.now().strftime('%H:%M')
        return jsonify(cpu=cpu, ram=ram, time=time, gpu=None)

@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    data    = request.json or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify(response="Ich habe nichts verstanden.", audio=None)
    try:
        r = req.post(f"{CORE_URL}/process",
                     json={"message": message},
                     timeout=60)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(response=f"Core nicht erreichbar: {e}", audio=None)

@app.route('/api/voice', methods=['POST'])
def voice_endpoint():
    data = request.json or {}
    b64  = data.get('audio', '')
    if not b64:
        return jsonify(transcript='', response='Kein Audio empfangen.', audio=None)
    try:
        tr = req.post(f"{CORE_URL}/transcribe",
                      json={"audio": b64, "format": "webm"},
                      timeout=30)
        transcript = tr.json().get('transcript', '')
        if not transcript:
            return jsonify(transcript='', response='Ich habe dich nicht verstanden.', audio=None)
        pr = req.post(f"{CORE_URL}/process",
                      json={"message": transcript},
                      timeout=60)
        result = pr.json()
        result['transcript'] = transcript
        return jsonify(result)
    except Exception as e:
        return jsonify(transcript='', response=f"Core nicht erreichbar: {e}", audio=None)

@app.route('/api/jumpscare', methods=['POST'])
def jumpscare_proxy():
    try:
        r = req.post(f"{CORE_URL}/jumpscare", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(response=f"Fehler: {e}")

@app.route('/api/spotify/playlist', methods=['POST'])
def spotify_playlist_proxy():
    try:
        r = req.post(f"{CORE_URL}/spotify/playlist", timeout=15)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(response=f"Fehler: {e}")

@app.route('/api/spotify/volume', methods=['GET', 'POST'])
def spotify_volume_proxy():
    try:
        if request.method == 'GET':
            r = req.get(f"{CORE_URL}/spotify/volume", timeout=5)
        else:
            r = req.post(f"{CORE_URL}/spotify/volume",
                        json=request.json or {}, timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(volume=None, error=str(e))

# ── START ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    log.info(f"BMO Web Interface startet auf Port {PORT}...")
    log.info(f"Lokal: http://localhost:{PORT}")
    if core_available():
        log.info(f"Core erreichbar auf {CORE_URL}")
    else:
        log.warning("Core NICHT erreichbar!")
    app.run(host='0.0.0.0', port=PORT, debug=False)