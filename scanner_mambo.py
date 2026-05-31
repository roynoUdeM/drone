#!/usr/bin/env python3
"""
Trouve l'adresse Bluetooth BLE de votre Parrot Mambo.
Copiez l'adresse affichée dans MAMBO_ADDR dans vol_programme.py.

Prérequis système :
  sudo apt install bluetooth bluez   (Linux)
  pip install bleak
"""

import asyncio
import sys


async def scanner():
    try:
        from bleak import BleakScanner
    except ImportError:
        print("La librairie 'bleak' n'est pas installée.")
        print("Lancez :  pip install bleak")
        sys.exit(1)

    print("Recherche des appareils Bluetooth BLE (10 secondes)...")
    print("Allumez votre Mambo maintenant.\n")

    devices = await BleakScanner.discover(timeout=10.0)

    mambo_trouves = []
    autres = []

    for d in devices:
        nom = d.name or ""
        if "Mambo" in nom or "mambo" in nom or "MAMBO" in nom:
            mambo_trouves.append(d)
        else:
            autres.append(d)

    if mambo_trouves:
        print("=== Mambo(s) détecté(s) ===")
        for d in mambo_trouves:
            print(f"  Nom     : {d.name}")
            print(f"  Adresse : {d.address}  ← copiez cette valeur dans MAMBO_ADDR")
            print()
    else:
        print("Aucun Mambo détecté.")
        print("Vérifiez que le drone est allumé et proche de votre ordinateur.\n")
        if autres:
            print("Appareils BLE trouvés (peut-être votre drone sous un autre nom) :")
            for d in autres:
                print(f"  {d.address}  —  {d.name or '(sans nom)'}")


if __name__ == "__main__":
    asyncio.run(scanner())
