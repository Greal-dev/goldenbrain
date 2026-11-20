"""Assistant d'installation (INV-INSTALL-1, INV-INSTALL-2, INV-INSTALL-3, INV-DISTANT-1) : accord = commande
exacte, rien sans accord, repli en instructions si droits administrateur, clavier fermé en interface,
routes fermées à l'interface distante. Aucun vrai poste : `Systeme` est remplacé par un faux."""

import pytest
from fastapi.testclient import TestClient

from conftest import PORT
from orchestrateur import api, executeur, installation
from orchestrateur.config import ConfigExecuteurs
from orchestrateur.installation import Assistant, Systeme
from orchestrateur.moteur import Moteur

H = {"X-Orchestrateur": "1"}


class Faux(Systeme):
    def __init__(self, presents=("python", "git"), admin=True, plateforme="win32", code=0, connectes=(), sortie=()):
        self.presents, self.admin, self.pf, self.code = set(presents), admin, plateforme, code
        self.connectes, self.texte = set(connectes), sortie
        self.lances: list[tuple] = []

    @property
    def plateforme(self):
        return self.pf

    def trouver(self, binaire, chemins=(), harnais=False):
        return "/faux/" + binaire if binaire in self.presents else ""

    def version_python(self):
        return (3, 12)

    def est_admin(self):
        return self.admin

    def code_de(self, argv):
        return 0 if argv[0].split("/")[-1] in self.connectes else 1

    def lancer(self, texte, interactif, sortie):
        self.lances.append((texte, interactif))
        for ligne in self.texte:
            sortie(ligne)
        return self.code


def commande(a, ident):
    return a.ligne(ident)["commande"]


def test_rien_ne_se_lance_sans_la_commande_exacte():
    f = Faux()
    a = Assistant(f)
    for accord in ("", "oui", commande(a, "tailscale") + " && del *"):
        with pytest.raises(installation.AccordRefuse):
            a.executer("tailscale", accord)
    assert f.lances == []


def test_accord_exact_lance_la_commande_du_catalogue():
    f = Faux()
    a = Assistant(f)
    r = a.executer("tailscale", commande(a, "tailscale"))
    assert f.lances == [(commande(a, "tailscale"), False)] and r.code == 0


def test_etape_inconnue_et_etape_bloquee():
    a = Assistant(Faux())
    with pytest.raises(installation.EtapeInconnue):
        a.ligne("../rm")
    with pytest.raises(installation.EtapeInconnue):
        a.ligne("git-connexion")
    assert a.ligne("codex")["etat"] == "bloque" and a.ligne("codex")["attend"] == ["node"]
    with pytest.raises(installation.EtapeBloquee):
        a.executer("codex", commande(a, "codex"))


def test_etape_deja_en_place_ne_lance_rien():
    f = Faux()
    r = Assistant(f).executer("git", "n'importe quoi")
    assert r.etat == "ok" and f.lances == []


def test_antigravity_est_une_instruction_jamais_une_commande():
    f = Faux(presents=("git",))
    a = Assistant(f)
    ag = a.ligne("agy")
    assert ag["etat"] == "manuel" and ag["commande"] == "" and "Antigravity" in ag["instructions"]
    r = a.executer("agy", "")
    assert r.code is None and f.lances == [] and r.repli


def test_sudo_sans_droits_donne_le_repli_sans_rien_lancer():
    f = Faux(presents=("python",), admin=False, plateforme="linux")
    a = Assistant(f)
    r = a.executer("git", commande(a, "git"))
    assert f.lances == [] and r.code is None
    assert "sudo apt-get install -y git" in r.repli and "administrateur" in r.repli


def test_echec_d_une_elevation_donne_le_repli():
    f = Faux(code=1, admin=False, sortie=("Access is denied.",))
    a = Assistant(f)
    r = a.executer("tailscale", commande(a, "tailscale"))
    assert r.code == 1 and commande(a, "tailscale") in r.repli


