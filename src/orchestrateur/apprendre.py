"""Mode « Apprendre » : l'agent explique ce qu'il fait, en termes simples, et clôt par « Ce que vous pouvez retenir ».

Rôle : décider si le mode est actif pour une tâche et fournir le complément de consigne correspondant.
Frontières : ne lance aucun tour, n'écrit rien dans le vault ; l'affichage des encadrés est dans le web
(`apprendre.js`, rendu Markdown des callouts) ; le champ `retenir` de la fiche est dans `fiches`.
Invariants portés : INV-APPRENDRE-1 (inactif = consigne strictement inchangée ; une tâche pose
`apprendre: oui|non` dans son frontmatter, qui l'emporte sur `[apprendre] actif`), INV-LANGUE-1.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass
class ConfigApprendre:
    """Mode « Apprendre » (INV-APPRENDRE-1) : actif pour toutes les tâches, sauf celles qui posent `apprendre: non`."""
    actif: bool = False

    def __post_init__(self):
        if not isinstance(self.actif, bool):
            raise ValueError("apprendre.actif : vrai ou faux")


VALEURS = {"oui": True, "non": False}


def texte_consigne() -> str:
    """Consigne ajoutée aux agents quand le mode est actif, dans la langue réglée (INV-LANGUE-1)."""
    from . import langues  # import tardif : `config` importe ce module, et `langues` importe `config`
    return langues.t("serveur.apprendre.consigne")


def actif(config, fm: dict) -> bool:
    """Réglage de la tâche s'il y en a un, sinon réglage général."""
    pose = str(fm.get("apprendre") or "").strip().lower()
    return VALEURS.get(pose, config.apprendre.actif)


def consigne(config, fm: dict) -> str:
    """Complément de consigne (avec son séparateur), vide quand le mode est inactif."""
    return f"\n\n{texte_consigne()}" if actif(config, fm) else ""
