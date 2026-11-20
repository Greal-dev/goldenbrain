@echo off
rem Python : premiere ligne de python.local (non suivi, chemin de l'interpreteur), sinon python du PATH.
set "PY=python"
if exist "%~dp0python.local" set /p PY=<"%~dp0python.local"
rem Met GoldenBrain a jour depuis la branche de diffusion (avance rapide seulement), puis redemarre le serveur s'il tourne.
rem Le Python embarque ignore PYTHONPATH et le dossier courant : src est ajoute explicitement.
"%PY%" -c "import sys, runpy; sys.path.insert(0, r'%~dp0src'); runpy.run_module('orchestrateur.mise_a_jour', run_name='__main__')"
set code=%errorlevel%
rem Double-clic : la fenetre reste ouverte pour lire le resultat ; « mettre-a-jour.cmd sans-pause » l'evite.
if /i not "%~1"=="sans-pause" pause
exit /b %code%
