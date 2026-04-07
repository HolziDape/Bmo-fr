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
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_intern", "logs", "bmo_web.log")
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
from flask_socketio import SocketIO
import requests as req
import psutil
import datetime
import functools
import io
import threading
import time as _time

try:
    import mss as _mss_lib
    from PIL import Image as _PilImage
    _SCREEN_OK      = True
    _SCREEN_BACKEND = 'mss'
except ImportError:
    try:
        from PIL import ImageGrab, Image as _PilImage
        _SCREEN_OK      = True
        _SCREEN_BACKEND = 'pil'
    except ImportError:
        _SCREEN_OK      = False
        _SCREEN_BACKEND = None

try:
    import pyautogui as _pag
    _pag.FAILSAFE = True
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False

app  = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

PORT       = 5000
CORE_URL   = "http://localhost:6000"

# ── KONFIGURATION (aus bmo_config.txt) ────────────────────────────
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_intern", "bmo_config.txt")

def _load_config():
    """Liest alle Schlüssel aus bmo_config.txt als Dict."""
    cfg = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg

def _save_config(data: dict):
    """Schreibt alle Schlüssel in bmo_config.txt."""
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        for k, v in data.items():
            f.write(f"{k}={v}\n")
    log.info("bmo_config.txt gespeichert.")

def _parse_friends(raw: str) -> list:
    """Parst 'Name|http://url,Name2|http://url2' in eine Liste von {name, url} Dicts."""
    result = []
    for entry in raw.split(','):
        entry = entry.strip()
        if not entry:
            continue
        if '|' in entry:
            name, url = entry.split('|', 1)
            result.append({'name': name.strip(), 'url': url.strip()})
        elif entry.startswith('http'):
            result.append({'name': 'Freund', 'url': entry})
    return result

_cfg           = _load_config()
WEB_PASSWORD   = _cfg.get("WEB_PASSWORD", "").strip() or None
# Neue FRIENDS-Liste — fällt auf altes FRIEND_URL zurück
_raw_friends   = _cfg.get("FRIENDS") or _cfg.get("FRIEND_URL", "")
FRIENDS: list  = _parse_friends(_raw_friends)
FRIEND_URL     = FRIENDS[0]['url'] if FRIENDS else "http://HIER_FREUND_IP:5000"
app.secret_key = (WEB_PASSWORD or "bmo-setup-mode") + "-bmo-secret-42"

def _save_password(pw: str):
    cfg = _load_config()
    cfg["WEB_PASSWORD"] = pw
    _save_config(cfg)
    log.info("Passwort in bmo_config.txt gespeichert.")

def _save_friends(friends_raw: str):
    cfg = _load_config()
    cfg["FRIENDS"] = friends_raw
    _save_config(cfg)
    log.info(f"FRIENDS gespeichert: {friends_raw}")

def _save_friend_url(url: str):
    _save_friends(url)


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
        # Noch kein Passwort gesetzt → Ersteinrichtung im Browser
        if not WEB_PASSWORD:
            return redirect(url_for('setup'))
        if not session.get('authenticated'):
            if request.path.startswith('/api/'):
                return jsonify(error="Nicht eingeloggt."), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

