"""Exécutant d'une tâche : l'humain (« Moi ») ou l'IA, et les notes de travail de l'utilisateur.

Rôle : lire le champ `executant` (absent = `ia`), le poser, refuser tout tour d'agent et toute
écriture d'agent sur une tâche tenue par l'humain ; tenir les notes de l'utilisateur (bloc géré
du corps, ajout et édition) ; amorcer les tours d'IA avec ces notes et l'état de la tâche.
Frontières : pas de HTTP (la garde reçoit méthode, chemin et en-tête) ni de harnais ; écrit par
`Vault.modifier` (clé gérée) et `Vault.reecrire` (bloc des notes seul), jamais autrement.
Invariants portés : INV-EXECUTANT-1, INV-EXECUTANT-2, INV-VAULT-1.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

from . import fiches, langues

HUMAIN, IA = "humain", "ia"
# Seule écriture d'agent admise sur une tâche tenue par l'humain : un lien.
PERMIS_AGENT = ("liens",)
_ROUTE = re.compile(r"^/api/taches/([^/]+)(?:/([^/]+))?(?:/[^/]+)?/?$")
_ENTETE = re.compile(r"^<!-- note (\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?: · modifiée (\d{4}-\d{2}-\d{2} \d{2}:\d{2}))? -->\r?$")
_MARQUEUR = re.compile(r"^(<!-- (?:note |orchestrateur:))", re.M)
PLAFOND = 6000  # caractères de notes transmis intégralement à l'agent ; au-delà, les plus anciennes sont résumées
TOURS = 3  # derniers tours rappelés dans l'amorce


def de(t) -> str:
    """`humain` seulement si posé tel quel ; toute autre valeur (ou l'absence) vaut `ia`."""
    return HUMAIN if str(t.fm.get("executant") or "").strip().lower() == HUMAIN else IA


def humain(t) -> bool:
    return de(t) == HUMAIN


def exiger_ia(t) -> None:
    """INV-EXECUTANT-1 : aucun tour d'agent sur une tâche tenue par l'humain."""
    if humain(t):
        from .vault import Conflit  # importé tard : `vault` -> `arbre` -> `executant`
        raise Conflit(langues.t("serveur.executant.refus"))


def refus_agent(vault, methode: str, chemin: str, agent: str) -> str:
    """Motif du refus d'une écriture d'agent (`orch`, en-tête X-Orch-Tache) ; vide si admise."""
    if methode == "GET" or not agent or not (m := _ROUTE.match(chemin)):
        return ""
    if m.group(2) == "notes":  # INV-EXECUTANT-2 : quel que soit le mode
        return langues.t("serveur.executant.refus_notes")
    if (m.group(2) or "") in PERMIS_AGENT:
        return ""
    try:
        return langues.t("serveur.executant.refus") if humain(vault.tache(m.group(1))) else ""
    except Exception:  # tâche inconnue : la route répondra elle-même 404
        return ""


def poser(moteur, ident: str, valeur: str) -> None:
    """Geste humain du curseur. Vers l'humain : la file d'attente est vidée (rien de neuf ne part) ;
    le tour en cours, lui, se termine."""
    if valeur not in (HUMAIN, IA):
        from .vault import Invalide
        raise Invalide(langues.t("serveur.executant.inconnu", valeur=valeur))
    moteur.vault.modifier(ident, {"executant": valeur})
    if valeur == HUMAIN and moteur.files.get(ident):
        moteur.files[ident].clear()
        moteur._sauver_actifs()  # INV-EXEC-9 : la file vidée ne revient pas au redémarrage
    moteur.publier("arbre")


# --- Notes de l'utilisateur : bloc géré du corps (INV-EXECUTANT-2) ---

def notes(texte: str) -> list[dict]:
    """Notes du bloc géré, dans l'ordre d'écriture : `n` (rang), `quand`, `modifiee`, `texte`."""
    if not (b := fiches.bornes_notes(texte)):
        return []
    out = []
    for ligne in fiches._lignes(texte[b[0]:b[1]])[1:-1]:
        if m := _ENTETE.match(fiches._nu(ligne)):
            out.append({"n": len(out), "quand": m.group(1), "modifiee": m.group(2) or "", "lignes": []})
        elif out:
            out[-1]["lignes"].append(fiches._nu(ligne))
    for x in out:
        x["texte"] = "\n".join(x.pop("lignes")).strip("\n")
    return out


def _texte_net(texte: str) -> str:
    texte = str(texte or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not texte:
        from .vault import Invalide
        raise Invalide(langues.t("serveur.executant.note_vide"))
    return _MARQUEUR.sub(r" \1", texte)  # une ligne de la note n'est jamais prise pour une borne


def _rendre(liste: list[dict], eol: str) -> str:
    lignes = [fiches.NOTES_DEBUT, "## Notes"]
    for x in liste:
        lignes.append(f"<!-- note {x['quand']}" + (f" · modifiée {x['modifiee']}" if x["modifiee"] else "") + " -->")
        lignes += _MARQUEUR.sub(r" \1", x["texte"]).split("\n")  # réécriture : jamais de borne dans le texte
    return eol.join(lignes + [fiches.NOTES_FIN])


def _remplacer(texte: str, liste: list[dict]) -> str:
    """Remplace le bloc des notes, ou le crée avant le bloc fiche (sinon en fin de fichier) ;
    le reste du fichier est restitué octet pour octet (INV-VAULT-1)."""
    eol = fiches.fin_de_ligne(texte)
    bloc = _rendre(liste, eol)
    if b := fiches.bornes_notes(texte):
        return texte[:b[0]] + bloc + texte[b[1]:]
    if b := fiches._bornes_bloc(texte):
        return texte[:b[0]] + bloc + eol + eol + texte[b[0]:]
    if texte and not texte.endswith("\n"):
        texte += eol
    return texte + eol + bloc + eol


def _maintenant() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def ajouter_note(vault, ident: str, texte: str) -> dict:
    texte, note = _texte_net(texte), {}

    def f(contenu: str) -> str:
        liste = notes(contenu)
        note.update(n=len(liste), quand=_maintenant(), modifiee="", texte=texte)
        return _remplacer(contenu, liste + [dict(note)])
    vault.reecrire(ident, f)
    return note


def modifier_note(vault, ident: str, n: int, texte: str) -> dict:
    texte, note = _texte_net(texte), {}

    def f(contenu: str) -> str:
        liste = notes(contenu)
        if not 0 <= n < len(liste):
            from .vault import NonTrouve
            raise NonTrouve(langues.t("serveur.executant.note_absente", n=n))
        liste[n].update(texte=texte, modifiee=_maintenant())
        note.update(liste[n])
        return _remplacer(contenu, liste)
    vault.reecrire(ident, f)
    return note


def vue(vault, ident: str) -> dict:
    """Exécutant et notes d'une tâche, pour sa vue détaillée."""
    t = vault.tache(ident)
    return {"executant": de(t), "notes": notes(fiches.lire(t.chemin))}


# --- Reprise par l'IA : amorce des tours (INV-EXECUTANT-2) ---

def _bloc_notes(liste: list[dict], chemin) -> list[str]:
    rendu = [f"### {x['quand']}" + (f" (modifiée {x['modifiee']})" if x["modifiee"] else "") + f"\n{x['texte']}"
             for x in liste]
    total, garde = 0, len(rendu)
    while garde and total + len(rendu[garde - 1]) <= PLAFOND:  # les plus récentes restent intégrales
        garde -= 1
        total += len(rendu[garde])
    if garde:
        rendu[:garde] = [f"- {x['quand']} — {' '.join(x['texte'].split())[:120]}…" for x in liste[:garde]]
        rendu.insert(0, f"(notes anciennes résumées ; texte intégral dans {chemin}, bloc « Notes »)")
    return rendu


def _derniers_tours(moteur, ident: str) -> list[str]:
    from . import sessions  # importé tard : `sessions` -> `catalogue` -> `vault` -> `executant`
    demandes = []
    for f in sessions._journaux(moteur.config.donnees, ident)[-TOURS - 1:]:
        try:  # deux tours de la même seconde partagent un journal : on lit chaque message soumis
            lignes = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for ligne in lignes:
            try:
                brut = json.loads(ligne) if '"orch_message"' in ligne else {}
            except ValueError:  # ligne tronquée par un arrêt brutal
                continue
            if brut.get("type") == "orch_message":
                demandes.append(f"- {f.parent.name} : {' '.join(str(brut.get('texte') or '').split())[:160] or '(sans message)'}")
    return demandes[-TOURS - 1:-1]  # le dernier est le tour qui part


def amorcer(moteur, ident: str, texte: str, neuve: bool) -> str:
    """Préfixe le tour des notes de l'utilisateur et de l'état de la tâche, quand la session est
    neuve ou que les notes ont changé depuis la dernière injection ; le journal garde le texte humain."""
    t = moteur.vault.tache(ident)
    contenu = fiches.lire(t.chemin)
    if not (liste := notes(contenu)):
        return texte
    vues = moteur.__dict__.setdefault("_notes_injectees", {})
    empreinte = hashlib.sha1(json.dumps(liste, ensure_ascii=False).encode("utf-8")).hexdigest()
    if not neuve and vues.get(ident) == empreinte:
        return texte
    vues[ident] = empreinte
    f = fiches.lire_fiche(contenu)
    etat = [f"- {libelle} : {f[cle]}" for cle, libelle in fiches.CHAMPS if f.get(cle)] or ["- (fiche vide)"]
    blocs = [f"[Notes de travail de l'utilisateur sur « {t.titre} » — {len(liste)} note(s) ; "
             "tu les lis, tu ne les modifies jamais : tu écris dans la conversation et la fiche]",
             "\n\n".join(_bloc_notes(liste, t.chemin)),
             "État de la tâche (fiche) :\n" + "\n".join(etat),
             "Derniers tours :\n" + ("\n".join(_derniers_tours(moteur, ident)) or "- (aucun)"),
             "Avant d'agir : commence ta réponse par un point de situation en 3 lignes tiré de ces "
             "notes (où en est réellement la tâche), puis seulement agis."]
    return "\n\n".join(blocs) + f"\n\n---\n\n{texte}"


def confier(moteur, ident: str, consigne: str) -> str:
    """Geste « Confier la suite » : la tâche passe à l'IA ; l'amorce porte notes et état."""
    poser(moteur, ident, IA)
    moteur.__dict__.get("_notes_injectees", {}).pop(ident, None)  # la reprise revoit toujours les notes
    return moteur.soumettre(ident, consigne.strip() or "Reprends la suite à partir de mes notes.")
