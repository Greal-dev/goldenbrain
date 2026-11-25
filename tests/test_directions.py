"""Directions visuelles d'essai (INV-DIRECTION-1) : contrastes AA mesurés en clair et en sombre, sobriété (poids, ni flou
d'arrière-plan, ni animation, ni ressource distante), et aucun effet sur l'interface par défaut."""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
DIRECTIONS = ("a", "b", "c")

# (premier plan, fond, seuil) : texte courant 4,5:1 ; bord d'un champ ou d'un bouton 3:1 (WCAG 1.4.11).
PAIRES = [
    ("texte", "fond", 4.5), ("texte", "panneau", 4.5), ("texte", "panneau-2", 4.5),
    ("texte-2", "panneau", 4.5), ("texte-2", "panneau-2", 4.5), ("texte-2", "fond", 4.5),
    ("accent-texte", "accent", 4.5), ("accent", "panneau", 4.5), ("accent", "fond", 3),
    ("texte", "accent-fond", 4.5), ("texte", "sel", 4.5), ("texte", "survol", 4.5),
    ("bord-fort", "panneau", 3),
]
# Couleurs écrites en dur dans la barre haute de B (identique en clair et en sombre).
BARRE_B = [("#eef1f6", "#2a3242"), ("#eef1f6", "#36405a"), ("#eef1f6", "#3437c9"), ("#b7c0cf", "#1d2330"),
           ("#b7c0cf", "#07080b"), ("#ffffff", "#1d2330"), ("#eef1f6", "#0f131b"), ("#9aa4b5", "#0f131b"),
           ("#ff9b93", "#1d2330"), ("#eef1f6", "#0b0e14")]


def luminance(hexa):
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def jetons(direction):
    """{nom: (clair, sombre)} des jetons light-dark() de la feuille, complétés par ceux de style.css."""
    def lire(texte):
        return {n: (c, s) for n, c, s in re.findall(r"--([\w-]+):\s*light-dark\((#[0-9a-f]{6}),\s*(#[0-9a-f]{6})\)", texte)}
    base = lire((WEB / "style.css").read_text(encoding="utf-8"))
    return base | lire((WEB / "directions" / f"{direction}.css").read_text(encoding="utf-8"))


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_contrastes_aa_en_clair_et_en_sombre(direction):
    j = jetons(direction)
    faibles = [f"{a}/{b} {schema} {contraste(j[a][i], j[b][i]):.2f}"
               for a, b, seuil in PAIRES for i, schema in enumerate(("clair", "sombre"))
               if contraste(j[a][i], j[b][i]) < seuil]
    assert not faibles, faibles


def test_barre_haute_de_b_lisible():
    assert [p for p in BARRE_B if contraste(*p) < 4.5] == []


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_sobriete_de_la_feuille(direction):
    css = (WEB / "directions" / f"{direction}.css").read_text(encoding="utf-8")
    assert len(css.encode("utf-8")) <= 15 * 1024
    for interdit in ("backdrop-filter", "@keyframes", "animation", "url(", "@import", "@font-face", "blur("):
        assert interdit not in css, interdit
    # Chaque règle est bornée à sa direction : sans le paramètre d'essai, rien ne s'applique.
    selecteurs = re.findall(r"(?:^|})\s*([^{}@/][^{}]*)\{", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
    hors = [s for s in selecteurs if any(f'[data-direction="{direction}"]' not in p for p in s.split(","))]
    assert not hors, hors
    assert ":focus-visible" in css  # focus toujours visible, redessiné dans chaque direction


def test_defaut_inchange():
    """Sans ?theme=, la page ne cite aucune direction ; theme.js n'en charge qu'une valeur connue."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "directions/" not in html
    js = (WEB / "theme.js").read_text(encoding="utf-8")
    assert "d === 'a' || d === 'b' || d === 'c'" in js