def test_echec_ordinaire_sans_elevation_n_invente_pas_de_repli():
    f = Faux(code=1, sortie=("réseau coupé",))
    a = Assistant(f)
    r = a.executer("claude", commande(a, "claude"))
    assert r.code == 1 and r.repli == ""


def test_connexion_qui_dialogue_devient_des_instructions_en_interface():
    f = Faux(presents=("python", "git", "claude"))
    a = Assistant(f)
    ligne = a.ligne("claude-connexion")
    assert ligne["etat"] == "a_connecter" and not ligne["sans_saisie"]
    assert ligne["instructions"].startswith("Dans un terminal") and ligne["au_terminal"]
    r = a.executer("claude-connexion", ligne["commande"], interactif=False)
    assert f.lances == [] and ligne["commande"] in r.repli  # le clavier n'est pas ici : rien n'est lancé
    a.executer("claude-connexion", ligne["commande"], interactif=True)
    assert f.lances == [("claude auth login", True)]  # terminal hérité : l'utilisateur dialogue seul avec l'outil


def test_etat_de_connexion_se_lit_par_la_commande_d_etat():
    a = Assistant(Faux(presents=("python", "git", "claude", "tailscale"), connectes=("claude",)))
    assert a.ligne("claude-connexion")["etat"] == "ok"
    assert a.ligne("tailscale-connexion")["etat"] == "a_connecter"
    assert a.ligne("copilot-connexion")["etat"] == "bloque"


def test_le_catalogue_ne_contient_que_des_commandes_fixes():
    for o in installation.OUTILS:
        cmds = [*o.installer.values(), *([o.connexion] if o.connexion else [])]
        for c in cmds:
            assert "{" not in c.texte and "%s" not in c.texte  # aucune donnée externe ne s'y glisse (INV-INSTALL-1)


def test_aucun_clavier_capture_en_mode_interface(monkeypatch):
    appels = []

    class P:
        stdout = iter(())

        def wait(self):
            return 0

        def kill(self):
            pass

    def popen(*a, **k):
        appels.append(k)
        return P()

    monkeypatch.setattr(installation.subprocess, "Popen", popen)
    Systeme().lancer("echo x", False, lambda ligne: None)
    assert appels[0]["stdin"] is installation.subprocess.DEVNULL  # INV-INSTALL-2


def reponses(*lignes):
    it = iter(lignes)

    def entree(_):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None
    return entree


def test_parcours_defaut_non_puis_oui_lance():
    f = Faux()
    a, sortie = Assistant(f), []
    installation.parcours(a, [], reponses("", "", "", ""), sortie.append)
    assert f.lances == [] and any("Ce qui va être fait" in s for s in sortie)
    installation.parcours(a, [], reponses("o"), sortie.append)
    assert [t for t, _ in f.lances] == [commande(a, "tailscale")] and f.lances[0][1] is True


def test_parcours_fin_de_saisie_arrete_sans_rien_lancer():
    f = Faux()
    assert installation.parcours(Assistant(f), [], reponses(), lambda s: None) == 1 and f.lances == []


def test_parcours_verifier_ne_lance_rien_et_refuse_un_harnais_inconnu():
    f = Faux()
    assert installation.parcours(Assistant(f), ["codex"], reponses("o"), lambda s: None, verifier=True) == 0
    assert f.lances == []
    assert installation.parcours(Assistant(f), ["inconnu"], reponses(), lambda s: None) == 2


def test_selection_ajoute_les_dependances_du_harnais():
    assert "node" in installation.selection(["codex"]) and "node" not in installation.selection(["claude"])


