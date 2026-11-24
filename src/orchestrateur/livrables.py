"""Livrables : la liste des artefacts qu'une tâche a produits, chez elle et chez ses parents.

Rôle : tenir, par tâche, un bloc géré `<!-- orchestrateur:livrables -->` (même format que les lignes :
`- [x] titre · date · Moi|IA · cible`) ; relever les livrables d'une tâche — déclarés, annoncés (attendus),
et ceux que ses traces (`## Traces`) et ses lignes à document citent déjà, sans migration — ; les agréger
sur toute la descendance d'une tâche, d'un groupe, d'un projet ou d'une casquette ; ouvrir un fichier du poste.
Un livrable est un document du vault (`note`), un fichier du poste (`fichier`), une adresse (`url`), un
artefact publié (`publie:`), une branche (`branche:`) ou un commit (`commit:`).
Frontières : écrit par `Vault.reecrire` (bloc géré seul, `fiches`) ; ne lance aucun tour d'agent ; n'ouvre un
fichier que par `resultat.ouvrir_systeme`.
Invariants portés : INV-LIVRABLES-1, INV-VAULT-1.
"""

from __future__ import annotations

import os
import re
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from . import arbre, executant, fiches, langues, resultat
from .vault import Conflit, Invalide, NonTrouve, aujourdhui

TYPES = ("note", "fichier", "url", "publie", "branche", "commit")
PREFIXES = ("publie", "branche", "commit")
LONGUEUR = 2000
SECTION_TRACES = "Traces"  # = api_reflexes.SECTION (nom de structure stable)
_DOCS = re.compile(r"(?:\[\[[^\]\n]+\]\]|`[^`\n]+`)(?:, (?:\[\[[^\]\n]+\]\]|`[^`\n]+`))*")
_UN_DOC = re.compile(r"\[\[([^\]\n]+)\]\]|`([^`\n]+)`")
_TRACE = re.compile(r"^- (\d{4}-\d{2}-\d{2})(?: \d{2}:\d{2})? — (.*)$")


def _une_ligne(brut) -> str:
    return " ".join(str(brut or "").split())


def _url_valide(v: str) -> bool:
    u = urlsplit(v)
    return u.scheme in ("http", "https") and bool(u.hostname)


def _rel_vault(vault, chemin: str) -> str | None:
    """Chemin relatif au vault (sans `.md`) d'un chemin absolu ou relatif au vault qui reste sous la racine."""
    try:
        p = Path(chemin) if os.path.isabs(chemin) else Path(vault.racine) / chemin
        rel = p.resolve().relative_to(vault.racine).as_posix()
    except (ValueError, OSError):
        return None
    return rel[:-3] if rel.endswith(".md") else rel


def normaliser(vault, brut, type_force: str = "") -> str:
    """Cible telle que stockée : `[[note]]`, chemin absolu, adresse, ou `publie:|branche:|commit:` + valeur.
    INV-LIVRABLES-1 : chemin sans `..` ni octet nul, adresse http(s) seule, longueur bornée."""
    v = _une_ligne(brut)
    if not v or len(v) > LONGUEUR or "\x00" in v or "·" in v or "<!--" in v or "-->" in v:
        raise Invalide(langues.t("serveur.livrables.cible_invalide"))
    if type_force and type_force not in TYPES:
        raise Invalide(langues.t("serveur.livrables.type_inconnu", type=type_force))
    pref = type_force if type_force in PREFIXES else ""
    for p in PREFIXES:
        if v.lower().startswith(p + ":") and not v.lower().startswith(p + "://"):
            pref, v = p, v[len(p) + 1:].strip()
            break
    if pref in ("branche", "commit"):
        if not v or re.search(r"[\s`\[\]\\]|\.\.", v):
            raise Invalide(langues.t("serveur.livrables.cible_invalide"))
        return f"{pref}:{v}"
    if pref == "publie":
        if not _url_valide(v):
            raise Invalide(langues.t("serveur.livrables.url_seule"))
        return f"publie:{v}"
    if m := re.fullmatch(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]", v):
        v = m.group(1).strip()
        if ".." in Path(v).parts:
            raise Invalide(langues.t("serveur.livrables.cible_invalide"))
        return f"[[{v[:-3] if v.endswith('.md') else v}]]"
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", v) and not re.match(r"^[A-Za-z]:[\\/]", v):
        if not _url_valide(v):
            raise Invalide(langues.t("serveur.livrables.url_seule"))  # javascript:, file:, data: … jamais gardés
        return v
    if type_force == "url":
        raise Invalide(langues.t("serveur.livrables.url_seule"))
    v = os.path.expanduser(v)
    if ".." in Path(v.replace("\\", "/")).parts:
        raise Invalide(langues.t("serveur.livrables.traversee"))
    if not os.path.isabs(v):  # relatif : seulement au vault, jamais ailleurs
        if (rel := _rel_vault(vault, v)) is None:
            raise Invalide(langues.t("serveur.livrables.relatif_hors_vault"))
        return f"[[{rel}]]"
    if (rel := _rel_vault(vault, v)) is not None and not type_force == "fichier":
        return f"[[{rel}]]"
    return os.path.normpath(v)


