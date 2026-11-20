"""Console GoldenBrain en terminal : `orch console <id>`, et l'ouverture de son onglet.

Rôle : afficher l'échange d'une tâche, le suivre en direct (flux SSE, étapes comprises), envoyer
chaque ligne saisie par la route du chat ; ouvrir la console dans un onglet de Windows Terminal.
Rendu : l'échange (Vous / Agent / GoldenBrain) en texte normal ; les étapes (outils, textes
intermédiaires) en gris atténué, indentées, tronquées, masquables par /etapes comme dans le chat.
Couleurs par séquences ANSI, repli en texte brut si le terminal ne les gère pas.
Frontières : stdlib seule ; client de l'API (`cli.appeler`), n'importe ni moteur ni vault.
Invariants portés : INV-CONSOLE-1 (un seul chemin d'envoi, la vue ne possède pas le tour).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable

from . import cli

AIDE = ("Entrée envoie la ligne à l'agent (comme le chat) ; /etapes affiche ou masque les étapes ; "
        "/arret arrête le tour ; /quitter ferme cette vue : le tour continue, suivi par GoldenBrain.")
OUTIL = "⚙"
LIGNES_ETAPE = 4      # une étape au-delà est tronquée : c'est un journal, pas l'échange
LARGEUR_ETAPE = 160
LARGEUR_TITRE = 40


class Rendu:
    """Mise en forme des lignes ; `couleurs` faux = texte brut (terminal sans ANSI, tests)."""

    def __init__(self, couleurs: bool = False, etapes: bool = False):
        self.couleurs = couleurs
        self.etapes = etapes  # même défaut que le chat : étapes masquées

    def _sgr(self, code: str, texte: str) -> str:
        return f"\x1b[{code}m{texte}\x1b[0m" if self.couleurs else texte

    def entete(self, qui: str, heure: str = "") -> str:
        return self._sgr("1", f"── {qui}{' · ' + heure if heure else ''}")

    def attenue(self, texte: str) -> str:
        return self._sgr("2;37", texte)

    def etape(self, texte: str) -> list[str]:
        """Une étape : grise, indentée, préfixée du symbole d'outil, tronquée."""
        lignes = [x[:LARGEUR_ETAPE] + ("…" if len(x) > LARGEUR_ETAPE else "")
                  for x in (texte or "").strip().splitlines() if x.strip()] or [""]
        reste = len(lignes) - LIGNES_ETAPE
        if reste > 0:
            lignes = lignes[:LIGNES_ETAPE] + [f"… ({reste} ligne{'s' if reste > 1 else ''} de plus)"]
        return [self.attenue(f"   {OUTIL} {lignes[0]}")] + [self.attenue(f"     {x}") for x in lignes[1:]]


def titre_onglet(titre: str) -> str:
    """Titre de la tâche, sans caractère de contrôle ni « ; » (que `wt` prend pour un séparateur),
    tronqué à un mot entier."""
    t = " ".join("".join(c if c.isprintable() else " " for c in titre).replace(";", ",").split())
    if len(t) <= LARGEUR_TITRE:
        return t
    coupe = t[:LARGEUR_TITRE - 1].rsplit(" ", 1)[0] or t[:LARGEUR_TITRE - 1]
    return coupe.rstrip(" ,.:-") + "…"


def _qui(m: dict) -> str:
    if m["role"] == "utilisateur":
        # Même règle que l'interface : un message entre crochets vient de GoldenBrain.
        return "GoldenBrain" if m["texte"].lstrip().startswith("[") else "Vous"
    return {"assistant": "Agent", "systeme": "GoldenBrain"}.get(m["role"], m["role"])