def test_parcours_liaison_lie_verifie_et_ne_montre_pas_le_jeton(monkeypatch, tmp_path):
    fichier = tmp_path / "liaison.json"
    monkeypatch.setattr(executeur, "LIAISON", fichier)

    def lier(serveur, code):
        fichier.write_text('{"serveur": "%s", "jeton": "SECRET-123"}' % serveur, encoding="utf-8")
        return "portable"

    monkeypatch.setattr(executeur, "lier", lier)
    monkeypatch.setattr(installation, "verifier_chef", lambda s, j: j == "SECRET-123")
    sortie, depart = [], []
    r = installation.parcours_liaison("", reponses("http://100.64.0.1:8300", "ABCD-EFGH", "o"), sortie.append, lambda s: depart.append(s) or 0)
    assert r == 0 and depart == ["http://100.64.0.1:8300"] and "SECRET-123" not in "\n".join(sortie)


# --- routes -----------------------------------------------------------------------------------
@pytest.fixture
def poste(config, vault, faux, monkeypatch, tmp_path):
    f = Faux()
    monkeypatch.setattr(installation, "Systeme", lambda: f)
    monkeypatch.setattr(executeur, "LIAISON", tmp_path / "liaison.json")
    config.executeurs = ConfigExecuteurs(ecoute="100.64.0.5")
    m = Moteur(config, vault, {"faux": faux})
    app = api.creer_app(config, m)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as local, \
            TestClient(app, base_url=f"http://100.64.0.5:{PORT}") as distant:
        yield f, m, local, distant


def attendre(local):
    for _ in range(200):
        vue = local.get("/api/installation/travail").json()
        if not vue["en_cours"] and vue["resultat"] is not None:
            return vue
    raise AssertionError("l'étape ne se termine pas")


def test_route_diagnostic_et_etape_sur_accord(poste):
    f, _, local, _ = poste
    plan = {e["id"]: e for e in local.get("/api/installation").json()["etapes"]}
    assert plan["git"]["etat"] == "ok" and plan["tailscale"]["etat"] == "manquant"
    assert local.post("/api/installation/etapes/tailscale", json={"accord": "x"}, headers=H).status_code == 400
    assert f.lances == []
    ok = local.post("/api/installation/etapes/tailscale", json={"accord": plan["tailscale"]["commande"]}, headers=H)
    assert ok.status_code == 200
    assert attendre(local)["resultat"]["code"] == 0 and f.lances == [(plan["tailscale"]["commande"], False)]


def test_route_etape_inconnue_bloquee_et_garde_de_l_en_tete(poste):
    _, _, local, _ = poste
    assert local.post("/api/installation/etapes/nimporte", json={"accord": ""}, headers=H).status_code == 404
    assert local.post("/api/installation/etapes/codex", json={"accord": ""}, headers=H).status_code == 409
    assert local.post("/api/installation/etapes/tailscale", json={"accord": ""}).status_code in (400, 403)  # INV-API-1


def test_routes_fermees_a_l_interface_distante(poste):
    _, _, local, distant = poste
    jeton = local.post("/api/executeurs/jetons", json={"nom": "portable"}, headers=H).json()["jeton"]
    for methode, chemin in (("get", "/api/installation"), ("get", "/api/installation/travail"),
                            ("post", "/api/installation/etapes/tailscale"), ("post", "/api/installation/appairage")):
        r = getattr(distant, methode)(chemin, headers={**H, "X-Orch-Jeton": jeton})
        assert r.status_code in (401, 403, 404), (chemin, r.status_code)


def test_route_appairage_ne_rend_jamais_le_jeton(poste, monkeypatch):
    _, _, local, _ = poste
    monkeypatch.setattr(executeur, "lier", lambda s, c: "portable")
    monkeypatch.setattr(installation, "verifier_chef", lambda s, j: True)
    r = local.post("/api/installation/appairage", json={"serveur": "http://100.64.0.1:8300", "code": "ABCD-EFGH"}, headers=H)
    assert r.status_code == 200 and r.json() == {"nom": "portable", "relie": True}
    refus = local.post("/api/installation/appairage", json={"serveur": "ftp://x", "code": "A"}, headers=H)
    assert refus.status_code in (400, 422)