SETUP_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>BMO – Ersteinrichtung</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  :root { --green:#2b8773; --green-dark:#1f6458; --bg:#1a1a2e; --bg2:#16213e; --bg3:#0f1628; --border:#2b3a5c; --text:#eee; --text2:#aaa; }
  html,body { height:100%; background:var(--bg); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; color:var(--text); overflow:hidden; }
  body::before { content:''; position:fixed; inset:0; z-index:0;
    background:radial-gradient(ellipse at 20% 50%,rgba(43,135,115,.15) 0%,transparent 60%),
               radial-gradient(ellipse at 80% 20%,rgba(43,135,115,.10) 0%,transparent 50%);
    animation:bgPulse 6s ease-in-out infinite alternate; }
  @keyframes bgPulse { from{opacity:.6} to{opacity:1} }
  .wrap { position:relative; z-index:1; height:100dvh; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:24px; }
  .bmo-figure { width:90px; height:90px; margin-bottom:16px; animation:bmoFloat 3s ease-in-out infinite; filter:drop-shadow(0 8px 24px rgba(43,135,115,.4)); }
  @keyframes bmoFloat { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)} }
  .card { background:var(--bg2); border:1px solid var(--border); border-radius:24px; padding:32px 28px; width:100%; max-width:380px; box-shadow:0 20px 60px rgba(0,0,0,.5); animation:cardIn .4s cubic-bezier(.32,1,.23,1); }
  @keyframes cardIn { from{opacity:0;transform:translateY(20px) scale(.97)} to{opacity:1;transform:none} }
  .badge { display:inline-block; background:rgba(43,135,115,.2); border:1px solid rgba(43,135,115,.4); color:#5eead4; border-radius:20px; padding:3px 12px; font-size:11px; font-weight:600; letter-spacing:.5px; text-transform:uppercase; margin-bottom:12px; }
  .card-title { font-size:22px; font-weight:700; margin-bottom:4px; }
  .card-sub { font-size:13px; color:var(--text2); margin-bottom:24px; line-height:1.5; }
  .input-wrap { position:relative; margin-bottom:12px; }
  .input-wrap .icon { position:absolute; left:14px; top:50%; transform:translateY(-50%); font-size:17px; pointer-events:none; }
  .lbl { font-size:12px; color:var(--text2); margin-bottom:6px; font-weight:500; }
  input[type=password] { width:100%; background:var(--bg3); border:1px solid var(--border); border-radius:14px; padding:13px 16px 13px 42px; color:var(--text); font-size:16px; outline:none; transition:border-color .2s; }
  input[type=password]:focus { border-color:var(--green); }
  input[type=password]::placeholder { color:#555; }
  button[type=submit] { width:100%; background:var(--green); border:none; border-radius:14px; padding:14px; color:#fff; font-size:16px; font-weight:700; cursor:pointer; transition:background .15s,transform .1s; margin-top:4px; }
  button[type=submit]:hover { background:var(--green-dark); }
  button[type=submit]:active { transform:scale(.97); }
  .err { display:flex; align-items:center; gap:8px; background:rgba(239,68,68,.12); border:1px solid rgba(239,68,68,.3); border-radius:12px; padding:10px 14px; color:#fca5a5; font-size:13px; margin-bottom:14px; animation:shake .3s ease; }
  @keyframes shake { 0%,100%{transform:translateX(0)} 25%{transform:translateX(-6px)} 75%{transform:translateX(6px)} }
</style>
</head>
<body>
<div class="wrap">
  <svg class="bmo-figure" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 215">
    <defs>
      <linearGradient id="s1" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#c2e8e0"/><stop offset="100%" stop-color="#96c8be"/></linearGradient>
      <linearGradient id="s2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#d0ede7"/><stop offset="100%" stop-color="#aed8d0"/></linearGradient>
      <linearGradient id="s3" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#1f6b5a"/><stop offset="100%" stop-color="#2d9478"/></linearGradient>
      <radialGradient id="s4" cx="38%" cy="35%"><stop offset="0%" stop-color="#f060aa"/><stop offset="100%" stop-color="#c0206a"/></radialGradient>
      <radialGradient id="s5" cx="38%" cy="35%"><stop offset="0%" stop-color="#4050c8"/><stop offset="100%" stop-color="#1a2080"/></radialGradient>
      <linearGradient id="s6" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#ffd020"/><stop offset="100%" stop-color="#d49a00"/></linearGradient>
    </defs>
    <rect width="180" height="215" fill="#6ecfbf"/>
    <rect x="11" y="7" width="158" height="202" rx="24" fill="#3ea090"/>
    <rect x="14" y="10" width="152" height="199" rx="22" fill="url(#s1)"/>
    <rect x="19" y="15" width="142" height="112" rx="19" fill="#7ab8ae"/>
    <rect x="22" y="18" width="136" height="108" rx="17" fill="url(#s2)"/>
    <rect x="28" y="21" width="124" height="18" rx="10" fill="rgba(255,255,255,0.22)"/>
    <ellipse cx="68" cy="60" rx="8" ry="10" fill="#1a1a1a"/><ellipse cx="65" cy="57" rx="2.5" ry="3" fill="rgba(255,255,255,0.35)"/>
    <ellipse cx="112" cy="60" rx="8" ry="10" fill="#1a1a1a"/><ellipse cx="109" cy="57" rx="2.5" ry="3" fill="rgba(255,255,255,0.35)"/>
    <path d="M53 90 Q90 124 127 90 Q90 100 53 90Z" fill="url(#s3)"/>
    <path d="M56 92 Q90 104 124 92" stroke="#e8f8f2" stroke-width="4" fill="none" stroke-linecap="round"/>
    <rect x="19" y="133" width="92" height="11" rx="5.5" fill="#2a8070"/>
    <circle cx="137" cy="138" r="10" fill="url(#s5)"/>
    <rect x="31" y="154" width="36" height="14" rx="4" fill="url(#s6)"/>
    <rect x="42" y="143" width="14" height="36" rx="4" fill="url(#s6)"/>
    <circle cx="138" cy="181" r="16" fill="url(#s4)"/>
  </svg>
  <div class="card">
    <div class="badge">✨ Ersteinrichtung</div>
    <div class="card-title">Willkommen bei BMO!</div>
    <div class="card-sub">Wähle ein Passwort für das Web-Interface.<br>Du brauchst es beim nächsten Login.</div>
    {% if error %}<div class="err">⚠️ {{ error }}</div>{% endif %}
    <form method="post">
      <div class="lbl">Neues Passwort</div>
      <div class="input-wrap">
        <span class="icon">🔑</span>
        <input type="password" name="password" placeholder="Passwort wählen..." autofocus autocomplete="new-password">
      </div>
      <div class="lbl">Passwort wiederholen</div>
      <div class="input-wrap">
        <span class="icon">🔒</span>
        <input type="password" name="password2" placeholder="Nochmal eingeben..." autocomplete="new-password">
      </div>
      <div class="lbl" style="margin-top:16px;">Freund IP <span style="color:#555;font-weight:400;">(optional — für Jumpscare &amp; Screen)</span></div>
      <div class="input-wrap">
        <span class="icon">👥</span>
        <input type="text" name="friend_url" placeholder="http://100.x.x.x:5000" autocomplete="off"
          style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:14px;padding:13px 16px 13px 42px;color:var(--text);font-size:16px;outline:none;transition:border-color .2s;">
      </div>
      <button type="submit">Speichern &amp; Loslegen ➤</button>
    </form>
  </div>
</div>
</body>
</html>"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>BMO – Login</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  :root {
    --green: #2b8773; --green-dark: #1f6458;
    --bg: #1a1a2e; --bg2: #16213e; --bg3: #0f1628;
    --border: #2b3a5c; --text: #eee; --text2: #aaa;
  }
  html, body {
    height: 100%; background: var(--bg);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: var(--text); overflow: hidden;
  }
  /* animierter Hintergrund */
  body::before {
    content: ''; position: fixed; inset: 0; z-index: 0;
    background: radial-gradient(ellipse at 20% 50%, rgba(43,135,115,.15) 0%, transparent 60%),
                radial-gradient(ellipse at 80% 20%, rgba(43,135,115,.10) 0%, transparent 50%);
    animation: bgPulse 6s ease-in-out infinite alternate;
  }
  @keyframes bgPulse {
    from { opacity: .6; }
    to   { opacity: 1; }
  }
  .wrap {
    position: relative; z-index: 1;
    height: 100dvh; display: flex; flex-direction: column;
    align-items: center; justify-content: center; padding: 24px;
  }
  /* BMO Figur */
  .bmo-figure {
    width: 90px; height: 90px; margin-bottom: 20px;
    animation: bmoFloat 3s ease-in-out infinite;
    filter: drop-shadow(0 8px 24px rgba(43,135,115,.4));
  }
  @keyframes bmoFloat {
    0%,100% { transform: translateY(0);   }
    50%      { transform: translateY(-8px); }
  }
  /* Karte */
  .card {
    background: var(--bg2); border: 1px solid var(--border);
    border-radius: 24px; padding: 32px 28px;
    width: 100%; max-width: 360px;
    box-shadow: 0 20px 60px rgba(0,0,0,.5);
    animation: cardIn .4s cubic-bezier(.32,1,.23,1);
  }
  @keyframes cardIn {
    from { opacity: 0; transform: translateY(20px) scale(.97); }
    to   { opacity: 1; transform: none; }
  }
  .card-title {
    font-size: 22px; font-weight: 700; color: var(--text);
    text-align: center; margin-bottom: 4px;
  }
  .card-sub {
    font-size: 13px; color: var(--text2);
    text-align: center; margin-bottom: 24px;
  }
  .input-wrap { position: relative; margin-bottom: 14px; }
  .input-wrap .icon {
    position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
    font-size: 18px; pointer-events: none;
  }
  input[type=password] {
    width: 100%; background: var(--bg3); border: 1px solid var(--border);
    border-radius: 14px; padding: 14px 16px 14px 42px;
    color: var(--text); font-size: 16px; outline: none;
    transition: border-color .2s;
  }
  input[type=password]:focus { border-color: var(--green); }
  input[type=password]::placeholder { color: #555; }
  button[type=submit] {
    width: 100%; background: var(--green); border: none; border-radius: 14px;
    padding: 14px; color: #fff; font-size: 16px; font-weight: 700;
    cursor: pointer; transition: background .15s, transform .1s;
    letter-spacing: .3px;
  }
  button[type=submit]:hover  { background: var(--green-dark); }
  button[type=submit]:active { transform: scale(.97); }
  .err {
    display: flex; align-items: center; gap: 8px;
    background: rgba(239,68,68,.12); border: 1px solid rgba(239,68,68,.3);
    border-radius: 12px; padding: 10px 14px;
    color: #fca5a5; font-size: 13px; margin-top: 12px;
    animation: shake .3s ease;
  }
  @keyframes shake {
    0%,100%{ transform: translateX(0); }
    25%     { transform: translateX(-6px); }
    75%     { transform: translateX(6px); }
  }
</style>
</head>
<body>
<div class="wrap">
  <!-- BMO Figur (inline SVG) -->
  <svg class="bmo-figure" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 215">
    <defs>
      <linearGradient id="lg1" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#c2e8e0"/><stop offset="100%" stop-color="#96c8be"/></linearGradient>
      <linearGradient id="lg2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#d0ede7"/><stop offset="100%" stop-color="#aed8d0"/></linearGradient>
      <linearGradient id="lg3" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#1f6b5a"/><stop offset="100%" stop-color="#2d9478"/></linearGradient>
      <radialGradient id="rg1" cx="38%" cy="35%"><stop offset="0%" stop-color="#f060aa"/><stop offset="100%" stop-color="#c0206a"/></radialGradient>
      <radialGradient id="rg2" cx="38%" cy="35%"><stop offset="0%" stop-color="#4050c8"/><stop offset="100%" stop-color="#1a2080"/></radialGradient>
      <linearGradient id="lg4" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#ffd020"/><stop offset="100%" stop-color="#d49a00"/></linearGradient>
    </defs>
    <rect width="180" height="215" fill="#6ecfbf"/>
    <rect x="11" y="7" width="158" height="202" rx="24" fill="#3ea090"/>
    <rect x="14" y="10" width="152" height="199" rx="22" fill="url(#lg1)"/>
    <rect x="19" y="15" width="142" height="112" rx="19" fill="#7ab8ae"/>
    <rect x="22" y="18" width="136" height="108" rx="17" fill="url(#lg2)"/>
    <rect x="28" y="21" width="124" height="18" rx="10" fill="rgba(255,255,255,0.22)"/>
    <ellipse cx="68" cy="60" rx="8" ry="10" fill="#1a1a1a"/>
    <ellipse cx="65" cy="57" rx="2.5" ry="3" fill="rgba(255,255,255,0.35)"/>
    <ellipse cx="112" cy="60" rx="8" ry="10" fill="#1a1a1a"/>
    <ellipse cx="109" cy="57" rx="2.5" ry="3" fill="rgba(255,255,255,0.35)"/>
    <path d="M53 90 Q90 124 127 90 Q90 100 53 90Z" fill="url(#lg3)"/>
    <path d="M56 92 Q90 104 124 92" stroke="#e8f8f2" stroke-width="4" fill="none" stroke-linecap="round"/>
    <rect x="19" y="133" width="92" height="11" rx="5.5" fill="#2a8070"/>
    <circle cx="137" cy="138" r="10" fill="url(#rg2)"/>
    <rect x="31" y="154" width="36" height="14" rx="4" fill="url(#lg4)"/>
    <rect x="42" y="143" width="14" height="36" rx="4" fill="url(#lg4)"/>
    <circle cx="138" cy="181" r="16" fill="url(#rg1)"/>
  </svg>

  <div class="card">
    <div class="card-title">Hallo! Ich bin BMO 👾</div>
    <div class="card-sub">Passwort eingeben um fortzufahren</div>
    <form method="post">
      <div class="input-wrap">
        <span class="icon">🔑</span>
        <input type="password" name="password" placeholder="Passwort" autofocus autocomplete="current-password">
      </div>
      <button type="submit">Einloggen ➤</button>
      {% if error %}
      <div class="err">⚠️ Falsches Passwort!</div>
      {% endif %}
    </form>
  </div>
</div>
</body>
</html>"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not WEB_PASSWORD:
        return redirect(url_for('setup'))
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

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """Ersteinrichtung — wird beim ersten Start angezeigt wenn noch kein Passwort gesetzt ist."""
    global WEB_PASSWORD, FRIEND_URL, FRIENDS
    if WEB_PASSWORD:
        return redirect(url_for('login'))
    error = None
    if request.method == 'POST':
        pw         = request.form.get('password', '').strip()
        pw2        = request.form.get('password2', '').strip()
        friend_url = request.form.get('friend_url', '').strip()
        if not pw:
            error = 'Passwort darf nicht leer sein.'
        elif pw != pw2:
            error = 'Passwörter stimmen nicht überein.'
        else:
            _save_password(pw)
            if friend_url:
                _save_friend_url(friend_url)
                FRIENDS    = _parse_friends(friend_url)
                FRIEND_URL = friend_url
            WEB_PASSWORD   = pw
            app.secret_key = pw + "-bmo-secret-42"
            session['authenticated'] = True
            log.info("Ersteinrichtung abgeschlossen.")
            return redirect(url_for('index'))
    from flask import render_template_string
    return render_template_string(SETUP_HTML, error=error)

# ── SETTINGS API ─────────────────────────────────────────────────
@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    cfg = _load_config()
    return jsonify(friends=cfg.get('FRIENDS', ''))

@app.route('/api/settings', methods=['POST'])
@login_required
def save_settings():
    global WEB_PASSWORD, FRIENDS, FRIEND_URL
    data = request.get_json(force=True)
    changed = []

    new_pw = (data.get('password') or '').strip()
    if new_pw:
        _save_password(new_pw)
        WEB_PASSWORD   = new_pw
        app.secret_key = new_pw + "-bmo-secret-42"
        session['authenticated'] = True
        changed.append('password')

    new_friends = (data.get('friends') or '').strip()
    if new_friends is not None:
        _save_friends(new_friends)
        FRIENDS    = _parse_friends(new_friends)
        FRIEND_URL = FRIENDS[0]['url'] if FRIENDS else FRIEND_URL
        changed.append('friends')

    return jsonify(ok=True, changed=changed)

@app.route('/api/friends', methods=['GET'])
@login_required
def list_friends():
    return jsonify(friends=[{'idx': i, 'name': f['name'], 'url': f['url']} for i, f in enumerate(FRIENDS)])

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

  /* ── TIMER BAR ── */
  #timerBar {
    display: none;
    flex-direction: column;
    gap: 4px;
    padding: 8px 12px;
    background: #1a2e1a;
    border-bottom: 1px solid #2d5a2d;
    flex-shrink: 0;
  }
  #timerBar.active { display: flex; }
  .timer-item {
    display: flex;
    align-items: center;
    gap: 10px;
    background: #0f2010;
    border: 1px solid #2d5a2d;
    border-radius: 10px;
    padding: 8px 12px;
    animation: fadeIn .3s ease;
  }
  .timer-item .timer-icon { font-size: 18px; flex-shrink: 0; }
  .timer-item .timer-label { flex: 1; font-size: 13px; color: var(--text2); }
  .timer-item .timer-countdown {
    font-size: 20px;
    font-weight: 700;
    color: #4ade80;
    font-variant-numeric: tabular-nums;
    letter-spacing: 1px;
  }
  .timer-item .timer-progress {
    position: absolute;
    bottom: 0; left: 0;
    height: 3px;
    background: #4ade80;
    border-radius: 0 0 10px 10px;
    transition: width 1s linear;
  }
  .timer-item { position: relative; overflow: hidden; }
  .timer-item.ending .timer-countdown { color: #f97316; }
  .timer-item.critical .timer-countdown { color: #ef4444; animation: pulse .6s infinite; }

  /* ── COMMANDS OVERLAY ── */
  .cmd-category { margin-bottom: 18px; }
  .cmd-category-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--text2);
    text-transform: uppercase;
    letter-spacing: .8px;
    margin-bottom: 8px;
  }
  .cmd-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 8px;
  }
  .cmd-btn {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 10px 8px;
    color: var(--text);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    text-align: center;
    transition: background .15s, transform .1s;
    line-height: 1.3;
  }
  .cmd-btn:active { transform: scale(.95); background: var(--border); }

  /* ── SCREEN OVERLAY ── */
  .screen-overlay {
    align-items: center;
    justify-content: center;
    padding: 0;
  }
  .screen-sheet {
    background: #000;
    border-radius: 16px;
    overflow: hidden;
    width: calc(100% - 24px);
    max-width: 900px;
    max-height: 92dvh;
    display: flex;
    flex-direction: column;
    transform: scale(.9);
    transition: transform .25s cubic-bezier(.32,1,.23,1);
  }
  .overlay.show .screen-sheet { transform: scale(1); }
  .screen-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    background: var(--bg3);
    flex-shrink: 0;
  }
  #screenImg {
    width: 100%;
    height: auto;
    display: block;
    object-fit: contain;
    background: #000;
  }
  #friendScreenImg {
    width: 100%;
    height: auto;
    display: block;
    object-fit: contain;
    background: #000;
  }
  /* Admin-zu-Freund Buttons */
  .qbtn.friend { border-color: #f59e0b; color: #fbbf24; }

  /* ── NOTIFY OVERLAY ── */
  .notify-form input, .notify-form textarea {
    width: 100%;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 11px 14px;
    color: var(--text);
    font-size: 15px;
    margin-bottom: 10px;
    outline: none;
    font-family: inherit;
  }
  .notify-form input:focus, .notify-form textarea:focus { border-color: var(--green); }
  .notify-form textarea { resize: vertical; min-height: 80px; }

  /* ── PROZESS LISTE ── */
  .proc-list { max-height: 52dvh; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
  .proc-item {
    display: flex; align-items: center; gap: 10px;
    background: var(--bg3); border: 1px solid var(--border);
    border-radius: 12px; padding: 9px 12px;
  }
  .proc-name { flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .proc-stats { font-size: 11px; color: var(--text2); flex-shrink: 0; min-width: 90px; text-align: right; }
  .proc-kill {
    background: rgba(239,68,68,.15); border: 1px solid rgba(239,68,68,.3);
    border-radius: 8px; padding: 4px 10px; color: #f87171;
    font-size: 12px; cursor: pointer; flex-shrink: 0;
  }
  .proc-kill:active { opacity: 0.7; }
  .proc-kill:disabled { opacity: 0.4; cursor: default; }

  /* ── DRAW TOOLBAR ── */
  .draw-toolbar {
    position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%);
    display: flex; gap: 8px; align-items: center;
    background: rgba(0,0,0,.8); border: 1px solid #334155;
    border-radius: 20px; padding: 6px 14px;
    backdrop-filter: blur(8px); z-index: 20;
  }
  #drawCanvas {
    position: absolute; top: 0; left: 0;
    width: 100%; height: 100%;
    cursor: crosshair; touch-action: none; z-index: 10;
  }

  /* ── PONG ── */
  #pongCanvas { width: 100%; display: block; border-radius: 12px; background: #0a0a1a; touch-action: none; }
  .pong-score {
    display: flex; justify-content: center; gap: 40px;
    font-size: 36px; font-weight: 700; color: #fff;
    margin-bottom: 8px; font-variant-numeric: tabular-nums;
  }
  .pong-info { text-align: center; color: var(--text2); font-size: 13px; margin-top: 8px; }
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
    <button class="qbtn orange" onclick="confirmShutdown()">
      <span class="icon">⏻</span>Shutdown
    </button>
    <button class="qbtn red" onclick="triggerJumpscare()">
      <span class="icon">👻</span>Jumpscare
    </button>
    <button class="qbtn" onclick="showCommands()" style="border-color:#6366f1;color:#818cf8;">
      <span class="icon">📋</span>Befehle
    </button>
    <button class="qbtn" onclick="showScreen()" style="border-color:#0ea5e9;color:#38bdf8;">
      <span class="icon">🖥️</span>Screen
    </button>
    <button class="qbtn" onclick="showNotify()" style="border-color:#06b6d4;color:#22d3ee;">
      <span class="icon">🔔</span>Notify
    </button>
    <button class="qbtn" onclick="showProcesses()" style="border-color:#fb923c;color:#fdba74;">
      <span class="icon">📋</span>Prozesse
    </button>
    <button class="qbtn" onclick="showSpiele()" style="border-color:#22c55e;color:#4ade80;position:relative;">
      <span class="icon">🎮</span>Spiele
      <span id="pongBadge" style="display:none;position:absolute;top:-5px;right:-5px;background:#ef4444;color:#fff;border-radius:50%;width:18px;height:18px;font-size:11px;font-weight:700;align-items:center;justify-content:center;animation:pulse .8s infinite;">!</span>
    </button>
    <button class="qbtn friend" onclick="showFreunde()">
      <span class="icon">👥</span>Freunde
    </button>
    <button class="qbtn" onclick="showSettings()" style="border-color:#475569;color:#94a3b8;">
      <span class="icon">⚙️</span>Settings
    </button>
    <button class="qbtn" id="liteModeBtn" onclick="toggleLiteMode()" style="border-color:#475569;color:#94a3b8;">
      <span class="icon">⚡</span>Lite
    </button>
  </div>

  <!-- TIMER BAR -->
  <div id="timerBar"></div>

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
    <div id="nowPlaying" style="background:var(--bg3);border:1px solid var(--border);border-radius:14px;padding:12px 14px;margin-bottom:16px;display:flex;align-items:center;gap:12px;">
      <img id="npCover" src="" alt=""
        style="width:64px;height:64px;border-radius:10px;object-fit:cover;flex-shrink:0;background:var(--bg2);display:none;">
      <span id="npIcon" style="font-size:28px;flex-shrink:0;">🎵</span>
      <div style="flex:1;overflow:hidden;">
        <div id="npTrack"  style="font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Lädt...</div>
        <div id="npArtist" style="font-size:12px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px;"></div>
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

<!-- FREUNDE OVERLAY -->
<div class="overlay" id="friendsOverlay" onclick="closeOverlay('friendsOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
      <h2 style="margin:0;">👥 Freunde</h2>
      <button onclick="toggleFriendsEdit()"
        style="background:none;border:1px solid var(--border);border-radius:10px;color:var(--text2);padding:6px 12px;cursor:pointer;font-size:13px;">✏️ Bearbeiten</button>
    </div>
    <!-- Edit-Bereich (standardmäßig versteckt) -->
    <div id="friendsEditArea" style="display:none;margin-bottom:16px;">
      <div style="font-size:13px;color:var(--text2);margin-bottom:6px;">Name|http://IP:5000 — eine pro Zeile</div>
      <textarea id="friendsEditInput" rows="4" placeholder="Alice|http://100.x.x.x:5000&#10;Bob|http://100.y.y.y:5000"
        style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:11px 14px;color:var(--text);font-size:14px;outline:none;box-sizing:border-box;resize:vertical;font-family:monospace;"></textarea>
      <div id="friendsEditMsg" style="font-size:13px;color:#5eead4;min-height:16px;margin-top:4px;"></div>
      <button onclick="saveFriendsEdit()"
        style="width:100%;margin-top:8px;padding:12px;background:var(--green);border:none;border-radius:12px;color:#000;font-size:14px;font-weight:600;cursor:pointer;">Speichern</button>
    </div>
    <button onclick="scareAll()"
      style="width:100%;padding:14px;background:#f59e0b;border:none;border-radius:14px;color:#000;font-size:15px;font-weight:700;cursor:pointer;margin-bottom:16px;">
      👻 Alle gleichzeitig schrecken
    </button>
    <div id="friendsList"></div>
    <button class="btn-primary" onclick="closeOverlay('friendsOverlay')" style="margin-top:14px;">Schließen</button>
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


<!-- COMMANDS OVERLAY -->
<div class="overlay" id="commandsOverlay" onclick="closeOverlay('commandsOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>📋 Alle Befehle</h2>
    <div id="commandsList">
      <div class="notes-empty">Lade...</div>
    </div>
    <button class="btn-primary" onclick="closeOverlay('commandsOverlay')" style="margin-top:14px;">Schließen</button>
  </div>
</div>

<!-- SCREEN OVERLAY -->
<div class="overlay screen-overlay" id="screenOverlay">
  <div class="screen-sheet" onclick="event.stopPropagation()">
    <div class="screen-header">
      <span style="font-weight:600;font-size:15px;color:#e2e8f0;">🖥️ Bildschirm Live</span>
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
        <span id="screenFps" style="font-size:11px;color:#64748b;"></span>
        <button id="remoteBtn" onclick="toggleRemote()"
          style="background:none;border:1px solid #334155;border-radius:8px;color:#94a3b8;padding:4px 10px;cursor:pointer;font-size:12px;transition:color .2s,border-color .2s;">
          🖱 Steuerung
        </button>
        <button id="drawScreenBtn" onclick="toggleDraw()"
          style="background:none;border:1px solid #334155;border-radius:8px;color:#94a3b8;padding:4px 10px;cursor:pointer;font-size:12px;transition:color .2s,border-color .2s;">
          ✏️ Zeichnen
        </button>
        <button onclick="toggleFullscreen('screenImg')"
          style="background:none;border:1px solid #334155;border-radius:8px;color:#94a3b8;padding:4px 10px;cursor:pointer;font-size:13px;">⛶ Vollbild</button>
        <button onclick="closeScreen()"
          style="background:none;border:1px solid #334155;border-radius:8px;color:#94a3b8;padding:4px 10px;cursor:pointer;font-size:13px;">
          ✕
        </button>
      </div>
    </div>
    <div style="position:relative;line-height:0;">
      <img id="screenImg" src="" alt="Bildschirm wird geladen..." style="width:100%;display:block;">
      <canvas id="drawCanvas" style="display:none;"></canvas>
      <div class="draw-toolbar" id="drawToolbar" style="display:none;">
        <input type="color" id="drawColor" value="#ff3333"
          style="width:28px;height:28px;border:none;border-radius:6px;cursor:pointer;background:none;padding:0;">
        <input type="range" id="drawWidth" min="2" max="20" value="5"
          style="width:70px;accent-color:var(--green);">
        <button onclick="clearDraw()"
          style="background:none;border:1px solid #475569;border-radius:8px;color:#94a3b8;padding:3px 10px;font-size:12px;cursor:pointer;">
          🗑
        </button>
      </div>
    </div>
    <div id="monitorPicker" style="display:flex;gap:6px;padding:6px 8px 2px;flex-wrap:wrap;"></div>
  </div>
</div>

<!-- FREUND SCREEN OVERLAY -->
<div class="overlay screen-overlay" id="friendScreenOverlay">
  <div class="screen-sheet" onclick="event.stopPropagation()">
    <div class="screen-header">
      <span id="friendScreenTitle" style="font-weight:600;font-size:15px;color:#fbbf24;">🖥️ Freund – Bildschirm Live</span>
      <div style="display:flex;gap:8px;align-items:center;">
        <span id="friendScreenStatus" style="font-size:11px;color:#64748b;"></span>
        <button onclick="toggleFullscreen('friendScreenImg')"
          style="background:none;border:1px solid #334155;border-radius:8px;color:#94a3b8;padding:5px 12px;cursor:pointer;font-size:13px;">⛶ Vollbild</button>
        <button onclick="closeFriendScreen()"
          style="background:none;border:1px solid #334155;border-radius:8px;color:#94a3b8;padding:5px 12px;cursor:pointer;font-size:13px;">
          ✕ Schließen
        </button>
      </div>
    </div>
    <div id="friendMonitorPicker" style="display:flex;gap:6px;padding:6px 0 2px;flex-wrap:wrap;"></div>
    <img id="friendScreenImg" src="" alt="Freund Bildschirm wird geladen..." ondblclick="toggleFullscreen('friendScreenImg')">
  </div>
</div>

<!-- SETTINGS OVERLAY -->
<div class="overlay" id="settingsOverlay" onclick="closeOverlay('settingsOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>⚙️ Einstellungen</h2>
    <div class="lbl" style="margin-top:12px;">Neues Passwort <span style="color:#555;font-weight:400;">(leer = keine Änderung)</span></div>
    <input type="password" id="setPw" placeholder="Neues Passwort..." autocomplete="new-password"
      style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:11px 14px;color:var(--text);font-size:15px;outline:none;box-sizing:border-box;margin-top:6px;">
    <div class="lbl" style="margin-top:14px;">Freunde <span style="color:#555;font-weight:400;">(Name|http://IP:5000, eine pro Zeile)</span></div>
    <textarea id="setFriends" rows="4" placeholder="Alice|http://100.x.x.x:5000&#10;Bob|http://100.y.y.y:5000"
      style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:11px 14px;color:var(--text);font-size:14px;outline:none;box-sizing:border-box;margin-top:6px;resize:vertical;font-family:monospace;"></textarea>
    <div id="settingsMsg" style="font-size:13px;color:#5eead4;min-height:18px;margin-top:8px;"></div>
    <div style="display:flex;gap:8px;margin-top:14px;">
      <button onclick="closeOverlay('settingsOverlay')"
        style="flex:1;padding:12px;border-radius:12px;border:1px solid var(--border);background:none;color:var(--text-muted);cursor:pointer;font-size:14px;">Abbrechen</button>
      <button onclick="saveSettings()"
        style="flex:2;padding:12px;border-radius:12px;border:none;background:var(--green);color:#000;cursor:pointer;font-size:14px;font-weight:600;">Speichern</button>
    </div>
  </div>
</div>

<!-- FREUNDE OVERLAY -->
<div class="overlay" id="freundeOverlay" onclick="closeOverlay('freundeOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2 id="freundeOverlayTitle">👥 Freund Aktionen</h2>
    <p style="color:var(--text2);font-size:13px;margin-bottom:18px;">Alles was du mit deinem Freund machen kannst.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
      <button onclick="closeOverlay('freundeOverlay');showFriendScreen(_selectedFriendIdx,_selectedFriendName)"
        style="padding:16px 12px;background:var(--bg3);border:1px solid #0ea5e9;border-radius:14px;color:#38bdf8;font-size:14px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;">
        <span style="font-size:22px;">🖥️</span>Screen ansehen
      </button>
      <button onclick="triggerFriendJumpscare(_selectedFriendIdx,_selectedFriendName);closeOverlay('freundeOverlay')"
        style="padding:16px 12px;background:var(--bg3);border:1px solid #ef4444;border-radius:14px;color:#f87171;font-size:14px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;">
        <span style="font-size:22px;">👻</span>Jumpscare
      </button>
      <button onclick="closeOverlay('freundeOverlay');showFreundNotify(_selectedFriendIdx)"
        style="padding:16px 12px;background:var(--bg3);border:1px solid #06b6d4;border-radius:14px;color:#22d3ee;font-size:14px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;">
        <span style="font-size:22px;">🔔</span>Notification
      </button>
      <button onclick="closeOverlay('freundeOverlay');showFreundProcesses(_selectedFriendIdx)"
        style="padding:16px 12px;background:var(--bg3);border:1px solid #fb923c;border-radius:14px;color:#fdba74;font-size:14px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;">
        <span style="font-size:22px;">📋</span>Prozesse
      </button>
      <button onclick="closeOverlay('freundeOverlay');challengeFriendPong(_selectedFriendIdx)"
        style="padding:16px 12px;background:var(--bg3);border:1px solid #22c55e;border-radius:14px;color:#4ade80;font-size:14px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;grid-column:span 2;">
        <span style="font-size:22px;">🏓</span>Pong herausfordern
      </button>
      <button onclick="closeOverlay('freundeOverlay');showFriendDraw(_selectedFriendIdx,_selectedFriendName)"
        style="padding:16px 12px;background:var(--bg3);border:1px solid #f472b6;border-radius:14px;color:#f472b6;font-size:14px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:6px;grid-column:span 2;">
        <span style="font-size:22px;">✏️</span>Auf Bildschirm zeichnen
      </button>
    </div>
    <button class="btn-primary" onclick="closeOverlay('freundeOverlay')" style="margin-top:14px;background:var(--bg3);">Schließen</button>
  </div>
</div>

<!-- FREUND DRAW OVERLAY -->
<div class="overlay" id="friendDrawOverlay" onclick="closeFriendDraw()">
  <div class="sheet" onclick="event.stopPropagation()" style="max-height:90dvh;">
    <div class="sheet-handle"></div>
    <h2>✏️ Auf Bildschirm zeichnen</h2>
    <div id="friendDrawMonitorPicker" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;"></div>
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;">
      <input type="color" id="friendDrawColor" value="#ff3333" style="width:36px;height:36px;border:none;border-radius:8px;cursor:pointer;background:none;">
      <input type="range" id="friendDrawWidth" min="2" max="20" value="5" style="flex:1;">
      <button onclick="sendFriendDraw('clear',{})"
        style="padding:6px 12px;background:none;border:1px solid #475569;border-radius:8px;color:#94a3b8;cursor:pointer;">🗑</button>
    </div>
    <canvas id="friendDrawCanvas"
      style="width:100%;aspect-ratio:16/9;background:#111;border-radius:12px;cursor:crosshair;touch-action:none;"></canvas>
    <p style="color:var(--text2);font-size:12px;margin-top:8px;text-align:center;">Zeichne hier — erscheint auf dem Bildschirm des Freundes</p>
    <button class="btn-primary" onclick="closeFriendDraw()" style="margin-top:10px;background:#f472b6;">Beenden</button>
  </div>
</div>

<!-- FREUND NOTIFY OVERLAY -->
<div class="overlay" id="freundNotifyOverlay" onclick="closeOverlay('freundNotifyOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>🔔 Notification an Freund</h2>
    <div class="notify-form">
      <input type="text" id="freundNotifyTitle" placeholder="Titel (z.B. BMO)" maxlength="64">
      <textarea id="freundNotifyMsg" placeholder="Nachricht..."></textarea>
    </div>
    <button class="btn-primary" onclick="sendFreundNotification()">🔔 Senden</button>
    <button class="btn-primary" onclick="closeOverlay('freundNotifyOverlay')"
      style="background:var(--bg3);border:1px solid var(--border);margin-top:8px;">Abbrechen</button>
  </div>
</div>

<!-- FREUND PROZESSE OVERLAY -->
<div class="overlay" id="freundProcessesOverlay" onclick="closeOverlay('freundProcessesOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
      <h2 style="margin:0;">📋 Freund – Prozesse</h2>
      <button onclick="loadFreundProcesses()"
        style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;color:var(--text2);padding:5px 14px;font-size:13px;cursor:pointer;">
        ↻ Reload
      </button>
    </div>
    <div class="proc-list" id="freundProcList">
      <div class="notes-empty">Lade...</div>
    </div>
    <button class="btn-primary" onclick="closeOverlay('freundProcessesOverlay')" style="margin-top:12px;">Schließen</button>
  </div>
</div>

<!-- SPIELE OVERLAY -->
<div class="overlay" id="spieleOverlay" onclick="closeOverlay('spieleOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>🎮 Spiele</h2>
    <div style="display:grid;gap:10px;margin-top:8px;">
      <button onclick="closeOverlay('spieleOverlay');showPong()"
        style="padding:20px;background:var(--bg3);border:1px solid #22c55e;border-radius:14px;color:#4ade80;font-size:16px;cursor:pointer;display:flex;align-items:center;gap:14px;">
        <span style="font-size:28px;">🏓</span>
        <div style="text-align:left;">
          <div style="font-weight:600;">Pong</div>
          <div style="font-size:12px;color:var(--text2);margin-top:2px;">Du vs KI · Fordere Freund heraus</div>
        </div>
      </button>
    </div>
    <button class="btn-primary" onclick="closeOverlay('spieleOverlay')" style="margin-top:14px;background:var(--bg3);">Schließen</button>
  </div>
</div>

<!-- SETTINGS OVERLAY -->
<div class="overlay" id="settingsOverlay" onclick="closeOverlay('settingsOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>⚙️ Settings</h2>
    <div style="margin-bottom:14px;">
      <div style="color:var(--text2);font-size:13px;margin-bottom:8px;">Admin-Zugriff für Freunde</div>
      <div style="color:var(--text3);font-size:12px;margin-bottom:10px;">
        Erlaubt Freunden Screen, Prozesse, Notify und Pong über deinen BMO-Link zu nutzen.
      </div>
      <button id="adminToggleBtn" onclick="toggleAdminAccess()"
        style="width:100%;padding:14px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;color:var(--text2);font-size:15px;cursor:pointer;transition:border-color .2s,color .2s;">
        🔒 Admin-Zugriff: AUS
      </button>
    </div>
    <button class="btn-primary" onclick="closeOverlay('settingsOverlay')" style="background:var(--bg3);">Schließen</button>
  </div>
</div>

<!-- NOTIFY OVERLAY -->
<div class="overlay" id="notifyOverlay" onclick="closeOverlay('notifyOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <h2>🔔 Windows Notification</h2>
    <p style="color:var(--text2);font-size:13px;margin-bottom:16px;">Sendet ein Popup direkt auf den PC-Bildschirm.</p>
    <div class="notify-form">
      <input type="text" id="notifyTitle" placeholder="Titel (z.B. BMO)" maxlength="64">
      <textarea id="notifyMsg" placeholder="Nachricht..."></textarea>
    </div>
    <button class="btn-primary" onclick="sendNotification()">🔔 Senden</button>
    <button class="btn-primary" onclick="closeOverlay('notifyOverlay')"
      style="background:var(--bg3);border:1px solid var(--border);margin-top:8px;">Abbrechen</button>
  </div>
</div>

<!-- PROZESSE OVERLAY -->
<div class="overlay" id="processesOverlay" onclick="closeOverlay('processesOverlay')">
  <div class="sheet" onclick="event.stopPropagation()">
    <div class="sheet-handle"></div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
      <h2 style="margin:0;">📋 Prozesse</h2>
      <button onclick="loadProcesses()"
        style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;color:var(--text2);padding:5px 14px;font-size:13px;cursor:pointer;">
        ↻ Reload
      </button>
    </div>
    <div class="proc-list" id="procList">
      <div class="notes-empty">Lade...</div>
    </div>
    <button class="btn-primary" onclick="closeOverlay('processesOverlay')" style="margin-top:12px;">Schließen</button>
  </div>
</div>

<!-- PONG OVERLAY -->
<div class="overlay" id="pongOverlay" onclick="void(0)">
  <div class="sheet" onclick="event.stopPropagation()" style="max-width:640px;">
    <div class="sheet-handle"></div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
      <h2 style="margin:0;">🏓 BMO Pong</h2>
      <button onclick="closePong()"
        style="background:none;border:1px solid var(--border);border-radius:8px;color:var(--text2);padding:5px 12px;font-size:13px;cursor:pointer;">✕</button>
    </div>
    <div class="pong-score">
      <span id="pongScoreL" style="color:#2b8773;">0</span>
      <span style="color:#475569;">:</span>
      <span id="pongScoreR" style="color:#f97316;">0</span>
    </div>
    <canvas id="pongCanvas" width="600" height="380"></canvas>
    <div class="pong-info" id="pongInfo">Verbinde...</div>
    <div id="pongChallengeBanner" style="display:none;margin-top:10px;padding:12px;background:#1e3a2f;border:1px solid #4ade80;border-radius:12px;text-align:center;">
      <div style="color:#4ade80;font-size:15px;margin-bottom:8px;">🏓 Dein Freund fordert dich heraus!</div>
      <button onclick="acceptPongChallenge()"
        style="padding:10px 24px;background:#4ade80;border:none;border-radius:10px;color:#000;font-size:14px;font-weight:700;cursor:pointer;">
        ✅ Annehmen
      </button>
    </div>
    <div style="display:flex;gap:8px;margin-top:10px;">
      <button onclick="pongReset()"
        style="flex:1;padding:12px;background:var(--bg3);border:1px solid var(--border);border-radius:12px;color:var(--text);font-size:14px;cursor:pointer;">
        ↺ Reset
      </button>
      <button onclick="closePong()"
        style="flex:1;padding:12px;background:var(--bg3);border:1px solid var(--border);border-radius:12px;color:var(--text);font-size:14px;cursor:pointer;">
        Beenden
      </button>
    </div>
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
loadFriends();

// ── TIMER ────────────────────────────────────────────────────────
let _knownTimers = {};  // id → {label, duration} für Abschluss-Erkennung

function fmtTime(secs) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0
    ? m + ':' + String(s).padStart(2, '0')
    : s + 's';
}

async function pollTimers() {
  try {
    const r = await fetch('/api/timers');
    const d = await r.json();
    const timers = d.timers || [];
    const bar    = document.getElementById('timerBar');

    // Abgelaufene Timer erkennen (waren in _knownTimers, fehlen jetzt)
    const currentIds = new Set(timers.map(t => t.id));
    for (const [id, info] of Object.entries(_knownTimers)) {
      if (!currentIds.has(parseInt(id))) {
        addMsg(`⏰ Timer abgelaufen: ${info.label}`, 'sys');
        delete _knownTimers[id];
      }
    }

    // Aktuelle Timer merken
    timers.forEach(t => { _knownTimers[t.id] = {label: t.label, duration: t.duration}; });

    if (!timers.length) {
      bar.classList.remove('active');
      bar.innerHTML = '';
      return;
    }

    bar.classList.add('active');
    bar.innerHTML = timers.map(t => {
      const pct   = Math.round((t.remaining / t.duration) * 100);
      const cls   = t.remaining <= 10 ? 'critical' : t.remaining <= 30 ? 'ending' : '';
      return `<div class="timer-item ${cls}">
        <span class="timer-icon">⏱️</span>
        <span class="timer-label">${t.label}</span>
        <span class="timer-countdown">${fmtTime(t.remaining)}</span>
        <div class="timer-progress" style="width:${pct}%"></div>
      </div>`;
    }).join('');
  } catch(e) {}
}

pollTimers();
setInterval(pollTimers, 1000);


// ── OVERLAY ─────────────────────────────────────────────────────
function showStats()       { updateStatus(); document.getElementById('statsOverlay').classList.add('show'); }
function confirmShutdown() { document.getElementById('shutdownOverlay').classList.add('show'); }
function closeOverlay(id)  { document.getElementById(id).classList.remove('show'); }

// ── COMMANDS OVERLAY ─────────────────────────────────────────────
async function showCommands() {
  document.getElementById('commandsOverlay').classList.add('show');
  const list = document.getElementById('commandsList');
  try {
    const r = await fetch('/api/commands');
    const d = await r.json();
    list.innerHTML = '';
    d.commands.forEach(cat => {
      const section = document.createElement('div');
      section.className = 'cmd-category';
      section.innerHTML = `<div class="cmd-category-title">${cat.icon} ${cat.category}</div>`;
      const grid = document.createElement('div');
      grid.className = 'cmd-grid';
      cat.items.forEach(item => {
        const btn = document.createElement('button');
        btn.className = 'cmd-btn';
        btn.textContent = item.label;
        btn.onclick = () => runCommand(item.msg);
        grid.appendChild(btn);
      });
      section.appendChild(grid);
      list.appendChild(section);
    });
  } catch(e) {
    list.innerHTML = '<div class="notes-empty">Fehler beim Laden.</div>';
  }
}

function runCommand(msg) {
  closeOverlay('commandsOverlay');
  input.value = msg;
  send();
}

// ── SCREEN OVERLAY ───────────────────────────────────────────────
let _screenActive = false;

async function showScreen() {
  _screenActive = true;
  document.getElementById('screenOverlay').classList.add('show');
  document.getElementById('screenImg').src = '/api/screen?' + Date.now();
  await loadMonitorPicker();
}

async function loadMonitorPicker() {
  try {
    const r = await fetch('/api/screen/monitors');
    const d = await r.json();
    const picker = document.getElementById('monitorPicker');
    picker.innerHTML = '';
    d.monitors.forEach(m => {
      const btn = document.createElement('button');
      btn.textContent = m.label;
      btn.dataset.idx = m.idx;
      btn.style.cssText = 'padding:4px 10px;border-radius:8px;font-size:12px;cursor:pointer;border:1px solid ' +
        (m.idx === d.active ? '#38bdf8;background:#0ea5e9;color:#fff;font-weight:600;' : '#334155;background:none;color:#94a3b8;');
      btn.onclick = () => selectMonitor(m.idx);
      picker.appendChild(btn);
    });
  } catch(e) {}
}

async function selectMonitor(idx) {
  _currentMonitorIdx = idx;
  await fetch('/api/screen/monitor', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({idx})});
  document.getElementById('screenImg').src = '/api/screen?' + Date.now();
  await loadMonitorPicker();
}

