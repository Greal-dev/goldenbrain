"""Exécuteurs distants (INV-DISTANT-1, 2, 3, 4) : jetons et refus sans jeton, annonce,
répartition, épinglage, conversation qui ne change pas de PC, perte et retour d'un exécuteur,
vault par l'API seulement. Le faux exécuteur tourne dans ce processus, harnais factice, et parle
au chef par son API (transport ASGI) : aucun réseau, aucun vrai harnais."""

import ast
import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import PORT, ecrire, scenario_ok, tache_md
from orchestrateur import api, executeur, executeurs
from orchestrateur.config import ConfigExecuteurs
from orchestrateur.harnais import Evenement
from orchestrateur.moteur import Envoi, Moteur

H = {"X-Orchestrateur": "1"}
LOCAL = f"http://127.0.0.1:{PORT}"
ECOUTE = "100.64.0.5"
DEPOT = "https://github.com/exemple/depot.git"


async def finir(m):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)
    await asyncio.sleep(0)


async def jusqua(cond, delai=5.0):
    for _ in range(int(delai / 0.02)):
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition jamais atteinte")


class Banc:
    """Chef (moteur + API) et faux exécuteurs reliés par transport ASGI."""

    def __init__(self, config, vault, faux, tmp_path, monkeypatch):
        monkeypatch.setattr(executeurs.Executeurs, "origine", lambda self, ident: DEPOT)
        self.m = Moteur(config, vault, {"faux": faux})
        self.app = api.creer_app(config, self.m)
        self.tmp, self.gits, self.taches = tmp_path, [], []
        self.jeton = self.m.executeurs.creer_jeton("pc2")

    def executeur(self, faux, jeton=None):
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=LOCAL)
        jeton = jeton or self.jeton

        async def http(methode, chemin, corps=None, delai=40):
            r = await client.request(methode, chemin, json=corps,
                                     headers={**H, "X-Orch-Jeton": jeton}, timeout=delai)
            return r.status_code, (r.json() if r.content else None)

        def git(*args):
            self.gits.append(args)
            if args[0] == "clone":
                Path(args[-1], ".git").mkdir(parents=True)

        e = executeur.Executeur(LOCAL, jeton, self.tmp / "depots", 1, http=http,
                                harnais={"faux": faux}, disponibles=["faux"], git=git)
        return e

    def lancer(self, e):
        t = asyncio.ensure_future(e.tourner())
        self.taches.append(t)
        return t

    async def couper(self, t):
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)

    async def fermer(self):
        for t in self.taches:
            await self.couper(t)


@pytest.fixture
def banc(config, vault, faux, tmp_path, monkeypatch):
    return Banc(config, vault, faux, tmp_path, monkeypatch)


# --- INV-DISTANT-1 : écoute, jetons, refus ---------------------------------------------------

def test_jamais_toutes_les_interfaces():
    for adresse in ("0.0.0.0", "::", "*"):
        with pytest.raises(ValueError):
            ConfigExecuteurs(ecoute=adresse)
    assert ConfigExecuteurs().ecoute == ""  # par défaut : boucle locale seule


