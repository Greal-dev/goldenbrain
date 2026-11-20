"""Page « Décisions » : tout ce qui attend l'utilisateur, une ligne par décision, la question en clair.

Rôle : réunir les sources — tâche au statut de retour (`[vault] statut_retour`), tâche terminée à valider, proposition en
attente, revue (propositions « fermer » groupées par auteur), échéance dépassée, routine en échec —, en extraire la
question à trancher, les trier par `ordonnancement.classer` et appliquer le lot de gestes
(validations, fermetures cochées).
Frontières : lecture seule du vault (« Faire documenter » n'écrit que par le tour de l'agent) ; les gestes passent par les fonctions humaines du moteur
(`revues.valider`, `trancher`) ; aucun tour n'est lancé.
Invariants portés : INV-EVITABLE-1 (pastille « évitable ? », informative) ; INV-DECISIONS-1 (une ligne par décision, question visible sans ouvrir la
fiche, tri par le classement unique d'ordonnancement, aucun statut posé sans geste humain).
"""

from __future__ import annotations

import re
from collections import defaultdict

from . import evitable, fiches, langues, ordonnancement, scan, sessions, temps
from .vault import ErreurOrch, Tache

GENRES = ("reponse", "validation", "proposition", "revue", "echeance", "scan", "agent", "routine")
LONGUEUR_QUESTION = 600


def libelle(genre: str) -> str:
    return {"reponse": langues.t("serveur.decisions.libelle_reponse"),
            "validation": langues.t("serveur.decisions.libelle_validation"),
            "proposition": langues.t("serveur.decisions.libelle_proposition"),
            "revue": langues.t("serveur.decisions.libelle_revue"),
            "echeance": langues.t("serveur.decisions.libelle_echeance"),
            "scan": langues.t("serveur.decisions.libelle_scan"),
            "agent": langues.t("serveur.decisions.libelle_agent"),
            "routine": langues.t("serveur.decisions.libelle_routine")}[genre]


def _court(texte: str, n: int = LONGUEUR_QUESTION) -> str:
    texte = " ".join(str(texte or "").split())
    return texte if len(texte) <= n else texte[: n - 1].rstrip() + "…"


def derniere_question(texte: str) -> str:
    """Dernière question d'un message d'agent : le dernier paragraphe qui en pose une, sinon le dernier."""
    paragraphes = [p.strip() for p in re.split(r"\n\s*\n", texte or "") if p.strip()]
    avec = [p for p in paragraphes if "?" in p]
    return _court((avec or paragraphes or [""])[-1])


def question_de(t: Tache) -> tuple[str, str]:
    """(texte, source) : `commentaire:` de la fiche, sinon son « Prochain pas » ; « » si rien."""
    for source, valeur in (("commentaire", t.fm.get("commentaire")),
                           ("prochain_pas", t.fiche.get("prochain_pas"))):
        if valeur and str(valeur).strip():
            return _court(valeur), source
    return "", ""


CONSIGNE_DOCUMENTER = """[Demande de l'utilisateur via la page « Décisions » : ta fiche est muette.] Réécris ton bloc <fiche> avec : `situation` = de quoi il s'agit, en une phrase claire pour quelqu'un qui ne connaît pas la tâche ; `fait` = ce qui a été fait, en une phrase ; `resultat` = où trouver le livrable ; `essai` = le mode de validation (comment l'essayer, ce qu'on doit voir ; un geste dans l'interface — ouvrir, cliquer, regarder — garde la tâche « à valider », une commande ou un test la laisse à la validation automatique). Ne refais pas le travail : documente-le seulement."""


def sujet_de(t: Tache) -> str:
    """« De quoi il s'agit » : la description de la tâche (corps, hors titre), sinon la situation de la fiche."""
    corps = [ligne for ligne in fiches.corps_sans_fiche(fiches.lire(t.chemin)).splitlines()
             if ligne.strip() and not ligne.lstrip().startswith("#")]
    return _court(" ".join(corps) or t.fiche.get("situation"), 300)


def documenter(moteur, tache: str) -> str:
    """Envoie à l'agent de la tâche la consigne d'écrire « de quoi il s'agit » et « ce qui a été fait »."""
    return moteur.soumettre(tache, CONSIGNE_DOCUMENTER)


def _depuis_journaux(moteur, ident: str) -> str:
    try:
        messages = sessions.relire_journaux(moteur.config.donnees, ident, 40, moteur.registre)
    except (OSError, ValueError):
        return ""
    for m in reversed(messages):
        if m.role == "assistant" and m.texte.strip():
            return derniere_question(m.texte)
    return ""


