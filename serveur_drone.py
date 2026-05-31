#!/usr/bin/env python3
"""
Serveur de contrôle du Parrot Mambo — Compatible Windows
Utilise bleak au lieu de pyparrot/bluepy (qui ne fonctionne pas sur Windows).

Usage :
  1. Allumez le Mambo
  2. python serveur_drone.py
  3. Ouvrez http://localhost:5000
"""

import asyncio
import struct
import time
import threading
import os
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__)

# ═══════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════
MAMBO_ADDR = "D0:3A:9F:EF:E6:22"

PUISSANCE_TRANSLATION = 30     # % pour avancer / reculer
DUREE_30CM            = 0.55   # secondes ≈ 30 cm

PUISSANCE_VIRAGE      = 80     # % pour tourner
DUREE_VIRAGE_90       = 0.65   # secondes ≈ 90°

PUISSANCE_VERTICAL    = 50     # % pour monter / descendre
DUREE_VERTICAL_30CM   = 0.45   # secondes ≈ 30 cm vertical
# ═══════════════════════════════════════════════════════

# ── UUIDs BLE du Parrot Mambo (protocole ARSDK) ──────
# Source : pyparrot/networking/bleConnection.py
CHAR_SEND_WITH_ACK  = "9a66fa0b-0800-9191-11e4-012d1540cb8e"  # décollage, atterrissage
CHAR_SEND_NO_ACK    = "9a66fa0a-0800-9191-11e4-012d1540cb8e"  # PCMD (mouvement continu)
CHAR_SEND_HIGH_PRIO = "9a66fa0c-0800-9191-11e4-012d1540cb8e"  # urgence

# Caractéristiques de réception (activées pour le handshake du drone)
NOTIFY_CHARS = [
    "9a66fb0e-0800-9191-11e4-012d1540cb8e",
    "9a66fb0f-0800-9191-11e4-012d1540cb8e",
    "9a66fb1b-0800-9191-11e4-012d1540cb8e",
    "9a66fb1c-0800-9191-11e4-012d1540cb8e",
]

# ── IDs de commandes ARSDK Minidrone ─────────────────
# Source : pyparrot/commandsandsensors/minidrone.xml
_PROJECT  = 2   # minidrone
_PILOTING = 0   # classe Piloting
_TAKEOFF  = 1
_PCMD     = 2
_LAND     = 3

_seq = {"ack": 0, "noack": 0}


def _paquet_ack(cmd_id):
    """Paquet pour commandes avec accusé de réception (décollage, atterrissage)."""
    _seq["ack"] = (_seq["ack"] + 1) % 256
    # format : data_type=4, seq, project, class, cmd
    return struct.pack("<BBBBH", 4, _seq["ack"], _PROJECT, _PILOTING, cmd_id)


def _paquet_pcmd(roll, pitch, yaw, vertical):
    """Paquet PCMD (mouvement continu, sans accusé de réception)."""
    _seq["noack"] = (_seq["noack"] + 1) % 256
    # format : data_type=2, seq, project, class, cmd, flag, roll, pitch, yaw, vertical, timestamp
    return struct.pack("<BBBBHBbbbbI",
                       2, _seq["noack"], _PROJECT, _PILOTING, _PCMD,
                       1, int(roll), int(pitch), int(yaw), int(vertical), 0)


# ── Contrôleur BLE asynchrone ────────────────────────

