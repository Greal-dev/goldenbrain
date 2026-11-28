"""Index du vault : tâches, conteneurs, création, déplacement (promotion : `transformations`).

Rôle : seule vue structurée du vault ; toute écriture passe par un chemin issu de l'index.
Frontières : ne lance aucun harnais, ne connaît pas l'état d'exécution (fourni par l'appelant).
Invariants portés : INV-VAULT-2 (déplacement non destructif), INV-VAULT-3 (chemins issus de
l'index, sous la racine), INV-VAULT-4 (verrou `paperclip` sur statut et tags ; levé par le seul
geste humain `liberer`). L'arbre au-dessus des tâches et ses gestes vivent dans `arbre.py`.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import arbre, fiches, langues, rangement
from .config import STATUTS_FIXES, ConfigVault

log = logging.getLogger(__name__)


class ErreurOrch(Exception):
    code = 400


class Invalide(ErreurOrch):
    code = 400


MOTS_PHRASE = 4  # une phrase : au moins quatre mots


def exiger_description(texte, objet: str) -> str:
    """Création par un agent : la description dit de quoi il s'agit, en une phrase au moins."""
    texte = " ".join(str(texte or "").split())
    if len(texte.split()) < MOTS_PHRASE:
        # objet « tâche » : phrase dédiée (l'article change selon la langue) ; autre objet : déjà traduit par l'appelant
        raise Invalide(langues.t("serveur.vault.tache_sans_description") if objet == "tâche"
                       else langues.t("serveur.vault.sans_description", objet=objet))
    return texte


class NonTrouve(ErreurOrch):
    code = 404


class Conflit(ErreurOrch):
    code = 409


class TropTot(ErreurOrch):
    code = 429


@dataclass
class Tache:
    id: str
    chemin: Path
    conteneur: str
    fm: dict
    titre: str
    # Bloc fiche, lu avec le frontmatter et mis en cache avec lui : la recherche n'y relit rien.
    fiche: dict = field(default_factory=fiches.fiche_vide)

    @property
    def parent_brut(self) -> str | None:
        return nettoyer_lien(self.fm.get("parent"))

    @property
    def statut(self) -> str:
        return str(self.fm.get("statut") or "")

    @property
    def pilotage(self) -> bool:
        """Conversation d'un conteneur : hors des listes et des compteurs (INV-PILOTAGE-1)."""
        return str(self.fm.get("nature") or "") == "pilotage"

    # Paperclip mis en sommeil le 13/11 : le verrou se lève par `[vault] verrou_paperclip = false`
    # (posé par Vault.__init__) sans toucher aux clés `paperclip:` des tâches.
    verrou_actif = True

    @property
    def verrouille(self) -> bool:
        return Tache.verrou_actif and "paperclip" in self.fm


@dataclass
class Conteneur:
    id: str
    titre: str
    casquette: str
    operation: str | None  # chemin de rattachement en texte (segments joints par ` > `)
    chemin: list[str] = field(default_factory=list)  # segments de `parent:`
    contexte: bool = False  # porte un `contexte.md` : seul un tel conteneur se range
    # `parent:` posé (même vide, `parent: ""`) : la place logique ne se déduit plus du dossier.
    explicite: bool = False


SEPARATEUR = re.compile(r"\s+>\s+")


def segments(v) -> list[str]:
    """Segments d'un `parent:` de conteneur (`A > B`), wikilinks et espaces superflus tolérés."""
    if not v or not isinstance(v, str):
        return []
    return [s for x in SEPARATEUR.split(v.strip()) if (s := nettoyer_lien(x))]


def nettoyer_lien(v) -> str | None:
    if not v or not isinstance(v, str):
        return None
    v = v.strip().removeprefix("[[").removesuffix("]]").split("|")[0].split("#")[0]
    return v.rsplit("/", 1)[-1].removesuffix(".md").strip() or None


def casquette_normalisee(v) -> str | None:
    m = re.match(r"(C\d+|META)", str(v or ""))
    return m.group(1) if m else None


def slugifier(texte: str, minuscules: bool = True) -> str:
    ascii_ = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_).strip("-")[:60].strip("-")
    return (slug.lower() if minuscules else slug) or "tache"