def rendre_historique(msgs: list[dict], r: Rendu) -> list[str]:
    """Même découpage que le chat : un tour = les messages de l'agent entre deux messages d'une autre
    source ; sa réponse = son dernier message non secondaire qui porte du texte ; le reste = étapes."""
    sortie: list[str] = []
    tour: list[dict] = []

    def vider() -> None:
        if not tour:
            return
        avec_texte = [m for m in tour if (m.get("texte") or "").strip()]
        final = next((m for m in reversed(avec_texte) if not m.get("secondaire")),
                     avec_texte[-1] if avec_texte else None)
        etapes = [x for m in tour
                  for x in ([m["texte"]] if m is not final and (m.get("texte") or "").strip() else [])
                  + list(m.get("outils") or [])]
        if n := len(etapes):
            sortie.extend([y for x in etapes for y in r.etape(x)] if r.etapes else [r.attenue(
                f"   ({n} étape{'s' if n > 1 else ''} masquée{'s' if n > 1 else ''} — /etapes)")])
        if final:
            sortie.append(r.entete("Agent", (final.get("horodatage") or "")[11:16]))
            sortie.append(final["texte"].strip())
        tour.clear()

    for m in msgs:
        if m["role"] == "assistant":
            tour.append(m)
            continue
        vider()
        sortie.append(r.entete(_qui(m), (m.get("horodatage") or "")[11:16]))
        if m["texte"]:
            sortie.append(m["texte"].strip())
    vider()
    return sortie


class Direct:
    """Rendu du flux en direct : un texte de l'agent reste en attente ; le suivant en fait une étape,
    la fin du tour en fait la réponse (même règle que l'historique : la réponse est le dernier texte)."""

    def __init__(self, r: Rendu):
        self.r = r
        self.attente = ""

    def evenement(self, evt: dict) -> list[str]:
        t, r = evt["type"], self.r
        if t == "tour_debut":
            self.attente = ""
            return [r.attenue("── Agent au travail…")]
        if t == "tour_texte":
            avant, self.attente = self.attente, evt.get("texte") or ""
            return r.etape(avant) if avant.strip() and r.etapes else []
        if t == "tour_outil":
            # Un texte suivi d'un outil est intermédiaire : il passe en étape avant l'outil.
            avant, self.attente = self.attente, ""
            return ([y for x in (avant, evt.get("texte", "")) if x.strip() for y in r.etape(x)]
                    if r.etapes else [])
        if t == "tour_fin":
            reponse, self.attente = self.attente.strip(), ""
            erreur = f" — {evt['erreur']}" if evt.get("erreur") else ""
            return ([r.entete("Agent"), reponse] if reponse else []) + [
                r.attenue(f"── Fin du tour ({evt.get('statut') or '?'}){erreur}")]
        return []


def suivre(ident: str, ecrire: Callable[[str], None], fin: threading.Event,
           pret: threading.Event, direct: Direct, titre: Callable[[], None]) -> None:
    """Lit le flux SSE et écrit les événements de la tâche ; se reconnecte s'il est coupé."""
    base = os.environ.get("ORCH_URL", "http://127.0.0.1:8300").rstrip("/")
    perdu = False
    while not fin.is_set():
        try:
            # Le serveur envoie une veille toutes les 15 s : 60 s sans rien = flux mort.
            with urllib.request.urlopen(base + "/api/evenements", timeout=60) as flux:
                if perdu:
                    ecrire(direct.r.attenue("(flux retrouvé)"))
                    titre()  # une reprise du terminal a pu effacer le titre de l'onglet
                perdu = False
                pret.set()
                for brut in flux:
                    if fin.is_set():
                        return
                    ligne = brut.decode("utf-8", "replace").strip()
                    if not ligne.startswith("data:"):
                        continue
                    evt = json.loads(ligne[5:])
                    if evt.get("tache") == ident:
                        for x in direct.evenement(evt):
                            ecrire(x)
        except (OSError, ValueError):
            pass
        if not fin.is_set():
            if not perdu:
                ecrire(direct.r.attenue("(flux en direct perdu, reconnexion…)"))
            perdu = True
            pret.set()
            fin.wait(2)


