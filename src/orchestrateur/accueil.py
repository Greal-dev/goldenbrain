"""Accueil d'un nouvel arrivant — le plan proposé : casquettes, opérations, projets, tâches, notes.

Rôle : à partir des sources que l'arrivant a cochées (questions, conversations d'agents, dossier
désigné, vault existant), bâtir un plan en mémoire où chaque élément porte sa source ; rendre aussi ce
qui est laissé de côté, et pourquoi. Calcul déterministe et local, sans modèle.
Frontières : n'écrit rien (l'écriture, après validation, est `accueil_ecriture.py`) ; ne lit que par
`accueil_sources.py` ; aucun état serveur entre la proposition et la validation (le client renvoie le plan
corrigé), de sorte qu'une proposition ne laisse aucune trace.
Invariants portés : INV-ACCUEIL-1 (local, par source consentie), INV-ACCUEIL-2 (proposition sans
écriture), INV-ACCUEIL-4 (rejouable : ce qui existe déjà est reconnu, jamais reproposé),
INV-ACCUEIL-5 (le vault de départ n'est proposé qu'à un vault vide).
"""

from __future__ import annotations

import re
import tempfile
import unicodedata
from pathlib import Path

from . import accueil_sources as src
from . import langues, squelette
from .vault import Invalide

MAX_PAR_PROJET = 15
MAX_ROLES = 8
SOURCES = ("questions", "conversations", "dossier", "vault")
RAISON = {
    "questions": "vos réponses aux questions",
    "conversations": "vos conversations avec des agents",
    "dossier": "le dossier que vous avez désigné",
    "vault": "le vault existant que vous avez désigné",
}


def _lu(source: str) -> str:
    return {"questions": langues.t("serveur.accueil.lu_questions"),
            "conversations": langues.t("serveur.accueil.lu_conversations"),
            "dossier": langues.t("serveur.accueil.lu_dossier"),
            "vault": langues.t("serveur.accueil.lu_vault")}[source]


def norm(texte: str) -> str:
    plat = unicodedata.normalize("NFKD", str(texte).casefold()).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plat).split())


def propre(texte, n: int = 80) -> str:
    return " ".join(str(texte or "").split())[:n]


class Plan:
    """Compteur d'identifiants locaux et listes du plan."""

    def __init__(self):
        self.n = 0
        self.casquettes, self.operations, self.projets, self.taches, self.notes, self.laisses = [], [], [], [], [], []

    def ident(self, p: str) -> str:
        self.n += 1
        return f"{p}{self.n}"

    def projet(self, nom: str, source: str, dossier: str = "", resume: str = "", existant: str | None = None) -> dict:
        cle = norm(nom)
        for p in self.projets:
            if norm(p["nom"]) == cle:
                if source not in p["source"].split(", "):
                    p["source"] += ", " + source
                p["dossier"] = p["dossier"] or dossier
                p["resume"] = p["resume"] or resume
                return p
        p = {"id": self.ident("p"), "nom": nom, "casquette": None, "operation": None, "dossier": dossier,
             "resume": resume, "source": source, "existe": existant, "place": None}
        self.projets.append(p)
        return p

    def vue(self) -> dict:
        return {"casquettes": self.casquettes, "operations": self.operations, "projets": self.projets,
                "taches": self.taches, "notes": self.notes, "laisses": self.laisses}


def _passage(dossier: str) -> bool:
    """Domicile, racine ou dossier temporaire : un lieu de passage, pas un projet."""
    p = Path(dossier)
    temp = {Path(tempfile.gettempdir()).resolve()}
    return p == src.maison() or p == p.parent or any(t == p or t in p.parents for t in temp) \
        or "Temp" in p.parts


def _questions(plan: Plan, q: dict) -> None:
    metier = propre(q.get("metier"), 120)
    roles = []
    for r in q.get("roles") or []:
        if (r := propre(r, 60)) and norm(r) not in {norm(x) for x in roles}:
            roles.append(r)
    projets = q.get("projets") if isinstance(q.get("projets"), list) else []
    for nom in projets[:MAX_PAR_PROJET]:  # « vos projets en cours » : rangés ensuite par `_ranger`
        if nom := propre(nom, 80):
            plan.projet(nom, "questions")
    for r in roles[:MAX_ROLES]:
        c = {"id": plan.ident("c"), "nom": r, "source": "questions"}
        plan.casquettes.append(c)
        corps = (f"Métier : {metier}\n\n" if metier else "") + f"Rôle : {r}\n"
        plan.notes.append({"id": plan.ident("n"), "titre": f"Profil — {r}", "corps": corps,
                           "casquette": c["id"], "projet": None, "source": "questions"})


