"""Ordonnancement de la file : prérequis bloquant puis libéré (INV-ORDO-1), cycle refusé, ordre
a→e et son motif, créneau donné au premier du classement, pause du moins prioritaire (INV-ORDO-2)."""

import asyncio

import pytest

from orchestrateur import liens, ordonnancement
from orchestrateur.ordonnancement import Candidat
from orchestrateur.vault import Conflit
from conftest import ecrire, tache_md
from test_simultanes import GO, laisser, lent, moteur, poste  # noqa: F401 (fixtures)

T = "Projets/C1-Alpha/taches/"


def test_prerequis_bloque_le_tour_puis_le_libere_seul(config, vault, racine, lent, poste):
    async def scenario():
        liens.lier(vault, "enfant", "prerequis", "mere")
        assert "prerequis: [mere]\n" in (racine / T / "enfant.md").read_text(encoding="utf-8")
        m = moteur(config, vault, lent, poste, mode="fixe")
        m.INTERVALLE_PREREQUIS_S = 0.01
        m.soumettre("enfant", "travaille")
        await laisser()
        assert "enfant" not in m.tours and m.etat_de("enfant") == "en_file"
        assert m.attente_prerequis("enfant") == [{"id": "mere", "titre": "Mère"}]
        assert m.etat_global()["file"][0]["attend"] == ["Mère"]
        ecrire(racine, T + "mere.md", tache_md(statut="fait", titre="Mère"))
        for _ in range(100):
            if "enfant" in m.tours:
                break
            await asyncio.sleep(0.01)
        assert "enfant" in m.tours and len(lent.lances) == 1  # parti seul, un seul tour
        await m.fermer()
    asyncio.run(scenario())


def test_cycle_de_prerequis_refuse_avec_motif_lisible(vault):
    liens.lier(vault, "enfant", "prerequis", "mere")
    liens.lier(vault, "petit", "prerequis", "enfant")
    with pytest.raises(Conflit, match="cycle"):
        liens.lier(vault, "mere", "prerequis", "petit")
    r = liens.refs(vault.index()[0], "mere")
    assert [x["id"] for x in r["requis_par"]] == ["enfant"] and r["prerequis"] == []
    liens.lier(vault, "mere", "alimente", "petit")  # « alimente » ne bloque rien : accepté


def test_ordre_a_e_et_motifs(config, racine, vault):
    ecrire(racine, T + "h.md", tache_md(extra="priorite: basse\n", titre="H"))
    ecrire(racine, T + "p.md", tache_md(extra="priorite: haute\n", titre="P"))
    ecrire(racine, T + "c.md", tache_md(titre="C"))
    ecrire(racine, T + "c1.md", tache_md(extra="prerequis: [c]\n", titre="C1"))
    ecrire(racine, T + "c2.md", tache_md(extra="prerequis: [c1]\n", titre="C2"))
    ecrire(racine, T + "e.md", tache_md(extra="echeance: 2026-12-01\n", titre="E"))
    ecrire(racine, T + "v1.md", tache_md(titre="V1"))
    ecrire(racine, T + "v2.md", tache_md(titre="V2"))
    candidats = [Candidat("v2", False, 6), Candidat("e", False, 5), Candidat("v1", False, 4),
                 Candidat("c", False, 3), Candidat("p", False, 2), Candidat("h", True, 7)]
    classe = ordonnancement.classer(vault, candidats)
    assert [(c.ident, motif) for c, motif in classe] == [
        ("h", "message d'un humain"), ("p", "priorité haute"), ("c", "débloque 2 tâches"),
        ("e", "échéance 2026-12-01"), ("v1", "ordre d'arrivée"), ("v2", "ordre d'arrivée")]


def test_creneau_libre_va_au_premier_du_classement_et_rang_affiche(
        config, vault, racine, lent, poste):
    async def scenario():
        ecrire(racine, T + "mere.md", tache_md(extra="priorite: basse\n", titre="Mère"))
        ecrire(racine, T + "petit.md", tache_md(extra="priorite: haute\n", titre="Petit"))
        m = moteur(config, vault, lent, poste, mode="fixe")
        m.config.moteur.simultanes_max = 1
        m.soumettre("x", "occupe")
        await laisser()
        m.soumettre("mere", "arrivée la première", de="x")
        m.soumettre("petit", "arrivée ensuite", de="x")
        await laisser()
        assert m.rang_file("petit") == {"rang": 1, "libelle": "1ᵉʳ", "motif": "priorité haute"}
        assert [f["tache"] for f in m.etat_global()["file"]] == ["petit", "mere"]
        await m.arreter("x")
        await laisser()
        assert "petit" in m.tours and "mere" not in m.tours
        await m.fermer()
    asyncio.run(scenario())


def test_ram_saturee_met_en_pause_le_moins_prioritaire_meme_ancien(
        config, vault, racine, lent, poste):
    async def scenario():
        ecrire(racine, T + "mere.md", tache_md(extra="priorite: basse\n", titre="Mère"))
        ecrire(racine, T + "enfant.md", tache_md(extra="priorite: haute\n", titre="Enfant"))
        m = moteur(config, vault, lent, poste, plafond=10, unite="go")
        poste.libre = 10 * GO
        m.soumettre("mere", "travaille", de="x")
        await laisser()
        m._sem.veiller_une_fois()
        m.soumettre("enfant", "travaille", de="x")
        await laisser()
        poste.libre = 4 * GO
        m._sem.veiller_une_fois()
        assert m._sem.en_pause("mere") and not m._sem.en_pause("enfant")
        await m.fermer()
    asyncio.run(scenario())