function closeScreen() {
  _screenActive = false;
  // Deaktiviere Remote/Draw beim Schließen
  if (_remoteOn) { _remoteOn = false; fetch('/api/remote/toggle',{method:'POST'}).catch(()=>{}); disableRemoteCapture(); }
  if (_drawMode)  { _drawMode = false;
    document.getElementById('drawCanvas').style.display = 'none';
    document.getElementById('drawToolbar').style.display = 'none';
    fetch('/api/draw', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'close'})}).catch(()=>{});
  }
  document.getElementById('screenOverlay').classList.remove('show');
  setTimeout(() => {
    if (!_screenActive) document.getElementById('screenImg').src = '';
  }, 300);
}

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

// ── FREUNDE (dynamisch) ──────────────────────────────────────────
let _friends = [];

async function loadFriends() {
  try {
    const r = await fetch('/api/friends');
    const d = await r.json();
    _friends = d.friends || [];
  } catch(e) {}
}

function renderFriendsList() {
  const list = document.getElementById('friendsList');
  if (!list) return;
  list.innerHTML = '';
  if (!_friends.length) {
    list.innerHTML = '<div style="color:var(--text2);font-size:14px;text-align:center;padding:16px;">Keine Freunde eingetragen.<br>Gehe zu Settings um Freunde hinzuzufügen.</div>';
    return;
  }
  _friends.forEach(f => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:8px;align-items:center;margin-bottom:12px;padding:10px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:14px;';
    row.id = `friendRow_${f.idx}`;
    row.innerHTML = `
      <div style="flex:1;min-width:0;">
        <div style="font-size:15px;font-weight:600;">${f.name}</div>
        <div id="friendStatus_${f.idx}" style="font-size:12px;color:var(--text2);margin-top:2px;">⏳ Prüfe...</div>
      </div>
      <button onclick="triggerFriendJumpscare(${f.idx},'${f.name}')" id="friendScareBtn_${f.idx}"
        style="padding:8px 12px;background:var(--bg3);border:1px solid #f59e0b;border-radius:10px;color:#fbbf24;font-size:13px;cursor:pointer;opacity:.4;" disabled>👻</button>
      <button onclick="closeOverlay('friendsOverlay');showFriendScreen(${f.idx},'${f.name}')" id="friendScreenBtn_${f.idx}"
        style="padding:8px 12px;background:var(--bg3);border:1px solid #0ea5e9;border-radius:10px;color:#38bdf8;font-size:13px;cursor:pointer;opacity:.4;" disabled>🖥️</button>
      <button onclick="selectFriendActions(${f.idx},'${f.name}')" id="friendMoreBtn_${f.idx}"
        style="padding:8px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:10px;color:var(--text2);font-size:13px;cursor:pointer;">⋯</button>`;
    list.appendChild(row);
    fetchFriendInfo(f.idx);
  });
}

