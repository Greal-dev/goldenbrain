#!/usr/bin/env bash
# GoldenBrain — installation en une commande (Linux, macOS), sans Python préinstallé :
#   curl -fsSL https://github.com/Greal-dev/goldenbrain/raw/main/installation/installer.sh | bash
# Rôle : récupère l'application (git), un Python 3.12 portable vérifié par empreinte, ses
# dépendances épinglées, puis crée l'entrée de menu (Linux) ou l'application (macOS) et lance.
# Frontières : tout s'installe dans le dossier de l'utilisateur, sans droits administrateur ;
# une copie existante de l'application n'est jamais remplacée (INV-PAQUET-1).
# Réglages facultatifs : GB_DEPOT, GB_BRANCHE, GB_DONNEES, GB_SANS_LANCEMENT=1.
set -euo pipefail

# Langue du système (fr, en, de, es ; anglais sinon).
langue() {
    local l=${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}
    if [ -z "$l" ] || [ "$l" = C ] || [ "$l" = POSIX ]; then
        l=$(defaults read -g AppleLocale 2>/dev/null || true)
    fi
    case "$l" in fr*) echo fr ;; de*) echo de ;; es*) echo es ;; *) echo en ;; esac
}

# Libellés visibles, regroupés pour la traduction.
case "$(langue)" in
fr)
    MSG_GIT_LINUX="Git est nécessaire (il sert aussi aux mises à jour). Installez-le, puis relancez cette commande : sudo apt install git (Debian, Ubuntu) ou sudo dnf install git (Fedora)."
    MSG_GIT_MAC="Git est nécessaire (il sert aussi aux mises à jour). Acceptez l'installation des outils proposée par macOS, puis relancez cette commande."
    MSG_SYSTEME="Système non pris en charge par l'installation automatique :"
    MSG_EMPREINTE="Téléchargement altéré (empreinte inattendue) :"
    MSG_ETAPE_APP="1/4 Récupération de GoldenBrain…"
    MSG_ETAPE_PY="2/4 Installation de Python (portable, réservé à GoldenBrain)…"
    MSG_ETAPE_DEP="3/4 Installation des composants…"
    MSG_ETAPE_RACC="4/4 Création du raccourci…"
    MSG_FIN="GoldenBrain est installé. Pour le relancer : menu des applications → GoldenBrain, ou la commande" ;;
de)
    MSG_GIT_LINUX="Git wird benötigt (auch für Updates). Installieren Sie es und führen Sie diesen Befehl erneut aus: sudo apt install git (Debian, Ubuntu) oder sudo dnf install git (Fedora)."
    MSG_GIT_MAC="Git wird benötigt (auch für Updates). Bestätigen Sie die von macOS angebotene Installation der Werkzeuge und führen Sie diesen Befehl dann erneut aus."
    MSG_SYSTEME="Dieses System wird von der automatischen Installation nicht unterstützt:"
    MSG_EMPREINTE="Beschädigter Download (unerwartete Prüfsumme):"
    MSG_ETAPE_APP="1/4 GoldenBrain wird heruntergeladen…"
    MSG_ETAPE_PY="2/4 Python wird installiert (portabel, nur für GoldenBrain)…"
    MSG_ETAPE_DEP="3/4 Komponenten werden installiert…"
    MSG_ETAPE_RACC="4/4 Verknüpfung wird erstellt…"
    MSG_FIN="GoldenBrain ist installiert. Erneut starten: Anwendungsmenü → GoldenBrain, oder mit dem Befehl" ;;
es)
    MSG_GIT_LINUX="Se necesita Git (también para las actualizaciones). Instálelo y vuelva a ejecutar este comando: sudo apt install git (Debian, Ubuntu) o sudo dnf install git (Fedora)."
    MSG_GIT_MAC="Se necesita Git (también para las actualizaciones). Acepte la instalación de herramientas que propone macOS y vuelva a ejecutar este comando."
    MSG_SYSTEME="Sistema no compatible con la instalación automática:"
    MSG_EMPREINTE="Descarga alterada (huella inesperada):"
    MSG_ETAPE_APP="1/4 Descargando GoldenBrain…"
    MSG_ETAPE_PY="2/4 Instalando Python (portátil, solo para GoldenBrain)…"
    MSG_ETAPE_DEP="3/4 Instalando los componentes…"
    MSG_ETAPE_RACC="4/4 Creando el acceso directo…"
    MSG_FIN="GoldenBrain está instalado. Para volver a iniciarlo: menú de aplicaciones → GoldenBrain, o el comando" ;;
*)
    MSG_GIT_LINUX="Git is required (it is also used for updates). Install it, then run this command again: sudo apt install git (Debian, Ubuntu) or sudo dnf install git (Fedora)."
    MSG_GIT_MAC="Git is required (it is also used for updates). Accept the tools installation offered by macOS, then run this command again."
    MSG_SYSTEME="System not supported by the automatic installation:"
    MSG_EMPREINTE="Corrupted download (unexpected checksum):"
    MSG_ETAPE_APP="1/4 Downloading GoldenBrain…"
    MSG_ETAPE_PY="2/4 Installing Python (portable, for GoldenBrain only)…"
    MSG_ETAPE_DEP="3/4 Installing components…"
    MSG_ETAPE_RACC="4/4 Creating the shortcut…"
    MSG_FIN="GoldenBrain is installed. To start it again: applications menu → GoldenBrain, or the command" ;;