def executer(ident: str, entree: Iterable[str], ecrire: Callable[[str], None],
             r: Rendu | None = None) -> int:
    """Boucle de la console : historique, suivi en direct, lignes saisies."""
    r = r or Rendu()
    q = urllib.parse.quote(ident, safe="")
    t = cli.appeler("GET", f"/taches/{q}")

    def titre() -> None:
        # OSC 0 : titre de l'onglet ; reposé après chaque reconnexion.
        if r.couleurs:
            ecrire(f"\x1b]0;{titre_onglet(t['titre'])}\x07")

    def historique() -> None:
        for x in rendre_historique(cli.appeler("GET", f"/taches/{q}/conversation"), r):
            ecrire(x)

    titre()
    fin, pret = threading.Event(), threading.Event()
    # Le flux est ouvert avant de lire l'historique : aucun événement ne tombe entre les deux.
    fil = threading.Thread(target=suivre, args=(ident, ecrire, fin, pret, Direct(r), titre),
                           daemon=True)
    fil.start()
    pret.wait(10)
    ecrire(r.entete(f"{t['titre']} ({ident}) — {t['etat_execution']}"))
    historique()
    ecrire(r.attenue(AIDE))
    try:
        for brute in entree:
            ligne = brute.strip()
            if not ligne:
                continue
            if ligne == "/quitter":
                break
            try:
                if ligne == "/arret":
                    rep = cli.appeler("POST", f"/taches/{q}/arret")
                    ecrire(r.attenue(f"(arrêt demandé : {rep['etat_execution']})"))
                elif ligne == "/etapes":
                    r.etapes = not r.etapes
                    ecrire(r.attenue(f"(étapes {'affichées' if r.etapes else 'masquées'})"))
                    historique()
                elif ligne == "/aide":
                    ecrire(r.attenue(AIDE))
                else:
                    # INV-CONSOLE-1 : la route du chat, sans `de` : le message est celui de l'utilisateur.
                    rep = cli.appeler("POST", f"/taches/{q}/messages", {"texte": ligne})
                    ecrire(r.attenue(f"(envoyé — {rep['etat_execution']})"))
            except cli.ErreurCli as e:
                ecrire(str(e))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        # INV-CONSOLE-1 : fermer la vue ne touche pas au tour ; le flux SSE (fil démon) se ferme
        # avec le processus.
        fin.set()
    ecrire(r.attenue("Console fermée ; le tour éventuel continue dans GoldenBrain."))
    return 0


def couleurs_possibles() -> bool:
    """ANSI seulement vers un vrai terminal qui les accepte (NO_COLOR respecté)."""
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return os.environ.get("TERM") != "dumb"
    try:  # Windows : activer le traitement des séquences (ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        import ctypes
        k = ctypes.windll.kernel32
        h, mode = k.GetStdHandle(-11), ctypes.c_uint32()
        return bool(k.GetConsoleMode(h, ctypes.byref(mode)) and k.SetConsoleMode(h, mode.value | 4))
    except (AttributeError, OSError):
        return False


def main(ident: str, url: str | None = None) -> int:
    if url:
        os.environ["ORCH_URL"] = url
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # symboles et accents sur une console cp850
    except (AttributeError, ValueError):
        pass
    try:
        return executer(ident, sys.stdin, lambda x: print(x, flush=True), Rendu(couleurs_possibles()))
    except cli.ErreurCli as e:
        print(str(e), file=sys.stderr)
        return 1


def lancer(argv: list[str], nouvelle_console: bool) -> None:
    drapeaux = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if nouvelle_console else 0
    subprocess.Popen(argv, creationflags=drapeaux)


def ouvrir(ident: str, titre: str, url: str, orch: str) -> list[str]:
    """Ouvre `orch console` dans un onglet de Windows Terminal, à défaut dans une console neuve."""
    commande = [sys.executable, orch, "console", ident, "--url", url]
    wt = shutil.which("wt")
    if wt:
        # --suppressApplicationTitle : sans lui, Windows Terminal remplace le titre par celui du
        # programme lancé (python.exe).
        lancer([wt, "-w", "0", "nt", "--title", titre_onglet(titre), "--suppressApplicationTitle",
                *commande], False)
    else:
        lancer(commande, True)
    return commande
