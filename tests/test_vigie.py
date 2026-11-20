"""Signe de vie des tours (INV-VIGIE-1, INV-VIGIE-2) : phrase d'activité, raison d'attente, silence
détecté sur un harnais factice muet, diagnostic d'un enfant bloquant simulé, gestes humains,
exploration prolongée. Aucune sonde système réelle : processus et horloge simulés."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from orchestrateur import api, diagnostic, liens, poste_ram, vigie
from orchestrateur.diagnostic import Processus, analyser, descendants
from orchestrateur.harnais import Evenement
from orchestrateur.vault import Conflit, Invalide
from orchestrateur.vigie import Vigie, phrase_outil, phrase_texte
from test_simultanes import laisser, lent, moteur, poste  # noqa: F401 (fixtures)

H = {"X-Orchestrateur": "1"}
DIAG = {"disponible": True, "phrase": "en attente de la réponse du modèle", "cpu_pct": 0.0,
        "bloquant": None, "enfants": []}


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def vigie_de(m, horloge, arret=lambda pid: True):
    sondes = []

    def sonde(pid):
        sondes.append(pid)
        return dict(DIAG)
    v = Vigie(m, horloge=horloge, sonde=sonde, arret=arret)
    v.sondes = sondes
    return v


# --- phrase d'activité --------------------------------------------------------------------
@pytest.mark.parametrize("outil, attendu", [
    ("Write: C:/exemple/projet/build.py", "écrit build.py"),
    ("Read: /tmp/dossier/notes.md", "lit notes.md"),
    ("Grep: facture", "cherche facture"),
    ("Bash: pytest -x -q", "lance les tests"),
    ("Bash: git push origin x", "publie ses modifications en ligne"),
    ("Bash: ls -la", "lance ls -la"),
    ("mcp__claude_ai_Gmail__search_threads: facture", "cherche dans Gmail"),
    ("command_execution: git status", "lance git status"),
    ("OutilInconnu", "utilise OutilInconnu"),
])
def test_phrase_outil_traduit_l_outil_en_francais_lisible(outil, attendu):
    assert phrase_outil(outil) == attendu


def test_phrase_texte_prend_la_premiere_phrase_du_dernier_paragraphe():
    texte = "Contexte lu.\n\n**Je reconstruis** chaque ticket en une page. Puis je vérifie."
    assert phrase_texte(texte) == "Je reconstruis chaque ticket en une page."
    assert len(phrase_texte("x" * 400)) == 161


def test_phrase_d_activite_du_tour_texte_puis_repli_sur_l_outil(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        v = vigie_de(m, Horloge())
        m.soumettre("mere", "travaille")
        await laisser()
        v.noter({"type": "tour_outil", "tache": "mere", "texte": "Write: C:/x/build.py"})
        assert v.vue("mere")["phrase"] == "écrit build.py"  # à défaut de message
        v.noter({"type": "tour_texte", "tache": "mere", "texte": "Je génère les PDF."})
        vue = v.vue("mere")
        assert vue["phrase"] == "Je génère les PDF." and vue["etape"] == "écrit build.py"
        assert vue["depuis"] and not vue["silencieux"]
        assert v.vue("enfant") is None  # hors tour
        await m.fermer()
    asyncio.run(scenario())


# --- silence -------------------------------------------------------------------------------
def test_silence_detecte_sur_un_harnais_muet_puis_diagnostique_et_publie(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        h = Horloge()
        v = vigie_de(m, h)
        q = m.abonner()
        m.soumettre("mere", "travaille")  # le harnais n'émet rien après sa session
        await laisser()
        await v.veiller_une_fois()
        assert not v.vue("mere")["silencieux"] and not v.sondes
        h.t += config.vigie.silence_s + 1
        await v.veiller_une_fois()
        vue = v.vue("mere")
        assert vue["silencieux"] and vue["silence_s"] > config.vigie.silence_s
        assert vue["diagnostic"]["phrase"] == "en attente de la réponse du modèle"
        assert v.sondes == [m.tours["mere"].harnais._proc.pid]
        assert [a["tache"] for a in v.alertes()] == ["mere"]
        evts = [q.get_nowait()["type"] for _ in range(q.qsize())]
        assert "vigie" in evts
        assert m.etat_de("mere") == "en_cours" and not lent.arrets  # INV-VIGIE-1 : rien d'arrêté
        v.noter({"type": "tour_outil", "tache": "mere", "texte": "Read: x"})
        assert not v.vue("mere")["silencieux"]  # un signe de vie lève l'alerte
        await m.fermer()
    asyncio.run(scenario())


def test_attendre_tait_l_alerte_pour_un_nouveau_delai(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        h = Horloge()
        v = vigie_de(m, h)
        m.soumettre("mere", "travaille")
        await laisser()
        v.vue("mere")  # le signe naît à la première lecture
        h.t += config.vigie.silence_s + 1
        assert v.vue("mere")["silencieux"]
        v.attendre("mere")
        assert not v.vue("mere")["silencieux"]
        h.t += config.vigie.silence_s + 1
        assert v.vue("mere")["silencieux"]
        with pytest.raises(Conflit):
            v.attendre("enfant")
        await m.fermer()
    asyncio.run(scenario())


def test_tour_en_pause_ram_n_est_pas_silencieux(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        h = Horloge()
        v = vigie_de(m, h)
        m.soumettre("mere", "travaille")
        await laisser()
        v.vue("mere")
        poste.occuper(90)
        m._sem.veiller_une_fois()  # RAM au-dessus du plafond : pause
        assert m._sem.en_pause("mere")
        h.t += config.vigie.silence_s + 1
        assert not v.vue("mere")["silencieux"]
        await m.fermer()
    asyncio.run(scenario())


# --- diagnostic d'un enfant bloquant simulé --------------------------------------------------
RACINE = Processus(100, 1, "claude.exe", "claude -p", 10_000.0)
MCP = Processus(101, 100, "node.exe", "node serveur-mcp.js", 10_002.0)
CONSOLE = Processus(102, 100, "conhost.exe", "conhost", 10_300.0)


def test_diagnostic_nomme_le_hook_bloquant_et_sa_duree():
    hook = Processus(103, 100, "bash.exe",
                     '"C:\\Program Files\\Git\\bin\\bash.exe" C:/exemple/.claude/hooks/import-checker.sh', 10_060.0)
    sous = Processus(104, 103, "grep.exe", "grep -r x", 10_500.0)
    d = analyser(RACINE.debut, [MCP, CONSOLE, hook, sous], 0.0, 10_600.0)
    assert d["phrase"] == "bloqué par un script de contrôle : import-checker.sh, 9 min"
    assert d["bloquant"]["pid"] == 103 and d["bloquant"]["hook"]
    assert {e["pid"] for e in d["enfants"]} == {101, 103, 104}  # la console est écartée


def test_diagnostic_nomme_la_commande_en_cours():
    chrome = Processus(105, 100, "chrome.exe",
                       '"C:\\Program Files\\Google\\Chrome\\chrome.exe" --headless --print-to-pdf=f.pdf', 10_240.0)
    d = analyser(RACINE.debut, [MCP, chrome], 1.0, 10_600.0)
    assert d["phrase"] == "commande en cours : chrome --headless --print-to-pdf=f.pdf, 6 min"


def test_diagnostic_sans_enfant_attend_le_modele_ou_calcule():
    assert analyser(RACINE.debut, [MCP], 0.4, 10_600.0)["phrase"] == "en attente de la réponse du modèle"
    assert analyser(RACINE.debut, [MCP], 55.0, 10_600.0)["phrase"] == "l'agent calcule (processeur 55 %)"


def test_descendants_ecarte_un_identifiant_recycle():
    recycle = Processus(106, 100, "vieux.exe", "vieux", 5_000.0)  # né avant son « parent »
    assert [p.pid for p in descendants(100, [RACINE, MCP, recycle])] == [101]


def test_diagnostic_hors_windows_est_neutre(monkeypatch):
    monkeypatch.setattr(diagnostic, "processus", lambda: [])
    d = diagnostic.diagnostiquer(1234, fenetre_s=0)
    assert not d["disponible"] and d["bloquant"] is None


# --- gestes ----------------------------------------------------------------------------------
def test_arreter_un_enfant_seulement_dans_l_arbre_du_tour(config, vault, lent, poste, monkeypatch):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        arretes = []
        v = vigie_de(m, Horloge(), arret=lambda pid: arretes.append(pid) or True)
        m.soumettre("mere", "travaille")
        await laisser()
        racine = m.tours["mere"].harnais._proc.pid
        monkeypatch.setattr(poste_ram, "arbre", lambda pid: [pid, pid + 1, pid + 2])
        assert await v.arreter_enfant("mere", racine + 2) == {"arrete": racine + 2}
        for pid in (racine, 99_999):  # la racine (c'est « Arrêter le tour ») et un étranger
            with pytest.raises(Invalide):
                await v.arreter_enfant("mere", pid)
        with pytest.raises(Conflit):
            await v.arreter_enfant("enfant", racine + 1)  # aucun tour
        assert arretes == [racine + 2] and m.etat_de("mere") == "en_cours"
        await m.fermer()
    asyncio.run(scenario())


# --- exploration prolongée --------------------------------------------------------------------
def test_exploration_prolongee_signalee_puis_levee_par_une_ecriture(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        v = vigie_de(m, Horloge())
        q = m.abonner()
        m.soumettre("mere", "travaille")
        await laisser()
        for i in range(config.vigie.lectures_max):
            v.noter({"type": "tour_outil", "tache": "mere", "texte": f"Read: f{i}.py"})
            v.noter({"type": "tour_outil", "tache": "mere", "texte": "Bash: ls"})  # neutre
        assert v.vue("mere")["exploration"] and v.alertes()[0]["lectures"] == config.vigie.lectures_max
        assert "vigie" in [q.get_nowait()["type"] for _ in range(q.qsize())]
        v.noter({"type": "tour_outil", "tache": "mere", "texte": "Edit: f.py"})
        assert not v.vue("mere")["exploration"] and v.alertes() == []
        await m.fermer()
    asyncio.run(scenario())


# --- raison d'attente (INV-VIGIE-2) -------------------------------------------------------------
def test_raison_d_attente_creneaux_au_maximum_et_rang(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        config.moteur.simultanes_max = 1
        v = vigie_de(m, Horloge())
        for t in ("mere", "enfant", "petit"):
            m.soumettre(t, "travaille")
        await laisser()
        assert v.raison_attente("mere") is None  # en cours
        assert v.raison_attente("enfant") == "agents simultanés au maximum (1/1)"
        assert v.raison_attente("petit") == "en file derrière 1 séance de travail ; agents simultanés au maximum (1/1)"
        await m.fermer()
    asyncio.run(scenario())


def test_raison_d_attente_memoire_et_quota(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, plafond=80, unite="pct")
        v = vigie_de(m, Horloge())
        poste.occuper(90)
        m._sem.veiller_une_fois()
        vault.modifier("enfant", {"echec_tour": "Quota épuisé : le tour a échoué. Motif du harnais : "
                                                "usage limit. Try again at 3:14 PM."})
        m.soumettre("enfant", "travaille")
        await laisser()
        assert v.raison_attente("enfant") == ("limité par la mémoire : 1.6 Go libres, plafond atteint ; "
                                              "dernière séance de travail : quota épuisé (reprise possible : 3:14 PM)")
        await m.fermer()
    asyncio.run(scenario())


def test_raison_d_attente_prerequis(config, vault, lent, poste):
    async def scenario():
        m = moteur(config, vault, lent, poste, mode="fixe")
        v = vigie_de(m, Horloge())
        liens.lier(vault, "enfant", "prerequis", "mere")
        m.soumettre("enfant", "travaille")
        await laisser()
        assert v.raison_attente("enfant") == "en attente d'un prérequis : Mère"
        await m.fermer()
    asyncio.run(scenario())


# --- API -----------------------------------------------------------------------------------
def test_api_vigie_lit_et_enrichit_l_etat(config, vault, lent):
    from orchestrateur.moteur import Moteur
    m = Moteur(config, vault, {"faux": lent})
    with TestClient(api.creer_app(config, m), base_url="http://127.0.0.1:8399") as c:
        assert isinstance(m.vigie, vigie.Vigie)
        assert c.get("/api/taches/mere/vigie", headers=H).json() == {"signe": None, "raison_attente": None,
                                                                          "incident": None}
        d = c.get("/api/taches/mere", headers=H).json()
        assert d["signe"] is None and d["raison_attente"] is None
        assert c.get("/api/etat", headers=H).json()["alertes_vigie"] == []
        assert c.post("/api/taches/mere/vigie/attendre", headers=H).status_code == 409
        assert c.post("/api/taches/mere/vigie/arreter-enfant", json={"pid": "x"}, headers=H).status_code == 400
        assert c.get("/api/taches/inconnue/vigie", headers=H).status_code == 404
