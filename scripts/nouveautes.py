"""Nouveautés d'une version publiée : `CHANGELOG.md`, note de version, commande `gh release create`.

Rôle : appelé par la CI au moment de publier une version verte vers le dépôt public.
  journal  : ajoute en tête de `CHANGELOG.md` la section de la version (entrées de `depuis..jusqua`),
             écrit la note de version à part et imprime le numéro de version ;
  message  : imprime le message du commit unique poussé sur le dépôt public (sujet daté + une ligne
             `Nouveauté:` par entrée de `depuis..jusqua`) : sans elles, « Quoi de neuf ? » reste vide ;
  release  : imprime la commande `gh release create` de cette version ; ne l'exécute qu'avec `--envoyer`.
Frontières : n'envoie rien sans `--envoyer` (publication externe = accord écrit de l'utilisateur) ; ne pousse rien ;
les entrées viennent de `orchestrateur.nouveautes` (INV-NOUV-1).
"""

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from orchestrateur import nouveautes  # noqa: E402


def journal(a) -> int:
    depot = Path(a.depot)
    sortie = Path(a.sortie)
    precedent = Path(a.precedent).read_text(encoding="utf-8") if a.precedent else ""
    jour = dt.date.fromisoformat(a.jour) if a.jour else dt.date.today()
    version = nouveautes.prochaine_version(precedent, jour)
    sec = nouveautes.section(version, nouveautes.entrees(depot, a.depuis or None, a.jusqua))
    sortie.write_text(nouveautes.ajouter(precedent, sec), encoding="utf-8")
    if a.notes:
        corps = sec.split("\n", 2)[2]  # sans le titre : GitHub affiche déjà le nom de la version
        Path(a.notes).write_text(corps + "\nJournal complet : CHANGELOG.md\n", encoding="utf-8")
    print(version)
    return 0


def message(a) -> int:
    jour = a.jour or dt.date.today().isoformat()
    heure = a.heure or dt.datetime.now().strftime("%H:%M")
    lignes = [f"Nouveauté: {e}" for e in nouveautes.entrees(Path(a.depot), a.depuis or None, a.jusqua)]
    print("\n".join([f"GoldenBrain, version du {jour} {heure}", "", *lignes]))
    return 0


def release(a) -> int:
    commande = ["gh", "release", "create", f"v{a.version}", "--repo", a.depot_distant, "--target", a.cible,
                "--title", f"GoldenBrain {a.version}", "--notes-file", a.notes]
    if not a.envoyer:
        print(" ".join(commande))
        return 0
    return subprocess.run(commande).returncode


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sous = p.add_subparsers(dest="action", required=True)
    j = sous.add_parser("journal", help="mettre CHANGELOG.md à jour pour une version")
    j.add_argument("--depot", default=str(RACINE), help="dépôt git où lire l'historique")
    j.add_argument("--depuis", default="", help="dernière version publiée (vide : tout l'historique)")
    j.add_argument("--jusqua", default="HEAD", help="version à publier")
    j.add_argument("--precedent", help="CHANGELOG.md de la version publiée précédente")
    j.add_argument("--sortie", default="CHANGELOG.md")
    j.add_argument("--notes", help="fichier où écrire la note de version (Release GitHub)")
    j.add_argument("--jour", help="date de la version, AAAA-MM-JJ (défaut : aujourd'hui)")
    m = sous.add_parser("message", help="message du commit public : sujet daté et lignes « Nouveauté: »")
    m.add_argument("--depot", default=str(RACINE), help="dépôt git où lire l'historique")
    m.add_argument("--depuis", default="", help="dernière version publiée (vide : tout l'historique)")
    m.add_argument("--jusqua", default="HEAD")
    m.add_argument("--jour", help="AAAA-MM-JJ (défaut : aujourd'hui)")
    m.add_argument("--heure", help="HH:MM (défaut : maintenant)")
    r = sous.add_parser("release", help="note de version GitHub (gh release create)")
    r.add_argument("--version", required=True)
    r.add_argument("--depot-distant", required=True, help="propriétaire/dépôt sur GitHub")
    r.add_argument("--cible", required=True, help="enregistrement publié (empreinte)")
    r.add_argument("--notes", required=True, help="fichier écrit par `journal --notes`")
    r.add_argument("--envoyer", action="store_true", help="exécuter réellement (sinon : afficher la commande)")
    a = p.parse_args()
    return {"journal": journal, "message": message, "release": release}[a.action](a)


if __name__ == "__main__":
    sys.exit(main())
