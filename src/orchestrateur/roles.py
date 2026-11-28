"""Moteurs par rôle : quel harnais et quel modèle pour un tour assistant ou temporaire.

Rôle : résoudre `[moteurs_par_role]` (conseil, persona, jardinage, mandat, fiche, tri, notes ; `tache` reste le
travail principal, inchangé), lancer un tour avec repli journalisé, compter les tours par harnais et par rôle.
Frontières : n'écrit ni dans le vault ni dans le journal d'un tour (les appelants journalisent les
événements, y compris l'événement `repli`) ; ne connaît aucun format de harnais.
Invariants portés : INV-MOTEUR-2 (seule exception à INV-MOTEUR-1 : repli explicite et journalisé d'un
rôle assistant sur le moteur suivant de son ordre, jamais pour un moteur fixé par un persona ou une tâche),
INV-ECO-1 (un rôle réglé par famille suit le curseur et l'équilibrage), INV-QUOTA-1 (secours unique sur
quota épuisé, y compris pour un moteur fixé : revue de la validation automatique).
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from typing import AsyncIterator, Callable

from . import echecs
from .config import ROLES, ConfigRole
from .harnais import Evenement
from .harnais.processus import resoudre

log = logging.getLogger(__name__)
QUOTA = echecs.QUOTA  # INV-QUOTA-1 : une seule reconnaissance du quota (« usage limit » d'OpenCode compris)
PANNE_S = 600  # un harnais en erreur de quota est évité d'emblée pendant ce délai
ASSISTANTS = tuple(r for r in ROLES if r != "tache")
# Rôle sans section dans `config.toml` : réglage par défaut (INV-EXECUTANT-3 : outil de rédaction économique).
DEFAUTS = {"notes": ConfigRole(famille="rapide"), "rex": ConfigRole(famille="opus")}


@dataclass
class Choix:
    harnais: str
    modele: str
    repli: tuple[tuple[str, str], ...] = ()  # (harnais, modèle) suivants, dans l'ordre ; vide = pas de repli
    secours: bool = field(default=True, compare=False)  # INV-QUOTA-1 : faux quand le rôle est réglé `repli = false`


class Roles:
    def __init__(self, config, registre: dict):
        self.config = config
        self.registre = registre
        self.tours: Counter[tuple[str, str]] = Counter()  # (harnais, rôle) -> tours lancés
        self.replis: deque[dict] = deque(maxlen=20)
        self.en_panne: dict[str, float] = {}
        self.economie = None  # posé par `economie.Economie` : curseur et équilibrage (INV-ECO-1)
        self.quota = None  # posé par `quota.Quotas` : secours sur quota épuisé (INV-QUOTA-1)

    # --- résolution --------------------------------------------------------------------------
    def choisir(self, role: str, explicite: str = "", modele: str = "",
                defaut: tuple[str, str] = ("", ""), prefere: str = "") -> Choix | None:
        """Moteur d'un rôle assistant, ou None (= moteur habituel de l'appelant).

        `explicite` (harnais fixé par un persona) l'emporte et supprime le repli (INV-MOTEUR-1).
        `defaut` : réglage hérité de l'appelant (ex. `[conseil] harnais, modele`) quand le rôle n'est pas réglé.
        `prefere` : harnais d'une conversation déjà ouverte, essayé en premier : l'ordre des crédits ne
        s'applique qu'au premier tour d'une conversation.
        """
        cfg = self.config.moteurs_par_role.get(role) or DEFAUTS.get(role)
        if explicite:
            return Choix(explicite, modele, secours=False)  # INV-MOTEUR-1 : moteur fixé, jamais secouru
        if cfg and cfg.harnais:
            repli = (cfg.repli_harnais or self.config.moteur.harnais_defaut, cfg.repli_modele)
            chaine = [(cfg.harnais, cfg.modele)] + ([repli] if cfg.repli and repli[0] != cfg.harnais else [])
        elif cfg and cfg.famille:
            # INV-ECO-1 : une conversation de rôle est neuve : famille décalée par le curseur,
            # fournisseur le moins tendu en tête. Un harnais fixé (persona, réglage) n'y passe pas.
            famille, ordre = (self.economie.pour_role(cfg.famille) if self.economie
                              else (cfg.famille, self.config.credits[cfg.famille]))
            # INV-QUOTA-1 : un harnais absent du poste n'entre jamais dans la chaîne.
            chaine = [(h, m) for h in ordre if self.installe(h)
                      and (m := self.config.harnais.get(h, {}).get("familles", {}).get(famille))]
            chaine = chaine if cfg.repli else chaine[:1]
        elif defaut[0]:
            chaine = [defaut]
        else:
            return None
        if prefere and any(h == prefere for h, _ in chaine):
            chaine.sort(key=lambda c: c[0] != prefere)  # tri stable : le reste garde son ordre
        return Choix(*chaine[0], tuple(chaine[1:]), not cfg or cfg.repli) if chaine else None

    def disponible(self, nom: str) -> str:
        """Vide si le harnais est utilisable, sinon le motif."""
        if nom not in self.registre:
            return f"harnais inconnu : {nom}"
        if self.en_panne.get(nom, 0) > time.monotonic():
            return f"harnais {nom} en erreur de quota (évité {PANNE_S // 60} min)"
        return self._absent(nom)

    def installe(self, nom: str) -> bool:
        """Faux seulement si c'est un harnais en ligne de commande dont l'exécutable manque au poste."""
        return not self._absent(nom)

    def _absent(self, nom: str) -> str:
        if nom not in self.registre:
            return ""  # inconnu : `disponible` le dit ; ici, seul l'exécutable manquant compte
        try:
            # Les adaptateurs en ligne de commande portent `commande` ; un faux ou un harnais interne, non.
            commande = getattr(self.registre[nom](self.config.harnais.get(nom, {})), "commande", "")
            if commande:
                resoudre(commande)
        except (FileNotFoundError, OSError) as e:
            return f"harnais indisponible : {e}"
        return ""

    # --- journal et compteurs ----------------------------------------------------------------
    def compter(self, harnais: str, role: str) -> None:
        self.tours[(harnais, role)] += 1

    def noter_repli(self, role: str, de: str, vers: str, motif: str) -> Evenement:
        if QUOTA.search(motif):
            self.en_panne[de] = time.monotonic() + PANNE_S
            if self.quota:
                self.quota.noter(de, motif)  # INV-QUOTA-1 : compte écarté jusqu'à sa reprise
        trace = {"role": role, "de": de, "vers": vers, "motif": motif[:300]}
        self.replis.append({**trace, "date": time.strftime("%Y-%m-%dT%H:%M:%S")})
        log.warning("repli du rôle %s : %s -> %s (%s)", role, de, vers, motif[:200])
        return Evenement("repli", texte=f"{role} : {de} -> {vers} ({motif[:200]})", brut={"type": "repli", **trace})

    def public(self) -> dict:
        return {"tours": [{"harnais": h, "role": r, "tours": n}
                          for (h, r), n in sorted(self.tours.items())],
                "replis": list(self.replis),
                "roles": {r: self._moteurs_du_role(r) for r in self.config.moteurs_par_role
                          if self.choisir(r)},
                "credits": self.config.credits}

    def _moteurs_du_role(self, role: str) -> dict:
        c = self.choisir(role)
        return {"famille": self.config.moteurs_par_role[role].famille, "harnais": c.harnais,
                "modele": c.modele, "moteurs": [[c.harnais, c.modele], *map(list, c.repli)]}

    # --- tour d'un rôle dans le moteur (jardinage, mandat) ----------------------------------------
    def pour_envoi(self, envoi) -> Choix | None:
        return self.choisir(envoi.role) if envoi.role in ASSISTANTS else None

    def reprendre(self, moteur, ident: str, envoi, choix: Choix | None, final, erreur: str | None,
                  outils: bool, arrete: bool) -> bool:
        """Tour de rôle en échec avant tout résultat : le remet en tête de file sur le moteur de la tâche."""
        if not (choix and choix.repli and erreur and not final and not outils and not arrete
                and not moteur.ferme):
            return False
        moteur.files[ident].appendleft(replace(envoi, role="tache"))
        self.noter_repli(envoi.role, choix.harnais, "moteur de la tâche", erreur)
        return True

    # --- tour d'un rôle hors boucle de tâche (conseil, persona) ------------------------------
    async def lancer(self, role: str, choix: Choix, message: str, *, consigne: str, env: dict[str, str],
                     sur_harnais: Callable[[object, str], None],
                     session: Callable[[str], str | None] = lambda nom: None) -> AsyncIterator[Evenement]:
        """Flux d'un tour : essaie le moteur du rôle, puis son repli s'il échoue avant tout résultat.

        `sur_harnais(harnais, nom)` est appelé avant chaque lancement (l'appelant y garde le harnais à
        arrêter). Un échec du dernier candidat remonte comme événement `erreur`. L'événement `repli`
        est destiné au journal. Pas de repli une fois un outil lancé (effet de bord possible).
        """
        candidats, secouru = [(choix.harnais, choix.modele), *choix.repli], False

        def secourir(nom: str, motif: str) -> bool:
            # INV-QUOTA-1 : le dernier moteur en quota épuisé cède UNE fois au meilleur autre compte.
            nonlocal secouru
            if secouru or not choix.secours or not self.quota or not QUOTA.search(motif or ""):
                return False
            self.quota.noter(nom, motif)
            famille = getattr(self.config.moteurs_par_role.get(role), "famille", "")
            s = self.quota.secours(famille or self.config.economie.famille_defaut, {h for h, _ in candidats})
            if s:
                candidats.append(s)
                secouru = True
            return bool(s)

        for i, (nom, modele) in enumerate(candidats):
            dernier = i == len(candidats) - 1
            motif = self.disponible(nom)
            if motif and dernier:
                dernier = not secourir(nom, motif)
            if not motif:
                outil, erreur, harnais = False, "", None
                try:
                    harnais = self.registre[nom](self.config.harnais.get(nom, {}))
                    sur_harnais(harnais, nom)
                    ouverture = session(nom)
                    texte = message
                    if not ouverture and not getattr(harnais, "consigne_native", True):
                        texte = consigne + "\n\n" + message
                    self.compter(nom, role)
                    async for ev in harnais.lancer(texte, session=ouverture, deriver=False,
                                                   consigne=consigne, env=env, modele=modele):
                        outil = outil or ev.type == "outil"
                        if ev.type == "erreur" and not outil and (not dernier or secourir(nom, ev.texte)):
                            erreur = ev.texte or "erreur du harnais"
                            break
                        yield ev
                        if ev.type == "fin":
                            return
                except (TimeoutError, GeneratorExit):
                    raise
                except Exception as e:
                    if dernier or outil:
                        raise
                    erreur = f"{type(e).__name__}: {e}"
                if not erreur:
                    return  # flux terminé sans erreur ni fin : l'appelant constate l'absence de résultat
                motif = erreur
                if harnais:
                    await harnais.arreter()
            if i < len(candidats) - 1:
                yield self.noter_repli(role, nom, candidats[i + 1][0], motif)
            else:
                raise RuntimeError(motif)  # dernier moteur indisponible : INV-MOTEUR-1
