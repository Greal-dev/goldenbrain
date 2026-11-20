@echo off
rem GoldenBrain - lanceur de l'installation "un clic" (Windows) : raccourci du menu Demarrer.
rem Premier lancement : recopie la graine (application livree, avec son historique git) dans
rem %LOCALAPPDATA%\GoldenBrain\app, seule copie que la mise a jour avance (INV-PAQUET-1) ; elle ne
rem remplace jamais une copie existante. Git embarque (MinGit) passe en tete du PATH pour la mise a jour.
setlocal
set "ICI=%~dp0"
if not defined GB_DONNEES set "GB_DONNEES=%LOCALAPPDATA%\GoldenBrain"
set "APP=%GB_DONNEES%\app"
set "PY=%ICI%python\python.exe"
rem Langue d'affichage de Windows (fr, en, de, es ; en sinon). "call" : chemin avec espaces.
set "GB_LANGUE=en"
for /f "usebackq delims=" %%L in (`call "%PY%" "%ICI%langue.py"`) do set "GB_LANGUE=%%L"
rem Libelles visibles, regroupes pour la traduction (ASCII : la console n'est pas en UTF-8).
set "MSG_COPIE=GoldenBrain: first installation in"
set "MSG_SANS_APP=GoldenBrain: application not found:"
if "%GB_LANGUE%"=="fr" (
    set "MSG_COPIE=GoldenBrain : premiere installation dans"
    set "MSG_SANS_APP=GoldenBrain : application introuvable :"
)
if "%GB_LANGUE%"=="de" (
    set "MSG_COPIE=GoldenBrain: Erstinstallation in"
    set "MSG_SANS_APP=GoldenBrain: Anwendung nicht gefunden:"
)
if "%GB_LANGUE%"=="es" (
    set "MSG_COPIE=GoldenBrain: primera instalacion en"
    set "MSG_SANS_APP=GoldenBrain: aplicacion no encontrada:"
)
set "PATH=%ICI%git\cmd;%PATH%"
if exist "%APP%\lancer.cmd" goto copie_faite
if not exist "%ICI%graine\lancer.cmd" (
    echo %MSG_SANS_APP% %ICI%graine
    pause
    exit /b 1
)
echo %MSG_COPIE% %APP%
if not exist "%GB_DONNEES%" mkdir "%GB_DONNEES%"
if exist "%APP%.copie" rmdir /s /q "%APP%.copie"
rem /H : le dossier .git (historique, indispensable a la mise a jour) peut etre cache.
xcopy "%ICI%graine" "%APP%.copie\" /E /I /H /K /Q /Y >nul || exit /b 1
move "%APP%.copie" "%APP%" >nul
:copie_faite
rem Premier lancement : reglages de depart avec la langue de Windows (jamais une config existante).
"%PY%" "%ICI%langue.py" "%APP%" >nul
rem Le paquet a pu deplacer son Python (reinstallation) : python.local suit a chaque lancement.
>"%APP%\python.local" echo %PY%
rem Deja lance : ouvrir seulement la page, sans second serveur.
"%PY%" "%ICI%deja_lance.py" "%APP%" && exit /b 0
call "%APP%\lancer.cmd"
