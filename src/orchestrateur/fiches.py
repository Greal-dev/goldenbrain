"""Lecture et réécriture d'UN fichier de tâche.

Rôle : découper frontmatter / corps, éditer les clés gérées ligne à ligne, lire et écrire
le bloc fiche, analyser le bloc `<fiche>` rendu par l'agent, écrire atomiquement.
Frontières : ne parcourt pas le vault, ne connaît ni l'index ni le moteur.
Invariants portés : INV-VAULT-1 (édition ligne à ligne, reste restitué octet pour octet),
INV-VAULT-2 (écriture atomique).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import stat
import uuid
from pathlib import Path

import yaml

DEBUT = "<!-- orchestrateur:debut -->"
FIN = "<!-- orchestrateur:fin -->"
# Bloc géré des notes de l'utilisateur (INV-EXECUTANT-2), distinct du bloc fiche.
NOTES_DEBUT = "<!-- orchestrateur:notes -->"
NOTES_FIN = "<!-- orchestrateur:notes-fin -->"
# Bloc géré des lignes de tâche (INV-LIGNES-1) : travaux courts cochables, distincts du bloc fiche
# (qu'un agent réécrit en entier) et des notes de l'utilisateur.
LIGNES_DEBUT = "<!-- orchestrateur:lignes -->"
LIGNES_FIN = "<!-- orchestrateur:lignes-fin -->"
CLES_GEREES = ("statut", "updated", "harnais", "session", "parent", "projet", "casquette", "tags",
               "alimente", "prerequis", "voir_aussi", "modele", "echeance", "priorite", "echec_tour", "ou", "controle",
               "moteur_impose", "moteur_motif", "execution", "validation", "validation_accord",
               "nature", "genre", "programme", "routine", "contexte", "rattrapage",
               "executant", "apprendre", "chaine", "chaine_phase", "reporte_jusqu_au")  # INV-DECISIONS-3, INV-ROUTINE-2, INV-EXECUTANT-1, INV-APPRENDRE-1, INV-CHAINE-1
CHAMPS = (("fait", "Fait"), ("resultat", "Résultat"), ("essai", "Essai"),
          ("situation", "Situation"), ("reste", "Reste à faire"), ("prochain_pas", "Prochain pas"))
# INV-APPRENDRE-1 : champ facultatif, hors CHAMPS (les autres lecteurs de la fiche l'ignorent) ; une seule ligne.
RETENIR = ("retenir", "Ce que vous pouvez retenir")
BOM = "﻿"


def lire(chemin: Path) -> str:
    # INV-VAULT-1 : surrogateescape garantit l'aller-retour octet pour octet même hors UTF-8.
    return chemin.read_bytes().decode("utf-8", errors="surrogateescape")


def ecrire_atomique(chemin: Path, texte: str) -> None:
    # INV-VAULT-2 : temporaire dans le même dossier puis os.replace, jamais de fichier à moitié écrit.
    # C10 : mkstemp crée en 0600 ; une fiche réécrite garde ses droits d'origine (un fichier neuf, ceux du umask).
    tmp = str(chemin.parent / f".orch-{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(texte.encode("utf-8", errors="surrogateescape"))
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, stat.S_IMODE(os.stat(chemin).st_mode))
        except FileNotFoundError:
            pass
        os.replace(tmp, chemin)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _lignes(texte: str) -> list[str]:
    # Découpe sur \n seulement : splitlines couperait aussi sur \x0c,  …
    return re.findall(r"[^\n]*\n|[^\n]+$", texte)


def _nu(ligne: str) -> str:
    return ligne.rstrip("\r\n")


def decouper(texte: str) -> tuple[list[str] | None, str, str, str]:
    """Renvoie (lignes du frontmatter | None, ouverture, fermeture, corps)."""
    lignes = _lignes(texte)
    if not lignes or _nu(lignes[0]).removeprefix(BOM) != "---":
        return None, "", "", texte
    for i in range(1, len(lignes)):
        if _nu(lignes[i]) in ("---", "..."):
            return lignes[1:i], lignes[0], lignes[i], "".join(lignes[i + 1:])
    return None, "", "", texte


def fin_de_ligne(texte: str) -> str:
    premiere = texte.find("\n")
    return "\r\n" if premiere > 0 and texte[premiere - 1] == "\r" else "\n"


def _jsonable(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


def frontmatter(texte: str) -> dict:
    tete = decouper(texte)[0]
    if tete is None:
        return {}
    try:
        donnees = yaml.safe_load("".join(tete))
    except yaml.YAMLError:
        # INV-VAULT-4, INV-EXEC-3 : un YAML cassé ne doit pas faire oublier `paperclip` ni `session`.
        return _repli(tete)
    return _jsonable(donnees) if isinstance(donnees, dict) else {}


def _repli(tete: list[str]) -> dict:
    donnees = {}
    for ligne in tete:
        if m := re.match(r"([A-Za-z_][\w-]*):\s*(.*)$", _nu(ligne)):
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            donnees[m.group(1)] = v
    return donnees


def _scalaire(v) -> str:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    s = str(v)
    # `>` admis hors tête : un chemin d'arbre `A > B` reste un scalaire nu (INV-VAULT-1).
    if re.fullmatch(r"[\w][\w.\-/~ >]*", s) and not s.endswith(" "):
        try:
            if yaml.safe_load(s) == s:
                return s
        except yaml.YAMLError:
            pass
    return json.dumps(s, ensure_ascii=False)


def valeur_yaml(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_scalaire(x) for x in v) + "]"
    return _scalaire(v)


def _etendue(tete: list[str], cle: str) -> tuple[int, int] | None:
    motif = re.compile(rf"{re.escape(cle)}\s*:")
    for i, ligne in enumerate(tete):
        if motif.match(ligne):
            j = i + 1
            # Valeur sur plusieurs lignes : lignes indentées ou liste en colonne 0.
            while j < len(tete) and ((tete[j][:1] in (" ", "\t") and tete[j].strip())
                                     or tete[j].startswith("- ") or _nu(tete[j]) == "-"):
                j += 1
            return i, j
    return None


def modifier_cles(texte: str, maj: dict) -> str:
    """Pose (ou retire si None) des clés gérées ; tout le reste est restitué tel quel."""
    tete, ouverture, fermeture, corps = decouper(texte)
    eol = fin_de_ligne(texte)
    if tete is None:
        tete, ouverture, fermeture, corps = [], f"---{eol}", f"---{eol}", texte
        if texte.startswith(BOM):
            ouverture, corps = BOM + ouverture, texte[1:]
    tete = list(tete)
    for cle, val in maj.items():
        if cle not in CLES_GEREES:
            raise ValueError(f"clé non gérée : {cle}")  # INV-VAULT-1
        pos = _etendue(tete, cle)
        if pos is None:
            if val is not None:
                tete.append(f"{cle}: {valeur_yaml(val)}{eol}")
            continue
        i, j = pos
        fin = tete[i][len(_nu(tete[i])):] or eol
        tete[i:j] = [] if val is None else [f"{cle}: {valeur_yaml(val)}{fin}"]
    return ouverture + "".join(tete) + fermeture + corps


def renommer_titre(texte: str, titre: str) -> str:
    """Remplace le titre `# …` du corps (celui que lit `vault.titre_de`) ; frontmatter et reste du corps
    restitués tels quels (INV-VAULT-1). Sans titre `# …`, en pose un en tête du corps."""
    _, _, _, corps = decouper(texte)
    debut = texte[:len(texte) - len(corps)]
    if m := re.search(r"^# +(.+?)\s*$", corps, flags=re.M):
        return debut + corps[:m.start(1)] + titre + corps[m.end(1):]
    eol = fin_de_ligne(texte)
    return debut + f"# {titre}{eol}" + (eol if corps.strip() else "") + corps


def retirer_cles(texte: str, cles: tuple[str, ...]) -> str:
    """Retire des clés quelconques (geste humain « libérer ») ; le reste restitué tel quel."""
    tete, ouverture, fermeture, corps = decouper(texte)
    if tete is None:
        return texte
    tete = list(tete)
    for cle in cles:
        if pos := _etendue(tete, cle):  # INV-VAULT-1 : édition ligne à ligne
            del tete[pos[0]:pos[1]]
    return ouverture + "".join(tete) + fermeture + corps


def _bornes_bloc(texte: str) -> tuple[int, int] | None:
    # Dernier `debut` seul sur sa ligne : un marqueur cité dans la prose n'est pas une borne, et
    # après un `debut` orphelin, c'est le bloc ajouté en fin de fichier qu'on retrouve.
    debuts = list(re.finditer(rf"^{re.escape(DEBUT)}\r?$", texte, re.M))
    if not debuts:
        return None
    fin = re.compile(rf"^{re.escape(FIN)}\r?$", re.M).search(texte, debuts[-1].end())
    return (debuts[-1].start(), fin.start() + len(FIN)) if fin else None


def _bornes_geres(texte: str, debut: str, fin_marque: str) -> tuple[int, int] | None:
    """Bornes d'un bloc géré (même règle que le bloc fiche : dernier début seul sur sa ligne)."""
    debuts = list(re.finditer(rf"^{re.escape(debut)}\r?$", texte, re.M))
    if not debuts:
        return None
    fin = re.compile(rf"^{re.escape(fin_marque)}\r?$", re.M).search(texte, debuts[-1].end())
    return (debuts[-1].start(), fin.start() + len(fin_marque)) if fin else None


