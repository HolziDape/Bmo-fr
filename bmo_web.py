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
import io
import threading
import time as _time

try:
    from PIL import ImageGrab
    _SCREEN_OK = True
except ImportError:
    _SCREEN_OK = False

app  = Flask(__name__)
CORS(app)

PORT       = 5000
CORE_URL   = "http://localhost:6000"

# ── KONFIGURATION (aus bmo_config.txt) ────────────────────────────
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bmo_config.txt")

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

_cfg           = _load_config()
WEB_PASSWORD   = _cfg.get("WEB_PASSWORD", "").strip() or None
FRIEND_URL     = _cfg.get("FRIEND_URL", "http://HIER_FREUND_IP:5000").strip()
app.secret_key = (WEB_PASSWORD or "bmo-setup-mode") + "-bmo-secret-42"

def _save_password(pw: str):
    cfg = _load_config()
    cfg["WEB_PASSWORD"] = pw
    _save_config(cfg)
    log.info("Passwort in bmo_config.txt gespeichert.")

def _save_friend_url(url: str):
    cfg = _load_config()
    cfg["FRIEND_URL"] = url
    _save_config(cfg)
    log.info(f"FRIEND_URL gespeichert: {url}")


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
    global WEB_PASSWORD, FRIEND_URL
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
                FRIEND_URL = friend_url
            WEB_PASSWORD   = pw
            app.secret_key = pw + "-bmo-secret-42"
            session['authenticated'] = True
            log.info("Ersteinrichtung abgeschlossen.")
            return redirect(url_for('index'))
    from flask import render_template_string
    return render_template_string(SETUP_HTML, error=error)

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
    <button class="qbtn friend" onclick="triggerFriendJumpscare()">
      <span class="icon">👻</span>F.Scare
    </button>
    <button class="qbtn friend" onclick="showFriendScreen()">
      <span class="icon">🖥️</span>F.Screen
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
      <div style="display:flex;gap:8px;align-items:center;">
        <span id="screenFps" style="font-size:11px;color:#64748b;"></span>
        <button onclick="closeScreen()"
          style="background:none;border:1px solid #334155;border-radius:8px;color:#94a3b8;padding:5px 12px;cursor:pointer;font-size:13px;">
          ✕ Schließen
        </button>
      </div>
    </div>
    <img id="screenImg" src="" alt="Bildschirm wird geladen...">
  </div>
</div>

<!-- FREUND SCREEN OVERLAY -->
<div class="overlay screen-overlay" id="friendScreenOverlay">
  <div class="screen-sheet" onclick="event.stopPropagation()">
    <div class="screen-header">
      <span style="font-weight:600;font-size:15px;color:#fbbf24;">🖥️ Freund – Bildschirm Live</span>
      <div style="display:flex;gap:8px;align-items:center;">
        <span id="friendScreenStatus" style="font-size:11px;color:#64748b;"></span>
        <button onclick="closeFriendScreen()"
          style="background:none;border:1px solid #334155;border-radius:8px;color:#94a3b8;padding:5px 12px;cursor:pointer;font-size:13px;">
          ✕ Schließen
        </button>
      </div>
    </div>
    <img id="friendScreenImg" src="" alt="Freund Bildschirm wird geladen...">
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

function showScreen() {
  _screenActive = true;
  document.getElementById('screenOverlay').classList.add('show');
  document.getElementById('screenImg').src = '/api/screen?' + Date.now();
}

function closeScreen() {
  _screenActive = false;
  document.getElementById('screenOverlay').classList.remove('show');
  // src leeren stoppt den MJPEG-Stream (spart Bandbreite)
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

// ── FREUND AKTIONEN ──────────────────────────────────────────────
async function triggerFriendJumpscare() {
  try {
    const r = await fetch('/api/friend/jumpscare', {method: 'POST'});
    const d = await r.json();
    if (d.ok) {
      addMsg('👻 Jumpscare an Freund gesendet!', 'sys');
    } else {
      addMsg('⛔ Freund hat Admin-Zugriff nicht aktiviert.', 'sys');
    }
  } catch(e) {
    addMsg('Freund nicht erreichbar 😢', 'sys');
  }
}

let _friendScreenActive = false;
function showFriendScreen() {
  _friendScreenActive = true;
  document.getElementById('friendScreenStatus').textContent = 'Verbinde...';
  document.getElementById('friendScreenOverlay').classList.add('show');
  const img = document.getElementById('friendScreenImg');
  img.src = '/api/friend/screen?' + Date.now();
  img.onload = () => { document.getElementById('friendScreenStatus').textContent = 'Live'; };
  img.onerror = () => { document.getElementById('friendScreenStatus').textContent = '⛔ Kein Zugriff'; img.src = ''; };
}
function closeFriendScreen() {
  _friendScreenActive = false;
  document.getElementById('friendScreenOverlay').classList.remove('show');
  setTimeout(() => { if (!_friendScreenActive) document.getElementById('friendScreenImg').src = ''; }, 300);
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
_screen_lock = threading.Lock()

def _screen_generator():
    """MJPEG-Generator: streamt den Desktop als ca. 10 FPS JPEG-Stream."""
    while True:
        if not _SCREEN_OK:
            break
        try:
            with _screen_lock:
                img = ImageGrab.grab()
            # Auf max. 1280px Breite skalieren
            w, h = img.size
            new_w = min(w, 1280)
            new_h = int(h * new_w / w)
            if (new_w, new_h) != (w, h):
                img = img.resize((new_w, new_h))
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=55)
            frame = buf.getvalue()
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        except Exception:
            pass
        _time.sleep(0.1)   # max. 10 FPS

@app.route('/api/screen')
@login_required
def screen_stream():
    if not _SCREEN_OK:
        return jsonify(error="Pillow (PIL) nicht installiert. Bitte: pip install Pillow"), 503
    return Response(_screen_generator(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# ── FREUND PROXY ROUTEN ────────────────────────────────────────────

@app.route('/api/friend/jumpscare', methods=['POST'])
@login_required
def friend_jumpscare():
    """Sendet Jumpscare an Freund (nur wenn Freund Admin-Zugriff aktiviert hat)."""
    if "HIER_FREUND_IP" in FRIEND_URL:
        return jsonify(ok=False, error="FRIEND_URL nicht konfiguriert.")
    try:
        r = req.post(f"{FRIEND_URL}/api/admin/jumpscare", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route('/api/friend/screen')
@login_required
def friend_screen():
    """Streamt den Bildschirm des Freundes (nur wenn Freund Admin-Zugriff aktiviert hat)."""
    if "HIER_FREUND_IP" in FRIEND_URL:
        return jsonify(error="FRIEND_URL nicht konfiguriert."), 503
    try:
        r = req.get(f"{FRIEND_URL}/api/admin/screen", stream=True, timeout=10)
        if r.status_code == 403:
            return jsonify(error="Freund hat Zugriff nicht erlaubt."), 403
        return Response(
            r.iter_content(chunk_size=4096),
            content_type=r.headers.get('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        )
    except Exception as e:
        return jsonify(error=str(e)), 503


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
    app.run(host='0.0.0.0', port=PORT, debug=False)
