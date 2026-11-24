"""Assistant « Ajouter ce PC comme exécuteur » : ce qui manque, étape par étape, jamais sans accord.

Rôle : catalogue des étapes (Python, git, Tailscale, GitHub CLI, Node, harnais et leurs connexions
officielles), diagnostic de ce poste, exécution d'UNE étape sur accord, repli en instructions à copier
quand une installation demande les droits administrateur ; puis appairage au chef. Sert la commande
`orch executeur installer` (terminal) et les routes locales `/api/installation` (Réglages).
Frontières : n'importe ni le moteur ni le vault ; ne parle au chef que par `executeur.py` (appairage) ;
ne lit, ne stocke ni ne transmet aucun identifiant de harnais, de GitHub ou de Tailscale.
Invariants portés : INV-INSTALL-1 (rien sans accord, portant la commande exacte affichée ; commandes
du seul catalogue), INV-INSTALL-2 (connexions lancées telles quelles dans l'outil officiel : jamais
d'identifiant manipulé ici), INV-INSTALL-3 (droits administrateur : repli en instructions à copier).
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import executeur, langues
from .harnais.processus import resoudre

W, L, M = "win32", "linux", "darwin"
ORDRE_ELEVATION = re.compile(r"administrat|elevat|access is denied|accès refusé|permission denied|EACCES|must be root|sudo", re.I)
OUI = {"o", "oui", "y", "yes"}


@dataclass(frozen=True)
class Commande:
    texte: str                  # affiché tel quel, lancé tel quel (INV-INSTALL-1)
    elevation: str = ""         # "" | "uac" (Windows demande lui-même) | "sudo" (mot de passe demandé par sudo)
    sans_saisie: bool = True    # faux : l'outil interroge l'utilisateur, il se lance dans un terminal


@dataclass(frozen=True)
class Outil:
    id: str
    libelle: str | Callable[[], str]    # texte fixe (nom propre) ou fonction (texte traduit à l'affichage)
    binaire: str
    installer: dict            # plateforme → Commande ; absente : instructions seulement
    manuel: str | Callable[[], str] = ""
    apres: tuple = ()          # outils à installer d'abord
    chemins: tuple = ()        # emplacements usuels hors PATH (Windows)
    harnais: bool = False
    optionnel: bool = False
    etat_connexion: tuple | None = None   # argv ; code 0 = connecté ; None : indétectable
    connexion: Commande | None = None
    connexion_manuelle: str | Callable[[], str] = ""


def _txt(v: str | Callable[[], str]) -> str:
    return v() if callable(v) else v


def _winget(ident: str) -> Commande:
    return Commande(f"winget install --id {ident} -e --accept-package-agreements --accept-source-agreements", "uac")


def _npm(paquet: str) -> dict:
    c = Commande(f"npm install -g {paquet}")
    # Linux : le préfixe global de npm (/usr/local) appartient à root, la commande nue échoue en EACCES (audit L3, A4).
    return {W: c, L: Commande(f"sudo npm install -g {paquet}", "sudo"), M: c}


# INV-INSTALL-1 : seul chemin vers une commande ; aucune donnée externe n'y entre.
OUTILS = (
    Outil("python", lambda: langues.t("serveur.installation.libelle_python"), "python", {},
          manuel=lambda: langues.t("serveur.installation.manuel_python")),
    Outil("git", "git", "git", {W: _winget("Git.Git"), L: Commande("sudo apt-get install -y git", "sudo"), M: Commande("brew install git")}),
    Outil("tailscale", lambda: langues.t("serveur.installation.libelle_tailscale"), "tailscale",
          {W: _winget("Tailscale.Tailscale"), L: Commande("curl -fsSL https://tailscale.com/install.sh | sh", "sudo")},
          manuel=lambda: langues.t("serveur.installation.manuel_tailscale"), chemins=(r"C:\Program Files\Tailscale\tailscale.exe",),
          etat_connexion=("tailscale", "status"), connexion=Commande("tailscale up")),
    Outil("gh", lambda: langues.t("serveur.installation.libelle_gh"), "gh", {W: _winget("GitHub.cli"), M: Commande("brew install gh")},
          manuel=lambda: langues.t("serveur.installation.manuel_gh"), optionnel=True, etat_connexion=("gh", "auth", "status"),
          connexion=Commande("gh auth login --hostname github.com --git-protocol https --web", sans_saisie=False)),
    Outil("node", lambda: langues.t("serveur.installation.libelle_node"), "node",
          {W: _winget("OpenJS.NodeJS.LTS"), M: Commande("brew install node")},
          manuel=lambda: langues.t("serveur.installation.manuel_node"), optionnel=True),
    Outil("claude", "Claude Code", "claude",
          {W: Commande('powershell -NoProfile -Command "irm https://claude.ai/install.ps1 | iex"'),
           L: Commande("curl -fsSL https://claude.ai/install.sh | bash"), M: Commande("curl -fsSL https://claude.ai/install.sh | bash")},
          harnais=True, optionnel=True, etat_connexion=("claude", "auth", "status"), connexion=Commande("claude auth login", sans_saisie=False)),
    Outil("codex", "Codex", "codex", _npm("@openai/codex"), apres=("node",), harnais=True, optionnel=True,
          etat_connexion=("codex", "login", "status"), connexion=Commande("codex login --device-auth")),
    Outil("copilot", "Copilot CLI", "copilot", _npm("@github/copilot"), apres=("node",), harnais=True, optionnel=True,
          connexion_manuelle=lambda: langues.t("serveur.installation.connexion_copilot")),
    Outil("opencode", "OpenCode", "opencode", _npm("opencode-ai"), apres=("node",), harnais=True, optionnel=True,
          connexion=Commande("opencode auth login", sans_saisie=False)),
    Outil("agy", "Antigravity", "agy", {}, manuel=lambda: langues.t("serveur.installation.manuel_agy"),
          harnais=True, optionnel=True, connexion_manuelle=lambda: langues.t("serveur.installation.connexion_agy")),
)
PAR_ID = {o.id: o for o in OUTILS}
HARNAIS_CHOISIS = tuple(o.id for o in OUTILS if o.harnais)


class EtapeInconnue(KeyError):
    pass


class EtapeBloquee(ValueError):
    pass


class AccordRefuse(ValueError):
    pass


class Systeme:
    """Le poste réel : ce que l'assistant en sait, ce qu'il y lance. Remplacé par un faux en test."""

    @property
    def plateforme(self) -> str:
        return L if sys.platform.startswith("linux") else sys.platform

    def trouver(self, binaire: str, chemins: tuple = (), harnais: bool = False) -> str:
        if binaire == "python":
            return sys.executable
        try:
            if harnais:
                return resoudre(binaire)[0]  # même résolution que l'annonce de l'exécuteur
        except FileNotFoundError:
            return ""
        return shutil.which(binaire) or next((c for c in chemins if os.path.exists(c)), "")

    def tete(self, binaire: str, chemins: tuple = (), harnais: bool = False) -> tuple:
        """Argv complet qui lance l'outil, sans ses arguments (vide : introuvable). Un harnais résolu
        par node vaut (node, script) : garder le seul interpréteur ferait lancer `node login status`."""
        chemin = self.trouver(binaire, chemins, harnais)
        if not chemin or not harnais:
            return (chemin,) if chemin else ()
        try:
            complet = tuple(resoudre(binaire))
        except FileNotFoundError:
            return (chemin,)
        return complet if complet[0] == chemin else (chemin,)

    def version_python(self) -> tuple:
        return sys.version_info[:2]

    def est_admin(self) -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin()) if sys.platform == W else os.geteuid() == 0
        except (AttributeError, OSError):
            return False

    def code_de(self, argv: tuple) -> int | None:
        try:
            return subprocess.run(list(argv), capture_output=True, timeout=20, stdin=subprocess.DEVNULL).returncode
        except (OSError, subprocess.SubprocessError):
            return None

    def lancer(self, texte: str, interactif: bool, sortie: Callable[[str], None]) -> int:
        """Interactif : terminal hérité tel quel (l'outil dialogue seul avec l'utilisateur).
        Sinon : clavier fermé, sortie rendue ligne à ligne ; arrêt après 15 minutes."""
        if interactif:
            return subprocess.run(texte, shell=True).returncode
        p = subprocess.Popen(texte, shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        minuteur = threading.Timer(900, p.kill)
        minuteur.start()
        try:
            for ligne in p.stdout:
                sortie(ligne.rstrip())
            return p.wait()
        finally:
            minuteur.cancel()


@dataclass
class Resultat:
    etape: str
    code: int | None           # None : rien n'a été lancé
    etat: str
    repli: str = ""            # instructions à copier


class Assistant:
    def __init__(self, systeme: Systeme | None = None):
        self.systeme = systeme or Systeme()

    # --- diagnostic -----------------------------------------------------------------------
    @staticmethod
    def ids() -> list[str]:
        return [i for o in OUTILS for i in (o.id, *((o.id + "-connexion",) if o.connexion or o.connexion_manuelle else ()))]

    def _present(self, o: Outil) -> bool:
        if o.id == "python":
            return self.systeme.version_python() >= (3, 12)
        return bool(self.systeme.trouver(o.binaire, o.chemins, o.harnais))

    def _commande(self, ident: str) -> tuple[Outil, Commande | None, bool]:
        base, _, suite = ident.partition("-")
        if base not in PAR_ID or suite not in ("", "connexion") or (suite and not (PAR_ID[base].connexion or PAR_ID[base].connexion_manuelle)):
            raise EtapeInconnue(ident)
        o = PAR_ID[base]
        if suite:
            return o, o.connexion, True
        return o, o.installer.get(self.systeme.plateforme), False

    def _etat_connexion(self, o: Outil) -> str:
        if not o.etat_connexion:
            return "inconnu"
        argv = (*(self.systeme.tete(o.binaire, o.chemins, o.harnais) or (o.binaire,)), *o.etat_connexion[1:])
        return "ok" if self.systeme.code_de(argv) == 0 else "a_connecter"

    def ligne(self, ident: str) -> dict:
        o, cmd, connexion = self._commande(ident)
        attend = [d for d in ([o.id] if connexion else o.apres) if not self._present(PAR_ID[d])]
        if connexion and not attend:
            etat = self._etat_connexion(o)
        elif attend:
            etat = "bloque"
        elif self._present(o) and not connexion:
            etat = "ok"
        else:
            etat = "manquant" if cmd else "manuel"
        instructions, au_terminal = "", False
        if etat == "manuel":
            instructions = _txt(o.manuel)
        elif etat in ("a_connecter", "inconnu"):
            if not cmd:
                instructions = _txt(o.connexion_manuelle)
            elif not cmd.sans_saisie:
                instructions = langues.t("serveur.installation.dans_un_terminal", commande=cmd.texte)
                au_terminal = True  # phrase déjà complète : l'interface ne l'enrobe pas (indépendant de la langue)
        libelle = langues.t("serveur.installation.connexion_de", libelle=_txt(o.libelle)) if connexion \
            else _txt(o.libelle)
        return {"id": ident, "libelle": libelle, "etat": etat,
                "genre": "connexion" if connexion else "harnais" if o.harnais else "outil", "optionnel": o.optionnel,
                "commande": cmd.texte if cmd else "", "elevation": cmd.elevation if cmd else "",
                "sans_saisie": cmd.sans_saisie if cmd else False, "instructions": instructions,
                "au_terminal": au_terminal, "attend": attend}

    def plan(self) -> list[dict]:
        return [self.ligne(i) for i in self.ids()]

    # --- exécution d'une étape ------------------------------------------------------------
    def executer(self, ident: str, accord: str, interactif: bool = False,
                 sortie: Callable[[str], None] | None = None) -> Resultat:
        """Lance l'étape `ident` si `accord` est la commande exacte affichée (INV-INSTALL-1)."""
        ligne = self.ligne(ident)
        _, cmd, connexion = self._commande(ident)
        if ligne["etat"] == "ok":
            return Resultat(ident, None, "ok")
        if ligne["etat"] == "bloque":
            raise EtapeBloquee(langues.t("serveur.installation.d_abord", etapes=", ".join(ligne["attend"])))
        if cmd is None:
            return Resultat(ident, None, ligne["etat"], ligne["instructions"])
        if accord != cmd.texte:
            raise AccordRefuse(langues.t("serveur.installation.accord_refuse"))
        admin = self.systeme.est_admin()
        # INV-INSTALL-2 : une commande qui dialogue avec l'utilisateur n'a pas de clavier ici.
        if not interactif and not cmd.sans_saisie:
            return Resultat(ident, None, ligne["etat"], langues.t("serveur.installation.dialogue", commande=cmd.texte))
        # INV-INSTALL-3 : sudo sans terminal ni droits ne peut pas aboutir.
        if not interactif and cmd.elevation == "sudo" and not admin:
            return Resultat(ident, None, ligne["etat"], self.repli_admin(cmd))
        lignes: list[str] = []

        def noter(l: str) -> None:
            lignes.append(l)
            if sortie:
                sortie(l)

        code = self.systeme.lancer(cmd.texte, interactif, noter)
        repli = ""
        if code != 0 and ((cmd.elevation and not admin) or ORDRE_ELEVATION.search("\n".join(lignes[-40:]))):
            repli = self.repli_admin(cmd)
        return Resultat(ident, code, self.ligne(ident)["etat"], repli)

    def repli_admin(self, cmd: Commande) -> str:
        if self.systeme.plateforme == W:
            return langues.t("serveur.installation.repli_windows", commande=cmd.texte)
        return langues.t("serveur.installation.repli", commande=cmd.texte)


