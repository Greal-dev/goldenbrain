"""Coupures réseau : classement des erreurs, sonde, gel des agents, reprise spontanée au retour.

Rôle : reconnaître l'échec d'un tour dû au réseau (`est_reseau`), le confirmer par une sonde légère
(résolution DNS + connexion TCP vers les points d'accès de chaque fournisseur, aucune donnée
envoyée), geler ce qui dépend du fournisseur injoignable, sonder à intervalle régulier, puis
relancer chaque tour gelé dans sa conversation quand le fournisseur répond de nouveau.
Frontières : aucun harnais lancé ici (la reprise passe par `reprise._resoumettre` donc
`Moteur.soumettre`) ; aucune écriture vault ; aucun sondage hors d'une erreur réseau déjà vue.
Invariants portés : INV-RESEAU-1 (une erreur réseau n'est gelée que si la sonde la confirme ; un
tour vivant n'est jamais tué ; aucun départ vers un fournisseur injoignable), INV-RESEAU-2 (sonde
toutes les 2 min les 10 premières minutes, puis toutes les 5 min, et aussitôt au réveil d'une mise
en veille de la machine ; au retour, une seule reprise par tour gelé, dans l'ordre du classement
INV-ORDO-2), INV-RESEAU-3 (réseau perdu, quota épuisé
et panne d'un seul fournisseur se distinguent), INV-RESEAU-4 (chaque sonde et l'arrêt de la veille laissent une trace ; durée de gel mesurée),
INV-EXEC-1 (tour gelé persisté, repris au
redémarrage comme un tour interrompu).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from . import echecs, langues, ordonnancement, reprise
from .echecs import RESEAU  # noqa: F401  (motifs : voir `echecs.py`)
from .propositions import maintenant

log = logging.getLogger(__name__)
ETAT = "attente_reseau"
MOTIF_REPRISE = "coupure du réseau"
PAS_GUET_S = 5.0     # INV-RESEAU-2 : pas du guet de veille (la pause d'intervalle, monotone, ne compte pas la veille)
SEUIL_VEILLE_S = 30.0  # écart horloge murale / horloge monotone au-delà duquel la machine a dormi
INTERVALLE_DEPART_S = 1.0  # un départ retenu relit l'état chaque seconde (comme le poste, INV-POSTE-1)


def est_reseau(motif: str) -> bool:
    """Erreur de connexion, non un quota (INV-RESEAU-3) : le quota a son propre traitement."""
    return bool(motif) and not echecs.est_quota(motif) and bool(RESEAU.search(motif))


def intervalle(conf, ecoule_s: float) -> float:
    """INV-RESEAU-2 : intervalle court pendant `duree_courte_s`, puis long."""
    return conf.intervalle_court_s if ecoule_s < conf.duree_courte_s else conf.intervalle_long_s


def _cible(hote: str) -> tuple[str, int]:
    nom, _, port = hote.partition(":")
    return nom, int(port) if port else 443


async def sonde_reelle(hote: str, delai_s: float) -> bool:
    """Résolution DNS puis connexion TCP, aussitôt refermée : rien n'est envoyé."""
    nom, port = _cible(hote)
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(nom, port), delai_s)
    except (OSError, TimeoutError, asyncio.TimeoutError):
        return False
    w.close()
    return True


@dataclass
class Gele:
    envoi: object
    harnais: str
    depuis: str
    motif: str
    t0: float = 0.0  # horloge monotone du gel (durée mesurée à la reprise)


