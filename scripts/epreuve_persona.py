"""Épreuve réelle (hors porte, coûte quelques centimes) : validation par persona avec boucle de réserves.

Usage : python scripts/epreuve_persona.py <dépôt> <dossier-temporaire>. Serveur réel sur port libre, vault
temporaire, harnais claude modèle haiku ; jamais le vrai vault. Attendu : réserve, renvoi, validation, cloture."""
import json, re, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path

DEPOT = Path(sys.argv[1])
BASE = Path(sys.argv[2])
PY = sys.executable
shutil.rmtree(BASE, ignore_errors=True)
vault, travail = BASE / "vault", BASE / "travail"
(vault / "Projets" / "P-essai" / "taches").mkdir(parents=True)
(vault / "Projets" / "P-essai" / "contexte.md").write_text(
    "---\ntype: contexte\nnom: Essai\ncasquette: META\n---\n# Essai\n", "utf-8")
travail.mkdir(parents=True)
(vault / "Projets" / "P-essai" / "taches" / "amorce.md").write_text("---\ntype: tache\ncasquette: META\nprojet: P-essai\nstatut: a-faire\n---\n# Amorce\n", "utf-8")
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
cfg = (DEPOT / "config.exemple.toml").read_text("utf-8")
cfg = cfg.replace("port = 8300", f"port = {port}")
cfg = cfg.replace('racine = "~/Documents/Vault"           # « ~ » = dossier personnel', f'racine = "{vault.as_posix()}"')
cfg = cfg.replace('mode = "humain"', 'mode = "persona"').replace('persona = "relecteur"\nboucles', 'persona = "valideur"\nboucles')
cfg = cfg.replace('# dossier = "~"                       # dossier', f'dossier = "{travail.as_posix()}"            # dossier', 1)
(BASE / "config.toml").write_text(cfg, "utf-8")
env = {**__import__("os").environ, "ORCH_CONFIG": str(BASE / "config.toml")}
srv = subprocess.Popen([PY, "-c", f"import sys,runpy; sys.path.insert(0, r'{DEPOT}/src'); runpy.run_module('orchestrateur', run_name='__main__')"],
                       env=env, stdout=open(BASE / "serveur.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
U = f"http://127.0.0.1:{port}/api"
def req(m, p, d=None):
    r = urllib.request.Request(U + p, method=m, data=json.dumps(d).encode() if d is not None else None,
                               headers={"Content-Type": "application/json", "X-Orchestrateur": "1"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read() or b"null")
try:
    for _ in range(40):
        try: req("GET", "/etat"); break
        except Exception: time.sleep(0.5)
    req("PUT", "/equipe/valideur", {"nom": "Valideur", "actif": True, "declenchement": "a-la-demande", "modele": "haiku",
        "mandat": "Tu valides une tâche déclarée terminée. Lis le fichier livrable.txt du dossier de travail (" + travail.as_posix() + "). "
                  "Règle de validation : le fichier doit contenir une ligne commençant par « Source: ». Sinon verdict reserves, avec le point : ajouter une ligne « Source: » .",
        "focus": "Présence de la ligne « Source: » dans livrable.txt."})
    t = req("POST", "/taches", {"titre": "Essai boucle de réserves", "conteneur": "Projets/P-essai", "harnais": "claude", "modele": "haiku",
        "lancer": True, "description": "Crée le fichier " + travail.as_posix() + "/livrable.txt contenant une ligne de salutation. Ne fais rien d'autre. Déclare la tâche terminée."})
    ident = t["id"]; print("tâche", ident, "port", port, flush=True)
    retour = req("GET", "/interface")["statut_retour"]  # INV-STATUT-1
    debut = time.time(); dernier = None
    while time.time() - debut < 600:
        t = req("GET", f"/taches/{ident}"); rev = req("GET", f"/taches/{ident}/revues")
        etat = (t["statut"], t.get("renvois"), [(a["persona"], a["verdict"]) for a in rev])
        if etat != dernier:
            print(round(time.time() - debut), etat, flush=True); dernier = etat
        if t["statut"] in ("cloture", retour, "bloque") and not any(a["verdict"] == "en_cours" for a in rev):
            break
        time.sleep(3)
    print("FINAL", json.dumps(req("GET", f"/taches/{ident}/revues"), ensure_ascii=False, indent=1))
    print("livrable:", (travail / "livrable.txt").read_text("utf-8") if (travail / "livrable.txt").exists() else None)
finally:
    srv.terminate()