def aujourdhui() -> dt.date:
    return dt.date.today()


def titre_de(texte: str, fm: dict, defaut: str) -> str:
    if m := re.search(r"^# +(.+?)\s*$", fiches.decouper(texte)[3], flags=re.M):
        return m.group(1)
    return str(fm.get("titre") or fm.get("title") or defaut)


TITRE_MAX = 200


def titre_valide(titre: str) -> str:
    """Titre propre : une ligne, non vide, raisonnablement court ; `Invalide` sinon (INV-RENOMMER-1)."""
    titre = " ".join(str(titre or "").split())
    if not titre:
        raise Invalide(langues.t("serveur.vault.titre_requis"))
    if len(titre) > TITRE_MAX:
        raise Invalide(langues.t("serveur.vault.titre_trop_long", max=TITRE_MAX))
    return titre


class Vault:
    def __init__(self, cfg: ConfigVault):
        self.cfg = cfg
        self.retour = cfg.statut_retour  # INV-STATUT-1 : seul nom reconnu pour l'attente humaine
        self.statuts = (*STATUTS_FIXES, self.retour)
        Tache.verrou_actif = cfg.verrou_paperclip
        self.racine = Path(cfg.racine).resolve()
        self._cache: dict[Path, tuple] = {}
        self._index: tuple | None = None
        self._rels: dict[Path, str] = {}
        self.apres_statut = None  # INV-REX-1 : écouteur (ident, ancien, nouveau, humain) posé par `rex.Rex`
        self._structure: tuple | None = None  # (index, arbre.Structure) : suit l'index

    # --- lecture -----------------------------------------------------------------------
    def _rel(self, p: Path) -> str:
        # `resolve()` coûte ~1 ms par chemin sous Windows (profil du 12/11) : on mémorise.
        if (rel := self._rels.get(p)) is None:
            rel = self._rels[p] = p.resolve().relative_to(self.racine).as_posix()
        return rel

    def _rel_sur(self, p: Path) -> str | None:
        # INV-VAULT-3 : un lien qui sort de la racine est ignoré, sans faire tomber l'index.
        try:
            return self._rel(p)
        except ValueError:
            log.warning("hors du vault, ignoré : %s", p)
            return None

    def _exclu(self, rel: str) -> bool:
        return any(fnmatch.fnmatch(rel, m) for m in self.cfg.exclure)

    def _lire_meta(self, p: Path) -> tuple[dict, str, dict]:
        st = p.stat()
        cle = (st.st_mtime_ns, st.st_size)
        if (c := self._cache.get(p)) and c[0] == cle:
            return c[1:]
        texte = fiches.lire(p)
        fm = fiches.frontmatter(texte)
        titre = titre_de(texte, fm, p.stem)
        self._cache[p] = (cle, fm, titre, fiches.lire_fiche(texte))
        return self._cache[p][1:]

    def index(self) -> tuple[dict[str, Tache], dict[str, Conteneur]]:
        # Un tour appelle l'index plusieurs fois de suite (0,35 s pièce sur ~250 fichiers,
        # mesuré le 12/11) : on le garde `index_ttl_s` secondes ; toute écriture le périme.
        if self._index and time.monotonic() - self._index[0] < self.cfg.index_ttl_s:
            return self._index[1]
        resultat = self._index_frais()
        self._index = (time.monotonic(), resultat)
        return resultat

    def _index_frais(self) -> tuple[dict[str, Tache], dict[str, Conteneur]]:
        fichiers: dict[str, Path] = {}
        prefixes = []
        for motif in self.cfg.taches:
            prefixes.append(motif.split("/taches/")[0] if "/taches/" in motif else None)
            for p in self.racine.glob(motif):
                if (rel := self._rel_sur(p)) is None:
                    continue
                if p.is_file() and not self._exclu(rel):
                    fichiers[rel] = p
        taches: dict[str, Tache] = {}
        for rel in sorted(fichiers):
            p = fichiers[rel]
            fm, titre, fiche = self._lire_meta(p)
            ident = p.stem
            if ident in taches:
                ident = f"{p.stem}~{hashlib.sha1(rel.encode()).hexdigest()[:4]}"
            dossier = p.parent.parent if p.parent.name == "taches" else p.parent
            taches[ident] = Tache(ident, p, self._rel(dossier) if dossier != self.racine else "",
                                  fm, titre, fiche)
        ids_conteneurs = {t.conteneur for t in taches.values()} | {self.cfg.arrivee}
        for prefixe in filter(None, prefixes):
            for d in self.racine.glob(prefixe):
                if ((d / "taches").is_dir() or (d / self.cfg.contexte).is_file()) \
                        and (rel := self._rel_sur(d)) is not None and not self._exclu(rel):
                    ids_conteneurs.add(rel)
        conteneurs = {c: self._conteneur(c, taches) for c in sorted(ids_conteneurs)}
        return taches, conteneurs

    def _conteneur(self, ident: str, taches: dict[str, Tache]) -> Conteneur:
        ctx = self.racine / ident / self.cfg.contexte
        try:
            fm, contexte = self._lire_meta(ctx)[0], True  # relu seulement si le fichier a changé
        except OSError:
            fm, contexte = {}, False
        cas = casquette_normalisee(fm.get("casquette"))
        if not cas:
            cas = next((c for t in taches.values() if t.conteneur == ident
                        and (c := casquette_normalisee(t.fm.get("casquette")))), None)
        chemin = segments(fm.get("parent"))
        return Conteneur(ident, str(fm.get("nom") or ident.rsplit("/", 1)[-1]), cas or "?",
                         " > ".join(chemin) or None, chemin, contexte,
                         fm.get("parent") is not None)

    def tache(self, ident: str) -> Tache:
        try:
            return self.index()[0][ident]
        except KeyError:
            raise NonTrouve(langues.t("serveur.vault.tache_inconnue", ident=ident)) from None

    def conteneur(self, ident: str) -> Conteneur:
        try:
            return self.index()[1][ident]
        except KeyError:
            raise NonTrouve(langues.t("serveur.vault.conteneur_inconnu", ident=ident)) from None

    @staticmethod
    def _parents(taches: dict[str, Tache]) -> dict[str, str | None]:
        return {t.id: (p if (p := t.parent_brut) in taches and p != t.id else None)
                for t in taches.values()}

    def enfants(self, ident: str) -> list[str]:
        parents = self._parents(self.index()[0])
        return [k for k, p in parents.items() if p == ident]

    def descendance(self, ident: str) -> list[str]:
        parents = self._parents(self.index()[0])
        ordre, i = [ident], 0
        while i < len(ordre):
            ordre += [k for k, p in parents.items() if p == ordre[i] and k not in ordre]
            i += 1
        return ordre

    def fil_ariane(self, ident: str, parents: dict | None = None) -> list[str]:
        # `parents` est fourni par un parcours de toutes les tâches (recherche).
        return [n["id"].split(":", 1)[1] if n["type"] == "casquette" else n["titre"]
                for n in arbre.fil(self, ident, parents)]

    @staticmethod
    def a_valider(t: Tache) -> bool:
        """Terminée par son agent (`fait` avec une session), en attente du validateur."""
        return t.statut == "fait" and bool(t.fm.get("session"))

    def ouverte(self, t: Tache) -> bool:
        return t.statut in self.cfg.statuts_ouverts or self.a_valider(t)

    def detail(self, ident: str) -> dict:
        t = self.tache(ident)
        texte = fiches.lire(t.chemin)
        return {"id": t.id, "chemin": str(t.chemin), "titre": t.titre, "conteneur": t.conteneur,
                "fil_ariane": self.fil_ariane(ident), "fil": arbre.fil(self, ident),
                "frontmatter": t.fm, "statut": t.statut,
                "genre": rangement.nature_de(t), "genre_pose": bool(rangement.valide(t.fm.get("genre"))),  # INV-NATURE-1
                "statut_verrouille": t.verrouille, "harnais": str(t.fm.get("harnais") or ""),
                "session": str(t.fm.get("session") or ""), "fiche": fiches.lire_fiche(texte),
                "corps": fiches.corps_sans_fiche(texte), "enfants": self.enfants(ident),
                "parent": self._parents(self.index()[0])[ident]}

    def arbre(self, toutes: bool, etat=lambda ident: "inactif") -> list[dict]:
        return arbre.rendre(self, toutes, etat)

    # --- écriture ----------------------------------------------------------------------
    def modifier(self, ident: str, maj: dict, fiche: dict | None = None) -> None:
        self._modifier(self.tache(ident), maj, fiche)

    def _modifier(self, t: Tache, maj: dict, fiche: dict | None = None) -> None:
        maj = dict(maj)
        if t.verrouille:  # INV-VAULT-4 : Paperclip reste seul maître du statut.
            maj.pop("statut", None)
            maj.pop("tags", None)
        texte = fiches.modifier_cles(fiches.lire(t.chemin), {**maj, "updated": aujourdhui()})
        if fiche is not None:
            texte = fiches.ecrire_fiche(texte, fiche)
        self._index = None
        fiches.ecrire_atomique(t.chemin, texte)

    def renommer(self, ident: str, titre: str) -> None:
        """Change le titre affiché (le `# …` du corps) ; identifiant et nom de fichier restent (INV-RENOMMER-1)."""
        titre = titre_valide(titre)
        t = self.tache(ident)
        if titre == t.titre:
            return
        texte = fiches.modifier_cles(fiches.lire(t.chemin), {"updated": aujourdhui()})
        self._index = None
        fiches.ecrire_atomique(t.chemin, fiches.renommer_titre(texte, titre))

    def statut_declare(self, declaration: str) -> str:
        """`statut:` d'une fiche (`en_cours`, `en_attente`, `terminee`) -> statut vault."""
        return {"en_cours": "en-cours", "en_attente": self.retour, "terminee": "fait"}[declaration]

    def poser_statut(self, ident: str, statut: str, humain: bool = False) -> None:
        if statut not in self.statuts:
            raise Invalide(langues.t("serveur.vault.statut_inconnu", statut=statut))
        t = self.tache(ident)
        if t.verrouille:  # INV-VAULT-4
            if humain:
                raise Conflit(langues.t("serveur.vault.statut_tenu_paperclip"))
            return
        maj: dict = {"statut": statut}
        tags = t.fm.get("tags")
        if isinstance(tags, list) and t.statut and t.statut in tags and t.statut != statut:
            maj["tags"] = [statut if x == t.statut else x for x in tags]
        from . import recent  # import tardif : recent -> etiquettes -> vault
        ouverts = self.cfg.statuts_ouverts
        maj.update(recent.pour_statut(t.fm, t.statut in ouverts, statut in ouverts, humain))  # INV-RECENT-1
        self.modifier(ident, maj)
        if self.apres_statut:
            self.apres_statut(ident, t.statut, statut, humain)

    def liberer(self, ident: str) -> None:
        """Geste humain : retire `paperclip` et `execution` ; la tâche redevient pilotable."""
        t = self.tache(ident)
        if "paperclip" not in t.fm and "execution" not in t.fm:
            raise Conflit(langues.t("serveur.vault.pas_tenue_paperclip"))
        texte = fiches.retirer_cles(fiches.lire(t.chemin), ("paperclip", "execution"))
        self._index = None
        fiches.ecrire_atomique(t.chemin, texte)

    def creer(self, titre: str, conteneur: str | None = None, parent: str | None = None,
              description: str = "", harnais: str | None = None,
              temps: dict | None = None, cles: dict | None = None) -> str:
        if not titre or not titre.strip():
            raise Invalide(langues.t("serveur.vault.titre_requis"))
        if parent:
            conteneur = conteneur or self.tache(parent).conteneur
        c = self.conteneur(conteneur or self.cfg.arrivee)  # INV-VAULT-3
        dossier = self.racine / c.id / "taches"
        dossier.mkdir(parents=True, exist_ok=True)
        jour = aujourdhui()
        base = f"{jour.isoformat()}-{slugifier(titre)}"
        chemin, n = dossier / f"{base}.md", 2
        while chemin.exists():
            chemin, n = dossier / f"{base}-{n}.md", n + 1
        fm = {"type": "tache", "created": jour, "updated": jour,
              "casquette": c.casquette if c.casquette != "?" else None,
              "projet": c.id.rsplit("/", 1)[-1], "statut": "a-faire",
              **self.cfg.gabarit_tache, "parent": parent, "harnais": harnais, **(temps or {}), **(cles or {})}
        lignes = [f"{k}: {fiches.valeur_yaml(v)}" for k, v in fm.items() if v is not None]
        corps = f"# {titre.strip()}\n" + (f"\n{description.strip()}\n" if description else "")
        self._index = None
        fiches.ecrire_atomique(chemin, "---\n" + "\n".join(lignes) + "\n---\n\n" + corps)
        return next(t.id for t in self.index()[0].values() if t.chemin == chemin)

    def _deplacer(self, ids: list[str], conteneur: str, maj: dict[str, dict]) -> None:
        c = self.conteneur(conteneur)  # INV-VAULT-3
        taches = self.index()[0]
        dest = self.racine / c.id / "taches"
        plan = [(taches[k], dest / taches[k].chemin.name) for k in ids]
        noms = [d for _, d in plan]
        # INV-VAULT-2 : un déplacement ne détruit jamais ; tout est vérifié avant d'agir.
        if len(set(noms)) != len(noms) or any(d.exists() and d != t.chemin for t, d in plan):
            raise Conflit(langues.t("serveur.vault.fichier_meme_nom", conteneur=conteneur))
        dest.mkdir(parents=True, exist_ok=True)
        commun = {"projet": c.id.rsplit("/", 1)[-1]}
        if c.casquette != "?":
            commun["casquette"] = c.casquette
        # INV-VAULT-2 : renommages d'abord, frontmatter ensuite ; au moindre échec, tout est
        # défait (octets d'origine restaurés, renommages annulés) : jamais d'état à moitié déplacé.
        renommes: list[tuple[Path, Path]] = []
        originaux: dict[Path, bytes] = {}
        try:
            for t, d in plan:
                if d != t.chemin:
                    self._index = None
                    os.rename(t.chemin, d)  # rename (et non replace) : échoue si la cible existe
                    renommes.append((t.chemin, d))
            # Par chemin et non par identifiant : un renommage décale les suffixes d'homonymes.
            for t, d in plan:
                originaux[d] = d.read_bytes()
                self._modifier(replace(t, chemin=d), {**commun, **maj.get(t.id, {})})
        except Exception as e:
            for d, octets in originaux.items():
                d.write_bytes(octets)
            for origine, d in reversed(renommes):
                self._index = None
                os.rename(d, origine)
            raise Conflit(langues.t("serveur.vault.deplacement_annule", erreur=e)) from e

    def deplacer_conteneur(self, ident: str, conteneur: str) -> None:
        self.tache(ident)
        self._deplacer(self.descendance(ident), conteneur, {ident: {"parent": None}})

    def deplacer_parent(self, ident: str, parent: str) -> None:
        t, mere = self.tache(ident), self.tache(parent)
        if parent in self.descendance(ident):
            raise Conflit(langues.t("serveur.vault.enfant_de_descendance"))
        if mere.conteneur == t.conteneur:
            self.modifier(ident, {"parent": parent})
        else:
            self._deplacer(self.descendance(ident), mere.conteneur, {ident: {"parent": parent}})

    def consigner(self, ident: str, section: str, ligne: str) -> None:
        """Ajoute une ligne horodatée à une section du corps (feux verts) ; frontmatter intact."""
        t = self.tache(ident)
        texte = fiches.ajouter_a_section(fiches.lire(t.chemin), section, ligne)
        self._index = None
        fiches.ecrire_atomique(t.chemin, texte)

    def reecrire(self, ident: str, transformer) -> None:
        """Réécrit le fichier par `transformer(texte) -> texte` (bloc géré des notes) ; le
        transformateur ne touche qu'à son bloc (INV-VAULT-1, INV-EXECUTANT-2)."""
        t = self.tache(ident)
        texte = transformer(fiches.lire(t.chemin))
        self._index = None
        fiches.ecrire_atomique(t.chemin, texte)

    def poser_temps(self, ident: str, maj: dict) -> None:
        """Pose ou retire (valeur None) `echeance` et `priorite` ; `maj` vient de `temps.valider`."""
        self.modifier(ident, maj)
