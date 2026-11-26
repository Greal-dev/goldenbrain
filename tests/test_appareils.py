"""Accès distant des appareils (INV-DISTANT-5, 6, 7, 8) : appairage par code QR à usage unique,
jeton d'appareil, refus 401 sans jeton (API et SSE), révocation, Origin et Host, gestes à
risque, routes réservées au poste, journal, et jamais d'écoute sur toutes les interfaces.
Les requêtes « distantes » arrivent par le client de test sur l'adresse d'écoute posée."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import PORT
from orchestrateur import __main__ as principal
from orchestrateur import api, api_appareils, appareils, qr
from orchestrateur.appairage import TropDEssais
from orchestrateur.config import ConfigDistant, ConfigExecuteurs
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide

H = {"X-Orchestrateur": "1"}
ECOUTE = "100.64.0.5"
DISTANT = f"http://{ECOUTE}:{PORT}"
LOCAL = f"http://127.0.0.1:{PORT}"


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def poste(config, vault, faux):
    config.executeurs = ConfigExecuteurs(ecoute=ECOUTE)
    config.distant = ConfigDistant(appareils=True)
    m = Moteur(config, vault, {"faux": faux})
    return api.creer_app(config, m)


def appairer(app, nom="Mon téléphone") -> TestClient:
    """Ouvre un code au poste, l'échange depuis le téléphone ; rend le client du téléphone."""
    with TestClient(app, base_url=LOCAL) as c:
        r = c.post("/api/appareils/appairage", json={"nom": nom}, headers=H)
        assert r.status_code == 200, r.text
        assert r.json()["lien"].startswith(f"{DISTANT}/appairer.html#") and "<svg" in r.json()["qr"]
        code = r.json()["code"]
    tel = TestClient(app, base_url=DISTANT)
    r = tel.post("/api/appareils/echange", json={"code": code}, headers=H)
    assert r.status_code == 200 and r.json()["nom"] == nom
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "secure" not in cookie
    return tel


# --- INV-DISTANT-6 : refus sans jeton, accès local inchangé ---------------------------------

def test_requete_distante_sans_jeton_refusee_api_sse_et_pages(poste):
    with TestClient(poste, base_url=f"http://autre-nom:{PORT}") as c:
        assert c.get("/api/arbre").status_code == 403  # hôte inconnu (INV-API-1)
    with TestClient(poste, base_url=DISTANT) as c:
        for chemin in ("/api/arbre", "/api/evenements", "/", "/index.html"):
            assert c.get(chemin).status_code == 401, chemin
        c.cookies.set(api_appareils.COOKIE, "jeton-invente")
        assert c.get("/api/arbre").status_code == 401
        assert c.get("/appairer.html").status_code == 200  # la page d'appairage reste servie
    with TestClient(poste, base_url=LOCAL) as c:
        assert c.get("/api/arbre").status_code == 200  # la boucle locale ne change pas


def test_appareil_appaire_passe_puis_revoque_refuse(poste):
    tel = appairer(poste)
    assert tel.get("/api/arbre").status_code == 200
    assert tel.get("/").status_code == 200
    with TestClient(poste, base_url=LOCAL) as c:
        vue = c.get("/api/appareils").json()
        assert [a["nom"] for a in vue["appareils"]] == ["Mon téléphone"]
        assert "empreinte" not in vue["appareils"][0]
        assert c.delete(f"/api/appareils/{vue['appareils'][0]['id']}", headers=H).status_code == 200
        genres = [e["genre"] for e in c.get("/api/appareils").json()["journal"]]
        assert genres[0] == "révocation" and "appairage" in genres  # INV-DISTANT-8
    assert tel.get("/api/arbre").status_code == 401
    assert tel.get("/api/evenements").status_code == 401


def test_flux_sse_ouvert_se_ferme_a_la_revocation():
    a = {"nom": "t", "revoque": False}

    class Requete:
        class state:
            appareil = a
    assert not api_appareils.revoque(Requete)
    a["revoque"] = True
    assert api_appareils.revoque(Requete)


