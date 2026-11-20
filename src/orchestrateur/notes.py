"""Notes du vault (lot 6) : chemins sûrs, liens, lecture et écriture d'une note.

Rôle : contrôler tout chemin venu d'un client, extraire et résoudre les liens d'une note
à la manière d'Obsidian, lire une note pour l'interface, l'écrire, la créer sans rien écraser,
la déplacer ou la renommer en réécrivant les liens qui la visent.
Frontières : ne parcourt pas le vault lui-même (index : `index_notes.py` ; balayage des
références : `references.py`) ; ne connaît pas HTTP ; le frontmatter n'est jamais réécrit.
Invariants portés : INV-NOTE-1 (chemins), INV-NOTE-2 (écriture), INV-NOTE-3 (déplacement).
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import os
import posixpath
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import unquote

from . import fiches, langues, references
from .vault import Conflit, Invalide, NonTrouve

INTERDITS = re.compile(r'[<>:"|?*\x00-\x1f]')
RESERVES = re.compile(r"(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³]|conin\$|conout\$)", re.I)
def _hors() -> str:
    return langues.t("serveur.notes.hors_vault")


class ConflitNote(Conflit):
    """409 qui porte la version courante de la note (INV-NOTE-2)."""

    def __init__(self, message: str, courante: dict):
        super().__init__(message)
        self.courante = courante


# --- INV-NOTE-1 : chemins ---------------------------------------------------------------
def exclu(rel: str, motifs: list[str]) -> bool:
    """Exclu si un segment est caché (nom commençant par un point : `.git`, `.obsidian`,
    `.claude`, `.trash`, `.playwright-mcp`…) ou si le chemin ou un de ses ancêtres répond à un
    motif de `notes.exclure` : un dossier exclu l'est à n'importe quelle profondeur."""
    parts = rel.split("/") if rel else []
    if any(s.startswith(".") for s in parts):
        return True
    # INV-NOTE-1 : insensible à la casse comme Windows/macOS, sinon `prive/` contournerait `Prive`.
    return any(fnmatch.fnmatchcase("/".join(parts[:i]).casefold(), m.casefold())
               for i in range(1, len(parts) + 1) for m in motifs)


def chemin_sur(racine: Path, chemin: str, motifs: list[str], vide_ok: bool = False
               ) -> tuple[str, Path]:
    """SEULE porte d'entrée d'un chemin client : renvoie (chemin relatif `/`, chemin absolu).

    INV-NOTE-1 : refuse `..`, absolus, lecteurs, UNC, flux alternatifs, noms réservés Windows,
    segments finissant par un point ou une espace (alias silencieux de Windows) ; puis résout
    liens symboliques, jonctions et noms courts 8.3 et revérifie racine et exclusions.
    """
    brut = (chemin or "").replace("\\", "/")
    if INTERDITS.search(brut):
        raise Invalide(langues.t("serveur.notes.chemin_invalide", chemin=chemin))
    if brut.startswith("/"):
        raise NonTrouve(_hors())
    segs = [s for s in brut.split("/") if s not in ("", ".")]
    for s in segs:
        if s == "..":
            raise NonTrouve(_hors())
        if s[-1] in ". " or RESERVES.fullmatch(s.split(".")[0].rstrip(" ")):
            raise Invalide(langues.t("serveur.notes.nom_reserve", nom=s))
    if not segs and not vide_ok:
        raise Invalide(langues.t("serveur.notes.chemin_vide"))
    rel = "/".join(segs)
    if exclu(rel, motifs):
        raise NonTrouve(_hors())
    reel = (racine / rel).resolve()
    try:
        rel_reel = reel.relative_to(racine).as_posix()
    except ValueError:
        raise NonTrouve(_hors()) from None
    rel_reel = "" if rel_reel == "." else rel_reel
    if exclu(rel_reel, motifs):
        raise NonTrouve(_hors())
    return rel_reel, reel


def nom_valide(nom: str) -> str:
    nom = (nom or "").strip()
    if nom.lower().endswith(".md"):
        nom = nom[:-3]
    if (not nom or "/" in nom or "\\" in nom or INTERDITS.search(nom) or nom[-1] in ". "
            or nom.startswith(".") or RESERVES.fullmatch(nom.split(".")[0].rstrip(" "))):
        raise Invalide(langues.t("serveur.notes.nom_invalide", nom=nom))
    return nom


# --- liens --------------------------------------------------------------------------------
WIKI = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
WIKI_CIBLE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
MARKDOWN = re.compile(r"(!?)\[([^\]\n]*)\]\(<?([^()<>\n]+?)>?(?:\s+\"[^\"\n]*\")?\)")
SCHEMA = re.compile(r"[a-z][a-z0-9+.-]*:", re.I)
CODE = re.compile(r"^(`{3,}|~{3,})[^\n]*\n.*?^\1[^\n]*$|`[^`\n]+`", re.M | re.S)


def _blanchir(m: re.Match) -> str:
    # Les liens cités dans du code ne sont pas des liens ; les numéros de ligne sont conservés.
    return re.sub(r"[^\n]", " ", m.group(0))


def liens_bruts(texte: str) -> list[tuple]:
    """(position, brut, cible, alias, ancre, incorporé, extrait) de chaque lien, dans l'ordre :
    wikilinks (incorporés ou non) et liens Markdown relatifs ; rien dans le code."""
    propre = CODE.sub(_blanchir, texte) if "`" in texte or "~~~" in texte else texte
    trouves = []
    for m in WIKI.finditer(propre):
        incorpore, interieur = m.groups()
        cible, _, alias = interieur.partition("|")
        cible, _, ancre = cible.rstrip("\\").partition("#")
        trouves.append((m.start(), m.group(0), cible.strip(), alias.strip(), ancre.strip(),
                        incorpore == "!"))
    if "](" in propre:
        for m in MARKDOWN.finditer(propre):
            url = unquote(m.group(3).strip())
            if SCHEMA.match(url) or url.startswith("#"):
                continue
            cible, _, ancre = url.partition("#")
            trouves.append((m.start(), m.group(0), cible.strip(), m.group(2).strip(),
                            ancre.strip(), m.group(1) == "!"))
        trouves.sort()
    sortie = []
    for t in trouves:
        fin = texte.find("\n", t[0])
        ligne = texte[texte.rfind("\n", 0, t[0]) + 1:fin if fin >= 0 else None]
        sortie.append((*t, ligne.strip()[:200]))
    return sortie


def cibles(texte: str) -> list[str]:
    """Cibles seules, pour l'index : même analyse que `liens_bruts`, sans le coût par lien
    de l'extrait (4 000 notes à lire en moins de 5 s)."""
    propre = CODE.sub(_blanchir, texte) if "`" in texte or "~~~" in texte else texte
    sortie = [m.partition("|")[0].rstrip("\\").partition("#")[0].strip()
              for m in WIKI_CIBLE.findall(propre)]
    if "](" in propre:
        sortie += [u.partition("#")[0].strip() for m in MARKDOWN.finditer(propre)
                   if not SCHEMA.match(u := unquote(m.group(3).strip())) and u[:1] != "#"]
    return sortie


