"""Composant déroulant unique (INV-DEROULANT-1) : survol avec délai d'intention, clic, clavier, toucher, Échap, clic extérieur,
épingle, un seul ouvert à la fois, aucun saut de mise en page, feuille montante au téléphone ; puis la mesure du mode discussion :
aucune zone permanente hors barre haute, rails, conversation (en-tête compris) et alertes exigeant un geste.
Vault temporaire, harnais factice.
"""
import pytest
from playwright.sync_api import expect

import univers
from conftest import demarrer

BOUTON, PANNEAU = "#btn-aujourdhui", "#panneau-aujourdhui"

# Zones permises en mode discussion ; tout autre élément visible et non vide est une « zone permanente » de trop.
MESURE = """() => {
  const permis = ['#bandeau .b-haut', '#volet-gauche', '.volet-t-notes', '.volet-t-conv', '.d-tete', '#bandeaux > [role=alert]']; // .d-tete : en-tête d'une ligne de la conversation
  const dans = (el) => permis.some((s) => el.closest(s));
  const contient = (el) => permis.some((s) => el.querySelector(s));
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (dans(el) || contient(el)) continue;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || cs.visibility === 'hidden' || +cs.opacity === 0) continue;
    if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) continue;
    out.push(`${el.tagName}#${el.id}.${[...el.classList].join('.')} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return out;
}"""


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("deroulant"), '\n[interface]\nmode = "avance"\n'):
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/causerie.md", univers.tache("Causer avec l'agent", "en-cours"))
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/urgente.md", univers.tache("Urgente du jour", "a-faire", "echeance: 2020-01-01\n"))
        yield s


def ouvrir(navigateur, srv, chemin="/", w=1366, h=768, toucher=False, discussion=False):
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR", has_touch=toucher)
    ctx.add_init_script("try{localStorage.setItem('gb.disposition-vu','1')}catch(e){}")  # bulle de premier usage : éphémère, hors mesure
    if not discussion:
        ctx.add_init_script("try{localStorage.setItem('gb.disposition','{\"tout\":true}')}catch(e){}")
    p = ctx.new_page()
    p.erreurs = []
    p.on("pageerror", lambda e: p.erreurs.append(str(e)))
    p.goto(srv.url + chemin)
    p.wait_for_selector("#bandeau .b-haut", state="visible", timeout=90000)
    p.wait_for_function("() => document.querySelector('#volet-gauche .ligne, .composer textarea')", timeout=90000)  # arbre ou fiche dessinés
    p.wait_for_timeout(500)
    return ctx, p


def test_survol_delai_d_intention_et_aucun_saut(navigateur, srv):
    ctx, p = ouvrir(navigateur, srv)
    # Chronométré dans la page : la mesure ne dépend pas de la lenteur du pilote de test.
    p.evaluate("""([b, s]) => { window.__t = {}; document.querySelector(b).addEventListener('pointerenter', () => { window.__t.entree = performance.now() });
      new MutationObserver(() => { if (!document.querySelector(s).hidden && !window.__t.ouvert) window.__t.ouvert = performance.now() })
        .observe(document.querySelector(s), { attributes: true }); }""", [BOUTON, PANNEAU])
    avant = p.evaluate("() => JSON.stringify(document.querySelector('#corps').getBoundingClientRect())")
    p.hover(BOUTON)
    expect(p.locator(PANNEAU)).to_be_visible(timeout=3000)
    delai = p.evaluate("() => window.__t.ouvert - window.__t.entree")
    assert delai >= 140, f"ouvert {delai:.0f} ms après l'entrée : pas de délai d'intention"
    assert p.evaluate("() => JSON.stringify(document.querySelector('#corps').getBoundingClientRect())") == avant, "le déroulant pousse le contenu"
    expect(p.locator(f"{PANNEAU} .apercu-liste li")).to_have_count(1, timeout=5000)
    p.mouse.move(700, 700)
    expect(p.locator(PANNEAU)).to_be_hidden(timeout=3000)
    assert not p.erreurs, p.erreurs
    ctx.close()


def test_passage_bref_n_ouvre_rien(navigateur, srv):
    ctx, p = ouvrir(navigateur, srv)
    box = p.locator(BOUTON).bounding_box()
    p.evaluate("""([b]) => { const el = document.querySelector(b);
      el.dispatchEvent(new PointerEvent('pointerenter', { pointerType: 'mouse' }));
      setTimeout(() => el.dispatchEvent(new PointerEvent('pointerleave', { pointerType: 'mouse' })), 40); }""", [BOUTON])
    p.wait_for_timeout(600)
    assert box and p.locator(PANNEAU).is_hidden(), "un passage de 40 ms a ouvert le déroulant"
    ctx.close()


