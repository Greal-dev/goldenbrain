"""Affichage par défaut « sobre éditorial » (INV-AFFICHAGE-1) : contrastes AA mesurés en clair et en sombre, barre haute
sombre comprise ; accent en une seule variable dont les fonds dérivent ; action positive à l'encre, jamais au rouge ;
sobriété de la surcouche (poids, ni flou, ni animation, ni ressource distante) ; plus aucune direction d'essai."""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
STYLE = (WEB / "style.css").read_text(encoding="utf-8")
AFFICHAGE = (WEB / "affichage.css").read_text(encoding="utf-8")

# (premier plan, fond, seuil) : texte courant 4,5:1 ; bord d'un champ, repère d'accent 3:1 (WCAG 1.4.11).
PAIRES = [
    ("texte", "fond", 4.5), ("texte", "panneau", 4.5), ("texte", "panneau-2", 4.5),
    ("texte-2", "panneau", 4.5), ("texte-2", "panneau-2", 4.5), ("texte-2", "fond", 4.5), ("texte-2", "survol", 4.5),
    ("accent-texte", "accent", 4.5), ("accent", "panneau", 4.5), ("accent", "fond", 3), ("accent", "accent-fond", 4.5),
    ("texte", "accent-fond", 4.5), ("texte", "sel", 4.5), ("texte", "survol", 4.5),
    ("action-texte", "action", 4.5), ("danger", "panneau", 4.5), ("danger", "danger-fond", 4.5),
    ("bord-fort", "panneau", 3), ("bord-fort", "panneau-2", 3),
]
# Barre haute : couleurs fixes, identiques en clair et en sombre ; les jetons y valent leur version sombre.
BARRE = "#1c1b19"
PAIRES_BARRE = [("#f1efea", BARRE), ("#ffffff", BARRE), ("#bdb9b1", BARRE), ("#f1efea", "#2a2926"), ("#bdb9b1", "#2a2926"),
                ("#f1efea", "#3a3834"), ("#ffffff", "#3a2620"), ("#ffffff", "#0c0c0b"), ("#161512", "#f1efea"),
                ("#f1efea", "#0f0f0e"), ("#a8a49c", "#0f0f0e")]


def luminance(hexa):
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def melange(a, b, part):
    """color-mix(in srgb, a part%, b) : moyenne pondérée par canal, en sRGB."""
    return "#" + "".join(f"{round(int(a[i:i + 2], 16) * part + int(b[i:i + 2], 16) * (1 - part)):02x}" for i in (1, 3, 5))


def jetons():
    """{nom: (clair, sombre)} : jetons light-dark() de style.css, puis alias et mélanges color-mix résolus."""
    j = {n: (c, s) for n, c, s in re.findall(r"--([\w-]+):\s*light-dark\((#[0-9a-f]{6}),\s*(#[0-9a-f]{6})\)", STYLE)}
    for n, a, p, b in re.findall(r"--([\w-]+):\s*color-mix\(in srgb, var\(--([\w-]+)\) (\d+)%, var\(--([\w-]+)\)\)", STYLE):
        j[n] = tuple(melange(j[a][i], j[b][i], int(p) / 100) for i in (0, 1))
    for n, a in re.findall(r"--([\w-]+):\s*var\(--([\w-]+)\);", STYLE):
        j[n] = j[a]
    return j


def test_contrastes_aa_en_clair_et_en_sombre():
    j = jetons()
    faibles = [f"{a}/{b} {schema} {contraste(j[a][i], j[b][i]):.2f}"
               for a, b, seuil in PAIRES for i, schema in enumerate(("clair", "sombre"))
               if contraste(j[a][i], j[b][i]) < seuil]
    assert not faibles, faibles


def test_barre_haute_sombre_lisible():
    j = jetons()
    assert f"--barre: {BARRE}" in AFFICHAGE and "#bandeau { color-scheme: dark;" in AFFICHAGE
    faibles = [p for p in PAIRES_BARRE if contraste(*p) < 4.5]
    # Repères dans la barre (version sombre des jetons) : accent du focus et de la pastille pressée, alerte, connexion perdue.
    faibles += [(n, s) for n, s in (("accent", 3), ("danger", 4.5)) if contraste(j[n][1], BARRE) < s]
    assert contraste(j["c-attente"][1], "#1b1205") >= 4.5  # pastille d'alerte : --sur-vif sur l'orange
    assert not faibles, faibles


def test_accent_unique_et_action_a_l_encre():
    assert len(re.findall(r"--accent:", STYLE)) == 1
    for derive in ("accent-fond", "sel"):
        assert re.search(rf"--{derive}: color-mix\(in srgb, var\(--accent\)", STYLE), derive
    feuilles = "".join(p.read_text(encoding="utf-8") for p in WEB.glob("*.css"))
    assert "background: var(--accent); border-color: var(--accent); color: var(--accent-texte)" not in feuilles
    assert re.search(r"\.btn\.primaire \{ background: var\(--action\)", STYLE)
    assert ":root .btn.primaire, :root .btn.primaire:hover { background: var(--action);" in AFFICHAGE  # la surcouche ne le rend pas transparent
    j = jetons()
    assert all(j["action"][i] != j["danger"][i] for i in (0, 1))


def test_sobriete_de_la_surcouche():
    assert len(AFFICHAGE.encode("utf-8")) <= 15 * 1024
    for interdit in ("backdrop-filter", "@keyframes", "animation", "url(", "@import", "@font-face", "blur("):
        assert interdit not in AFFICHAGE, interdit
    assert ":focus-visible" in AFFICHAGE
    assert (WEB / "styles.liste").read_text(encoding="utf-8").split()[-1] == "affichage.css"  # dernière : elle l'emporte


def test_plus_de_direction_d_essai():
    assert not (WEB / "directions").exists()
    for f in ("index.html", "theme.js"):
        texte = (WEB / f).read_text(encoding="utf-8")
        assert "directions/" not in texte and "data-direction" not in texte and "dataset.direction" not in texte
