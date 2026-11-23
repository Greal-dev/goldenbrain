"""Assistant par défaut absent du poste : le dire avant de lancer, au lieu de lancer et d'échouer.

Rôle : garde posée à la création d'une tâche lancée (l'envoi d'un message garde son repli propre, INV-QUOTA-1) ; si l'assistant qui doit travailler
(demandé, propre à la tâche, sinon `moteur.harnais_defaut`) manque au poste et qu'aucune bascule automatique
(INV-QUOTA-1) ne le remplacerait, refuse avec le diagnostic : lequel manque, lesquels sont prêts, où s'y prendre.
Frontières : ne détecte rien lui-même (`roles.installe`), n'installe rien (INV-PREMIERS-PAS-1), n'écrit rien.
Invariants portés : INV-PREMIERS-PAS-2.
"""

from __future__ import annotations

from . import langues
from .vault import Conflit


def exiger(moteur, ident: str | None, harnais: str | None, interne: bool = False) -> None:
    """Lève `Conflit` (409) si l'assistant effectif est absent et sans remplaçant ; sinon ne fait rien."""
    if interne:
        return  # revue, mandat : leurs rôles ont leurs propres replis (roles.py)
    nom = harnais or (str(moteur.vault.tache(ident).fm.get("harnais") or "") if ident else "") \
        or moteur.config.moteur.harnais_defaut
    if nom not in moteur.registre or moteur.roles.installe(nom):
        return
    eco = moteur.config.economie
    if eco.quota_bascule and moteur.quota.secours(eco.famille_defaut, {nom}):
        return  # le tour basculera seul sur un autre assistant
    prets = [n for n in moteur.registre if n != nom and moteur.roles.installe(n)]
    raise Conflit(langues.t("serveur.assistant.absent", nom=nom, prets=", ".join(prets) or "—"))