def typer(cible: str) -> tuple[str, str]:
    """(type, valeur) d'une cible stockée."""
    for p in PREFIXES:
        if cible.startswith(p + ":"):
            return p, cible[len(p) + 1:]
    if cible.startswith("[["):
        return "note", cible[2:-2]
    return ("url", cible) if cible.lower().startswith(("http://", "https://")) else ("fichier", cible)


def cle(vault, cible: str) -> str:
    """Clé de dédoublonnage : un même artefact cité de plusieurs façons n'est listé qu'une fois."""
    type_, v = typer(cible)
    if type_ == "note":
        return "note:" + (_rel_vault(vault, v) or v).casefold()
    if type_ in ("url", "publie"):
        u = urlsplit(v)
        return f"url:{u.scheme.lower()}://{(u.netloc or '').lower()}{u.path.rstrip('/')}{'?' + u.query if u.query else ''}"
    return f"{type_}:{os.path.normcase(v)}"


def titre_de(cible: str) -> str:
    type_, v = typer(cible)
    if type_ in ("url", "publie"):
        u = urlsplit(v)
        return (u.hostname or "") + u.path.rstrip("/")
    return v if type_ in ("branche", "commit") else (v.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or v)


# --- écriture : le bloc géré de la tâche -----------------------------------------------------------------

def _appliquer(vault, ident: str, f) -> list[dict]:
    vault.tache(ident)
    sortie: list[dict] = []

    def transformer(texte: str) -> str:
        lignes = fiches.lire_lignes(texte, "livrables")
        f(lignes)
        sortie.extend(lignes)
        return fiches.modifier_cles(fiches.ecrire_lignes(texte, lignes, "livrables"), {"updated": aujourdhui()})
    vault.reecrire(ident, transformer)
    return sortie


def _index(lignes: list[dict], i) -> int:
    if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(lignes):
        raise Invalide(langues.t("serveur.livrables.inconnu"))
    return i


def _titre(brut, defaut: str = "") -> str:
    t = _une_ligne(brut) or defaut
    if not t or len(t) > 300:
        raise Invalide(langues.t("serveur.livrables.titre_requis"))
    return t


def declarer(vault, ident: str, brut, titre: str = "", auteur: str = "moi", type_: str = "") -> list[dict]:
    """Déclare un livrable. Un attendu de même titre non encore produit est rempli (« attendu → produit »)."""
    cible = normaliser(vault, brut, type_)
    nom = _titre(titre, titre_de(cible))
    ligne = {"fait": True, "texte": nom, "date": aujourdhui().isoformat(), "auteur": "ia" if auteur == "ia" else "moi", "lien": cible}

    def f(lignes):
        if any(x["lien"] and cle(vault, x["lien"]) == cle(vault, cible) for x in lignes):
            return  # déjà déclaré : idempotent
        for x in lignes:
            if not x["lien"] and not x["fait"] and x["texte"].casefold() == nom.casefold():
                x.update(fait=True, lien=cible)
                return
        lignes.append(ligne)
    return _appliquer(vault, ident, f)


def annoncer(vault, ident: str, titre: str, auteur: str = "moi") -> list[dict]:
    """Annonce un livrable attendu (case à cocher quand il est produit)."""
    ligne = {"fait": False, "texte": _titre(titre), "date": aujourdhui().isoformat(), "auteur": "ia" if auteur == "ia" else "moi", "lien": ""}
    return _appliquer(vault, ident, lambda lignes: lignes.append(ligne))