def extraire(texte: str) -> list[dict]:
    return [{"brut": b, "cible": c, "alias": a, "ancre": n, "incorpore": i, "extrait": x}
            for _, b, c, a, n, i, x in liens_bruts(texte)]


def cle_nom(cible: str) -> str:
    """Clé de recherche par nom : dernier segment, sans casse, sans `.md`."""
    nom = cible.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return nom[:-3] if nom.endswith(".md") else nom


def _distance(a: str, b: str) -> int:
    pa, pb = [x for x in a.split("/") if x], [x for x in b.split("/") if x]
    commun = 0
    for x, y in zip(pa, pb):
        if x.lower() != y.lower():
            break
        commun += 1
    return len(pa) + len(pb) - 2 * commun


def resoudre(cible: str, depuis: str | None, chemins: dict[str, str],
             par_nom: dict[str, set[str]]) -> str | None:
    """Ordre d'Obsidian : chemin exact depuis la racine, puis relatif au dossier de la note,
    puis par nom (le plus proche du dossier de la note, puis le chemin le plus court).
    `chemins` : chemin en minuscules -> chemin ; `par_nom` : `cle_nom` -> chemins."""
    c = cible.strip().replace("\\", "/")
    if not c:
        return depuis or None  # `[[#ancre]]` : la note elle-même
    c = c.lstrip("/")
    dossier = posixpath.dirname(depuis) if depuis else ""

    def exact(x: str) -> str | None:
        x = posixpath.normpath(x)
        if x == "." or x.startswith("../") or x == "..":
            return None
        return chemins.get(x.lower()) or chemins.get(x.lower() + ".md")

    if r := exact(c):
        return r
    if dossier and (r := exact(f"{dossier}/{c}")):
        return r
    suffixe = c.lower().removesuffix(".md")
    candidats = [x for x in par_nom.get(cle_nom(c), ())
                 if "/" not in suffixe or x.lower().removesuffix(".md") == suffixe
                 or x.lower().removesuffix(".md").endswith("/" + suffixe)]
    if not candidats:
        return None
    return min(candidats, key=lambda x: (_distance(dossier, posixpath.dirname(x)), len(x), x))


