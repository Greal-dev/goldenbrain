"""Arbre libre au-dessus des tâches : construction, fil d'Ariane, gestes « déplacer » et « monter ».

Rôle : bâtir, en une passe sur l'index en mémoire, la hiérarchie casquette → nœuds nommés
(opérations et conteneurs, profondeur libre) → tâches. La place d'un conteneur se lit dans
l'imbrication des dossiers (INV-ARBRE-2) ; `parent: A > B` de son `contexte.md` n'est qu'un
repli, lu pour un dossier pas encore aligné. Calcule aussi les écritures d'un rattachement
logique (repli des dossiers non déplaçables) et les exécute tout ou rien.
Frontières : ne lit aucun fichier pour construire l'arbre (index du `Vault`) ; ne crée, ne
déplace ni ne renomme aucun dossier (le déplacement réel est dans `geste.py`) ; les gestes sur
une tâche réutilisent ceux du `Vault`.
Invariants portés : INV-ARBRE-1 (seules `parent`, `casquette` et `updated` existante changent ;
tout ou rien, octets d'origine restaurés), INV-ARBRE-2 (le dossier fait foi), INV-VAULT-1.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import executant, fiches, langues, rangement, temps
from . import vault as V

log = logging.getLogger(__name__)
SEP = " > "


@dataclass
class Noeud:
    id: str
    type: str  # "casquette" | "operation" | "conteneur"
    titre: str
    casquette: str
    segment: str  # nom du nœud dans un chemin : opération = son nom ; conteneur = son dossier
    chemin: list[str]  # segments de la casquette (exclue) jusqu'au nœud inclus
    parent: str | None
    enfants: list[str] = field(default_factory=list)


def nom_dossier(cid: str) -> str:
    return cid.rsplit("/", 1)[-1]


def _cle(chemin: list[str]) -> list[str]:
    return [s.casefold() for s in chemin]


class Structure:
    """Nœuds au-dessus des tâches, tous conteneurs compris (même sans tâche visible)."""

    def __init__(self, conts: dict, libelles: dict, hors: frozenset[str] = frozenset(),
                 bases: tuple[str, str] = ("Casquettes", "Projets")):
        self.noeuds: dict[str, Noeud] = {}
        self._conts, self._libelles = conts, libelles
        self._ops: dict[tuple[str, str], str] = {}
        par_nom: dict[tuple[str, str], str] = {}
        for c in conts.values():
            par_nom.setdefault((c.casquette, nom_dossier(c.id).casefold()), c.id)
        # INV-ARBRE-2 : place lue dans les dossiers — (conteneur ancêtre, opérations, dossier
        # d'où partent ces opérations). `physique` : le conteneur ancêtre seul.
        self.places = {cid: self._place(cid, conts, hors, bases) for cid in conts}
        self.physique = {cid: p[0] for cid, p in self.places.items()}
        # `implicites` : placés par leur dossier (sans `parent:`) ; `logiques` : placés par un
        # `parent:` que leur dossier contredit (repli : écart à aligner ou dossier non déplaçable).
        self.implicites: set[str] = set()
        self.logiques: set[str] = set()
        self.dossiers_op: dict[str, set[str]] = defaultdict(set)  # opération → ses dossiers
        self._ancres = {c.id: self._ancre(c, par_nom) for c in conts.values()}
        self._couper_cycles()
        for cid in conts:
            self._conteneur(cid)

    @staticmethod
    def _place(cid: str, conts: dict, hors: frozenset[str],
               bases: tuple[str, str]) -> tuple[str | None, list[str], str | None]:
        """Place dans les dossiers : le plus proche conteneur ancêtre (hors casquettes et
        arrivée), les dossiers intermédiaires étant des opérations ; à défaut, les dossiers entre
        un dossier de casquette (ou `Projets`) et le conteneur."""
        parts = cid.split("/")
        for i in range(len(parts) - 1, 0, -1):
            d = "/".join(parts[:i])
            if d in conts and d not in hors:
                return d, parts[i:-1], d
        cas, projets = (b.split("/") for b in bases)
        for base in ([*cas, None], projets):  # None : n'importe quel dossier de casquette
            n = len(base)
            if len(parts) > n and all(x is None or x == y for x, y in zip(base, parts)):
                return None, parts[n:-1], "/".join(parts[:n])
        return None, [], None

    def _ancre(self, c, par_nom) -> tuple[str | None, list[str]]:
        x, ops, _ = self.places[c.id]
        if not c.explicite:
            self.implicites.add(c.id)  # INV-ARBRE-2 : sans `parent:`, le dossier dit tout
            return x, list(ops)
        # Repli : le DERNIER segment qui désigne un conteneur fixe la place ; ce conteneur porte
        # sa propre place ; les segments suivants sont des opérations sous lui.
        resolus = [par_nom.get((c.casquette, s.casefold())) for s in c.chemin]
        if c.id in resolus:
            log.warning("chemin qui se cite lui-même, rendu sous sa casquette : %s", c.id)
            ancre = None, []
        else:
            k = max((i for i, r in enumerate(resolus) if r), default=-1)
            ancre = (resolus[k] if k >= 0 else None), list(c.chemin[k + 1:])
        if (ancre[0], _cle(ancre[1])) != (x, _cle(ops)):
            self.logiques.add(c.id)
        return ancre

    def _couper_cycles(self) -> None:
        for cid in self._ancres:
            vus, x = {cid}, self._ancres[cid][0]
            while x and x not in vus:
                vus.add(x)
                x = self._ancres[x][0]
            if x == cid:
                log.warning("cycle de conteneurs coupé, rendu sous sa casquette : %s", cid)
                self._ancres[cid] = (None, [])
                self.implicites.discard(cid)
                self.logiques.add(cid)

    def _ajouter(self, n: Noeud) -> Noeud:
        self.noeuds[n.id] = n
        if n.parent:
            self.noeuds[n.parent].enfants.append(n.id)
        return n

    def _casquette(self, cas: str) -> Noeud:
        ident = f"casquette:{cas}"
        return self.noeuds.get(ident) or self._ajouter(
            Noeud(ident, "casquette", self._libelles.get(cas, cas), cas, "", [], None))

    def _operation(self, p: Noeud, nom: str) -> Noeud:
        if ident := self._ops.get((p.id, nom.casefold())):
            return self.noeuds[ident]
        chemin = [*p.chemin, nom]
        ident = self._ops[(p.id, nom.casefold())] = f"operation:{p.casquette}/{SEP.join(chemin)}"
        return self._ajouter(Noeud(ident, "operation", nom, p.casquette, nom, chemin, p.id))

    def _conteneur(self, cid: str) -> Noeud:
        if n := self.noeuds.get(cid):
            return n
        c, (x, ops) = self._conts[cid], self._ancres[cid]
        p = self._conteneur(x) if x else self._casquette(c.casquette)
        base = self.places[cid][2] if cid in self.implicites else None
        for op in ops:
            p = self._operation(p, op)
            if base:  # opération lue dans un dossier : on retient lequel
                base = f"{base}/{op}"
                self.dossiers_op[p.id].add(base)
        nom = nom_dossier(cid)
        return self._ajouter(Noeud(cid, "conteneur", c.titre, c.casquette, nom, [*p.chemin, nom],
                                   p.id))

    def conteneur(self, cid: str):
        return self._conts[cid]

    def sous_arbre(self, ident: str) -> list[str]:
        ordre, i = [ident], 0
        while i < len(ordre):
            ordre += self.noeuds[ordre[i]].enfants
            i += 1
        return ordre

    def ordonnes(self, n: Noeud) -> list[str]:
        # Conteneurs (ordre des identifiants) puis opérations (ordre des noms) : l'ordre d'avant.
        conts = sorted(e for e in n.enfants if self.noeuds[e].type == "conteneur")
        return conts + sorted((e for e in n.enfants if self.noeuds[e].type == "operation"),
                              key=lambda e: self.noeuds[e].titre)


def structure(vault, idx: tuple | None = None) -> Structure:
    idx = idx or vault.index()
    if vault._structure is None or vault._structure[0] is not idx:
        cfg = vault.cfg
        # Un dossier de casquette et l'arrivée ne sont jamais le parent implicite d'un projet.
        hors = frozenset(c for c in idx[1] if c == cfg.arrivee
                         or c.rsplit("/", 1)[0] == cfg.casquettes)
        vault._structure = (idx, Structure(idx[1], cfg.libelles, hors,
                                           (cfg.casquettes, cfg.projets)))
    return vault._structure[1]


def rendre(vault, toutes: bool, etat) -> list[dict]:
    idx = taches, conts = vault.index()
    s = structure(vault, idx)
    parents = vault._parents(taches)
    enfants: dict[str | None, list[str]] = defaultdict(list)
    for k, p in parents.items():
        if not taches[k].pilotage:  # INV-PILOTAGE-1 : la conversation d'un conteneur n'est pas listée
            enfants[p].append(k)
    racines: dict[str, list[str]] = defaultdict(list)
    for k in enfants[None]:
        racines[taches[k].conteneur].append(k)

    def noeud_tache(k: str, vus: set) -> dict | None:
        t = taches[k]
        kids = [n for e in enfants[k] if e not in vus and (n := noeud_tache(e, vus | {e}))]
        n_ouv = vault.ouverte(t) + sum(n["ouvertes"] for n in kids)
        if not toutes and not n_ouv:
            return None
        return {"id": k, "type": "tache", "titre": t.titre, "statut": t.statut,
                "statut_verrouille": t.verrouille, "etat_execution": etat(k),
                "echec": str(t.fm.get("echec_tour") or ""), "ouvertes": n_ouv, "enfants": kids,
                "situation": t.fiche.get("situation") or "",
                "maj": str(t.fm.get("updated") or ""),
                "genre": rangement.nature_de(t),  # INV-NATURE-1 : repère et filtre de l'arbre
                "etiquettes": _etiquettes(t.fm),  # INV-ETIQUETTE-1 : puces de l'arbre, filtre
                "lignes": [sum(x["fait"] for x in t.fiche["lignes"]), len(t.fiche["lignes"])],  # INV-LIGNES-1
                "harnais": str(t.fm.get("harnais") or ""),
                "modele": str(t.fm.get("modele") or ""), "a_valider": vault.a_valider(t),
                "executant": executant.de(t),  # INV-EXECUTANT-1 : pastille et filtre « Moi / IA »
                **temps.vue(vault, t),
                "deplacable": True, "montable": parents[k] is not None}

    def noeud(ident: str) -> dict | None:
        n = s.noeuds[ident]
        kids = [x for k in racines[ident] if (x := noeud_tache(k, {k}))] \
            if n.type == "conteneur" else []
        kids += [x for e in s.ordonnes(n) if (x := noeud(e))]
        if not kids:
            return None
        sous_casquette = n.parent is None or s.noeuds[n.parent].type == "casquette"
        deplacable = n.type == "operation" or (n.type == "conteneur" and conts[ident].contexte)
        return {"id": ident, "type": n.type, "titre": n.titre,
                "ouvertes": sum(x["ouvertes"] for x in kids), "enfants": kids,
                "deplacable": deplacable, "montable": deplacable and not sous_casquette,
                "logique": ident in s.logiques}  # INV-ARBRE-2 : rattachement par `parent:` seul

    casquettes = sorted((n for n in s.noeuds.values() if n.type == "casquette"),
                        key=lambda n: n.casquette)
    return [x for n in casquettes if (x := noeud(n.id))]


def fil(vault, ident: str, parents: dict | None = None) -> list[dict]:
    """Ancêtres d'une tâche, de la casquette à sa mère, avec les identifiants de `GET /arbre`."""
    idx = vault.index()
    taches = idx[0]
    s = structure(vault, idx)
    parents = parents or vault._parents(taches)
    chaine, nid = [], taches[ident].conteneur
    while nid is not None:
        n = s.noeuds[nid]
        chaine.insert(0, {"id": n.id, "type": n.type, "titre": n.titre})
        nid = n.parent
    meres, p = [], parents[ident]
    while p and p not in meres and p != ident:
        meres.insert(0, p)
        p = parents[p]
    return chaine + [{"id": m, "type": "tache", "titre": taches[m].titre} for m in meres]