def _ligne_tache(moteur, k: str, t: Tache, genre: str, parents: dict) -> dict:
    vault = moteur.vault
    fil = vault.fil_ariane(k, parents)
    return {"id": f"{genre}:{k}", "genre": genre, "libelle": libelle(genre), "tache": k,
            "titre": t.titre, "projet": fil[-2] if len(fil) > 1 else langues.t("serveur.decisions.sans_projet"),
            "statut": t.statut, "priorite": str(t.fm.get("priorite") or "").strip().casefold(),
            "echeance": _echeance(t), "retard": _retard(vault, t), "question": "", "source": "",
            "resultat": "", "essai": "", "sujet": "", "fait": "", "muette": False, "proposition": None, "fermetures": [],
            "rapide": False, "_age": str(t.fm.get("updated") or t.fm.get("created") or "")}


def _echeance(t: Tache) -> str:
    e = temps.echeance_de(t.fm)
    return e.isoformat() if e else ""


def _retard(vault, t: Tache) -> bool:
    return temps.en_retard(vault, t)


def lignes(moteur) -> list[dict]:
    """Une ligne par décision, sans la question ni le rang (assez pour compter)."""
    vault = moteur.vault
    taches = vault.index()[0]
    parents = vault._parents(taches)
    sortie, prises = [], set()
    for k, t in taches.items():
        genre = ("reponse" if t.statut == vault.retour else "validation" if vault.a_valider(t)
                 else "echeance" if _retard(vault, t) else "")
        if genre:
            prises.add(k)
            sortie.append(_ligne_tache(moteur, k, t, genre, parents))
    routines = getattr(moteur, "routines", None)
    for k, d in routines.en_echec() if routines else []:  # INV-ROUTINE-4 : jusqu'à une exécution réussie
        if k in taches and k not in prises:
            ligne = _ligne_tache(moteur, k, taches[k], "routine", parents)
            jour, _, heure = str(d.get("a") or "")[:16].partition("T")
            ligne.update(id=f"routine:{k}", source="routine", _age=str(d.get("a") or ""),
                         question=_court(langues.t("serveur.decisions.routine_echec", jour=jour, heure=heure,
                                                   motif=d.get("motif") or langues.t("serveur.decisions.cause_inconnue"))))
            sortie.append(ligne)
    revues: dict[str, list[dict]] = defaultdict(list)
    for p in moteur.propositions.liste:
        if p.get("etat") != "en_attente" or p.get("tache") not in taches:
            continue
        if p.get("de") == scan.AUTEUR:  # INV-SCAN-1 : groupées à part, classées par gain et effort
            ligne = _ligne_tache(moteur, p["tache"], taches[p["tache"]], "scan", parents)
            ligne.update(id=f"scan:{p['n']}", projet=langues.t("serveur.decisions.projet_scan"), proposition=p, rapide=True, _age=p.get("cree") or "")
            sortie.append(ligne)
            continue
        if p["type"] == "fermer":
            revues[p.get("de") or ""].append(p)
            continue
        t = taches[p["tache"]]
        ligne = _ligne_tache(moteur, p["tache"], t, "proposition", parents)
        ligne.update(id=f"proposition:{p['n']}", proposition=p, rapide=True, _age=p.get("cree") or "")
        sortie.append(ligne)
    for de, ps in revues.items():
        t = taches[ps[0]["tache"]]
        ligne = _ligne_tache(moteur, ps[0]["tache"], t, "revue", parents)
        ligne.update(id=f"revue:{de}", projet=langues.t("serveur.decisions.revue"), _age=min(p.get("cree") or "" for p in ps),
                     titre=langues.t("serveur.decisions.revue_de", de=de) if de
                     else langues.t("serveur.decisions.revue"), rapide=False, echeance="", retard=False,
                     priorite="",
                     fermetures=[{"n": p["n"], "tache": p["tache"], "titre": p.get("titre_tache") or "",
                                  "statut": p["valeur"], "motif": p.get("motif") or ""} for p in ps])
        sortie.append(ligne)
    for a in moteur.agents_cc.decisions():  # INV-AGENTSCC-1 : sans tâche, à rattacher ou à créer
        sortie.append({"id": f"agent:{a['id']}", "genre": "agent", "libelle": libelle("agent"), "tache": "",
                       "titre": a["nom"], "projet": langues.t("serveur.decisions.projet_agents"), "statut": "", "priorite": "", "echeance": "",
                       "retard": False, "question": "", "source": "", "resultat": "", "essai": "", "sujet": "",
                       "fait": "", "muette": False, "proposition": None, "fermetures": [], "rapide": False,
                       "agent": a, "_age": a["maj"]})
    return sortie


