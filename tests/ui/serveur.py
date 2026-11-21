"""Lanceur du VRAI serveur pour les tests d'interface : `python tests/ui/serveur.py <config.toml>`.

Rôle : inscrire le harnais factice dans le registre `HARNAIS`, puis exécuter `orchestrateur.__main__`
tel quel (même app, même uvicorn, même boucle que `lancer.cmd`). Aucun faux serveur.
Frontières : le Python embarqué ignore PYTHONPATH, d'où l'ajout explicite de `src` et de ce dossier.
"""

import os
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path[:0] = [str(ICI.parents[1] / "src"), str(ICI)]



def faux_poste():
    """Assistant d'installation : un poste Windows factice où seul git est présent ; aucune vraie commande n'est lancée."""
    import tempfile

    from orchestrateur import executeur, installation

    executeur.LIAISON = Path(tempfile.mkdtemp()) / "liaison.json"  # jamais la vraie liaison du poste

    class SystemeFactice(installation.Systeme):
        presents = {"python", "git"}

        @property
        def plateforme(self):
            return "win32"

        def trouver(self, binaire, chemins=(), harnais=False):
            return "C:/faux/" + binaire if binaire in self.presents else ""

        def version_python(self):
            return (3, 12)

        def est_admin(self):
            return True

        def code_de(self, argv):
            return 0 if argv[0] in self.presents else 1

        def lancer(self, texte, interactif, sortie):
            sortie("[faux] " + texte)
            SystemeFactice.presents.add("tailscale")
            return 0

    installation.Systeme = SystemeFactice


if __name__ == "__main__":
    os.environ["ORCH_CONFIG"] = sys.argv[1]
    from harnais_factice import HarnaisFactice
    from orchestrateur.__main__ import main
    from orchestrateur.harnais import HARNAIS

    HARNAIS["faux"] = HarnaisFactice
    if os.environ.get("GB_DEMO"):  # démonstration : la colonne « Moteur » montre un harnais réel, joué par le factice
        HARNAIS["claude"] = HarnaisFactice
    faux_poste()  # INV-INSTALL-1 : l'interface n'atteint jamais le vrai poste
    from orchestrateur import console
    console.lancer = lambda argv, nouvelle: None  # jamais d'onglet de terminal réel pendant les scénarios
    main()
