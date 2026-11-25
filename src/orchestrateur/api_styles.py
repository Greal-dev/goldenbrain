"""Feuille de styles unique de l'interface (INV-REACTIVITE-1).

Rôle : servir `/style-tout.css`, la concaténation des feuilles de `web/styles.liste` dans l'ordre de la cascade. Dix-huit
requêtes de feuilles au premier affichage deviennent une, sans étape de construction : l'assemblage se fait à la demande,
mémorisé tant qu'aucune feuille ne change (date de modification), et les fichiers sources restent ceux que l'on édite.
Frontières : lit `web/` seulement ; une feuille citée mais absente est ignorée (jamais une page sans style pour autant).
Invariants portés : INV-REACTIVITE-1.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Request, Response

LISTE = "styles.liste"


def feuilles(web: Path) -> list[str]:
    """Noms des feuilles, dans l'ordre de la liste ; lignes vides et commentaires (#) écartés."""
    try:
        lignes = (web / LISTE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [n for n in (ligne.strip() for ligne in lignes) if n and not n.startswith("#")]


def routes(web: Path) -> APIRouter:
    r = APIRouter()
    memo: dict = {"cle": None, "texte": "", "etag": ""}

    @r.get("/style-tout.css", include_in_schema=False)
    def feuille(request: Request):
        noms = [n for n in feuilles(web) if (web / n).is_file()]
        cle = tuple((n, (web / n).stat().st_mtime_ns) for n in noms)
        if memo["cle"] != cle:
            texte = "\n".join(f"/* {n} */\n" + (web / n).read_text(encoding="utf-8") for n in noms)
            memo.update(cle=cle, texte=texte, etag='"' + hashlib.sha1(texte.encode("utf-8")).hexdigest()[:16] + '"')
        if request.headers.get("if-none-match") == memo["etag"]:
            return Response(status_code=304, headers={"ETag": memo["etag"], "Cache-Control": "no-cache"})
        return Response(memo["texte"], media_type="text/css", headers={"ETag": memo["etag"], "Cache-Control": "no-cache"})

    return r
