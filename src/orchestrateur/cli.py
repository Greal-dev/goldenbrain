"""Commande `orch` : client HTTP de l'API, à l'usage des agents.

Rôle : arbre, recherche, lecture d'une tâche, message à une tâche, délégation à une tâche enfant
(INV-ECO-1 : la délégation passe par GoldenBrain, qui choisit le fournisseur), propositions de structure,
sollicitation d'un persona de l'équipe, feu vert lié à une version, création d'une tâche (description
exigée ; `--lancer`, `--envoi` pour l'agent de tri Telegram), `rattacher` et `telegram` (envois
Telegram), arrêt et relance d'une tâche (chat de projet, INV-PILOTAGE-1) ; `console` délègue à
`console.py` ; `m365` délègue à `m365.py` (INV-M365-1) ; `telegram-jeton` à `telegram_jeton.py` (saisie sans écho, INV-TELEGRAM-2) ; `natif <fichier>`, relais de l'interface native lancé dans l'onglet du terminal
(INV-NATIF-1) ; `executeur` délègue à `executeur.py` (INV-DISTANT-1), `executeur installer` à `installation.py` (INV-INSTALL-1) ; `jeton-executeur` crée
ou révoque le jeton d'un exécuteur, depuis le poste du chef.
Frontières : stdlib seule (hors `console`, `m365`, `executeur`, `installation`, importés tard) ; n'importe ni le moteur ni le vault ; sortie texte, code de retour
non nul en cas d'erreur.
Invariants portés : INV-MSG-1 (transmet `ORCH_SAUTS` + 1), INV-EXEC-5 (ne fait que proposer), `reflexes` et `tracer` : `cli_reflexes.py`,
INV-EQUIPE-1 (un tour de persona, marqué `ORCH_PERSONA`, ne sollicite pas l'équipe),
INV-FEU-1 (`feu-vert verifier` rend 0 seulement pour un feu vert accordé à ce sha exact ; serveur
injoignable = non nul).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import cli_chaines, cli_lignes, cli_reflexes


class ErreurCli(Exception):
    pass


def natif(fichier: str) -> int:
    """INV-NATIF-1 : écrit son PID (que GoldenBrain surveille) puis exécute le harnais au premier
    plan de l'onglet ; sa fin, onglet fermé compris, est la fermeture de l'interface native."""
    spec = json.loads(open(fichier, encoding="utf-8").read())
    with open(os.path.splitext(fichier)[0] + ".pid", "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    env = {**os.environ, **spec.get("env", {})}
    if spec.get("argv"):
        return subprocess.run(spec["argv"], cwd=spec.get("dossier"), env=env).returncode
    return subprocess.run(spec["commande"], cwd=spec.get("dossier"), env=env,
                          shell=True).returncode


def appeler(methode: str, chemin: str, corps: dict | None = None):
    base = os.environ.get("ORCH_URL", "http://127.0.0.1:8300").rstrip("/")
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(base + "/api" + chemin, data=donnees, method=methode, headers={
        "Content-Type": "application/json", "X-Orchestrateur": "1",
        **({"X-Orch-Tache": os.environ["ORCH_TACHE"]} if os.environ.get("ORCH_TACHE") else {}),
        # INV-DISTANT-1 : sur un exécuteur, chaque appel porte son jeton.
        **({"X-Orch-Jeton": os.environ["ORCH_JETON"]} if os.environ.get("ORCH_JETON") else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        corps = {}
        try:
            corps = json.loads(e.read().decode("utf-8"))
            detail = corps.get("detail")
        except ValueError:
            detail = e.reason
        raise ErreurCli(f"erreur {e.code} : {detail}" + rendre_proches(corps)) from None
    except urllib.error.URLError as e:
        raise ErreurCli(f"orchestrateur injoignable ({base}) : {e.reason}") from None


def _q(ident: str) -> str:
    return urllib.parse.quote(ident, safe="")


def _echeance(n: dict) -> str:
    if not n.get("echeance"):
        return ""
    return f" — échéance {n['echeance']}" + (" (en retard)" if n.get("retard") else "")


def rendre_proches(corps) -> str:
    """INV-RAPPROCHEMENT-1 : liste des tâches proches d'un refus 409, et le geste à faire."""
    cands = corps.get("candidates") if isinstance(corps, dict) else None
    if not cands:
        return cli_lignes.rendre_rangement(corps)  # INV-PLAFOND-1 : parent plein ou nature mélangée
    lignes = [f"\n- {c['id']} [{c.get('statut') or '?'}] {c['titre']} ({' > '.join(c['fil_ariane'])})"
              f" — proximité {c['score']}" + (" — FORTE" if c["forte"] else "") for c in cands]
    return ("".join(lignes) + "\nComplète la tâche trouvée : orch dire <id> \"<ton complément>\", ou, si c'est un travail court, "
            "orch ligne <id> \"<ce qui est fait>\" ; ne crée une nouvelle tâche (--nouvelle) que si c'est vraiment un autre sujet.")


