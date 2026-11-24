"""Premiers pas : quels assistants IA sont prêts sur ce poste, comment installer celui qui manque.

Rôle : au premier lancement, dresser la liste des assistants IA connus (catalogue d'`installation.py`) avec,
pour chacun, installé ou non, connecté ou non, la commande à copier et la page officielle ; dire lesquels
GoldenBrain peut piloter tout de suite (démonstration) ; retenir que les premiers pas sont faits ou différés.
Routes sous `/api/accueil/premiers-pas` : réservées au poste par la garde de l'accueil (INV-ACCUEIL-1).
Frontières : diagnostic seulement — n'installe ni ne connecte rien (l'installation pas à pas reste
`api_installation.py`) ; ne crée aucune tâche (la démonstration passe par `POST /api/taches`).
Invariants portés : INV-PREMIERS-PAS-1.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter

from . import cerveau, fiches, installation, langues

ROUTE = "/api/accueil/premiers-pas"
# Pages officielles, ouvertes par l'utilisateur lui-même ; GoldenBrain ne les télécharge jamais.
LIENS = {
    "claude": "https://docs.anthropic.com/en/docs/claude-code/setup",
    "codex": "https://github.com/openai/codex",
    "copilot": "https://github.com/features/copilot/cli",
    "opencode": "https://opencode.ai/",
    "agy": "https://antigravity.google/",
}


def assistants(assistant: installation.Assistant, registre) -> list[dict]:
    """INV-PREMIERS-PAS-1 : un état par assistant connu, lu sur le poste ; rien n'est lancé hormis
    la vérification de connexion de l'outil officiel déjà installé (`auth status`, sans saisie)."""
    sortie = []
    for ident in installation.HARNAIS_CHOISIS:
        ligne = assistant.ligne(ident)
        installe = ligne["etat"] == "ok"
        connexion, aide = "", ""
        if installe and ident + "-connexion" in assistant.ids():
            c = assistant.ligne(ident + "-connexion")
            connexion = c["etat"]
            aide = c["instructions"] or (langues.t("serveur.premiers_pas.lancer", commande=c["commande"]) if c["commande"] else "")
        sortie.append({"id": ident, "libelle": ligne["libelle"], "installe": installe, "etat": ligne["etat"],
                       "commande": ligne["commande"], "instructions": ligne["instructions"], "attend": ligne["attend"],
                       "lien": LIENS.get(ident, ""), "connexion": connexion, "aide_connexion": aide,
                       "pilotable": installe and ident in registre and connexion != "a_connecter"})
    # Un assistant déclaré à la main dans la configuration, hors catalogue : GoldenBrain ne sait pas le
    # détecter ; il a été posé sciemment, il est proposé tel quel.
    for nom in registre:
        if nom not in installation.PAR_ID:
            sortie.append({"id": nom, "libelle": nom, "installe": True, "etat": "ok", "commande": "", "instructions": "",
                           "attend": [], "lien": "", "connexion": "", "aide_connexion": "", "pilotable": True})
    return sortie


def routes(config, moteur, vault) -> APIRouter:
    r = APIRouter()
    chemin = config.donnees / "etat" / "premiers-pas.json"

    def etat() -> str:
        try:
            return str(json.loads(chemin.read_text(encoding="utf-8")).get("etat") or "")
        except (OSError, ValueError):
            return ""

    @r.get(ROUTE)
    async def lire():
        # Léger, lu à chaque ouverture de l'interface : aucun outil n'est interrogé ici.
        return {"propose": not etat() and cerveau.parcours_ouvert(config, not vault.index()[0]), "etat": etat() or "jamais"}  # une fois, vault vide

    @r.get(ROUTE + "/assistants")
    async def diagnostic():
        liste = await asyncio.to_thread(assistants, installation.Assistant(), moteur.registre)
        return {"assistants": liste, "defaut": config.moteur.harnais_defaut}

    @r.post(ROUTE + "/fait")
    async def fait():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fiches.ecrire_atomique(chemin, json.dumps({"etat": "fait"}))
        return {"etat": "fait"}

    return r
