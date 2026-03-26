"""
BMO Web Interface (v4 — Mobile-optimiert)
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
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "bmo_web.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("BMO-Web")

from flask import Flask, request, jsonify, Response, session, redirect, url_for
from flask_cors import CORS
import requests as req
import psutil
import datetime
import functools

app  = Flask(__name__)
CORS(app)

PORT           = 5000
CORE_URL       = "http://localhost:6000"
WEB_PASSWORD   = "1505"                        # ← Passwort hier ändern
app.secret_key = "bmo-secret-key-change-me-42"  # ← für Session-Cookie

# ── TAILSCALE HTTPS ────────────────────────────────────────────────
# Nach "tailscale cert damjan.xxxx.ts.net" die Pfade anpassen:
TS_CERT = r"C:\Users\damja\damjan.tail18e29f.ts.net.crt"
TS_KEY  = r"C:\Users\damja\damjan.tail18e29f.ts.net.key"
SSL_CONTEXT = (TS_CERT, TS_KEY) if os.path.exists(TS_CERT) else None

# ── VERBINDUNGSCHECK ───────────────────────────────────────────────
def core_available():
    try:
        r = req.get(f"{CORE_URL}/ping", timeout=2)
        return r.status_code == 200
    except:
        return False

# ── AUTH ────────────────────────────────────────────────────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            if request.path.startswith('/api/'):
                return jsonify(error="Nicht eingeloggt."), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

LOGIN_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>BMO – Login</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    height: 100dvh; display: flex; align-items: center; justify-content: center;
    background: #1a1a2e;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #eee;
  }
  .card {
    background: #16213e; border: 1px solid #2b3a5c; border-radius: 20px;
    padding: 36px 28px; width: 100%; max-width: 360px; margin: 16px;
  }
  h1 { font-size: 28px; font-weight: 700; margin-bottom: 6px; color: #2b8773; }
  p  { font-size: 13px; color: #aaa; margin-bottom: 28px; }
  input[type=password] {
    width: 100%; background: #0f1628; border: 1px solid #2b3a5c; border-radius: 14px;
    padding: 14px 16px; color: #eee; font-size: 16px; outline: none; margin-bottom: 14px;
  }
  input[type=password]:focus { border-color: #2b8773; }
  button {
    width: 100%; background: #2b8773; border: none; border-radius: 14px;
    padding: 14px; color: #fff; font-size: 16px; font-weight: 600; cursor: pointer;
  }
  .err { color: #ef4444; font-size: 13px; margin-top: 12px; text-align: center; }
</style>
</head>
<body>
<div class="card">
  <h1>BMO 👾</h1>
  <p>Passwort eingeben um fortzufahren.</p>
  <form method="post">
    <input type="password" name="password" placeholder="Passwort" autofocus autocomplete="current-password">
    <button type="submit">Einloggen</button>
    {% if error %}<div class="err">Falsches Passwort!</div>{% endif %}
  </form>
</div>
</body>
</html>"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = False
    if request.method == 'POST':
        if request.form.get('password') == WEB_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        error = True
    from flask import render_template_string
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── BMO ICON SVG ──────────────────────────────────────────────────
BMO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 215">
  <defs>
    <!-- Körper Verlauf: leichter Glanz oben -->
    <linearGradient id="bodyGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#c2e8e0"/>
      <stop offset="100%" stop-color="#96c8be"/>
    </linearGradient>
    <!-- Bildschirm Verlauf -->
    <linearGradient id="screenGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#d0ede7"/>
      <stop offset="100%" stop-color="#aed8d0"/>
    </linearGradient>
    <!-- Mund Verlauf -->
    <linearGradient id="mouthGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#1f6b5a"/>
      <stop offset="100%" stop-color="#2d9478"/>
    </linearGradient>
    <!-- Pink Button Verlauf -->
    <radialGradient id="pinkGrad" cx="38%" cy="35%">
      <stop offset="0%"   stop-color="#f060aa"/>
      <stop offset="100%" stop-color="#c0206a"/>
    </radialGradient>
    <!-- Grün Button Verlauf -->
    <radialGradient id="greenGrad" cx="38%" cy="35%">
      <stop offset="0%"   stop-color="#6ad648"/>
      <stop offset="100%" stop-color="#38962a"/>
    </radialGradient>
    <!-- Blau Button Verlauf -->
    <radialGradient id="blueGrad" cx="38%" cy="35%">
      <stop offset="0%"   stop-color="#4050c8"/>
      <stop offset="100%" stop-color="#1a2080"/>
    </radialGradient>
    <!-- D-Pad Verlauf -->
    <linearGradient id="dpadGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#ffd020"/>
      <stop offset="100%" stop-color="#d49a00"/>
    </linearGradient>
    <!-- Cyan Dreieck -->
    <linearGradient id="triGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#80e8f8"/>
      <stop offset="100%" stop-color="#28b8d8"/>
    </linearGradient>
  </defs>

  <!-- Hintergrund -->
  <rect width="180" height="215" fill="#6ecfbf"/>

  <!-- Körper äußerer Schatten/Rand -->
  <rect x="11" y="7" width="158" height="202" rx="24" fill="#3ea090"/>
  <!-- Körper Hauptfläche -->
  <rect x="14" y="10" width="152" height="199" rx="22" fill="url(#bodyGrad)"/>

  <!-- Bildschirm Rand -->
  <rect x="19" y="15" width="142" height="112" rx="19" fill="#7ab8ae"/>
  <!-- Bildschirm Fläche -->
  <rect x="22" y="18" width="136" height="108" rx="17" fill="url(#screenGrad)"/>
  <!-- Bildschirm Glanzstreifen oben -->
  <rect x="28" y="21" width="124" height="18" rx="10" fill="rgba(255,255,255,0.22)"/>

  <!-- Linkes Auge -->
  <ellipse cx="68" cy="60" rx="8" ry="10" fill="#1a1a1a"/>
  <ellipse cx="65" cy="57" rx="2.5" ry="3" fill="rgba(255,255,255,0.35)"/>
  <!-- Rechtes Auge -->
  <ellipse cx="112" cy="60" rx="8" ry="10" fill="#1a1a1a"/>
  <ellipse cx="109" cy="57" rx="2.5" ry="3" fill="rgba(255,255,255,0.35)"/>

  <!-- Mund – offenes Lächeln -->
  <path d="M53 90 Q90 124 127 90 Q90 100 53 90Z" fill="url(#mouthGrad)"/>
  <!-- Zähne -->
  <path d="M56 92 Q90 104 124 92" stroke="#e8f8f2" stroke-width="4"
        fill="none" stroke-linecap="round"/>

  <!-- Speaker-Leiste -->
  <rect x="19" y="133" width="92" height="11" rx="5.5" fill="#2a8070"/>
  <!-- Highlight auf Leiste -->
  <rect x="23" y="134" width="84" height="4" rx="2" fill="rgba(255,255,255,0.15)"/>

  <!-- Kreis rechts der Leiste -->
  <circle cx="137" cy="138" r="10" fill="url(#blueGrad)"/>
  <circle cx="134" cy="135" r="3" fill="rgba(255,255,255,0.3)"/>

  <!-- D-Pad: horizontal -->
  <rect x="31" y="154" width="36" height="14" rx="4" fill="url(#dpadGrad)"/>
  <!-- D-Pad: vertikal -->
  <rect x="42" y="143" width="14" height="36" rx="4" fill="url(#dpadGrad)"/>
  <!-- D-Pad Highlight -->
  <circle cx="49" cy="161" r="4" fill="rgba(255,255,255,0.2)"/>

  <!-- Zwei Dash-Buttons -->
  <rect x="31" y="187" width="14" height="8" rx="3" fill="url(#blueGrad)"/>
  <rect x="51" y="187" width="14" height="8" rx="3" fill="url(#blueGrad)"/>

  <!-- Dreieck-Button -->
  <polygon points="113,145 128,168 98,168" fill="url(#triGrad)"/>
  <polygon points="113,150 124,165 102,165" fill="rgba(255,255,255,0.15)"/>

  <!-- Pink-Button -->
  <circle cx="138" cy="181" r="16" fill="url(#pinkGrad)"/>
  <circle cx="133" cy="176" r="5" fill="rgba(255,255,255,0.25)"/>

  <!-- Grüner Button -->
  <circle cx="160" cy="152" r="12" fill="url(#greenGrad)"/>
  <circle cx="156" cy="148" r="4" fill="rgba(255,255,255,0.25)"/>
</svg>'''

# ── HTML SEITE ─────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="BMO">
<meta name="theme-color" content="#2b8773">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<link rel="manifest" href="/manifest.json">
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
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }
  .header-icon {
    height: 48px;
    width: auto;
    border-radius: 10px;
    flex-shrink: 0;
    box-shadow: 0 2px 6px rgba(0,0,0,0.4);
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
  .qbtn.green  { border-color: var(--green); }
  .qbtn.red    { border-color: #ef4444; color: #ef4444; }
  .qbtn.orange { border-color: #f97316; color: #f97316; }
  .qbtn.purple { border-color: #a855f7; color: #a855f7; }
  .qbtn.teal   { border-color: #3dd6c0; color: #3dd6c0; }
  .qbtn.yellow { border-color: #facc15; color: #facc15; }

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
  .msg.bmo img { max-width: 100%; border-radius: 10px; margin-bottom: 6px; display: block; }

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
  #camBtn { background: #1e3a5f; color: #fff; }

  /* ── OVERLAY ── */
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
    max-height: 88dvh;
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

  /* ── CONFIRM / SHEET BUTTONS ── */
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
  .btn-cancel  { background: var(--bg3); color: var(--text); border: 1px solid var(--border) !important; }
  .btn-confirm { background: #ef4444; color: #fff; }
  .btn-primary {
    width: 100%; padding: 14px;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 14px;
    color: var(--text);
    font-size: 16px;
    cursor: pointer;
    margin-top: 10px;
  }
  .btn-primary:active { opacity: .7; }

  /* ── KAMERA ── */
  #cameraVideo {
    width: 100%;
    border-radius: 14px;
    background: #000;
    max-height: 280px;
    object-fit: cover;
    display: block;
  }
  #capturedPreview {
    display: none;
    margin-bottom: 12px;
  }
  #capturedPreview img {
    width: 100%;
    border-radius: 14px;
    display: block;
  }
  .photo-question {
    width: 100%;
    padding: 12px 15px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 14px;
    color: var(--text);
    font-size: 15px;
    outline: none;
    font-family: inherit;
    margin-bottom: 12px;
  }
  .photo-question:focus { border-color: var(--green); }
  .camera-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 10px;
  }

  /* ── NOTIZEN ── */
  .note-input-row {
    display: flex;
    gap: 8px;
    margin-bottom: 14px;
  }
  .note-input-row input {
    flex: 1;
    padding: 12px 15px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 14px;
    color: var(--text);
    font-size: 15px;
    outline: none;
    font-family: inherit;
  }
  .note-input-row input:focus { border-color: var(--green); }
  .note-add-btn {
    padding: 12px 18px;
    background: var(--green);
    border: none;
    border-radius: 14px;
    color: #fff;
    font-size: 20px;
    cursor: pointer;
    flex-shrink: 0;
  }
  .note-add-btn:active { opacity: .7; }
  .notes-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 340px;
    overflow-y: auto;
  }
  .note-item {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 12px 14px;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    animation: fadeIn .2s ease;
  }
  .note-item .note-text {
    flex: 1;
    font-size: 15px;
    line-height: 1.45;
    word-break: break-word;
  }
  .note-item .note-date {
    font-size: 11px;
    color: var(--text2);
    margin-top: 4px;
  }
  .note-del {
    background: none;
    border: none;
    color: #ef4444;
    font-size: 20px;
    cursor: pointer;
    flex-shrink: 0;
    padding: 0 2px;
    line-height: 1;
    opacity: .7;
  }
  .note-del:active { opacity: 1; }
  .notes-empty {
    text-align: center;
    color: var(--text2);
    font-size: 14px;
    padding: 28px 0;
  }
</style>
</head>
<body>
<div class="app">

  <!-- HEADER -->
  <header>
    <div class="dot" id="coreDot"></div>
    <img src="/icon.svg" class="header-icon" alt="BMO">
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

    <button class="qbtn green" onclick="showHistory()">
      <span class="icon">💬</span>Verlauf
    </button>
    <button class="qbtn orange" onclick="confirmShutdown()">
      <span class="icon">⏻</span>Shutdown
    </button>
    <button class="qbtn red" onclick="triggerJumpscare()">
      <span class="icon">👻</span>Jumpscare
    </button>
    <button class="qbtn" onclick="clearContext()" style="border-color:#64748b;color:#94a3b8;">
      <span class="icon">🗑️</span>Reset
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
    <button class="ibtn" id="camBtn" onclick="showCamera()">📷</button>
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
    <button class="btn-primary" onclick="closeOverlay('statsOverlay')">Schließen</button>
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
    <div id="nowPlaying" style="background:var(--bg3);border:1px solid var(--border);border-radius:14px;padding:12px 14px;margin-bottom:16px;min-height:48px;display:flex;align-items:center;gap:10px;">
      <span style="font-size:20px;" id="npIcon">🎵</span>
      <div style="flex:1;overflow:hidden;">
        <div id="npTrack"  style="font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Lädt...</div>
        <div id="npArtist" style="font-size:12px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"></div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px;">
      <button onclick="spPlaylist()" style="padding:14px;background:var(--green);border:none;border-radius:14px;color:#fff;font-size:15px;font-weight:600;cursor:pointer;">▶ Playlist</button>
      <button onclick="spPause()"    style="padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:15px;font-weight:600;cursor:pointer;">⏸ Pause</button>
      <button onclick="spResume()"   style="padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:15px;font-weight:600;cursor:pointer;">▶ Weiter</button>
      <button onclick="spSkip()"     style="padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:15px;font-weight:600;cursor:pointer;">⏭ Skip</button>
    </div>
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
    <button class="btn-primary" onclick="closeOverlay('spotifyOverlay')">Schließen</button>
  </div>
</div>

<!-- KAMERA OVERLAY -->
<div class="overlay" id="cameraOverlay" onclick="void(0)">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>📷 Foto aufnehmen</h2>

    <!-- Live-Vorschau -->
    <div style="margin-bottom:12px;">
      <video id="cameraVideo" autoplay playsinline muted></video>
    </div>

    <!-- Aufgenommenes Bild -->
    <div id="capturedPreview">
      <img id="capturedImg" alt="Aufgenommenes Foto">
    </div>

    <!-- Optionale Frage -->
    <input type="text" id="photoQuestion" class="photo-question"
      placeholder="Frage an BMO (optional) – z.B. Was ist das?">

    <!-- Buttons -->
    <div class="camera-actions">
      <button id="captureBtn" onclick="capturePhoto()"
        style="padding:14px;background:var(--green);border:none;border-radius:14px;color:#fff;font-size:15px;font-weight:600;cursor:pointer;">
        📸 Aufnehmen
      </button>
      <button id="sendPhotoBtn" onclick="sendPhoto()" disabled
        style="padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text);font-size:15px;font-weight:600;cursor:pointer;opacity:.4;">
        ➤ Senden
      </button>
    </div>
    <button class="btn-primary" onclick="closeCamera()">Schließen</button>
  </div>
</div>

<!-- VERLAUF OVERLAY -->
<div class="overlay" id="historyOverlay" onclick="closeOverlay('historyOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
      <h2 style="margin:0;">💬 Gesprächsverlauf</h2>
      <button onclick="clearHistory()"
        style="background:none;border:1px solid #ef4444;border-radius:10px;color:#ef4444;font-size:12px;padding:6px 10px;cursor:pointer;">
        Alles löschen
      </button>
    </div>
    <div id="historyList" class="notes-list">
      <div class="notes-empty">Lade...</div>
    </div>
    <button class="btn-primary" onclick="closeOverlay('historyOverlay')">Schließen</button>
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

    const cpu = d.cpu || 0, ram = d.ram || 0;
    document.getElementById('sCpu').textContent  = cpu + '%';
    document.getElementById('sRam').textContent  = ram + '%';
    document.getElementById('sTime').textContent = d.time || '--';

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

// ── CHAT-VERLAUF LADEN ───────────────────────────────────────────
async function loadChatHistory() {
  try {
    const r = await fetch('/api/conversations');
    const d = await r.json();
    const convs = (d.conversations || []).slice(0, 20).reverse();
    if (!convs.length) return;
    chat.innerHTML = '';
    convs.forEach(c => {
      addMsg(c.user, 'user');
      addMsg(c.bmo,  'bmo');
    });
    addMsg('— ältere Nachrichten oben —', 'sys');
  } catch(e) {}
}
loadChatHistory();

// ── OVERLAY ─────────────────────────────────────────────────────
function showStats()       { updateStatus(); document.getElementById('statsOverlay').classList.add('show'); }
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
async function clearContext() {
  try {
    await fetch('/api/history/clear', {method: 'POST'});
    chat.innerHTML = '<div class="msg sys">Kontext gelöscht 🗑️</div>';
  } catch(e) { addMsg('Fehler 😢', 'sys'); }
}

async function triggerJumpscare() {
  try {
    await fetch('/api/jumpscare', {method: 'POST'});
    addMsg('👻 BOO!', 'sys');
  } catch(e) {
    addMsg('Jumpscare fehlgeschlagen 😢', 'sys');
  }
}

// ── SPOTIFY ─────────────────────────────────────────────────────
async function updateNowPlaying() {
  try {
    const r = await fetch('/api/spotify/current');
    const d = await r.json();
    if (d.track) {
      document.getElementById('npTrack').textContent  = d.track;
      document.getElementById('npArtist').textContent = d.artist;
      document.getElementById('npIcon').textContent   = d.playing ? '▶️' : '⏸';
    } else {
      document.getElementById('npTrack').textContent  = 'Nichts läuft gerade';
      document.getElementById('npArtist').textContent = '';
      document.getElementById('npIcon').textContent   = '🎵';
    }
  } catch(e) {}
}

async function showSpotify() {
  updateNowPlaying();
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

// ── KAMERA ─────────────────────────────────────────────────────
let cameraStream = null;
let capturedB64  = null;

async function showCamera() {
  capturedB64 = null;
  document.getElementById('capturedPreview').style.display = 'none';
  document.getElementById('cameraVideo').style.display     = 'block';
  document.getElementById('photoQuestion').value = '';
  const sendBtn = document.getElementById('sendPhotoBtn');
  sendBtn.disabled = true;
  sendBtn.style.opacity = '.4';

  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }
    });
    document.getElementById('cameraVideo').srcObject = cameraStream;
  } catch(e) {
    alert('Kamera verweigert oder nicht verfügbar.');
    return;
  }
  document.getElementById('cameraOverlay').classList.add('show');
}

function capturePhoto() {
  const video  = document.getElementById('cameraVideo');
  const canvas = document.createElement('canvas');
  canvas.width  = video.videoWidth  || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext('2d').drawImage(video, 0, 0);
  capturedB64 = canvas.toDataURL('image/jpeg', 0.85).split(',')[1];

  document.getElementById('capturedImg').src = 'data:image/jpeg;base64,' + capturedB64;
  document.getElementById('capturedPreview').style.display = 'block';
  document.getElementById('cameraVideo').style.display     = 'none';

  // Kamera-Stream stoppen
  if (cameraStream) { cameraStream.getTracks().forEach(t => t.stop()); cameraStream = null; }

  const sendBtn = document.getElementById('sendPhotoBtn');
  sendBtn.disabled = false;
  sendBtn.style.opacity = '1';
}

function closeCamera() {
  if (cameraStream) { cameraStream.getTracks().forEach(t => t.stop()); cameraStream = null; }
  document.getElementById('cameraOverlay').classList.remove('show');
}

async function sendPhoto() {
  if (!capturedB64) return;
  const question = document.getElementById('photoQuestion').value.trim()
                   || 'Was siehst du auf diesem Bild? Beschreibe es kurz auf Deutsch.';
  closeCamera();

  // Vorschau im Chat zeigen
  const div = document.createElement('div');
  div.className = 'msg user';
  const img = document.createElement('img');
  img.src = 'data:image/jpeg;base64,' + capturedB64;
  img.style.maxWidth = '100%';
  img.style.borderRadius = '10px';
  div.appendChild(img);
  if (question !== 'Was siehst du auf diesem Bild? Beschreibe es kurz auf Deutsch.') {
    const q = document.createElement('div');
    q.style.marginTop = '6px';
    q.style.fontSize  = '14px';
    q.textContent = question;
    div.appendChild(q);
  }
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;

  setTyping(true);
  try {
    const r = await fetch('/api/photo', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({image: capturedB64, question})
    });
    const d = await r.json();
    setTyping(false);
    addMsg(d.response || 'Keine Antwort.', 'bmo', d.audio || null);
  } catch(e) {
    setTyping(false);
    addMsg('Foto-Analyse fehlgeschlagen 😢', 'sys');
  }
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

// ── VERLAUF ─────────────────────────────────────────────────────
async function showHistory() {
  document.getElementById('historyOverlay').classList.add('show');
  await loadHistory();
}

async function loadHistory() {
  try {
    const r = await fetch('/api/conversations');
    const d = await r.json();
    renderHistory(d.conversations || []);
  } catch(e) {
    document.getElementById('historyList').innerHTML =
      '<div class="notes-empty">Fehler beim Laden.</div>';
  }
}

function renderHistory(convs) {
  const list = document.getElementById('historyList');
  if (!convs.length) {
    list.innerHTML = '<div class="notes-empty">Noch keine Gespräche gespeichert.</div>';
    return;
  }
  list.innerHTML = convs.map(c => `
    <div class="note-item" style="flex-direction:column;gap:6px;">
      <div style="font-size:11px;color:var(--text2);">${c.timestamp || ''}</div>
      <div style="font-size:13px;color:var(--text2);">Du: ${escHtml(c.user)}</div>
      <div style="font-size:14px;line-height:1.45;">BMO: ${escHtml(c.bmo)}</div>
    </div>
  `).join('');
}

async function clearHistory() {
  if (!confirm('Gesamten Verlauf löschen?')) return;
  try {
    await fetch('/api/conversations', {method: 'DELETE'});
    renderHistory([]);
  } catch(e) {}
}

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
@login_required
def index():
    return HTML

@app.route('/icon.svg')
def icon_svg():
    return Response(BMO_SVG, mimetype='image/svg+xml')

@app.route('/manifest.json')
def manifest():
    return jsonify(
        name="BMO",
        short_name="BMO",
        start_url="/",
        display="standalone",
        background_color="#1a1a2e",
        theme_color="#2b8773",
        icons=[{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]
    )

@app.route('/api/status')
@login_required
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
@login_required
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
@login_required
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

@app.route('/api/photo', methods=['POST'])
@login_required
def photo_endpoint():
    data = request.json or {}
    try:
        r = req.post(f"{CORE_URL}/photo", json=data, timeout=90)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(response=f"Core nicht erreichbar: {e}", action=None)

@app.route('/api/conversations', methods=['GET'])
@login_required
def conversations_get():
    try:
        r = req.get(f"{CORE_URL}/conversations", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(conversations=[], error=str(e))

@app.route('/api/conversations', methods=['DELETE'])
@login_required
def conversations_delete():
    try:
        r = req.delete(f"{CORE_URL}/conversations", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/jumpscare', methods=['POST'])
@login_required
def jumpscare_proxy():
    try:
        r = req.post(f"{CORE_URL}/jumpscare", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(response=f"Fehler: {e}")

@app.route('/api/spotify/playlist', methods=['POST'])
@login_required
def spotify_playlist_proxy():
    try:
        r = req.post(f"{CORE_URL}/spotify/playlist", timeout=15)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(response=f"Fehler: {e}")

@app.route('/api/history/clear', methods=['POST'])
@login_required
def history_clear_proxy():
    try:
        r = req.post(f"{CORE_URL}/history/clear", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(status="error", message=str(e))

@app.route('/api/spotify/current', methods=['GET'])
@login_required
def spotify_current_proxy():
    try:
        r = req.get(f"{CORE_URL}/spotify/current", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(track=None, artist=None, playing=False)

@app.route('/api/spotify/volume', methods=['GET', 'POST'])
@login_required
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
    proto = "https" if SSL_CONTEXT else "http"
    log.info(f"BMO Web Interface startet auf Port {PORT} ({proto.upper()})...")
    log.info(f"Lokal: {proto}://localhost:{PORT}")
    if SSL_CONTEXT:
        log.info("Tailscale-Zertifikat geladen.")
    else:
        log.warning("Kein Zertifikat gefunden — läuft ohne HTTPS (Mikro/Kamera nur auf localhost).")
    if core_available():
        log.info(f"Core erreichbar auf {CORE_URL}")
    else:
        log.warning("Core NICHT erreichbar!")
    app.run(host='0.0.0.0', port=PORT, debug=False, ssl_context=SSL_CONTEXT or None)