def rendre_arbre(noeuds: list[dict], niveau: int = 0) -> list[str]:
    lignes = []
    for n in noeuds:
        if n["type"] == "tache":
            etat = n.get("etat_execution")
            suffixe = f" ({etat})" if etat and etat != "inactif" else ""
            lignes.append(f"{'  ' * niveau}- {n['id']} [{n.get('statut') or '?'}] {n['titre']}{suffixe}"
                          f"{_echeance(n)}")
        else:
            lignes.append(f"{'  ' * niveau}{n['titre']} ({n['type']}, {n['ouvertes']} ouvertes)")
        lignes += rendre_arbre(n["enfants"], niveau + 1)
    return lignes


def rendre_tache(t: dict) -> list[str]:
    f = t["fiche"]
    lignes = [f"# {t['titre']}", f"id : {t['id']}", f"chemin : {t['chemin']}",
              f"place : {' > '.join(t['fil_ariane'])}", f"statut : {t['statut']}",
              f"exécution : {t['etat_execution']}",
              "exécutant : " + ("Moi (l'utilisateur ; aucun agent n'y écrit)" if t.get("executant") == "humain" else "IA"),
              f"parent : {t['parent'] or '-'}",
              f"enfants : {', '.join(t['enfants']) or '-'}", "", "## Fiche",
              f"fait : {f['fait']}", f"situation : {f['situation']}", f"reste : {f['reste']}",
              f"prochain pas : {f['prochain_pas']}"]
    lignes += [f"- [{'x' if s['fait'] else ' '}] {s['texte']}" for s in f["sous_taches"]]
    if t.get("notes"):  # INV-EXECUTANT-2 : lisibles par l'agent, jamais modifiables
        lignes += ["", "## Notes de l'utilisateur (lecture seule)"]
        lignes += [f"### {n['quand']}\n{n['texte']}" for n in t["notes"]]
    return lignes


def rendre_recherche(resultats: list[dict]) -> list[str]:
    lignes = []
    for r in resultats:
        lignes.append(f"- {r['id']} [{r.get('statut') or '?'}] {r['titre']} "
                      f"({' > '.join(r['fil_ariane'])}){_echeance(r)}")
        if r.get("extrait"):
            lignes.append(f"    {r['extrait']}")
    return lignes


PAS_POSTE_S = 2.0  # redemande : garde la place dans la file (elle expire en 15 s sans demande)


def _attendre_poste(source: str, motif: str, attente_min: float) -> list[str]:
    """INV-POSTE-1 : demande le poste et attend son tour (file, premier arrivé) jusqu'à
    `attente_min` minutes ; passé ce délai (0 : aussitôt), quitte la file et échoue (code 1)."""
    limite = time.monotonic() + attente_min * 60
    dernier = None
    while True:
        r = appeler("POST", "/poste/reserver", {"tache": source, "motif": motif, "attendre": True})
        if r["poste"]:
            return ["poste réservé ; rendu d'office à la fin de ton tour (ou `orch poste liberer`) ; "
                    "expire à défaut dans le délai réglé"]
        if time.monotonic() >= limite:
            appeler("POST", "/poste/annuler", {"tache": source})
            raise ErreurCli(f"poste toujours pris après {attente_min:g} min (rang {r['rang']}) ; "
                            "réessaie plus tard ou allonge `--attente`")
        if r["rang"] != dernier:
            dernier = r["rang"]
            qui = (r.get("titulaire") or {}).get("tache")
            print(f"en attente du poste (rang {dernier})" + (f", tenu par {qui}" if qui else ""),
                  file=sys.stderr, flush=True)
        time.sleep(PAS_POSTE_S)