def test_desactive_par_defaut_tout_refuse(config, vault, faux):
    config.executeurs = ConfigExecuteurs(ecoute=ECOUTE)
    assert config.distant.appareils is False
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=DISTANT) as c:
        assert c.get("/appairer.html").status_code == 401
        assert c.post("/api/appareils/echange", json={"code": "x"}, headers=H).status_code == 401
    with TestClient(app, base_url=LOCAL) as c:
        assert c.post("/api/appareils/appairage", json={}, headers=H).status_code == 400


def test_jeton_stocke_hache_et_relu(config, poste):
    tel = appairer(poste)
    jeton = tel.cookies.get(api_appareils.COOKIE)
    brut = (config.donnees / "etat" / "appareils.json").read_text(encoding="utf-8")
    assert jeton and jeton not in brut and len(jeton) >= 40
    assert appareils.Appareils(config.donnees).identifier(jeton)["nom"] == "Mon téléphone"


def test_cookie_secure_en_https(poste):
    with TestClient(poste, base_url=LOCAL) as c:
        code = c.post("/api/appareils/appairage", json={}, headers=H).json()["code"]
    with TestClient(poste, base_url=f"https://{ECOUTE}:{PORT}") as tel:
        r = tel.post("/api/appareils/echange", json={"code": code}, headers=H)
        assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower()


# --- INV-DISTANT-5 : code à usage unique, court, tentatives limitées -------------------------

def test_code_deja_utilise_ou_expire_refuse(tmp_path):
    h = Horloge()
    reg = appareils.Appareils(tmp_path, horloge=h)
    code = reg.ouvrir_code("a")["code"]
    reg.echanger(code, "1.2.3.4")
    with pytest.raises(Invalide):
        reg.echanger(code, "1.2.3.4")  # déjà utilisé
    code = reg.ouvrir_code("b")["code"]
    h.t += appareils.VALIDITE_S + 1
    with pytest.raises(Invalide):
        reg.echanger(code, "1.2.3.4")  # expiré


def test_tentatives_limitees_puis_verrou(tmp_path):
    h = Horloge()
    reg = appareils.Appareils(tmp_path, horloge=h)
    bon = reg.ouvrir_code("a")["code"]
    for _ in range(appareils.ECHECS_MAX):
        with pytest.raises(Invalide):
            reg.echanger("mauvais", "1.2.3.4")
    with pytest.raises(TropDEssais):
        reg.echanger(bon, "1.2.3.4")  # même le bon code attend la fin du verrou
    h.t += appareils.VERROU_S + 1
    assert reg.echanger(bon, "1.2.3.4")[0]["nom"] == "a"
    for _ in range(appareils.CODES_MAX):
        reg.ouvrir_code("x")
    with pytest.raises(TropDEssais):
        reg.ouvrir_code("x")


def test_echange_par_http_code_reutilise_refuse(poste):
    with TestClient(poste, base_url=LOCAL) as c:
        code = c.post("/api/appareils/appairage", json={}, headers=H).json()["code"]
    with TestClient(poste, base_url=DISTANT) as tel:
        assert tel.post("/api/appareils/echange", json={"code": code}, headers=H).status_code == 200
        assert tel.post("/api/appareils/echange", json={"code": code}, headers=H).status_code == 400


# --- INV-DISTANT-7 : Origin, Host, gestes à risque, réservé au poste -------------------------

def test_origine_ou_hote_etrangers_refuses(poste):
    tel = appairer(poste)
    assert tel.get("/api/arbre", headers={"Origin": "https://malveillant.example"}).status_code == 403
    assert tel.get("/api/arbre", headers={"Origin": DISTANT}).status_code == 200
    assert tel.get("/api/arbre", headers={"Host": f"malveillant.example:{PORT}"}).status_code == 403


def test_routes_du_poste_refusees_a_l_appareil(poste):
    tel = appairer(poste)
    for methode, chemin in (("GET", "/api/appareils"), ("POST", "/api/appareils/appairage"),
                            ("GET", "/api/installation"), ("POST", "/api/executeurs/jetons"),
                            ("POST", "/api/taches/x/natif"), ("GET", "/api/taches/x/resultat"),
                            ("POST", "/api/taches/x/resultat/ouvrir")):
        assert tel.request(methode, chemin, json={}, headers=H).status_code == 403, chemin


