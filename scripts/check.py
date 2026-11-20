"""Gate unique : tests + contrôles de structure.

Rôle : pytest, modules ≤ 500 lignes, en-tête de module présent, tout `INV-*` cité dans `src/`
défini dans `docs/ARCHITECTURE.md`, et `docs/CODE_MAP.md` à jour (tout fichier y figure, aucun fantôme, les `INV-*`
de chaque module de `src/` sur sa ligne), et la syntaxe de chaque `web/*.js` lu comme module ES (`node --check`
sur une copie `.mjs` : en `.js`, une erreur de syntaxe d'un module passe inaperçue — chaîne coupée du 15/11),
et tout `read_text`/`write_text`/`open`/`subprocess(text=True)` sans `encoding` explicite (cp1252 sous Windows). Code de retour non nul au premier manquement.
"""

import ast
import hashlib
import shutil
import tempfile
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CONNUS = "docs/publication-connue.txt"  # INV-PUB-1 : éléments déjà recensés, en avertissement
MOTIF_INV = re.compile(r"INV-[A-Z]+-\d+")


def carte(definis: set[str]) -> list[str]:
    """Contrôle `docs/CODE_MAP.md` : couverture des fichiers, fichiers fantômes, `INV-*` par module."""
    texte = (RACINE / "docs" / "CODE_MAP.md").read_text("utf-8")
    lignes = {}
    for ligne in texte.splitlines():
        if m := re.match(r"\| `([^`]+)` \|", ligne):
            lignes[m.group(1)] = ligne
    reels = {f.relative_to(RACINE).as_posix() for d in ("src", "web", "scripts", "tests")
             for f in (RACINE / d).rglob("*") if f.is_file() and "__pycache__" not in f.parts
             and f.suffix != ".pyc"} | {"orch.py"}
    erreurs = [f"CODE_MAP : {f} absent de la carte" for f in sorted(reels - set(lignes))]
    erreurs += [f"CODE_MAP : {f} n'existe plus" for f in sorted(set(lignes) - reels)]
    for f, ligne in lignes.items():
        if f.startswith("src/") and f in reels:
            cites = set(MOTIF_INV.findall((RACINE / f).read_text("utf-8")))
            for inv in sorted(cites - set(MOTIF_INV.findall(ligne))):
                erreurs.append(f"CODE_MAP : {f} cite {inv}, absent de sa ligne")
        for inv in sorted(set(MOTIF_INV.findall(ligne)) - definis):
            erreurs.append(f"CODE_MAP : {inv} (ligne de {f}) absent de docs/ARCHITECTURE.md")
    return erreurs


# INV-PUB-1 : motifs génériques versionnés ; les motifs personnels (nom, projets…) restent hors du
# dépôt, dans `.sensible` (une expression régulière par ligne, `#` = commentaire).
MOTIFS_PUBLICS = {
    "adresse électronique": r"[\w.+-]+@(?!example\.(?:org|com|net)\b)[\w-]+(?:\.[\w-]+)+",
    "chemin personnel": r"(?:\b[a-z]:[\\/]+users|/c/users|/home)[\\/]+(?!utilisateur\b|public\b|<)[\w.-]+",
    "identifiant de session": r"\b(?!00000000-)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    "jeton": r"\bsk-[\w-]{20,}|\bghp_\w{20,}|\bgithub_pat_\w+|\bAKIA[0-9A-Z]{16}\b|\bxox[abps]-[\w-]+"
             r"|\bAIza[\w-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY-----",
}


MENTION_AUTEUR = re.compile(r"GoldenBrain — Copyright \d{4} [A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'’-]*")  # un nom, rien d'autre
DEPOT_PUBLIC = re.compile(re.escape("github.com/Greal-dev/goldenbrain"), re.I)  # adresse publique du dépôt (19/11)