def basculer(vault, ident: str, i) -> list[dict]:
    def f(lignes):
        x = lignes[_index(lignes, i)]
        if x["lien"]:
            raise Invalide(langues.t("serveur.livrables.deja_produit"))
        x["fait"] ^= True
    return _appliquer(vault, ident, f)


def retirer(vault, ident: str, i) -> list[dict]:
    def f(lignes):
        del lignes[_index(lignes, i)]
    return _appliquer(vault, ident, f)


# --- lecture : relevé d'une tâche, puis d'une descendance ------------------------------------------------

def _traces(texte: str) -> list[tuple[str, str, str]]:
    """(date, texte, cible) de chaque document cité par une ligne de la section `## Traces`."""
    tete = re.search(rf"^## {SECTION_TRACES}\r?$", texte, re.M)
    if not tete:
        return []
    sortie = []
    for brut in texte[tete.end():].split("\n")[1:]:
        brut = brut.rstrip("\r")
        if not brut.startswith("- "):
            break
        if not (m := _TRACE.match(brut)):
            continue
        corps = m.group(2)
        debut, sep, fin = corps.rpartition(" — ")
        if sep and _DOCS.fullmatch(fin.strip()):
            for d in _UN_DOC.finditer(fin):
                sortie.append((m.group(1), debut.strip(), f"[[{d.group(1)}]]" if d.group(1) else d.group(2)))
    return sortie


def _cible_de_ligne(vault, taches: dict, lien: str) -> str | None:
    """Le lien d'une ligne s'il désigne un document ; None pour un lien vers une tâche (« Devenue ligne »)."""
    if not lien:
        return None
    if m := re.fullmatch(r"\[\[([^\]|#]+)\]\]", lien):
        return None if m.group(1).strip() in taches else lien
    return lien


def _item(vault, cible: str, titre: str, date: str, auteur: str, source: str, distant: bool) -> dict | None:
    """Un livrable prêt à servir ; None si la cible ne se laisse pas lire (jamais d'erreur pour une trace ancienne)."""
    try:
        cible = normaliser(vault, cible)
    except Invalide:
        return None
    type_, v = typer(cible)
    existe, ouvrable = None, type_ in ("url", "publie", "note")
    if type_ == "note":
        rel = _rel_vault(vault, v) or v
        existe = any((Path(vault.racine) / (rel + e)).is_file() for e in (".md", "")) if _rel_vault(vault, v) is not None else False
        v = rel + (".md" if (Path(vault.racine) / (rel + ".md")).is_file() else "")
    elif type_ == "fichier" and not distant:  # INV-LIVRABLES-1 : hors vault, rien n'est lu depuis un appareil distant
        existe = os.path.exists(v)
        ouvrable = existe
    return {"type": type_, "cible": v, "cle": cle(vault, cible), "titre": titre or titre_de(cible), "date": date,
            "auteur": auteur, "existe": existe, "ouvrable": ouvrable, "sources": [source]}


def _fusion(items: list[dict]) -> list[dict]:
    """Dédoublonne : le déclaré prime pour le titre et l'auteur ; la date la plus ancienne ; les sources se cumulent."""
    par: dict[str, dict] = {}
    for it in items:
        if (a := par.get(it["cle"])) is None:
            par[it["cle"]] = it
            continue
        if "declare" in it["sources"] and "declare" not in a["sources"]:
            a.update(titre=it["titre"], auteur=it["auteur"])
        a["date"] = min(a["date"], it["date"])
        a["sources"] = sorted({*a["sources"], *it["sources"]})
    return sorted(par.values(), key=lambda x: (x["date"], x["titre"]), reverse=True)