async function fetchFriendInfo(idx) {
  const statusEl = document.getElementById(`friendStatus_${idx}`);
  const scareBtn = document.getElementById(`friendScareBtn_${idx}`);
  const screenBtn = document.getElementById(`friendScreenBtn_${idx}`);
  try {
    const r = await fetch(`/api/friend/${idx}/info`);
    const d = await r.json();
    if (!d.online) {
      statusEl.innerHTML = '<span style="color:#ef4444;">● Offline</span>';
      return;
    }
    const adminTxt = d.admin_access
      ? '<span style="color:#4ade80;">✓ Admin-Zugriff aktiv</span>'
      : '<span style="color:#94a3b8;">✗ Admin-Zugriff gesperrt</span>';
    statusEl.innerHTML = '<span style="color:#4ade80;">● Online</span> · ' + adminTxt;
    scareBtn.disabled = false; scareBtn.style.opacity = '1';
    if (d.admin_access) { screenBtn.disabled = false; screenBtn.style.opacity = '1'; }
  } catch(e) {
    statusEl.innerHTML = '<span style="color:#ef4444;">● Offline</span>';
  }
}

function showFriends() {
  renderFriendsList();
  document.getElementById('friendsEditArea').style.display = 'none';
  document.getElementById('friendsOverlay').classList.add('show');
}

function toggleFriendsEdit() {
  const area = document.getElementById('friendsEditArea');
  const open = area.style.display !== 'none';
  if (open) {
    area.style.display = 'none';
  } else {
    document.getElementById('friendsEditInput').value =
      (_friends.map(f => f.name + '|' + (f.url || '')).join('\\n'));
    document.getElementById('friendsEditMsg').textContent = '';
    area.style.display = '';
  }
}

async function saveFriendsEdit() {
  const raw = document.getElementById('friendsEditInput').value
                .split('\\n').map(s => s.trim()).filter(Boolean).join(',');
  const msg = document.getElementById('friendsEditMsg');
  msg.textContent = 'Speichere...';
  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({friends: raw})
    });
    const d = await r.json();
    if (d.ok) {
      msg.textContent = 'Gespeichert ✓';
      await loadFriends();
      renderFriendsList();
      setTimeout(() => { document.getElementById('friendsEditArea').style.display = 'none'; }, 800);
    } else {
      msg.style.color = '#f87171';
      msg.textContent = 'Fehler beim Speichern.';
    }
  } catch(e) {
    msg.style.color = '#f87171';
    msg.textContent = 'Verbindungsfehler.';
  }
}

function toggleFullscreen(imgId) {
  const el = document.getElementById(imgId);
  if (!document.fullscreenElement) {
    el.requestFullscreen && el.requestFullscreen();
  } else {
    document.exitFullscreen && document.exitFullscreen();
  }
}

async function triggerFriendJumpscare(idx, name) {
  try {
    const r = await fetch(`/api/friend/${idx}/jumpscare`, {method: 'POST'});
    const d = await r.json();
    addMsg(d.ok ? `👻 Jumpscare an ${name} gesendet!` : `⛔ ${name}: ${d.error || 'Admin-Zugriff nicht aktiviert.'}`, 'sys');
  } catch(e) {
    addMsg(`${name} nicht erreichbar 😢`, 'sys');
  }
}

async function scareAll() {
  if (!_friends.length) return;
  closeOverlay('friendsOverlay');
  addMsg('👻 Scare an alle Freunde...', 'sys');
  await Promise.all(_friends.map(f => triggerFriendJumpscare(f.idx, f.name)));
}

let _friendScreenActive = false;
let _friendScreenIdx = 0;

async function showFriendScreen(idx, name) {
  _friendScreenActive = true;
  _friendScreenIdx = idx;
  document.getElementById('friendScreenTitle').textContent = `🖥️ ${name} – Bildschirm Live`;
  document.getElementById('friendScreenStatus').textContent = 'Verbinde...';
  document.getElementById('friendMonitorPicker').innerHTML = '';
  document.getElementById('friendScreenOverlay').classList.add('show');
  const img = document.getElementById('friendScreenImg');
  img.src = `/api/friend/${idx}/screen?` + Date.now();
  img.onload  = () => { document.getElementById('friendScreenStatus').textContent = 'Live'; };
  img.onerror = () => { document.getElementById('friendScreenStatus').textContent = '⛔ Kein Zugriff'; img.src = ''; };
  await loadFriendMonitorPicker(idx);
}

async function loadFriendMonitorPicker(idx) {
  try {
    const r = await fetch(`/api/friend/${idx}/screen/monitors`);
    const d = await r.json();
    const picker = document.getElementById('friendMonitorPicker');
    picker.innerHTML = '';
    (d.monitors || []).forEach(m => {
      const btn = document.createElement('button');
      btn.textContent = m.label;
      btn.style.cssText = 'padding:4px 10px;border-radius:8px;font-size:12px;cursor:pointer;border:1px solid ' +
        (m.idx === d.active ? '#fbbf24;background:#f59e0b;color:#000;font-weight:600;' : '#334155;background:none;color:#94a3b8;');
      btn.onclick = () => selectFriendMonitor(idx, m.idx);
      picker.appendChild(btn);
    });
  } catch(e) {}
}

async function selectFriendMonitor(friendIdx, monIdx) {
  await fetch(`/api/friend/${friendIdx}/screen/monitor`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({idx: monIdx})});
  const img = document.getElementById('friendScreenImg');
  img.src = `/api/friend/${friendIdx}/screen?` + Date.now();
  await loadFriendMonitorPicker(friendIdx);
}

function closeFriendScreen() {
  _friendScreenActive = false;
  document.getElementById('friendScreenOverlay').classList.remove('show');
  setTimeout(() => { if (!_friendScreenActive) document.getElementById('friendScreenImg').src = ''; }, 300);
}

// ── SETTINGS ─────────────────────────────────────────────────────
async function toggleAdminAccess() {
  try {
    const r = await fetch('/api/admin/toggle', {method:'POST'});
    const d = await r.json();
    const btn = document.getElementById('adminToggleBtn');
    if (btn) {
      btn.textContent = d.enabled ? '🔓 Admin-Zugriff: AN' : '🔒 Admin-Zugriff: AUS';
      btn.style.borderColor = d.enabled ? '#4ade80' : '';
      btn.style.color = d.enabled ? '#4ade80' : '';
    }
  } catch(e) {}
}

async function showSettings() {
  try {
    const r = await fetch('/api/settings');
    const d = await r.json();
    document.getElementById('setFriends').value =
      (d.friends || '').split(',').map(s => s.trim()).filter(Boolean).join('\\n');
  } catch(e) {}
  document.getElementById('setPw').value = '';
  document.getElementById('settingsMsg').style.color = '#5eead4';
  document.getElementById('settingsMsg').textContent = '';
  document.getElementById('settingsOverlay').classList.add('show');
}

async function saveSettings() {
  const pw      = document.getElementById('setPw').value.trim();
  const friends = document.getElementById('setFriends').value
                    .split('\\n').map(s => s.trim()).filter(Boolean).join(',');
  const msg = document.getElementById('settingsMsg');
  msg.textContent = 'Speichere...';
  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({password: pw, friends})
    });
    const d = await r.json();
    if (d.ok) {
      msg.textContent = 'Gespeichert ✓';
      await loadFriends();
      setTimeout(() => closeOverlay('settingsOverlay'), 800);
    } else {
      msg.style.color = '#fca5a5'; msg.textContent = 'Fehler';
    }
  } catch(e) {
    msg.style.color = '#fca5a5'; msg.textContent = 'Verbindungsfehler';
  }
}
// ── FREUNDE OVERLAY ──────────────────────────────────────────────
let _selectedFriendIdx = 0;
let _selectedFriendName = '';

function showFreunde() {
  renderFriendsList();
  document.getElementById('friendsOverlay').classList.add('show');
}

let _friendDrawActive = false;
let _friendDrawIdx = 0;

async function showFriendDraw(idx, name) {
  _friendDrawIdx = idx;
  _friendDrawActive = true;
  // Lade Monitore des Freundes
  try {
    const r = await fetch(`/api/friend/${idx}/draw/monitors`);
    const d = await r.json();
    const picker = document.getElementById('friendDrawMonitorPicker');
    if (picker && d.monitors) {
      picker.innerHTML = d.monitors.map(m =>
        `<button onclick="setFriendDrawMonitor(${m.idx})" id="fdmon_${m.idx}"
          style="padding:6px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);cursor:pointer;font-size:13px;">${m.label}</button>`
      ).join('');
      if (d.monitors.length > 0) setFriendDrawMonitor(d.monitors[0].idx);
    }
  } catch(e) {}
  document.getElementById('friendDrawOverlay').classList.add('show');
}