class Reseau:
    def __init__(self, moteur, sonde=sonde_reelle, dormir=asyncio.sleep, horloge=time.monotonic,
                 reel=time.time, guetter=asyncio.sleep):
        self.m, self.sonde, self.dormir, self.horloge = moteur, sonde, dormir, horloge
        self.reel, self.guetter = reel, guetter  # horloge murale (saute à la veille) ; pause du guet
        self.gele: dict[str, Gele] = {}  # tâche -> tour tombé en erreur réseau, message gardé
        self.retenus: set[str] = set()   # tâches dont le prochain départ attend le réseau
        self.hors: dict[str, str] = {}   # fournisseur (harnais) injoignable -> depuis (ISO)
        self.perdu_depuis = ""           # non vide : aucun fournisseur sondé ne répond
        self._t0 = self._gel_t0 = 0.0
        self._veille: asyncio.Task | None = None

    @property
    def conf(self):
        return self.m.config.reseau

    # --- sonde ---------------------------------------------------------------------------
    async def sonder(self) -> dict[str, bool]:
        """{harnais: joignable} pour les fournisseurs qui ont des points d'accès configurés."""
        hotes = {h: l for h, l in self.conf.hotes.items() if l}
        uniques = sorted({x for l in hotes.values() for x in l})
        rep = await asyncio.gather(*(self._sonder_un(x) for x in uniques), return_exceptions=True)
        vu = {x: r is True for x, r in zip(uniques, rep)}
        return {h: any(vu[x] for x in l) for h, l in hotes.items()}

    async def _sonder_un(self, hote: str):
        """Une sonde, tracée : hôte, résultat, durée (un gel resté sans trace n'a pu être expliqué)."""
        t = self.horloge()
        try:
            r = await self.sonde(hote, self.conf.delai_sonde_s)
        except Exception as e:  # compté comme injoignable par `sonder`
            r = e
        log.info("réseau : sonde %s -> %s en %.2f s%s", hote, "répond" if r is True else "muet",
                 self.horloge() - t, f" ({type(r).__name__}: {r})" if isinstance(r, Exception) else "")
        return r

    def _appliquer(self, res: dict[str, bool]) -> None:
        now, avant, tenait = maintenant(), (set(self.hors), self.perdu_depuis), self._tient()
        self.hors = {h: self.hors.get(h, now) for h, ok in res.items() if not ok}
        tout = bool(res) and not any(res.values())
        self.perdu_depuis = (self.perdu_depuis or now) if tout else ""
        if not tenait and self._tient():
            self._gel_t0 = self.horloge()
        elif tenait and not self._tient():  # levée : durée du gel, une ligne de mesure
            self.m.mesures.ajouter({"type": "gel", "date": now, "portee": "reseau", "harnais": sorted(avant[0]),
                                    "gel_s": round(self.horloge() - self._gel_t0, 1)})
        if (set(self.hors), self.perdu_depuis) != avant:
            log.warning("réseau : fournisseurs injoignables %s, perdu depuis %s",
                        sorted(self.hors) or "aucun", self.perdu_depuis or "—")
            self.m.publier("reseau")
            self.m.publier("arbre")

    def bloque(self, harnais: str) -> bool:
        """INV-RESEAU-1 : ce fournisseur est injoignable (ou, sans point d'accès connu, tout l'est)."""
        return harnais in self.hors or (bool(self.perdu_depuis) and not self.conf.hotes.get(harnais))

    def _tient(self) -> bool:
        return bool(self.hors or self.perdu_depuis)

    # --- gel -----------------------------------------------------------------------------
    async def signaler(self, ident: str, envoi, motif: str, harnais: str) -> bool:
        """Un tour vient d'échouer sur `motif`. Vrai : gelé (la sonde confirme que ce fournisseur est
        injoignable) ; faux : échec ordinaire, la sonde ne voit aucune coupure (INV-RESEAU-1)."""
        if not self.conf.actif or not est_reseau(motif):
            return False
        res = await self.sonder()
        self._appliquer(res)
        if not self.bloque(harnais):
            return False
        self.gele[ident] = Gele(envoi, harnais, maintenant(), motif, self.horloge())
        # INV-EXEC-1 : survit à un arrêt ; un gel n'est pas une reprise ratée, la marque tombe
        self.m.actifs[ident] = {**reprise.enregistrement(ident, envoi), "reprise": False}
        self.m._sauver_actifs()
        self.m.etats[ident] = ETAT
        self.m._journaliser_echec(
            ident, motif, langues.t("serveur.reseau.gele_journal", motif=" ".join(motif.split())[:300]))
        self.m.incidents.noter(ident, harnais, motif, langues.t("serveur.reseau.gele_action"))  # INV-INCIDENT-1
        self.m.publier("reseau")
        self.m.publier("arbre")
        self._lancer_veille()
        return True

    def oublier(self, ident: str) -> None:
        """L'humain arrête la tâche : plus de reprise automatique."""
        if self.gele.pop(ident, None) is not None:
            self.m.actifs.pop(ident, None)
            self.m._sauver_actifs()
            self.m.publier("reseau")

    async def attendre_depart(self, ident: str, envoi) -> None:
        """INV-RESEAU-1 : aucun tour ne démarre vers un fournisseur injoignable ; sans changement
        de l'état, rien n'est sondé ici (la veille s'en charge)."""
        h = self.harnais_de(ident, envoi)
        if not self.bloque(h):
            return
        self.retenus.add(ident)
        self.m.publier("reseau")
        try:
            while self.bloque(h):
                await asyncio.sleep(INTERVALLE_DEPART_S)
        finally:
            self.retenus.discard(ident)
            self.m.publier("reseau")

    def harnais_de(self, ident: str, envoi) -> str:
        try:
            fm = self.m.vault.tache(ident).fm
        except Exception:  # la tâche échouera lisiblement plus loin
            fm = {}
        return str(getattr(envoi, "harnais", None) or fm.get("harnais") or self.m.config.moteur.harnais_defaut)

    # --- reprise -------------------------------------------------------------------------
    def _lancer_veille(self) -> None:
        if self._veille is None or self._veille.done():
            self._t0 = self.horloge()
            self._veille = asyncio.get_running_loop().create_task(self._veiller())

    async def _veiller(self) -> None:
        # INV-EXEC-6 : la veille ne meurt pas en silence ; elle s'éteint quand tout répond.
        raison = "arrêt de la veille (tâche annulée)"
        try:
            while self._tient() and not self.m.ferme:
                await self._pause(intervalle(self.conf, self.horloge() - self._t0))
                try:
                    self._appliquer(await self.sonder())
                    self.reprendre()
                except Exception:
                    log.exception("veille du réseau")
            raison = "serveur fermé" if self.m.ferme else "tous les fournisseurs répondent"
        except Exception as e:
            raison = f"{type(e).__name__}: {e}"
            raise
        finally:  # trace de l'arrêt : une veille éteinte sans mot laisse un gel inexplicable
            log.info("réseau : boucle de veille arrêtée après %.0f s (%s), %d tour(s) encore gelé(s)",
                     self.horloge() - self._t0, raison, len(self.gele))

    async def _pause(self, duree: float) -> None:
        """INV-RESEAU-2 : l'intervalle s'interrompt au réveil de veille. `time.monotonic` ne compte pas la
        veille sous Linux : la pause d'intervalle seule survivrait au réveil ; l'écart entre l'horloge
        murale et l'horloge monotone, guetté par pas, trahit la veille. Sans veille (ou sans guet
        possible), comportement inchangé."""
        pause = asyncio.ensure_future(self.dormir(duree))
        guet = asyncio.ensure_future(self._guetter())
        try:
            await asyncio.wait({pause, guet}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in (pause, guet):
                t.cancel()
            await asyncio.gather(pause, guet, return_exceptions=True)
        if not pause.cancelled() and pause.exception() is not None:
            raise pause.exception()

    async def _guetter(self) -> None:
        try:
            m0, r0 = self.horloge(), self.reel()
            while True:
                await self.guetter(PAS_GUET_S)
                m1, r1 = self.horloge(), self.reel()
                if (r1 - r0) - (m1 - m0) > SEUIL_VEILLE_S:
                    log.info("réseau : réveil de veille détecté, sonde immédiate")
                    return
                m0, r0 = m1, r1
        except Exception:  # INV-EXEC-6 : un guet en panne laisse l'intervalle ordinaire courir
            log.exception("guet de veille")
            await asyncio.Future()

    def reprendre(self) -> list[str]:
        """INV-RESEAU-2 : relance, une seule fois, chaque tour gelé dont le fournisseur répond, dans l'ordre
        du classement (INV-ORDO-2)."""
        prets = [i for i, g in self.gele.items() if not self.bloque(g.harnais)]
        cands = [ordonnancement.Candidat(i, ordonnancement.humain(self.gele[i].envoi), n)
                 for n, i in enumerate(prets)]
        try:
            ordre = [prets[c.numero] for c, _ in ordonnancement.classer(self.m.vault, cands)]
        except Exception:  # INV-EXEC-6 : à défaut de classement, l'ordre du gel
            log.exception("classement des reprises")
            ordre = prets
        reprises = []
        for ident in ordre:
            g = self.gele.pop(ident)
            self.m.mesures.ajouter({"type": "gel", "date": maintenant(), "portee": "tache", "tache": ident,
                                    "harnais": g.harnais, "gel_s": round(self.horloge() - g.t0, 1)})
            try:
                if self.m.vault.ouverte(self.m.vault.tache(ident)):
                    self.m.interrompus[ident] = reprise.enregistrement(ident, g.envoi)
                    reprise._resoumettre(self.m, ident, MOTIF_REPRISE, auto=True)
                    self.m.files[ident].rotate(1)  # le tour repris passe avant les messages en file
                    reprises.append(ident)
                else:
                    self.m.etats[ident] = "inactif"
            except Exception as e:  # une tâche disparue n'empêche pas les autres
                log.warning("reprise de %s impossible : %s", ident, e)
            self.m.actifs.pop(ident, None)
        if prets:
            self.m._sauver_actifs()
            self.m.publier("reseau")
        return reprises

    # --- état ----------------------------------------------------------------------------
    def public(self) -> dict:
        return {"actif": self.conf.actif, "perdu_depuis": self.perdu_depuis or None, "hors": dict(self.hors),
                "en_attente": len(self.gele) + len(self.retenus - set(self.gele)),
                "taches": sorted(self.gele)}
