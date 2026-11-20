"""Dictionnaires de langue (INV-LANGUE-1) : contrôle de la porte et outil des traducteurs.

Rôle : vérifier que `web/langues/{fr,en,de,es}.json` ont exactement les mêmes clés et les mêmes paramètres `{x}`,
que toute clé citée par le code existe, et qu'aucun libellé visible n'est codé en dur dans `web/` (hors
exceptions motivées de `scripts/langues_exceptions.txt`). Fusionner un lot de traductions dans les quatre fichiers.
Frontières : ne traduit rien ; n'écrit que les dictionnaires (commande `ajouter`, `normaliser`).
Usage : python scripts/dictionnaires.py controle | reste [web/x.js …] | ajouter <lot.json> | normaliser
  lot.json : {"cle": {"fr": "…", "en": "…", "de": "…", "es": "…"}, …}
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
WEB = RACINE / "web"
DOSSIER = WEB / "langues"
LANGUES = ("fr", "en", "de", "es")
EXCEPTIONS = RACINE / "scripts" / "langues_exceptions.txt"
PARAM = re.compile(r"\{(\w+)\}")
# Mots isolés qui ne se traduisent pas : noms propres, touches du clavier, noms techniques du navigateur.
INVARIABLES = {
    "GoldenBrain", "Telegram", "Claude", "Codex", "OpenCode", "Copilot", "Antigravity", "GitHub", "Gemini", "Markdown",
    "Enter", "Escape", "Tab", "Backspace", "Delete", "Home", "End", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
    "PageUp", "PageDown", "Shift", "Control", "Meta", "Alt", "AbortError", "Content-Type", "Accept", "Linux", "Windows",
    "Debian", "Python", "Playwright", "Fable", "Opus", "Sonnet", "Haiku", "OK", "Claude Code", "Mistral", "Ollama",
}
ACCENT = re.compile(r"[À-ÖØ-öø-ÿŒœ’«»…]")


def lire(code: str) -> dict[str, str]:
    return json.loads((DOSSIER / f"{code}.json").read_text(encoding="utf-8"))


def ecrire(code: str, d: dict[str, str]) -> None:
    texte = json.dumps(dict(sorted(d.items())), ensure_ascii=False, indent=1) + "\n"
    (DOSSIER / f"{code}.json").write_text(texte, encoding="utf-8", newline="\n")


def parite() -> list[str]:
    """Mêmes clés et mêmes paramètres `{x}` dans les quatre langues ; aucun texte vide."""
    dicos = {c: lire(c) for c in LANGUES}
    source = dicos["fr"]
    erreurs = []
    for code, d in dicos.items():
        erreurs += [f"langues/{code}.json : clé « {k} » absente (présente en fr)" for k in sorted(source.keys() - d.keys())]
        erreurs += [f"langues/{code}.json : clé « {k} » en trop (absente de fr)" for k in sorted(d.keys() - source.keys())]
        for k in sorted(source.keys() & d.keys()):
            if not str(d[k]).strip():
                erreurs.append(f"langues/{code}.json : « {k} » vide")
            elif set(PARAM.findall(d[k])) != set(PARAM.findall(source[k])):
                erreurs.append(f"langues/{code}.json : « {k} » n'a pas les paramètres de fr {sorted(set(PARAM.findall(source[k])))}")
    return erreurs


APPEL_HTML = re.compile(r"""data-t(?:-[a-z-]+)?="([\w.-]+)\"""")
APPEL_PY = re.compile(r"""\bt\(\s*["']([\w.-]+)["']""")


def cles_citees() -> dict[str, str]:
    """Clé → premier fichier qui la cite (t(), tn(), data-t*, langues.t côté serveur)."""
    citees: dict[str, str] = {}
    for f in sorted(WEB.glob("*.js")) + sorted(WEB.glob("*.html")):
        texte = f.read_text(encoding="utf-8")
        if f.suffix == ".html":
            for k in APPEL_HTML.findall(texte):
                citees.setdefault(k, f.name)
            continue
        # Clé = littéral entier passé à t()/tn() ; une clé calculée (`statut.${x}`) échappe au contrôle.
        for _, k, sorte in litteraux(texte):
            if sorte and re.fullmatch(r"[\w.-]+", k) and "." in k:
                for c in ((f"{k}.un", f"{k}.plusieurs") if sorte == "tn" else (k,)):
                    citees.setdefault(c, f.name)
    for f in sorted((RACINE / "src").rglob("*.py")):
        texte = f.read_text(encoding="utf-8")
        if "langues" in texte:
            for k in APPEL_PY.findall(texte):
                citees.setdefault(k, f.name)
    return citees


def cles_manquantes() -> list[str]:
    fr = lire("fr")
    return [f"{f} : clé « {k} » absente de langues/fr.json" for k, f in sorted(cles_citees().items()) if k not in fr]


# --- Libellés codés en dur -------------------------------------------------------------------------------------
REGEX_AVANT = set("(,=:[!&|?{};+-*%<>~^") | {""}


