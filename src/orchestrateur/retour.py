"""Modifier un message envoyé : retour arrière de la conversation, archive de la fin, code restaurable.

Rôle : repérer les tours d'une tâche dans ses journaux, relier chaque message de l'utilisateur à
son tour, dresser le plan d'une modification (échanges retirés, mécanisme du harnais, fichiers du
vault touchés, plan du code), l'exécuter (archive des journaux retirés, conversation reprise au
point ou repli par transcription, restauration du code sur demande) et relire les versions archivées.
Pose aussi, avant chaque tour, le point de restauration du code (`MixinRetour.point_avant_tour`).
Frontières : pas de HTTP (`api_retour`) ; git par `points` ; le vault n'est écrit que par
`Vault.modifier` (clé `session`), jamais annulé (le frontmatter de l'utilisateur n’est jamais réécrit).
Invariants portés : INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import re
import shutil
from pathlib import Path

from . import fiches, langues, points, sessions
from .vault import Conflit, Invalide

log = logging.getLogger(__name__)
# Tête du message de repli : la conversation l'affiche réduite à une ligne (INV-RETOUR-1).
MARQUE = "[GoldenBrain — conversation reprise après modification d'un message."
REPLI = re.compile(re.escape(MARQUE) + r".*?\n>>>\]\n\n", re.S)
LIGNE_REPLI = "↺ *Conversation reprise par transcription après modification d'un message.*\n\n"
TRANSCRIPTION_MAX = 40_000
OUTILS_ECRITURE = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _extrait(texte: str) -> str:
    return " ".join((texte or "").split())[:80]


def _plein(texte: str) -> str:
    # Le transcript peut porter un en-tête avant le message (amorce du chat de projet, repli) :
    # on cherche le début du message envoyé dans le texte entier, espaces normalisés.
    return " ".join(REPLI.sub("", texte or "").split())


def _lire_json(ligne: str) -> dict | None:
    try:
        brut = json.loads(ligne)
    except ValueError:
        return None
    return brut if isinstance(brut, dict) else None


def lister(donnees: Path, ident: str) -> list[dict]:
    """Tours de la tâche dans l'ordre : un tour commence à une ligne `orch_message` de ses journaux
    (deux tours dans la même seconde partagent un fichier : le tour est une portion de fichier)."""
    out: list[dict] = []
    for f in sessions._journaux(donnees, ident):
        k = 0
        for n, ligne in enumerate(f.read_text("utf-8", errors="replace").splitlines()):
            if '"orch_message"' not in ligne and '"orch_point"' not in ligne:
                continue
            brut = _lire_json(ligne) or {}
            if brut.get("type") == "orch_message":
                out.append({"id": f"{f.parent.name}/{f.stem}#{k}", "fichier": f, "ligne": n,
                            "texte": str(brut.get("texte") or ""), "date": str(brut.get("date") or ""),
                            "harnais": str(brut.get("harnais") or ""), "point": None})
                k += 1
            elif brut.get("type") == "orch_point" and out and out[-1]["fichier"] == f:
                out[-1]["point"] = brut
    return out


def annoter(messages: list[dict], tours: list[dict]) -> list[dict]:
    """Relie chaque message de l'utilisateur à son tour (du plus récent au plus ancien), chaque réponse
    de l'IA au tour qui la suit, et réduit l'en-tête d'un repli à une ligne. Un message sans tour
    (écrit au terminal) n'est pas modifiable, ni la réponse qui le précède."""
    k = len(tours) - 1
    for m in reversed(messages):
        if m.get("role") != "utilisateur":
            continue
        plein = _plein(m.get("texte", ""))
        while k >= 0 and _extrait(REPLI.sub("", tours[k]["texte"])) not in plein:
            k -= 1
        if k < 0:
            break
        m["tour"] = tours[k]["id"]
        k -= 1
    for m in messages:
        if m.get("role") == "utilisateur" and MARQUE in (m.get("texte") or ""):
            m["texte"] = REPLI.sub(LIGNE_REPLI, m["texte"], count=1)
    # « Répondre à partir d'ici » sur une réponse de l'IA = modifier le message qui la suit : `suite` est
    # le tour de ce message ; `dernier` : aucun message ne suit, la réponse part dans le fil normal.
    suite, rien_apres = None, True
    for m in reversed(messages):
        if m.get("role") == "utilisateur":
            suite, rien_apres = m.get("tour"), False
        elif m.get("role") == "assistant":
            if suite:
                m["suite"] = suite
            elif rien_apres:
                m["dernier"] = True
    return messages


def portions(donnees: Path, ident: str, premier: dict) -> list[tuple[Path, int]]:
    """Ce que retire la modification du tour `premier` : la fin de son fichier depuis sa ligne, puis
    tous les journaux suivants (échecs et remontées compris)."""
    fichiers = sessions._journaux(donnees, ident)
    i = fichiers.index(premier["fichier"])
    return [(premier["fichier"], premier["ligne"])] + [(f, 0) for f in fichiers[i + 1:]]


