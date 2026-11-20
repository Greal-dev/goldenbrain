"""Accueil — écriture du plan validé : seul chemin qui touche au vault, toujours en ajout.

Rôle : relire le plan renvoyé par le client (jamais fait confiance : noms, références, longueurs,
harnais, sessions revalidés), puis créer casquettes, opérations, projets (`contexte.md` + `taches/`),
tâches (clés `harnais` et `session` : « Reprendre » continue la conversation d'origine) et notes liées.
Frontières : ne lit aucun historique ; écrit par `fiches.ecrire_atomique` et `Vault.creer` ; un fichier
déjà là n'est jamais modifié (INV-ACCUEIL-3) : il est compté parmi les « ignorés ».
Invariants portés : INV-ACCUEIL-3 (ajout sans écrasement), INV-ACCUEIL-5, INV-VAULT-1, INV-VAULT-2.
"""

from __future__ import annotations

import os
import re
from fnmatch import fnmatch
from pathlib import Path

from . import fiches, langues, squelette
from .accueil import norm, propre
from .accueil_sources import HARNAIS_LUS
from .vault import Invalide, aujourdhui, slugifier

LIMITES = {"casquettes": 20, "operations": 60, "projets": 300, "taches": 2000, "notes": 600}
SESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,79}$")
CODE = re.compile(r"^(C\d+)-(.+)$")
# Fiche de projet à compléter : l'IA la lit avant chaque tâche du projet (guide, « Organiser votre second cerveau »).
MODELE_CONTEXTE = ("\n## Objectif\n\n(À compléter : ce que ce projet doit produire, et pour quand.)\n"
                   "\n## Repères\n\n(Personnes, documents, liens utiles : [[nom d'une note]].)\n"
                   "\n## Consignes pour l'IA\n\n(Ce que l'IA doit savoir avant chaque tâche : ton, contraintes, "
                   "ce qu'il ne faut pas faire.)\n")


def _noms() -> dict[str, str]:
    return {"casquettes": langues.t("serveur.accueil_ecriture.nom_casquettes"),
            "operations": langues.t("serveur.accueil_ecriture.nom_operations"),
            "projets": langues.t("serveur.accueil_ecriture.nom_projets"),
            "taches": langues.t("serveur.accueil_ecriture.nom_taches"),
            "notes": langues.t("serveur.accueil_ecriture.nom_notes")}


def _sans_nom() -> dict[str, str]:
    return {"casquettes": langues.t("serveur.accueil_ecriture.casquette_sans_nom"),
            "operations": langues.t("serveur.accueil_ecriture.operation_sans_nom"),
            "projets": langues.t("serveur.accueil_ecriture.projet_sans_nom")}


def nettoyer(plan: dict) -> dict:
    """Plan revalidé : listes bornées, noms nettoyés, références résolues."""
    if not isinstance(plan, dict):
        raise Invalide(langues.t("serveur.accueil_ecriture.plan_illisible"))
    out = {}
    for cle, maxi in LIMITES.items():
        liste = plan.get(cle) or []
        if not isinstance(liste, list) or len(liste) > maxi:
            raise Invalide(langues.t("serveur.accueil_ecriture.limite", nom=_noms()[cle], maxi=maxi))
        out[cle] = [x for x in liste if isinstance(x, dict)]
    ids = {k: {str(x.get("id")) for x in out[k]} for k in ("casquettes", "operations", "projets")}
    for cle in ("casquettes", "operations", "projets"):
        for x in out[cle]:
            x["nom"] = propre(x.get("nom"))
            if not x["nom"]:
                raise Invalide(_sans_nom()[cle])
    for x in out["operations"]:
        if str(x.get("casquette")) not in ids["casquettes"]:
            raise Invalide(langues.t("serveur.accueil_ecriture.operation_sans_casquette", nom=x["nom"]))
    for x in out["projets"]:
        if str(x.get("casquette")) not in ids["casquettes"]:
            raise Invalide(langues.t("serveur.accueil_ecriture.projet_sans_casquette", nom=x["nom"]))
        if x.get("operation") and str(x["operation"]) not in ids["operations"]:
            raise Invalide(langues.t("serveur.accueil_ecriture.projet_operation_inconnue", nom=x["nom"]))
        if x.get("dossier") and not Path(str(x["dossier"])).is_dir():
            x["dossier"] = ""
    for x in out["taches"]:
        x["titre"] = propre(x.get("titre"), 160)
        if not x["titre"] or str(x.get("projet")) not in ids["projets"]:
            raise Invalide(langues.t("serveur.accueil_ecriture.tache_incomplete"))
        if x.get("harnais") not in (*HARNAIS_LUS, None) or (x.get("session") and not SESSION.match(str(x["session"]))):
            raise Invalide(langues.t("serveur.accueil_ecriture.tache_conversation", titre=x["titre"]))
    for x in out["notes"]:
        x["titre"] = propre(x.get("titre"), 120)
        if not x["titre"]:
            raise Invalide(langues.t("serveur.accueil_ecriture.note_sans_titre"))
    return out


