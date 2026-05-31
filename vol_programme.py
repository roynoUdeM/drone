#!/usr/bin/env python3
"""
Programme de vol Parrot - Séquence simple
  1. Décollage
  2. Avancer 30 cm
  3. Tourner 90 degrés (droite)
  4. Reculer 30 cm
  5. Atterrissage

Modèles supportés : Bebop 2 (Wi-Fi) et Mambo (BLE ou Wi-Fi)
"""

import sys
import math
import time

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────
MODELE = "bebop"   # "bebop"  ou  "mambo"

# Pour Mambo uniquement : True = Wi-Fi, False = Bluetooth BLE
MAMBO_WIFI = True

# Adresse IP du Bebop (laisser tel quel si votre routeur est standard)
BEBOP_IP = "192.168.42.1"
# ─────────────────────────────────────────


def vol_bebop():
    from pyparrot.Bebop import Bebop

    drone = Bebop()
    print("Connexion au Bebop...")
    connected = drone.connect(10)
    if not connected:
        print("ERREUR : impossible de se connecter au Bebop.")
        print("Vérifiez que vous êtes connecté au Wi-Fi du drone.")
        sys.exit(1)

    print("Connecté ! Mise à jour des états...")
    drone.smart_sleep(2)

    print(">>> Décollage")
    drone.safe_takeoff(10)
    drone.smart_sleep(2)

    print(">>> Avancer 30 cm")
    # move_relative(dx_m, dy_m, dz_m, dr_rad)
    # dx positif = avant, dy positif = droite, dz positif = bas
    drone.move_relative(0.30, 0, 0, 0)
    drone.smart_sleep(2)

    print(">>> Tourner 90 degrés vers la droite")
    drone.move_relative(0, 0, 0, math.radians(90))
    drone.smart_sleep(2)

    print(">>> Reculer 30 cm")
    drone.move_relative(-0.30, 0, 0, 0)
    drone.smart_sleep(2)

    print(">>> Atterrissage")
    drone.safe_land(10)
    drone.smart_sleep(2)

    drone.disconnect()
    print("Mission accomplie !")


def vol_mambo():
    from pyparrot.Mambo import Mambo

    # L'adresse BLE de votre Mambo (ignorée en mode Wi-Fi)
    mambo_addr = ""
    drone = Mambo(mambo_addr, use_wifi=MAMBO_WIFI)

    print("Connexion au Mambo...")
    connected = drone.connect(num_retries=3)
    if not connected:
        print("ERREUR : impossible de se connecter au Mambo.")
        print("En BLE : vérifiez l'adresse Bluetooth.")
        print("En Wi-Fi : vérifiez la connexion Wi-Fi au drone.")
        sys.exit(1)

    print("Connecté ! Mise à jour des états...")
    drone.smart_sleep(2)

    print(">>> Décollage")
    drone.safe_takeoff(10)
    drone.smart_sleep(2)

    # Le Mambo n'a pas de move_relative — on utilise fly_direct
    # (valeurs : -100 à +100 en % de puissance, + durée en secondes)
    # Calibration approximative : 25 % pendant ~0.6 s ≈ 30 cm
    PUISSANCE = 25          # % de poussée
    DUREE_30CM = 0.6        # secondes (à ajuster selon votre drone)
    DUREE_VIRAGE_90 = 0.65  # secondes pour 90° (à ajuster)

    print(">>> Avancer 30 cm")
    drone.fly_direct(roll=0, pitch=PUISSANCE, yaw=0,
                     vertical_movement=0, duration=DUREE_30CM)
    drone.smart_sleep(1)

    print(">>> Tourner 90 degrés vers la droite")
    drone.fly_direct(roll=0, pitch=0, yaw=100,
                     vertical_movement=0, duration=DUREE_VIRAGE_90)
    drone.smart_sleep(1)

    print(">>> Reculer 30 cm")
    drone.fly_direct(roll=0, pitch=-PUISSANCE, yaw=0,
                     vertical_movement=0, duration=DUREE_30CM)
    drone.smart_sleep(1)

    print(">>> Atterrissage")
    drone.safe_land(10)
    drone.smart_sleep(2)

    drone.disconnect()
    print("Mission accomplie !")


if __name__ == "__main__":
    modele = MODELE.lower().strip()

    if modele == "bebop":
        vol_bebop()
    elif modele == "mambo":
        vol_mambo()
    else:
        print(f"Modèle inconnu : '{MODELE}'. Choisissez 'bebop' ou 'mambo'.")
        sys.exit(1)