def bornes_notes(texte: str) -> tuple[int, int] | None:
    return _bornes_geres(texte, NOTES_DEBUT, NOTES_FIN)


def bornes_lignes(texte: str) -> tuple[int, int] | None:
    return _bornes_geres(texte, LIGNES_DEBUT, LIGNES_FIN)


# Une ligne : `- [x] texte · AAAA-MM-JJ · Moi|IA[ · lien]` ; le texte peut contenir « · » (lecture ancrée à droite).
_LIGNE = re.compile(r"^- \[([ xX])\] (.*?) · (\d{4}-\d{2}-\d{2}) · (Moi|IA)(?: · (.+))?$")


def lire_lignes(texte: str) -> list[dict]:
    if not (b := bornes_lignes(texte)):
        return []
    sortie = []
    for brut in texte[b[0]:b[1]].split("\n"):
        if m := _LIGNE.match(brut.rstrip("\r")):
            sortie.append({"fait": m.group(1) != " ", "texte": m.group(2).strip(), "date": m.group(3),
                           "auteur": m.group(4).lower(), "lien": (m.group(5) or "").strip()})
    return sortie


def rendre_lignes(lignes: list[dict], eol: str = "\n") -> str:
    corps = [f"- [{'x' if x['fait'] else ' '}] {_une_ligne(x['texte'])} · {x['date']} · "
             f"{'IA' if x['auteur'] == 'ia' else 'Moi'}" + (f" · {_une_ligne(x['lien'])}" if x.get("lien") else "")
             for x in lignes]
    return eol.join([LIGNES_DEBUT, "## Lignes", *corps, LIGNES_FIN])


