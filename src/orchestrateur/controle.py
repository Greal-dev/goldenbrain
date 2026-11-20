"""Contrôle requis (R2) : une fin déclarée « terminée » n'est retenue que si le contrôle passe.

Rôle : un projet déclare `controle: <commande>` dans son `contexte.md` (le conteneur le plus proche
l'emporte, comme `depot:`). Quand l'agent déclare `terminee`, le moteur lance cette commande une
fois, dans le dossier de travail de la tâche (ou le sous-dossier `controle_dossier:` de la fiche,
borné à ce dossier), sous réservation du poste ; il conserve verdict, date, référence de l'état
vérifié et journal (`<donnees>/etat/controles.json`, reflet `controle:` dans le frontmatter).
Frontières : aucune boucle de réparation (l'échec rend la main, il ne relance pas l'agent) ; aucune
commande lue ailleurs que dans la clé `controle:` d'un contexte ; jamais de shell ; le succès ne pose
ni `cloture` ni validation. Mélangé au `Moteur` (poste, vault, config, publier, journal d'échec).
Invariants portés : INV-CONTROLE-1.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import re
import shlex
import subprocess
import sys
from functools import cached_property
from pathlib import Path

from . import depot, fiches, langues
from .harnais.processus import SESSION_PROPRE, Processus, resoudre
from .poste import MixinPoste
from .propositions import lire_liste, maintenant
from .vault import NonTrouve

log = logging.getLogger(__name__)
NATURES_SANS_FIN = ("permanente", "recurrente", "pilotage", "routine")  # INV-EXEC-7 : jamais de fin, donc pas de contrôle


def declare(vault, ident: str) -> tuple[str, str] | None:
    """(commande, conteneur qui la déclare) ; None si aucun contexte ancêtre ne déclare de contrôle."""
    for c, fm in depot.contextes(vault, ident):
        if (cmd := str(fm.get("controle") or "").strip()):
            return cmd, c
    return None


def argv(commande: str) -> list[str]:
    """Commande déclarée -> argv, sans shell (pas d'opérateurs, pas d'expansion) ; `{python}` vaut
    l'interpréteur du serveur. Exécutable introuvable : FileNotFoundError."""
    parts = [p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p
             for p in shlex.split(commande, posix=False)]
    if not parts:
        raise FileNotFoundError(langues.t("serveur.controle.commande_vide"))
    parts = [sys.executable if p == "{python}" else p for p in parts]
    return resoudre(parts[0]) + parts[1:]


def dossier_verifie(base: str, final: str) -> Path:
    """Dossier contrôlé : `controle_dossier:` du dernier bloc `<fiche>` s'il est sous `base`
    (un arbre de travail du dépôt), sinon `base`. Hors de `base` ou absent : ValueError."""
    blocs = re.findall(r"<fiche>(.*?)</fiche>", final or "", flags=re.S)
    m = re.search(r"^\s*controle_dossier\s*:\s*(.+?)\s*$", blocs[-1], re.M) if blocs else None
    racine = Path(base).resolve()
    if not m:
        return racine
    d = Path(m.group(1).strip().strip('"'))
    d = (d if d.is_absolute() else racine / d).resolve()
    if not d.is_relative_to(racine) or not d.is_dir():
        raise ValueError(langues.t("serveur.controle.dossier_hors", dossier=m.group(1).strip()))
    return d


def _git(dossier: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(dossier), *args], capture_output=True, timeout=10,
                           text=True, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def reference(dossier: Path) -> str:
    """État exact vérifié : `branche@commit`, suffixé `+modifs:<empreinte>` si l'arbre n'est pas
    propre ; vide hors dépôt git (l'état n'est alors pas référencé, jamais présumé identique)."""
    if not (commit := _git(dossier, "rev-parse", "--short=12", "HEAD")):
        return ""
    ref = f"{_git(dossier, 'rev-parse', '--abbrev-ref', 'HEAD') or '?'}@{commit}"
    if etat := _git(dossier, "status", "--porcelain", "--untracked-files=normal"):
        diff = _git(dossier, "diff", "HEAD") or ""
        ref += "+modifs:" + hashlib.sha256((etat + diff).encode()).hexdigest()[:12]
    return ref


async def executer(commande: str, dossier: Path, journal: Path, delai_s: int) -> tuple[bool, str]:
    """Lance la commande ; sortie dans `journal`. (réussi, cause) ; délai dépassé : arbre tué."""
    try:
        args = argv(commande)
    except (FileNotFoundError, ValueError) as e:
        return False, langues.t("serveur.controle.non_lancee", erreur=e)
    p = Processus()
    with open(journal, "wb") as sortie:
        try:
            p.proc = await asyncio.create_subprocess_exec(
                *args, cwd=str(dossier), stdin=subprocess.DEVNULL, stdout=sortie,
                stderr=subprocess.STDOUT, **SESSION_PROPRE)
            code = await asyncio.wait_for(p.proc.wait(), delai_s or None)
        except TimeoutError:
            await p.arreter()
            return False, langues.t("serveur.controle.duree_max", delai=delai_s)
        except OSError as e:
            return False, langues.t("serveur.controle.non_lancee", erreur=e)
        finally:
            if p.proc and p.proc.returncode is None:
                await asyncio.shield(p.arreter())  # annulation : pas d'orphelin
    return code == 0, "" if code == 0 else langues.t("serveur.controle.echec_code", code=code)