let _friendDrawMonitor = 1;
function setFriendDrawMonitor(idx) {
  _friendDrawMonitor = idx;
  document.querySelectorAll('[id^="fdmon_"]').forEach(b => {
    b.style.borderColor = b.id === `fdmon_${idx}` ? '#f472b6' : '';
    b.style.color = b.id === `fdmon_${idx}` ? '#f472b6' : '';
  });
}

async function sendFriendDraw(action, stroke) {
  try {
    await fetch(`/api/friend/${_friendDrawIdx}/draw`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action, ...stroke, monitor: _friendDrawMonitor})
    });
  } catch(e) {}
}

function closeFriendDraw() {
  _friendDrawActive = false;
  sendFriendDraw('close', {});
  closeOverlay('friendDrawOverlay');
}

(function _initFriendDrawCanvas() {
  let _fDrawing = false, _fStroke = null;
  function _setup() {
    const canvas = document.getElementById('friendDrawCanvas');
    if (!canvas) return;
    canvas.width  = canvas.offsetWidth  || 640;
    canvas.height = canvas.offsetHeight || 360;
    const ctx = canvas.getContext('2d');
    function getPos(e) {
      const rect = canvas.getBoundingClientRect();
      const t = e.touches ? e.touches[0] : e;
      return { x: (t.clientX - rect.left) / rect.width, y: (t.clientY - rect.top) / rect.height };
    }
    function startDraw(e) {
      e.preventDefault(); _fDrawing = true;
      const p = getPos(e);
      const color = document.getElementById('friendDrawColor').value;
      const width = parseInt(document.getElementById('friendDrawWidth').value);
      _fStroke = {pts: [[p.x, p.y]], color, width};
      ctx.beginPath(); ctx.moveTo(p.x * canvas.width, p.y * canvas.height);
      ctx.strokeStyle = color; ctx.lineWidth = width;
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    }
    function doDraw(e) {
      e.preventDefault();
      if (!_fDrawing || !_fStroke) return;
      const p = getPos(e);
      _fStroke.pts.push([p.x, p.y]);
      ctx.lineTo(p.x * canvas.width, p.y * canvas.height); ctx.stroke();
    }
    function endDraw() {
      if (!_fDrawing || !_fStroke) return;
      _fDrawing = false;
      if (_fStroke.pts.length > 1) sendFriendDraw('add', _fStroke);
      _fStroke = null;
    }
    canvas.onmousedown  = startDraw; canvas.onmousemove  = doDraw; canvas.onmouseup   = endDraw;
    canvas.ontouchstart = startDraw; canvas.ontouchmove  = doDraw; canvas.ontouchend  = endDraw;
  }
  document.getElementById('friendDrawOverlay')?.addEventListener('transitionend', _setup);
})();

function selectFriendActions(idx, name) {
  _selectedFriendIdx = idx;
  _selectedFriendName = name;
  document.getElementById('freundeOverlayTitle').textContent = '👥 ' + name;
  closeOverlay('friendsOverlay');
  document.getElementById('freundeOverlay').classList.add('show');
}

function showFreundNotify(idx) {
  _selectedFriendIdx = (idx !== undefined) ? idx : _selectedFriendIdx;
  document.getElementById('freundNotifyOverlay').classList.add('show');
}
async function sendFreundNotification() {
  const title = document.getElementById('freundNotifyTitle').value.trim() || 'BMO';
  const msg   = document.getElementById('freundNotifyMsg').value.trim();
  if (!msg) return;
  try {
    const r = await fetch(`/api/friend/${_selectedFriendIdx}/notify`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({title, message: msg})
    });
    const d = await r.json();
    addMsg(d.ok ? '🔔 Notification an Freund gesendet!' : '⛔ ' + (d.error||'Fehler'), 'sys');
  } catch(e) { addMsg('Freund nicht erreichbar 😢', 'sys'); }
  closeOverlay('freundNotifyOverlay');
}
async function showFreundProcesses(idx) {
  _selectedFriendIdx = (idx !== undefined) ? idx : _selectedFriendIdx;
  document.getElementById('freundProcessesOverlay').classList.add('show');
  await loadFreundProcesses();
}
async function loadFreundProcesses() {
  document.getElementById('freundProcList').innerHTML = '<div class="notes-empty">Lade...</div>';
  try {
    const r = await fetch(`/api/friend/${_selectedFriendIdx}/processes`);
    const d = await r.json();
    if (d.error) { document.getElementById('freundProcList').innerHTML = `<div class="notes-empty">⛔ ${escHtml(d.error)}</div>`; return; }
    const procs = d.processes || [];
    if (!procs.length) { document.getElementById('freundProcList').innerHTML = '<div class="notes-empty">Keine Prozesse.</div>'; return; }
    document.getElementById('freundProcList').innerHTML = procs.map(p => `
      <div class="proc-item" id="fprc-${p.pid}">
        <div class="proc-name" title="${escHtml(p.name)}">${escHtml(p.name)}</div>
        <div class="proc-stats">CPU ${p.cpu}% · RAM ${p.mem}%</div>
        <button class="proc-kill" onclick="killFreundProcess(${p.pid},this)">Kill</button>
      </div>
    `).join('');
  } catch(e) { document.getElementById('freundProcList').innerHTML = '<div class="notes-empty">Freund nicht erreichbar 😢</div>'; }
}
async function killFreundProcess(pid, btn) {
  btn.disabled = true; btn.textContent = '...';
  try {
    const r = await fetch(`/api/friend/${_selectedFriendIdx}/processes/${pid}/kill`, {method:'POST'});
    const d = await r.json();
    if (d.ok) { document.getElementById('fprc-' + pid)?.remove(); }
    else { btn.textContent = '⛔'; setTimeout(() => { btn.textContent = 'Kill'; btn.disabled = false; }, 2000); }
  } catch(e) { btn.textContent = 'Kill'; btn.disabled = false; }
}

// ── SPIELE OVERLAY ───────────────────────────────────────────────
function showSpiele() {
  document.getElementById('spieleOverlay').classList.add('show');
}

// ── SPOTIFY ─────────────────────────────────────────────────────
async function updateNowPlaying() {
  try {
    const r = await fetch('/api/spotify/current');
    const d = await r.json();
    const cover  = document.getElementById('npCover');
    const icon   = document.getElementById('npIcon');
    if (d.track) {
      document.getElementById('npTrack').textContent  = d.track;
      document.getElementById('npArtist').textContent = d.artist;
      icon.textContent = d.playing ? '▶️' : '⏸️';
      if (d.cover) {
        cover.src          = d.cover;
        cover.style.display = 'block';
        icon.style.display  = 'none';
      } else {
        cover.style.display = 'none';
        icon.style.display  = 'block';
        icon.textContent    = d.playing ? '▶️' : '⏸️';
      }
    } else {
      document.getElementById('npTrack').textContent  = 'Nichts läuft gerade';
      document.getElementById('npArtist').textContent = '';
      cover.style.display = 'none';
      icon.style.display  = 'block';
      icon.textContent    = '🎵';
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

// ── UTILS ────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                  .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function throttle(fn, delay) {
  let last = 0;
  return function(...args) {
    const now = Date.now();
    if (now - last >= delay) { last = now; fn(...args); }
  };
}

// ── WINDOWS NOTIFICATION ─────────────────────────────────────────
function showNotify() {
  document.getElementById('notifyTitle').value = 'BMO';
  document.getElementById('notifyMsg').value = '';
  document.getElementById('notifyOverlay').classList.add('show');
  setTimeout(() => document.getElementById('notifyMsg').focus(), 300);
}
async function sendNotification() {
  const title   = document.getElementById('notifyTitle').value.trim() || 'BMO';
  const message = document.getElementById('notifyMsg').value.trim();
  if (!message) return;
  try {
    const r = await fetch('/api/notify', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({title, message})
    });
    const d = await r.json();
    closeOverlay('notifyOverlay');
    addMsg(d.ok ? '🔔 Notification gesendet!' : '⛔ ' + (d.error || 'Fehler'), 'sys');
  } catch(e) { addMsg('Fehler 😢', 'sys'); }
}
async function friendNotify() {
  const title   = prompt('Titel:', 'Hey!');
  if (title === null) return;
  const message = prompt('Nachricht:', '');
  if (!message) return;
  try {
    const r = await fetch('/api/friend/notify', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({title, message})
    });
    const d = await r.json();
    addMsg(d.ok ? '🔔 Notification an Freund gesendet!' : '⛔ ' + (d.error || 'Kein Zugriff'), 'sys');
  } catch(e) { addMsg('Freund nicht erreichbar 😢', 'sys'); }
}

// ── PROZESS MANAGER ──────────────────────────────────────────────
async function showProcesses() {
  document.getElementById('processesOverlay').classList.add('show');
  await loadProcesses();
}
async function loadProcesses() {
  document.getElementById('procList').innerHTML = '<div class="notes-empty">Lade...</div>';
  try {
    const r = await fetch('/api/processes');
    const d = await r.json();
    renderProcesses(d.processes || []);
  } catch(e) {
    document.getElementById('procList').innerHTML = '<div class="notes-empty">Fehler beim Laden.</div>';
  }
}
function renderProcesses(procs) {
  if (!procs.length) {
    document.getElementById('procList').innerHTML = '<div class="notes-empty">Keine Prozesse.</div>';
    return;
  }
  document.getElementById('procList').innerHTML = procs.map(p => `
    <div class="proc-item" id="proc-${p.pid}">
      <div class="proc-name" title="${escHtml(p.name)}">${escHtml(p.name)}</div>
      <div class="proc-stats">CPU ${p.cpu}% · RAM ${p.mem}%</div>
      <button class="proc-kill" onclick="killProcess(${p.pid},this)">Kill</button>
    </div>
  `).join('');
}
async function killProcess(pid, btn) {
  btn.disabled = true; btn.textContent = '...';
  try {
    const r = await fetch('/api/processes/' + pid + '/kill', {method:'POST'});
    const d = await r.json();
    if (d.ok) {
      document.getElementById('proc-' + pid)?.remove();
    } else {
      btn.textContent = '⛔';
      setTimeout(() => { btn.textContent = 'Kill'; btn.disabled = false; }, 2000);
    }
  } catch(e) { btn.textContent = 'Kill'; btn.disabled = false; }
}

// ── REMOTE CONTROL ───────────────────────────────────────────────
let _remoteOn = false;

async function toggleRemote() {
  try {
    const r = await fetch('/api/remote/toggle', {method:'POST'});
    const d = await r.json();
    _remoteOn = d.enabled;
    const btn = document.getElementById('remoteBtn');
    if (_remoteOn) {
      btn.style.color = '#4ade80'; btn.style.borderColor = '#4ade80';
      enableRemoteCapture();
    } else {
      btn.style.color = '#94a3b8'; btn.style.borderColor = '#334155';
      disableRemoteCapture();
    }
  } catch(e) {}
}

function enableRemoteCapture() {
  let ov = document.getElementById('remoteOverlay');
  if (!ov) {
    ov = document.createElement('div');
    ov.id = 'remoteOverlay';
    ov.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;cursor:crosshair;z-index:15;';
    document.getElementById('screenImg').parentElement.appendChild(ov);
  }
  ov.style.display = 'block';
  const sendMove = throttle(e => _sendRemote('move', e, ov), 40);
  ov.onmousemove  = sendMove;
  ov.onclick      = e => _sendRemote('click', e, ov);
  ov.ondblclick   = e => _sendRemote('dblclick', e, ov);
  ov.onwheel      = e => {
    e.preventDefault();
    const rect = ov.getBoundingClientRect();
    _sendRemoteRaw('scroll', {
      rx: (e.clientX - rect.left) / rect.width,
      ry: (e.clientY - rect.top)  / rect.height,
      delta: e.deltaY > 0 ? -3 : 3
    });
  };
  ov.ontouchmove  = e => { e.preventDefault(); _sendRemote('move',  e.touches[0], ov); };
  ov.ontouchstart = e => { e.preventDefault(); _sendRemote('click', e.touches[0], ov); };
}
function disableRemoteCapture() {
  const ov = document.getElementById('remoteOverlay');
  if (ov) ov.style.display = 'none';
}
function _sendRemote(type, e, container) {
  const rect = container.getBoundingClientRect();
  _sendRemoteRaw(type, {
    rx: (e.clientX - rect.left) / rect.width,
    ry: (e.clientY - rect.top)  / rect.height
  });
}
async function _sendRemoteRaw(type, data) {
  if (!_remoteOn) return;
  try {
    await fetch('/api/remote/input', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({type, ...data})
    });
  } catch(e) {}
}

// ── DRAW OVERLAY ─────────────────────────────────────────────────
let _drawMode = false, _drawing = false, _curStroke = null;
let _currentMonitorIdx = 1;

function toggleDraw() {
  _drawMode = !_drawMode;
  const canvas  = document.getElementById('drawCanvas');
  const toolbar = document.getElementById('drawToolbar');
  const btn     = document.getElementById('drawScreenBtn');
  if (_drawMode) {
    const img = document.getElementById('screenImg');
    canvas.width  = img.offsetWidth;
    canvas.height = img.offsetHeight;
    canvas.style.display = 'block';
    toolbar.style.display = 'flex';
    btn.style.color = '#f472b6'; btn.style.borderColor = '#f472b6';
    _setupDrawCanvas(canvas);
  } else {
    canvas.style.display = 'none';
    toolbar.style.display = 'none';
    btn.style.color = '#94a3b8'; btn.style.borderColor = '#334155';
    fetch('/api/draw', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({action:'close'})
    }).catch(()=>{});
  }
}
function _setupDrawCanvas(canvas) {
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  function getPos(e) {
    const rect = canvas.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return {
      x: (t.clientX - rect.left) / rect.width,
      y: (t.clientY - rect.top)  / rect.height
    };
  }
  function startDraw(e) {
    e.preventDefault(); _drawing = true;
    const p = getPos(e);
    const color = document.getElementById('drawColor').value;
    const width = parseInt(document.getElementById('drawWidth').value);
    _curStroke = {pts: [[p.x, p.y]], color, width};
    ctx.beginPath();
    ctx.moveTo(p.x * canvas.width, p.y * canvas.height);
    ctx.strokeStyle = color; ctx.lineWidth = width;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  }
  function doDraw(e) {
    e.preventDefault();
    if (!_drawing || !_curStroke) return;
    const p = getPos(e);
    _curStroke.pts.push([p.x, p.y]);
    ctx.lineTo(p.x * canvas.width, p.y * canvas.height);
    ctx.stroke();
  }
  function endDraw() {
    if (!_drawing || !_curStroke) return;
    _drawing = false;
    if (_curStroke.pts.length > 1) {
      fetch('/api/draw', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({action:'add', ..._curStroke, monitor: _currentMonitorIdx})
      }).catch(()=>{});
    }
    _curStroke = null;
  }
  canvas.onmousedown  = startDraw; canvas.onmousemove  = doDraw; canvas.onmouseup   = endDraw;
  canvas.ontouchstart = startDraw; canvas.ontouchmove  = doDraw; canvas.ontouchend  = endDraw;
}
async function clearDraw() {
  const canvas = document.getElementById('drawCanvas');
  canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
  await fetch('/api/draw', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action:'clear'})
  }).catch(()=>{});
}

