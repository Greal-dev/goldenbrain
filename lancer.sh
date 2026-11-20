#!/usr/bin/env bash
# Lance GoldenBrain (équivalent Linux de lancer.cmd) : http://127.0.0.1:8300
# Python : première ligne de python.local (non suivi), sinon python3 du PATH.
cd "$(dirname "$0")" || exit 1
PY=python3
[ -f python.local ] && read -r PY < python.local
# Premier lancement : crée config.toml (vos écarts seulement).
[ -f config.toml ] || cp config.depart.toml config.toml
# Adresse annoncée : le port de config.toml s'il y est réglé (installation à blanc, 19/11).
PORT=$(sed -n 's/^port *= *\([0-9]*\).*/\1/p' config.toml | head -n 1)
echo "GoldenBrain : http://127.0.0.1:${PORT:-8300}"
while true; do
    "$PY" -c "import sys, runpy; sys.path.insert(0, 'src'); runpy.run_module('orchestrateur', run_name='__main__')"
    code=$?
    # Code de sortie 3 = redémarrage demandé depuis l'interface (INV-VERSION-1) : on relance.
    [ "$code" -eq 3 ] && continue
    # INV-MAJ-3 : une mise à jour automatique laisse .maj_retour (version précédente), supprimé par tout démarrage réussi ;
    # s'il reste, le serveur relancé n'a pas démarré : on rétablit cette version et on relance.
    if [ "$code" -ne 0 ] && [ -f .maj_retour ]; then
        read -r ancienne < .maj_retour
        unlink .maj_retour
        if [[ "$ancienne" =~ ^[0-9a-f]{7,40}$ ]] && git reset --hard --quiet "$ancienne"; then
            echo "Mise à jour automatique en échec : version $ancienne rétablie."
            continue
        fi
    fi
    exit "$code"
done