def propres(moteur, ident: str, distant: bool) -> dict:
    """Livrables et attendus d'UNE tâche : déclarés, traces et lignes à document (relevés d'office)."""
    vault = moteur.vault
    t = vault.tache(ident)
    texte = fiches.lire(t.chemin)
    taches = vault.index()[0]
    auteur_trace = "moi" if executant.humain(t) else "ia"
    items, attendus = [], []
    for i, x in enumerate(fiches.lire_lignes(texte, "livrables")):
        if not x["lien"]:
            attendus.append({"index": i, "titre": x["texte"], "produit": x["fait"], "date": x["date"], "auteur": x["auteur"]})
        elif it := _item(vault, x["lien"], x["texte"], x["date"], x["auteur"], "declare", distant):
            items.append({**it, "index": i})
    for date, _texte, cible in _traces(texte):
        if it := _item(vault, cible, "", date, auteur_trace, "trace", distant):
            items.append(it)
    for x in fiches.lire_lignes(texte):
        if (cible := _cible_de_ligne(vault, taches, x["lien"])) and (it := _item(vault, cible, "", x["date"], x["auteur"], "ligne", distant)):
            items.append(it)
    declares = {it["cle"]: it.get("index") for it in items if "index" in it}
    out = _fusion(items)
    for it in out:
        it["index"] = declares.get(it["cle"])  # retirable à la main seulement s'il est déclaré
    return {"id": ident, "titre": t.titre, "livrables": out, "attendus": attendus}


def _taches_de(vault, ident: str) -> list[str]:
    taches = vault.index()[0]
    if ident in taches:
        return vault.descendance(ident)
    s = arbre.structure(vault)
    if ident not in s.noeuds:
        raise NonTrouve(langues.t("serveur.livrables.noeud_inconnu", ident=ident))
    conts = {c for c in s.sous_arbre(ident) if s.noeuds[c].type == "conteneur"}
    return sorted(k for k, t in taches.items() if t.conteneur in conts)


def releve(moteur, ident: str, distant: bool = False, type_: str = "", q: str = "") -> dict:
    """Livrables d'une tâche ou de toute sa descendance (groupe, projet, casquette), groupés par tâche d'origine."""
    if type_ and type_ not in TYPES:
        raise Invalide(langues.t("serveur.livrables.type_inconnu", type=type_))
    vault = moteur.vault
    q = _une_ligne(q).casefold()
    groupes, vus, manquants = [], set(), 0
    for k in _taches_de(vault, ident):
        g = propres(moteur, k, distant)
        manquants += sum(1 for a in g["attendus"] if not a["produit"])
        g["livrables"] = [x for x in g["livrables"] if (not type_ or x["type"] == type_)
                          and (not q or q in f"{x['titre']} {x['cible']} {g['titre']}".casefold())]
        if not type_ and not q or g["livrables"]:
            vus.update(x["cle"] for x in g["livrables"])
            if g["livrables"] or g["attendus"]:
                groupes.append(g)
    groupes.sort(key=lambda g: (g["id"] != ident, -max((x["date"] > "" and int(x["date"].replace("-", "")) for x in g["livrables"]), default=0)))
    return {"de": ident, "groupes": groupes, "total": len(vus), "manquants": manquants,
            "agrege": len(groupes) > 1 or bool(groupes and groupes[0]["id"] != ident)}


# --- ouverture d'un fichier du poste ---------------------------------------------------------------------

def ouvrir(moteur, ident: str, cible: str) -> dict:
    """Ouvre un fichier du poste d'une liste recalculée (jamais un chemin libre) ; INV-RESULTAT-1 : bornes, rien d'exécuté."""
    vault = moteur.vault
    trouve = next((x for k in _taches_de(vault, ident) for x in propres(moteur, k, False)["livrables"]
                   if x["type"] == "fichier" and x["cible"] == cible), None)
    if trouve is None:
        raise NonTrouve(langues.t("serveur.livrables.disparu"))
    if not trouve["existe"]:
        raise Conflit(langues.t("serveur.livrables.fichier_disparu", nom=trouve["titre"]))
    p = Path(cible).resolve()
    if not any(p.is_relative_to(r) for r in resultat._racines(vault, None)) or set(p.parts) & resultat.IGNORES:
        raise Conflit(langues.t("serveur.livrables.hors_bornes"))
    message = langues.t("serveur.livrables.ouvert", titre=trouve["titre"])
    if p.is_file() and p.suffix.lower() in resultat.EXECUTABLES:
        p, message = p.parent, langues.t("serveur.resultat.dossier_a_la_place")
    try:
        resultat.ouvrir_systeme(str(p))
    except (OSError, webbrowser.Error) as e:
        raise Conflit(langues.t("serveur.resultat.echec", libelle=trouve["titre"])) from e
    return {"message": message}
