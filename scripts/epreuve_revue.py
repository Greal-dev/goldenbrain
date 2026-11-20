"""Épreuve réelle (hors porte, quelques centimes) : revue planifiée de cohérence.

Usage : python scripts/epreuve_revue.py <dépôt> <dossier-temporaire> [attente-s].
Serveur réel sur port libre, vault temporaire, harnais claude modèle haiku ; jamais le vrai vault.
Attendu : rien avant l'échéance (heure = maintenant + 2 min), une revue à l'échéance, résultat
(statut, fiche, propositions) enregistré, `etat/jardinage.json` à jour, pas de seconde revue."""
import datetime as dt, json, os, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path

DEPOT, BASE = Path(sys.argv[1]), Path(sys.argv[2])
ATTENTE = int(sys.argv[3]) if len(sys.argv) > 3 else 420
PY = sys.executable
shutil.rmtree(BASE, ignore_errors=True)
vault, travail = BASE / "vault", BASE / "travail"
cont = vault / "Projets" / "P-essai" / "taches"
cont.mkdir(parents=True)
travail.mkdir(parents=True)
(vault / "Projets" / "P-essai" / "contexte.md").write_text(
    "---\ntype: contexte\nnom: Essai\ncasquette: META\n---\n# Essai\n", "utf-8")
for nom in ("compta-asso", "compta-asso-doublon"):
    (cont / f"{nom}.md").write_text(
        f"---\ntype: tache\ncasquette: META\nprojet: P-essai\nstatut: a-faire\n---\n# Déclarer la compta de l'association ({nom})\n", "utf-8")
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
echeance = (dt.datetime.now() + dt.timedelta(minutes=2)).replace(second=0, microsecond=0)
(BASE / "etat").mkdir(parents=True)
# Dernière revue = maintenant : la seule échéance due est celle de dans deux minutes.
(BASE / "etat" / "jardinage.json").write_text(
    json.dumps({"derniere": dt.datetime.now().isoformat(timespec="seconds")}), "utf-8")
cfg = (DEPOT / "config.exemple.toml").read_text("utf-8")
cfg = cfg.replace("port = 8300", f"port = {port}")
cfg = cfg.replace('racine = "~/Documents/Vault"           # « ~ » = dossier personnel', f'racine = "{vault.as_posix()}"')
cfg = cfg.replace('# dossier = "~"                       # dossier', f'dossier = "{travail.as_posix()}"            # dossier', 1)
cfg = cfg.replace('arguments = ["--dangerously-skip-permissions"]',
                  'arguments = ["--dangerously-skip-permissions", "--model", "haiku"]')
cfg = cfg.replace('rythme = "a-la-demande"', 'rythme = "quotidien"').replace('heure = "07:30"', f'heure = "{echeance:%H:%M}"')
(BASE / "config.toml").write_text(cfg, "utf-8")
env = {**os.environ, "ORCH_CONFIG": str(BASE / "config.toml")}
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
    print("port", port, "échéance", f"{echeance:%H:%M}", "jardinage", req("GET", "/jardinage"), flush=True)
    debut, dernier, tache = time.time(), None, None
    while time.time() - debut < ATTENTE:
        j = req("GET", "/jardinage")
        tache = j["tache"]
        t = req("GET", f"/taches/{tache}") if tache else {}
        etat = (j["derniere"], tache, t.get("statut"), t.get("etat_execution"))
        if etat != dernier:
            print(dt.datetime.now().strftime("%H:%M:%S"), etat, flush=True); dernier = etat
        if tache and t.get("etat_execution") not in ("en_cours", "en_file", None) and dt.datetime.now() > echeance:
            break
        time.sleep(5)
    if tache:
        print("FICHE", json.dumps(req("GET", f"/taches/{tache}").get("fiche"), ensure_ascii=False, indent=1))
    print("PROPOSITIONS", json.dumps(req("GET", "/propositions"), ensure_ascii=False)[:1500])
    print("ETAT", (BASE / "etat" / "jardinage.json").read_text("utf-8") if (BASE / "etat" / "jardinage.json").exists() else None)
finally:
    srv.terminate()
