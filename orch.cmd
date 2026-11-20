@echo off
rem Python : premiere ligne de python.local (non suivi, chemin de l'interpreteur), sinon python du PATH.
set "PY=python"
if exist "%~dp0python.local" set /p PY=<"%~dp0python.local"
"%PY%" "%~dp0orch.py" %*