class Controles:
    """Dernier verdict par tâche, persisté (survit au redémarrage ; fichier illisible = aucun)."""

    def __init__(self, fichier: Path):
        self.fichier = fichier
        self._v = {v["tache"]: v for v in lire_liste(fichier)
                   if isinstance(v, dict) and v.get("tache")}

    def dernier(self, ident: str) -> dict | None:
        return dict(self._v[ident]) if ident in self._v else None

    def poser(self, verdict: dict) -> None:
        self._v[verdict["tache"]] = verdict
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            fiches.ecrire_atomique(self.fichier, json.dumps(list(self._v.values()),
                                                            ensure_ascii=False, indent=1))
        except OSError as e:
            log.warning("verdict de contrôle non persisté : %s", e)


def resume(v: dict) -> str:
    """Reflet lisible du verdict dans le frontmatter (`controle:`)."""
    mot = "réussi" if v["verdict"] == "reussi" else "échoué"
    return " · ".join(x for x in (f"{mot} le {v['date'][:16].replace('T', ' ')}",
                                  v.get("reference") or "état non référencé",
                                  v.get("cause") or "") if x)


class MixinControle(MixinPoste):
    INTERVALLE_CONTROLE_S = 1.0

    @cached_property
    def controles(self) -> Controles:
        return Controles(self.config.donnees / "etat" / "controles.json")

    @cached_property
    def _verdicts_tour(self) -> dict[str, dict]:
        return {}

    def controle_vue(self, ident: str) -> dict | None:
        """INV-CONTROLE-1 : contrôle requis et dernier verdict, périmé si l'état vérifié a changé.
        Sans contrôle déclaré : None (aucune preuve affichée, positive ou non)."""
        if not (d := declare(self.vault, ident)):
            return None
        v = self.controles.dernier(ident)
        if v and v.get("reference"):
            v["perime"] = reference(Path(v["dossier"])) != v["reference"]
        elif v:
            v["perime"] = None  # état non référencé : ni frais ni périmé, on ne le présume pas
        return {"commande": d[0], "declare_par": d[1], "verdict": v}

    async def _controler(self, ident: str, final, erreur, tour) -> None:
        """Fin de tour déclarée `terminee` d'une tâche à contrôle requis : lance le contrôle
        (INV-CONTROLE-1) et garde le verdict pour `_statut_controle`. Ne lève jamais."""
        self._verdicts_tour.pop(ident, None)
        if erreur or final is None or (tour and tour.arrete) or fiches.declaration(final) != "terminee":
            return
        try:
            t = self.vault.tache(ident)
            if str(t.fm.get("nature") or "") in NATURES_SANS_FIN or not (d := declare(self.vault, ident)):
                return
            v = await self._lancer_controle(ident, d[0], final)
        except NonTrouve:
            return
        except Exception as e:  # INV-EXEC-6 : un contrôle en panne est un contrôle échoué, visible
            log.exception("contrôle de %s", ident)
            v = {"tache": ident, "verdict": "echoue", "date": maintenant(), "commande": "",
                 "dossier": "", "reference": "", "journal": "", "cause": f"{type(e).__name__}: {e}"}
        self._verdicts_tour[ident] = v
        self.controles.poser(v)
        try:
            self.vault.modifier(ident, {"controle": resume(v)})
        except (NonTrouve, OSError):
            log.warning("reflet du contrôle non écrit : %s", ident)
        if v["verdict"] != "reussi":
            self._journaliser_echec(ident, "controle", langues.t(
                "serveur.controle.echec_journal", cause=v["cause"],
                journal=v["journal"] or langues.t("serveur.controle.aucun")))
        self.publier("controle", tache=ident, verdict=v["verdict"])

    async def _lancer_controle(self, ident: str, commande: str, final: str) -> dict:
        base, _ = depot.dossier_de_travail(self.vault, ident)
        v = {"tache": ident, "verdict": "echoue", "commande": commande, "dossier": "",
             "reference": "", "journal": "", "cause": ""}
        if not base:
            return {**v, "date": maintenant(), "cause": langues.t("serveur.controle.sans_dossier")}
        try:
            dossier = dossier_verifie(base, final)
        except ValueError as e:
            return {**v, "date": maintenant(), "cause": str(e)}
        # INV-POSTE-1 : un contrôle est une épreuve lourde ; il attend un poste libre et le tient.
        # Il prend son rang dans la file du poste ; sa demande répétée l'y maintient.
        while self.poste.demander(ident, langues.t("serveur.controle.poste_motif")) is None:
            await asyncio.sleep(self.INTERVALLE_CONTROLE_S)
        self.publier("poste")
        self.publier("controle", tache=ident, verdict="en_cours")
        try:
            now = dt.datetime.now()
            jdir = self.config.donnees / "journal" / now.strftime("%Y-%m-%d")
            jdir.mkdir(parents=True, exist_ok=True)
            journal = jdir / f"{ident}-controle-{now.strftime('%H%M%S')}.log"
            ok, cause = await executer(commande, dossier, journal, self.config.moteur.controle_duree_s)
            # Référence prise après : un artefact du contrôle lui-même ne rend pas le verdict périmé.
            ref = await asyncio.to_thread(reference, dossier)
        finally:
            if self.poste.rendre(ident):
                self.publier("poste")
        return {**v, "verdict": "reussi" if ok else "echoue", "date": maintenant(),
                "dossier": str(dossier), "reference": ref, "journal": str(journal), "cause": cause}

    def _statut_controle(self, ident: str, statut: str) -> str:
        # INV-CONTROLE-1 : « fait » exige le succès du contrôle requis lancé pour ce tour.
        v = self._verdicts_tour.pop(ident, None)
        return self.vault.retour if statut == "fait" and v and v["verdict"] != "reussi" else statut
