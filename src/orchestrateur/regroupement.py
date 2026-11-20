"""Exécution par tâche ou regroupée sous la tâche mère : réglage hérité, règle automatique, acheminement.

Rôle : lire le réglage `execution:` (tâche mère ou `contexte.md` d'un conteneur, hérité vers le bas,
défaut `automatique`) ; décider, pour les sous-tâches d'une mère, entre une conversation par tâche et
la conversation de la mère (règle déterministe, motif affiché) ; acheminer vers la mère le message
adressé à une sous-tâche regroupée ; écrire la fiche et le statut d'une sous-tâche sur demande de la
conversation de sa mère ; dire quelles sous-tâches la mère porte en ce moment.
Frontières : aucun second chemin d'exécution — la mère travaille par `Moteur.soumettre` ; aucune
session n'est créée ni effacée (la bascule n'a rien à migrer) ; écritures vault par `Vault.modifier`
(clés gérées, INV-VAULT-1) et, pour un conteneur, par `fiches.modifier_cles` sur son `contexte.md`.
Invariants portés : INV-REGROUPE-1, INV-REGROUPE-2, INV-REGROUPE-3.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import asdict, dataclass

from . import arbre, controle, fiches, langues, liens, ordonnancement
from .vault import Conflit, Invalide, NonTrouve, Tache

log = logging.getLogger(__name__)
REGLAGES = ("automatique", "par_tache", "regroupee")


def _libelle(reglage: str) -> str:
    return {"automatique": langues.t("serveur.regroupement.reglage_automatique"),
            "par_tache": langues.t("serveur.regroupement.reglage_par_tache"),
            "regroupee": langues.t("serveur.regroupement.reglage_regroupee")}[reglage]


TAILLES_LOURDES = ("m", "l", "xl")
CHAMPS = ("fait", "resultat", "essai", "situation", "reste", "prochain_pas")


@dataclass
class Decision:
    mode: str  # "par_tache" | "regroupee"
    motif: str
    parent: str = ""
    parent_titre: str = ""
    reglage: str = "automatique"
    origine: str = ""  # où le réglage est posé (titre) ; vide : défaut


# --- réglage ---------------------------------------------------------------------------------
def _valeur(fm: dict) -> str:
    v = str(fm.get("execution") or "").strip().lower()
    return v if v in REGLAGES else ""


def _fm_conteneur(vault, cid: str) -> dict:
    p = vault.racine / cid / vault.cfg.contexte
    return vault._lire_meta(p)[0] if p.is_file() else {}


def propre(vault, noeud: str) -> str:
    """Réglage posé sur le nœud lui-même (tâche ou conteneur), sinon ""."""
    taches = vault.index()[0]
    return _valeur(taches[noeud].fm) if noeud in taches else _valeur(_fm_conteneur(vault, noeud))


def herite(vault, noeud: str) -> tuple[str, str]:
    """(réglage, titre de l'ancêtre qui le pose) hérité par le nœud ; ("automatique", "") à défaut."""
    taches, _ = vault.index()
    if noeud in taches:
        chaine = arbre.fil(vault, noeud)
    else:
        s = arbre.structure(vault)
        if noeud not in s.noeuds:
            raise Invalide(langues.t("serveur.regroupement.noeud_inconnu", ident=noeud))
        chaine, n = [], s.noeuds[noeud].parent
        while n is not None:
            chaine.insert(0, {"id": n, "type": s.noeuds[n].type, "titre": s.noeuds[n].titre})
            n = s.noeuds[n].parent
    for n in reversed(chaine):
        if n["type"] in ("tache", "conteneur") and (v := propre(vault, n["id"])):
            return v, n["titre"]
    return "automatique", ""


def regler(moteur, noeud: str, reglage: str) -> None:
    """Pose (ou retire, "") le réglage d'une tâche ou d'un conteneur à `contexte.md`."""
    if reglage and reglage not in REGLAGES:
        raise Invalide(langues.t("serveur.regroupement.reglage_attendu", valeurs=", ".join(REGLAGES)))
    vault = moteur.vault
    if noeud in vault.index()[0]:
        vault.modifier(noeud, {"execution": reglage or None})
    else:
        if noeud not in arbre.structure(vault).noeuds:
            raise Invalide(langues.t("serveur.regroupement.noeud_inconnu", ident=noeud))
        p = vault.racine / noeud / vault.cfg.contexte
        if not p.is_file():
            raise Conflit(langues.t("serveur.regroupement.reglage_conteneur"))
        fiches.ecrire_atomique(p, fiches.modifier_cles(fiches.lire(p), {"execution": reglage or None}))
    moteur.publier("arbre")


# --- règle -----------------------------------------------------------------------------------
def _moteur_de(moteur, t: Tache) -> tuple[str, str]:
    return (str(t.fm.get("harnais") or moteur.config.moteur.harnais_defaut),
            str(t.fm.get("modele") or ""))


def _lourde(t: Tache) -> bool:
    return (str(t.fm.get("epreuves") or "").strip().lower() == "lourdes"
            or str(t.fm.get("taille") or "").strip().lower() in TAILLES_LOURDES)


def sous_taches(vault, mere: str) -> list[Tache]:
    taches = vault.index()[0]
    return [taches[k] for k in vault.enfants(mere)
            if vault.ouverte(taches[k]) and not taches[k].pilotage]


def _automatique(moteur, mere: Tache, enfants: list[Tache]) -> tuple[str, str]:
    """INV-REGROUPE-1 : règle déterministe ; la première condition rencontrée donne le motif."""
    n = len(enfants)
    if n < 2:
        return "par_tache", langues.t("serveur.regroupement.une_seule")
    for e in enfants:  # isolation : jamais regroupée, même quand la RAM manque
        if _moteur_de(moteur, e) != _moteur_de(moteur, mere):
            return "par_tache", langues.t("serveur.regroupement.autre_assistant", titre=e.titre)
        if str(e.fm.get("branche") or "") and str(e.fm.get("branche")) != str(mere.fm.get("branche") or ""):
            return "par_tache", langues.t("serveur.regroupement.propre_version", titre=e.titre)
        if str(e.fm.get("ou") or "") != str(mere.fm.get("ou") or ""):
            return "par_tache", langues.t("serveur.regroupement.ailleurs", titre=e.titre)
    sem = moteur._sem
    if sem.regule() and (sem.pauses or sem.depasse(sem.mesure)):  # INV-SIMULT-1 : signal de RAM
        return "regroupee", langues.t("serveur.regroupement.memoire", n=n)
    lourdes = [e for e in enfants if _lourde(e)]
    if lourdes:
        return "par_tache", (langues.t("serveur.regroupement.lourdes.un", n=n) if len(lourdes) == 1
                             else langues.t("serveur.regroupement.lourdes.plusieurs", n=n, m=len(lourdes)))
    if any(e.conteneur != mere.conteneur for e in enfants):
        return "par_tache", langues.t("serveur.regroupement.domaines", n=n)
    ids = {e.id for e in enfants}
    requiert = liens.prerequis(moteur.vault.index()[0])[0]
    if sum(1 for e in enfants if set(requiert.get(e.id, [])) & ids) < n - 1:
        return "par_tache", langues.t("serveur.regroupement.independantes", n=n)
    return "regroupee", langues.t("serveur.regroupement.enchainees", n=n)


def decider(moteur, ident: str) -> Decision | None:
    """Décision qui gouverne la tâche `ident` en tant que sous-tâche ; None sans mère."""
    vault = moteur.vault
    taches = vault.index()[0]
    p = vault._parents(taches).get(ident)
    if not p or p not in taches or taches[ident].pilotage:
        return None
    mere = taches[p]
    reglage, origine = herite(vault, ident)
    if not vault.ouverte(mere) or mere.verrouille:
        mode, motif = "par_tache", langues.t("serveur.regroupement.mere_close")
    elif reglage != "automatique":
        mode, motif = reglage, langues.t("serveur.regroupement.reglage_pose", reglage=_libelle(reglage), origine=origine)
    else:
        mode, motif = _automatique(moteur, mere, sous_taches(vault, p))
    motif = (langues.t("serveur.regroupement.motif_regroupee", titre=mere.titre, motif=motif) if mode == "regroupee"
             else langues.t("serveur.regroupement.motif_par_tache", motif=motif))
    return Decision(mode, motif, p, mere.titre, reglage, origine)


def vue(moteur, ident: str) -> dict:
    """Réglage propre, réglage hérité et décision, pour l'interface."""
    reglage, origine = herite(moteur.vault, ident)
    d = decider(moteur, ident) if ident in moteur.vault.index()[0] else None
    return {"reglage": propre(moteur.vault, ident), "herite": reglage, "herite_de": origine,
            "decision": asdict(d) if d else None}


# --- mode regroupé ---------------------------------------------------------------------------
def ordre(moteur, mere: str) -> list[Tache]:
    """Sous-tâches dans l'ordre de l'ordonnancement : prérequis d'abord, puis classement INV-ORDO-2."""
    vault = moteur.vault
    enfants = sous_taches(vault, mere)
    classes = [c.ident for c, _ in ordonnancement.classer(
        vault, [ordonnancement.Candidat(e.id, False, i) for i, e in enumerate(enfants)])]
    requiert = liens.prerequis(vault.index()[0])[0]
    restants, sortie = list(classes), []
    while restants:
        pret = next((k for k in restants if not set(requiert.get(k, [])) & set(restants)), restants[0])
        sortie.append(pret)
        restants.remove(pret)
    par_id = {e.id: e for e in enfants}
    return [par_id[k] for k in sortie]


def acheminer(moteur, ident: str, texte: str, de: str) -> tuple[str, str, str]:
    """INV-REGROUPE-2 : (tâche qui travaille, texte, sous-tâche portée). Sans regroupement, ou pour
    un message venu de la mère elle-même, rien ne change."""
    d = decider(moteur, ident)
    if d is None or d.mode != "regroupee" or de == d.parent:
        return ident, texte, ""
    t = moteur.vault.tache(ident)
    liste = "\n".join(f"{i}. {e.titre} (id {e.id}) [{e.statut}]"
                      for i, e in enumerate(ordre(moteur, d.parent), 1))
    entete = (f"[Pour la sous-tâche « {t.titre} » (id {ident}, fichier {t.chemin}) — {d.motif}.\n"
              f"Tu travailles pour tes sous-tâches dans cet ordre :\n{liste}\n"
              f"Pour chacune, à chaque étape : orch fiche <id> --statut en_cours|en_attente|terminee "
              f"--fait \"…\" --situation \"…\" --reste \"…\" (sa fiche et son statut proposé).]")
    _tracer(moteur, ident, langues.t("serveur.regroupement.trace_message", titre=d.parent_titre, texte=texte))
    return d.parent, f"{entete}\n\n{texte}", ident


def _tracer(moteur, ident: str, texte: str) -> None:
    # Trace propre à la sous-tâche : sa conversation la montre comme message du système.
    try:
        with moteur._journal(ident) as journal:
            journal.write(json.dumps({"type": "orch_regroupe", "texte": texte,
                                      "date": dt.datetime.now().isoformat(timespec="seconds")},
                                     ensure_ascii=False) + "\n")
    except OSError:
        log.exception("trace de regroupement impossible : %s", ident)


def ecrire_fiche(moteur, ident: str, de: str, statut: str, champs: dict) -> str:
    """INV-REGROUPE-2 : la conversation de la mère écrit fiche et statut proposé d'une sous-tâche."""
    d = decider(moteur, ident)
    if d is None or d.mode != "regroupee" or de != d.parent:
        raise Conflit(langues.t("serveur.regroupement.fiche_par_mere"))
    from .moteur import STATUT_DECLARE  # import tardif : le moteur importe ce module
    if statut and statut not in STATUT_DECLARE:
        raise Invalide(langues.t("serveur.regroupement.statut_attendu", valeurs=", ".join(STATUT_DECLARE)))
    vault = moteur.vault
    t = vault.tache(ident)
    fiche = {**t.fiche, **{k: v for k, v in champs.items() if k in CHAMPS and v}}
    nouveau = vault.statut_declare(statut) if statut else ""
    if nouveau == "fait" and controle.declare(vault, ident):
        # INV-CONTROLE-1 : « Terminée » exige le contrôle requis, lancé par un tour propre.
        nouveau = vault.retour
        fiche["situation"] = (fiche.get("situation") or "") + " — contrôle requis à lancer"
    if nouveau == "fait" and str(t.fm.get("nature") or "") in controle.NATURES_SANS_FIN:
        nouveau = "en-cours"  # INV-EXEC-7
    vault.modifier(ident, {}, fiche)
    if nouveau and vault.ouverte(t):
        vault.poser_statut(ident, nouveau)
    if (tour := moteur.tours.get(de)) is not None:  # INV-REGROUPE-3 : repère jusqu'à la fin du tour
        if moteur._portees.get(de, (None,))[0] is not tour:
            moteur._portees[de] = (tour, set())
        moteur._portees[de][1].add(ident)
    _tracer(moteur, ident, langues.t("serveur.regroupement.trace_fiche", titre=d.parent_titre,
                                     statut=nouveau or langues.t("serveur.regroupement.statut_inchange"),
                                     fait=fiche.get("fait", "")))
    moteur.publier("arbre")
    return vault.tache(ident).statut


class MixinRegroupement:
    """Partie du moteur : repère « IA au travail » d'une sous-tâche portée par sa mère."""

    @property
    def _portees(self) -> dict:
        if not hasattr(self, "_portees_"):
            self._portees_ = {}
        return self._portees_

    def portees(self) -> dict[str, str]:
        """INV-REGROUPE-3 : {sous-tâche: état} des sous-tâches que leur mère porte ou va porter."""
        out: dict[str, str] = {}
        for mere, q in list(self.files.items()):
            for e in list(q):
                if e.pour:
                    out.setdefault(e.pour, "en_file")
        for mere, e in list(self.envois.items()):
            if e.pour and mere in self.tours:
                out[e.pour] = "en_cours"
        for mere, (tour, ids) in list(self._portees.items()):
            if self.tours.get(mere) is tour:
                out.update(dict.fromkeys(ids, "en_cours"))
        return out

    def etat_de(self, ident: str) -> str:
        e = self.etats.get(ident, "inactif")
        if e != "inactif":
            return e
        return self.portees().get(ident) or ("en_pause" if self.pause_de(ident) else e)  # INV-EXEC-10