class MamboController:
    """Gère la connexion BLE et l'envoi de commandes dans un thread asyncio dédié."""

    def __init__(self):
        self.client = None
        self._loop  = asyncio.new_event_loop()
        threading.Thread(target=self._boucle_asyncio, daemon=True).start()

    def _boucle_asyncio(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _executer(self, coro, timeout=30):
        """Exécute une coroutine dans le thread asyncio et attend le résultat."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _notification(self, sender, data):
        pass  # handshake requis, contenu ignoré

    async def _connecter_async(self):
        from bleak import BleakClient
        self.client = BleakClient(MAMBO_ADDR)
        await self.client.connect(timeout=15.0)
        # Activer les notifications = handshake indispensable pour que le drone accepte les commandes
        for uuid in NOTIFY_CHARS:
            try:
                await self.client.start_notify(uuid, self._notification)
            except Exception:
                pass   # certains firmwares n'ont pas toutes les caractéristiques
        await asyncio.sleep(0.5)
        # Démarrer le keep-alive : envoie un PCMD neutre toutes les 0.5 s
        # pour éviter que le Mambo coupe la connexion BLE par inactivité
        asyncio.ensure_future(self._keep_alive())

    async def _keep_alive(self):
        while self.client and self.client.is_connected:
            try:
                pkt = bytearray(_paquet_pcmd(0, 0, 0, 0))
                await self.client.write_gatt_char(CHAR_SEND_NO_ACK, pkt, response=False)
            except Exception:
                break
            await asyncio.sleep(0.5)

    async def _cmd_ack_async(self, paquet):
        await self.client.write_gatt_char(
            CHAR_SEND_WITH_ACK, bytearray(paquet), response=False)

    async def _fly_async(self, roll, pitch, yaw, vertical, duree):
        fin = time.time() + duree
        while time.time() < fin:
            pkt = bytearray(_paquet_pcmd(roll, pitch, yaw, vertical))
            await self.client.write_gatt_char(CHAR_SEND_NO_ACK, pkt, response=False)
            await asyncio.sleep(0.05)
        # Arrêt propre
        stop = bytearray(_paquet_pcmd(0, 0, 0, 0))
        await self.client.write_gatt_char(CHAR_SEND_NO_ACK, stop, response=False)

    # ── Interface publique (appelée depuis Flask / threads) ──

    def connecter(self):
        self._executer(self._connecter_async(), timeout=20)

    def decoller(self):
        self._executer(self._cmd_ack_async(_paquet_ack(_TAKEOFF)))
        time.sleep(2.5)

    def atterrir(self):
        self._executer(self._cmd_ack_async(_paquet_ack(_LAND)))
        time.sleep(2.5)

    def fly_direct(self, roll, pitch, yaw, vertical, duree):
        self._executer(self._fly_async(roll, pitch, yaw, vertical, duree),
                       timeout=duree + 5)
        time.sleep(0.3)

    @property
    def connecte(self):
        return self.client is not None and self.client.is_connected


# ── Singleton ─────────────────────────────────────────
mambo = MamboController()

etat = {"connecte": False, "en_vol": False, "altitude_cm": 0}
prog = {"en_cours": False, "etape": -1, "total": 0,
        "message": "", "succes": None}


# ── Fonctions drone ───────────────────────────────────

def _decoller():
    mambo.decoller()
    etat["en_vol"]      = True
    etat["altitude_cm"] = 50

def _atterrir():
    mambo.atterrir()
    etat["en_vol"]      = False
    etat["altitude_cm"] = 0

def _avancer():
    mambo.fly_direct(0, PUISSANCE_TRANSLATION, 0, 0, DUREE_30CM)

def _reculer():
    mambo.fly_direct(0, -PUISSANCE_TRANSLATION, 0, 0, DUREE_30CM)

def _tourner_gauche():
    mambo.fly_direct(0, 0, -PUISSANCE_VIRAGE, 0, DUREE_VIRAGE_90)

def _tourner_droite():
    mambo.fly_direct(0, 0, PUISSANCE_VIRAGE, 0, DUREE_VIRAGE_90)

def _monter():
    mambo.fly_direct(0, 0, 0, PUISSANCE_VERTICAL, DUREE_VERTICAL_30CM)
    etat["altitude_cm"] = min(etat["altitude_cm"] + 30, 200)

def _descendre():
    mambo.fly_direct(0, 0, 0, -PUISSANCE_VERTICAL, DUREE_VERTICAL_30CM)
    etat["altitude_cm"] = max(etat["altitude_cm"] - 30, 20)


ACTIONS = {
    "decoller":       _decoller,
    "atterrir":       _atterrir,
    "avancer":        _avancer,
    "reculer":        _reculer,
    "tourner_gauche": _tourner_gauche,
    "tourner_droite": _tourner_droite,
    "monter":         _monter,
    "descendre":      _descendre,
}

LABELS = {
    "decoller":       "Décollage",
    "atterrir":       "Atterrissage",
    "avancer":        "Avancer 30 cm",
    "reculer":        "Reculer 30 cm",
    "tourner_gauche": "Tourner gauche 90°",
    "tourner_droite": "Tourner droite 90°",
    "monter":         "Monter 30 cm",
    "descendre":      "Descendre 30 cm",
}


def _executer_programme(actions):
    prog.update(en_cours=True, total=len(actions), succes=None)
    for i, action in enumerate(actions):
        prog.update(etape=i, message=LABELS.get(action, action) + "...")
        try:
            ACTIONS[action]()
        except Exception as e:
            prog.update(en_cours=False, succes=False, etape=-1,
                        message=f"Erreur : {e}")
            return
    prog.update(en_cours=False, succes=True, etape=-1,
                message="Programme terminé !")


# ── Routes Flask ──────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "interface_blocs.html")

@app.route("/api/etat")
def api_etat():
    return jsonify({**etat, "programme": prog})

@app.route("/api/connecter", methods=["POST"])
def api_connecter():
    if etat["connecte"]:
        return jsonify({"ok": True, "message": "Déjà connecté", **etat})
    try:
        mambo.connecter()
        etat["connecte"] = True
        return jsonify({"ok": True, "message": "Mambo connecté !", **etat})
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower() or "unreachable" in msg.lower():
            msg = "Drone introuvable — allumez le Mambo et réessayez"
        elif "timeout" in msg.lower():
            msg = "Délai dépassé — drone trop loin ?"
        return jsonify({"ok": False, "message": msg, **etat})

@app.route("/api/programme", methods=["POST"])
def api_programme():
    if not etat["connecte"]:
        return jsonify({"ok": False, "message": "Non connecté"})
    if prog["en_cours"]:
        return jsonify({"ok": False, "message": "Programme déjà en cours"})
    actions = request.get_json(force=True).get("actions", [])
    if not actions:
        return jsonify({"ok": False, "message": "Programme vide"})
    threading.Thread(target=_executer_programme, args=(actions,), daemon=True).start()
    return jsonify({"ok": True, "message": "C'est parti !"})


if __name__ == "__main__":
    print("=" * 50)
    print("  Contrôle Mambo — démarrage du serveur")
    print("  Ouvrez http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