def ecrire_lignes(texte: str, lignes: list[dict]) -> str:
    """Remplace le bloc des lignes, ou l'insère avant le bloc fiche (sinon en fin de fichier) ; le reste
    est restitué tel quel (INV-VAULT-1). Liste vide : le bloc disparaît."""
    eol = fin_de_ligne(texte)
    if b := bornes_lignes(texte):
        if not lignes:
            avant, apres = texte[:b[0]], texte[b[1]:]
            apres = apres[2 * len(eol):] if apres.startswith(eol * 2) else apres[len(eol):] if apres.startswith(eol) else apres
            if not apres and avant.endswith(eol * 2):  # le bloc fermait le fichier : sa ligne vide d'appui part avec lui
                avant = avant[:-len(eol)]
            return avant + apres
        return texte[:b[0]] + rendre_lignes(lignes, eol) + texte[b[1]:]
    if not lignes:
        return texte
    bloc = rendre_lignes(lignes, eol)
    if fb := _bornes_bloc(texte):
        return texte[:fb[0]] + bloc + eol + eol + texte[fb[0]:]
    if texte and not texte.endswith("\n"):
        texte += eol
    return texte + eol + bloc + eol


def fiche_vide() -> dict:
    return {"fait": "", "resultat": "", "essai": "", "situation": "", "reste": "",
            "prochain_pas": "", "sous_taches": [], "lignes": []}


def lire_fiche(texte: str) -> dict:
    fiche = fiche_vide()
    fiche["lignes"] = lire_lignes(texte)
    bornes = _bornes_bloc(texte)
    if not bornes:
        return fiche
    libelles = {libelle: cle for cle, libelle in (*CHAMPS, RETENIR)}
    for ligne in texte[bornes[0]:bornes[1]].split("\n"):
        ligne = ligne.rstrip("\r")
        if m := re.match(r"- \*\*(.+?)\*\* : ?(.*)$", ligne):
            if m.group(1) in libelles:
                fiche[libelles[m.group(1)]] = m.group(2).strip()
        elif m := re.match(r"- \[([ xX])\] (.*)$", ligne):
            fiche["sous_taches"].append({"fait": m.group(1) != " ", "texte": m.group(2).strip()})
    return fiche


def _une_ligne(s: str) -> str:
    # Une valeur ne doit jamais pouvoir ouvrir ni fermer un commentaire (bornes du bloc).
    return " ".join(str(s).split()).replace("<!--", "<! --").replace("-->", "-- >")


