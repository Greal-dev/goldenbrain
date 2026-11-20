"""Chat de projet : la conversation d'un conteneur (casquette, opération, projet) ou d'une tâche mère.

Rôle : trouver ou créer la tâche de pilotage d'un nœud de l'arbre (`nature: pilotage`, une par
nœud), composer l'amorçage de chaque tour (fiche de contexte, descendance avec statut, état
d'exécution et fiche, remontées reçues) et consigner la remontée d'une descendante qui finit un tour.
Frontières : aucun second chemin d'exécution — la conversation est un tour ordinaire du moteur
(`Moteur.soumettre`) ; aucun geste humain (valider, fermer, déplacer) : le chat les propose.
Invariants portés : INV-PILOTAGE-1 (une tâche de pilotage par nœud, créée au premier message,
absente des listes et compteurs), INV-PILOTAGE-2 (amorçage rafraîchi à chaque tour, borné),
INV-PILOTAGE-3 (remontée = une ligne journalisée et gardée pour le tour suivant, sans tour).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path

from . import arbre, fiches, langues
from .config import RACINE_DEPOT
from .vault import Invalide, Tache

log = logging.getLogger(__name__)
SEUIL = 40  # lignes de descendance au-delà desquelles l'amorçage se résume
CHAMP_MAX = 160  # longueur d'un champ de fiche une fois le seuil franchi
CONTEXTE_MAX = 4000  # caractères de la fiche de contexte recopiés au premier tour
REMONTEES_MAX = 20
TACHES_MERES = True  # une tâche mère est amorcée de sa descendance (désactivé par les tests anciens)


def _cible(t: Tache) -> str:
    return str(t.fm.get("pilote") or "")


def trouver(vault, noeud: str) -> str | None:
    """Tâche de pilotage du nœud, ou None. Un projet la porte dans son dossier (elle le suit s'il
    est déplacé) ; une casquette ou une opération la désigne par `pilote:`."""
    for t in vault.index()[0].values():
        if not t.pilotage:
            continue
        c = _cible(t)
        if c.startswith(("casquette:", "operation:")):
            if c == noeud:
                return t.id
        elif t.conteneur == noeud:
            return t.id
    return None


def ouvrir(moteur, noeud: str) -> str:
    """INV-PILOTAGE-1 : rend la tâche de pilotage du nœud, créée à la première demande."""
    vault = moteur.vault
    s = arbre.structure(vault)
    if noeud not in s.noeuds:  # INV-VAULT-3 : seul un nœud connu de l'arbre
        raise Invalide(langues.t("serveur.pilotage.noeud_inconnu", noeud=noeud))
    if ident := trouver(vault, noeud):
        return ident
    n = s.noeuds[noeud]
    dossier = noeud if n.type == "conteneur" else vault.cfg.arrivee
    ident = vault.creer(f"Pilotage — {n.titre}", dossier,
                        description="Conversation de pilotage de ce conteneur (GoldenBrain).",
                        cles={"nature": "pilotage", "pilote": noeud})
    moteur.publier("arbre")
    return ident


# --- amorçage ------------------------------------------------------------------------------
def _descendance(vault, t: Tache) -> tuple[list[tuple[int, Tache]], str]:
    """(profondeur, tâche) dans l'ordre de l'arbre, et le chemin de la fiche de contexte."""
    taches, conts = vault.index()
    parents = vault._parents(taches)
    if t.pilotage:
        cible = _cible(t) if _cible(t).startswith(("casquette:", "operation:")) else t.conteneur
        s = arbre.structure(vault)
        dedans = set(s.sous_arbre(cible)) if cible in s.noeuds else {cible}
        membres = {k for k, x in taches.items() if x.conteneur in dedans and not x.pilotage}
        contexte = vault.racine / cible / vault.cfg.contexte if cible in conts else None
    else:
        membres = set(vault.descendance(t.id)[1:])
        contexte = None
    enfants: dict[str | None, list[str]] = {}
    for k in sorted(membres):
        p = parents[k] if parents[k] in membres else None
        enfants.setdefault(p, []).append(k)
    ordre: list[tuple[int, Tache]] = []

    def parcourir(p: str | None, prof: int) -> None:
        for k in enfants.get(p, []):
            if all(k != x.id for _, x in ordre):
                ordre.append((prof, taches[k]))
                parcourir(k, prof + 1)
    parcourir(None, 0)
    return ordre, (str(contexte) if contexte and contexte.is_file() else "")


def _ligne(vault, moteur, prof: int, t: Tache, court: bool) -> str:
    f = t.fiche
    champs = [(nom, str(f.get(cle) or "").strip()) for nom, cle in
              (("fait", "fait"), ("situation", "situation"), ("reste", "reste"))]
    rendu = " | ".join(f"{nom} : {v[:CHAMP_MAX] if court else v}" for nom, v in champs if v)
    return (f"{'  ' * prof}- {t.titre} (id {t.id}) [{t.statut or '?'} · "
            f"{moteur.etat_de(t.id)}]" + (f" — {rendu}" if rendu else ""))


def _arbre(vault, moteur, ordre: list[tuple[int, Tache]]) -> list[str]:
    court = len(ordre) > SEUIL
    if not court:
        return [_ligne(vault, moteur, p, t, False) for p, t in ordre]
    # INV-PILOTAGE-2 : au-delà du seuil, les tâches closes ne sont que comptées et les ouvertes
    # bornées ; le détail reste à `orch lire`.
    ouvertes = [(p, t) for p, t in ordre if vault.ouverte(t)]
    lignes = [_ligne(vault, moteur, p, t, True) for p, t in ouvertes[:SEUIL]]
    if len(ouvertes) > SEUIL:
        lignes.append(f"- … et {len(ouvertes) - SEUIL} autres tâches ouvertes (orch chercher)")
    lignes.append(f"- {len(ordre) - len(ouvertes)} tâches closes non détaillées")
    return lignes


def amorcer(moteur, ident: str, texte: str) -> str:
    """INV-PILOTAGE-2 : préfixe le message d'un tour de pilotage (ou d'une tâche mère) de l'état
    de la descendance ; le message journalisé reste celui de l'humain."""
    vault = moteur.vault
    t = vault.tache(ident)
    if not t.pilotage and not (TACHES_MERES and vault.enfants(ident)):
        return texte
    ordre, contexte = _descendance(vault, t)
    blocs = [f"[Pilotage de « {t.titre} » — état de la descendance au "
             f"{dt.datetime.now():%Y-%m-%d %H:%M}, rafraîchi à chaque tour]"]
    if contexte:
        if t.fm.get("session"):
            blocs.append(f"Fiche de contexte : {contexte}")
        else:
            blocs.append(f"Fiche de contexte ({contexte}) :\n"
                         f"{fiches.lire(Path(contexte))[:CONTEXTE_MAX]}")
    blocs.append("Descendance :\n" + ("\n".join(_arbre(vault, moteur, ordre)) or "(aucune tâche)"))
    if lues := lire_remontees(moteur, ident):
        blocs.append("Remontées depuis ton dernier tour :\n" + "\n".join(f"- {x}" for x in lues))
    if t.pilotage:
        blocs.append(_GESTES.format(orch=_orch(), noeud=_cible(t) or t.conteneur,
                                    conteneur=t.conteneur))
    return "\n\n".join(blocs) + f"\n\n---\n\n{texte}"


