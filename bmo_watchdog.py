"""
BMO Watchdog
=============
Überwacht bmo_core.py und bmo_web.py.
Wenn ein Prozess abstürzt, startet er ihn automatisch neu.

Starten mit: pythonw bmo_watchdog.py
(oder über bmo_start.bat — ersetzt den direkten Start)
"""

import subprocess
import time
import os
import sys
import logging

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE, "logs", "bmo_watchdog.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ]
)
log = logging.getLogger("BMO-Watchdog")

PYTHON = sys.executable  # derselbe Interpreter der den Watchdog startet
CORE   = os.path.join(BASE, "bmo_core.py")
WEB    = os.path.join(BASE, "bmo_web.py")

CHECK_INTERVAL = 20   # Sekunden zwischen Checks
CORE_DELAY     = 8    # Sekunden warten bevor Web gestartet wird (Core braucht Zeit)

core_proc: subprocess.Popen | None = None
web_proc:  subprocess.Popen | None = None


def start_core():
    global core_proc
    log.info("Starte bmo_core.py ...")
    core_proc = subprocess.Popen(
        [PYTHON, CORE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log.info(f"Core PID: {core_proc.pid}")


def start_web():
    global web_proc
    log.info("Starte bmo_web.py ...")
    web_proc = subprocess.Popen(
        [PYTHON, WEB],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log.info(f"Web PID: {web_proc.pid}")


def is_running(proc: subprocess.Popen | None) -> bool:
    return proc is not None and proc.poll() is None


log.info("BMO Watchdog gestartet.")
log.info(f"Core: {CORE}")
log.info(f"Web:  {WEB}")
log.info(f"Check-Intervall: {CHECK_INTERVAL}s")

# Erster Start
start_core()
time.sleep(CORE_DELAY)
start_web()

# Hauptschleife
while True:
    time.sleep(CHECK_INTERVAL)

    if not is_running(core_proc):
        log.warning("Core ist abgestürzt! Neustart...")
        start_core()
        time.sleep(CORE_DELAY)
        # Web auch neu starten falls es läuft (hängt am Core)
        if is_running(web_proc):
            web_proc.terminate()
            web_proc = None
        start_web()
    elif not is_running(web_proc):
        log.warning("Web ist abgestürzt! Neustart...")
        start_web()