class Ecrivain:
    def __init__(self, vault):
        self.vault, self.racine = vault, vault.racine
        self.crees = {"casquettes": 0, "projets": 0, "taches": 0, "notes": 0, "dossiers": 0}
        self.ignores: list[str] = []
        self.stems = {p.stem.casefold() for p in self._md()}

    def _md(self):
        for d, noms, fichiers in os.walk(self.racine):
            noms[:] = [n for n in noms if not n.startswith(".")]
            for f in fichiers:
                if f.endswith(".md"):
                    yield Path(f)

    def neuf(self, chemin: Path, texte: str, deja: str) -> bool:
        if chemin.exists():
            self.ignores.append(deja)
            return False
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(chemin, texte)
        return True

    def stem(self, titre: str) -> str:
        base = slugifier(titre)
        s, n = base, 2
        while s.casefold() in self.stems:
            s, n = f"{base}-{n}", n + 1
        self.stems.add(s.casefold())
        return s

    def code_casquette(self, nom: str) -> tuple[str, str]:
        """(code, dossier) : une casquette de même nom est reprise, sinon le premier code libre."""
        base, pris, cle = self.racine / self.vault.cfg.casquettes, set(), norm(nom)
        for d in (base.iterdir() if base.is_dir() else []):
            if m := CODE.match(d.name):
                pris.add(m.group(1))
                if norm(m.group(2)) == cle:
                    return m.group(1), d.name
        pris |= {c.casquette for c in self.vault.index()[1].values()}
        n = 1
        while f"C{n}" in pris:
            n += 1
        return f"C{n}", f"C{n}-{slugifier(nom, False)}"


def _frontmatter(cles: dict) -> str:
    return "---\n" + "\n".join(f"{k}: {fiches.valeur_yaml(v)}" for k, v in cles.items() if v not in (None, "")) + "\n---\n\n"


def visible(cfg, rel: str) -> bool:
    """Un dossier du vault ne peut porter un projet que si un motif `[vault] taches` le désigne."""
    segs = Path(rel).parts
    for motif in cfg.taches:
        m = motif.split("/")
        if "taches" in m and m.index("taches") == len(segs) and all(fnmatch(a, b) for a, b in zip(segs, m)):
            return True
    return False


def _rel(e: Ecrivain, p: dict, cas: dict, ops: dict) -> str:
    """Dossier du vault où vit (ou vivra) le projet."""
    cfg, dossier_cas = e.vault.cfg, cas[str(p["casquette"])][1]
    if p.get("place") and ".." not in Path(str(p["place"])).parts and (e.racine / str(p["place"])).is_dir() and visible(cfg, str(p["place"])):
        return str(p["place"])
    op = ops.get(str(p.get("operation")))
    return "/".join(filter(None, [cfg.casquettes, dossier_cas, op, slugifier(p["nom"], False)]))


def _projets(e: Ecrivain, p: dict, cas: dict, ops: dict) -> tuple[str, str]:
    """(identifiant du conteneur, dossier) du projet ; crée son `contexte.md` s'il manque."""
    cfg, code = e.vault.cfg, cas[str(p["casquette"])][0]
    if p.get("existe") and str(p["existe"]) in e.vault.index()[1]:
        return str(p["existe"]), ""
    rel = _rel(e, p, cas, ops)
    cible = e.racine / rel
    ctx = cible / cfg.contexte
    texte = _frontmatter({"type": "contexte", "nom": p["nom"], "casquette": code, "depot": p.get("dossier"),
                          "resume": propre(p.get("resume") or (f"Notes d'origine : {p['place']}/" if p.get("place") else ""), 140), "source": "accueil", "created": aujourdhui(),
                          "statut": "actif", "tags": ["contexte", "projet"]}) + f"# {p['nom']}\n\n{propre(p.get('resume'), 140)}\n" + MODELE_CONTEXTE
    if e.neuf(ctx, texte, langues.t("serveur.accueil_ecriture.deja_projet", nom=p["nom"])):
        e.crees["projets"] += 1
    return rel, rel