def _orch() -> str:
    return f'"{Path(sys.executable).as_posix()}" "{(RACINE_DEPOT / "orch.py").as_posix()}"'


_GESTES = """Tu pilotes ce conteneur (nœud {noeud}). Gestes par {orch} :
- créer une tâche : creer "<titre>" --conteneur <id de projet> (orch conteneurs) ou --parent <id> --description "<consigne, au moins une phrase>" (exigée) ;
- la lancer, la relancer avec une consigne ou lui écrire : dire <id> "<message>" ; reprendre un tour coupé : relancer <id> ;
- l'arrêter : arreter <id> ; lire son état : lire <id> ;
- réorganiser : proposer deplacer|projet|operation|ticket|tache|lier|renommer ... --motif "<pourquoi>".
Valider, fermer ou déplacer un dossier restent des gestes humains : tu les proposes, tu ne les fais pas.
Tu ne travailles pas toi-même dans les dépôts : tu confies le travail aux tâches."""


# --- remontée --------------------------------------------------------------------------------
def _fichier(moteur, ident: str) -> Path:
    return moteur.config.donnees / "etat" / "remontees" / f"{ident}.jsonl"


def lire_remontees(moteur, ident: str) -> list[str]:
    """Remontées en attente, consommées par le tour qui les lit."""
    f = _fichier(moteur, ident)
    try:
        lignes = f.read_text("utf-8").splitlines()
        f.unlink()
    except OSError:
        return []
    return [str(json.loads(x)) for x in lignes if x.strip()][-REMONTEES_MAX:]


def destinataires(vault, ident: str) -> list[str]:
    """Conversations existantes au-dessus de la tâche : pilotage de chaque nœud ancêtre, tâches
    mères qui ont déjà une session."""
    out = []
    for n in arbre.fil(vault, ident):
        if n["type"] == "tache":
            if TACHES_MERES and vault.tache(n["id"]).fm.get("session"):
                out.append(n["id"])
        elif (p := trouver(vault, n["id"])) and p != ident:
            out.append(p)
    return out


def remonter(moteur, ident: str, fiche: dict) -> None:
    """INV-PILOTAGE-3 : une ligne de synthèse vers chaque conversation au-dessus, sans tour."""
    vault = moteur.vault
    try:
        t = vault.tache(ident)
        cibles = destinataires(vault, ident)
    except Exception:  # la remontée ne fait jamais échouer la fin d'un tour
        log.exception("remontée impossible : %s", ident)
        return
    ligne = (f"« {t.titre} » ({ident}) a fini un tour [{t.statut}] — "
             f"{str(fiche.get('fait') or '').strip()} / {str(fiche.get('situation') or '').strip()}")
    for cible in cibles:
        try:
            f = _fichier(moteur, cible)
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, "a", encoding="utf-8") as sortie:
                sortie.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            with moteur._journal(cible) as journal:  # visible dans le chat comme message du système
                journal.write(json.dumps({"type": "orch_remontee", "texte": ligne,
                                          "date": dt.datetime.now().isoformat(timespec="seconds")},
                                         ensure_ascii=False) + "\n")
            moteur.publier("remontee", tache=cible)
        except OSError as e:
            log.warning("remontée %s -> %s non consignée : %s", ident, cible, e)