# --- lecture ---------------------------------------------------------------------------------
TITRE = re.compile(r"^# +(.+?)\s*$", re.M)
CLE_FM = re.compile(r"^(titre|title|type):[ \t]*(.*?)\s*$", re.M | re.I)


def meta_rapide(texte: str, nom: str) -> tuple[str, str]:
    """(titre, type) sans analyse YAML : l'index lit ~4 000 notes en quelques secondes."""
    tete, _, _, corps = fiches.decouper(texte)
    cles = {k.lower(): v.strip("\"'") for k, v in CLE_FM.findall("".join(tete or []))}
    m = TITRE.search(corps)
    titre = m.group(1) if m else cles.get("titre") or cles.get("title") or nom
    return titre, cles.get("type", "")


def iso(mtime_ns: int) -> str:
    return dt.datetime.fromtimestamp(mtime_ns / 1e9).isoformat(timespec="seconds")


def nom_de(rel: str) -> str:
    nom = rel.rsplit("/", 1)[-1]
    return nom[:-3] if nom.lower().endswith(".md") else nom


def vers_client(texte: str) -> tuple[str, str, bool]:
    """(contenu tel que l'éditeur le voit, fin de ligne d'origine, BOM présent)."""
    bom = texte.startswith(fiches.BOM)
    texte = texte.removeprefix(fiches.BOM)
    eol = fiches.fin_de_ligne(texte)
    return (texte.replace("\r\n", "\n") if eol == "\r\n" else texte), eol, bom


def depuis_client(contenu: str, eol: str, bom: bool) -> str:
    # INV-NOTE-2 : transformation exactement inverse de `vers_client` (aller-retour à l'octet).
    if eol == "\r\n":
        contenu = contenu.replace("\r\n", "\n").replace("\n", "\r\n")
    if bom and not contenu.startswith(fiches.BOM):
        contenu = fiches.BOM + contenu
    return contenu


def note(index, vault, rel: str, p: Path) -> dict:
    """Modèle `Note` du contrat ; `index` : `IndexNotes` (résolution, entrants)."""
    try:
        st = p.stat()
        texte = fiches.lire(p)
    except FileNotFoundError:
        raise NonTrouve(langues.t("serveur.notes.introuvable", chemin=rel)) from None
    except (IsADirectoryError, PermissionError):
        raise Invalide(langues.t("serveur.notes.pas_une_note", chemin=rel)) from None
    contenu, _, _ = vers_client(texte)
    nom = nom_de(rel)
    titre, type_ = meta_rapide(texte, nom)
    liens = [{"brut": x["brut"], "cible": x["cible"], "chemin": index.resoudre(x["cible"], rel),
              "alias": x["alias"], "ancre": x["ancre"], "incorpore": x["incorpore"]}
             for x in extraire(texte)]
    cible = vault.racine / rel
    tache = next((t.id for t in vault.index()[0].values() if t.chemin == cible), None)
    return {"chemin": rel, "nom": nom, "titre": titre, "type": type_, "maj": iso(st.st_mtime_ns),
            "contenu": contenu, "mtime_ns": str(st.st_mtime_ns),
            "frontmatter": fiches.frontmatter(texte), "liens": liens,
            "entrants": index.entrants(rel), "tache": tache}


# --- écriture (INV-NOTE-2) ----------------------------------------------------------------
_ECRITURE = threading.Lock()  # contrôle de date puis remplacement : pas d'entrelacement local


