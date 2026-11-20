"""Saisie sécurisée du jeton du bot Telegram, dans un terminal du poste.

Rôle : `saisir` demande le jeton sans l'afficher (une étoile par caractère), le vérifie (getMe), l'enregistre dans le coffre
du poste et confirme « jeton enregistré pour @nom » ; `commande`/`argv` donnent la commande exacte que
l'interface montre puis lance ; `ouvrir_terminal` l'ouvre dans un terminal (Windows Terminal ou console,
émulateur Linux, Terminal de macOS).
Frontières : aucune conversation d'agent, aucun harnais IA : le jeton ne passe que par le clavier du
terminal, le coffre et l'appel `getMe` ; jamais affiché, journalisé ni renvoyé à l'interface.
Invariants portés : INV-INSTALL-1 (commande exacte, jamais de texte libre), INV-TELEGRAM-2.
"""

from __future__ import annotations

import getpass
import os
import shlex
import shutil
import subprocess
import sys

from . import coffre, langues, natif
from .config import RACINE_DEPOT
from .telegram import Client, ErreurTelegram, masquer
from .telegram_connexion import fichier_jeton

# Émulateurs Linux : (binaire, arguments placés avant la commande). Ordre = préférence.
EMULATEURS = (("x-terminal-emulator", ("-e",)), ("gnome-terminal", ("--",)), ("kgx", ("-e",)),
              ("konsole", ("-e",)), ("xfce4-terminal", ("-x",)), ("tilix", ("-e",)),
              ("kitty", ()), ("alacritty", ("-e",)), ("xterm", ("-e",)))


def argv(config) -> list[str]:
    """La commande du catalogue : toujours celle-ci, aucune donnée extérieure n'y entre (INV-INSTALL-1)."""
    r = [sys.executable, str(RACINE_DEPOT / "orch.py"), "telegram-jeton", "--pause"]
    return r + ["--config", str(config.chemin)] if config.chemin else r


def commande(config) -> str:
    """Texte montré à l'utilisateur ; l'accord rendu doit lui être identique, caractère pour caractère."""
    return " ".join(f'"{x}"' if " " in x else x for x in argv(config))


def ouvrir_terminal(arguments: list[str]) -> str:
    """Ouvre `arguments` dans un terminal ; rend "" si c'est fait, sinon le motif (repli : copier la commande)."""
    dossier = str(RACINE_DEPOT)
    try:
        if sys.platform == "win32":
            natif.ouvrir_onglet("Jeton Telegram", dossier, arguments)
        elif sys.platform == "darwin":
            script = f'tell application "Terminal" to do script {_applescript(shlex.join(arguments))}'
            subprocess.Popen(["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'])
        else:
            if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                return langues.t("serveur.telegram_jeton.aucun_affichage")
            for binaire, avant in EMULATEURS:
                if chemin := shutil.which(binaire):
                    subprocess.Popen([chemin, *avant, *arguments], cwd=dossier, start_new_session=True)
                    return ""
            return langues.t("serveur.telegram_jeton.aucune_invite")
    except OSError as e:
        return langues.t("serveur.telegram_jeton.ouverture_impossible", detail=e)
    return ""


ESSAIS = 3  # tentatives de saisie avant de fermer la fenêtre


def _applescript(texte: str) -> str:
    return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lire_masque(invite: str) -> str:
    """Saisie masquée qui affiche une étoile par caractère : avec getpass, rien ne s'affiche et l'on
    ne sait pas si le collage a pris (retour d'essai, 18/11). Hors terminal : getpass."""
    if not sys.stdin.isatty():
        return getpass.getpass(invite)
    sys.stdout.write(invite)
    sys.stdout.flush()
    lus: list[str] = []
    for c in _caracteres():
        if c in ("\r", "\n"):
            break
        if c == "\x03":
            raise KeyboardInterrupt
        if c in ("\x08", "\x7f"):
            if lus:
                lus.pop()
                sys.stdout.write("\b \b")
        elif c.isprintable():
            lus.append(c)
            sys.stdout.write("*")
        sys.stdout.flush()
    sys.stdout.write("\n")
    return "".join(lus)


def _caracteres():
    """Caractères du clavier un par un, sans écho (msvcrt sous Windows, termios ailleurs)."""
    if os.name == "nt":
        import msvcrt
        while True:
            yield msvcrt.getwch()
    import termios
    import tty
    fd = sys.stdin.fileno()
    avant = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            c = sys.stdin.read(1)
            if not c:
                return
            yield c
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, avant)


def saisir(config, lire=lire_masque, sortie=print, pause=None, essais: int = ESSAIS) -> int:
    """Demande, vérifie et enregistre le jeton ; 0 si enregistré. Saisie vide ou jeton refusé : on
    redemande, jusqu'à `essais` fois, au lieu de fermer la fenêtre (retour d'essai, 18/11). `pause` :
    attente avant de fermer."""
    try:
        for n in range(1, essais + 1):
            try:
                jeton = lire("Jeton du bot (une étoile par caractère ; Entrée pour valider) : ").strip()
            except (EOFError, KeyboardInterrupt):
                sortie("Saisie interrompue : rien n'est enregistré.")
                return 1
            reste = f" Nouvel essai ({n + 1}/{essais})." if n < essais else ""
            if not jeton:
                sortie("Aucun jeton saisi : rien n'est enregistré. Pour coller dans un terminal : Ctrl+Maj+V "
                       "ou clic droit → Coller (des étoiles apparaissent), puis Entrée." + reste)
                continue
            try:
                moi = Client(config.telegram.api, jeton).appel("getMe", {}, 15)
            except ErreurTelegram as e:
                sortie(f"Jeton refusé par Telegram : {masquer(str(e), jeton)}. Rien n'est enregistré." + reste)
                continue
            try:
                coffre.proteger(jeton, fichier_jeton(config))
            except OSError as e:
                sortie(f"Enregistrement impossible : {masquer(str(e), jeton)}")
                return 1
            sortie(f"jeton enregistré pour @{moi.get('username', '?')}")
            if os.environ.get(config.telegram.jeton_variable, "").strip():
                sortie(f"Attention : la variable {config.telegram.jeton_variable} reste prioritaire sur ce jeton.")
            return 0
        return 1
    finally:
        if pause:
            try:
                pause("Appuyez sur Entrée pour fermer cette fenêtre. ")
            except (EOFError, KeyboardInterrupt):
                pass