async function challengeFriendPong(idx) {
  _selectedFriendIdx = (idx !== undefined) ? idx : _selectedFriendIdx;
  try {
    const r = await fetch(`/api/friend/${_selectedFriendIdx}/pong/challenge`, {method:'POST'});
    const d = await r.json();
    if (d.ok) {
      showPong(false, true);  // Admin = linkes Paddle, right_human=true für Freund
    } else {
      addMsg('⛔ ' + (d.error || 'Pong-Herausforderung fehlgeschlagen.'), 'sys');
    }
  } catch(e) {
    addMsg('Freund nicht erreichbar 😢', 'sys');
  }
}

// ── PONG GAME ────────────────────────────────────────────────────
let _pongActive = false, _pongRAF = null, _pongPoll = null;
let _myPaddleY = 0.5;
let _pongFriendMode = false;  // true = wir sind rechts (Freund-Herausforderung)
let _pongDisconnectHandled = false;

async function showPong(friendJoin = false, rightHuman = false) {
  _pongFriendMode = friendJoin;
  _pongDisconnectHandled = false;
  document.getElementById('pongOverlay').classList.add('show');
  // Prüfen ob Freund uns bereits eingeladen hat
  if (!friendJoin && !rightHuman) {
    try {
      const r = await fetch('/api/pong/pending');
      const d = await r.json();
      if (d.pending) {
        document.getElementById('pongBadge').style.display = 'none';
        document.getElementById('pongChallengeBanner').style.display = 'block';
        return;
      }
    } catch(e) {}
  }
  if (!friendJoin) {
    await fetch('/api/pong/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({right_human: rightHuman})}).catch(()=>{});
  }
  _pongActive = true;
  document.getElementById('pongInfo').textContent =
    friendJoin ? '🟠 Du = rechtes Paddle (Maus/Touch)' : '🟢 Du = linkes Paddle (Maus/Touch)';
  _startPongInput();
  _startPongRender();
}
function closePong() {
  _pongActive = false;
  if (_pongRAF)  cancelAnimationFrame(_pongRAF);
  if (_pongPoll) clearInterval(_pongPoll);
  document.getElementById('pongOverlay').classList.remove('show');
}
async function acceptPongChallenge() {
  document.getElementById('pongChallengeBanner').style.display = 'none';
  document.getElementById('pongBadge').style.display = 'none';
  await fetch('/api/pong/accept', {method:'POST'}).catch(()=>{});
  _pongFriendMode = false;
  _pongDisconnectHandled = false;
  _pongActive = true;
  document.getElementById('pongOverlay').classList.add('show');
  document.getElementById('pongInfo').textContent = '🟢 Du = linkes Paddle (Maus/Touch)';
  _startPongInput();
  _startPongRender();
}

// Polling: prüfen ob Freund uns herausfordert — Badge zeigen, Overlay NICHT automatisch öffnen
setInterval(async () => {
  try {
    const r = await fetch('/api/pong/pending/peek');
    const d = await r.json();
    const badge = document.getElementById('pongBadge');
    badge.style.display = d.pending ? 'flex' : 'none';
  } catch(e) {}
}, 1000);

async function pongReset() {
  closePong();
  await new Promise(r => setTimeout(r, 200));
  showPong();
}
function _startPongInput() {
  const canvas = document.getElementById('pongCanvas');
  function updateY(e) {
    const rect = canvas.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    _myPaddleY = Math.max(0.08, Math.min(0.92, (t.clientY - rect.top) / rect.height));
  }
  canvas.onmousemove  = updateY;
  canvas.ontouchmove  = e => { e.preventDefault(); updateY(e); };
  canvas.ontouchstart = e => { e.preventDefault(); updateY(e); };
  const side = _pongFriendMode ? 'right' : 'left';
  const url  = _pongFriendMode ? `/api/friend/${_selectedFriendIdx}/pong/paddle` : '/api/pong/paddle';
  _pongPoll = setInterval(async () => {
    if (!_pongActive) return;
    fetch(url, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({side, y: _myPaddleY})
    }).catch(()=>{});
  }, 40);
}
function _startPongRender() {
  const canvas = document.getElementById('pongCanvas');
  const ctx    = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  let state = null, frame = 0;
  const stateUrl = _pongFriendMode ? `/api/friend/${_selectedFriendIdx}/pong/state` : '/api/pong/state';

  async function fetchState() {
    try { state = await (await fetch(stateUrl)).json(); } catch(e) {}
  }
  function loop() {
    if (!_pongActive) return;
    if (frame++ % 2 === 0) fetchState();
    // Disconnect-Erkennung
    if (state && state.opponent_left && !_pongDisconnectHandled) {
      _pongDisconnectHandled = true;
      const who = state.opponent_left === 'right' ? 'Freund' : 'Gegner';
      document.getElementById('pongInfo').textContent = `⚠️ ${who} hat das Spiel verlassen.`;
      _pongActive = false;
      if (_pongPoll) { clearInterval(_pongPoll); _pongPoll = null; }
      setTimeout(() => document.getElementById('pongOverlay').classList.remove('show'), 3000);
      return;
    }
    ctx.fillStyle = '#0a0a1a'; ctx.fillRect(0, 0, W, H);
    ctx.setLineDash([8, 12]); ctx.strokeStyle = '#1e293b'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(W/2, 0); ctx.lineTo(W/2, H); ctx.stroke();
    ctx.setLineDash([]);
    if (state) {
      document.getElementById('pongScoreL').textContent = state.score_l ?? 0;
      document.getElementById('pongScoreR').textContent = state.score_r ?? 0;
      const ph = H * 0.15, pw = 12;
      // Left paddle (always us unless friend mode)
      ctx.fillStyle = !_pongFriendMode ? '#2b8773' : '#1e4d43';
      _roundRect(ctx, 8, state.left * H - ph/2, pw, ph, 4);
      if (!_pongFriendMode) { ctx.strokeStyle='#4ade80'; ctx.lineWidth=2; _roundRect(ctx, 8, state.left*H-ph/2, pw, ph, 4, true); }
      // Right paddle (AI or friend-mode us)
      const rightActive = _pongFriendMode || (state.right_human);
      ctx.fillStyle = rightActive ? '#f97316' : '#5a2d0c';
      _roundRect(ctx, W-8-pw, state.right * H - ph/2, pw, ph, 4);
      if (_pongFriendMode) { ctx.strokeStyle='#4ade80'; ctx.lineWidth=2; _roundRect(ctx, W-8-pw, state.right*H-ph/2, pw, ph, 4, true); }
      // AI label on right
      if (!_pongFriendMode && !state.right_human) {
        ctx.fillStyle = '#475569'; ctx.font = '11px monospace';
        ctx.fillText('🤖', W - 28, 18);
      }
      // Ball glow (nur wenn Spiel läuft)
      if (!state.right_human || state.friend_ready) {
        const bx = state.ball.x * W, by = state.ball.y * H;
        const grd = ctx.createRadialGradient(bx, by, 0, bx, by, 14);
        grd.addColorStop(0, 'rgba(255,255,255,.9)');
        grd.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = grd; ctx.beginPath(); ctx.arc(bx, by, 14, 0, Math.PI*2); ctx.fill();
        ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(bx, by, 6, 0, Math.PI*2); ctx.fill();
      }
      // Warte auf Freund
      if (state.right_human && !state.friend_ready) {
        ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = '#94a3b8'; ctx.font = 'bold 22px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('Warte auf Freund...', W/2, H/2);
        ctx.textAlign = 'left';
      }
      // Countdown
      if (state.countdown > 0) {
        ctx.fillStyle = 'rgba(0,0,0,0.45)'; ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = '#4ade80'; ctx.font = 'bold 96px monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(state.countdown, W/2, H/2);
        ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
      }
    }
    _pongRAF = requestAnimationFrame(loop);
  }
  fetchState(); loop();
}
function _roundRect(ctx, x, y, w, h, r, stroke=false) {
  ctx.beginPath();
  if (ctx.roundRect) { ctx.roundRect(x, y, w, h, r); }
  else { ctx.rect(x, y, w, h); }
  stroke ? ctx.stroke() : ctx.fill();
}

// ── LITE-MODE ──────────────────────────────────────────────────────
async function loadLiteMode() {
  try {
    const r = await fetch('/api/lite-mode');
    if (!r.ok) return;
    const d = await r.json();
    updateLiteBtn(d.lite_mode);
  } catch(e) {}
}

function updateLiteBtn(on) {
  const btn = document.getElementById('liteModeBtn');
  if (!btn) return;
  btn.style.borderColor = on ? '#22c55e' : '#475569';
  btn.style.color       = on ? '#4ade80' : '#94a3b8';
  btn.style.background  = on ? 'rgba(34,197,94,0.08)' : '';
}

async function toggleLiteMode() {
  try {
    const r = await fetch('/api/lite-mode');
    if (!r.ok) { alert('Core nicht erreichbar.'); return; }
    const cur = (await r.json()).lite_mode;
    const r2 = await fetch('/api/lite-mode/set', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enable: !cur})
    });
    const d = await r2.json();
    updateLiteBtn(d.lite_mode);
    alert('Lite-Mode ' + (d.lite_mode ? 'aktiviert' : 'deaktiviert') + '. BMO Core neu starten damit Änderung greift.');
  } catch(e) { alert('Fehler: Core erreichbar?'); }
}

loadLiteMode();

// ── FRESH START ON LOAD ──────────────────────────────────────────
fetch('/api/history/clear', {method: 'POST'}).catch(() => {});
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
        r = req.get(f"{CORE_URL}/status", timeout=(3, 5))
        return jsonify(r.json())
    except:
        cpu  = psutil.cpu_percent()
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

@app.route('/api/timers', methods=['GET'])
@login_required
def timers_proxy():
    try:
        r = req.get(f"{CORE_URL}/timers", timeout=3)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(timers=[])

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

# ── COMMANDS ──────────────────────────────────────────────────────
COMMANDS = [
    {"category": "Zeit & Info", "icon": "ℹ️", "items": [
        {"label": "Uhrzeit",        "msg": "Wie spät ist es?"},
        {"label": "System Status",  "msg": "System Status"},
        {"label": "Wetter",         "msg": "Wie ist das Wetter?"},
        {"label": "News",           "msg": "Was gibt es Neues?"},
        {"label": "Witz",           "msg": "Erzähl mir einen Witz"},
    ]},
    {"category": "Musik", "icon": "🎵", "items": [
        {"label": "Playlist",       "msg": "Spiel meine Playlist"},
        {"label": "Pause",          "msg": "Pause"},
        {"label": "Weiter",         "msg": "weiter"},
        {"label": "Skip",           "msg": "nächstes Lied"},
        {"label": "Lauter",         "msg": "lauter"},
        {"label": "Leiser",         "msg": "leiser"},
        {"label": "Lautstärke 50%", "msg": "Lautstärke 50"},
        {"label": "Lautstärke 80%", "msg": "Lautstärke 80"},
    ]},
    {"category": "Apps öffnen", "icon": "🖥️", "items": [
        {"label": "Chrome",         "msg": "Öffne Chrome"},
        {"label": "Spotify",        "msg": "Öffne Spotify"},
        {"label": "Discord",        "msg": "Öffne Discord"},
        {"label": "VS Code",        "msg": "Öffne VS Code"},
        {"label": "Explorer",       "msg": "Öffne Explorer"},
        {"label": "Notepad",        "msg": "Öffne Notepad"},
        {"label": "Rechner",        "msg": "Öffne Rechner"},
        {"label": "Terminal",       "msg": "Öffne Terminal"},
        {"label": "Task-Manager",   "msg": "Öffne Task Manager"},
    ]},
    {"category": "System", "icon": "⚙️", "items": [
        {"label": "Screenshot",     "msg": "Mach einen Screenshot"},
        {"label": "Timer 5min",     "msg": "Timer 5 Minuten"},
        {"label": "Timer 10min",    "msg": "Timer 10 Minuten"},
        {"label": "Timer 25min",    "msg": "Timer 25 Minuten"},
        {"label": "Timer 1h",       "msg": "Timer 60 Minuten"},
        {"label": "PC ausschalten", "msg": "schalte den PC aus"},
    ]},
]

@app.route('/api/commands')
@login_required
def commands_list():
    return jsonify(commands=COMMANDS)

# ── SCREEN STREAMING ──────────────────────────────────────────────
_latest_frame: bytes | None = None
_frame_lock     = threading.Lock()
_capture_active = False
_screen_viewers = 0
_viewers_lock   = threading.Lock()
_selected_monitor = 1  # 1 = erster echter Monitor (mss: 0 = alle zusammen)
_monitor_lock   = threading.Lock()

def _capture_daemon():
    """Hintergrund-Thread: läuft nur solange jemand den Screen anschaut."""
    global _latest_frame, _capture_active
    target_interval = 1.0 / 25  # ~25 FPS
    sct = _mss_lib.mss() if _SCREEN_BACKEND == 'mss' else None
    while True:
        with _viewers_lock:
            if _screen_viewers == 0:
                _capture_active = False
                break
        t0 = _time.monotonic()
        try:
            if _SCREEN_BACKEND == 'mss':
                with _monitor_lock:
                    mon_idx = _selected_monitor
                monitors = sct.monitors
                mon = monitors[mon_idx] if mon_idx < len(monitors) else monitors[1]
                raw = sct.grab(mon)
                img = _PilImage.frombytes('RGB', raw.size, raw.bgra, 'raw', 'BGRX')
            else:
                img = ImageGrab.grab()
            w, h = img.size
            nw = min(w, 1920)
            nh = int(h * nw / w)
            if (nw, nh) != (w, h):
                img = img.resize((nw, nh))
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=72, optimize=False)
            with _frame_lock:
                _latest_frame = buf.getvalue()
        except Exception:
            pass
        elapsed = _time.monotonic() - t0
        wait = target_interval - elapsed
        if wait > 0:
            _time.sleep(wait)
    if sct:
        sct.close()

def _ensure_capture_running():
    global _capture_active
    with _viewers_lock:
        if not _capture_active and _SCREEN_OK:
            _capture_active = True
            threading.Thread(target=_capture_daemon, daemon=True).start()

def _screen_generator():
    """MJPEG-Generator: startet Capture beim ersten Zuschauer, stoppt wenn keiner mehr schaut."""
    global _screen_viewers
    with _viewers_lock:
        _screen_viewers += 1
    _ensure_capture_running()
    try:
        while True:
            with _frame_lock:
                frame = _latest_frame
            if frame:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            _time.sleep(0.04)
    finally:
        with _viewers_lock:
            _screen_viewers = max(0, _screen_viewers - 1)

@app.route('/api/screen/monitors')
@login_required
def screen_monitors():
    """Gibt alle verfügbaren Monitore zurück."""
    if not _SCREEN_OK or _SCREEN_BACKEND != 'mss':
        return jsonify(monitors=[{'idx': 1, 'label': 'Monitor 1'}])
    try:
        with _mss_lib.mss() as sct:
            result = []
            for i, m in enumerate(sct.monitors):
                if i == 0:
                    continue  # Index 0 = alle zusammen, überspringen
                result.append({'idx': i, 'label': f'Monitor {i}  ({m["width"]}×{m["height"]})'})
        with _monitor_lock:
            active = _selected_monitor
        return jsonify(monitors=result, active=active)
    except Exception as e:
        return jsonify(monitors=[{'idx': 1, 'label': 'Monitor 1'}], active=1)

@app.route('/api/screen/monitor', methods=['POST'])
@login_required
def screen_set_monitor():
    """Setzt den aktiven Monitor für den Stream."""
    global _selected_monitor
    idx = request.get_json(force=True).get('idx', 1)
    with _monitor_lock:
        _selected_monitor = int(idx)
    return jsonify(ok=True, active=_selected_monitor)