def est_note(rel: str) -> None:
    if not rel.lower().endswith(".md"):
        raise Invalide(langues.t("serveur.notes.pas_une_note_md", chemin=rel))


def ecrire(index, vault, rel: str, p: Path, contenu: str, mtime_ns: str) -> dict:
    est_note(rel)
    with _ECRITURE:
        try:
            st = p.stat()
        except FileNotFoundError:
            raise NonTrouve(langues.t("serveur.notes.introuvable", chemin=rel)) from None
        if str(st.st_mtime_ns) != str(mtime_ns):
            # INV-NOTE-2 : modifiée ailleurs (Obsidian, agent) depuis la lecture : rien n'est écrit.
            raise ConflitNote(langues.t("serveur.notes.changee_ailleurs"),
                              note(index, vault, rel, p))
        _, eol, bom = vers_client(fiches.lire(p))
        try:
            fiches.ecrire_atomique(p, depuis_client(contenu, eol, bom))
            if (nouveau := p.stat().st_mtime_ns) <= st.st_mtime_ns:
                # INV-NOTE-2 : horloge de fichier grossière (ext4) : deux écritures rapprochées
                # garderaient la même date et le conflit passerait inaperçu.
                os.utime(p, ns=(st.st_mtime_ns + 1,) * 2)
        except PermissionError:
            raise Conflit(langues.t("serveur.notes.verrouillee")) from None
    index.maj(rel)
    return note(index, vault, rel, p)


def creer(index, vault, dossier: str, d: Path, nom: str, contenu: str,
          creer_dossier: bool) -> dict:
    nom = nom_valide(nom)
    if not d.is_dir():
        if d.exists():
            raise Invalide(langues.t("serveur.notes.pas_un_dossier", dossier=dossier))
        if not creer_dossier:
            raise NonTrouve(langues.t("serveur.notes.dossier_absent", dossier=dossier))
        d.mkdir(parents=True)
    rel = f"{dossier}/{nom}.md" if dossier else f"{nom}.md"
    if exclu(rel, index.motifs):  # INV-NOTE-1 : un motif d'exclusion peut viser le nom seul
        raise NonTrouve(_hors())
    p = d / f"{nom}.md"
    # INV-NOTE-2 : un vault partagé avec Windows/macOS ne tolère pas deux notes à la casse près ;
    # sous Linux, `link` seul les laisserait coexister.
    if any(x.name.casefold() == p.name.casefold() for x in d.iterdir()):
        raise Conflit(langues.t("serveur.notes.existe_deja", chemin=rel))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".orch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenu.encode("utf-8", errors="surrogateescape"))
            f.flush()
            os.fsync(f.fileno())
        # INV-NOTE-2 : `link` échoue si la cible existe (exact) :
        # création atomique qui n'écrase jamais.
        os.link(tmp, p)
    except FileExistsError:
        raise Conflit(langues.t("serveur.notes.existe_deja", chemin=rel)) from None
    finally:
        Path(tmp).unlink(missing_ok=True)
    index.maj(rel)
    return note(index, vault, rel, p)


# --- déplacement (INV-NOTE-3) -------------------------------------------------------------
def _renommer_wikilinks(texte: str, src: str, rel: str, nom: str, resoudre) -> str:
    """`[[ancien]]`, `[[ancien|a]]`, `[[ancien#x]]`, `![[ancien]]` -> `nom`, seulement s'ils
    résolvent (depuis `src`, index d'avant le déplacement) vers `rel` : homonymes intacts."""
    propre = CODE.sub(_blanchir, texte) if "`" in texte or "~~~" in texte else texte
    morceaux, pos = [], 0
    for m in WIKI.finditer(propre):
        interieur = m.group(2)
        cible = interieur.partition("|")[0].rstrip("\\").partition("#")[0].strip()
        if not cible or "/" in cible or "\\" in cible or cle_nom(cible) != cle_nom(rel) \
                or resoudre(cible, src) != rel:
            continue
        debut = m.start(2) + interieur.find(cible)
        morceaux += [texte[pos:debut], nom + (cible[-3:] if cible.lower().endswith(".md") else "")]
        pos = debut + len(cible)
    return "".join(morceaux) + texte[pos:]