def test_jeton_hache_persiste_puis_revoque(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    jeton = m.executeurs.creer_jeton("pc2")
    brut = (config.donnees / "etat" / "executeurs.json").read_text(encoding="utf-8")
    assert jeton not in brut and executeurs.empreinte(jeton) in brut
    assert Moteur(config, vault, {"faux": faux}).executeurs.identifier(jeton) == "pc2"
    assert m.executeurs.identifier("faux-jeton") is None and m.executeurs.identifier("") is None
    with pytest.raises(Exception):
        m.executeurs.creer_jeton("chef")
    m.executeurs.revoquer("pc2")
    assert m.executeurs.identifier(jeton) is None


def test_refus_sans_jeton_sur_l_interface_distante(config, vault, faux):
    config.executeurs = ConfigExecuteurs(ecoute=ECOUTE)
    m = Moteur(config, vault, {"faux": faux})
    jeton = m.executeurs.creer_jeton("pc2")
    app = api.creer_app(config, m)
    with TestClient(app, base_url=f"http://{ECOUTE}:{PORT}") as c:
        assert c.get("/api/arbre").status_code == 401
        assert c.get("/api/arbre", headers={"X-Orch-Jeton": "mauvais"}).status_code == 401
        assert c.get("/api/arbre", headers={"X-Orch-Jeton": jeton}).status_code == 200
        # les jetons se gèrent au poste du chef, et l'exécuteur n'a que l'API
        r = c.post("/api/executeurs/jetons", json={"nom": "pc3"}, headers={**H, "X-Orch-Jeton": jeton})
        assert r.status_code == 401
        assert c.get("/", headers={"X-Orch-Jeton": jeton}).status_code == 401
    with TestClient(app, base_url=LOCAL) as c:
        assert c.get("/api/arbre").status_code == 200  # le poste lui-même reste sans jeton
        assert c.post("/api/executeurs/annonce", json={}, headers=H).status_code == 401
        r = c.post("/api/executeurs/jetons", json={"nom": "pc3"}, headers=H)
        assert r.status_code == 200 and m.executeurs.identifier(r.json()["jeton"]) == "pc3"
        assert c.delete("/api/executeurs/jetons/pc3", headers=H).status_code == 200


# --- annonce et répartition (INV-DISTANT-2) --------------------------------------------------

def test_annonce_puis_vue_des_pc_connectes(banc):
    async def essai():
        e = banc.executeur(banc.m.registre["faux"])
        await e.annoncer()
        vue = banc.m.executeurs.public()
        assert vue[0]["nom"] == "pc2" and vue[0]["connecte"] and vue[0]["harnais"] == ["faux"]
        assert vue[0]["places"] == 1 and "libre" in vue[0]["memoire"]
    asyncio.run(essai())


def test_repartition_chef_d_abord_puis_executeur_avec_place(banc, vault, monkeypatch):
    reg = banc.m.executeurs
    envoi = Envoi("go")

    async def essai():
        assert reg.placer("mere", envoi) == ""  # aucun exécuteur connu
        reg.annoncer("pc2", {"harnais": ["faux"], "memoire": {"libre": 8}, "places": 1})
        assert reg.placer("mere", envoi) == ""  # le chef a de la place
        monkeypatch.setattr(banc.m._sem, "peut_demarrer", lambda: False)
        assert reg.placer("mere", envoi) == "pc2"  # le chef est plein
        assert reg.placer("mere", Envoi("x", role="revue")) == ""  # tour de rôle : chef
        ecrire(vault.racine, "Projets/C1-Alpha/taches/lourde.md", tache_md(extra="vault: intensif\n"))
        assert reg.placer("lourde", envoi) == ""
        reg.lieux["autre"] = "pc2"  # sa place est prise
        assert reg.placer("mere", envoi) == ""
    asyncio.run(essai())


def test_harnais_absent_de_l_executeur_echoue_avant_lancement(banc):
    reg = banc.m.executeurs
    reg.annoncer("pc2", {"harnais": ["codex"]})
    reg.lieux["mere"] = "pc2"
    with pytest.raises(Exception, match="absent de l'ordinateur d'appoint"):
        reg.envelopper("mere", "faux", object())


def test_epinglage_conversation_et_vault_par_l_api(banc, vault, faux):
    ecrire(vault.racine, "Projets/C1-Alpha/taches/mere.md",
           tache_md(extra="executeur: pc2\n", titre="Mère"))

    async def essai():
        banc.lancer(banc.executeur(faux))
        banc.m.soumettre("mere", "go")
        await finir(banc.m)
        # la session, la fiche et le journal sont tenus par le chef
        t = vault.tache("mere")
        assert t.fm.get("session") == "s-1" and banc.m.executeurs.nes["mere"] == "pc2"
        assert t.fiche["fait"] == "lu le dossier"
        # sans épinglage, la conversation reste sur le PC où elle est née
        ecrire(vault.racine, "Projets/C1-Alpha/taches/mere.md",
               tache_md(extra="session: s-1\n", titre="Mère"))
        banc.m.soumettre("mere", "suite")
        await finir(banc.m)
        await banc.fermer()

    asyncio.run(essai())
    assert len(faux.lances) == 2 and faux.lances[1]["session"] == "s-1"
    for lance in faux.lances:
        # INV-DISTANT-3 : préambule imposé ; l'agent joint le chef par son API, jeton à l'appui
        assert lance["message"].startswith("[GoldenBrain — tu travailles sur l'exécuteur « pc2 »")
        assert lance["env"]["ORCH_URL"] == LOCAL and lance["env"]["ORCH_JETON"] == banc.jeton
    assert banc.gits[0][0] == "clone" and banc.gits[1][2] == "fetch"


def test_conversation_nee_au_chef_y_reste_meme_epinglee(banc, vault):
    ecrire(vault.racine, "Projets/C1-Alpha/taches/mere.md",
           tache_md(extra="session: s-9\nexecuteur: pc2\n", titre="Mère"))
    banc.m.executeurs.annoncer("pc2", {"harnais": ["faux"]})
    assert banc.m.executeurs.placer("mere", Envoi("go")) == ""


def test_le_client_executeur_n_importe_pas_le_vault():
    arbre = ast.parse(Path(executeur.__file__).read_text(encoding="utf-8"))
    importes = {a.name for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom) for a in n.names}
    importes |= {n.module or "" for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom)}
    assert not importes & {"vault", "moteur", "catalogue", "fiches", "depot"}


# --- perte et retour (INV-DISTANT-4) ---------------------------------------------------------