def fichiers_touches(retires: list[tuple[Path, int]]) -> list[str]:
    """Fichiers écrits par les tours retirés, relevés dans leurs journaux (Claude : outils d'écriture ;
    Codex : `file_change`). Relevé indicatif : un fichier écrit par une commande shell échappe."""
    vus: dict[str, None] = {}
    for f, debut in retires:
        for ligne in f.read_text("utf-8", errors="replace").splitlines()[debut:]:
            if "tool_use" not in ligne and "file_change" not in ligne:
                continue
            brut = _lire_json(ligne) or {}
            message = brut.get("message") if isinstance(brut.get("message"), dict) else {}
            for bloc in message.get("content") or []:
                if isinstance(bloc, dict) and bloc.get("type") == "tool_use" and bloc.get("name") in OUTILS_ECRITURE:
                    entree = bloc.get("input") or {}
                    if chemin := entree.get("file_path") or entree.get("notebook_path"):
                        vus[str(chemin)] = None
            item = brut.get("item") if isinstance(brut.get("item"), dict) else {}
            if item.get("type") == "file_change":
                for c in item.get("changes") or []:
                    if isinstance(c, dict) and c.get("path"):
                        vus[str(c["path"])] = None
    return list(vus)


def _sous(chemin: str, racine: Path | None) -> bool:
    if not racine:
        return False
    try:
        Path(chemin).resolve().relative_to(Path(racine).resolve())
        return True
    except (ValueError, OSError):
        return False


def _position(tours: list[dict], tour: str) -> int:
    # Le tour désigné par le client doit être un tour connu.
    for i, j in enumerate(tours):
        if j["id"] == tour:
            return i
    raise Invalide(langues.t("serveur.retour.tour_inconnu"))


def _transcription(messages: list[dict], tour: str) -> str:
    avant = []
    for m in messages:
        if m.get("tour") == tour:
            break
        if m.get("role") in ("utilisateur", "assistant") and (m.get("texte") or "").strip():
            avant.append(f"{'Vous' if m['role'] == 'utilisateur' else 'Agent'} : {m['texte'].strip()}")
    return "\n\n".join(avant)[-TRANSCRIPTION_MAX:]


def plan(moteur, ident: str, tour: str, messages: list[dict], harnais) -> dict:
    """Plan à blanc d'une modification : rien n'est écrit."""
    t = moteur.vault.tache(ident)
    tours = lister(moteur.config.donnees, ident)
    i = _position(tours, tour)
    premier, session, uuid = tours[i], str(t.fm.get("session") or ""), ""
    if session and hasattr(harnais, "point_de_reprise"):
        uuid = harnais.point_de_reprise(session, REPLI.sub("", premier["texte"]), premier["date"])
    mecanisme = "natif" if uuid else ("transcription" if i > 0 else "neuve")
    point = premier["point"]
    depot = Path(point["depot"]) if point else None
    retires = portions(moteur.config.donnees, ident, premier)
    touches = fichiers_touches(retires)
    racine = moteur.vault.racine
    code = None
    if point:
        try:
            code = {"depot": str(depot), "ref": point["ref"], "fichiers": points.plan(depot, point["commit"])}
        except (points.ErreurPoint, OSError) as e:
            code = {"depot": str(depot), "ref": point["ref"], "erreur": str(e), "fichiers": []}
    return {"tour": tour, "retires": len(tours) - i, "mecanisme": mecanisme,
            "harnais": getattr(harnais, "nom", ""), "point_reprise": uuid,
            "vault": [str(t.chemin)] + [c for c in touches if _sous(c, racine) and not _sous(c, t.chemin)],
            "hors_depot": [c for c in touches if not _sous(c, racine) and not _sous(c, depot)],
            "code": code, "_premier": premier, "_portions": retires, "_session": session,
            "_transcription": _transcription(messages, tour) if mecanisme == "transcription" else ""}


async def modifier(moteur, ident: str, tour: str, texte: str, code: bool,
                   messages: list[dict], harnais) -> dict:
    """INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3 : retire le tour et la suite, renvoie `texte`."""
    if not (texte or "").strip():
        raise Invalide(langues.t("serveur.retour.message_vide"))
    if (moteur.etat_de(ident) in ("en_cours", "en_file") or moteur.files[ident]
            or moteur.natif.ouvert(ident)):
        raise Conflit(langues.t("serveur.retour.tour_en_cours"))
    p = await asyncio.to_thread(plan, moteur, ident, tour, messages, harnais)
    restauration = None
    if code:
        if not p["code"] or p["code"].get("erreur"):
            raise Conflit(langues.t("serveur.retour.sans_restauration"))
        try:  # tout ou rien, AVANT de toucher à la conversation : un échec laisse tout en l'état
            restauration = await asyncio.to_thread(points.restaurer, Path(p["code"]["depot"]), ident,
                                                   p["_premier"]["point"]["commit"])
        except points.ErreurPoint as e:
            raise Conflit(str(e)) from e
    n = archiver(moteur.config.donnees, ident, p, texte, restauration)
    if p["mecanisme"] == "natif":
        moteur.rembobinages[ident] = (p["harnais"], p["point_reprise"])
    else:
        moteur.vault.modifier(ident, {"session": None})  # conversation neuve, l'ancienne reste sur disque
        if p["mecanisme"] == "transcription":
            texte = (f"{MARQUE} La conversation précédente a été tronquée ; voici sa transcription "
                     f"jusqu'au message modifié (exclu) :\n<<<\n{p['_transcription']}\n>>>]\n\n{texte}")
    etat = moteur.soumettre(ident, texte)
    moteur.publier("conversation", tache=ident)
    return {"etat_execution": etat, "version": n, "mecanisme": p["mecanisme"],
            "restauration": restauration}


