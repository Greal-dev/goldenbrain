"""Lignes de tâche : travaux courts, sans livrable ni branche propres, tenus en liste cochable dans la fiche.

Rôle : ajouter, cocher, retirer une ligne ; promouvoir une ligne en tâche fille ; faire d'une tâche une ligne de
sa mère. Une ligne porte son texte, son état, sa date, son auteur (Moi / IA) et un lien éventuel (document ou tâche).
Frontières : écrit par `Vault.reecrire` (bloc géré des lignes seul, `fiches`) et `Vault.modifier` ; ne lance aucun
tour d'agent ; la création d'une tâche passe par `Moteur.creer`.
Invariants portés : INV-LIGNES-1, INV-VAULT-1.
"""

from __future__ import annotations

from . import executant, fiches, langues, rangement
from .vault import Conflit, Invalide, aujourdhui

LONGUEUR = 300  # une ligne reste une ligne : au-delà, c'est une tâche
FERMEES = ("fait", "cloture", "abandonne")


def _texte(brut: str) -> str:
    texte = " ".join(str(brut or "").split())
    if not texte:
        raise Invalide(langues.t("serveur.lignes.texte_requis"))
    if len(texte) > LONGUEUR:
        raise Invalide(langues.t("serveur.lignes.trop_longue", max=LONGUEUR))
    return texte


def _index(lignes: list[dict], i) -> int:
    if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(lignes):
        raise Invalide(langues.t("serveur.lignes.inconnue"))
    return i


def _appliquer(vault, ident: str, f) -> list[dict]:
    """Applique `f(lignes)` à la liste lue dans le fichier, puis la réécrit (bloc seul) ; renvoie la liste."""
    vault.tache(ident)
    sortie: list[dict] = []

    def transformer(texte: str) -> str:
        lignes = fiches.lire_lignes(texte)
        f(lignes)
        sortie.extend(lignes)
        return fiches.modifier_cles(fiches.ecrire_lignes(texte, lignes), {"updated": aujourdhui()})
    vault.reecrire(ident, transformer)
    return sortie


def ajouter(vault, ident: str, texte: str, auteur: str = "moi", lien: str = "", fait: bool = False) -> list[dict]:
    ligne = {"fait": bool(fait), "texte": _texte(texte), "date": aujourdhui().isoformat(),
             "auteur": "ia" if auteur == "ia" else "moi", "lien": " ".join(str(lien or "").split())}
    return _appliquer(vault, ident, lambda lignes: lignes.append(ligne))


def basculer(vault, ident: str, i) -> list[dict]:
    def f(lignes):
        lignes[_index(lignes, i)]["fait"] ^= True
    return _appliquer(vault, ident, f)


def retirer(vault, ident: str, i) -> list[dict]:
    def f(lignes):
        del lignes[_index(lignes, i)]
    return _appliquer(vault, ident, f)


def promouvoir(moteur, ident: str, i) -> dict:
    """Ligne -> tâche fille (même projet, nature déduite ou héritée de la mère) ; la ligne quitte la liste."""
    vault = moteur.vault
    mere = vault.tache(ident)
    lignes = fiches.lire_lignes(fiches.lire(mere.chemin))
    ligne = lignes[_index(lignes, i)]
    titre = ligne["texte"]
    nouvelle = moteur.creer(titre, langues.t("serveur.lignes.promue_description", mere=mere.titre), None, ident)
    genre = rangement.deduire(titre) or rangement.nature_de(mere)
    if genre:
        vault.modifier(nouvelle, {"genre": genre})
    if ligne["fait"]:
        vault.poser_statut(nouvelle, "fait", humain=True)
    return {"id": nouvelle, "lignes": retirer(vault, ident, i)}


def en_ligne(moteur, ident: str, vers: str | None = None) -> dict:
    """Tâche -> ligne de `vers` (par défaut sa mère) ; la tâche est close, jamais supprimée (lien conservé)."""
    vault = moteur.vault
    t = vault.tache(ident)
    cible = vers or vault.detail(ident)["parent"]
    if not cible or cible == ident:
        raise Invalide(langues.t("serveur.lignes.sans_cible"))
    cible_t = vault.tache(cible)
    if cible in vault.descendance(ident):
        raise Conflit(langues.t("serveur.lignes.cible_descendante"))
    if any(vault.ouverte(vault.tache(k)) for k in vault.enfants(ident)):
        raise Conflit(langues.t("serveur.lignes.enfants_ouverts"))
    if moteur.etat_de(ident) in ("en_cours", "en_file"):
        raise Conflit(langues.t("serveur.lignes.en_cours"))
    ferme = t.statut in FERMEES
    auteur = "moi" if executant.humain(t) else "ia"
    lignes = ajouter(vault, cible, t.titre, auteur, f"[[{t.chemin.stem}]]", ferme)
    if not ferme:
        vault.poser_statut(ident, "cloture", humain=True)
    vault.consigner(ident, "Devenue ligne", f"- {aujourdhui().isoformat()} : ligne de [[{cible_t.chemin.stem}]]")
    moteur.publier("arbre")
    return {"vers": cible, "lignes": lignes}
