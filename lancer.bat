@echo off
title Drone Mambo
color 0A

echo.
echo  ========================================
echo    DRONE MAMBO - Demarrage
echo  ========================================
echo.

REM Aller dans le dossier du script
cd /d "%~dp0"

REM Mise a jour depuis GitHub
echo  Mise a jour en cours...
git pull origin claude/gallant-maxwell-piDzj
echo.

REM Verifier que Python est installe
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERREUR : Python n est pas installe !
    echo  Allez sur https://www.python.org/downloads/
    pause
    exit
)

REM Installer les librairies manquantes si besoin
python -c "import bleak" >nul 2>&1
if errorlevel 1 (
    echo  Installation de bleak...
    pip install bleak
)

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo  Installation de flask...
    pip install flask
)

echo.
echo  Allumez votre Mambo puis cliquez Connecter dans le navigateur !
echo  Fermez cette fenetre pour arreter le serveur.
echo.

REM Ouvrir le navigateur apres 2 secondes (pendant que le serveur demarre)
start "" cmd /c "timeout /t 2 >nul && start http://localhost:5000"

REM Lancer le serveur (bloque ici jusqu a fermeture)
python serveur_drone.py

pause