def test_clic_echap_clic_exterieur_et_un_seul_ouvert(navigateur, srv):
    ctx, p = ouvrir(navigateur, srv)
    p.click(BOUTON)
    expect(p.locator(PANNEAU)).to_be_visible()
    expect(p.locator(BOUTON)).to_have_attribute("aria-expanded", "true")
    p.mouse.move(700, 700)
    p.wait_for_timeout(600)
    expect(p.locator(PANNEAU)).to_be_visible()  # ouvert au clic : la sortie du curseur ne le ferme pas
    p.keyboard.press("Escape")
    expect(p.locator(PANNEAU)).to_be_hidden()
    p.click(BOUTON)
    expect(p.locator(PANNEAU)).to_be_visible()
    p.click("#btn-decisions")  # un seul déroulant ouvert à la fois
    expect(p.locator("#panneau-decisions")).to_be_visible()
    expect(p.locator(PANNEAU)).to_be_hidden()
    p.mouse.click(700, 600)  # clic extérieur
    expect(p.locator("#panneau-decisions")).to_be_hidden()
    p.click(BOUTON)
    p.click(f"{PANNEAU} [data-tout-voir]")  # « Tout voir » mène à la page pleine
    expect(p.locator(PANNEAU)).to_be_hidden()
    expect(p.locator(BOUTON)).to_have_attribute("aria-pressed", "true")
    ctx.close()


def test_epingle_resiste_au_clic_exterieur(navigateur, srv):
    ctx, p = ouvrir(navigateur, srv)
    p.click(BOUTON)
    pin = p.locator(f"{PANNEAU} .der-epingle")
    pin.click()
    expect(pin).to_have_attribute("aria-pressed", "true")
    p.mouse.click(700, 600)
    p.keyboard.press("Escape")  # le focus n'est pas dans le panneau : l'épinglé reste
    expect(p.locator(PANNEAU)).to_be_visible()
    pin.click()
    p.mouse.click(700, 600)
    expect(p.locator(PANNEAU)).to_be_hidden()
    ctx.close()


def test_clavier_focus_dans_le_panneau_puis_retour(navigateur, srv):
    ctx, p = ouvrir(navigateur, srv)
    p.focus(BOUTON)
    p.keyboard.press("Enter")
    expect(p.locator(PANNEAU)).to_be_visible()
    p.wait_for_function(f"() => document.querySelector('{PANNEAU}').contains(document.activeElement)")
    p.keyboard.press("Escape")
    expect(p.locator(PANNEAU)).to_be_hidden()
    assert p.evaluate(f"() => document.activeElement === document.querySelector('{BOUTON}')"), "le focus ne revient pas à la pastille"
    ctx.close()


def test_toucher_au_telephone_feuille_du_bas(navigateur, srv):
    """Au téléphone, les pastilles de la barre se taisent ; « Détails » de la fiche est le déroulant joignable : il monte du bas."""
    ctx, p = ouvrir(navigateur, srv, "/#t=causerie", w=390, h=844, toucher=True)
    bouton, panneau = '[data-id="details-bascule"]', '[data-id="details"]'
    p.wait_for_selector(bouton, state="visible", timeout=90000)
    p.tap(bouton)
    expect(p.locator(panneau)).to_be_visible()
    r = p.evaluate(f"""() => {{ const r = document.querySelector('{panneau}').getBoundingClientRect(); return [r.left, r.right, r.bottom, innerWidth, innerHeight] }}""")
    assert r[0] == 0 and abs(r[1] - r[3]) < 1 and abs(r[2] - r[4]) < 1, f"pas une feuille du bas : {r}"
    p.tap(bouton)  # toucher = clic : retoucher referme
    expect(p.locator(panneau)).to_be_hidden()
    ctx.close()


def test_mode_discussion_aucune_zone_permanente(navigateur, srv):
    ctx, p = ouvrir(navigateur, srv, "/#t=causerie", discussion=True)
    p.wait_for_selector("body.discussion .composer textarea", timeout=90000)
    p.wait_for_timeout(1500)
    trop = p.evaluate(MESURE)
    print("\nZONES HORS BARRE, RAILS ET CONVERSATION :", trop)
    assert trop == [], f"zones permanentes en mode discussion : {trop}"
    h = p.evaluate("() => document.querySelector('#bandeau .b-haut').getBoundingClientRect().height")
    assert h <= 48, f"barre haute de {h:.0f} px : plus d'une rangée"
    ctx.close()