def test_gestes_a_risque_interdits_par_defaut(poste):
    tel = appairer(poste)
    assert tel.post("/api/redemarrer", headers=H).status_code == 403
    assert tel.post("/api/taches/x/arret", headers=H).status_code == 403
    assert tel.delete("/api/taches/x", headers=H).status_code == 403


def test_gestes_a_risque_confirmes(config, vault, faux):
    config.executeurs = ConfigExecuteurs(ecoute=ECOUTE)
    config.distant = ConfigDistant(appareils=True, gestes="confirmer")
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    tel = appairer(app)
    assert tel.post("/api/taches/x/arret", headers=H).status_code == 428
    r = tel.post("/api/taches/x/arret", headers={**H, "X-Orch-Confirmation": "1"})
    assert r.status_code not in (401, 403, 428)  # la garde laisse passer ; la route juge


# --- configuration et écoute (INV-DISTANT-1, 7) ----------------------------------------------

def test_jamais_d_ecoute_sur_toutes_les_interfaces(config):
    # revue du 2026-11-18 : un nom ou une forme abrégée échappait à la garde (adresse du socket ≠ chaîne)
    for adresse in ("0.0.0.0", "::", "*", "0", "0x0", "poste.exemple.ts.net", "224.0.0.1"):
        with pytest.raises(ValueError):
            ConfigExecuteurs(ecoute=adresse)
    assert ConfigExecuteurs(ecoute=" 100.64.0.5 ").ecoute == ECOUTE
    config.executeurs = ConfigExecuteurs(ecoute=ECOUTE)
    assert principal.adresses(config) == (["127.0.0.1", ECOUTE], [])
    config.distant = ConfigDistant(appareils=True, certificat="c.crt", cle="c.key")
    assert principal.adresses(config) == (["127.0.0.1"], [ECOUTE])
    config.executeurs = ConfigExecuteurs()
    assert principal.adresses(config) == (["127.0.0.1"], [])


def test_config_distant_validee():
    assert ConfigDistant() == ConfigDistant(appareils=False, gestes="interdire")
    for mauvais in ({"gestes": "autoriser"}, {"nom_hote": "a b"}, {"certificat": "c.crt"}):
        with pytest.raises(ValueError):
            ConfigDistant(**mauvais)


def test_journal_cumule_les_refus_repetes(tmp_path):
    h = Horloge()
    reg = appareils.Appareils(tmp_path, horloge=h)
    for _ in range(3):
        reg.noter("refus", "1.2.3.4", "/api/arbre")
    assert len(reg.journal) == 1 and reg.journal[0]["nb"] == 3


# --- code QR (INV-DISTANT-5) ------------------------------------------------------------------

def test_qr_taille_selon_la_version_et_limite():
    assert len(qr.matrice("x")) == 21
    assert len(qr.matrice("y" * 100)) == 4 * 6 + 17  # 100 octets → version 6 en correction M
    assert len(qr.matrice("z" * 213)) == 57
    with pytest.raises(ValueError):
        qr.matrice("z" * 214)
    s = qr.svg("https://exemple.test/appairer.html#abc")
    assert s.startswith("<svg") and "viewBox" in s


def test_appairer_html_lit_le_fragment():
    # Le code voyage dans le fragment : jamais dans un journal HTTP (INV-DISTANT-5).
    js = (Path(api.__file__).parents[2] / "web" / "appairer.js").read_text(encoding="utf-8")
    assert "location.hash" in js and json.dumps(api_appareils.ROUTE_ECHANGE) in js.replace("'", '"')


def test_csp_autorise_les_codes_qr_en_data():
    # Régression (intégration du 2026-11-18) : sans img-src data:, le code QR de Réglages → Appareils était bloqué.
    from orchestrateur import api
    for entetes in (api.ENTETES, api.ENTETES_FICHIER):
        assert "img-src 'self' data:" in entetes["Content-Security-Policy"]


def test_qr_png_valide():
    import struct, zlib
    p = qr.png("https://exemple.test/appairer.html#abc")
    assert p[:8] == b"\x89PNG\r\n\x1a\n"
    larg, haut = struct.unpack(">II", p[16:24])
    assert larg == haut and larg % 8 == 0
    i = p.index(b"IDAT")
    assert len(zlib.decompress(p[i + 4:p.index(b"IEND") - 8])) == haut * (larg + 1)