def rendre_bloc(fiche: dict, eol: str = "\n") -> str:
    lignes = [DEBUT, "## Fiche"]
    lignes += [f"- **{libelle}** : {_une_ligne(fiche.get(cle, ''))}" for cle, libelle in CHAMPS]
    if fiche.get(RETENIR[0]):
        lignes.append(f"- **{RETENIR[1]}** : {_une_ligne(fiche[RETENIR[0]])}")
    if fiche.get("sous_taches"):
        lignes += ["", "### Sous-tâches"]
        lignes += [f"- [{'x' if s['fait'] else ' '}] {_une_ligne(s['texte'])}"
                   for s in fiche["sous_taches"]]
    lignes.append(FIN)
    return eol.join(lignes)


def ecrire_fiche(texte: str, fiche: dict) -> str:
    """Remplace le bloc fiche, ou l'ajoute en fin de fichier s'il n'existe pas."""
    eol = fin_de_ligne(texte)
    bloc = rendre_bloc(fiche, eol)
    if bornes := _bornes_bloc(texte):
        return texte[:bornes[0]] + bloc + texte[bornes[1]:]
    if texte and not texte.endswith("\n"):
        texte += eol
    return texte + eol + bloc + eol


def ajouter_a_section(texte: str, titre: str, ligne: str) -> str:
    """Ajoute une ligne de liste à la fin de la section `## <titre>` du corps (créée avant le
    bloc fiche, ou en fin de fichier) ; rien d'autre n'est touché (INV-VAULT-1)."""
    eol = fin_de_ligne(texte)
    ligne = _une_ligne(ligne)
    tete = re.compile(rf"^## {re.escape(titre)}\r?$", re.M).search(texte)
    if tete:
        pos = texte.find("\n", tete.end())
        pos = len(texte) if pos < 0 else pos + 1
        while (m := re.match(r"- [^\n]*(\n|$)", texte[pos:])) and m.group(0):
            pos += len(m.group(0))
        avant = texte[:pos] if texte[:pos].endswith("\n") else texte[:pos] + eol
        return avant + ligne + eol + texte[pos:]
    bornes = _bornes_bloc(texte)
    pos = bornes[0] if bornes else len(texte)
    avant = texte[:pos].rstrip("\r\n")
    return avant + eol + eol + f"## {titre}" + eol + ligne + eol + (eol if bornes else "") + texte[pos:]


def corps_sans_fiche(texte: str) -> str:
    corps = decouper(texte)[3]
    for bornes_de in (_bornes_bloc, bornes_notes, bornes_lignes):  # les notes s'affichent dans leur panneau
        if bornes := bornes_de(corps):
            corps = corps[:bornes[0]] + corps[bornes[1]:]
    return corps.strip()


def analyser_rendu(texte: str) -> dict | None:
    """Analyse tolérante du dernier bloc `<fiche>` d'un message ; None s'il est absent."""
    blocs = re.findall(r"<fiche>(.*?)</fiche>", texte or "", flags=re.S)
    if not blocs:
        return None
    fiche = fiche_vide()
    for ligne in blocs[-1].splitlines():
        ligne = ligne.strip()
        if m := re.match(r"- \[([ xX])\]\s*(.*)$", ligne):
            fiche["sous_taches"].append({"fait": m.group(1) != " ", "texte": m.group(2).strip()})
        elif m := re.match(r"(fait|resultat|essai|situation|reste|prochain_pas|retenir)\s*:\s*(.*)$", ligne):
            fiche[m.group(1)] = m.group(2).strip()
    return fiche


def sans_rendu(texte: str) -> str:
    """Retire les blocs `<fiche>` et `<decoupage>` d'un message : ils sont lus par le moteur
    et affichés ailleurs (carte Fiche, tickets créés)."""
    return re.sub(r"<(fiche|decoupage)>.*?</\1>", "", texte or "", flags=re.S).strip()


DECLARATIONS = ("en_cours", "en_attente", "terminee")


def declaration(texte: str) -> str:
    """Ligne `statut:` du dernier bloc `<fiche>` ; absente ou invalide = `en_attente`."""
    blocs = re.findall(r"<fiche>(.*?)</fiche>", texte or "", flags=re.S)
    m = re.search(r"^\s*statut\s*:\s*(\S+)", blocs[-1], flags=re.M) if blocs else None
    valeur = m.group(1).casefold().replace("é", "e").replace("-", "_") if m else ""
    return valeur if valeur in DECLARATIONS else "en_attente"