def verifier_chef(serveur: str, jeton: str) -> bool:
    """Le chef répond-il, et reconnaît-il ce jeton ? (lecture seule : rien n'est annoncé)"""
    req = urllib.request.Request(serveur.rstrip("/") + "/api/arbre", headers={"X-Orchestrateur": "1", "X-Orch-Jeton": jeton})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except (OSError, urllib.error.URLError):
        return False


# --- parcours au terminal ---------------------------------------------------------------------
def selection(harnais: list[str]) -> list[str]:
    voulus = {"python", "git", "tailscale", "gh", *harnais}
    voulus |= {d for h in harnais for d in PAR_ID[h].apres}
    return [i for i in Assistant.ids() if i.removesuffix("-connexion") in voulus]


def parcours(assistant: Assistant, harnais: list[str], entree=input, sortie=print, verifier: bool = False) -> int:
    """Étape par étape : affiche ce qui va être fait, demande, puis seulement alors lance. Défaut : non."""
    inconnus = [h for h in harnais if h not in HARNAIS_CHOISIS]
    if inconnus:
        sortie(f"harnais inconnu : {', '.join(inconnus)} (choix : {', '.join(HARNAIS_CHOISIS)})")
        return 2
    ids = selection(harnais)
    echec = False
    for n, ident in enumerate(ids, 1):
        l = assistant.ligne(ident)
        sortie(f"── {n}/{len(ids)} {l['libelle']} : {l['etat']}")
        if l["etat"] == "ok" or verifier:
            continue
        if l["etat"] == "bloque":
            sortie(f"   d'abord : {', '.join(l['attend'])}")
            continue
        if not l["commande"]:
            sortie("   " + (l["instructions"] or "à faire à la main"))
            continue
        sortie(f"   Ce qui va être fait : {l['commande']}")
        if l["etat"] != "manquant":
            sortie("   La connexion se fait dans l'outil officiel : GoldenBrain ne voit ni ne garde ce que tu y saisis.")
        if l["elevation"] == "uac":
            sortie("   Windows peut te demander ton accord pour les droits administrateur.")
        if l["elevation"] == "sudo":
            sortie("   sudo te demandera ton mot de passe (à lui seul).")
        try:
            reponse = entree("   Faire cette étape ? [o/N] ").strip().casefold()
        except (EOFError, KeyboardInterrupt):
            sortie("   arrêt : rien de plus n'est lancé.")
            return 1
        if reponse not in OUI:
            sortie("   passée.")
            continue
        r = assistant.executer(ident, l["commande"], interactif=True)
        sortie(f"   → {r.etat}" + (f" (code {r.code})" if r.code else ""))
        echec = echec or bool(r.code)
        if r.repli:
            sortie(r.repli)
    return 1 if echec else 0