def litteraux(src: str):
    """(ligne, texte statique, est_cle) de chaque littéral chaîne d'un source JS, commentaires et regex exclus.

    Les gabarits `…${expr}…` rendent leur texte statique (expressions remplacées par un espace) et leurs
    expressions sont analysées à leur tour. `est_cle` : « t » ou « tn » si premier argument de t()/tn(), sinon vide.
    """
    i, n, ligne, dernier = 0, len(src), 1, ""
    while i < n:
        c = src[i]
        if c == "\n":
            ligne += 1
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            ligne += src.count("\n", i, j)
            i = j
            continue
        if c == "/" and (dernier in REGEX_AVANT or re.search(r"\b(return|typeof|case|of|in)\s*$", src[max(0, i - 8):i])):
            j, classe = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    classe = True
                elif src[j] == "]":
                    classe = False
                elif src[j] == "/" and not classe:
                    break
                j += 1
            i, dernier = j + 1, "x"
            continue
        if c in "'\"`":
            debut_ligne = ligne
            m = re.search(r"(?<![\w.$])(tn?)\(\s*$", src[max(0, i - 6):i])
            est_cle = m.group(1) if m else ""
            j, morceaux, exprs = i + 1, [], []
            while j < n and src[j] != c:
                if src[j] == "\\":
                    morceaux.append(src[j:j + 2])
                    j += 2
                    continue
                if c == "`" and src.startswith("${", j):
                    k, prof = j + 2, 1
                    while k < n and prof:
                        prof += {"{": 1, "}": -1}.get(src[k], 0)
                        k += 1
                    exprs.append((ligne, src[j + 2:k - 1]))
                    morceaux.append(" ")
                    j = k
                    continue
                if src[j] == "\n":
                    ligne += 1
                morceaux.append(src[j])
                j += 1
            yield debut_ligne, "".join(morceaux), est_cle
            for l0, e in exprs:
                for l, txt, cle in litteraux(e):
                    yield l0 + l - 1, txt, cle
            i, dernier = j + 1, "x"
            continue
        if not c.isspace():
            dernier = c if not (c.isalnum() or c in "_$)]") else "x"
            if c.isalnum() or c == "_":
                m = re.match(r"[\w$]+", src[i:])
                mot = m.group(0)
                dernier = "" if mot in ("return", "typeof", "case", "of", "in", "else", "do") else "x"
                i += len(mot)
                continue
        i += 1


def visible(texte: str) -> bool:
    """Heuristique : texte destiné à l'œil — accent ou guillemet français, mot à majuscule initiale (« Valider »,
    « Nouvelle tâche »), ou trois mots en minuscules sans signe technique. Le reste passe pour un identifiant."""
    t = texte.strip()
    if not re.search(r"[A-Za-zÀ-ÿ]{2}", t) or t.startswith(("/", "./", "#", "http", "data:")) or t in INVARIABLES:
        return False
    if ACCENT.search(t):
        return True
    if re.match(r"[A-Z][a-z]", t):
        return " " in t or bool(re.fullmatch(r"[A-Z][a-z]+[.!?:]?", t))
    if re.fullmatch(r"[a-z0-9\s,'?!.:]+", t):
        return len(re.findall(r"\b[a-z]{2,}\b", t)) >= 3 and not re.search(r"\w[.:]\w", t)
    return False


def exceptions() -> set[tuple[str, str]]:
    """`fichier | littéral | motif` par ligne ; # en tête : commentaire."""
    if not EXCEPTIONS.is_file():
        return set()
    sortie = set()
    for l in EXCEPTIONS.read_text(encoding="utf-8").splitlines():
        if l.strip() and not l.startswith("#"):
            f, lit, *_ = [x.strip() for x in l.split(" | ")]
            sortie.add((f, lit))
    return sortie


class _Html(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pile, self.trouves = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in ("br", "img", "input", "meta", "link", "hr", "source"):
            self.pile.append((tag, a))
        for nom in ("title", "placeholder", "aria-label", "alt"):
            if a.get(nom) and visible(a[nom]) and f"data-t-{nom}" not in a:
                self.trouves.append((self.getpos()[0], a[nom]))

    def handle_endtag(self, tag):
        while self.pile and self.pile.pop()[0] != tag:
            pass

    def handle_data(self, data):
        if data.strip() and visible(data) and self.pile and self.pile[-1][0] not in ("script", "style", "title") \
                and "data-t" not in self.pile[-1][1]:
            self.trouves.append((self.getpos()[0], data.strip()))


def en_dur(fichiers: list[Path] | None = None) -> list[str]:
    """Libellés visibles hors dictionnaire dans web/*.js et web/*.html (exceptions motivées retirées)."""
    excl = exceptions()
    sortie = []
    if fichiers is None:
        fichiers = sorted(WEB.glob("*.js")) + sorted(WEB.glob("*.html"))
    for f in fichiers:
        texte = f.read_text(encoding="utf-8")
        if f.suffix == ".html":
            p = _Html()
            p.feed(texte)
            trouves = p.trouves
        else:
            trouves = [(l, s) for l, s, cle in litteraux(texte) if not cle and visible(s)]
        sortie += [f"web/{f.name}:{l} : libellé en dur « {s[:80]} »" for l, s in trouves if (f.name, s) not in excl]
    return sortie


def controles() -> list[str]:
    """INV-LANGUE-1 : parité des quatre dictionnaires, clés citées existantes, aucun libellé en dur."""
    return parite() + cles_manquantes() + en_dur()


def ajouter(lot: Path) -> None:
    donnees = json.loads(lot.read_text(encoding="utf-8"))
    dicos = {c: lire(c) for c in LANGUES}
    for cle, textes in donnees.items():
        manque = [c for c in LANGUES if c not in textes]
        if manque:
            raise SystemExit(f"{cle} : langue(s) manquante(s) {manque}")
        for c in LANGUES:
            dicos[c][cle] = textes[c]
    for c, d in dicos.items():
        ecrire(c, d)


def main(args: list[str]) -> int:
    cmd = args[0] if args else "controle"
    if cmd == "ajouter":
        ajouter(Path(args[1]))
        erreurs = parite()
    elif cmd == "normaliser":
        for c in LANGUES:
            ecrire(c, lire(c))
        erreurs = parite()
    elif cmd == "reste":
        erreurs = en_dur([RACINE / a for a in args[1:]] or None)
    else:
        erreurs = controles()
    for e in erreurs:
        print(e)
    print(f"{len(erreurs)} écart(s)")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