def deplacer(index, vault, rel: str, p: Path, vers: str, q: Path, creer_dossier: bool,
             exclure: list[str], occupe) -> tuple[dict, int, bool]:
    """INV-NOTE-3 : (Note à sa nouvelle place, fichiers réécrits, une tâche a bougé).
    `occupe(id)` : un tour tourne ou attend sur cette tâche."""
    est_note(rel)
    est_note(vers)
    nom_valide(nom_de(vers))
    if not p.is_file():
        raise NonTrouve(langues.t("serveur.notes.introuvable", chemin=rel))
    t = next((t for t in vault.index()[0].values() if t.chemin == p), None)
    if t is not None and nom_de(rel) != nom_de(vers):
        raise Conflit(langues.t("serveur.notes.renommer_par_titre"))
    if t is not None and occupe(t.id):
        raise Conflit(langues.t("serveur.notes.seance_en_cours"))
    with _ECRITURE:
        if q.exists():
            raise Conflit(langues.t("serveur.notes.destination_existe", chemin=vers))  # INV-VAULT-2
        manquants = [d for d in [q.parent, *q.parent.parents] if not d.exists()]
        if manquants and not creer_dossier:
            raise NonTrouve(langues.t("serveur.notes.dossier_absent", dossier=posixpath.dirname(vers)))
        if not q.parent.is_dir() and not manquants:
            raise Invalide(langues.t("serveur.notes.pas_un_dossier", dossier=posixpath.dirname(vers)))
        deps = [(rel, vers)]
        racine = vault.racine
        # Contenus calculés AVANT toute écriture : une erreur de calcul ne laisse rien à défaire.
        textes: dict[str, tuple[bytes, str]] = {}
        existants = references.inventaire(racine, exclure)
        for r in references.planifier(racine, deps, exclure, [], existants):
            octets = (racine / r.fichier).read_bytes()
            nouveau, _ = references.reecrire(octets.decode("utf-8"), r.fichier, deps, racine,
                                             existants=existants[0])
            textes[r.fichier] = (octets, nouveau)
        if nom_de(rel) != nom_de(vers):
            # Mêmes exclusions que les chemins (lot 5) : Archives, .obsidian, `vault.exclure`.
            for src in sorted((index.citant(rel) | {rel}) & set(existants[1])):
                if src not in textes:
                    try:
                        octets = (racine / src).read_bytes()
                        textes[src] = (octets, octets.decode("utf-8"))
                    except (OSError, UnicodeDecodeError):
                        continue
                octets, texte = textes[src]
                textes[src] = (octets, _renommer_wikilinks(texte, src, rel, nom_de(vers),
                                                           index.resoudre))
        ecrits = [(f, o, x) for f, (o, x) in textes.items() if x != o.decode("utf-8")]
        # INV-ALIGN-2 : un tour sur une tâche dont le fichier est réécrit bloque, nommément.
        par_chemin = {t.chemin: t for t in vault.index()[0].values()}
        if bloquantes := [b for f, _, _ in ecrits if (b := par_chemin.get(racine / f))
                          and occupe(b.id)]:
            noms = ", ".join(f"« {b.titre} » ({b.id})" for b in bloquantes)
            raise Conflit(langues.t("serveur.notes.seance_en_cours_sur", taches=noms))
        crees: list[Path] = []
        faits: list[tuple[Path, bytes]] = []
        bouge = False
        try:
            for d in reversed(manquants):
                d.mkdir()
                crees.append(d)
            os.rename(p, q)  # rename (et non replace) : échoue si la cible existe
            bouge = True
            for f, octets, texte in ecrits:
                cible = racine / references.nouveau_chemin(f, deps)
                faits.append((cible, octets))
                fiches.ecrire_atomique(cible, texte)
        except Exception as e:
            for cible, octets in reversed(faits):
                cible.write_bytes(octets)
            if bouge:
                os.rename(q, p)
            for d in reversed(crees):
                d.rmdir()
            if isinstance(e, PermissionError):
                raise Conflit(langues.t("serveur.notes.deplacement_verrouille", fichier=e.filename or e)) from e
            raise Conflit(langues.t("serveur.notes.deplacement_annule", erreur=e)) from e
        finally:
            vault._index = None
    for f in [rel, vers, *(references.nouveau_chemin(f, deps) for f, _, _ in ecrits)]:
        if f.lower().endswith(".md"):
            index.maj(f)
    return note(index, vault, vers, q), len(ecrits), t is not None
