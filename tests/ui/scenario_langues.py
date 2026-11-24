"""Scénario « langues » (INV-LANGUE-1) : en anglais, allemand et espagnol, aucun texte visible ne reste en français.

Rôle : serveur dédié (mode avancé, petit vault neutre), bascule de la langue par Réglages → Affichage (mémorisée
dans `config.toml`, `[interface] langue`), puis parcours des écrans principaux : accueil, arbre, tâche (et renommage du titre), Réglages
(groupes dépliés, « Signaler »), Décisions, Équipe, Notes, Aujourd'hui, En cours, volet « manager », guide « ? » (celui de la langue).
Fuite = valeur française de `fr.json`, différente de sa traduction, retrouvée dans le texte visible ; on écarte les
valeurs communes aux deux langues, les noms propres et les contenus du vault de test.
Option hors porte : `GB_CAPTURES_LANGUES=<dossier>` écrit l'accueil et une tâche dans les quatre langues (8 PNG).
Frontières : serveur et vault temporaires, harnais factice ; n'écrit jamais dans le dépôt ni le vrai vault.
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect

import univers
from aides_arbre import deplier_tout
from conftest import demarrer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from orchestrateur.equipe import EXEMPLES  # noqa: E402

RACINE = Path(__file__).resolve().parents[2]
DICOS = RACINE / "web" / "langues"
INVARIABLES = {"GoldenBrain", "Telegram", "Claude", "Codex", "Markdown", "Guide", "Notes", "Version"}

# Contenu du vault de démonstration : titres neutres, aucune donnée personnelle (INV-PUB-1).
PROJETS = {
    "C1-Orion": ("Orion", {
        "maquette": ("Orion website mockup", "en-cours", "priorite: haute\nharnais: faux\n"),
        "export": ("Orion CSV export", "a-faire", "echeance: 2026-12-04\n"),
        "tests": ("Orion unit tests", "fait", ""),
    }),
    "C2-Vega": ("Vega", {
        "devis": ("Vega quotes", "a-faire", "executant: humain\necheance: 2026-11-28\n"),
        "accord": ("Vega approval", "retour-humain", "harnais: faux\n"),
    }),
}
NOTE = ("Ressources/orion-palette.md", "Orion palette", "Blue, grey. See [[Projets/C1-Orion/taches/maquette|mockup]].")
# Ce que joue le harnais factice (texte et fiche de l'agent) : contenu, pas interface.
AGENT = ["je lis le dossier", "Travail fait.", "lu le dossier", "en bonne voie", "rien", "relire", "lire", "Read: dossier",
         "bonjour s-faux", "Bonjour"]
# Personas d'exemple : données écrites dans le dossier de l'équipe au premier démarrage, contenu de l'utilisateur.
CONTENUS = [t for _, (n, ts) in PROJETS.items() for t in [n] + [x[0] for x in ts.values()]] + [NOTE[1], NOTE[2], "mockup"] + AGENT \
    + [x for i, p in EXEMPLES.items() for x in (i, p["nom"], ", ".join(p.get("mots", [])))]


def _vault(vault: Path) -> None:
    for dossier, (nom, taches) in PROJETS.items():
        univers.ecrire(vault, f"Projets/{dossier}/contexte.md",
                       f"---\ntype: contexte\ncasquette: {dossier.split('-')[0]}-Pro\nnom: {nom}\n---\n")
        for f, (titre, statut, extra) in taches.items():
            univers.ecrire(vault, f"Projets/{dossier}/taches/{f}.md", univers.tache(titre, statut, extra))
    univers.ecrire(vault, NOTE[0], f"---\ntype: ressource\ntags: [demo]\n---\n\n# {NOTE[1]}\n\n{NOTE[2]}\n")


@pytest.fixture(scope="module")
def srv(tmp_path_factory, navigateur):
    construire = univers.construire

    def construire_neutre(dossier, port, telegram_api=""):
        config = construire(dossier, port, telegram_api)
        vault = dossier / "vault"
        for d in ("Projets", "_meta"):  # l'univers commun porte des titres français : ici, seul le vault neutre
            shutil.rmtree(vault / d, ignore_errors=True)
        _vault(vault)
        # Le harnais factice ne lance rien ; nommer une commande qui existe évite « indisponible » à l'écran.
        config.write_text(config.read_text(encoding="utf-8").replace(
            "[harnais.faux]\n", f'[harnais.faux]\ncommande = "{Path(sys.executable).as_posix()}"\n'), encoding="utf-8")
        return config

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(univers, "construire", construire_neutre)
        for s in demarrer(tmp_path_factory.mktemp("ui-langues"), '\n[interface]\nmode = "avance"\n'):
            _un_tour(navigateur, s.url)
            yield s


def _un_tour(navigateur, url: str) -> None:
    """Un tour factice terminé : la tâche montre conversation et fiche, Décisions une validation à trancher."""
    ctx = navigateur.new_context(locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")  # INV-DISCUSSION-1 : disposition complète
    page = ctx.new_page()
    try:
        page.goto(url + "/#t=maquette")
        page.fill(".composer textarea", "Bonjour")
        page.press(".composer textarea", "Control+Enter")
        expect(page.locator(".msg.agent.final")).to_be_visible(timeout=20000)
    finally:
        ctx.close()


def _motifs(code: str) -> list[tuple[str, re.Pattern]]:
    """(clé, motif) des valeurs françaises qui ne devraient pas paraître dans la langue `code`."""
    fr = json.loads((DICOS / "fr.json").read_text(encoding="utf-8"))
    cible = json.loads((DICOS / f"{code}.json").read_text(encoding="utf-8"))
    communes = set(cible.values())
    motifs = []
    for cle, v in fr.items():
        if cible.get(cle) == v or v in communes or v in INVARIABLES:
            continue
        morceaux = [m.strip() for m in re.split(r"\{\w+\}", v)]
        if sum(len(re.findall(r"[^\W\d_]", m)) for m in morceaux) < 4:
            continue  # ponctuation, unités, sigles : rien de français à reconnaître
        corps = r"[^\n]{0,120}?".join(re.escape(m) for m in morceaux if m)
        motifs.append((cle, re.compile(rf"(?<!\w){corps}(?!\w)")))
    return motifs


def _texte(page) -> str:
    # Le code cité (identifiants, clés de configuration, statuts du vault) ne se traduit jamais : écarté.
    texte, codes = page.evaluate("""() => [document.body.innerText + '\\n' + [...document.querySelectorAll('input[placeholder], textarea[placeholder]')]
        .filter((e) => e.offsetParent).map((e) => e.placeholder).join('\\n'),
        [...document.querySelectorAll('code, pre, kbd')].map((e) => e.innerText).filter(Boolean)]""")
    for c in sorted({c.strip() for c in CONTENUS + codes} - {""}, key=len, reverse=True):
        texte = texte.replace(c, " ")
    return texte


def _fuites(page, motifs, ecran: str) -> list[str]:
    texte = _texte(page)
    return [f"{ecran} : « {m.group(0)} » ({cle})" for cle, motif in motifs if (m := motif.search(texte))]


def _choisir_langue(page, url: str, code: str, config: Path) -> None:
    page.goto(url + "/#reglages/langue")
    choix = page.locator('select[data-id="langue"]')
    expect(choix).to_be_visible()
    if page.evaluate("document.documentElement.lang") != code:
        with page.expect_navigation():
            choix.select_option(code)
    page.wait_for_function("(c) => document.documentElement.lang === c", arg=code)
    assert re.search(rf'^langue\s*=\s*"{code}"', config.read_text(encoding="utf-8"), re.M)


def _ecran(page, url: str, hachure: str, attendu: str) -> None:
    page.goto("about:blank")
    page.goto(url + "/" + hachure)
    page.wait_for_selector(attendu)
    page.wait_for_selector("#arbre .ligne")


def _cliche(page, chemin: Path) -> None:
    page.mouse.move(1365, 767)  # ni survol ni infobulle sur l'image
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(300)
    page.screenshot(path=str(chemin))


def _dico(code: str) -> dict:
    return json.loads((DICOS / f"{code}.json").read_text(encoding="utf-8"))


def _renommer(page, url: str, code: str, motifs) -> list[str]:
    """INV-RENOMMER-1 : infobulle, champ, refus du titre vide et renommage, dans la langue ; titre rétabli ensuite."""
    d, titre = _dico(code), page.locator("[data-id=titre-tache]")
    expect(titre).to_have_attribute("title", d["renommer.aide"])
    titre.click()
    champ = page.locator("[data-id=titre-champ]")
    expect(champ).to_have_attribute("aria-label", d["renommer.champ"])
    champ.fill("")
    champ.press("Enter")
    expect(page.get_by_text(d["renommer.vide"])).to_be_visible()
    fuites = _fuites(page, motifs, "renommer")
    champ.fill(f"Orion website mockup {code}")
    champ.press("Enter")
    expect(page.locator("[data-id=titre-tache]")).to_contain_text(f"Orion website mockup {code}")
    r = page.request.post(url + "/api/taches/maquette/renommer", headers={"X-Orchestrateur": "1"},
                          data={"titre": "Orion website mockup"})
    assert r.ok, r.text()
    return fuites


def _parcours(page, url: str, code: str) -> list[str]:
    motifs = _motifs(code)
    fuites = []
    _ecran(page, url, "", ".casc-titre")
    deplier_tout(page)
    fuites += _fuites(page, motifs, "accueil et arbre")
    _ecran(page, url, "#t=maquette", ".d-titre")
    fuites += _fuites(page, motifs, "tâche")
    fuites += _renommer(page, url, code, motifs)
    _ecran(page, url, "#reglages", ".reglages")
    page.evaluate("document.querySelectorAll('details').forEach((d) => { d.open = true; })")
    expect(page.locator("[data-id=signaler-anomalie]")).to_have_text(_dico(code)["signaler.anomalie"])  # INV-SIGNAL-1
    fuites += _fuites(page, motifs, "Réglages")
    for hachure, attendu, nom in (("#decisions", ".decisions", "Décisions"), ("#equipe", ".equipe", "Équipe"),
                                  ("#aujourdhui", ".aujourdhui", "Aujourd'hui"), ("#en-cours", "[data-id=travaux]", "En cours"),
                                  (f"#n={NOTE[0]}", ".vue-note .d-titre", "note")):
        _ecran(page, url, hachure, attendu)
        fuites += _fuites(page, motifs, nom)
    page.locator("#onglet-notes").click()
    page.wait_for_selector("#notes-arbre [role=treeitem], #notes-arbre .ligne")
    fuites += _fuites(page, motifs, "Notes")
    page.locator("#btn-manager").click()  # volet « manager » (INV-MANAGER-1) : fil vide, aide et saisie
    page.wait_for_selector("#volet-manager .mgr-aide")
    fuites += _fuites(page, motifs, "Manager")
    page.locator("#btn-manager").click()
    expect(page.locator("#volet-manager")).to_be_hidden()
    page.locator("#btn-guide").click()
    page.wait_for_selector(".guide-corps .guide-section")
    titre = re.search(r"^## (.+?)(?:\s*\{#[\w-]+\})?$", (RACINE / "docs" / f"GUIDE.{code}.md").read_text(encoding="utf-8"), re.M)[1]
    expect(page.locator(".guide-corps")).to_contain_text(titre)  # le guide de la langue, pas le français
    fuites += _fuites(page, motifs, "guide")
    return fuites


@pytest.mark.parametrize("code", ["en", "de", "es"])
def test_aucun_francais_visible(navigateur, srv, code):
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")  # INV-DISCUSSION-1 : disposition complète
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    try:
        _choisir_langue(page, srv.url, code, srv.config)
        fuites = _parcours(page, srv.url, code)
        assert not fuites, "\n".join(fuites)
        assert not erreurs, erreurs
    finally:
        ctx.close()


@pytest.mark.skipif(not os.environ.get("GB_CAPTURES_LANGUES"), reason="captures hors porte : GB_CAPTURES_LANGUES=<dossier>")
def test_captures_quatre_langues(navigateur, srv):
    sortie = Path(os.environ["GB_CAPTURES_LANGUES"])
    sortie.mkdir(parents=True, exist_ok=True)
    ctx = navigateur.new_context(viewport={"width": 1366, "height": 768}, locale="fr-FR")
    ctx.add_init_script("try{localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")  # INV-DISCUSSION-1 : disposition complète
    page = ctx.new_page()
    try:
        for code in ("fr", "en", "de", "es"):
            _choisir_langue(page, srv.url, code, srv.config)
            _ecran(page, srv.url, "", ".casc-titre")
            deplier_tout(page)
            _cliche(page, sortie / f"accueil-{code}.png")
            _ecran(page, srv.url, "#t=maquette", ".d-titre")
            _cliche(page, sortie / f"tache-{code}.png")
    finally:
        ctx.close()
