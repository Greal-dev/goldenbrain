"""Route du compagnon mobile : `GET /api/compagnon/instantane` (lecture seule, validée par ETag).

Rôle : servir l'instantané de `compagnon.py` ; répondre 304 quand rien n'a changé depuis l'empreinte
que le téléphone détient (`If-None-Match`). Frontières : aucune écriture ; la garde d'appareil
(INV-DISTANT-6) s'applique avant, comme à toute route ; aucun cache HTTP (`no-store`) : le seul stockage
local est celui, optionnel, que décide `hors_ligne` (INV-PWA-2).
Invariants portés : INV-COMPAGNON-1 (voir `compagnon.py`), INV-PWA-2 (le serveur dit si le stockage
local est permis et pour combien de temps).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from . import compagnon


def routes(config, moteur) -> APIRouter:
    r = APIRouter(prefix="/api/compagnon")

    @r.get("/instantane")
    async def instantane(request: Request):
        contenu = await asyncio.to_thread(compagnon.instantane, moteur)
        etag = f'"{compagnon.empreinte(contenu)}"'
        entetes = {"ETag": etag, "Cache-Control": "no-store"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=entetes)
        return JSONResponse({"empreinte": etag.strip('"'), "genere": compagnon.horodatage(), "ttl_s": compagnon.TTL_S,
                             "hors_ligne": config.distant.hors_ligne, **contenu}, headers=entetes)

    return r
