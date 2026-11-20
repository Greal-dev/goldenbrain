"""Agents simultanés : routes `/api/simultanes` (lire, régler) et « Reprendre maintenant ».

Rôle : valider et appliquer le réglage (mode, nombre fixe, garde, marge, plafond), le persister
clé par clé dans `config.toml` (`[moteur] simultanes_max`, `[simultanes]`), lever une pause RAM.
Frontières : aucune décision de régulation (module `simultanes`) ; aucune écriture vault.
Invariants portés : INV-SIMULT-1 (une reprise forcée exempte le tour de toute nouvelle pause).
"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from . import langues
from .config import ConfigSimultanes
from .fiches import ecrire_atomique
from .simultanes import GO
from .vault import Conflit, Invalide
from .verrou_config import sous_verrou_config


class CorpsSimultanes(BaseModel):
    mode: str | None = None
    simultanes_max: int | None = None
    garde_max: int | None = None
    marge_pct: float | None = None
    plafond: float | None = None
    unite: str | None = None


def _valeur(v) -> str:
    return f'"{v}"' if isinstance(v, str) else str(v).lower() if isinstance(v, bool) else repr(v)


@sous_verrou_config
def ecrire_cles(chemin: Path, section: str, cles: dict) -> None:
    """Remplace ou ajoute les clés données dans `[section]` ; le reste du fichier est restitué
    tel quel (commentaires, autres clés, fins de ligne)."""
    texte = chemin.read_bytes().decode("utf-8") if chemin.is_file() else ""
    eol = "\r\n" if "\r\n" in texte else "\n"
    lignes = texte.splitlines(keepends=True)
    entete = re.compile(rf"^\ufeff?\s*\[{section}\]\s*(#.*)?$")  # BOM ou commentaire admis
    debut = next((i for i, ligne in enumerate(lignes) if entete.match(ligne.rstrip("\r\n"))), None)
    if debut is None:
        if lignes and not lignes[-1].endswith(("\n", "\r")):
            lignes[-1] += eol
        lignes += ([eol] if lignes else []) + [f"[{section}]{eol}"]
        debut = len(lignes) - 1
    fin = next((j for j in range(debut + 1, len(lignes)) if lignes[j].lstrip().startswith("[")),
               len(lignes))
    while fin > debut + 1 and not lignes[fin - 1].strip():
        fin -= 1  # les nouvelles clés se placent avant la ligne vide qui sépare les sections
    for cle, v in cles.items():
        ligne = f"{cle} = {_valeur(v)}{eol}"
        i = next((j for j in range(debut + 1, fin) if re.match(rf"\s*{cle}\s*=", lignes[j])), None)
        if i is None:
            lignes.insert(fin, ligne)
            fin += 1
        else:
            lignes[i] = ligne
    ecrire_atomique(chemin, "".join(lignes))  # INV-VAULT-2 : temporaire unique, puis os.replace


def appliquer(config, c: CorpsSimultanes) -> None:
    """Valide tout, persiste, puis applique en mémoire (en cas d'échec rien ne change)."""
    champs = {k: v for k, v in c.model_dump().items() if v is not None and k != "simultanes_max"}
    try:
        cible = ConfigSimultanes(**{**asdict(config.simultanes), **champs})
    except (TypeError, ValueError) as e:
        raise Invalide(str(e)) from e
    if c.simultanes_max is not None and not 1 <= c.simultanes_max <= 64:
        raise Invalide(langues.t("serveur.api_simultanes.hors_bornes"))
    if config.chemin:
        if champs:
            ecrire_cles(config.chemin, "simultanes", champs)
        if c.simultanes_max is not None:
            ecrire_cles(config.chemin, "moteur", {"simultanes_max": c.simultanes_max})
    config.simultanes = cible
    if c.simultanes_max is not None:
        config.moteur.simultanes_max = c.simultanes_max


def routes(config, moteur) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/simultanes")
    async def lire():
        return moteur._sem.public()

    @r.put("/simultanes")
    async def regler(c: CorpsSimultanes):
        m = moteur._sem.mesure
        if c.unite and c.plafond is None and m and c.unite != config.simultanes.unite:
            # Même seuil dans l'autre unité : 80 % ne devient pas 80 Go (revue du 15/11).
            octets = (config.simultanes.plafond * GO if config.simultanes.unite == "go"
                      else m.total * config.simultanes.plafond / 100)
            c.plafond = round(octets / GO if c.unite == "go" else min(99, 100 * octets / m.total), 1)
        appliquer(config, c)
        moteur._sem.veiller_maintenant()  # le nouveau mode s'applique sans attendre la veille
        moteur.publier("simultanes")
        return moteur._sem.public()

    @r.post("/taches/{ident}/reprendre-ram")
    async def reprendre(ident: str):
        cles = [k for k, p in moteur._sem.pauses.items() if p.tache == ident]
        if not cles:
            raise Conflit(langues.t("serveur.api_simultanes.pas_en_pause"))
        for k in cles:
            moteur._sem.reprendre(k, force=True)
        return {"pause_ram": False}

    return r