# --- gestes ------------------------------------------------------------------------------
def _nature(vault, s: Structure, ident: str) -> str:
    taches, conts = vault.index()
    if ident.startswith(("casquette:", "operation:")) and ident in s.noeuds:
        return s.noeuds[ident].type
    if ident in taches:
        return "tache"
    if ident in conts:
        return "conteneur"
    raise V.NonTrouve(langues.t("serveur.arbre.element_inconnu", ident=ident))


def deplacer(vault, noeud: str, sous: str, taches_seules: bool = False) -> None:
    s = structure(vault)
    src, dst = _nature(vault, s, noeud), _nature(vault, s, sous)
    if src == "tache":
        if dst == "tache":
            vault.deplacer_parent(noeud, sous)
        elif dst == "conteneur":
            vault.deplacer_conteneur(noeud, sous)
        else:
            raise V.Conflit(langues.t("serveur.arbre.tache_dans_projet"))
        return
    _, n, cible = place(vault, noeud, sous, taches_seules)
    executer(vault, ecritures_logiques(vault, s, n, cible.chemin, cible.casquette))


def monter(vault, noeud: str, taches_seules: bool = False) -> None:
    s = structure(vault)
    if _nature(vault, s, noeud) == "tache":
        parents = vault._parents(vault.index()[0])
        if not (mere := parents[noeud]):
            raise V.Conflit(langues.t("serveur.arbre.sans_mere"))
        if grand_mere := parents[mere]:
            vault.deplacer_parent(noeud, grand_mere)
        else:
            vault.modifier(noeud, {"parent": None})
        return
    _, n, cible = place(vault, noeud, None, taches_seules)
    executer(vault, ecritures_logiques(vault, s, n, cible.chemin, cible.casquette))