def test_executeur_perdu_puis_revenu_reprend_le_tour_une_fois(banc, vault, faux, config):
    config.executeurs.delai_perte_s = 0.3
    ecrire(vault.racine, "Projets/C1-Alpha/taches/mere.md",
           tache_md(extra="executeur: pc2\n", titre="Mère"))
    faux.scenario = [Evenement("session", session="s-1"), "attendre"]
    reg = banc.m.executeurs

    async def essai():
        premier = banc.lancer(banc.executeur(faux))
        banc.m.soumettre("mere", "go")
        await jusqua(lambda: vault.tache("mere").fm.get("session") == "s-1")
        await banc.couper(premier)  # veille, coupure : l'exécuteur disparaît sans prévenir
        await asyncio.sleep(0.4)
        vue = reg.public()[0]
        assert not vue["connecte"] and vue["tours"][0]["attente"]
        assert banc.m.etat_de("mere") == "en_cours"  # rien n'est tué pendant l'absence
        faux.scenario = scenario_ok()
        banc.lancer(banc.executeur(faux))  # il revient (redémarré)
        await finir(banc.m)
        await banc.fermer()

    asyncio.run(essai())
    assert len(faux.lances) == 2
    reprise_ = faux.lances[1]
    assert reprise_["session"] == "s-1" and "redémarrage de l'exécuteur" in reprise_["message"]
    assert vault.tache("mere").fiche["fait"] == "lu le dossier"


def test_evenements_renvoyes_non_rejoues_et_tour_inconnu_abandonne(banc):
    reg = banc.m.executeurs

    async def essai():
        t = executeurs.TourDistant("t1", "mere", "pc2", {})
        reg.tours["t1"] = t
        ev = {"n": 1, "type": "texte", "texte": "a"}
        assert reg.recevoir("pc2", "t1", [ev], False) and reg.recevoir("pc2", "t1", [ev], False)
        assert t.file.qsize() == 1
        assert not reg.recevoir("pc2", "inconnu", [ev], False)  # chef redémarré : 410
        assert reg.annoncer("pc2", {"tours": ["inconnu", "t1"]})["abandonner"] == ["inconnu"]
    asyncio.run(essai())


# --- état par PC et réparation (INV-INSTALL-4) ------------------------------------------------

class FauxAssistant:
    """Assistant factice : une étape manquante que `executer` règle si l'accord est sa commande."""

    def __init__(self):
        self.fait, self.lancees = False, []

    def plan(self):
        etat = "ok" if self.fait else "manquant"
        return [{"id": "git", "libelle": "git", "etat": etat, "genre": "outil", "optionnel": False,
                 "commande": "installer-git", "instructions": "", "attend": []},
                {"id": "gh", "libelle": "GitHub CLI", "etat": "manquant", "genre": "outil", "optionnel": True,
                 "commande": "installer-gh", "instructions": "", "attend": []}]

    def executer(self, ident, accord):
        if accord != "installer-git":
            raise ValueError("l'accord ne porte pas la commande affichée")
        self.lancees.append(ident)
        self.fait = True
        return type("R", (), {"etat": "ok", "code": 0, "repli": ""})()


def test_etat_des_prerequis_puis_reparation_sur_accord_exact(banc):
    async def essai():
        faux = FauxAssistant()
        e = banc.executeur(banc.m.registre["faux"])
        e.assistant = faux
        await e.annoncer()
        reg = banc.m.executeurs
        pc = reg.public()[0]
        assert [p["id"] for p in pc["prerequis"]] == ["git", "gh"] and pc["prerequis"][0]["etat"] == "manquant"
        with pytest.raises(Exception):
            reg.reparer("pc2", "git", "autre-commande")        # accord ≠ commande affichée
        with pytest.raises(Exception):
            reg.reparer("pc2", "inconnue", "x")
        banc.lancer(e)
        reg.reparer("pc2", "git", "installer-git")
        await jusqua(lambda: faux.lancees)
        await jusqua(lambda: reg.public()[0]["reparation"])
        pc = reg.public()[0]
        assert pc["reparation"]["etat"] == "ok" and pc["prerequis"][0]["etat"] == "ok"
        with pytest.raises(Exception):
            reg.reparer("pc2", "git", "installer-git")          # déjà fait : rien à réparer
        await banc.fermer()
    asyncio.run(essai())


def test_executeur_refuse_un_accord_qui_n_est_pas_sa_commande(banc):
    async def essai():
        faux = FauxAssistant()
        e = banc.executeur(banc.m.registre["faux"])
        e.assistant = faux
        await e.reparer({"etape": "git", "accord": "commande-quelconque"})
        assert not faux.lancees
        assert banc.m.executeurs.public()[0]["reparation"]["etat"] == "refuse"
    asyncio.run(essai())


def test_la_reparation_ne_se_demande_pas_par_l_interface_distante(config, vault, faux):
    config.executeurs.ecoute = ECOUTE
    m = Moteur(config, vault, {"faux": faux})
    jeton = m.executeurs.creer_jeton("pc2")
    with TestClient(api.creer_app(config, m), base_url=f"http://{ECOUTE}:{PORT}") as c:
        r = c.post("/api/executeurs/reparations", headers={**H, "X-Orch-Jeton": jeton},
                   json={"nom": "pc2", "etape": "git", "accord": "x"})
        assert r.status_code == 401  # réservé au poste, comme les jetons
