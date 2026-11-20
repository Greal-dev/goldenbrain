@echo off
rem Python : premiere ligne de python.local (non suivi, chemin de l'interpreteur), sinon python du PATH.
set "PY=python"
if exist "%~dp0python.local" set /p PY=<"%~dp0python.local"
rem Lance GoldenBrain et ouvre l'interface. Premier lancement : crée config.toml (vos écarts seulement).
if not exist "%~dp0config.toml" copy "%~dp0config.depart.toml" "%~dp0config.toml" >nul
start "" http://127.0.0.1:8300
:serveur
rem Le Python embarqué ignore PYTHONPATH et le dossier courant : src est ajouté explicitement.
"%PY%" -c "import sys, runpy; sys.path.insert(0, r'%~dp0src'); runpy.run_module('orchestrateur', run_name='__main__')"
rem Code de sortie 3 = redémarrage demandé depuis l'interface (INV-VERSION-1) : on relance, sans rouvrir le navigateur.
if %errorlevel%==3 goto serveur
rem INV-MAJ-3 : si le serveur relance apres une mise a jour automatique n'a pas demarre, .maj_retour (version precedente) est retabli, puis on relance.
if %errorlevel%==0 goto fin
if not exist "%~dp0.maj_retour" goto fin
set /p ANCIENNE=<"%~dp0.maj_retour"
del "%~dp0.maj_retour"
git -C "%~dp0." reset --hard --quiet %ANCIENNE% && goto serveur
:fin