def _poste(action: str, motif: str, source: str, attente_min: float = 30) -> list[str]:
    """INV-POSTE-1 : le titulaire est la tâche courante (`ORCH_TACHE`)."""
    if action == "etat":
        d = appeler("GET", "/poste")
        r = d["poste"]
        ligne = (f"poste réservé par {r['tache']} depuis {r['depuis'][11:16]}"
                 + (f" : {r['motif']}" if r["motif"] else "")) if r else "poste libre"
        return [ligne] + [f"  file {i}. {e['tache']}" for i, e in enumerate(d.get("file") or [], 1)]
    if not source:
        raise ErreurCli("ORCH_TACHE absent : le poste se réserve depuis une tâche")
    if action == "reserver":
        return _attendre_poste(source, motif, attente_min)
    rendu = appeler("POST", "/poste/liberer", {"tache": source})["libere"]
    return ["poste rendu" if rendu else "rien à rendre (poste libre)"]


def feu_vert(a, source: str, sauts: int) -> tuple[list[str], int]:
    if a.geste == "verifier":
        try:
            f = appeler("GET", f"/feux-verts/{_q(a.sha)}")
        except ErreurCli as e:  # INV-FEU-1 : sans réponse, pas de feu vert
            return [f"pas de feu vert pour {a.sha} : {e}"], 1
        if f.get("etat") == "accorde" and f.get("sha") == a.sha.strip().lower():
            return [f"feu vert accordé pour {f['sha']} par {f['auteur']} le {f['verdict_le']} : "
                    f"{f['motif']}"], 0
        return [f"pas de feu vert pour {a.sha} (état : {f.get('etat')})"], 1
    if a.geste == "demander":
        f = appeler("POST", "/feux-verts", {"sha": a.sha, "objet": a.texte, "a": a.a,
                                            "de": source, "sauts": sauts})
        return [f"feu vert demandé à {f['controleur']} pour {f['sha']} ; son verdict te "
                f"reviendra en message"], 0
    f = appeler("POST", f"/feux-verts/{_q(a.sha)}/verdict", {"geste": a.geste, "motif": a.texte,
                                                             "de": source, "sauts": sauts})
    return [f"{'feu vert accordé' if f['etat'] == 'accorde' else 'feu vert refusé'} pour "
            f"{f['sha']} ; consigné sur la tâche {f['demandeur']}"], 0


def deleguer(titre: str, brief: str, source: str, sauts: int, forcer: bool = False) -> list[str]:
    """Sous-agent par GoldenBrain : tâche enfant de l'appelante, qui l'alimente, lancée avec un brief
    explicite (un autre fournisseur ne partage pas le contexte de l'appelant) ; son résultat revient à
    l'appelante par la propagation des liens (INV-LIEN-1), plafonnée par les sauts (INV-MSG-1)."""
    if not source:
        raise ErreurCli("ORCH_TACHE absent : deleguer s'emploie depuis une tâche")
    if not brief.strip():
        raise ErreurCli("deleguer attend un brief : objectif, contexte utile, livrable attendu")
    t = appeler("POST", "/taches", {"titre": titre, "description": brief, "parent": source,
                                  **({"forcer": True} if forcer else {})})
    appeler("POST", f"/taches/{_q(t['id'])}/liens", {"type": "alimente", "cible": source})
    texte = (f"{brief}\n\n[Travail délégué par la tâche {source} (`orch lire {source}` donne sa fiche). "
             f"Ta fiche finale lui revient d'office : rends un livrable autonome.]")
    r = appeler("POST", f"/taches/{_q(t['id'])}/messages", {"texte": texte, "de": source, "sauts": sauts})
    return [f"tâche {t['id']} créée sous {source} et lancée (état : {r['etat_execution']}) ; "
            f"son résultat te reviendra en message"]


