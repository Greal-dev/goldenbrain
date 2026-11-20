"""Moteurs par tâche : clé `modele`, changement de harnais (sessions.json, préambule, retour),
INV-MOTEUR-1, consigne non native, dérivation refusée, `GET /harnais`, conversation relue dans
les journaux, surcharge harnais/modèle à l'envoi."""

import asyncio
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from orchestrateur import api, fiches, sessions
from orchestrateur.harnais import Evenement, codex
from orchestrateur.harnais.codex import HarnaisCodex
from orchestrateur.moteur import Moteur
from conftest import scenario_ok

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}
DONNEES = Path(__file__).parent / "donnees"


def sous_classe(faux, **attrs):
    return type("Faux2", (faux,), {"lances": [], "arrets": [], **attrs})


async def finir(m: Moteur):
    while any(not b.done() for b in m.boucles.values()):
        await asyncio.gather(*m.boucles.values(), return_exceptions=True)


def tourner(m: Moteur, ident: str, texte: str = "go", **kw):
    async def scenario():
        m.soumettre(ident, texte, **kw)
        await finir(m)
    asyncio.run(scenario())


# --- clé gérée `modele` ------------------------------------------------------------------
def test_modele_ecrit_puis_retire_reste_octet_pour_octet():
    texte = "---\r\ntype: tache  # garde\r\nstatut: a-faire\r\ninconnue: [x,  y]\r\n---\r\ncorps\r\n"
    pose = fiches.modifier_cles(texte, {"modele": "opus"})
    assert pose == texte.replace("---\r\ncorps", "modele: opus\r\n---\r\ncorps")
    change = fiches.modifier_cles(pose, {"modele": "openai/gpt-6"})
    assert "modele: openai/gpt-6\r\n" in change
    assert fiches.modifier_cles(change, {"modele": None}) == texte


