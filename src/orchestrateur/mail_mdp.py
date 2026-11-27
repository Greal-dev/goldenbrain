"""Saisie sécurisée du mot de passe d'application de la messagerie, dans un terminal du poste.

Rôle : `saisir` demande le mot de passe sans l'afficher (une étoile par caractère, `telegram_jeton.lire_masque`),
l'essaie (connexion IMAP), l'enregistre dans le coffre du poste et confirme ; `argv`/`commande` donnent la
commande exacte que les Réglages montrent puis lancent (`telegram_jeton.ouvrir_terminal`).
Frontières : aucun agent, aucun harnais ; le mot de passe ne passe que par le clavier, le coffre et la connexion
IMAP ; jamais affiché, journalisé ni renvoyé à l'interface.
Invariants portés : INV-INSTALL-1 (commande exacte), INV-MAIL-1.
"""

from __future__ import annotations

import sys

from . import coffre, mail_imap, telegram_jeton
from .config import RACINE_DEPOT

ESSAIS = 3


def argv(config) -> list[str]:
    r = [sys.executable, str(RACINE_DEPOT / "orch.py"), "messagerie-mdp", "--pause"]
    return r + ["--config", str(config.chemin)] if config.chemin else r


def commande(config) -> str:
    return " ".join(f'"{x}"' if " " in x else x for x in argv(config))


def saisir(config, lire=telegram_jeton.lire_masque, sortie=print, pause=None, essais: int = ESSAIS) -> int:
    """0 si le mot de passe est essayé puis enregistré ; on redemande jusqu'à `essais` fois."""
    cpt = mail_imap.compte(config)
    try:
        if not cpt.adresse:
            sortie("Adresse de messagerie absente : renseignez-la d'abord dans Réglages → Messagerie.")
            return 1
        sortie(f"Compte : {cpt.adresse}")
        for n in range(1, essais + 1):
            try:
                mdp = lire("Mot de passe d'application (une étoile par caractère ; Entrée pour valider) : ").replace(" ", "")
            except (EOFError, KeyboardInterrupt):
                sortie("Saisie interrompue : rien n'est enregistré.")
                return 1
            reste = f" Nouvel essai ({n + 1}/{essais})." if n < essais else ""
            if not mdp:
                sortie("Aucun mot de passe saisi : rien n'est enregistré." + reste)
                continue
            boite = mail_imap.Boite(cpt, mdp)
            try:
                boite.tester()
            except mail_imap.ErreurMail as e:
                sortie(f"Connexion refusée : {str(e).replace(mdp, '•••')}. Rien n'est enregistré." + reste)
                continue
            finally:
                boite.fermer()
            try:
                coffre.proteger(mdp, cpt.fichier_mdp)
            except OSError as e:
                sortie(f"Enregistrement impossible : {str(e).replace(mdp, '•••')}")
                return 1
            sortie(f"mot de passe enregistré pour {cpt.adresse}")
            return 0
        return 1
    finally:
        if pause:
            try:
                pause("Appuyez sur Entrée pour fermer cette fenêtre. ")
            except (EOFError, KeyboardInterrupt):
                pass