def _m365(a) -> int:
    """Appel direct à Microsoft 365, sans le serveur GoldenBrain (INV-M365-1, INV-M365-3)."""
    from . import m365  # import tardif : la commande ne charge le connecteur que si on l'emploie
    try:
        conf = m365.charger()
        if a.action == "connecter":
            m365.connecter(conf)
            return 0
        sortie = (m365.rendre_reponse(m365.demander(conf, a.question)) if a.action == "demander"
                  else m365.rendre_contexte(m365.contexte(conf, a.question, a.source, a.nombre)))
    except (m365.ErreurM365, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print("\n".join(sortie))
    return 0


def _agents_cc(r: dict) -> list[str]:
    """Un groupe par ligne : nom, état, nombre de sessions, rattachement proposé."""
    if not r["actif"]:
        return ["relevé débrayé : réglez [agents_cc] dossier dans config.toml"]
    sortie = [f"{len(r['groupes'])} agent(s) regroupé(s) — dernier relevé {r['derniere'] or 'jamais'}"]
    for g in r["groupes"]:
        cible = (f" -> {g['tache']}" if g["tache"] else "") + (" (ignoré)" if g["ignore"] else "")
        sortie.append(f"{g['nom']} [{g['etat']}] {len(g['historique']) + 1} session(s) : {g['action']}{cible}"
                      f" — {g['motif']}")
    return sortie


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="orch", description="Pilotage des tâches de l'orchestrateur.")
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("guide", help="guide d'utilisation (docs/GUIDE.md) : à lire d'abord")  # INV-GUIDE-1
    sous.add_parser("arbre", help="arbre des tâches ouvertes")
    ac = sous.add_parser("agents-cc", help="agents de Claude Code regroupés et rattachement proposé (lecture seule)")
    ac.add_argument("--relever", action="store_true", help="relire le dossier de Claude Code maintenant")
    sous.add_parser("natif", help="relais de l'interface native (lancé par GoldenBrain)").add_argument("fichier")
    sous.add_parser("lire", help="fiche et chemin d'une tâche").add_argument("id")
    d = sous.add_parser("dire", help="message à une autre tâche")
    d.add_argument("id")
    d.add_argument("message")
    sous.add_parser("chercher", help="tâches dont le titre, la fiche ou la place contiennent tous les mots").add_argument("mots")
    for m in (cli_reflexes, cli_chaines, cli_lignes): m.ajouter(sous)  # reflexes, tracer, chaine, ligne : INV-REFLEXES-1, INV-TRACE-1, INV-CHAINE-3
    de = sous.add_parser("deleguer", help="confier un travail à une tâche enfant, lancée par GoldenBrain")
    de.add_argument("titre")
    de.add_argument("brief", help="objectif, contexte utile, livrable attendu")
    de.add_argument("--nouvelle", dest="forcer", action="store_true", help="créer malgré une tâche proche (sinon : orch dire)")
    cr = sous.add_parser("creer", help="créer une tâche (description d'au moins une phrase exigée)")
    cr.add_argument("titre")
    cr.add_argument("--description", default="", help="de quoi il s'agit, au moins une phrase")
    cr.add_argument("--conteneur", default=None, help="projet ; défaut : celui de la tâche courante")
    cr.add_argument("--parent", default=None, help="tâche parente")
    cr.add_argument("--envoi", type=int, default=0, help="n° de l'envoi Telegram rangé par cette tâche")
    cr.add_argument("--nouvelle", dest="forcer", action="store_true", help="créer malgré une tâche proche (sinon : orch dire)")
    cr.add_argument("--lancer", action="store_true", help="lancer la tâche aussitôt (premier tour)")
    cr.add_argument("--mission", default="", help="consigne du premier tour (avec --lancer)")
    ra0 = sous.add_parser("rapprochement", help="tâches proches d'un titre ; sans titre : créations évitées")
    ra0.add_argument("titre", nargs="?", default="")
    so = sous.add_parser("solliciter", help="avis d'un persona de l'équipe sur la tâche courante")
    so.add_argument("persona")
    so.add_argument("question")
    sous.add_parser("conteneurs", help="identifiants et titres des conteneurs (projets)")
    sous.add_parser("reevaluer", help="rejouer la validation automatique sur les tâches faites, sans rien clore")
    sous.add_parser("arreter", help="arrêter le tour d'une tâche").add_argument("id")
    sous.add_parser("relancer", help="reprendre le tour interrompu d'une tâche").add_argument("id")
    ra = sous.add_parser("rattacher", help="rattacher un envoi Telegram à une tâche existante")
    ra.add_argument("envoi", type=int)
    ra.add_argument("id")
    te = sous.add_parser("telegram", help="poser une question sur Telegram ; la réponse revient à la tâche courante")
    te.add_argument("texte")
    te.add_argument("--validation", action="store_true", help="compte rendu à valider : boutons Valider / Renvoyer")
    te.add_argument("--tache", default="", help="tâche touchée : ajoute sa ligne (titre, place, lien)")
    te.add_argument("--choix", action="append", default=[], help="tâche candidate (2 ou 3 fois) : boutons de choix au lieu de deviner")
    te.add_argument("--geste", default="", help="statut=<s> | echeance=AAAA-MM-JJ | priorite=<p> sur "
                                                "--tache, appliqué si l'utilisateur confirme")
    tj = sous.add_parser("telegram-jeton", help="saisir le jeton du bot Telegram sans l'afficher (coffre du poste)")
    tj.add_argument("--pause", action="store_true", help="attendre Entrée avant de fermer (fenêtre ouverte par Réglages)")
    tj.add_argument("--config", help="config.toml à utiliser (transmis par l'interface)")
    po = sous.add_parser("poste", help="réserver / rendre le poste pendant une porte lourde")
    po.add_argument("action", choices=["reserver", "liberer", "etat"])
    po.add_argument("motif", nargs="?", default="", help="pourquoi (reserver)")
    po.add_argument("--attente", type=float, metavar="MIN", help="reserver : minutes d'attente "
                    "maximale dans la file si le poste est pris (défaut 30, ORCH_POSTE_ATTENTE_MIN ; "
                    "0 = ne pas attendre)")
    rn = sous.add_parser("renommer", help="changer le titre d'une tâche (identifiant et fichier inchangés)")
    rn.add_argument("id"), rn.add_argument("titre")
    pr = sous.add_parser("proposer", help="proposer un changement de structure")
    pr.add_argument("type", choices=["deplacer", "ticket", "projet", "lier", "operation", "tache",
                                     "perimetre", "echeance", "fermer", "renommer"])
    pr.add_argument("id")
    pr.add_argument("valeur", nargs="+", help="conteneur, titre, nom, texte ; pour lier : "
                                              "<alimente|prerequis|voir_aussi> <cible> (prerequis : <cible> "
                                              "doit être terminée avant que <id> démarre) ; pour echeance : AAAA-MM-JJ ; pour fermer : cloture ou abandonne ; pour renommer : le titre explicite proposé")
    pr.add_argument("--motif", default="", help="pourquoi, en une ligne")
    fv = sous.add_parser("feu-vert", help="feu vert du contrôleur lié à une version (sha)")
    fv.add_argument("geste", choices=["demander", "accorder", "refuser", "verifier"])
    fv.add_argument("sha", help="sha complet : git rev-parse HEAD")
    fv.add_argument("texte", nargs="?", default="", help="objet (demander) ou motif (verdict)")
    fv.add_argument("--a", default="", help="demander : tâche du contrôleur")
    fi = sous.add_parser("fiche", help="exécution regroupée : fiche et statut proposé d'une sous-tâche")
    fi.add_argument("id")
    fi.add_argument("--statut", default="", choices=["", "en_cours", "en_attente", "terminee"])
    for champ in ("fait", "resultat", "essai", "situation", "reste", "prochain-pas"):
        fi.add_argument(f"--{champ}", default="")
    co = sous.add_parser("console", help="suivre une tâche et lui écrire depuis le terminal")
    co.add_argument("id")
    co.add_argument("--url", default=None, help="adresse de GoldenBrain (sinon ORCH_URL)")
    ms = sous.add_parser("m365", help="connaissance d'entreprise Microsoft 365 Copilot (lecture seule)")
    ms.add_argument("action", choices=["connecter", "demander", "contexte"])
    ms.add_argument("question", nargs="?", default="")
    ms.add_argument("--source", default="", help="contexte : sharePoint, oneDriveBusiness, externalItem")
    ms.add_argument("--nombre", type=int, default=10, help="contexte : extraits au plus (1-25)")
    ex = sous.add_parser("executeur", help="faire de ce PC un exécuteur d'un GoldenBrain chef")
    ex.add_argument("action", nargs="?", choices=["installer"], default="", help="installer : assistant d'installation des prérequis, étape par étape, avec accord")
    ex.add_argument("--harnais", default="claude", help="installer : harnais à installer, séparés par des virgules (claude, codex, copilot, opencode, agy)")
    ex.add_argument("--verifier", action="store_true", help="installer : seulement l'état de ce PC, rien n'est lancé")
    ex.add_argument("--serveur", default="", help="adresse du chef, ex. http://100.64.0.1:8300 (omise : celle de l'appairage)")
    ex.add_argument("--code", default="", help="code d'appairage affiché par le chef (Réglages → PC connectés)")
    ex.add_argument("--jeton", default=None, help="jeton de l'exécuteur (sinon ORCH_JETON_EXECUTEUR)")
    ex.add_argument("--depots", default=None, help="dossier des clones (défaut ~/goldenbrain-depots)")
    ex.add_argument("--places", type=int, default=1, help="tours simultanés acceptés")
    je = sous.add_parser("jeton-executeur", help="créer (ou révoquer) le jeton d'un exécuteur")
    je.add_argument("nom")
    je.add_argument("--revoquer", action="store_true")
    a = p.parse_args(argv)
    if a.commande == "feu-vert" and a.geste != "verifier" and not a.texte.strip():
        fv.error(f"{a.geste} attend un texte (objet ou motif)")
    if a.commande == "feu-vert" and a.geste == "demander" and not a.a:
        fv.error("demander attend --a <tâche du contrôleur>")
    if a.commande == "natif":
        return natif(a.fichier)
    if a.commande == "guide":  # lu sur place : utile serveur arrêté ou sur un exécuteur distant
        from pathlib import Path
        print((Path(__file__).resolve().parents[2] / "docs" / "GUIDE.md").read_text(encoding="utf-8"))
        return 0
    if a.commande == "creer" and a.mission and not a.lancer:
        cr.error("--mission attend --lancer")
    if a.commande == "proposer":
        attendus = 2 if a.type == "lier" else 1
        if len(a.valeur) != attendus:
            pr.error(f"{a.type} attend {attendus} valeur(s) après l'identifiant")
        a.valeur = ":".join(a.valeur)  # lier : « alimente:<cible> »
    for flux in (sys.stdout, sys.stderr):  # console Windows : un titre exotique ne doit pas planter
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(errors="replace")
    if a.commande == "console":
        from . import console  # console importe cli : import tardif
        return console.main(a.id, a.url)
    if a.commande == "m365":
        return _m365(a)
    if a.commande == "telegram-jeton":  # local au poste : ni serveur, ni agent, ni conversation
        from . import config, telegram_jeton
        return telegram_jeton.saisir(config.charger(a.config), pause=input if a.pause else None)
    if a.commande == "executeur" and a.action == "installer":
        from . import installation
        return installation.principal(a.serveur, a.harnais, a.verifier)
    if a.commande == "executeur":
        from . import executeur  # harnais importés tard : la commande des agents reste légère
        return executeur.main(a.serveur, a.jeton or os.environ.get("ORCH_JETON_EXECUTEUR", ""),
                              a.depots, a.places, a.code)
    source = os.environ.get("ORCH_TACHE", "")
    try:
        sauts = int(os.environ.get("ORCH_SAUTS") or 0) + 1
    except ValueError:
        sauts = 1
    try:
        if m := next((m for m in (cli_reflexes, cli_chaines, cli_lignes) if a.commande in m.COMMANDES), None):
            sortie = m.executer(a, appeler, _q, source)
        elif a.commande == "arbre":
            sortie = rendre_arbre(appeler("GET", "/arbre")["noeuds"]) or ["(aucune tâche ouverte)"]
        elif a.commande == "lire":
            sortie = rendre_tache(appeler("GET", f"/taches/{_q(a.id)}"))
        elif a.commande == "dire":
            r = appeler("POST", f"/taches/{_q(a.id)}/messages",
                        {"texte": a.message, "de": source or None, "sauts": sauts})
            sortie = [f"message transmis à {a.id} (état : {r['etat_execution']})"]
        elif a.commande == "creer":
            corps = {"titre": a.titre, "description": a.description, "de": source or "orch"}
            if a.conteneur:
                corps["conteneur"] = a.conteneur
            if a.parent:
                corps["parent"] = a.parent
            if a.forcer:
                corps["forcer"] = True
            if a.lancer:
                corps.update({"lancer": True, "mission": a.mission})
            r = appeler("POST", "/taches", corps)  # 400 lisible sans description (INV-DECISIONS-1)
            sortie = [f"tâche créée{' et lancée' if a.lancer else ''} : {r['id']} — {r['titre']}"]
            if a.envoi:
                try:  # la tâche existe déjà : un échec de Telegram ne doit pas pousser à la recréer
                    tg = appeler("POST", f"/telegram/envois/{a.envoi}/issue", {"tache": r["id"], "cree": True})
                    sortie.append(f"Telegram : {tg['texte']}")
                except ErreurCli as e:
                    sortie.append(f"Telegram non prévenu ({e}) ; réessayer : orch rattacher {a.envoi} {r['id']}")
        elif a.commande == "renommer":  # INV-RENOMMER-1 : le titre seul change
            sortie = [f"{a.id} renommée : {appeler('POST', f'/taches/{_q(a.id)}/renommer', {'titre': a.titre})['titre']}"]
        elif a.commande == "rapprochement":
            if a.titre:
                q = urllib.parse.urlencode({"titre": a.titre})
                sortie = rendre_proches({"candidates": appeler("GET", f"/rapprochement/proches?{q}")["candidates"]}
                                        ).lstrip("\n").split("\n") or []
                sortie = sortie if sortie != [""] else ["(aucune tâche proche)"]
            else:
                m = appeler("GET", "/rapprochement/mesure")
                sortie = [f"créations évitées : {m['evitees']} (refus non forcés {m['refus_non_forces']}, "
                          f"compléments {m['complements']}) ; forcées après refus : {m['forces_apres_refus']}"]
        elif a.commande == "chercher":
            q = urllib.parse.urlencode({"q": a.mots})
            sortie = rendre_recherche(appeler("GET", f"/recherche?{q}")) or ["(aucune tâche)"]
        elif a.commande == "conteneurs":
            sortie = [f"- {c['id']} : {c['titre']}" for c in appeler("GET", "/conteneurs")] or ["(aucun)"]
        elif a.commande == "reevaluer":
            r = appeler("POST", "/validation-auto/reevaluer")
            sortie = [f"{i} [{n['issue']}] {n['motif']}" for i, n in r["taches"].items()] or ["(aucune tâche faite en validation automatique)"]
        elif a.commande in ("arreter", "relancer"):
            r = appeler("POST", f"/taches/{_q(a.id)}/{'arret' if a.commande == 'arreter' else 'relancer'}")
            sortie = [f"{a.id} : {r['etat_execution']}"]
        elif a.commande == "deleguer":
            sortie = deleguer(a.titre, a.brief, source, sauts, a.forcer)
        elif a.commande == "fiche":  # INV-REGROUPE-2 : écrite par la conversation de la mère
            if not source:
                raise ErreurCli("ORCH_TACHE absent : fiche s'emploie depuis la conversation de la mère")
            r = appeler("POST", f"/taches/{_q(a.id)}/fiche-regroupee",
                        {"de": source, "statut": a.statut, "fait": a.fait, "resultat": a.resultat,
                         "essai": a.essai, "situation": a.situation, "reste": a.reste,
                         "prochain_pas": a.prochain_pas})
            sortie = [f"fiche de {a.id} mise à jour (statut : {r['statut']})"]
        elif a.commande == "agents-cc":
            sortie = _agents_cc(appeler("GET", "/agents-cc" + ("?relever=true" if a.relever else "")))
        elif a.commande == "rattacher":
            r = appeler("POST", f"/telegram/envois/{a.envoi}/issue", {"tache": a.id, "cree": False})
            sortie = [f"Telegram : {r['texte']}"]
        elif a.commande == "telegram":
            if not source:
                raise ErreurCli("ORCH_TACHE absent : telegram s'emploie depuis une tâche")
            corps = {"tache": source, "texte": a.texte, "boutons": a.validation}
            corps.update({k: v for k, v in (("vise", a.tache), ("choix", a.choix), ("geste", a.geste)) if v})
            appeler("POST", "/telegram/question", corps)
            sortie = ["compte rendu envoyé sur Telegram (Valider / Renvoyer)"] if a.validation else \
                ["choix proposé sur Telegram ; la tâche retenue te reviendra en message"] if a.choix else \
                ["geste proposé sur Telegram ; la confirmation te reviendra en message"] if a.geste else \
                ["message envoyé sur Telegram ; la réponse te reviendra en message"]
        elif a.commande == "poste":
            att = a.attente if a.attente is not None else float(os.environ.get("ORCH_POSTE_ATTENTE_MIN") or 30)
            sortie = _poste(a.action, a.motif, source, att)
        elif a.commande == "solliciter":
            if os.environ.get("ORCH_PERSONA"):
                raise ErreurCli("un persona ne sollicite pas l'équipe (une revue ne déclenche "
                                "pas de revue)")
            if not source:
                raise ErreurCli("ORCH_TACHE absent : solliciter s'emploie depuis une tâche")
            appeler("POST", f"/taches/{_q(source)}/solliciter",
                    {"persona": a.persona, "question": a.question})
            sortie = [f"{a.persona} sollicité ; son avis te reviendra en message"]
        elif a.commande == "jeton-executeur":
            if a.revoquer:
                appeler("DELETE", f"/executeurs/jetons/{_q(a.nom)}")
                sortie = [f"jeton de {a.nom} révoqué"]
            else:
                r = appeler("POST", "/executeurs/jetons", {"nom": a.nom})
                sortie = [f"jeton de {a.nom} (montré une seule fois) :", r["jeton"]]
        elif a.commande == "feu-vert":
            sortie, code = feu_vert(a, source, sauts)
            print("\n".join(sortie), file=sys.stdout if code == 0 else sys.stderr)
            return code
        else:
            r = appeler("POST", "/propositions", {"type": a.type, "tache": a.id,
                                                  "valeur": a.valeur, "de": source,
                                                  "motif": a.motif})
            if r.get("etat") == "ignoree":  # INV-INTERFACE-3 : mode simple, rien n'est mémorisé (installation à blanc, 19/11)
                sortie = ["proposition ignorée : l'interface ne retient pas les propositions "
                          "(mode simple ; Réglages > Propositions)"]
            else:
                suite = "en attente de décision humaine" if r.get("etat", "en_attente") == "en_attente" else r["etat"]
                sortie = [f"proposition n°{r['n']} enregistrée ({r['type']} {r['tache']} -> "
                          f"{r['valeur']}) ; {suite}"]
    except ErreurCli as e:
        print(str(e), file=sys.stderr)
        return 1
    print("\n".join(sortie))
    return 0


if __name__ == "__main__":
    sys.exit(main())