def _racine_archives(donnees: Path, ident: str) -> Path:
    return donnees / "archives" / "retours" / ident


def archiver(donnees: Path, ident: str, p: dict, nouveau: str, restauration: dict | None) -> int:
    """INV-RETOUR-2 : la fin retirée est DÉPLACÉE dans l'archive (copie écrite d'abord, original
    tronqué ou déplacé ensuite), jamais supprimée."""
    racine = _racine_archives(donnees, ident)
    n = 1 + max((int(d.name) for d in racine.glob("*") if d.name.isdigit()), default=0)
    dossier = racine / str(n)
    for f, debut in p["_portions"]:
        cible = dossier / "journal" / f.parent.name / f.name
        cible.parent.mkdir(parents=True, exist_ok=True)
        if debut == 0:
            shutil.move(str(f), str(cible))
            continue
        lignes = f.read_bytes().splitlines(keepends=True)
        cible.write_bytes(b"".join(lignes[debut:]))
        fiches.ecrire_atomique(f, b"".join(lignes[:debut]).decode("utf-8", "surrogateescape"))
    premier = p["_premier"]
    (dossier / "retour.json").write_text(json.dumps({
        "n": n, "date": dt.datetime.now().isoformat(timespec="seconds"), "tour": p["tour"],
        "ancien": premier["texte"], "nouveau": nouveau, "harnais": p["harnais"],
        "session": p["_session"], "mecanisme": p["mecanisme"], "retires": p["retires"],
        "point_code": (premier["point"] or {}).get("ref"),
        "restauration": restauration}, ensure_ascii=False, indent=1), "utf-8")
    return n


def versions(donnees: Path, ident: str) -> list[dict]:
    out = []
    for d in _racine_archives(donnees, ident).glob("*/retour.json"):
        try:
            out.append(json.loads(d.read_text("utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda v: v.get("n", 0), reverse=True)


def version(donnees: Path, ident: str, n: int, registre: dict, harnais) -> dict:
    """Une version précédente : la fin retirée, relue dans la session d'origine quand le harnais
    a un transcript lisible, sinon dans les journaux archivés."""
    dossier = _racine_archives(donnees, ident) / str(int(n))
    try:
        meta = json.loads((dossier / "retour.json").read_text("utf-8"))
    except (OSError, ValueError):
        raise Invalide(langues.t("serveur.retour.version_inconnue")) from None
    msgs = []
    if meta.get("session") and meta.get("harnais") == getattr(harnais, "nom", None):
        try:
            lus = harnais.transcript(meta["session"], 0)
            debut = max((i for i, m in enumerate(lus) if m.role == "utilisateur"
                         and _extrait(REPLI.sub("", meta.get("ancien", ""))) in _plein(m.texte)), default=None)
            msgs = lus[debut:] if debut is not None else []
        except NotImplementedError:
            msgs = []
    if not msgs:
        msgs = sessions.relire_journaux(dossier, ident, 0, registre)
    return {**meta, "messages": [{"role": m.role, "texte": m.texte, "outils": m.outils,
                                  "horodatage": m.horodatage, "secondaire": m.secondaire} for m in msgs]}


class MixinRetour:
    """Branché sur le `Moteur` : point de restauration et reprise au point avant chaque tour."""

    @property
    def rembobinages(self) -> dict:
        # tâche -> (harnais, point) : consommé par le tour suivant de la tâche (INV-RETOUR-1).
        return self.__dict__.setdefault("_rembobinages", {})

    async def point_avant_tour(self, ident: str, harnais, journal, choix) -> None:
        attente = self.rembobinages.get(ident)
        if attente and not choix and attente[0] == getattr(harnais, "nom", None):
            harnais.reprendre_a = self.rembobinages.pop(ident)[1]
        if getattr(harnais, "distant", None) or not getattr(harnais, "dossier", ""):
            return  # codespace (dépôt hors du poste) ou adaptateur sans dossier de travail
        try:  # INV-RETOUR-3 : un échec de point se journalise, jamais n'empêche le tour
            depot = await asyncio.to_thread(points.depot_de, harnais.dossier)
            if depot:
                p = await asyncio.to_thread(points.creer, depot, ident)
                journal.write(json.dumps({"type": "orch_point", **p}, ensure_ascii=False) + "\n")
                journal.flush()
        except Exception as e:
            log.warning("point de restauration impossible pour %s : %s", ident, e)
