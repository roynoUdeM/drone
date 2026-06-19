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
PUISSANCE_TRANSLATION = 30     # % pour avancer / reculer
DUREE_30CM            = 0.80   # secondes ≈ 30 cm

PUISSANCE_VIRAGE      = 80     # % pour tourner
DUREE_VIRAGE_90       = 0.93   # secondes ≈ 90°

PUISSANCE_VERTICAL    = 50     # % pour monter / descendre
DUREE_VERTICAL_30CM   = 0.65   # secondes ≈ 30 cm vertical
# ═══════════════════════════════════════════════════════

drone_actif = {"nom": "", "adresse": ""}

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
_PROJECT      = 2   # minidrone
_PILOTING     = 0   # classe Piloting
_TAKEOFF      = 1
_PCMD         = 2
_LAND         = 3

_MEDIA_RECORD = 6   # classe MediaRecord
_TAKE_PICTURE = 0   # commande Picture

_seq = {"ack": 0, "noack": 0}


def _paquet_ack(cmd_id):
    """Paquet pour commandes avec accusé de réception (décollage, atterrissage)."""
    _seq["ack"] = (_seq["ack"] + 1) % 256
    return struct.pack("<BBBBH", 4, _seq["ack"], _PROJECT, _PILOTING, cmd_id)


def _paquet_photo():
    """Paquet pour déclencher la prise de photo (caméra verticale)."""
    _seq["ack"] = (_seq["ack"] + 1) % 256
    # data_type=4, seq, project=2, class=6 (MediaRecord), cmd=0 (Picture), mass_storage_id=0
    return struct.pack("<BBBBHb", 4, _seq["ack"], _PROJECT, _MEDIA_RECORD, _TAKE_PICTURE, 0)


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
        self.client    = None
        self._loop     = asyncio.new_event_loop()
        self._moving   = False   # True pendant fly_direct → keep_alive se tait
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
        from bleak import BleakClient, BleakScanner

        addr = drone_actif["adresse"]
        nom  = drone_actif["nom"]
        print(f"[1/3] Recherche de {nom} ({addr}) en Bluetooth...")
        etat["statut"] = "Recherche du drone..."
        device = await BleakScanner.find_device_by_address(addr, timeout=8.0)
        if device is None:
            raise Exception(
                f"{nom} introuvable — "
                "vérifiez qu'il est allumé et que son LED clignote en vert"
            )
        print(f"[2/3] {nom} trouvé — connexion BLE...")
        etat["statut"] = "Connexion BLE..."

        self.client = BleakClient(device)
        await self.client.connect(timeout=12.0)
        print(f"[3/3] Connecté — handshake...")

        # Activer les notifications = handshake indispensable
        for uuid in NOTIFY_CHARS:
            try:
                await self.client.start_notify(uuid, self._notification)
            except Exception:
                pass
        await asyncio.sleep(0.5)

        # Keep-alive : PCMD neutre toutes les 0.5 s pour maintenir la connexion
        asyncio.ensure_future(self._keep_alive())

    async def _keep_alive(self):
        while self.client and self.client.is_connected:
            try:
                if not self._moving:   # ne pas interrompre un mouvement en cours
                    pkt = bytearray(_paquet_pcmd(0, 0, 0, 0))
                    await self.client.write_gatt_char(CHAR_SEND_NO_ACK, pkt, response=False)
            except Exception:
                break
            await asyncio.sleep(0.5)

    async def _cmd_ack_async(self, paquet):
        await self.client.write_gatt_char(
            CHAR_SEND_WITH_ACK, bytearray(paquet), response=False)

    async def _fly_async(self, roll, pitch, yaw, vertical, duree):
        self._moving = True
        try:
            fin = time.time() + duree
            while time.time() < fin:
                pkt = bytearray(_paquet_pcmd(roll, pitch, yaw, vertical))
                await self.client.write_gatt_char(CHAR_SEND_NO_ACK, pkt, response=False)
                await asyncio.sleep(0.05)
            # Arrêt propre
            stop = bytearray(_paquet_pcmd(0, 0, 0, 0))
            await self.client.write_gatt_char(CHAR_SEND_NO_ACK, stop, response=False)
        finally:
            self._moving = False

    # ── Interface publique (appelée depuis Flask / threads) ──

    def connecter(self):
        self._executer(self._connecter_async(), timeout=30)

    def deconnecter(self):
        try:
            async def _disc():
                if self.client:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None
            self._executer(_disc(), timeout=8)
        except Exception:
            pass
        self.client = None

    def decoller(self):
        self._executer(self._cmd_ack_async(_paquet_ack(_TAKEOFF)))
        time.sleep(2.5)

    def atterrir(self):
        self._executer(self._cmd_ack_async(_paquet_ack(_LAND)))
        time.sleep(2.5)

    def fly_direct(self, roll, pitch, yaw, vertical, duree):
        self._executer(self._fly_async(roll, pitch, yaw, vertical, duree),
                       timeout=duree + 5)
        time.sleep(1.2)  # pause pour laisser le drone se stabiliser avant la prochaine action

    def prendre_photo(self):
        self._executer(self._cmd_ack_async(_paquet_photo()))
        time.sleep(0.5)

    @property
    def connecte(self):
        return self.client is not None and self.client.is_connected


