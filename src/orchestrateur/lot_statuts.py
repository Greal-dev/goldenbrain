"""Modification en bloc des tâches : statut, échéance, parent — tout ou rien, annulable.

Rôle : appliquer un changement à un lot de tâches choisies par l'utilisateur ; valider tout le lot AVANT la première
écriture (mêmes validations qu'à l'unité), écrire, restaurer en cas d'échec en cours de route ; garder l'état d'avant
(`donnees/lots/<lot>.json`) pour l'annulation en un geste ; tracer le changement dans le journal de chaque tâche
(`donnees/journal/statuts/<tâche>.jsonl`).
Frontières : pas de HTTP (`api_lots`) ; écrit par les gestes du vault (`poser_statut`, `poser_temps`, `rattachement`),
jamais directement ; ne touche jamais une tâche dont un agent travaille (exclue et signalée, INV-VERROU-1).
Invariants portés : INV-LOT-1 (tout ou rien, exclusion des tâches occupées, annulation, trace), INV-VERROU-1, INV-VAULT-4.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path

from . import langues, rattachement, temps
from .vault import Conflit, Invalide

MAX_LOT = 200
FERMEES = ("fait", "cloture", "abandonne")


def _dossier(moteur, sous: str) -> Path:
    d = moteur.config.donnees / sous
    d.mkdir(parents=True, exist_ok=True)
    return d


def _trace(moteur, ident: str, ligne: dict) -> None:
    """Une ligne par changement, au journal de la tâche (jamais bloquant : l'écriture de la fiche a déjà eu lieu)."""
    try:
        with (_dossier(moteur, "journal/statuts") / f"{ident}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _etat(t) -> dict:
    return {"statut": t.statut, "echeance": str(t.fm.get("echeance") or ""),
            "parent": t.parent_brut or rattachement.RACINE}


def _plan(moteur, ids, statut, echeance, parent) -> tuple[list, list]:
    """(à changer, exclues). Lève avant toute écriture : mêmes refus qu'à l'unité."""
    vault = moteur.vault
    if statut is None and echeance is None and parent is None:
        raise Invalide(langues.t("serveur.lot.rien"))
    if statut is not None and statut not in vault.statuts:
        raise Invalide(langues.t("serveur.vault.statut_inconnu", statut=statut))
    maj = temps.valider(echeance, None) if echeance is not None else None
    ids = rattachement.normaliser(ids)
    if len(ids) > MAX_LOT:
        raise Invalide(langues.t("serveur.lot.trop", max=MAX_LOT))
    taches = [vault.tache(i) for i in ids]  # NonTrouve : tout le lot refusé
    exclues = [{"id": t.id, "titre": t.titre, **(moteur.occupation(t.id) or {})} for t in taches if moteur.occupation(t.id)]
    gardes = [t for t in taches if t.id not in {e["id"] for e in exclues}]
    if statut is not None and (v := next((t for t in gardes if t.verrouille), None)):  # INV-VAULT-4
        raise Conflit(langues.t("serveur.vault.statut_tenu_paperclip") + f" ({v.titre})")
    if parent is not None and gardes:
        rattachement.verifier(vault, moteur.config.rangement, moteur.occupation, [t.id for t in gardes], parent)
    return [(t, maj) for t in gardes], exclues


def apercu(moteur, ids, statut=None, echeance=None, parent=None) -> dict:
    """Ce que ferait le lot, sans rien écrire : tâches retenues, exclues, récapitulatif par statut d'origine."""
    plan, exclues = _plan(moteur, ids, statut, echeance, parent)
    de: dict[str, int] = {}
    for t, _ in plan:
        de[t.statut] = de.get(t.statut, 0) + 1
    return {"retenues": [t.id for t, _ in plan], "exclues": exclues, "de": de}


def appliquer(moteur, ids, statut=None, echeance=None, parent=None) -> dict:
    plan, exclues = _plan(moteur, ids, statut, echeance, parent)
    vault = moteur.vault
    avant = {t.id: _etat(t) for t, _ in plan}
    faits: list[str] = []
    try:
        for t, maj in plan:
            if statut is not None and t.statut != statut:
                vault.poser_statut(t.id, statut, humain=True)
            if maj is not None:
                vault.poser_temps(t.id, maj)
            faits.append(t.id)
        if parent is not None:
            rattachement.appliquer(vault, moteur.config.rangement, moteur.occupation, [t.id for t, _ in plan], parent)
    except Exception:  # tout ou rien : l'état d'avant revient, puis l'erreur d'origine remonte
        _restaurer(moteur, avant)
        raise
    lot = uuid.uuid4().hex[:12]
    maintenant = dt.datetime.now().isoformat(timespec="seconds")
    apres = {i: _etat(vault.tache(i)) for i in avant}
    for i in avant:
        if statut is not None:
            moteur.liberer(i)  # INV-EXEC-11 : geste humain, comme à l'unité
        _trace(moteur, i, {"quand": maintenant, "lot": lot, "avant": avant[i], "apres": apres[i]})
    (_dossier(moteur, "lots") / f"{lot}.json").write_text(
        json.dumps({"lot": lot, "quand": maintenant, "avant": avant, "apres": apres, "annule": False}, ensure_ascii=False),
        encoding="utf-8")
    moteur.publier("arbre")
    return {"lot": lot, "changees": list(avant), "exclues": exclues}


def _restaurer(moteur, avant: dict) -> list[str]:
    """Remet l'état d'avant ; une erreur sur une tâche n'arrête pas les autres. Rend les tâches restaurées."""
    vault, rendues = moteur.vault, []
    lots: dict[str, list[str]] = {}
    for i, e in avant.items():
        try:
            if vault.tache(i).statut != e["statut"]:
                vault.poser_statut(i, e["statut"], humain=True)
            vault.poser_temps(i, temps.valider(e["echeance"], None))
            lots.setdefault(e["parent"], []).append(i)
            rendues.append(i)
        except Exception:  # noqa: BLE001 — la restauration va au bout du possible
            continue
    for parent, ids in lots.items():
        try:
            rattachement.appliquer(vault, moteur.config.rangement, moteur.occupation, ids, parent)
        except Exception:  # noqa: BLE001
            continue
    return rendues


def annuler(moteur, lot: str) -> dict:
    """Défait le lot : seules les tâches encore dans l'état posé par le lot reviennent ; les autres sont signalées."""
    chemin = _dossier(moteur, "lots") / f"{''.join(c for c in lot if c.isalnum())}.json"
    if not chemin.is_file():
        raise Conflit(langues.t("serveur.lot.inconnu"))
    d = json.loads(chemin.read_text(encoding="utf-8"))
    if d.get("annule"):
        raise Conflit(langues.t("serveur.lot.deja_annule"))
    vault, restaurables, ignorees = moteur.vault, {}, []
    for i, e in d["avant"].items():
        try:
            t = vault.tache(i)
        except Exception:  # noqa: BLE001 — tâche disparue
            ignorees.append({"id": i, "titre": i})
            continue
        if moteur.occupation(i) or _etat(t) != d["apres"][i]:  # modifiée ou prise depuis : on ne l'écrase pas
            ignorees.append({"id": i, "titre": t.titre})
        else:
            restaurables[i] = e
    rendues = _restaurer(moteur, restaurables)
    d["annule"] = True
    chemin.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    maintenant = dt.datetime.now().isoformat(timespec="seconds")
    for i in rendues:
        _trace(moteur, i, {"quand": maintenant, "lot": lot, "annule": True, "avant": d["apres"][i], "apres": d["avant"][i]})
    moteur.publier("arbre")
    return {"restaurees": rendues, "ignorees": ignorees}
