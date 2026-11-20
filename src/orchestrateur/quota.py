"""Quota épuisé : comptes écartés jusqu'à leur reprise, bascule unique d'un tour sur un autre moteur.

Rôle : retenir quel harnais (compte) a épuisé son quota et jusqu'à quand (`etat/quotas.json`) ;
choisir un moteur de secours (crédits de la famille, équilibrage du mode intelligent, comptes
épuisés exclus) ; relancer UNE fois le tour échoué d'une tâche dont le moteur n'est pas imposé ; idem pour un
harnais absent du poste (exécutable introuvable).
Frontières : écrit la fiche par `sessions.changement` (reprise avec préambule, `moteur_impose` retiré),
remet l'envoi en tête de file ; ne lance aucun harnais lui-même ; l'attente d'un moteur imposé
reste à `reveil` (INV-EXEC-10).
Invariants portés : INV-QUOTA-1 (au plus une bascule par tour et par compte, journalisée, jamais
pour un moteur imposé).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import replace

from . import echecs, economie, fiches, langues, sessions

log = logging.getLogger(__name__)
SANS_HEURE_S = 1800  # un quota sans heure de reprise écarte le compte 30 minutes


class Quotas:
    def __init__(self, moteur):
        self.m = moteur
        self.fichier = moteur.config.donnees / "etat" / "quotas.json"
        try:
            lu = json.loads(self.fichier.read_text("utf-8"))
        except (OSError, ValueError):
            lu = {}
        self.epuises: dict[str, str] = {str(h): str(a) for h, a in lu.items()} if isinstance(lu, dict) else {}
        self.essais: dict[str, set[str]] = {}  # tâche -> harnais déjà essayés depuis le dernier succès
        moteur.roles.quota = self  # INV-QUOTA-1 : secours des tours de rôle (revues, personas)

    # --- comptes épuisés -------------------------------------------------------------------
    def noter(self, harnais: str, motif: str) -> None:
        now = dt.datetime.now()
        jusqua = echecs.heure_reprise(motif, now) or now + dt.timedelta(seconds=SANS_HEURE_S)
        self.epuises[harnais] = jusqua.isoformat(timespec="seconds")
        self._sauver()

    def epuise(self, harnais: str) -> bool:
        a = self.epuises.get(harnais)
        try:
            if a and dt.datetime.fromisoformat(a) > dt.datetime.now():
                return True
        except ValueError:
            pass
        if a:
            self.epuises.pop(harnais, None)
            self._sauver()
        return False

    def _sauver(self) -> None:
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.fichier, json.dumps(self.epuises))
        except OSError as e:
            log.warning("quotas non persistés : %s", e)

    def public(self) -> dict[str, str]:
        """Comptes épuisés et heure de reprise (jauge de l'interface)."""
        return {h: a for h, a in list(self.epuises.items()) if self.epuise(h)}

    # --- secours ---------------------------------------------------------------------------
    def secours(self, famille: str, exclure: set[str]) -> tuple[str, str] | None:
        """Meilleur autre moteur : crédits de la famille d'abord, le moins tendu en tête (INV-ECO-1)."""
        cfg = self.m.config
        ordre = [*cfg.credits.get(famille, []), *cfg.harnais]
        eco = self.m.economie
        vus = [h for i, h in enumerate(ordre) if h not in ordre[:i] and h in self.m.registre
               and h in cfg.harnais and h not in exclure and not self.epuise(h)
               and not self.m.roles.disponible(h)]
        if not vus:
            return None
        tensions = {h: eco.tension(h) for h in vus}
        vus.sort(key=lambda h: (tensions[h] is None, tensions[h][0] if tensions[h] else 0))
        h = vus[0]
        return h, str((cfg.harnais[h].get("familles") or {}).get(famille, ""))

    # --- bascule d'un tour de tâche ----------------------------------------------------------
    def basculer(self, ident: str, envoi, erreur: str | None, nom: str, arrete: bool) -> bool:
        """Fin d'un tour de tâche : sur quota épuisé ou harnais absent du poste d'un moteur non imposé,
        relance unique ailleurs."""
        absent = bool(erreur) and echecs.est_introuvable(erreur)
        if arrete or not erreur or not (absent or echecs.est_quota(erreur)):
            self.essais.pop(ident, None)  # tour abouti ou autre échec : nouvelle chance au prochain quota
            return False
        if envoi.role not in ("", "tache"):
            return False
        if not absent:
            self.noter(nom, erreur)  # un harnais absent n'a pas de quota : `secours` l'écarte (disponible)
        essais = self.essais.setdefault(ident, set())
        essais.add(nom)
        try:
            t = self.m.vault.tache(ident)
        except Exception:  # noqa: BLE001 — tâche disparue : rien à relancer
            return False
        # Un modèle posé à la création (assistant Telegram, sous-tâche) n'impose rien à un harnais absent :
        # rien n'y tournera jamais ; seule la case « moteur imposé » retient (INV-MOTEUR-1).
        pose = str(t.fm.get("modele") or "")
        if (not self.m.config.economie.quota_bascule or self.m.ferme or economie.impose(t.fm)
                or (pose and not absent)):
            return False  # INV-QUOTA-1 : moteur imposé → attente de la reprise (INV-EXEC-10)
        familles = self.m.config.harnais.get(nom, {}).get("familles") or {}
        famille = (next((f for f, m in familles.items() if str(m) == pose), "") if pose else "") \
            or self.m.economie.decider(t).famille or self.m.config.economie.famille_defaut
        if not (choix := self.secours(famille, essais)):
            return False
        vers, modele = choix
        # Modèle laissé au curseur (`None`) : un modèle écrit vaudrait « posé à la main » ; sauf s'il
        # l'était déjà : il suit alors la famille sur le secours.
        maj = sessions.changement(t, self.m.sessions, vers, (modele or "") if pose else None,
                                  self.m.config.moteur.harnais_defaut)
        maj["moteur_impose"] = None  # bascule automatique : le curseur garde la main
        motif = "harnais non installé" if absent else "quota épuisé"
        maj["moteur_motif"] = f"bascule sur {motif} : {nom} -> {vers}"
        self.m.vault.modifier(ident, maj)
        self.m.annuler_reveil(ident)
        sur = f"{vers} ({modele})" if modele else vers
        action = langues.t("serveur.quota.relance_absent", sur=sur) if absent \
            else langues.t("serveur.quota.relance", sur=sur)
        journal = langues.t("serveur.quota.journal_absent", message=echecs.message(erreur), sur=sur) if absent \
            else langues.t("serveur.quota.journal", message=echecs.message(erreur), sur=sur)
        self.m._journaliser_echec(ident, erreur, journal)
        self.m.incidents.noter(ident, nom, erreur, action)
        self.m.files[ident].appendleft(replace(envoi, harnais=None, modele=None))
        self.m.publier("arbre")
        log.warning("bascule sur %s de %s : %s -> %s", motif, ident, nom, vers)
        return True