def _conversations(plan: Plan, vault, cfg: dict) -> None:
    convs = src.conversations(list(cfg.get("harnais") or src.HARNAIS_LUS), int(cfg.get("depuis_jours") or 90))
    taches = vault.index()[0].values()
    reprises = {str(t.fm.get("session")) for t in taches if t.fm.get("session")}
    deja = {(norm(Path(t.conteneur).name), norm(t.titre)) for t in taches}
    par_projet: dict[str, list[src.Conv]] = {}
    for c in sorted(convs, key=lambda c: c.fin, reverse=True):
        base = {"titre": c.titre, "harnais": c.harnais, "session": c.session, "source": "conversations"}
        if _passage(c.dossier):
            plan.laisses.append({**base, "pourquoi": langues.t("serveur.accueil.passage")})
        elif c.session in reprises:
            plan.laisses.append({**base, "pourquoi": langues.t("serveur.accueil.deja_reprise")})
        else:
            par_projet.setdefault(src.racine_depot(c.dossier), []).append(c)
    for racine, liste in par_projet.items():
        p, vus = plan.projet(Path(racine).name or racine, "conversations", racine), set()
        n = 0
        for c in liste:
            base = {"titre": c.titre, "harnais": c.harnais, "session": c.session, "source": "conversations"}
            if (norm(p["nom"]), norm(c.titre)) in deja:
                plan.laisses.append({**base, "pourquoi": langues.t("serveur.accueil.titre_existe")})
            elif norm(c.titre) in vus:
                plan.laisses.append({**base, "pourquoi": langues.t("serveur.accueil.doublon")})
            elif c.volume < 2 and c.etat != "en_cours":
                plan.laisses.append({**base, "pourquoi": langues.t("serveur.accueil.sans_suite")})
            elif n >= MAX_PAR_PROJET:
                plan.laisses.append({**base, "pourquoi": langues.t("serveur.accueil.au_dela", n=MAX_PAR_PROJET)})
            else:
                vus.add(norm(c.titre))
                n += 1
                etat = {"en_cours": "en cours", "terminee": "terminée", "abandonnee": "abandonnée"}[c.etat]
                plan.taches.append({**base, "id": plan.ident("t"), "projet": p["id"],
                                    "detail": f"Conversation {c.harnais} du {c.debut} au {c.fin}, "
                                              f"{c.volume} message(s), {etat}."})


def _dossier(plan: Plan, chemin: str) -> None:
    for d in src.projets_du_dossier(chemin):
        plan.projet(d["nom"], "dossier", d["dossier"], d["resume"])


def _vault(plan: Plan, vault, chemin: str) -> None:
    racine = vault.racine.resolve()
    cible = Path(chemin).expanduser().resolve() if chemin else racine
    if cible != racine and racine not in cible.parents:
        raise Invalide(langues.t("serveur.accueil.vault_hors_config"))
    for d in src.vault_existant(cible):
        rel = (cible / d["dossier"]).relative_to(racine).as_posix()
        p = plan.projet(d["nom"], "vault", "", f"{d['notes']} note(s) déjà là")
        p["place"] = rel
        for k in d["cases"]:
            plan.taches.append({"id": plan.ident("t"), "titre": k["titre"], "projet": p["id"], "harnais": None,
                                "session": None, "source": "vault", "detail": f"Case à cocher de {k['note']}"})


def _ranger(plan: Plan, vault) -> None:
    """Casquette, opération et existant de chaque projet ; défauts quand une source manque."""
    if not plan.casquettes:
        plan.casquettes.append({"id": plan.ident("c"), "nom": "Mes projets", "source": langues.t("serveur.accueil.par_defaut")})
    existants = {norm(c.titre): cid for cid, c in vault.index()[1].items() if c.contexte}
    for p in plan.projets:
        conts = vault.index()[1]
        if (cid := (p["place"] if p["place"] in conts else None) or existants.get(norm(p["nom"]))):
            p["existe"] = cid
        mots = norm(p["nom"] + " " + p["dossier"])
        choix = next((c for c in plan.casquettes if norm(c["nom"]) and norm(c["nom"]) in mots), plan.casquettes[0])
        p["casquette"] = choix["id"]
    groupes: dict[str, list[dict]] = {}
    for p in plan.projets:
        if p["dossier"] and not p["existe"]:
            groupes.setdefault(str(Path(p["dossier"]).parent), []).append(p)
    for parent, liste in groupes.items():
        if len(liste) >= 2 and not _passage(parent):
            o = {"id": plan.ident("o"), "nom": Path(parent).name, "casquette": liste[0]["casquette"],
                 "source": liste[0]["source"].split(", ")[0]}
            plan.operations.append(o)
            for p in liste:
                p["operation"], p["casquette"] = o["id"], o["casquette"]


def proposer(vault, sources: dict) -> dict:
    """Plan proposé pour les sources cochées. N'écrit rien (INV-ACCUEIL-2)."""
    plan, actives = Plan(), [s for s in SOURCES if (sources.get(s) or {}).get("actif")]
    if not actives:
        raise Invalide(langues.t("serveur.accueil.aucune_source"))
    if "questions" in actives:
        _questions(plan, sources["questions"])
    if "conversations" in actives:
        _conversations(plan, vault, sources["conversations"])
    if "dossier" in actives:
        _dossier(plan, str(sources["dossier"].get("chemin") or ""))
    if "vault" in actives:
        _vault(plan, vault, str(sources["vault"].get("chemin") or ""))
    _ranger(plan, vault)
    for p in plan.projets:  # première note de connaissance de chaque projet nouveau
        if not p["existe"]:
            plan.notes.append({"id": plan.ident("n"), "titre": p["nom"], "projet": p["id"], "casquette": None,
                               "corps": p["resume"] or f"Projet repéré à partir de {RAISON[p['source'].split(', ')[0]]}.",
                               "source": p["source"]})
    return {**plan.vue(), "sources": actives, "squelette": squelette.propose(vault),
            "confidentialite": {"modele": False, "texte": langues.t("serveur.accueil.confidentialite")},
            "lu": [_lu(s) for s in actives]}