# --- modèle et consigne -------------------------------------------------------------------
def test_modele_passe_au_harnais_et_conversation_continue(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    m.changer_moteur("mere", modele="opus")
    assert vault.tache("mere").fm["modele"] == "opus"
    tourner(m, "mere")
    m.changer_moteur("mere", modele="sonnet")  # même harnais : la session reste
    tourner(m, "mere")
    assert [(x["modele"], x["session"]) for x in faux.lances] == [("opus", None), ("sonnet", "s-1")]
    m.changer_moteur("mere", modele="")
    assert "modele" not in vault.tache("mere").fm


def test_consigne_non_native_en_tete_du_premier_message_seulement(config, vault, faux):
    sans = sous_classe(faux, consigne_native=False)
    m = Moteur(config, vault, {"faux": sans})
    tourner(m, "mere", "premier")
    tourner(m, "mere", "second")
    premier, second = (x["message"] for x in sans.lances)
    assert premier.startswith("Tâche Mère (") and premier.endswith("\n\npremier")
    assert second == "second"


def test_consigne_native_jamais_dans_le_message(config, vault, faux):
    m = Moteur(config, vault, {"faux": faux})
    tourner(m, "mere", "premier")
    assert faux.lances[0]["message"] == "premier"


# --- changement de harnais ----------------------------------------------------------------
def test_changement_de_harnais_memoire_preambule_et_retour(config, vault, faux):
    autre = sous_classe(faux, scenario=scenario_ok("s-2"))
    m = Moteur(config, vault, {"faux": faux, "autre": autre})
    tourner(m, "mere", "un")
    m.changer_moteur("mere", modele="opus")
    m.changer_moteur("mere", harnais="autre")
    fm = vault.tache("mere").fm
    assert fm["harnais"] == "autre" and "session" not in fm and "modele" not in fm
    memoire = json.loads((config.donnees / "etat" / "sessions.json").read_text("utf-8"))
    assert memoire == {"mere": {"faux": "s-1"}}
    tourner(m, "mere", "deux")
    msg = autre.lances[0]["message"]
    chemin = vault.tache("mere").chemin
    assert msg == (f"[Reprise de la tâche dans autre. Lis sa fiche : {chemin}. Conversation "
                   f"précédente (faux) : non disponible.]\n\ndeux")
    assert autre.lances[0]["session"] is None and vault.tache("mere").fm["session"] == "s-2"
    tourner(m, "mere", "trois")  # second tour dans le nouveau harnais : pas de préambule
    assert autre.lances[1]["message"] == "trois"
    m.changer_moteur("mere", harnais="faux")  # retour : l'ancienne session est reprise
    assert vault.tache("mere").fm["session"] == "s-1"
    tourner(m, "mere", "quatre")
    assert faux.lances[-1]["session"] == "s-1" and faux.lances[-1]["message"] == "quatre"
    assert Moteur(config, vault, {"faux": faux}).sessions.session("mere", "autre") == "s-2"


def test_preambule_cite_le_transcript_de_l_ancien_harnais(config, vault, faux):
    avec = sous_classe(faux, chemin_transcript=lambda self, s: f"C:/t/{s}.jsonl")
    autre = sous_classe(faux, consigne_native=False)
    m = Moteur(config, vault, {"faux": avec, "autre": autre})
    tourner(m, "mere")
    m.changer_moteur("mere", harnais="autre")
    tourner(m, "mere", "suite")
    msg = autre.lances[0]["message"]
    assert msg.startswith("Tâche Mère (")  # la consigne d'abord, puis le préambule
    assert "Conversation précédente (faux) : C:/t/s-1.jsonl.]\n\nsuite" in msg


def test_harnais_inconnu_dans_la_fiche_bloque_sans_rien_lancer(config, vault, faux, racine):
    m = Moteur(config, vault, {"faux": faux})
    vault.modifier("mere", {"harnais": "fantome"})
    q = m.abonner()
    tourner(m, "mere")
    assert faux.lances == [] and vault.tache("mere").statut == "bloque"
    fin = [e for e in iter_q(q) if e["type"] == "tour_fin"]
    assert "harnais inconnu : fantome" in fin[0]["erreur"]


def test_harnais_indisponible_bloque_sans_repli(config, vault, faux):
    config.harnais["codex"] = {"commande": "introuvable-orch-xyz"}
    m = Moteur(config, vault, {"faux": faux, "codex": HarnaisCodex})
    m.changer_moteur("mere", harnais="codex")
    q = m.abonner()
    tourner(m, "mere")
    assert faux.lances == [] and vault.tache("mere").statut == "bloque"
    erreurs = [e.get("erreur", "") for e in iter_q(q) if e["type"] == "tour_fin"]
    assert "exécutable introuvable" in erreurs[0]


def iter_q(q):
    while not q.empty():
        yield q.get_nowait()


def test_changement_refuse_pendant_un_tour_et_valeurs_invalides(config, vault, faux):
    faux.scenario = [Evenement("session", session="s-1"), "attendre"]

    async def scenario():
        m = Moteur(config, vault, {"faux": faux})
        m.soumettre("mere", "x")
        while m.etat_de("mere") != "en_cours" or not faux.lances:
            await asyncio.sleep(0.01)
        try:
            m.changer_moteur("mere", modele="opus")
        except Exception as e:
            code = e.code
        await m.arreter("mere")
        await finir(m)
        return m, code

    m, code = asyncio.run(scenario())
    assert code == 409
    for kw in ({"harnais": "fantome"}, {"modele": "-x"}, {"modele": "a b"}):
        try:
            m.changer_moteur("mere", **kw)
            raise AssertionError(kw)
        except Exception as e:
            assert getattr(e, "code", None) == 400


def test_derivation_refusee_si_le_harnais_ne_sait_pas_deriver(config, vault, faux):
    sans = sous_classe(faux, sait_deriver=False)
    m = Moteur(config, vault, {"faux": sans})
    vault.modifier("mere", {"session": "orig"})
    try:
        m.deriver("mere", "Fille", "enfant", True)
        raise AssertionError("409 attendu")
    except Exception as e:
        assert e.code == 409 and "ne sait pas dériver" in str(e)
    assert m.deriver("mere", "Fille", "enfant", False)  # sans fil : permis


# --- journaux et conversation reconstruite ------------------------------------------------
def test_relire_journaux_d_un_flux_codex_reel(tmp_path):
    jour = tmp_path / "journal" / "2026-11-13"
    jour.mkdir(parents=True)
    lignes = (DONNEES / "codex-derive-outil.jsonl").read_text("utf-8").splitlines()
    tete = json.dumps({"type": "orch_message", "texte": "fais", "de": "", "harnais": "codex",
                       "date": "2026-11-13T11:00:00"})
    (jour / "t-110000.jsonl").write_text("\n".join([tete, lignes[0], lignes[0], *lignes[1:]]),
                                         encoding="utf-8")
    (jour / "t-b-110000.jsonl").write_text(tete, encoding="utf-8")  # autre tâche : ignorée
    msgs = sessions.relire_journaux(tmp_path, "t", 200, {"codex": HarnaisCodex})
    assert [(x.role, x.texte, len(x.outils)) for x in msgs] == [
        ("utilisateur", "fais", 0), ("assistant", "J’exécute `echo salut`.\n\nok", 1)]
    assert msgs[0].horodatage == "2026-11-13T11:00:00"
    assert sessions.relire_journaux(tmp_path / "rien", "t", 10, {}) == []


def client_pour(config, vault, registre):
    return TestClient(api.creer_app(config, Moteur(config, vault, registre)), base_url=BASE)


def attendre(c, ident):
    import time
    for _ in range(300):
        if c.get(f"/api/taches/{ident}").json()["etat_execution"] == "inactif":
            return
        time.sleep(0.01)
    raise AssertionError("tour non terminé")


def test_conversation_reconstruite_quand_transcript_absent(config, vault, faux):
    def transcript(self, session, limite):
        raise NotImplementedError

    sans = sous_classe(faux, transcript=transcript)
    with client_pour(config, vault, {"faux": sans}) as c:
        assert c.post("/api/taches/mere/messages", headers=H, json={"texte": "fais"}).status_code == 202
        attendre(c, "mere")
        conv = c.get("/api/taches/mere/conversation").json()
    assert [(x["role"], x["texte"], x["outils"]) for x in conv] == [
        ("utilisateur", "fais", []), ("assistant", "je lis", ["Read: x"])]


# --- API ---------------------------------------------------------------------------------
class FauxAuto:
    nom = "auto"
    appels = 0

    def __init__(self, conf):
        pass

    def decouvrir_modeles(self):
        type(self).appels += 1
        return ["p/m1", "p/m2"]


def test_get_harnais_liste_auto_en_cache_et_executable_absent(config, vault, faux):
    config.harnais = {"faux": {"commande": sys.executable, "modeles": ["opus", "sonnet"]},
                      "auto": {"commande": sys.executable, "modeles": "auto"},
                      "absent": {"commande": "introuvable-orch-xyz", "modeles": "auto"}}
    with client_pour(config, vault, {"faux": faux, "auto": FauxAuto, "absent": FauxAuto}) as c:
        premiere = c.get("/api/harnais").json()
        seconde = c.get("/api/harnais").json()
    assert premiere == seconde
    par_nom = {h["nom"]: h for h in premiere}
    assert par_nom["faux"] == {"nom": "faux", "disponible": True, "motif": "",
                               "modeles": ["opus", "sonnet"], "modele_defaut": ""}
    assert par_nom["auto"]["modeles"] == ["p/m1", "p/m2"] and FauxAuto.appels == 1
    assert par_nom["absent"]["disponible"] is False and par_nom["absent"]["modeles"] == []
    assert "introuvable" in par_nom["absent"]["motif"]


def test_route_moteur_et_surcharge_a_l_envoi(config, vault, faux):
    autre = sous_classe(faux, scenario=scenario_ok("s-2"))
    with client_pour(config, vault, {"faux": faux, "autre": autre}) as c:
        r = c.post("/api/taches/mere/moteur", headers=H, json={"harnais": "faux", "modele": "opus"})
        assert r.status_code == 200 and r.json()["frontmatter"]["modele"] == "opus"
        assert c.post("/api/taches/mere/moteur", headers=H,
                      json={"harnais": "fantome"}).status_code == 400
        assert c.post("/api/taches/mere/messages", headers=H,
                      json={"texte": "x", "modele": "-x"}).status_code == 400
        r = c.post("/api/taches/mere/messages", headers=H,
                   json={"texte": "go", "harnais": "autre", "modele": "luna"})
        assert r.status_code == 202
        attendre(c, "mere")
        t = c.get("/api/taches/mere").json()
        assert t["harnais"] == "autre" and t["session"] == "s-2"
        assert t["frontmatter"]["modele"] == "luna" and autre.lances[0]["modele"] == "luna"
        r = c.post("/api/taches", headers=H, json={"titre": "Neuve", "conteneur": "Projets/C1-Alpha",
                                                    "harnais": "autre", "modele": "luna"})
        assert r.status_code == 201
        assert r.json()["frontmatter"]["modele"] == "luna" and r.json()["harnais"] == "autre"


def test_derivation_409_par_l_api(config, vault, faux):
    sans = sous_classe(faux, sait_deriver=False)
    vault.modifier("mere", {"session": "orig"})
    with client_pour(config, vault, {"faux": sans}) as c:
        r = c.post("/api/taches/mere/deriver", headers=H,
                   json={"titre": "F", "lien": "enfant", "avec_fil": True})
    assert r.status_code == 409


def test_codex_de_bout_en_bout_par_le_moteur(config, vault, monkeypatch, tmp_path):
    from test_harnais_cli import FAUX_CODEX
    script = tmp_path / "faux_codex.py"
    script.write_text(FAUX_CODEX, encoding="utf-8")
    monkeypatch.setattr(codex, "resoudre", lambda commande: [sys.executable, str(script)])
    config.harnais["codex"] = {"dossier": str(tmp_path)}
    m = Moteur(config, vault, {"codex": HarnaisCodex})
    m.changer_moteur("mere", harnais="codex", modele="gpt-6")
    tourner(m, "mere", "fais")
    t = vault.tache("mere")
    assert t.fm["session"] == "th-1" and t.statut == "bloque"  # INV-EXEC-12 : fiche absente, relancée puis bloquée
    situation = json.loads(fiches.lire_fiche(fiches.lire(t.chemin))["situation"])
    # INV-COMPACT-1 : seuil par défaut 45 % de la fenêtre de gpt (272 000 jetons)
    assert situation["argv"] == ["exec", "--json", "-c", "model_auto_compact_token_limit=122400", "-m", "gpt-6", "-"]
    assert situation["prompt"].startswith("Tâche Mère (") and situation["prompt"].endswith("fais")
