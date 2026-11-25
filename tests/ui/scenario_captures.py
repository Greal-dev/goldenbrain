"""Captures et vidéo de démonstration sur un vault fictif, dans les quatre langues (INV-PUB-1 : aucune donnée réelle).

Rôle : par langue, un serveur dédié (vault `demo_vault.py`, langue posée dans `config.toml`, harnais factice
inscrit sous le nom « claude » et jouant les scènes de la démonstration), puis un parcours filmé : arbre qui
s'anime, tâche (conversation et note), écran « En cours » (sous-agents), graphe du second cerveau. Quatre
images prises en chemin : `arbre-<l>.png`, `tache-<l>.png`, `travaux-<l>.png`, `graphe-<l>.png`, et la vidéo
`demo-<l>.webm`.
Frontières : écrit dans `GB_CAPTURES` (posé par `scripts/captures.py`, qui joue alors les quatre langues à vitesse
de lecture) ; sans lui, porte d'interface : français seul, pauses écourtées, sorties dans le dossier du test.
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect

import demo_vault
import univers
from aides_arbre import deplier_tout
from conftest import demarrer

SORTIE = os.environ.get("GB_CAPTURES")
LANGUES = ("fr", "en", "de", "es") if SORTIE else ("fr",)
LENTEUR = 1.0 if SORTIE else 0.05  # la vidéo se lit ; la porte, elle, n'attend pas
H = {"X-Orchestrateur": "1"}  # l'API refuse ce qui ne vient pas de l'interface
TAILLE = {"width": 1600, "height": 900}


@pytest.fixture(scope="module", params=LANGUES)
def demo(request, tmp_path_factory):
    code = request.param
    dossier = tmp_path_factory.mktemp(f"ui-captures-{code}")
    scenes = dossier / "scenes.json"
    scenes.write_text(json.dumps(demo_vault.scenes(code), ensure_ascii=False), encoding="utf-8")
    construire = univers.construire

    def construire_demo(d, port, telegram_api=""):
        # Vault écrit AVANT le démarrage : les index (tâches, notes, graphe) naissent sur la démonstration.
        config = construire(d, port, telegram_api)
        demo_vault.ecrire_vault(d / "vault", code)
        exe = Path(sys.executable).as_posix()  # une commande qui existe : ni « indisponible » ni vrai agent
        texte = config.read_text(encoding="utf-8").replace('harnais_defaut = "faux"', 'harnais_defaut = "claude"')
        texte = texte.replace("silence_s = 3\n", "silence_s = 300\n")  # pas d'alerte « silencieux » sur l'image
        texte += f'\n[harnais.claude]\ncommande = "{exe}"\n\n[interface]\nlangue = "{code}"\n'
        config.write_text(texte, encoding="utf-8")
        return config

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GB_DEMO", str(scenes))  # hérité par le serveur, lu par le harnais factice
        mp.setattr(univers, "construire", construire_demo)
        for srv in demarrer(dossier):
            srv.code = code
            yield srv


def _pause(page, secondes: float) -> None:
    page.wait_for_timeout(int(secondes * 1000 * LENTEUR))


def _cliche(page, chemin: Path) -> None:
    page.mouse.move(TAILLE["width"] - 1, TAILLE["height"] - 1)  # ni survol ni focus : infobulles hors de l'image
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(300)
    page.screenshot(path=str(chemin))


def _titre(code: str, fichier: str) -> str:
    return next(t[0] for _, _, _, ts in demo_vault.DEMO[code]["projets"] for f, t in ts.items() if f == fichier)


def test_captures_et_video(navigateur, demo, tmp_path):
    code, d = demo.code, demo_vault.DEMO[demo.code]
    sortie = Path(SORTIE or tmp_path)
    sortie.mkdir(parents=True, exist_ok=True)
    films = tmp_path / "films"
    ctx = navigateur.new_context(viewport=TAILLE, locale=code, record_video_dir=str(films), record_video_size=TAILLE)
    ctx.add_init_script("try{localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")  # INV-DISCUSSION-1 : disposition complète
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        page.goto(demo.url + "/")
        page.wait_for_selector(f"#arbre .ligne >> text={d['projets'][0][1]}", timeout=20000)
        deplier_tout(page)
        _pause(page, 2)
        for fichier in ("calendrier", "relances", "csv"):  # trois agents au travail pendant qu'on regarde
            r = page.request.post(f"{demo.url}/api/taches/{fichier}/messages", data={"texte": demo_vault.message_de(code, fichier)}, headers=H)
            assert r.ok, r.text()
            _pause(page, 0.6)
        situation = d["scenes"]["calendrier"][2]["situation"]
        expect(page.locator(".casc-corps", has_text=situation)).to_be_visible(timeout=20000)
        expect(page.locator(".casc-corps", has_text=d["scenes"]["relances"][2]["situation"])).to_be_visible(timeout=20000)
        _pause(page, 2.5)
        _cliche(page, sortie / f"arbre-{code}.png")

        page.locator("#arbre .ligne .titre", has_text=_titre(code, "accueil")).first.click()
        expect(page.locator(".d-titre")).to_have_text(_titre(code, "accueil"))
        _pause(page, 1.5)
        page.locator(".composer textarea").press_sequentially(d["message"], delay=35 * LENTEUR)
        page.press(".composer textarea", "Control+Enter")
        expect(page.locator(".msg.agent.final")).to_be_visible(timeout=20000)
        _pause(page, 3)
        page.locator(".notes-ajout textarea").press_sequentially(d["note"], delay=35 * LENTEUR)
        page.press(".notes-ajout textarea", "Control+Enter")
        expect(page.locator(".note-t")).to_contain_text(d["note"])
        _pause(page, 2)
        _cliche(page, sortie / f"tache-{code}.png")

        page.click("#btn-travaux")  # INV-DEROULANT-1 : l'aperçu déroule, « Tout voir » mène à la page
        page.click("#panneau-travaux [data-tout-voir]")
        carte = page.locator("[data-id=travaux] [data-id=tr-tour][data-tache=csv]")
        expect(carte.locator("[data-id=tr-sous-agent]")).to_have_count(2, timeout=10000)
        _pause(page, 3)
        _cliche(page, sortie / f"travaux-{code}.png")

        page.goto(demo.url + "/#g")
        page.wait_for_selector(".g-canvas[data-stable='1']", timeout=20000)
        _pause(page, 1.5)
        boite = page.locator(".g-canvas").bounding_box()
        page.mouse.move(boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2)
        for _ in range(6):  # recul à la molette : tout le graphe dans le cadre
            page.mouse.wheel(0, 100)
            page.wait_for_timeout(250)
        _pause(page, 2)
        _cliche(page, sortie / f"graphe-{code}.png")
        assert not erreurs, erreurs
    finally:
        page.request.post(f"{demo.url}/api/taches/csv/arret", headers=H)
        ctx.close()
    shutil.move(page.video.path(), sortie / f"demo-{code}.webm")