def appliquer(vault, plan: dict) -> dict:
    """Écrit le plan validé, en ajout seulement. Rend les comptes et ce qui existait déjà."""
    garde = bool(plan.get("squelette")) if isinstance(plan, dict) else False
    plan = nettoyer(plan)
    e = Ecrivain(vault)
    cas = {}
    for c in plan["casquettes"]:
        cas[str(c["id"])] = e.code_casquette(c["nom"])
        e.crees["casquettes"] += not (e.racine / vault.cfg.casquettes / cas[str(c["id"])][1]).is_dir()
    ops = {str(o["id"]): slugifier(o["nom"], False) for o in plan["operations"]}
    for p in plan["projets"]:  # tout refuser avant d'écrire : un projet hors des motifs `[vault] taches` n'aurait pas de conteneur
        rel = _rel(e, p, {k: (v[0], v[1]) for k, v in cas.items()}, ops)
        if not (p.get("existe") and str(p["existe"]) in vault.index()[1]) and not visible(vault.cfg, rel):
            raise Invalide(langues.t("serveur.accueil_ecriture.motif_absent", rel=rel))
    if garde:  # INV-ACCUEIL-5 : ce qui manque est recalculé ici, jamais lu du client
        depart = squelette.creer(vault)
        e.crees["dossiers"], e.crees["notes"] = depart["dossiers"], depart["notes"]
        e.stems.add(Path(squelette.LISEZ_MOI).stem.casefold())
    projets = {}
    for p in plan["projets"]:
        projets[str(p["id"])] = _projets(e, p, {k: (v[0], v[1]) for k, v in cas.items()}, ops)
    vault._index = None  # les `contexte.md` neufs doivent apparaître dans l'index avant les tâches
    profils = {}
    for n in plan["notes"]:  # noms des notes d'abord : les liens se croisent
        n["stem"] = e.stem("profil-" + str(cas.get(str(n.get("casquette")), ("", ""))[1]) if n.get("casquette") and not n.get("projet") else n["titre"])
        if n.get("casquette") and not n.get("projet") and str(n["casquette"]) in cas:  # lien par chemin : plusieurs casquettes, plusieurs profils
            profils[str(n["casquette"])] = f"{vault.cfg.casquettes}/{cas[str(n['casquette'])][1]}/notes/{n['stem']}|{n['stem']}"
    liens_projets: dict[str, list[str]] = {}
    for n in plan["notes"]:
        if n.get("projet") and projets.get(str(n["projet"]), ("", ""))[1]:  # seulement les notes réellement écrites
            cid = str(next((p["casquette"] for p in plan["projets"] if str(p["id"]) == str(n["projet"])), ""))
            liens_projets.setdefault(cid, []).append(f"{projets[str(n['projet'])][1]}/notes/{n['stem']}|{n['titre']}")
    for n in plan["notes"]:
        _note(e, n, plan, cas, projets, profils, liens_projets)
    existantes = vault.index()[0].values()
    for t in plan["taches"]:
        cid = projets[str(t["projet"])][0]
        if any((t.get("session") and x.fm.get("session") == t["session"])
               or (x.conteneur == cid and norm(x.titre) == norm(t["titre"])) for x in existantes):
            e.ignores.append(langues.t("serveur.accueil_ecriture.deja_tache", titre=t["titre"]))
            continue
        cles = {"session": t.get("session"), "source": "accueil"}
        vault.creer(t["titre"], conteneur=cid, description=propre(t.get("detail"), 300),
                    harnais=t.get("harnais"), cles=cles)
        e.crees["taches"] += 1
    return {"crees": e.crees, "ignores": e.ignores}


def _note(e: Ecrivain, n: dict, plan: dict, cas: dict, projets: dict, profils: dict, liens: dict) -> None:
    corps = f"# {n['titre']}\n\n{str(n.get('corps') or '').strip()[:2000]}\n"
    if n.get("projet") and str(n["projet"]) in projets:
        p = next(x for x in plan["projets"] if str(x["id"]) == str(n["projet"]))
        dossier = e.racine / projets[str(n["projet"])][1] / "notes" if projets[str(n["projet"])][1] else None
        if dossier is None:
            return  # projet déjà là : on n'y ajoute pas de note
        if (lien := profils.get(str(p["casquette"]))):
            corps += f"\nCasquette : [[{lien}]]\n"
    elif n.get("casquette") and str(n["casquette"]) in cas:
        dossier = e.racine / e.vault.cfg.casquettes / cas[str(n["casquette"])][1] / "notes"
        if (suite := liens.get(str(n["casquette"]))):
            corps += "\nProjets :\n" + "".join(f"- [[{s}]]\n" for s in suite)
    else:
        return
    texte = _frontmatter({"type": "note", "titre": n["titre"], "source": "accueil", "created": aujourdhui(),
                          "tags": ["accueil"]}) + corps
    if e.neuf(dossier / f"{n['stem']}.md", texte, langues.t("serveur.accueil_ecriture.deja_note", titre=n["titre"])):
        e.crees["notes"] += 1