def parcours_liaison(serveur: str, entree=input, sortie=print, demarrer=None) -> int:
    """Appairage au chef : adresse + code court affichés par le chef ; le jeton reçu n'est jamais montré."""
    garde, jeton = executeur.liaison()
    serveur = serveur or garde
    if jeton and serveur == garde and verifier_chef(serveur, jeton):
        sortie(f"déjà relié à {serveur}.")
    else:
        try:
            serveur = serveur or entree("Adresse du chef (ex. http://100.x.y.z:8300 ; vide pour passer) : ").strip()
            code = entree("Code affiché par le chef (Réglages → PC connectés → Appairer un PC ; vide pour passer) : ").strip() if serveur else ""
        except (EOFError, KeyboardInterrupt):
            return 1
        if not (serveur and code):
            sortie("appairage passé : relance cette commande avec le code du chef.")
            return 0
        try:
            sortie(f"appairé comme « {executeur.lier(serveur, code)} ».")
        except executeur.AppairageRefuse as e:
            sortie(f"appairage refusé : {e}")
            return 1
        if not verifier_chef(serveur, executeur.liaison()[1]):
            sortie("le chef ne répond pas avec ce jeton : vérifie l'adresse et Tailscale.")
            return 1
        sortie("le chef reconnaît ce PC.")
    try:
        if entree("Démarrer l'exécuteur maintenant ? [o/N] ").strip().casefold() in OUI and demarrer:
            return demarrer(serveur)
    except (EOFError, KeyboardInterrupt):
        pass
    sortie("Pour le démarrer plus tard : python orch.py executeur")
    return 0


def principal(serveur: str, harnais: str, verifier: bool) -> int:
    """`orch executeur installer` : prérequis d'abord (chaque étape sur accord), puis appairage au chef."""
    r = parcours(Assistant(), [h.strip() for h in harnais.split(",") if h.strip()], verifier=verifier)
    if r or verifier:
        return r
    return parcours_liaison(serveur, demarrer=lambda s: executeur.main(s, "", None, 1))