esac

principal() {
    local depot=${GB_DEPOT:-https://github.com/Greal-dev/goldenbrain.git}
    local branche=${GB_BRANCHE:-main}
    local systeme cle donnees
    case "$(uname -s)-$(uname -m)" in
        Linux-x86_64) systeme=linux; cle=python-linux-x86_64 ;;
        Linux-aarch64) systeme=linux; cle=python-linux-aarch64 ;;
        Darwin-arm64) systeme=macos; cle=python-macos-arm64 ;;
        Darwin-x86_64) systeme=macos; cle=python-macos-x86_64 ;;
        *) echo "$MSG_SYSTEME $(uname -s) $(uname -m)"; exit 1 ;;
    esac
    if [ "$systeme" = macos ]; then
        donnees=${GB_DONNEES:-$HOME/Library/Application Support/GoldenBrain}
    else
        donnees=${GB_DONNEES:-${XDG_DATA_HOME:-$HOME/.local/share}/goldenbrain}
    fi
    # Sur macOS, « git » sans les outils de développement ouvre la fenêtre qui les installe.
    if ! git --version >/dev/null 2>&1; then
        if [ "$systeme" = macos ]; then xcode-select --install >/dev/null 2>&1 || true; echo "$MSG_GIT_MAC"
        else echo "$MSG_GIT_LINUX"; fi
        exit 1
    fi
    mkdir -p "$donnees"
    local app="$donnees/app"

    echo "$MSG_ETAPE_APP"
    if [ ! -d "$app" ]; then
        git clone --quiet --branch "$branche" "$depot" "$app.copie"
        mv "$app.copie" "$app"
    fi

    echo "$MSG_ETAPE_PY"
    local py="$donnees/python/bin/python3"
    if [ ! -x "$py" ]; then
        local url empreinte archive
        read -r url empreinte < <(awk -v c="$cle" '$1 == c {print $2, $3}' "$app/installation/versions.txt")
        archive=$(mktemp)
        curl -fsSL "$url" -o "$archive"
        local calcul
        if command -v sha256sum >/dev/null 2>&1; then calcul=$(sha256sum "$archive")
        else calcul=$(shasum -a 256 "$archive"); fi
        if [ "${calcul%% *}" != "$empreinte" ]; then rm -f "$archive"; echo "$MSG_EMPREINTE $url"; exit 1; fi
        rm -rf "$donnees/python"
        tar -xzf "$archive" -C "$donnees"
        rm -f "$archive"
    fi

    echo "$MSG_ETAPE_DEP"
    "$py" -m pip install --quiet --disable-pip-version-check --no-warn-script-location \
        -c "$app/installation/contraintes.txt" fastapi uvicorn PyYAML

    echo "$MSG_ETAPE_RACC"
    # Le raccourci appelle le lanceur de l'application : il suit ses mises à jour.
    local lanceur="$donnees/goldenbrain"
    printf '#!/bin/sh\nexport GB_DONNEES="%s" GB_PYTHON="%s"\nexec /bin/sh "%s/installation/goldenbrain.sh" "$@"\n' \
        "$donnees" "$py" "$app" > "$lanceur"
    chmod +x "$lanceur"
    if [ "$systeme" = macos ]; then
        local paquet="$HOME/Applications/GoldenBrain.app/Contents"
        mkdir -p "$paquet/MacOS" "$paquet/Resources"
        printf '#!/bin/sh\nexec "%s"\n' "$lanceur" > "$paquet/MacOS/GoldenBrain"
        chmod +x "$paquet/MacOS/GoldenBrain"
        "$py" -c 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import construction; construction.icns(Path(sys.argv[2]), Path(sys.argv[3]))' \
            "$app/scripts" "$app/web/icone-512.png" "$paquet/Resources/GoldenBrain.icns"
        sed 's/@VERSION@/1/' "$app/installation/Info.plist" > "$paquet/Info.plist"
    else
        mkdir -p "$HOME/.local/bin" "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
        ln -sf "$lanceur" "$HOME/.local/bin/goldenbrain"
        sed -e "s|@LANCEUR@|$lanceur|" -e "s|@ICONE@|$app/web/icone-512.png|" \
            "$app/installation/goldenbrain.desktop" \
            > "${XDG_DATA_HOME:-$HOME/.local/share}/applications/goldenbrain.desktop"
    fi
    echo "$MSG_FIN $lanceur"
    [ "${GB_SANS_LANCEMENT:-}" = 1 ] || "$lanceur"
}

# Tout le script est lu avant d'agir : un téléchargement interrompu n'exécute rien à moitié.
principal "$@"
