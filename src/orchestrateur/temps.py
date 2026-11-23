"""Le temps d'une tâche : échéance, priorité, retard, groupes de la vue « Aujourd'hui ».

Rôle : lire (avec tolérance) et valider (strictement) les clés `echeance` et `priorite`, dire si
une tâche est en retard, composer les groupes de la vue « Aujourd'hui ».
Frontières : lit l'index en mémoire de `Vault` ; n'écrit rien (l'écriture passe par
`Vault.poser_temps`, édition ligne à ligne, INV-VAULT-1).
Invariants portés : INV-TEMPS-1 (lecture tolérante, écriture stricte ; une valeur hors norme du
vault n'est jamais réécrite ni rejetée à la lecture).
"""

from __future__ import annotations

import datetime as dt

from . import langues
from . import vault as V  # module (et non `from`) : vault importe arbre, qui importe temps

PRIORITES = ("haute", "moyenne", "basse")
# `normale` existe déjà dans le vault : lue comme `moyenne` pour le tri, affichée telle quelle.
RANGS = {"haute": 0, "moyenne": 1, "normale": 1, "basse": 2}
HORIZON_JOURS = 7
GROUPES = ("retard", "aujourdhui", "semaine", "amoi")


def echeance_de(fm: dict, cle: str = "echeance") -> dt.date | None:
    """Date lue dans le frontmatter ; toute valeur illisible vaut « pas d'échéance »."""
    v = fm.get(cle)
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v).strip()[:10]) if v else None
    except ValueError:
        return None


def priorite_de(fm: dict) -> str:
    return str(fm.get("priorite") or "").strip().casefold()


def rang(priorite: str) -> int:
    return RANGS.get(priorite, 3)  # sans priorité (ou inconnue) : après les basses


def en_retard(vault: V.Vault, t: V.Tache) -> bool:
    e = echeance_de(t.fm)
    return bool(e and e < V.aujourdhui() and vault.ouverte(t))


def vue(vault: V.Vault, t: V.Tache) -> dict:
    """Champs communs aux nœuds de l'arbre, aux recherches et à la vue « Aujourd'hui »."""
    e = echeance_de(t.fm)
    return {"echeance": e.isoformat() if e else "", "priorite": priorite_de(t.fm),
            "retard": en_retard(vault, t)}


def reportee(t: V.Tache) -> bool:
    """INV-DECISIONS-3 : décision reportée, masquée (page, pastilles) jusqu'à la date, puis de retour d'elle-même."""
    d = echeance_de(t.fm, "reporte_jusqu_au")
    return bool(d and d > V.aujourdhui())


def poser(vault: V.Vault, ident: str, echeance, priorite) -> dict:
    """Pose le temps ; une échéance future donnée à une décision en attente est un report (INV-DECISIONS-3).
    Voie unique de l'interface, du téléphone et de Telegram."""
    maj = valider(echeance, priorite)
    if "echeance" in maj:
        t, e = vault.tache(ident), maj["echeance"]
        attend = t.statut == vault.retour or vault.a_valider(t) or en_retard(vault, t)
        maj["reporte_jusqu_au"] = e if e and e > V.aujourdhui() and attend else None
    vault.poser_temps(ident, maj)
    return maj


def valider(echeance, priorite) -> dict:
    """Écriture : date ISO exacte ou vide (retire la clé) ; priorité de la liste ou vide."""
    maj: dict = {}
    if echeance is not None:
        s = str(echeance).strip()
        try:
            maj["echeance"] = dt.date.fromisoformat(s) if s else None
        except ValueError:
            raise V.Invalide(langues.t("serveur.temps.echeance_format", valeur=s)) from None
    if priorite is not None:
        p = str(priorite).strip().casefold()
        if p and p not in PRIORITES:
            raise V.Invalide(langues.t("serveur.temps.priorite_attendue", valeurs=", ".join(PRIORITES)))
        maj["priorite"] = p or None
    return maj


def nb_retard(vault: V.Vault) -> int:
    return sum(en_retard(vault, t) for t in vault.index()[0].values())


def _cle_tri(t: dict) -> tuple:
    return (rang(t["priorite"]), t["echeance"] or "9999", t["titre"].casefold())


def aujourdhui(vault: V.Vault) -> dict:
    """Groupes de « qu'est-ce que je fais aujourd'hui ? » : chaque tâche ouverte n'apparaît que
    dans le premier groupe qui la concerne ; chaque groupe est trié par priorité."""
    jour = V.aujourdhui()
    limite = jour + dt.timedelta(days=HORIZON_JOURS)
    taches = vault.index()[0]
    parents = vault._parents(taches)
    groupes: dict[str, list] = {cle: [] for cle in GROUPES}
    for k, t in taches.items():
        if not vault.ouverte(t) or t.pilotage:  # INV-PILOTAGE-1
            continue
        e = echeance_de(t.fm)
        if e and e < jour:
            cle = "retard"
        elif e == jour:
            cle = "aujourdhui"
        elif e and e <= limite:
            cle = "semaine"
        elif t.statut == vault.retour or vault.a_valider(t):
            cle = "amoi"
        else:
            continue
        groupes[cle].append({"id": k, "titre": t.titre, "statut": t.statut,
                             "a_valider": vault.a_valider(t),
                             "resultat": t.fiche.get("resultat") or "",
                             "essai": t.fiche.get("essai") or "", **vue(vault, t),
                             "fil_ariane": vault.fil_ariane(k, parents)})
    titres = {"retard": langues.t("serveur.temps.retard"), "aujourdhui": langues.t("serveur.temps.aujourdhui"),
              "semaine": langues.t("serveur.temps.semaine", n=HORIZON_JOURS), "amoi": langues.t("serveur.temps.amoi")}
    return {"date": jour.isoformat(),
            "groupes": [{"cle": cle, "titre": titres[cle], "taches": sorted(groupes[cle], key=_cle_tri)}
                        for cle in GROUPES]}
