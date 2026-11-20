"""Écran « En cours » (INV-TRAVAUX-1, INV-TRAVAUX-2) : sous-agents et avancement lus dans le flux
des harnais (Claude Code, OpenCode, Codex), tenus par la vigie, exposés par `GET /api/travaux` ;
pause et reprise à la main. Harnais factice, aucun processus réel."""

import asyncio

from fastapi.testclient import TestClient

from orchestrateur import api
from orchestrateur.harnais import suivi
from orchestrateur.moteur import Moteur
from orchestrateur.vigie import SOUS_AGENTS_MAX, Vigie
from test_simultanes import laisser, lent, moteur, poste  # noqa: F401 (fixtures)

H = {"X-Orchestrateur": "1"}


def _suivis(evs):
    return [e.suivi for e in evs]


# --- lecture du flux ----------------------------------------------------------------------
def test_claude_sous_agent_lance_puis_revenu_et_liste_d_etapes():
    ouverts: set = set()
    lancement = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Task",
         "input": {"description": "Relire le module", "subagent_type": "Explore", "prompt": "…"}},
        {"type": "tool_use", "id": "t2", "name": "TodoWrite", "input": {"todos": [
            {"content": "a", "status": "completed"}, {"content": "b", "status": "in_progress"}]}}]}}
    assert _suivis(suivi.claude(lancement, ouverts)) == [
        {"sous_agent": {"id": "t1", "description": "Relire le module", "genre": "Explore"}},
        {"avancement": {"fait": 1, "total": 2}}]
    retour = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": False},
        {"type": "tool_result", "tool_use_id": "t9"}]}}  # outil ordinaire : ignoré
    assert _suivis(suivi.claude(retour, ouverts)) == [
        {"sous_agent": {"id": "t1", "fin": True, "erreur": False}}]
    assert ouverts == set()


def test_claude_liste_d_etapes_d_un_sous_agent_ne_change_pas_l_avancement():
    ligne = {"type": "assistant", "parent_tool_use_id": "t1", "message": {"content": [
        {"type": "tool_use", "id": "x", "name": "TodoWrite", "input": {"todos": [{"status": "completed"}]}}]}}
    assert suivi.claude(ligne, set()) == []
    assert suivi.claude({"type": "assistant", "message": "illisible"}, set()) == []


def test_opencode_tache_terminee_et_codex_liste():
    part = {"tool": "task", "callID": "c1", "state": {"status": "completed",
                                                      "input": {"description": "Chercher", "prompt": "p"}}}
    assert _suivis(suivi.opencode(part)) == [
        {"sous_agent": {"id": "c1", "description": "Chercher", "genre": ""}},
        {"sous_agent": {"id": "c1", "fin": True, "erreur": False}}]
    item = {"type": "todo_list", "items": [{"text": "a", "completed": True}, {"text": "b", "completed": False}]}
    assert _suivis(suivi.codex(item)) == [{"avancement": {"fait": 1, "total": 2}}]
    assert suivi.codex({"type": "todo_list", "items": []}) == []


# --- vigie --------------------------------------------------------------------------------
def test_vigie_tient_sous_agents_avancement_et_fichiers_bornes(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        v = Vigie(m, horloge=lambda: 1000.0, sonde=lambda pid: {}, arret=lambda pid: True)
        m.soumettre("mere", "travaille")
        await laisser()
        noter = lambda **d: v.noter({"type": "suivi", "tache": "mere", **d})  # noqa: E731
        noter(sous_agent={"id": "a", "description": "Relire", "genre": "Explore"})
        noter(sous_agent={"id": "a", "fin": True, "erreur": True})
        noter(avancement={"fait": 2, "total": 5})
        v.noter({"type": "tour_outil", "tache": "mere", "texte": "Write: /x/a.py"})
        v.noter({"type": "tour_outil", "tache": "mere", "texte": "Edit: /x/a.py"})
        vue = v.vue("mere")
        sa = vue["sous_agents"][0]
        assert sa["description"] == "Relire" and sa["fin"] and sa["erreur"]
        assert vue["avancement"] == {"fait": 2, "total": 5} and vue["fichiers"] == 1
        for i in range(SOUS_AGENTS_MAX + 5):
            noter(sous_agent={"id": f"n{i}", "description": str(i)})
        ids = [s["id"] for s in v.vue("mere")["sous_agents"]]
        assert len(ids) == SOUS_AGENTS_MAX and "a" not in ids  # le fini part d'abord
        await m.fermer()
    asyncio.run(scenario())


# --- API ----------------------------------------------------------------------------------
def test_api_travaux_liste_tours_file_et_pause(config, vault, lent, poste):
    config.moteur.simultanes_max = 1
    m = Moteur(config, vault, {"faux": lent})
    m._sem.poste = poste
    with TestClient(api.creer_app(config, m), base_url="http://127.0.0.1:8399") as c:
        vide = c.get("/api/travaux", headers=H).json()
        assert vide["tours"] == [] and vide["file"] == [] and "routines" in vide and "incidents" in vide
        for t in ("mere", "enfant"):
            assert c.post(f"/api/taches/{t}/messages", json={"texte": "go"}, headers=H).status_code < 300
        d = c.get("/api/travaux", headers=H).json()
        tour = d["tours"][0]
        assert tour["tache"] == "mere" and tour["harnais"] and "projet" in tour and tour["signe"]
        assert [f["tache"] for f in d["file"]] == ["enfant"] and "raison" in d["file"][0]
        assert c.post("/api/taches/mere/suspendre", headers=H).status_code == 200
        assert c.get("/api/travaux", headers=H).json()["tours"][0]["signe"]["pause_manuelle"]
        assert c.post("/api/taches/mere/suspendre", headers=H).status_code == 409
        assert c.post("/api/taches/mere/continuer", headers=H).status_code == 200
        assert c.post("/api/taches/enfant/continuer", headers=H).status_code == 409
        assert c.post("/api/taches/mere/arret", headers=H).status_code < 300