def motifs_personnels() -> list[str]:
    """`.sensible` de l'arbre de travail, sinon du checkout principal (arbres `git worktree`)."""
    commun = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=RACINE, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    for dossier in (RACINE, Path(commun).parent if commun else RACINE):
        if (f := dossier / ".sensible").is_file():
            return [l.strip() for l in f.read_text("utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return []


def sensibles() -> list[str]:
    """INV-PUB-1 : aucun fichier suivi (ou à suivre) ne contient de donnée sensible."""
    personnels = motifs_personnels()
    if not personnels:  # INV-PUB-1 : une garde sans motif personnel ne cherche aucun nom propre ; le dire, pas l'ignorer
        print("AVERTISSEMENT : `.sensible` absent ou vide, aucun motif personnel contrôlé (INV-PUB-1)")
    motifs = {**MOTIFS_PUBLICS, **{f"motif personnel n°{i}": m for i, m in enumerate(personnels, 1)}}
    regex = {nom: re.compile(m, re.I) for nom, m in motifs.items()}
    sortie = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=RACINE,
                            capture_output=True)
    if sortie.returncode:
        return ["garde de publication : liste des fichiers git illisible"]
    erreurs, connus = [], recenses()
    for rel in filter(None, sortie.stdout.decode("utf-8").split("\0")):
        try:
            texte = (RACINE / rel).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # fichier binaire ou supprimé de l'arbre
        for n, ligne in enumerate(texte.splitlines(), 1):
            # INV-PUB-1 : seule mention d'auteur admise, la ligne de copyright de `NOTICE`
            # (motifs personnels levés ; motifs génériques maintenus).
            admise = rel == "NOTICE" and MENTION_AUTEUR.fullmatch(ligne.strip())
            # INV-PUB-1 : l'adresse du dépôt public est soustraite aux seuls motifs personnels.
            sans_depot = DEPOT_PUBLIC.sub("", ligne)
            trouves = [f"{rel}:{n} : {nom} (INV-PUB-1)" for nom, r in regex.items()
                       if r.search(sans_depot if nom.startswith("motif personnel") else ligne)
                       and not (admise and nom.startswith("motif personnel"))]
            # INV-PUB-1 : un élément déjà recensé (liste de référence) avertit ; seul le nouveau bloque.
            if trouves and (rel, empreinte(ligne)) in connus:
                print(*(f"AVERTISSEMENT : {e} déjà recensé ({CONNUS})" for e in trouves), sep="\n")
            else:
                erreurs += trouves
    return erreurs


def empreinte(ligne: str) -> str:
    """Empreinte d'une ligne (sans espaces de bord) : la liste de référence ne recopie aucune donnée."""
    return hashlib.sha256(ligne.strip().encode("utf-8")).hexdigest()[:16]


def recenses() -> set[tuple[str, str]]:
    """Paires (fichier, empreinte) de la liste de référence `docs/publication-connue.txt`."""
    if not (f := RACINE / CONNUS).is_file():
        return set()
    return {tuple(l.split("\t", 1)) for l in f.read_text("utf-8").splitlines()
            if l.strip() and not l.startswith("#") and "\t" in l}


def scripts_web() -> list[str]:
    """Syntaxe des modules de l'interface ; sans `node` sur le poste, le contrôle est signalé, pas sauté en silence."""
    if not (node := shutil.which("node")):
        print("CONTRÔLE : node absent, syntaxe de web/*.js non vérifiée")
        return []
    erreurs = []
    with tempfile.TemporaryDirectory() as d:
        for f in sorted((RACINE / "web").glob("*.js")):
            copie = Path(d) / (f.stem + ".mjs")
            copie.write_bytes(f.read_bytes())
            r = subprocess.run([node, "--check", str(copie)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode:
                ligne = next((x for x in r.stderr.splitlines() if "Error" in x), "erreur de syntaxe")
                erreurs.append(f"web/{f.name} : {ligne.strip()}")
    return erreurs


def _mot(appel: ast.Call, nom: str, rang: int) -> bool:
    """Argument `nom` passé par mot-clé, ou en position `rang` (None : mot-clé seul)."""
    return any(k.arg == nom for k in appel.keywords) or (rang is not None and len(appel.args) > rang)


def _texte_vrai(appel: ast.Call, nom: str) -> bool:
    return any(k.arg == nom and not (isinstance(k.value, ast.Constant) and not k.value.value)
               for k in appel.keywords)


def encodages_implicites(arbre: ast.AST) -> list[tuple[int, str]]:
    """Portabilité Windows : lecture/écriture texte sans `encoding` (le défaut est cp1252 sous Windows).

    Visés : `read_text`, `write_text`, `open` en mode texte, `subprocess` avec `text=True` ou
    `universal_newlines=True`. Un mode binaire (`b` dans le mode littéral) n'est pas visé.
    """
    trouves = []
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nom = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
        if nom == "read_text" and not _mot(n, "encoding", 0):
            trouves.append((n.lineno, "read_text() sans encoding"))
        elif nom == "write_text" and not _mot(n, "encoding", 1):
            trouves.append((n.lineno, "write_text() sans encoding"))
        elif nom == "open":
            rang = 0 if isinstance(f, ast.Attribute) else 1  # Path.open(mode) / open(fichier, mode)
            mode = n.args[rang] if len(n.args) > rang else next((k.value for k in n.keywords if k.arg == "mode"), None)
            binaire = isinstance(mode, ast.Constant) and "b" in str(mode.value)
            if not binaire and not _mot(n, "encoding", rang + 2):
                trouves.append((n.lineno, "open() en mode texte sans encoding"))
        elif nom in {"run", "Popen", "check_output", "check_call"} and not _mot(n, "encoding", None) \
                and (_texte_vrai(n, "text") or _texte_vrai(n, "universal_newlines")):
            trouves.append((n.lineno, f"{nom}(text=True) sans encoding"))
    return trouves


def encodages() -> list[str]:
    """Contrôle `encodages_implicites` sur `src/`, `scripts/`, `tests/` et `orch.py`."""
    fichiers = [RACINE / "orch.py"] + [f for d in ("src", "scripts", "tests") for f in sorted((RACINE / d).rglob("*.py"))]
    return [f"{f.relative_to(RACINE).as_posix()}:{n} : {msg} (portabilité Windows)"
            for f in fichiers for n, msg in encodages_implicites(ast.parse(f.read_text(encoding="utf-8")))]


def controles() -> list[str]:
    erreurs = sensibles()
    definis = set(MOTIF_INV.findall((RACINE / "docs" / "ARCHITECTURE.md").read_text("utf-8")))
    if not definis:
        erreurs.append("docs/ARCHITECTURE.md ne définit aucun INV-*")
    erreurs += carte(definis)
    erreurs += scripts_web()
    erreurs += encodages()
    sys.path.insert(0, str(RACINE / "scripts"))
    import dictionnaires  # INV-LANGUE-1 : quatre dictionnaires aux clés identiques, aucun libellé en dur dans web/
    erreurs += dictionnaires.controles()
    sys.path.insert(0, str(RACINE / "src"))
    from orchestrateur import guide  # INV-GUIDE-1 : section manquante au guide → porte rouge
    erreurs += guide.manquements(guide.lire())
    erreurs += guide.manquements_traduits()  # INV-LANGUE-1 : chaque guide traduit porte toutes les ancres
    for f in sorted((RACINE / "src").rglob("*.py")):
        rel = f.relative_to(RACINE).as_posix()
        texte = f.read_text("utf-8")
        if (n := len(texte.splitlines())) > 500:
            erreurs.append(f"{rel} : {n} lignes (> 500)")
        if not ast.get_docstring(ast.parse(texte)):
            erreurs.append(f"{rel} : en-tête de module absent")
        for inv in sorted(set(MOTIF_INV.findall(texte)) - definis):
            erreurs.append(f"{rel} : {inv} absent de docs/ARCHITECTURE.md")
    return erreurs


def main() -> int:
    erreurs = controles()
    for e in erreurs:
        print(f"CONTRÔLE : {e}")
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                           cwd=RACINE).returncode
    ok = not erreurs and tests == 0
    print("GATE : vert" if ok else "GATE : rouge")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
