"""Régression : les bordures de champs étaient à 1,7:1 (WCAG 1.4.11 exige 3:1).

Rôle : lit --bord-fort et les fonds dans web/style.css et mesure le contraste dans les deux thèmes.
Le champ (--panneau, --panneau-2) et le fond de page (--fond) sont les surfaces sur lesquelles
une bordure de champ se détache ; les états de survol et de sélection sont passagers, hors mesure.
"""
import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "web" / "style.css"
SEUIL = 3.0


def _jeton(nom: str) -> tuple[str, str]:
    m = re.search(rf"--{nom}:\s*light-dark\(\s*(#[0-9a-fA-F]{{6}})\s*,\s*(#[0-9a-fA-F]{{6}})\s*\)",
                  CSS.read_text(encoding="utf-8"))
    assert m, f"jeton --{nom} introuvable"
    return m.group(1), m.group(2)


def _luminance(hexa: str) -> float:
    canaux = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contraste(a: str, b: str) -> float:
    haut, bas = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (haut + 0.05) / (bas + 0.05)


def test_bordure_de_champ_a_3_pour_1_dans_les_deux_themes():
    bord = _jeton("bord-fort")
    for theme in (0, 1):
        for fond in ("fond", "panneau", "panneau-2"):
            c = _contraste(bord[theme], _jeton(fond)[theme])
            assert c >= SEUIL, (
                f"--bord-fort {bord[theme]} sur --{fond} {_jeton(fond)[theme]} "
                f"({'clair' if theme == 0 else 'sombre'}) : {c:.2f}:1 < {SEUIL}:1")
