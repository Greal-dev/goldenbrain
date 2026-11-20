"""Geste d'arbre sur un projet ou une opération : le dossier se déplace (le dossier fait foi).

Rôle : traduire « ranger ce nœud sous celui-là » (ou « le monter d'un niveau ») en un plan à
blanc — dossier à déplacer, références à réécrire, clés à poser — appliqué ensuite par
`Aligneur.appliquer` (même jeton, même point de restauration git, même tout ou rien).
Frontières : ne déplace rien lui-même ; la place est validée par `arbre.place`, les dossiers
calculés par `Aligneur.dossier`, l'application est celle de l'alignement (INV-ALIGN-1).
Invariants portés : INV-ARBRE-2 (un geste déplace le dossier ; `parent:` n'est plus écrit, sauf
rattachement logique d'un dossier non déplaçable), INV-ALIGN-3 (dépôt jamais déplacé).
"""

from __future__ import annotations

from . import arbre, langues
from .alignement import _egal, _nom_invalide, _sous
from .vault import SEPARATEUR, Conflit, casquette_normalisee


def planifier(aligneur, noeud: str, sous: str | None) -> dict:
    """Plan du geste : `sous` = cible ; absent = monter d'un niveau. N'écrit rien."""
    vault, cfg = aligneur.vault, aligneur.cfg
    s, n, cible = arbre.place(vault, noeud, sous)
    return _planifier(aligneur, s, n, cible, None)


def planifier_operation(aligneur, tache: str, nom: str) -> dict:
    """Plan de l'acceptation d'une proposition « operation » : le projet de `tache` rejoint
    l'opération `nom` (chemin `A > B`, existante ou nouvelle) en déplaçant son dossier."""
    vault = aligneur.vault
    c = vault.conteneur(vault.tache(tache).conteneur)
    chemin = [x.strip() for x in SEPARATEUR.split((nom or "").strip()) if x.strip()]
    if not chemin:
        raise Conflit(langues.t("serveur.geste.nom_requis"))
    if not c.contexte:
        raise Conflit(langues.t("serveur.geste.sans_contexte", dossier=c.id, fiche=aligneur.cfg.contexte))
    s = arbre.structure(vault)
    cle = [x.casefold() for x in chemin]
    n = s.noeuds[c.id]
    existante = next((o for o in s.noeuds.values() if o.type == "operation"
                      and o.casquette == c.casquette and [x.casefold() for x in o.chemin] == cle),
                     None)
    if existante:
        return planifier(aligneur, c.id, existante.id)
    # Opération nouvelle : son dossier est créé sous celui de la casquette, avec le projet dedans.
    casq = next((x for x in s.noeuds.values()
                 if x.type == "casquette" and x.casquette == c.casquette), None)
    if casq is None or any(_nom_invalide(x) for x in chemin):
        raise Conflit(langues.t("serveur.geste.casquette_ou_nom"))
    base = aligneur.dossier(s, casq.id, aligneur._casquettes())
    cible = arbre.Noeud(f"operation:{c.casquette}/{arbre.SEP.join(chemin)}", "operation",
                        chemin[-1], c.casquette, chemin[-1], chemin, casq.id)
    return _planifier(aligneur, s, n, cible, "/".join([base, *chemin, arbre.nom_dossier(c.id)]))


def _planifier(aligneur, s, n, cible, vers: str | None) -> dict:
    """Cœur du plan ; `vers` impose la destination (opération nouvelle, sans nœud dans `s`)."""
    vault, cfg = aligneur.vault, aligneur.cfg
    if cible.id == n.parent:
        raise Conflit(langues.t("serveur.geste.deja_sous", titre=n.titre, parent=cible.titre))
    cas = cible.casquette
    if cas == "?" and cas != n.casquette:
        raise Conflit(langues.t("serveur.geste.casquette_inconnue"))
    taches, conts = vault.index()
    sous_arbre = [d for d in s.sous_arbre(n.id) if s.noeuds[d].type == "conteneur"]
    ecarts = {e.conteneur for e in aligneur._bruts()}
    if x := next((d for d in sous_arbre if d != n.id and d in ecarts), None):
        raise Conflit(langues.t("serveur.geste.pas_range", ident=x))
    deps, avert, fiches_ = [], [], {}
    if n.type == "conteneur" and aligneur._depot(aligneur.racine / n.id):
        # Non déplaçable (INV-ALIGN-3) : il garde un rattachement logique, signalé comme tel.
        for p, maj in arbre.ecritures_logiques(vault, s, n, cible.chemin, cas).items():
            fiches_[p.relative_to(aligneur.racine).as_posix()] = maj
        avert.append(langues.t("serveur.geste.avert_code", titre=n.titre))
    else:
        de = _source(aligneur, s, n)
        vers = vers or _destination(aligneur, s, n, cible)
        if not _egal(de, vers):
            if aligneur.protege(de):
                raise Conflit(langues.t("serveur.geste.protege", chemin=de))
            if (aligneur.racine / vers).exists():
                raise Conflit(langues.t("serveur.geste.destination_existe", chemin=vers))
            if _sous(vers, de):
                raise Conflit(langues.t("serveur.geste.destination_dans_soi"))
            deps.append((de, vers))
        for d in sous_arbre:
            c, maj = conts[d], {}
            if c.explicite:
                maj["parent"] = None  # INV-ARBRE-2 : rangé, le dossier suffit
            if cas != c.casquette:
                maj["casquette"] = cas
            if maj and c.contexte:
                fiches_[f"{d}/{cfg.contexte}"] = maj
            if "casquette" in maj:  # la casquette suit sur chaque tâche du conteneur
                for t in taches.values():
                    if t.conteneur == d and casquette_normalisee(t.fm.get("casquette")) != cas:
                        fiches_[t.chemin.relative_to(aligneur.racine).as_posix()] = \
                            {"casquette": cas}
    if not deps and not fiches_:
        raise Conflit(langues.t("serveur.geste.rien_a_changer", titre=n.titre))
    return aligneur.simuler(deps, avert, fiches_, "déplacement")


def _source(aligneur, s, n) -> str:
    if n.type == "conteneur":
        return n.id
    de = aligneur.dossier(s, n.id, aligneur._casquettes())
    if not (aligneur.racine / de).is_dir():
        raise Conflit(langues.t("serveur.geste.operation_sans_dossier", titre=n.titre, chemin=de))
    return de


def _destination(aligneur, s, n, cible) -> str:
    cfg, nom = aligneur.cfg, n.segment
    if _nom_invalide(nom):
        raise Conflit(langues.t("serveur.geste.nom_inutilisable", nom=nom))
    if cible.type == "casquette" and n.type == "conteneur":
        anc, ops, _ = s.places[n.id]
        # Déjà directement sous une casquette dans les dossiers : il ne bouge pas, sauf s'il
        # est rangé dans le dossier d'une autre casquette.
        if not anc and not ops and not (_sous(n.id, cfg.casquettes) and cible.casquette
                                        != n.casquette):
            return n.id
        return f"{cfg.projets}/{nom}"
    return f"{aligneur.dossier(s, cible.id, aligneur._casquettes())}/{nom}"
