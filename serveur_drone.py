#!/usr/bin/env python3
"""
Serveur de contrôle du Parrot Mambo (Bluetooth BLE uniquement).
Usage :
  1. Allumez le Mambo
  2. python3 scanner_mambo.py   → copiez l'adresse dans MAMBO_ADDR
  3. python3 serveur_drone.py
  4. Ouvrez http://localhost:5000 dans votre navigateur
"""

import os
import sys
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__)

# ═══════════════════════════════════════════════════════
#  CONFIGURATION  — modifiez seulement cette section
# ═══════════════════════════════════════════════════════

# Adresse BLE du Mambo  (trouvez-la avec : python3 scanner_mambo.py)
# Exemple : "e0:14:9f:aa:bb:cc"
MAMBO_ADDR = ""

# ── Calibration des mouvements ───────────────────────
# Valeurs de départ raisonnables pour un Mambo standard.
# Ajustez si le drone va trop loin ou pas assez.

PUISSANCE_TRANSLATION  = 30    # % pour avancer / reculer
DUREE_30CM             = 0.55  # secondes ≈ 30 cm

PUISSANCE_VIRAGE       = 80    # % pour tourner
DUREE_VIRAGE_90        = 0.65  # secondes ≈ 90°

PUISSANCE_VERTICAL     = 50    # % pour monter / descendre
DUREE_VERTICAL_30CM    = 0.45  # secondes ≈ 30 cm vertical

# ═══════════════════════════════════════════════════════

drone = None
etat  = {"connecte": False, "en_vol": False, "altitude_cm": 0}


def get_drone():
    global drone
    if drone is None:
        from pyparrot.Mambo import Mambo
        drone = Mambo(MAMBO_ADDR, use_wifi=False)
    return drone


def rep(ok, message):
    """Retourne une réponse JSON unifiée avec l'état courant."""
    return jsonify({"ok": ok, "message": message, **etat}), 200 if ok else 500


# ── Pages ────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)),
                               "interface_drone.html")


# ── API ──────────────────────────────────────────────

@app.route("/api/etat")
def api_etat():
    return jsonify(etat)


@app.route("/api/connecter", methods=["POST"])
def api_connecter():
    if etat["connecte"]:
        return rep(True, "Déjà connecté")
    if not MAMBO_ADDR:
        return rep(False, "MAMBO_ADDR vide — lancez scanner_mambo.py")
    d = get_drone()
    ok = d.connect(num_retries=3)
    if ok:
        etat["connecte"] = True
        d.smart_sleep(1)
        return rep(True, "Mambo connecté !")
    return rep(False, "Connexion échouée — drone allumé et proche ?")


@app.route("/api/decoller", methods=["POST"])
def api_decoller():
    if not etat["connecte"]:
        return rep(False, "Non connecté")
    if etat["en_vol"]:
        return rep(False, "Déjà en vol")
    d = get_drone()
    d.safe_takeoff(10)
    d.smart_sleep(2)
    etat["en_vol"]      = True
    etat["altitude_cm"] = 50
    return rep(True, "Décollage !")


@app.route("/api/atterrir", methods=["POST"])
def api_atterrir():
    if not etat["connecte"]:
        return rep(False, "Non connecté")
    if not etat["en_vol"]:
        return rep(False, "Pas en vol")
    d = get_drone()
    d.safe_land(10)
    d.smart_sleep(2)
    etat["en_vol"]      = False
    etat["altitude_cm"] = 0
    return rep(True, "Atterrissage !")


@app.route("/api/avancer", methods=["POST"])
def api_avancer():
    if not etat["en_vol"]:
        return rep(False, "Pas en vol")
    d = get_drone()
    d.fly_direct(roll=0, pitch=PUISSANCE_TRANSLATION,
                 yaw=0, vertical_movement=0, duration=DUREE_30CM)
    d.smart_sleep(0.5)
    return rep(True, "Avancé 30 cm")


@app.route("/api/reculer", methods=["POST"])
def api_reculer():
    if not etat["en_vol"]:
        return rep(False, "Pas en vol")
    d = get_drone()
    d.fly_direct(roll=0, pitch=-PUISSANCE_TRANSLATION,
                 yaw=0, vertical_movement=0, duration=DUREE_30CM)
    d.smart_sleep(0.5)
    return rep(True, "Reculé 30 cm")


@app.route("/api/tourner_gauche", methods=["POST"])
def api_tourner_gauche():
    if not etat["en_vol"]:
        return rep(False, "Pas en vol")
    d = get_drone()
    d.fly_direct(roll=0, pitch=0, yaw=-PUISSANCE_VIRAGE,
                 vertical_movement=0, duration=DUREE_VIRAGE_90)
    d.smart_sleep(0.5)
    return rep(True, "Tourné 90° gauche")


@app.route("/api/tourner_droite", methods=["POST"])
def api_tourner_droite():
    if not etat["en_vol"]:
        return rep(False, "Pas en vol")
    d = get_drone()
    d.fly_direct(roll=0, pitch=0, yaw=PUISSANCE_VIRAGE,
                 vertical_movement=0, duration=DUREE_VIRAGE_90)
    d.smart_sleep(0.5)
    return rep(True, "Tourné 90° droite")


@app.route("/api/monter", methods=["POST"])
def api_monter():
    if not etat["en_vol"]:
        return rep(False, "Pas en vol")
    d = get_drone()
    d.fly_direct(roll=0, pitch=0, yaw=0,
                 vertical_movement=PUISSANCE_VERTICAL,
                 duration=DUREE_VERTICAL_30CM)
    d.smart_sleep(0.5)
    etat["altitude_cm"] = min(etat["altitude_cm"] + 30, 200)
    return rep(True, "Monté 30 cm")


@app.route("/api/descendre", methods=["POST"])
def api_descendre():
    if not etat["en_vol"]:
        return rep(False, "Pas en vol")
    d = get_drone()
    d.fly_direct(roll=0, pitch=0, yaw=0,
                 vertical_movement=-PUISSANCE_VERTICAL,
                 duration=DUREE_VERTICAL_30CM)
    d.smart_sleep(0.5)
    etat["altitude_cm"] = max(etat["altitude_cm"] - 30, 20)
    return rep(True, "Descendu 30 cm")


if __name__ == "__main__":
    if not MAMBO_ADDR:
        print("╔══════════════════════════════════════════════════╗")
        print("║  ATTENTION : MAMBO_ADDR est vide !               ║")
        print("║                                                  ║")
        print("║  1. Allumez votre Mambo                          ║")
        print("║  2. Lancez :  python3 scanner_mambo.py           ║")
        print("║  3. Copiez l'adresse dans MAMBO_ADDR             ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

    print("Serveur démarré → http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
