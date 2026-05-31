#!/usr/bin/env python3
"""
Programme de vol Parrot Mambo - Séquence simple
  1. Décollage
  2. Avancer 30 cm
  3. Tourner 90 degrés (droite)
  4. Reculer 30 cm
  5. Atterrissage
"""

import sys

# ═══════════════════════════════════════════════════════
#  CONFIGURATION  (seule section à modifier)
# ═══════════════════════════════════════════════════════

# Mode de connexion : True = Wi-Fi (module FPV requis)
#                     False = Bluetooth BLE (défaut Mambo)
MAMBO_WIFI = False

# Adresse Bluetooth BLE du Mambo — utilisée seulement si MAMBO_WIFI = False
# Pour la trouver : lancez  python3 scanner_mambo.py
# Exemple : "e0:14:9f:XX:XX:XX"
MAMBO_ADDR = ""

# ── Calibration des mouvements ───────────────────────
# Le Mambo n'a pas de déplacement précis en cm ; on pilote
# en donnant une puissance (%) + une durée (s).
# Ajustez ces valeurs si le drone va trop loin ou pas assez.

PUISSANCE_AVANT_ARRIERE = 30   # % de poussée (1-100)
DUREE_30CM              = 0.6  # secondes ≈ 30 cm à puissance 30

PUISSANCE_VIRAGE        = 80   # % de rotation (1-100)
DUREE_VIRAGE_90         = 0.7  # secondes ≈ 90°  à puissance 80

# ═══════════════════════════════════════════════════════


def connexion_mambo():
    from pyparrot.Mambo import Mambo

    if not MAMBO_WIFI and MAMBO_ADDR == "":
        print("ERREUR : MAMBO_ADDR est vide.")
        print("  → Lancez  python3 scanner_mambo.py  pour trouver l'adresse BLE,")
        print("    puis renseignez MAMBO_ADDR dans ce fichier.")
        print("  → Ou passez MAMBO_WIFI = True si vous avez le module Wi-Fi/FPV.")
        sys.exit(1)

    drone = Mambo(MAMBO_ADDR, use_wifi=MAMBO_WIFI)

    mode = "Wi-Fi" if MAMBO_WIFI else f"Bluetooth BLE ({MAMBO_ADDR})"
    print(f"Connexion au Mambo via {mode}...")
    connected = drone.connect(num_retries=3)

    if not connected:
        print("ERREUR : impossible de se connecter au Mambo.")
        if MAMBO_WIFI:
            print("  → Vérifiez que vous êtes connecté au Wi-Fi du drone.")
        else:
            print("  → Vérifiez que le drone est allumé et l'adresse BLE correcte.")
            print("    Relancez  python3 scanner_mambo.py  si besoin.")
        sys.exit(1)

    return drone


def vol_mambo():
    drone = connexion_mambo()

    print("Connecté ! Stabilisation...")
    drone.smart_sleep(2)

    # ── 1. Décollage ────────────────────────────────────
    print("\n[1/5] Décollage")
    drone.safe_takeoff(10)
    drone.smart_sleep(2)

    # ── 2. Avancer 30 cm ────────────────────────────────
    # fly_direct(roll, pitch, yaw, vertical_movement, duration)
    #   pitch > 0  → avancer   |   pitch < 0  → reculer
    #   roll  > 0  → droite    |   roll  < 0  → gauche
    #   yaw   > 0  → rotation droite
    print("[2/5] Avancer 30 cm")
    drone.fly_direct(roll=0, pitch=PUISSANCE_AVANT_ARRIERE, yaw=0,
                     vertical_movement=0, duration=DUREE_30CM)
    drone.smart_sleep(1)

    # ── 3. Tourner 90° à droite ─────────────────────────
    print("[3/5] Tourner 90° à droite")
    drone.fly_direct(roll=0, pitch=0, yaw=PUISSANCE_VIRAGE,
                     vertical_movement=0, duration=DUREE_VIRAGE_90)
    drone.smart_sleep(1)

    # ── 4. Reculer 30 cm ────────────────────────────────
    print("[4/5] Reculer 30 cm")
    drone.fly_direct(roll=0, pitch=-PUISSANCE_AVANT_ARRIERE, yaw=0,
                     vertical_movement=0, duration=DUREE_30CM)
    drone.smart_sleep(1)

    # ── 5. Atterrissage ─────────────────────────────────
    print("[5/5] Atterrissage")
    drone.safe_land(10)
    drone.smart_sleep(2)

    drone.disconnect()
    print("\nMission accomplie !")


if __name__ == "__main__":
    vol_mambo()