def compter(moteur) -> int:
    return len(lignes(moteur))


def rassembler(moteur) -> dict:
    """Décisions complètes, triées par `ordonnancement.classer` (INV-DECISIONS-1)."""
    vault = moteur.vault
    taches = vault.index()[0]
    toutes = lignes(moteur)
    reglage_ev = evitable.lire(moteur.config.donnees)
    agents = [lg for lg in toutes if lg["genre"] == "agent"]
    preco = [lg for lg in toutes if lg["genre"] == "scan"]
    toutes = [lg for lg in toutes if lg["genre"] not in ("agent", "scan")]
    for lg in toutes:
        t = taches.get(lg["tache"])
        if lg["genre"] != "revue":
            lg["sujet"], lg["fait"] = sujet_de(t), _court(t.fiche.get("fait"), 300)
        # Une ligne de tâche sans l'un des deux : « Fiche muette », à faire documenter par son agent.
        lg["muette"] = lg["genre"] in ("reponse", "validation", "echeance") and not (lg["sujet"] and lg["fait"])
        if lg["genre"] in ("reponse", "echeance"):
            lg["question"], lg["source"] = question_de(t)
            if lg["genre"] == "reponse" and not lg["question"]:
                lg["question"], lg["source"] = _depuis_journaux(moteur, lg["tache"]), "agent"
        elif lg["genre"] == "validation":
            lg["resultat"] = _court(t.fiche.get("resultat"))
            lg["essai"] = _court(t.fiche.get("essai"))
            lg["rapide"] = bool(lg["resultat"])  # sans résultat annoncé, on ouvre la fiche
            if a := moteur.validation_auto.motif(lg["tache"]):  # INV-VALID-2 : pourquoi pas close
                lg["auto"] = {"issue": a["issue"], "motif": a.get("motif", ""), "date": a.get("date", "")}
        if ev := evitable.evaluer(moteur, t, lg["genre"], lg["question"], reglage_ev):  # INV-EVITABLE-1
            lg["evitable"] = ev
    ordre = sorted(range(len(toutes)), key=lambda i: (toutes[i]["_age"], toutes[i]["id"]))
    candidats = [ordonnancement.Candidat(toutes[i]["tache"], False, n) for n, i in enumerate(ordre)]
    for rang, (c, motif) in enumerate(ordonnancement.classer(vault, candidats), 1):
        lg = toutes[ordre[c.numero]]
        lg["rang"], lg["motif"] = rang, motif
    toutes.sort(key=lambda lg: lg["rang"])
    # INV-SCAN-1 : les préconisations suivent les tâches, gain décroissant puis effort croissant.
    for n, lg in enumerate(sorted(preco, key=lambda lg: scan.ordre(lg["proposition"])), len(toutes) + 1):
        lg["rang"], lg["motif"] = n, langues.t("serveur.decisions.gain_effort", gain=lg["proposition"].get("gain"),
                                               effort=lg["proposition"].get("effort"))
        toutes.append(lg)
    # Un agent sans tâche n'a rien à classer : il vient après les tâches, le plus récent d'abord.
    for n, lg in enumerate(sorted(agents, key=lambda lg: lg["_age"], reverse=True), len(toutes) + 1):
        lg["rang"], lg["motif"] = n, lg["agent"]["motif"]
        toutes.append(lg)
    for lg in toutes:
        lg.pop("_age")
    return {"decisions": toutes, "total": len(toutes), "clos_auto": moteur.validation_auto.clos_recents()}


def valider_lot(moteur, taches: list[str]) -> dict:
    """Valide chaque tâche à valider ; un refus (verrou, tâche déjà validée) n'arrête pas le lot."""
    return _lot(taches, lambda k: (moteur.demi_verrou(k, False, seule=True), moteur.revues.valider(k)))


def fermer_lot(moteur, numeros: list[int]) -> dict:
    """Accepte les fermetures cochées (statut posé sur ce geste, INV-EXEC-5) ; les autres restent."""
    return _lot(numeros, lambda n: moteur.trancher(n, True))


def _lot(cibles: list, geste) -> dict:
    faits, echecs = [], []
    for c in cibles:
        try:
            geste(c)
            faits.append(c)
        except ErreurOrch as e:
            echecs.append({"cible": c, "erreur": str(e)})
    return {"faits": faits, "echecs": echecs}
