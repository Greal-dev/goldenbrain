"""Ouverture d'une tâche allégée (INV-DETAIL-1, audit du 23/11) : le fil de discussion est l'objet principal.

Mesure : hauteur occupée, dans le volet de la tâche, au-dessus des messages (bas de la barre « Échanges ») ; objectif ≤ 15 % de l'écran.
Tout le reste (fiche, moteur, liens, lignes…) reste à un clic derrière « Détails », choix mémorisé. Vault temporaire, harnais factice.
"""
import pytest
from playwright.sync_api import expect

import univers
from conftest import demarrer

LANGUES = ("fr", "de", "es")
FICHE = ("\n<!-- orchestrateur:debut -->\n## Fiche\n- **Fait** : Dossier relu et corrigé de bout en bout\n- **Résultat** : livrable-dense\n"
         "- **Essai** : ouvrir le livrable et vérifier chaque section\n- **Situation** : en bonne voie, deux relectures restent à planifier\n"
         "- **Reste à faire** : relecture finale\n- **Prochain pas** : envoyer au client\n<!-- orchestrateur:fin -->\n")
MESURES = []


@pytest.fixture(scope="module", params=LANGUES)
def srv(request, tmp_path_factory):
    for s in demarrer(tmp_path_factory.mktemp("allege"), f'\n[interface]\nmode = "avance"\nlangue = "{request.param}"\n'):
        s.code = request.param
        univers.ecrire(s.vault, "Projets/C1-Alpha/taches/dense.md", univers.tache("Préparer la réponse au dossier de consultation", "en-cours", 'parent: "[[mere]]"\n') + FICHE)
        yield s


def ouvrir(navigateur, srv, w, h):
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR")
    p = ctx.new_page()
    p.goto(srv.url + "/#t=dense")
    p.wait_for_selector(".composer textarea", timeout=90000)
    p.fill(".composer textarea", "Bonjour")
    p.press(".composer textarea", "Control+Enter")
    expect(p.locator(".msg.agent.final")).to_be_visible(timeout=20000)
    p.ctx = ctx
    return p


def hauteur_avant_message(p, srv=None):
    # La pastille d'état de l'en-tête change tant que l'agent travaille et peut passer à la ligne sur mobile :
    # mesurer une fois la tâche inactive et la hauteur stable (flaky constaté en CI, 115 à 161 px).
    if srv is not None:
        for _ in range(100):
            if p.request.get(srv.url + "/api/taches/dense").json().get("etat_execution") == "inactif":
                break
            p.wait_for_timeout(200)
    mesure = "() => document.querySelector('.conv-tete').getBoundingClientRect().bottom"
    precedente = None
    for _ in range(50):
        courante = p.evaluate(mesure)
        if courante == precedente:
            break
        precedente = courante
        p.wait_for_timeout(300)
    return p.evaluate("""() => { const v = document.querySelector('#volet-droit').getBoundingClientRect(); const m = document.querySelector('.conv-tete'); return m.getBoundingClientRect().bottom - v.top }""")


@pytest.mark.parametrize("taille", [(1366, 768), (390, 844)])
def test_ouverture_de_tache_le_fil_occupe_l_essentiel_de_l_ecran(navigateur, srv, taille):
    w, h = taille
    p = ouvrir(navigateur, srv, w, h)
    haut = hauteur_avant_message(p, srv)
    MESURES.append((srv.code, taille, round(haut), round(100 * haut / h, 1)))
    print(f"MESURE {srv.code} {w}x{h} : {haut:.0f}px = {100 * haut / h:.1f} %")
    assert haut <= 0.15 * h, f"{haut:.0f} px au-dessus du premier message ({100 * haut / h:.1f} % de {h}) : objectif ≤ 15 %"
    p.ctx.close()


def test_details_a_un_clic_et_choix_memorise(navigateur, srv):
    p = ouvrir(navigateur, srv, 1366, 768)
    assert not p.is_visible('[data-id="details"]'), "les détails devraient être repliés par défaut"
    p.click('[data-id="details-bascule"]')
    for sel in ('.fiche', '.moteur select', '.d-rattache', '.d-actions', '.corps'):
        assert p.is_visible(sel), f"{sel} inaccessible après « Détails »"
    p.reload()
    p.wait_for_selector(".composer textarea")
    assert p.is_visible('[data-id="details"]'), "le choix « ouvert » n'est pas mémorisé"
    p.click('[data-id="details-bascule"]')
    p.reload()
    p.wait_for_selector(".composer textarea")
    assert not p.is_visible('[data-id="details"]'), "le choix « replié » n'est pas mémorisé"
    p.ctx.close()


def test_en_tete_une_seule_ligne_au_bureau(navigateur, srv):
    p = ouvrir(navigateur, srv, 1366, 768)
    h = p.evaluate("() => document.querySelector('.d-une').getBoundingClientRect().height")
    assert h <= 48, f"l'en-tête fait {h:.0f} px : plus d'une ligne"
    p.ctx.close()


@pytest.mark.parametrize("taille", [(1366, 768), (390, 844)])
def test_tour_en_cours_l_en_tete_ne_depasse_pas_le_budget(navigateur, srv, taille):
    """Pendant un tour (état d'exécution + Arrêter + Résultat dans l'en-tête), le haut reste ≤ 15 % — en espagnol aussi."""
    w, h = taille
    ctx = navigateur.new_context(viewport={"width": w, "height": h}, locale="fr-FR")
    p = ctx.new_page()
    p.goto(srv.url + "/#t=dense")
    p.wait_for_selector(".composer textarea", timeout=90000)
    p.fill(".composer textarea", "[lent 20] travaille longtemps")
    p.press(".composer textarea", "Control+Enter")
    expect(p.locator(".d-une .etat.en_cours")).to_be_visible(timeout=20000)
    haut = hauteur_avant_message(p)
    assert haut <= 0.15 * h, f"{srv.code} {w}x{h} tour en cours : {haut:.0f} px ({100 * haut / h:.1f} % de {h}) : objectif ≤ 15 %"
    ctx.close()