@app.route('/api/screen')
@login_required
def screen_stream():
    if not _SCREEN_OK:
        return jsonify(error="Pillow (PIL) nicht installiert. Bitte: pip install Pillow"), 503
    return Response(_screen_generator(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ── FREUND PROXY ROUTEN ────────────────────────────────────────────

@app.route('/api/friend/<int:idx>/info')
@login_required
def friend_info(idx):
    """Prüft ob Freund online ist und ob Admin-Zugriff aktiv."""
    if idx >= len(FRIENDS):
        return jsonify(online=False, admin_access=False), 404
    url = FRIENDS[idx]['url']
    try:
        r = req.get(f"{url}/api/admin/info", timeout=3)
        return jsonify(r.json())
    except Exception:
        return jsonify(online=False, admin_access=False)

@app.route('/api/friend/<int:idx>/jumpscare', methods=['POST'])
@login_required
def friend_jumpscare(idx):
    """Sendet Jumpscare an Freund idx."""
    if idx >= len(FRIENDS):
        return jsonify(ok=False, error="Unbekannter Freund."), 404
    url = FRIENDS[idx]['url']
    try:
        r = req.post(f"{url}/api/admin/jumpscare", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/<int:idx>/screen')
@login_required
def friend_screen(idx):
    """Streamt den Bildschirm von Freund idx."""
    if idx >= len(FRIENDS):
        return jsonify(error="Unbekannter Freund."), 404
    url = FRIENDS[idx]['url']
    try:
        r = req.get(f"{url}/api/admin/screen", stream=True, timeout=10)
        if r.status_code == 403:
            return jsonify(error="Freund hat Zugriff nicht erlaubt."), 403
        return Response(
            r.iter_content(chunk_size=4096),
            content_type=r.headers.get('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        )
    except Exception as e:
        return jsonify(error=str(e)), 503

@app.route('/api/friend/<int:idx>/screen/monitors')
@login_required
def friend_screen_monitors(idx):
    if idx >= len(FRIENDS):
        return jsonify(monitors=[], active=1), 404
    url = FRIENDS[idx]['url']
    try:
        r = req.get(f"{url}/api/admin/screen/monitors", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(monitors=[{'idx': 1, 'label': 'Monitor 1'}], active=1)

@app.route('/api/friend/<int:idx>/screen/monitor', methods=['POST'])
@login_required
def friend_screen_set_monitor(idx):
    if idx >= len(FRIENDS):
        return jsonify(ok=False), 404
    url = FRIENDS[idx]['url']
    try:
        data = request.get_json(force=True)
        r = req.post(f"{url}/api/admin/screen/monitor", json=data, timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ── WINDOWS NOTIFICATION ──────────────────────────────────────────
@app.route('/api/notify', methods=['POST'])
@login_required
def send_notification():
    data = request.json or {}
    title   = str(data.get('title', 'BMO'))[:64]
    message = str(data.get('message', ''))[:256]
    if not message:
        return jsonify(ok=False, error="Keine Nachricht.")
    try:
        try:
            from winotify import Notification
            toast = Notification(app_id="BMO", title=title, msg=message)
            toast.show()
        except ImportError:
            # Fallback: PowerShell BalloonTip via systray
            t = title.replace('"', '').replace("'", "")
            m = message.replace('"', '').replace("'", "")
            ps = (
                'Add-Type -AssemblyName System.Windows.Forms;'
                '$n=New-Object System.Windows.Forms.NotifyIcon;'
                '$n.Icon=[System.Drawing.SystemIcons]::Information;'
                '$n.Visible=$true;'
                f'$n.ShowBalloonTip(4000,\'{t}\',\'{m}\',[System.Windows.Forms.ToolTipIcon]::Info);'
                'Start-Sleep 5; $n.Dispose()'
            )
            subprocess.Popen(['powershell', '-WindowStyle', 'Hidden', '-Command', ps])
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/<int:idx>/notify', methods=['POST'])
@login_required
def friend_notify_idx(idx):
    if idx >= len(FRIENDS):
        return jsonify(ok=False, error="Unbekannter Freund.")
    url = FRIENDS[idx]['url']
    try:
        r = req.post(f"{url}/api/admin/notify", json=request.json or {}, timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/notify', methods=['POST'])
@login_required
def friend_notify():
    if "HIER_FREUND_IP" in FRIEND_URL:
        return jsonify(ok=False, error="FRIEND_URL nicht konfiguriert.")
    try:
        r = req.post(f"{FRIEND_URL}/api/admin/notify", json=request.json or {}, timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

# ── PROZESS MANAGER ───────────────────────────────────────────────
@app.route('/api/processes', methods=['GET'])
@login_required
def list_processes():
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
        try:
            info = p.info
            procs.append({
                'pid':  info['pid'],
                'name': info['name'] or '?',
                'cpu':  round(info['cpu_percent'] or 0, 1),
                'mem':  round(info['memory_percent'] or 0, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x['mem'], reverse=True)
    return jsonify(processes=procs[:80])

@app.route('/api/processes/<int:pid>/kill', methods=['POST'])
@login_required
def kill_process(pid):
    try:
        p = psutil.Process(pid)
        name = p.name()
        p.terminate()
        return jsonify(ok=True, name=name)
    except psutil.NoSuchProcess:
        return jsonify(ok=False, error="Prozess nicht gefunden.")
    except psutil.AccessDenied:
        return jsonify(ok=False, error="Zugriff verweigert.")
    except Exception as e:
        return jsonify(ok=False, error=str(e))

# ── REMOTE CONTROL ────────────────────────────────────────────────
_remote_enabled = False

@app.route('/api/remote/toggle', methods=['POST'])
@login_required
def remote_toggle():
    global _remote_enabled
    _remote_enabled = not _remote_enabled
    return jsonify(enabled=_remote_enabled)

@app.route('/api/remote/input', methods=['POST'])
@login_required
def remote_input():
    if not _remote_enabled:
        return jsonify(ok=False, error="Remote control deaktiviert.")
    if not _PYAUTOGUI_OK:
        return jsonify(ok=False, error="pyautogui nicht installiert: pip install pyautogui")
    data = request.json or {}
    evt  = data.get('type')
    try:
        sw, sh = _pag.size()
        rx = float(data.get('rx', 0))
        ry = float(data.get('ry', 0))
        x, y = int(rx * sw), int(ry * sh)
        if evt == 'move':
            _pag.moveTo(x, y, duration=0)
        elif evt == 'click':
            _pag.click(x, y, button=data.get('button', 'left'))
        elif evt == 'dblclick':
            _pag.doubleClick(x, y)
        elif evt == 'scroll':
            _pag.scroll(int(data.get('delta', 3)), x=x, y=y)
        elif evt == 'key':
            k = data.get('key', '')
            if k:
                _pag.press(k)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

# ── DRAWING OVERLAY ───────────────────────────────────────────────
_draw_strokes = []
_draw_lock    = threading.Lock()
_draw_active  = False

def _draw_overlay_thread(monitor=None):
    global _draw_active
    try:
        import tkinter as tk
        _draw_active = True
        root = tk.Tk()
        root.overrideredirect(True)
        if monitor:
            sw = monitor['w']
            sh = monitor['h']
            mx = monitor['x']
            my = monitor['y']
        else:
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            mx, my = 0, 0
        root.geometry(f"{sw}x{sh}+{mx}+{my}")
        root.attributes('-topmost', True)
        root.configure(bg='black')
        root.attributes('-transparentcolor', 'black')
        cv = tk.Canvas(root, width=sw, height=sh, bg='black', highlightthickness=0)
        cv.pack()
        _items = []

        def _refresh():
            nonlocal _items
            for it in _items:
                cv.delete(it)
            _items = []
            if not _draw_active:
                root.destroy()
                return
            with _draw_lock:
                strokes = list(_draw_strokes)
            for stroke in strokes:
                pts = stroke.get('pts', [])
                col = stroke.get('color', '#ff3333')
                w   = stroke.get('width', 5)
                for i in range(len(pts) - 1):
                    x1, y1 = pts[i][0] * sw,   pts[i][1] * sh
                    x2, y2 = pts[i+1][0] * sw, pts[i+1][1] * sh
                    it = cv.create_line(x1, y1, x2, y2, fill=col, width=w,
                                        capstyle=tk.ROUND, joinstyle=tk.ROUND)
                    _items.append(it)
            root.after(80, _refresh)

        root.after(80, _refresh)
        root.mainloop()
    except Exception as e:
        log.warning(f"Draw overlay error: {e}")
    finally:
        _draw_active = False

@app.route('/api/draw', methods=['POST'])
@login_required
def draw_overlay():
    global _draw_strokes, _draw_active
    data   = request.json or {}
    action = data.get('action', 'add')
    if action == 'clear':
        with _draw_lock:
            _draw_strokes = []
        return jsonify(ok=True)
    elif action == 'close':
        _draw_active = False
        with _draw_lock:
            _draw_strokes = []
        return jsonify(ok=True)
    elif action == 'add':
        seg = {
            'pts':   data.get('pts', []),
            'color': data.get('color', '#ff3333'),
            'width': min(int(data.get('width', 5)), 24),
        }
        with _draw_lock:
            _draw_strokes.append(seg)
        if not _draw_active:
            mon_idx = data.get('monitor', 1)
            monitor = None
            try:
                import mss
                with mss.mss() as sct:
                    idx = int(mon_idx) if mon_idx else 1
                    m = sct.monitors[idx] if idx < len(sct.monitors) else sct.monitors[1]
                    monitor = {'x': m['left'], 'y': m['top'], 'w': m['width'], 'h': m['height']}
            except Exception:
                pass
            threading.Thread(target=_draw_overlay_thread, args=(monitor,), daemon=True).start()
        return jsonify(ok=True)
    return jsonify(ok=False, error="Unbekannte Aktion.")

@app.route('/api/draw/monitors', methods=['GET'])
@login_required
def draw_monitors():
    """Gibt verfügbare Monitore zurück für die Zeichenfunktion."""
    try:
        import mss
        with mss.mss() as sct:
            monitors = []
            for i, m in enumerate(sct.monitors[1:], 1):  # skip [0] which is "all"
                monitors.append({'idx': i, 'label': f'Monitor {i}', 'x': m['left'], 'y': m['top'], 'w': m['width'], 'h': m['height']})
        return jsonify(monitors=monitors, active=1)
    except Exception as e:
        return jsonify(monitors=[{'idx': 1, 'label': 'Monitor 1', 'x': 0, 'y': 0, 'w': 1920, 'h': 1080}], active=1)

# ── PONG GAME ─────────────────────────────────────────────────────
import random as _random
_pong_lock = threading.Lock()
_pong_pending = False
_pong_pending_lock = threading.Lock()
_pong = {
    'ball':        {'x': 0.5, 'y': 0.5, 'vx': 0.014, 'vy': 0.008},
    'left':        0.5, 'left_prev':  0.5,
    'right':       0.5, 'right_prev': 0.5,
    'score_l':     0,   'score_r':    0,
    'running':     False,
    'right_human': False,  # True wenn Freund rechts spielt
    'friend_ready':    False,   # True sobald Freund beigetreten ist
    'countdown_until': 0.0,    # time.time() + 3 wenn Countdown läuft
    'left_last_seen':  0.0,    # Letzter Paddle-Update vom Admin
    'right_last_seen': 0.0,    # Letzter Paddle-Update vom Freund
    'opponent_left':   '',     # 'left' oder 'right' wenn jemand getrennt wurde
}
_PONG_DISCONNECT_TIMEOUT = 8.0

def _reset_ball(b, direction):
    b['x'], b['y'] = 0.5, 0.5
    b['vx'] = direction * (0.013 + _random.uniform(0, 0.003))
    b['vy'] = (_random.random() - 0.5) * 0.018

def _pong_step():
    with _pong_lock:
        if not _pong['running']:
            return
        b = _pong['ball']

        # Paddle-Geschwindigkeit (für Spin)
        lv = _pong['left']  - _pong['left_prev']
        rv = _pong['right'] - _pong['right_prev']
        _pong['left_prev']  = _pong['left']
        _pong['right_prev'] = _pong['right']

        # KI für rechtes Paddle (wenn kein Freund)
        if not _pong['right_human']:
            t = b['y']; c = _pong['right']
            _pong['right'] = max(0.08, min(0.92, c + max(-0.024, min(0.024, t - c))))

        b['x'] += b['vx']
        b['y'] += b['vy']

        if b['y'] <= 0.02:
            b['y'] = 0.02; b['vy'] = abs(b['vy'])
        if b['y'] >= 0.98:
            b['y'] = 0.98; b['vy'] = -abs(b['vy'])

        ph = 0.15
        # Linkes Paddle
        if b['x'] <= 0.04:
            if abs(b['y'] - _pong['left']) < ph:
                b['x'] = 0.04
                b['vx'] = abs(b['vx']) * 1.06
                b['vy'] += (b['y'] - _pong['left']) * 0.06 + lv * 1.4
            elif b['x'] < 0:
                _pong['score_r'] += 1
                _reset_ball(b, 1)
        # Rechtes Paddle
        if b['x'] >= 0.96:
            if abs(b['y'] - _pong['right']) < ph:
                b['x'] = 0.96
                b['vx'] = -abs(b['vx']) * 1.06
                b['vy'] += (b['y'] - _pong['right']) * 0.06 + rv * 1.4
            elif b['x'] > 1.0:
                _pong['score_l'] += 1
                _reset_ball(b, -1)

        spd = (b['vx']**2 + b['vy']**2) ** 0.5
        mx  = 0.030
        if spd > mx:
            b['vx'] = b['vx'] / spd * mx
            b['vy'] = b['vy'] / spd * mx

def _pong_loop():
    while _pong['running']:
        with _pong_lock:
            rh = _pong['right_human']
            fr = _pong['friend_ready']
            cu = _pong['countdown_until']
            # Disconnect-Erkennung: nur im Multiplayer wenn Countdown vorbei
            if rh and fr and _time.time() > cu:
                now = _time.time()
                lls = _pong['left_last_seen']
                rls = _pong['right_last_seen']
                if lls > 0 and now - lls > _PONG_DISCONNECT_TIMEOUT:
                    _pong['opponent_left'] = 'left'
                    _pong['running'] = False
                elif rls > 0 and now - rls > _PONG_DISCONNECT_TIMEOUT:
                    _pong['opponent_left'] = 'right'
                    _pong['running'] = False
        if not _pong['running']:
            break
        if rh and not fr:
            # Warte auf Freund
            _time.sleep(0.1)
            continue
        if _time.time() < cu:
            # Countdown läuft — Ball einfrieren
            _time.sleep(0.016)
            continue
        _pong_step()
        try:
            socketio.emit('pong_state', _pong_state_dict())
        except Exception:
            pass
        _time.sleep(0.016)  # ~62 fps

def _pong_state_dict():
    import math as _math
    with _pong_lock:
        cu = _pong['countdown_until']
        cd = max(0, _math.ceil(cu - _time.time())) if cu > 0 else 0
        return dict(
            ball=dict(_pong['ball']),
            left=_pong['left'], right=_pong['right'],
            score_l=_pong['score_l'], score_r=_pong['score_r'],
            running=_pong['running'],
            right_human=_pong['right_human'],
            friend_ready=_pong['friend_ready'],
            countdown=cd,
            opponent_left=_pong['opponent_left'],
        )

@app.route('/api/pong/start', methods=['POST'])
@login_required
def pong_start():
    data = request.json or {}
    right_human = bool(data.get('right_human', False))
    with _pong_lock:
        _pong['score_l'] = 0; _pong['score_r'] = 0
        _pong['right_human'] = right_human
        _pong['friend_ready'] = not right_human  # bei AI sofort ready
        _pong['countdown_until'] = _time.time() + 3 if not right_human else 0.0
        _pong['opponent_left'] = ''
        _pong['left_last_seen'] = _time.time()
        _pong['right_last_seen'] = _time.time()
        b = _pong['ball']
        _reset_ball(b, 1 if _random.random() > 0.5 else -1)
        if not _pong['running']:
            _pong['running'] = True
            threading.Thread(target=_pong_loop, daemon=True).start()
    return jsonify(ok=True)

@app.route('/api/pong/state', methods=['GET'])
@login_required
def pong_state():
    return jsonify(**_pong_state_dict())

@app.route('/api/pong/paddle', methods=['POST'])
@login_required
def pong_paddle():
    data = request.json or {}
    side = data.get('side')
    y    = max(0.08, min(0.92, float(data.get('y', 0.5))))
    with _pong_lock:
        if side in ('left', 'right'):
            _pong[side] = y
        _pong['left_last_seen'] = _time.time()
    return jsonify(ok=True)

@app.route('/api/pong/reset', methods=['POST'])
@login_required
def pong_reset():
    with _pong_lock:
        _pong['score_l'] = 0; _pong['score_r'] = 0
        _pong['right_human'] = False
        _pong['running'] = False
        _pong['opponent_left'] = ''
        _pong['left_last_seen'] = 0.0
        _pong['right_last_seen'] = 0.0
        b = _pong['ball']
        b['x'], b['y'] = 0.5, 0.5
        b['vx'], b['vy'] = 0.014, 0.008
    return jsonify(ok=True)

@app.route('/api/pong/challenge', methods=['POST'])
@login_required
def pong_challenge():
    """Freund fordert uns heraus — Pong starten und pending setzen."""
    global _pong_pending
    with _pong_lock:
        _pong['right_human'] = True
        _pong['friend_ready'] = True   # Freund ist schon da
        _pong['countdown_until'] = _time.time() + 3
        _pong['score_l'] = 0; _pong['score_r'] = 0
        _pong['opponent_left'] = ''
        _pong['left_last_seen'] = _time.time()
        _pong['right_last_seen'] = _time.time()
        b = _pong['ball']
        _reset_ball(b, 1 if _random.random() > 0.5 else -1)
        if not _pong['running']:
            _pong['running'] = True
            threading.Thread(target=_pong_loop, daemon=True).start()
    with _pong_pending_lock:
        _pong_pending = True
    try:
        from winotify import Notification
        toast = Notification(app_id="BMO", title="🏓 Pong-Challenge!", msg="Dein Freund fordert dich heraus! BMO öffnen um anzunehmen.")
        toast.show()
    except Exception:
        pass
    return jsonify(ok=True)

@app.route('/api/pong/pending')
@login_required
def pong_pending():
    global _pong_pending
    with _pong_pending_lock:
        p = _pong_pending
        _pong_pending = False
    return jsonify(pending=p)

@app.route('/api/pong/pending/peek')
@login_required
def pong_pending_peek():
    """Gibt pending-Status zurück OHNE ihn zu konsumieren."""
    with _pong_pending_lock:
        p = _pong_pending
    return jsonify(pending=p)

@app.route('/api/pong/accept', methods=['POST'])
@login_required
def pong_accept():
    """Admin nimmt Pong-Challenge an — Countdown starten."""
    with _pong_lock:
        _pong['friend_ready'] = True
        _pong['countdown_until'] = _time.time() + 3
        _pong['opponent_left'] = ''
        _pong['left_last_seen'] = _time.time()
        _pong['right_last_seen'] = _time.time()
    return jsonify(ok=True)

@app.route('/api/friend/<int:idx>/pong/state')
@login_required
def friend_pong_state_idx(idx):
    if idx >= len(FRIENDS):
        return jsonify(running=False, error="Unbekannter Freund.")
    url = FRIENDS[idx]['url']
    try:
        r = req.get(f"{url}/api/admin/pong/state", timeout=3)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(running=False, error=str(e))

@app.route('/api/friend/pong/state')
@login_required
def friend_pong_state():
    if "HIER_FREUND_IP" in FRIEND_URL:
        return jsonify(running=False, error="FRIEND_URL nicht konfiguriert.")
    try:
        r = req.get(f"{FRIEND_URL}/api/admin/pong/state", timeout=3)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(running=False, error=str(e))

@app.route('/api/friend/<int:idx>/pong/paddle', methods=['POST'])
@login_required
def friend_pong_paddle_idx(idx):
    if idx >= len(FRIENDS):
        return jsonify(ok=False, error="Unbekannter Freund.")
    url = FRIENDS[idx]['url']
    try:
        r = req.post(f"{url}/api/admin/pong/paddle", json=request.json or {}, timeout=2)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/pong/paddle', methods=['POST'])
@login_required
def friend_pong_paddle():
    if "HIER_FREUND_IP" in FRIEND_URL:
        return jsonify(ok=False, error="FRIEND_URL nicht konfiguriert.")
    try:
        r = req.post(f"{FRIEND_URL}/api/admin/pong/paddle", json=request.json or {}, timeout=2)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/<int:idx>/pong/challenge', methods=['POST'])
@login_required
def friend_pong_challenge_idx(idx):
    if idx >= len(FRIENDS):
        return jsonify(ok=False, error="Unbekannter Freund.")
    url = FRIENDS[idx]['url']
    try:
        r = req.post(f"{url}/api/admin/pong/challenge", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/pong/challenge', methods=['POST'])
@login_required
def friend_pong_challenge():
    if "HIER_FREUND_IP" in FRIEND_URL:
        return jsonify(ok=False, error="FRIEND_URL nicht konfiguriert.")
    try:
        r = req.post(f"{FRIEND_URL}/api/admin/pong/challenge", timeout=5)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/<int:idx>/draw', methods=['POST'])
@login_required
def friend_draw_idx(idx):
    if idx >= len(FRIENDS):
        return jsonify(ok=False, error="Unbekannter Freund.")
    url = FRIENDS[idx]['url']
    try:
        r = req.post(f"{url}/api/admin/draw", json=request.json or {}, timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/<int:idx>/draw/monitors', methods=['GET'])
@login_required
def friend_draw_monitors_idx(idx):
    if idx >= len(FRIENDS):
        return jsonify(monitors=[])
    url = FRIENDS[idx]['url']
    try:
        r = req.get(f"{url}/api/admin/draw/monitors", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(monitors=[{'idx': 1, 'label': 'Monitor 1', 'x': 0, 'y': 0, 'w': 1920, 'h': 1080}])

@app.route('/api/friend/<int:idx>/processes')
@login_required
def friend_processes_idx(idx):
    if idx >= len(FRIENDS):
        return jsonify(error="Unbekannter Freund.")
    url = FRIENDS[idx]['url']
    try:
        r = req.get(f"{url}/api/admin/processes", timeout=5)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(error=str(e))

@app.route('/api/friend/processes')
@login_required
def friend_processes():
    if "HIER_FREUND_IP" in FRIEND_URL:
        return jsonify(error="FRIEND_URL nicht konfiguriert.")
    try:
        r = req.get(f"{FRIEND_URL}/api/admin/processes", timeout=5)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(error=str(e))

@app.route('/api/friend/<int:idx>/processes/<int:pid>/kill', methods=['POST'])
@login_required
def friend_kill_process_idx(idx, pid):
    if idx >= len(FRIENDS):
        return jsonify(ok=False, error="Unbekannter Freund.")
    url = FRIENDS[idx]['url']
    try:
        r = req.post(f"{url}/api/admin/processes/{pid}/kill", timeout=5)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/processes/<int:pid>/kill', methods=['POST'])
@login_required
def friend_kill_process(pid):
    if "HIER_FREUND_IP" in FRIEND_URL:
        return jsonify(ok=False, error="FRIEND_URL nicht konfiguriert.")
    try:
        r = req.post(f"{FRIEND_URL}/api/admin/processes/{pid}/kill", timeout=5)
        return jsonify(**r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

# ── ADMIN ROUTEN (kein Login nötig — für Freunde) ─────────────────
_admin_enabled = False

@app.route('/api/admin/toggle', methods=['POST'])
@login_required
def admin_toggle():
    global _admin_enabled
    _admin_enabled = not _admin_enabled
    log.info(f"Admin-Zugriff: {'AN' if _admin_enabled else 'AUS'}")
    return jsonify(enabled=_admin_enabled)

def _admin_check():
    if not _admin_enabled:
        from flask import abort
        abort(403)

@app.route('/api/admin/pong/state')
def admin_pong_state():
    return jsonify(**_pong_state_dict())

@app.route('/api/admin/pong/stream')
def admin_pong_stream():
    """SSE-Stream: pusht Pong-State ~60fps direkt zum Browser."""
    import json as _json
    def generate():
        while True:
            s = _pong_state_dict()
            yield f"data: {_json.dumps(s)}\n\n"
            _time.sleep(0.016)
    resp = Response(generate(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp

@app.route('/api/admin/pong/join', methods=['POST'])
def admin_pong_join():
    with _pong_lock:
        _pong['right_human'] = True
        _pong['friend_ready'] = True
        _pong['countdown_until'] = _time.time() + 3
        _pong['opponent_left'] = ''
        _pong['left_last_seen'] = _time.time()
        _pong['right_last_seen'] = _time.time()
    return jsonify(ok=True)

@app.route('/api/admin/pong/paddle', methods=['POST'])
def admin_pong_paddle():
    data = request.json or {}
    side = data.get('side')
    y    = max(0.08, min(0.92, float(data.get('y', 0.5))))
    with _pong_lock:
        if side in ('left', 'right'):
            _pong[side] = y
        _pong['right_last_seen'] = _time.time()
    return jsonify(ok=True)

@socketio.on('pong_paddle')
def ws_pong_paddle(data):
    """WebSocket-Handler: Paddle-Update vom Browser (niedrigere Latenz als HTTP POST)."""
    try:
        y    = max(0.08, min(0.92, float(data.get('y', 0.5))))
        side = data.get('side', 'right')
        with _pong_lock:
            if side in ('left', 'right'):
                _pong[side] = y
            if side == 'right':
                _pong['right_last_seen'] = _time.time()
            elif side == 'left':
                _pong['left_last_seen'] = _time.time()
    except Exception:
        pass

@app.route('/api/admin/pong/challenge', methods=['POST'])
def admin_pong_challenge():
    global _pong_pending
    with _pong_lock:
        _pong['right_human'] = True
        _pong['friend_ready'] = False  # Warte bis Admin annimmt
        _pong['countdown_until'] = 0.0
        _pong['score_l'] = 0; _pong['score_r'] = 0
        _pong['opponent_left'] = ''
        _pong['left_last_seen'] = _time.time()
        _pong['right_last_seen'] = _time.time()
        b = _pong['ball']
        _reset_ball(b, 1 if _random.random() > 0.5 else -1)
        if not _pong['running']:
            _pong['running'] = True
            threading.Thread(target=_pong_loop, daemon=True).start()
    with _pong_pending_lock:
        _pong_pending = True
    try:
        from winotify import Notification
        toast = Notification(app_id="BMO", title="🏓 Pong-Challenge!", msg="Dein Freund fordert dich heraus! BMO öffnen um anzunehmen.")
        toast.show()
    except Exception:
        pass
    return jsonify(ok=True)

@app.route('/api/admin/jumpscare', methods=['POST'])
def admin_jumpscare():
    _admin_check()
    try:
        import subprocess as _sp
        _sp.Popen(['python', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bmo_jumpscare.py')],
                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:
        pass
    return jsonify(ok=True)

@app.route('/api/admin/screen')
def admin_screen():
    _admin_check()
    if not _SCREEN_OK:
        return jsonify(error="Pillow nicht installiert"), 503
    return Response(_screen_generator(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/admin/notify', methods=['POST'])
def admin_notify():
    _admin_check()
    data    = request.json or {}
    title   = str(data.get('title', 'BMO'))[:64]
    message = str(data.get('message', ''))[:256]
    if not message:
        return jsonify(ok=False, error="Keine Nachricht.")
    try:
        try:
            from winotify import Notification
            toast = Notification(app_id="BMO", title=title, msg=message)
            toast.show()
        except ImportError:
            t = title.replace('"','').replace("'",'')
            m = message.replace('"','').replace("'",'')
            ps = (
                'Add-Type -AssemblyName System.Windows.Forms;'
                '$n=New-Object System.Windows.Forms.NotifyIcon;'
                '$n.Icon=[System.Drawing.SystemIcons]::Information;'
                '$n.Visible=$true;'
                f'$n.ShowBalloonTip(4000,\'{t}\',\'{m}\',[System.Windows.Forms.ToolTipIcon]::Info);'
                'Start-Sleep 5; $n.Dispose()'
            )
            subprocess.Popen(['powershell', '-WindowStyle', 'Hidden', '-Command', ps])
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/admin/processes')
def admin_processes():
    _admin_check()
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            info = p.info
            procs.append({'pid': info['pid'], 'name': info['name'] or '?',
                          'cpu': round(info['cpu_percent'] or 0, 1),
                          'mem': round(info['memory_percent'] or 0, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x['mem'], reverse=True)
    return jsonify(processes=procs[:80])

@app.route('/api/admin/processes/<int:pid>/kill', methods=['POST'])
def admin_kill_process(pid):
    _admin_check()
    try:
        p = psutil.Process(pid)
        name = p.name()
        p.terminate()
        return jsonify(ok=True, name=name)
    except psutil.NoSuchProcess:
        return jsonify(ok=False, error="Prozess nicht gefunden.")
    except psutil.AccessDenied:
        return jsonify(ok=False, error="Zugriff verweigert.")
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/lite-mode', methods=['GET'])
@login_required
def api_lite_mode_get():
    """Gibt aktuellen Lite-Mode Status vom Core zurück."""
    try:
        r = req.get(f"{CORE_URL}/lite-mode", timeout=3)
        return jsonify(r.json())
    except Exception:
        return jsonify(lite_mode=False, error='Core nicht erreichbar')

@app.route('/api/lite-mode/set', methods=['POST'])
@login_required
def api_lite_mode_set():
    """Setzt Lite-Mode auf Core."""
    data = request.get_json(silent=True) or {}
    try:
        r = req.post(f"{CORE_URL}/lite-mode", json=data, timeout=3)
        return jsonify(r.json())
    except Exception:
        return jsonify(error='Core nicht erreichbar'), 503

# ── START ──────────────────────────────────────────────────────────
if __name__ == '__main__':
    log.info(f"BMO Web Interface startet auf Port {PORT}...")
    log.info(f"Lokal: http://localhost:{PORT}")
    if core_available():
        log.info(f"Core erreichbar auf {CORE_URL}")
    else:
        log.warning("Core NICHT erreichbar!")
    if not WEB_PASSWORD:
        log.info("Ersteinrichtung erforderlich — öffne Browser auf /setup ...")
        def _open_setup():
            import time, webbrowser
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{PORT}/setup")
        threading.Thread(target=_open_setup, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)