# ── Singleton ─────────────────────────────────────────
mambo = MamboController()

etat = {"connecte": False, "en_vol": False, "altitude_cm": 0, "statut": ""}
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

def _prendre_photo():
    mambo.prendre_photo()


ACTIONS = {
    "decoller":       _decoller,
    "atterrir":       _atterrir,
    "avancer":        _avancer,
    "reculer":        _reculer,
    "tourner_gauche": _tourner_gauche,
    "tourner_droite": _tourner_droite,
    "monter":         _monter,
    "descendre":      _descendre,
    "photo":          _prendre_photo,
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
    "photo":          "Prendre une photo",
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
    return jsonify({**etat, "programme": prog, "drone_actif": drone_actif})

@app.route("/api/scanner", methods=["POST"])
def api_scanner():
    """Scanne le Bluetooth et retourne les drones Parrot détectés à proximité."""
    async def _scan():
        from bleak import BleakScanner
        devices = await BleakScanner.discover(timeout=5.0)
        drones = []
        for d in devices:
            nom = (d.name or "").strip()
            if any(k in nom.upper() for k in ["MAMBO", "PARROT", "SWING", "ROLLING", "BEBOP", "ANAFI"]):
                drones.append({"nom": nom, "adresse": d.address})
        return drones
    try:
        drones = asyncio.run_coroutine_threadsafe(_scan(), mambo._loop).result(timeout=15)
        return jsonify({"ok": True, "drones": drones})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e), "drones": []})

@app.route("/api/connecter", methods=["POST"])
def api_connecter():
    global drone_actif
    data = request.get_json(force=True) or {}
    drone_actif["nom"]     = data.get("nom", "Drone")
    drone_actif["adresse"] = data.get("adresse", "")
    if not drone_actif["adresse"]:
        return jsonify({"ok": False, "message": "Adresse Bluetooth manquante", **etat})

    # Déconnecter proprement si une connexion précédente existe
    if etat["connecte"] or mambo.client is not None:
        mambo.deconnecter()
        etat["connecte"] = False
        etat["en_vol"]   = False

    try:
        mambo.connecter()
        etat["connecte"] = True
        return jsonify({"ok": True, "message": f"{drone_actif['nom']} connecté !", **etat, "drone_actif": drone_actif})
    except Exception as e:
        etat["connecte"] = False
        msg = str(e)
        if "not found" in msg.lower() or "unreachable" in msg.lower() or "introuvable" in msg.lower():
            msg = f"{drone_actif['nom']} introuvable — allumez le drone et attendez que la LED clignote"
        elif "timeout" in msg.lower():
            msg = "Délai dépassé — drone trop loin ou pile trop faible ?"
        return jsonify({"ok": False, "message": msg, **etat})

@app.route("/api/urgence", methods=["POST"])
def api_urgence():
    """Atterrissage forcé immédiat — interrompt tout programme en cours."""
    prog.update(en_cours=False, succes=False, etape=-1, message="Atterrissage d'urgence !")
    try:
        mambo.atterrir()
        etat["en_vol"]      = False
        etat["altitude_cm"] = 0
        return jsonify({"ok": True, "message": "Atterrissage d'urgence effectué", **etat})
    except Exception as e:
        return jsonify({"ok": False, "message": f"Urgence échouée : {e}", **etat})

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
