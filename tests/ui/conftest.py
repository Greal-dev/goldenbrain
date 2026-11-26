"""Fixtures des scénarios d'interface : vrai serveur sur vault temporaire, navigateur Playwright.

Rôle : `serveur` (une instance par session pytest, port libre, vault temporaire, harnais factice),
`page` (page neuve par scénario, erreurs console collectées dans `page.erreurs`).
Frontières : jamais le vrai vault, jamais les ports 8300/8310 ; le serveur est arrêté et son dossier
supprimé à la fin. Les scénarios vivent dans `scenario_*.py` (hors porte rapide, voir README).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

import univers
from faux_telegram import FauxTelegram

SERVEUR = Path(__file__).with_name("serveur.py")


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def serveur(tmp_path_factory):
    yield from demarrer(tmp_path_factory.mktemp("ui"))


def demarrer(dossier: Path, supplement: str = "", cerveau_fait: bool = True, ttl: float = 0, avant=None, sonde_vault: bool = True):
    """Vrai serveur sur un univers neuf ; `supplement` s'ajoute à la fin de son config.toml. `cerveau_fait` : le second cerveau est
    réglé (INV-CERVEAU-1) ; faux = poste neuf, le parcours « Configurer votre second cerveau » ouvre l'interface.
    `avant(vault)` peuple le vault avant le lancement ; `sonde_vault=False` attend le serveur par `/`, sans chauffer le vault
    (mesure à froid, INV-FROID-1)."""
    port = port_libre()
    faux_tg = FauxTelegram()
    config = univers.construire(dossier, port, faux_tg.url)
    if avant:
        avant(dossier / "vault")
    if cerveau_fait:
        (dossier / "etat").mkdir(exist_ok=True)
        (dossier / "etat" / "cerveau.json").write_text('{"etat": "fait"}', encoding="utf-8")
    if ttl:
        config.write_text(config.read_text(encoding="utf-8").replace("index_ttl_s = 0", f"index_ttl_s = {ttl}", 1), encoding="utf-8")
    if supplement:
        config.write_text(config.read_text(encoding="utf-8") + supplement, encoding="utf-8")
    # Journal sur fichier, jamais sur un tuyau : un tuyau que personne ne vide se remplit (quelques Ko
    # sous Windows) et l'écriture suivante bloque le serveur, d'où les expirations en cascade de
    # `page.goto` constatées sous charge (porte d'interface, 15/11).
    journal = dossier / "serveur.log"
    sortie = journal.open("wb")
    home = dossier / "home"  # poste factice de l'accueil : jamais le vrai dossier personnel (INV-ACCUEIL-1)
    home.mkdir()
    temporaire = dossier / "temporaire"  # le dossier de travail des scénarios n'est pas « temporaire » pour l'accueil
    temporaire.mkdir()
    proc = subprocess.Popen([sys.executable, str(SERVEUR), str(config)], stdout=sortie, stderr=subprocess.STDOUT,
                            env={**{k: v for k, v in os.environ.items() if not k.startswith("ORCH_")}, "ORCH_ACCUEIL_HOME": str(home), "TMPDIR": str(temporaire), "TEMP": str(temporaire)})
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail(f"le serveur s'est arrêté : {journal.read_text('utf-8', 'replace')}")
            try:
                urllib.request.urlopen(f"{url}/api/arbre" if sonde_vault else f"{url}/", timeout=30).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("le serveur ne répond pas")
        yield type("Serveur", (), {"url": url, "port": port, "vault": dossier / "vault", "config": config,
                                   "telegram": faux_tg, "home": home, "dossier": dossier, "proc": proc})
    finally:
        faux_tg.arreter()
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        sortie.close()


@pytest.fixture(scope="session")
def navigateur():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        yield nav
        nav.close()


@pytest.fixture
def page(navigateur, serveur):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")  # INV-LANGUE-1 : sinon la langue détectée serait celle de Chromium (en-US)
    ctx.add_init_script("try{localStorage.setItem('gb.detail-ouvert','1')}catch(e){}")  # INV-DETAIL-1 : les scénarios existants visent le contenu des Détails ; la fermeture par défaut est gardée par scenario_detail_allege
    ctx.add_init_script("try{localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")  # INV-DISCUSSION-1 : les scénarios existants visent la disposition complète ; le mode discussion est gardé par scenario_discussion
    p = ctx.new_page()
    p.erreurs = []
    p.on("console", lambda m: p.erreurs.append(m.text) if m.type in ("error", "warning") else None)
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.url_serveur = serveur.url
    yield p
    ctx.close()


def deplier_infos(page, timeout: float = 5000) -> None:
    """INV-DEROULANT-1 : les bandeaux d'information vivent dans la pastille « Infos » ; la déplier et l'épingler avant de les viser
    (épinglée, elle survit aux clics ailleurs ; elle se referme d'elle-même quand plus rien n'est à dire)."""
    b = page.locator("#btn-etat")
    b.wait_for(state="visible", timeout=timeout)
    if b.get_attribute("aria-expanded") != "true":
        b.click()
    pin = page.locator("#panneau-etat .der-epingle")
    if pin.get_attribute("aria-pressed") != "true":
        pin.click()
