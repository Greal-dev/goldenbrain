"""Dossier de travail d'une tâche : la racine du dépôt de code de son projet.

Rôle : un projet du vault déclare son dépôt (clé `depot:` de son `contexte.md`, à défaut la
table `<vault>/_meta/projets-externes.md`, colonnes `| dépôt | casquette | projet |`) ; tout tour
d'une tâche de ce projet ou de ses descendants s'exécute dans ce dossier, pour tous les harnais.
Frontières : lecture seule du vault ; ne lance rien. Le repli (dossier du harnais) reste au moteur.
Invariants portés : INV-DEPOT-1, INV-INTEG-2 (clé `integration:`).
"""

from __future__ import annotations

from pathlib import Path

from . import arbre

TABLE = "_meta/projets-externes.md"


def _table(vault) -> list[tuple[str, str]]:
    """(dépôt, projet) des lignes de la table ; absente ou illisible : vide."""
    try:
        lignes = (vault.racine / TABLE).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []
    out = []
    for ligne in lignes:
        cases = [c.strip() for c in ligne.strip().strip("|").split("|")]
        if ligne.lstrip().startswith("|") and len(cases) >= 3 and cases[2] and (":" in cases[0] or cases[0].startswith("/")):
            out.append((cases[0], cases[2]))
    return out


def _existe(chemin: str) -> str | None:
    p = Path(chemin.strip().strip('"'))
    return str(p) if p.is_dir() else None


def contextes(vault, ident: str) -> list[tuple[str, dict]]:
    """(conteneur, frontmatter de son `contexte.md`), du conteneur de la tâche vers la casquette.
    Partagé par le dossier de travail (INV-DEPOT-1) et le contrôle requis (INV-CONTROLE-1)."""
    t = vault.tache(ident)
    s = arbre.structure(vault, vault.index())
    cid, out = t.conteneur, []
    while cid is not None and cid in s.noeuds:
        n = s.noeuds[cid]
        if n.type == "conteneur":
            try:
                fm = vault._lire_meta(vault.racine / n.id / vault.cfg.contexte)[0]
            except OSError:
                fm = {}
            out.append((n.id, fm))
        cid = n.parent
    return out


def dossier_de_travail(vault, ident: str) -> tuple[str | None, str]:
    """INV-DEPOT-1 : (dossier, origine) ; `(None, "")` sans dépôt déclaré ou existant.

    On remonte du conteneur de la tâche vers la casquette : le conteneur le plus proche qui
    déclare un dépôt l'emporte. Un `depot:` qui ne désigne pas un dossier existant est ignoré
    (repli, jamais un tour lancé dans un dossier fantôme)."""
    t = vault.tache(ident)
    table = _table(vault)
    for c, fm in contextes(vault, ident):
        if (d := fm.get("depot")) and (ok := _existe(str(d))):
            return ok, f"depot: de {c}"
        slug = c.rsplit("/", 1)[-1].casefold()
        for chemin, projet in table:
            if projet.casefold() in (slug, str(t.fm.get("projet") or "").casefold()) \
                    and (ok := _existe(chemin)):
                return ok, f"{TABLE} ({projet})"
    return None, ""


def conf_harnais(vault, conf: dict, ident: str) -> dict:
    """Section `[harnais.<nom>]` dont le `dossier` est celui du dépôt du projet, s'il y en a un."""
    d, _ = dossier_de_travail(vault, ident)
    return {**conf, "dossier": d} if d else conf


def integration(vault, ident: str) -> str | None:
    """INV-INTEG-2 : tâche d'intégration déclarée (`integration:` du `contexte.md`), conteneur le plus proche."""
    for _, fm in contextes(vault, ident):
        if c := str(fm.get("integration") or "").strip():
            return c
    return None
