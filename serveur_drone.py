#!/usr/bin/env python3
"""
Serveur de contrôle du Parrot Mambo (Bluetooth BLE).
Usage :
  1. Allumez le Mambo
  2. python serveur_drone.py
  3. Ouvrez http://localhost:5000
"""

import os
import threading
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__)

# ═══════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════
MAMBO_ADDR = "D0:3A:9F:EF:E6:22"

PUISSANCE_TRANSLATION = 30
DUREE_30CM            = 0.55

PUISSANCE_VIRAGE      = 80
DUREE_VIRAGE_90       = 0.65

PUISSANCE_VERTICAL    = 50
DUREE_VERTICAL_30CM   = 0.45
# ═══════════════════════════════════════════════════════

drone = None
etat  = {"connecte": False, "en_vol": False, "altitude_cm": 0}

prog  = {"en_cours": False, "etape": -1, "total": 0,
         "message": "", "succes": None}


def get_drone():
    global drone
    if drone is None:
        from pyparrot.Mambo import Mambo
        drone = Mambo(MAMBO_ADDR, use_wifi=False)
    return drone


# ── Logique drone (fonctions internes) ───────────────

def _decoller():
    if not etat["connecte"]: raise Exception("Non connecté")
    d = get_drone()
    d.safe_takeoff(10)
    d.smart_sleep(2)
    etat["en_vol"] = True
    etat["altitude_cm"] = 50

def _atterrir():
    d = get_drone()
    d.safe_land(10)
    d.smart_sleep(2)
    etat["en_vol"] = False
    etat["altitude_cm"] = 0

def _avancer():
    d = get_drone()
    d.fly_direct(roll=0, pitch=PUISSANCE_TRANSLATION,
                 yaw=0, vertical_movement=0, duration=DUREE_30CM)
    d.smart_sleep(0.6)

def _reculer():
    d = get_drone()
    d.fly_direct(roll=0, pitch=-PUISSANCE_TRANSLATION,
                 yaw=0, vertical_movement=0, duration=DUREE_30CM)
    d.smart_sleep(0.6)

def _tourner_gauche():
    d = get_drone()
    d.fly_direct(roll=0, pitch=0, yaw=-PUISSANCE_VIRAGE,
                 vertical_movement=0, duration=DUREE_VIRAGE_90)
    d.smart_sleep(0.6)

def _tourner_droite():
    d = get_drone()
    d.fly_direct(roll=0, pitch=0, yaw=PUISSANCE_VIRAGE,
                 vertical_movement=0, duration=DUREE_VIRAGE_90)
    d.smart_sleep(0.6)

def _monter():
    d = get_drone()
    d.fly_direct(roll=0, pitch=0, yaw=0,
                 vertical_movement=PUISSANCE_VERTICAL,
                 duration=DUREE_VERTICAL_30CM)
    d.smart_sleep(0.6)
    etat["altitude_cm"] = min(etat["altitude_cm"] + 30, 200)

def _descendre():
    d = get_drone()
    d.fly_direct(roll=0, pitch=0, yaw=0,
                 vertical_movement=-PUISSANCE_VERTICAL,
                 duration=DUREE_VERTICAL_30CM)
    d.smart_sleep(0.6)
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
    prog["en_cours"] = True
    prog["total"]    = len(actions)
    prog["succes"]   = None

    for i, action in enumerate(actions):
        prog["etape"]   = i
        prog["message"] = LABELS.get(action, action) + "..."
        try:
            ACTIONS[action]()
        except Exception as e:
            prog["message"]  = f"Erreur : {e}"
            prog["en_cours"] = False
            prog["succes"]   = False
            prog["etape"]    = -1
            return

    prog["en_cours"] = False
    prog["succes"]   = True
    prog["etape"]    = -1
    prog["message"]  = "Programme terminé !"


# ── Routes ───────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "interface_blocs.html"
    )

@app.route("/api/etat")
def api_etat():
    return jsonify({**etat, "programme": prog})

@app.route("/api/connecter", methods=["POST"])
def api_connecter():
    if etat["connecte"]:
        return jsonify({"ok": True, "message": "Déjà connecté", **etat})
    d = get_drone()
    ok = d.connect(num_retries=3)
    if ok:
        etat["connecte"] = True
        d.smart_sleep(1)
        return jsonify({"ok": True, "message": "Mambo connecté !", **etat})
    return jsonify({"ok": False, "message": "Connexion échouée — drone allumé ?", **etat})

@app.route("/api/programme", methods=["POST"])
def api_programme():
    if not etat["connecte"]:
        return jsonify({"ok": False, "message": "Non connecté"})
    if prog["en_cours"]:
        return jsonify({"ok": False, "message": "Programme déjà en cours"})

    actions = request.get_json(force=True).get("actions", [])
    if not actions:
        return jsonify({"ok": False, "message": "Programme vide"})

    invalides = [a for a in actions if a not in ACTIONS]
    if invalides:
        return jsonify({"ok": False, "message": f"Action inconnue : {invalides[0]}"})

    t = threading.Thread(target=_executer_programme, args=(actions,), daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "C'est parti !"})


if __name__ == "__main__":
    print("Serveur démarré → http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
