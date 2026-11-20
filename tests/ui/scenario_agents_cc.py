"""Scénario « agents de Claude Code » (INV-AGENTSCC-1) : les doublons sont regroupés dans Décisions, la
proposition se modifie, le lot est appliqué d'un geste ; rien n'est créé ni rattaché avant le geste."""

import json
import shutil

import univers
from aides_arbre import _ECRITS, nettoyer_vault  # noqa: F401  (fixture autouse)
from playwright.sync_api import expect

H = {"X-Orchestrateur": "1"}


def _job(jobs, rep, nom, session, maj, dossier, detail):
    (jobs / rep).mkdir(parents=True)
    (jobs / rep / "state.json").write_text(json.dumps({
        "name": nom, "state": "done", "cwd": dossier, "sessionId": session, "resumeSessionId": session,
        "createdAt": "2026-11-01T10:00:00.000Z", "updatedAt": maj, "detail": detail}), encoding="utf-8")


def carte(page, nom):
    return page.locator(".dc-agent", has=page.locator(".dc-titre", has_text=nom))


def test_agents_doublons_regroupes_proposition_modifiee_et_lot(page, serveur):
    jobs = serveur.vault.parent / "jobs"
    depot = serveur.vault.parent / "depot-ag"
    depot.mkdir(exist_ok=True)
    univers.ecrire(serveur.vault, "Projets/C1-AgUi/contexte.md",
                   f'---\ntype: contexte\ncasquette: C1-Pro\nnom: AgUi\ndepot: "{depot.as_posix()}"\n---\n')
    univers.ecrire(serveur.vault, "Projets/C1-AgUi/taches/ag-audit.md", univers.tache("Revue du contrat Zeta"))
    _ECRITS.append(serveur.vault / "Projets" / "C1-AgUi")
    d = str(depot)
    _job(jobs, "a1", "Revue du contrat Zeta", "s-ag1", "2026-11-10T10:00:00.000Z", r"C:\Ailleurs", "Contrat relu.")
    for i, (nom, maj) in enumerate((("Controleur Omega", "05"), ("controleur omega ⑂", "12"), ("Controleur Omega (2)", "08"))):
        _job(jobs, f"b{i}", nom, f"s-ag-o{i}", f"2026-11-{maj}T10:00:00.000Z", d, "Audit en cours.")
    try:
        page.request.get(serveur.url + "/api/agents-cc?relever=true")
        page.goto(page.url_serveur + "/#decisions")
        zeta, omega = carte(page, "Revue du contrat Zeta"), carte(page, "Omega")
        expect(zeta).to_have_count(1)
        expect(omega).to_have_count(1)  # trois sessions doublons : une seule carte
        expect(omega).to_contain_text("3 conversations")
        expect(zeta.locator("select")).to_have_value("rattacher:ag-audit")
        # Avant tout geste, rien n'est rattaché.
        assert "session" not in page.request.get(serveur.url + "/api/taches/ag-audit").json()["frontmatter"]
        # La proposition se change : « ignorer » pour Zeta, création proposée pour Omega.
        zeta.locator("select").select_option("ignorer:")
        zeta.locator(".dc-coche").check()
        omega.locator(".dc-coche").check()
        expect(page.locator("#dc-lot-agents")).to_have_text("Appliquer aux agents cochés (2)")
        page.click("#dc-lot-agents")
        expect(omega).to_have_count(0, timeout=5000)
        expect(zeta).to_have_count(0)
        creees = [f.stem for f in (serveur.vault / "Projets/C1-AgUi/taches").glob("*.md") if f.stem != "ag-audit"]
        assert len(creees) == 1
        assert page.request.get(serveur.url + f"/api/taches/{creees[0]}").json()["frontmatter"]["session"] == "s-ag-o1"
        assert "session" not in page.request.get(serveur.url + "/api/taches/ag-audit").json()["frontmatter"]
        assert not page.erreurs, page.erreurs
    finally:
        shutil.rmtree(jobs, ignore_errors=True)
        page.request.get(serveur.url + "/api/agents-cc?relever=true")
