#!/bin/sh
# GoldenBrain — lanceur de l'installation « un clic » (Linux, macOS).
# Rôle : au premier lancement, recopie la graine (l'application livrée par le paquet, avec son
# historique git) dans le dossier de données de l'utilisateur, seul endroit inscriptible où la
# mise à jour peut avancer (INV-PAQUET-1) ; désigne le Python embarqué (python.local) ; démarre
# le serveur s'il ne répond pas encore ; ouvre le navigateur.
# Frontières : ne touche jamais une copie existante ; écrit config.toml seulement s'il est absent
# (langue du système) ; ne touche jamais le vault.
# Réglages facultatifs : GB_DONNEES (dossier de données), GB_GRAINE (application à recopier),
# GB_PYTHON (interpréteur), GB_NAVIGATEUR (commande qui ouvre l'adresse).
set -eu

# Langue du système (fr, en, de, es ; anglais sinon). Lancé depuis le Finder, macOS ne pose pas
# LANG : la langue vient alors de ses préférences.
langue() {
    l=${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}
    if [ -z "$l" ] || [ "$l" = C ] || [ "$l" = POSIX ]; then
        l=$(defaults read -g AppleLocale 2>/dev/null || true)
    fi
    case "$l" in fr*) echo fr ;; de*) echo de ;; es*) echo es ;; *) echo en ;; esac
}
LANGUE=$(langue)

# Libellés visibles, regroupés pour la traduction.
case "$LANGUE" in
fr)
    MSG_COPIE="GoldenBrain : première installation dans"
    MSG_DEMARRE="GoldenBrain démarre…"
    MSG_PRET="GoldenBrain est prêt :"
    MSG_ECHEC="GoldenBrain n'a pas démarré. Détail dans :"
    MSG_SANS_APP="GoldenBrain : application introuvable :" ;;
de)
    MSG_COPIE="GoldenBrain: Erstinstallation in"
    MSG_DEMARRE="GoldenBrain wird gestartet…"
    MSG_PRET="GoldenBrain ist bereit:"
    MSG_ECHEC="GoldenBrain konnte nicht gestartet werden. Details in:"
    MSG_SANS_APP="GoldenBrain: Anwendung nicht gefunden:" ;;
es)
    MSG_COPIE="GoldenBrain: primera instalación en"
    MSG_DEMARRE="GoldenBrain se está iniciando…"
    MSG_PRET="GoldenBrain está listo:"
    MSG_ECHEC="GoldenBrain no se ha iniciado. Detalles en:"
    MSG_SANS_APP="GoldenBrain: aplicación no encontrada:" ;;
*)
    MSG_COPIE="GoldenBrain: first installation in"
    MSG_DEMARRE="GoldenBrain is starting…"
    MSG_PRET="GoldenBrain is ready:"
    MSG_ECHEC="GoldenBrain did not start. Details in:"
    MSG_SANS_APP="GoldenBrain: application not found:" ;;
esac

ICI=$(cd "$(dirname "$0")" && pwd)
case "$(uname -s)" in
    Darwin) DEFAUT="$HOME/Library/Application Support/GoldenBrain"; OUVRIR=open ;;
    *) DEFAUT="${XDG_DATA_HOME:-$HOME/.local/share}/goldenbrain"; OUVRIR=xdg-open ;;
esac
DONNEES=${GB_DONNEES:-$DEFAUT}
GRAINE=${GB_GRAINE:-$ICI/app}
PY=${GB_PYTHON:-$ICI/python/bin/python3}
NAV=${GB_NAVIGATEUR:-$OUVRIR}
APP="$DONNEES/app"
JOURNAL="$DONNEES/lancement.log"

avertir() {
    echo "$1"
    # Lancé depuis le menu, sans terminal : le message doit se voir quand même.
    if command -v osascript >/dev/null 2>&1; then
        osascript -e "display dialog \"$1\" buttons {\"OK\"} with title \"GoldenBrain\"" >/dev/null 2>&1 || true
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send GoldenBrain "$1" || true
    fi
}

# INV-PAQUET-1 : la graine ne remplace jamais une copie existante (mise à jour, réglages, état).
if [ ! -d "$APP" ]; then
    if [ ! -d "$GRAINE" ]; then avertir "$MSG_SANS_APP $GRAINE"; exit 1; fi
    echo "$MSG_COPIE $APP"
    mkdir -p "$DONNEES"
    rm -rf "$APP.copie"
    cp -R "$GRAINE" "$APP.copie"
    mv "$APP.copie" "$APP"
fi
# Le paquet a pu déplacer son Python (mise à niveau) : python.local suit à chaque lancement.
printf '%s\n' "$PY" > "$APP/python.local"

# Premier lancement : les réglages de départ, avec la langue du système (l'interface s'ouvre dans
# la même langue). Seulement si cette version de GoldenBrain connaît le réglage `langue` : une
# clé inconnue l'empêcherait de démarrer. Une configuration existante n'est jamais touchée.
if [ -z "${ORCH_CONFIG:-}" ] && [ ! -f "$APP/config.toml" ] && [ -f "$APP/config.depart.toml" ] \
    && grep -q 'langue = ' "$APP/config.exemple.toml" 2>/dev/null; then
    awk -v l="$LANGUE" '{ print } $0 == "[interface]" { print "langue = \"" l "\""; vu = 1 }
        END { if (!vu) printf "\n[interface]\nlangue = \"%s\"\n", l }' \
        "$APP/config.depart.toml" > "$APP/config.toml"
fi

PORT=8300
CONFIG=${ORCH_CONFIG:-$APP/config.toml}
if [ -f "$CONFIG" ]; then
    P=$(sed -n 's/^port *= *\([0-9]*\).*/\1/p' "$CONFIG" | head -n 1)
    PORT=${P:-8300}
fi
URL="http://127.0.0.1:$PORT"

repond() {
    "$PY" -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2).close()" "$URL/" >/dev/null 2>&1
}

if ! repond; then
    echo "$MSG_DEMARRE"
    # Détaché du lanceur : le serveur survit à la fermeture du menu ou du terminal.
    nohup /bin/bash "$APP/lancer.sh" >"$JOURNAL" 2>&1 </dev/null &
    SERVEUR=$!
    n=0
    until repond; do
        n=$((n + 1))
        # Serveur déjà sorti (vault, port, Python) : inutile d'attendre la fin du délai.
        if [ "$n" -ge 90 ] || ! kill -0 "$SERVEUR" 2>/dev/null; then avertir "$MSG_ECHEC $JOURNAL"; exit 1; fi
        sleep 1
    done
fi
echo "$MSG_PRET $URL"
"$NAV" "$URL" >/dev/null 2>&1 &