def place(vault, noeud: str, sous: str | None,
          taches_seules: bool = False) -> tuple[Structure, Noeud, Noeud]:
    """Projet ou opération `noeud` et sa nouvelle place : `sous`, ou (absent) le grand-parent."""
    s = structure(vault)
    src = _nature(vault, s, noeud)
    if src == "casquette":
        raise V.Conflit(langues.t("serveur.arbre.casquette_fixe"))
    if src == "tache":
        raise V.Conflit(langues.t("serveur.arbre.tache_se_deplace"))
    if taches_seules:  # INV-ARBRE-2 : plus de geste purement logique par l'API
        raise V.Conflit(langues.t("serveur.arbre.plan_requis"))
    n = s.noeuds[noeud]
    if sous is None:
        p = s.noeuds[n.parent]
        if p.type == "casquette":
            raise V.Conflit(langues.t("serveur.arbre.deja_sous_casquette"))
        return s, n, s.noeuds[p.parent]
    if _nature(vault, s, sous) == "tache":
        raise V.Conflit(langues.t("serveur.arbre.pas_sous_tache"))
    if sous in s.sous_arbre(noeud):
        raise V.Conflit(langues.t("serveur.arbre.sous_lui_meme"))
    return s, n, s.noeuds[sous]


def ecritures_logiques(vault, s: Structure, n: Noeud, sous: list[str],
                       cas: str) -> dict[Path, dict]:
    """Rattachement logique (repli, sans déplacer de dossier) de `n` sous le chemin `sous` de la
    casquette `cas`, sa descendance avec lui : les clés à écrire, rien n'est écrit ici."""
    if any(SEP in x for x in [*sous, n.segment]):
        raise V.Conflit(langues.t("serveur.arbre.nom_separateur", sep=SEP.strip()))
    if cas == "?" and cas != n.casquette:
        raise V.Conflit(langues.t("serveur.arbre.casquette_inconnue"))
    taches, conts = vault.index()
    ancien, neuf = n.chemin, [*sous, n.segment]
    ecritures: dict[Path, dict] = {}
    for d in s.sous_arbre(n.id):
        if s.noeuds[d].type != "conteneur":
            continue
        c = conts[d]
        rattache = sous if d == n.id else neuf + s.noeuds[s.noeuds[d].parent].chemin[len(ancien):]
        maj: dict = {}
        range_ = bool(s.places[d][0] or s.places[d][1])
        suit = d != n.id and d in s.implicites
        if suit:
            pass  # rangé dans le dossier de son parent : il le suit sans rien écrire
        elif _cle(rattache) != _cle(c.chemin) or (not rattache and range_ and not c.explicite):
            # Vide mais rangé dans un conteneur ou une opération : `parent: ""` dit « sous la
            # casquette » ; sans la clé, le dossier le replacerait là (INV-ARBRE-2).
            maj["parent"] = SEP.join(rattache) or ("" if range_ else None)
        if cas != c.casquette and not (suit and cas == n.casquette):
            maj["casquette"] = cas  # un implicite garde la sienne si le geste n'en change pas
        if not maj:
            continue
        if not c.contexte:
            raise V.Conflit(langues.t("serveur.arbre.sans_contexte", dossier=d))
        ecritures[vault.racine / d / vault.cfg.contexte] = maj
        if "casquette" in maj:  # la casquette suit sur chaque tâche du conteneur
            for t in taches.values():
                if t.conteneur == d and V.casquette_normalisee(t.fm.get("casquette")) != cas:
                    ecritures[t.chemin] = {"casquette": cas}
    return ecritures


def executer(vault, ecritures: dict[Path, dict]) -> None:
    """INV-ARBRE-1 : tout ou rien ; au moindre échec, octets d'origine restaurés, puis 409."""
    plan = []
    for p, maj in ecritures.items():
        octets = p.read_bytes()
        texte = octets.decode("utf-8", errors="surrogateescape")
        if "updated" in fiches.frontmatter(texte):  # INV-ARBRE-1 : jamais créée par un geste
            maj = {**maj, "updated": V.aujourdhui()}
        plan.append((p, octets, fiches.modifier_cles(texte, maj)))  # INV-VAULT-1
    faits: list[tuple[Path, bytes]] = []
    vault._index = None
    try:
        for p, octets, texte in plan:
            faits.append((p, octets))
            fiches.ecrire_atomique(p, texte)
    except Exception as e:
        for p, octets in faits:
            p.write_bytes(octets)
        raise V.Conflit(langues.t("serveur.arbre.geste_annule", erreur=e)) from e


def _etiquettes(fm: dict) -> list[str]:
    from . import etiquettes  # import tardif : `etiquettes` dépend de `vault`, qui dépend de ce module
    return etiquettes.de(fm)
