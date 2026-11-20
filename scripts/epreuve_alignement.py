"""Épreuve réelle (hors porte) : alignement d'un dossier sur une COPIE partielle du vault.

Usage : python scripts/epreuve_alignement.py <dépôt> <dossier-temporaire> [vault-source]
Copie quelques projets et leurs liens du vault source (lecture seule) dans <dossier-temporaire>, en fait
un dépôt git, lance le vrai serveur sur un port libre et joue : écarts, plan, application, deuxième
passage (idempotence), geste d'arbre (projet déplacé sous un autre). Vérifie que le vault source est intact
(hachage avant/après des fichiers copiés)."""
import hashlib, json, os, shutil, socket, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

DEPOT, BASE = Path(sys.argv[1]), Path(sys.argv[2])
SOURCE = Path(sys.argv[3]) if len(sys.argv) > 3 else Path.home() / "Documents" / "Vault"
# Copie et geste d'arbre désignés hors du dépôt (INV-PUB-1) : COPIES="Projets/A,Projets/B,Casquettes/C1-X",
# GESTE="Projets/B>Projets/A" (B passe sous A). Défaut : tout `Projets`, sans geste.
COPIES = ["Projets"]
PY = sys.executable
if os.environ.get("COPIES"):  # large : COPIES="Projets,Casquettes,_meta/annuaire.md,memory.md"
    COPIES = os.environ["COPIES"].split(",")
TOUS = bool(os.environ.get("TOUS"))  # TOUS=1 : applique tous les écarts sans conflit en un plan


def empreinte(racine: Path, rels) -> str:
    h = hashlib.sha256()
    for rel in rels:
        p = racine / rel
        for f in sorted([p] if p.is_file() else p.rglob("*")):
            if f.is_file():
                h.update(f.relative_to(racine).as_posix().encode() + f.read_bytes())
    return h.hexdigest()


avant = empreinte(SOURCE, COPIES)
shutil.rmtree(BASE, ignore_errors=True)
vault = BASE / "vault"
for rel in COPIES:
    s, d = SOURCE / rel, vault / rel
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(s, d, ignore=shutil.ignore_patterns(".git", ".claude")) if s.is_dir() else shutil.copy2(s, d)
for c in (["init", "-q"], ["config", "user.name", "essai"], ["config", "user.email", "e@e"], ["add", "-A"],
          ["commit", "-q", "-m", "copie"]):
    subprocess.run(["git", *c], cwd=vault, check=True, capture_output=True)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
cfg = (DEPOT / "config.exemple.toml").read_text("utf-8").replace("port = 8300", f"port = {port}")
cfg = cfg.replace('racine = "~/Documents/Vault"           # « ~ » = dossier personnel', f'racine = "{vault.as_posix()}"')
if os.environ.get("APRES"):  # commande alignement.apres à éprouver
    cfg = cfg.replace('apres = ""', "apres = " + json.dumps(os.environ["APRES"]))
(BASE / "config.toml").write_text(cfg, "utf-8")
env = {**os.environ, "ORCH_CONFIG": str(BASE / "config.toml")}
srv = subprocess.Popen([PY, "-c", f"import sys,runpy; sys.path.insert(0, r'{DEPOT}/src'); runpy.run_module('orchestrateur', run_name='__main__')"],
                       env=env, stdout=open(BASE / "serveur.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
U = f"http://127.0.0.1:{port}/api"


def req(m, p, d=None):
    r = urllib.request.Request(U + p, method=m, data=json.dumps(d).encode() if d is not None else None,
                               headers={"Content-Type": "application/json", "X-Orchestrateur": "1"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=120).read() or b"null")
    except urllib.error.HTTPError as e:
        return {"HTTP": e.code, "corps": e.read().decode()[:600]}


def montrer(titre, v):
    v = {k: x for k, x in v.items() if k != "arbre"} if isinstance(v, dict) else v
    print(f"--- {titre}\n{json.dumps(v, ensure_ascii=False, indent=1)[:1800]}", flush=True)


try:
    for _ in range(40):
        try: req("GET", "/etat"); break
        except Exception: time.sleep(0.5)
    ecarts = req("GET", "/alignement"); montrer("écarts de la copie", ecarts); t0 = time.time()
    libres = [e["conteneur"] for e in ecarts if not e.get("conflit")] if isinstance(ecarts, list) else []
    if libres:
        plan = req("POST", "/alignement/plan", {"conteneurs": libres if TOUS else libres[:1]}); montrer("plan", plan)
        if "jeton" in plan:
            print("durée plan", round(time.time() - t0, 1), "s"); montrer("application", req("POST", "/alignement/appliquer", {"jeton": plan["jeton"], "point_git": True}))
    # Geste d'arbre : un projet passe sous un autre (INV-ARBRE-2 : planifié puis appliqué par l'alignement).
    noeud, _, sous = os.environ.get("GESTE", "").partition(">")
    plan = req("POST", "/arbre/plan", {"noeud": noeud, "sous": sous}) if sous else {}; montrer("plan du geste", plan)
    if "jeton" in plan:
        montrer("application du geste", req("POST", "/alignement/appliquer", {"jeton": plan["jeton"], "point_git": True}))
    montrer("écarts après", req("GET", "/alignement"))
    print("git log:", subprocess.run(["git", "log", "--oneline"], cwd=vault, capture_output=True, text=True, encoding="utf-8").stdout)
    print("git status:", subprocess.run(["git", "status", "--short"], cwd=vault, capture_output=True, text=True, encoding="utf-8").stdout[:800])
finally:
    srv.terminate()
apres = empreinte(SOURCE, COPIES)
time.sleep(2); print("marqueur apres :", (vault / "marqueur.txt").exists())
print("vault source intact :", avant == apres)
print("fin d'épreuve ; copie dans", vault)
