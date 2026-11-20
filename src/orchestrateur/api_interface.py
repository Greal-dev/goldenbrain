"""Mode simple / avancé : routes `/api/interface`, garde des familles débrayées, persistance.

Rôle : exposer et modifier `[interface]` ; refuser (409) les routes d'une famille débrayée ;
réécrire la seule section `[interface]` de `config.toml`.
Frontières : aucune logique métier ; les tours (propagation, revues, jardinage, avis) sont
retenus par leurs modules, pas ici.
Invariants portés : INV-INTERFACE-1 (famille débrayée = aucun tour et routes en 409),
INV-INTERFACE-2 (la persistance ne touche que `[interface]`).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from . import langues
from .config import FAMILLES, Config, ConfigInterface
from .fiches import ecrire_atomique
from .vault import Invalide
from .verrou_config import sous_verrou_config

# (famille, chemin, seulement les écritures) : lire reste inoffensif pour l'équipe, les liens
# et les transformations ; alignement, jardinage et notes sont fermés en entier.
FERMEES = [
    ("equipe", re.compile(r"^/api/equipe(/|$)"), True),
    ("equipe", re.compile(r"^/api/taches/[^/]+/solliciter$"), True),
    ("liens", re.compile(r"^/api/taches/[^/]+/liens(/retirer)?$"), True),
    ("transformations", re.compile(r"^/api/(taches/[^/]+/promouvoir|conteneurs/reduire)$"), True),
    ("alignement", re.compile(r"^/api/alignement(/|$)"), False),
    ("jardinage", re.compile(r"^/api/jardinage$"), False),
    ("notes", re.compile(r"^/api/vault(/|$)"), False),
]


def famille_fermee(interface: ConfigInterface, chemin: str, methode: str) -> str | None:
    """Famille débrayée qui interdit cette requête, sinon None."""
    for famille, motif, ecriture in FERMEES:
        if motif.search(chemin) and not interface.actif(famille) and (methode != "GET" or not ecriture):
            return famille
    return None


class CorpsInterface(BaseModel):
    mode: str | None = None
    familles: dict[str, bool | None] | None = None
    propositions: str | None = None
    langue: str | None = None


def ecrire_section(chemin: Path, interface: ConfigInterface) -> None:
    """Remplace (ou ajoute) la section `[interface]` ; le reste du fichier est restitué tel quel."""
    cles = [("mode", f'"{interface.mode}"')]
    cles += [(f, str(getattr(interface, f)).lower()) for f in FAMILLES if getattr(interface, f) is not None]
    if interface.propositions:
        cles.append(("propositions", f'"{interface.propositions}"'))
    if interface.langue:
        cles.append(("langue", f'"{interface.langue}"'))
    remplacer_section(chemin, "interface", cles)


@sous_verrou_config
def remplacer_section(chemin: Path, nom: str, cles: list[tuple[str, str]], garder: tuple[str, ...] = ()) -> None:
    """Remplace (ou ajoute) la section `[nom]` par `cles` (valeurs TOML déjà rendues), sauf les clés de `garder` ; INV-INTERFACE-2."""
    texte = chemin.read_bytes().decode("utf-8") if chemin.is_file() else ""  # sans conversion de fins de ligne
    eol = "\r\n" if "\r\n" in texte else "\n"
    lignes = texte.splitlines(keepends=True)
    bloc = [f"[{nom}]{eol}", *(f"{k} = {v}{eol}" for k, v in cles)]
    debut = next((i for i, ligne in enumerate(lignes) if ligne.strip() == f"[{nom}]"), None)
    if debut is None:
        if lignes and not lignes[-1].endswith(("\n", "\r")):
            lignes[-1] += eol
        lignes += ([eol] if lignes else []) + bloc
    else:
        fin = next((j for j in range(debut + 1, len(lignes)) if lignes[j].lstrip().startswith("[")),
                   len(lignes))
        # Clés posées à la main que ce réglage ne porte pas (ex. `api`, `jeton_fichier`) : on ne les efface pas.
        gardees = [x for x in lignes[debut + 1:fin]
                   if "=" in x and not x.lstrip().startswith("#") and x.split("=", 1)[0].strip() in garder and x.split("=", 1)[0].strip() not in dict(cles)]
        lignes[debut:fin] = bloc + gardees + ([eol] if fin < len(lignes) else [])
    ecrire_atomique(chemin, "".join(lignes))  # INV-VAULT-2 : temporaire unique, puis os.replace


def appliquer(config: Config, c: CorpsInterface) -> dict:
    """Valide, applique en mémoire puis persiste. Changer de mode remet les familles au mode."""
    cible = ConfigInterface(**{k: getattr(config.interface, k) for k in
                               ("mode", "propositions", "langue", *FAMILLES)})
    if c.mode is not None:
        cible = ConfigInterface(mode=c.mode, langue=cible.langue)  # la langue survit au changement de mode
    for famille, valeur in (c.familles or {}).items():
        if famille not in FAMILLES:
            raise ValueError(f"famille inconnue : {famille}")
        setattr(cible, famille, valeur)
    if c.propositions is not None:
        cible.propositions = c.propositions
    if c.langue is not None:
        cible.langue = c.langue
    cible.__post_init__()
    if config.chemin:
        ecrire_section(config.chemin, cible)  # d'abord le disque : en cas d'échec rien ne change
    for k, v in vars(cible).items():
        setattr(config.interface, k, v)
    langues.regler(config.interface.langue)
    return config.interface.public()


def routes(config: Config, publier) -> APIRouter:
    r = APIRouter(prefix="/api/interface")

    # INV-STATUT-1 : l'interface reçoit le nom du statut de retour, jamais codé en dur.
    def etat(public: dict) -> dict:
        return {**public, "statut_retour": config.vault.statut_retour}

    @r.get("")
    async def lire():
        return etat(config.interface.public())

    @r.put("")
    async def ecrire(c: CorpsInterface):
        try:
            etat_ui = etat(appliquer(config, c))
        except ValueError as e:
            raise Invalide(str(e)) from e
        publier("interface")
        return etat_ui

    return r
