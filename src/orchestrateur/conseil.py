"""Avis d'un agent rapide avant de promouvoir une tâche ou de réduire un projet (lot 7).

Rôle : rassembler les faits utiles, lancer une conversation éphémère du harnais de `[conseil]`
sous un délai strict, lire le bloc `<conseil>` rendu.
Frontières : aucune écriture dans le vault (lecture de l'index et du dossier seulement) ; aucune
session gardée ; hors de `simultanes_max` ; seul le journal du tour est écrit (`<donnees>`).
Invariants portés : INV-EXEC-4 (journal du tour), INV-MOTEUR-1 (harnais inconnu ou
indisponible : `indisponible`), INV-MOTEUR-2 (repli du rôle « conseil », journalisé).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from contextlib import aclosing
from dataclasses import asdict

from . import fiches, langues
from .vault import Invalide

log = logging.getLogger(__name__)
ACTIONS = ("promouvoir", "reduire")
AVIS = {"favorable": "favorable", "defavorable": "defavorable", "défavorable": "defavorable"}


def analyser(texte: str) -> tuple[str, str] | None:
    """Dernier bloc `<conseil>` : (avis, motif) ; None s'il manque ou si l'avis est illisible."""
    blocs = re.findall(r"<conseil>(.*?)</conseil>", texte or "", flags=re.S)
    if not blocs:
        return None
    avis = re.search(r"^\s*avis\s*:\s*(\S+)", blocs[-1], flags=re.M)
    motif = re.search(r"^\s*motif\s*:\s*(.*)$", blocs[-1], flags=re.M)
    valeur = AVIS.get(avis.group(1).casefold()) if avis else None
    return (valeur, motif.group(1).strip() if motif else "") if valeur else None


def faits(vault, action: str, tache: str | None, conteneur: str | None) -> str:
    """Message du conseil. Lit l'index et le dossier : hors de la boucle d'événements."""
    if action == "promouvoir":
        if not tache:
            raise Invalide(langues.t("serveur.conseil.tache_requise"))
        t = vault.tache(tache)
        f = fiches.lire_fiche(fiches.lire(t.chemin))
        sous = [f"- [{'x' if s['fait'] else ' '}] {s['texte']}" for s in f["sous_taches"]]
        return "\n".join([
            f"Action envisagée : élever la tâche « {t.titre} » en projet.",
            f"Fiche — fait : {f['fait']} ; situation : {f['situation']} ; reste : {f['reste']} ;"
            f" prochain pas : {f['prochain_pas']}",
            "Sous-tâches :", *(sous or ["- aucune"]),
            f"Tâches enfants : {len(vault.enfants(tache))}",
            "Description de la tâche :",
            fiches.corps_sans_fiche(fiches.lire(t.chemin)) or "(vide)"])
    if action == "reduire":
        if not conteneur:
            raise Invalide(langues.t("serveur.conseil.projet_requis"))
        c = vault.conteneur(conteneur)
        taches = [t for t in vault.index()[0].values() if t.conteneur == c.id]
        ouvertes = [t for t in taches if vault.ouverte(t)]
        dossier = vault.racine / c.id
        propres = {t.chemin.resolve() for t in taches} | {(dossier / vault.cfg.contexte).resolve()}
        autres = sum(p.resolve() not in propres for p in dossier.rglob("*.md"))
        return "\n".join([
            f"Action envisagée : réduire le projet « {c.titre} » en une seule tâche.",
            f"Tâches ouvertes : {len(ouvertes)} ; fermées : {len(taches) - len(ouvertes)}",
            *(f"- {t.titre} ({t.statut or '?'})" for t in taches),
            f"Autres notes du dossier : {autres}"])
    raise Invalide(langues.t("serveur.conseil.action_attendue"))


def _resultat(avis: str, motif: str, debut: float) -> dict:
    return {"avis": avis, "motif": motif, "duree_s": round(time.monotonic() - debut, 2)}


async def avis(moteur, action: str, tache: str | None = None,
               conteneur: str | None = None) -> dict:
    debut = time.monotonic()
    cfg = moteur.config.conseil
    if action not in ACTIONS:
        raise Invalide(langues.t("serveur.conseil.action_attendue"))
    if not cfg.actif or not moteur.config.interface.actif("conseil"):  # INV-INTERFACE-1
        return _resultat("indisponible", langues.t("serveur.conseil.desactive"), debut)
    message = await asyncio.to_thread(faits, moteur.vault, action, tache, conteneur)
    # INV-MOTEUR-2 : le rôle « conseil » peut se replier, journalisé ; sans réglage, `[conseil]` seul.
    choix = moteur.roles.choisir("conseil", defaut=(cfg.harnais, cfg.modele))
    final, erreur, courant = None, None, []
    try:
        # INV-EXEC-4 : journal du tour ; aucune session gardée (conversation éphémère).
        with moteur._journal(f"conseil-{action}") as journal:
            flux = moteur.roles.lancer("conseil", choix, message, consigne=cfg.consigne, env={},
                                       sur_harnais=lambda h, nom: courant.append(h))
            async with aclosing(flux), asyncio.timeout(cfg.delai_s):
                async for ev in flux:
                    journal.write(json.dumps(ev.brut or asdict(ev), ensure_ascii=False) + "\n")
                    if ev.type == "fin":
                        final = ev.texte
                    elif ev.type == "erreur":
                        erreur = ev.texte or langues.t("serveur.conseil.erreur_assistant")
    except TimeoutError:
        erreur = langues.t("serveur.conseil.delai", delai=cfg.delai_s)
    except Exception as e:  # harnais introuvable ou en échec : jamais d'erreur bloquante
        erreur = langues.t("serveur.conseil.indisponible", erreur=f"{type(e).__name__}: {e}")
    finally:
        for harnais in courant:
            # Délai dépassé ou fin : le processus est arrêté, aucun orphelin.
            await asyncio.shield(harnais.arreter())
    if erreur:
        return _resultat("indisponible", erreur, debut)
    lu = analyser(final or "")
    if not lu:
        return _resultat("indisponible", langues.t("serveur.conseil.illisible"), debut)
    return _resultat(lu[0], lu[1], debut)
