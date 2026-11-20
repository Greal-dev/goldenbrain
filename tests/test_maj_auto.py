"""Mise à jour automatique : INV-MAJ-3 (gel, pause sûre, avance rapide, redémarrage unique, retour arrière).

Dépôts git temporaires (voir test_mise_a_jour) ; moteur, vigie et version factices : on teste la séquence.
"""

import asyncio
import datetime as dt
import json
from types import SimpleNamespace

import pytest

from orchestrateur import maj_auto
from orchestrateur.config import ConfigMiseAJour
from orchestrateur.moteur import Moteur
from orchestrateur.vault import ErreurOrch, Invalide
from test_mise_a_jour import depots, git, publier  # noqa: F401  (fixture `depots`)

C = ConfigMiseAJour()


class Sem:
    gele = False

    def geler(self): self.gele = True
    def degeler(self): self.gele = False
    def en_pause(self, ident): return ident in self.pauses
    pauses: set = set()


class Vigie:
    def __init__(self): self.silencieux, self.enfants = True, []
    def vue(self, ident): return {"silencieux": self.silencieux, "diagnostic": None}
    async def diagnostiquer(self, ident):
        return {"disponible": True, "bloquant": None, "enfants": self.enfants}


class Version:
    code_sortie, appels = 0, 0

    def redemarrer(self):
        self.appels += 1
        self.code_sortie = 3


def tour(minutes):
    return SimpleNamespace(depuis=(dt.datetime.now() - dt.timedelta(minutes=minutes)).isoformat(timespec="seconds"))


class Faux:
    """Moteur factice : ce que MajAuto lit, rien de plus."""

    def __init__(self, tmp):
        self.tours, self.envois, self.files, self.attente = {}, {}, {}, {}
        self.ferme, self._sem, self.vigie = False, Sem(), Vigie()
        self.sessions_ok = {"t1", "t2", "q"}
        outer = self
        self.vault = SimpleNamespace(
            tache=lambda i: SimpleNamespace(fm={"session": "s"} if i in outer.sessions_ok else {}),
            ouverte=lambda t: True)


def monter(tmp_path, depots, **kw):
    _, local, ailleurs = depots
    faux, version = Faux(tmp_path), Version()

    async def controle(actualiser):
        from orchestrateur import mise_a_jour
        return mise_a_jour.etat(local, C, recuperer=True)
    auto = maj_auto.MajAuto(faux, version, local, C, controle, lambda: None, tmp_path / "etat" / "maj_auto.json",
                            calme_s=0, **kw)
    auto.reglage["actif"] = True
    auto.verifier_import = lambda: None
    return auto, faux, version, local, ailleurs


def pas(auto):
    asyncio.run(auto.pas())


def test_sans_option_rien_ne_bouge(tmp_path, depots):
    auto, faux, version, local, ailleurs = monter(tmp_path, depots)
    auto.reglage["actif"] = False
    publier(ailleurs)
    pas(auto)
    assert faux._sem.gele is False and auto.phase == "veille" and version.appels == 0


def test_sequence_complete_gel_attente_avance_redemarrage_unique_puis_bandeau(tmp_path, depots):
    auto, faux, version, local, ailleurs = monter(tmp_path, depots)
    avant = git(local, "rev-parse", "HEAD")
    publier(ailleurs)
    faux.tours["t1"] = tour(2)  # un tour jeune : on l'attend
    faux.files["q"] = [object()]
    pas(auto)
    assert faux._sem.gele and auto.phase == "gel" and auto.attendus == ["t1"]
    assert git(local, "rev-parse", "HEAD") == avant and version.appels == 0  # rien n'est interrompu
    pas(auto)
    assert version.appels == 0
    faux.tours.clear()  # le tour se termine de lui-même
    pas(auto)
    assert git(local, "rev-parse", "HEAD") != avant and version.appels == 1 and auto.phase == "redemarre"
    for _ in range(3):
        pas(auto)
    assert version.appels == 1  # redémarrage unique
    assert (local / ".maj_retour").read_text(encoding="utf-8") == avant[:7]
    # Nouveau processus : bandeau avec les tâches à reprendre, retour supprimé.
    neuf = maj_auto.MajAuto(faux, Version(), local, C, None, lambda: None, tmp_path / "etat" / "maj_auto.json")

    async def lancer():
        neuf.demarrer()
        neuf.fermer()
    asyncio.run(lancer())
    b = neuf.vue()["bandeau"]
    assert b["version"] == git(local, "rev-parse", "--short", "HEAD") and b["reprises"] == 1 and ":" in b["a"]
    assert not (local / ".maj_retour").exists()
    neuf.fermer_bandeau()
    assert neuf.vue()["bandeau"] is None


@pytest.mark.parametrize("cas,attendu", [
    ("sur", True), ("jeune", False), ("actif", False), ("commande", False), ("sans_session", False), ("pause_ram", True)])
def test_tour_en_retard_pause_seulement_si_aucun_risque(tmp_path, depots, cas, attendu):
    auto, faux, *_ = monter(tmp_path, depots)
    faux.tours["t1"] = tour(2 if cas == "jeune" else 45)
    if cas == "actif":
        faux.vigie.silencieux = False
    if cas == "commande":
        faux.vigie.enfants = [{"nom": "pytest"}]
    if cas == "sans_session":
        faux.sessions_ok.discard("t1")
    if cas == "pause_ram":
        faux._sem.pauses = {"t1"}
        faux.vigie.silencieux = False
    ok, _ = asyncio.run(auto.pausable("t1"))
    assert ok is attendu
    faux._sem.pauses = set()


def test_tour_repris_sans_progres_n_est_jamais_pause(tmp_path, depots):
    auto, faux, *_ = monter(tmp_path, depots)
    faux.tours["t1"] = tour(60)
    faux.envois["t1"] = SimpleNamespace(reprise=True, progres=False)
    assert asyncio.run(auto.pausable("t1"))[0] is False


def test_pause_sure_laisse_couper_le_tour_au_redemarrage(tmp_path, depots):
    auto, faux, version, local, ailleurs = monter(tmp_path, depots)
    publier(ailleurs)
    faux.tours["t2"] = tour(45)  # en retard, silencieux, sans processus, session connue
    pas(auto)
    assert version.appels == 1
    assert auto.etat["redemarrage"]["reprises"] == ["t2"]  # sera repris dans sa session (INV-EXEC-1)


def test_tour_a_risque_en_retard_est_attendu_jamais_coupe(tmp_path, depots):
    auto, faux, version, local, ailleurs = monter(tmp_path, depots)
    publier(ailleurs)
    faux.tours["t1"] = tour(90)
    faux.vigie.enfants = [{"nom": "build"}]
    for _ in range(3):
        pas(auto)
    assert version.appels == 0 and auto.attendus == ["t1"] and faux._sem.gele


def test_echec_du_chargement_retour_a_la_version_precedente_et_une_seule_tentative(tmp_path, depots):
    auto, faux, version, local, ailleurs = monter(tmp_path, depots)
    avant = git(local, "rev-parse", "HEAD")
    publier(ailleurs)

    def casse():
        raise ErreurOrch("ImportError: module cassé")
    auto.verifier_import = casse
    pas(auto)
    assert git(local, "rev-parse", "HEAD") == avant and version.appels == 0
    assert "module cassé" in auto.vue()["incident"]["cause"] and auto.vue()["incident"]["geste"]
    assert faux._sem.gele is False and auto.phase == "veille"
    for _ in range(3):
        pas(auto)  # même version distante : jamais de boucle
    assert git(local, "rev-parse", "HEAD") == avant
    publier(ailleurs, "c.txt")  # une nouvelle version : nouvelle tentative
    auto.verifier_import = lambda: None
    pas(auto)
    assert version.appels == 1 and git(local, "rev-parse", "HEAD") != avant


def test_refus_d_avance_rapide_incident_visible_sans_retentative(tmp_path, depots):
    auto, faux, version, local, ailleurs = monter(tmp_path, depots)
    publier(ailleurs)
    (local / "a.txt").write_text("modifié à la main\n", encoding="utf-8")
    pas(auto)
    inc = auto.vue()["incident"]
    assert "modifications locales" in inc["cause"] and inc["geste"] and version.appels == 0
    assert faux._sem.gele is False


def test_hors_fenetre_ou_utilisateur_a_l_ecran_la_mise_a_jour_est_reportee(tmp_path, depots):
    auto, faux, version, local, ailleurs = monter(tmp_path, depots)
    publier(ailleurs)
    maintenant = dt.datetime(2026, 11, 18, 14, 0)
    auto.maintenant = lambda: maintenant
    auto.reglage.update(fenetre_debut="22:00", fenetre_fin="06:00")
    pas(auto)
    assert not faux._sem.gele and version.appels == 0  # en plein jour
    maintenant = dt.datetime(2026, 11, 19, 2, 0)
    auto.maintenant = lambda: maintenant
    auto.calme_s = 3600
    auto.activite()
    pas(auto)
    assert not faux._sem.gele  # la nuit, mais quelqu'un est à l'écran
    auto.calme_s = 0
    pas(auto)
    assert version.appels == 1


def test_fenetre_traversant_minuit_et_reglage_valide():
    r = {"fenetre_debut": "22:00", "fenetre_fin": "06:00"}
    assert maj_auto.dans_fenetre(r, dt.datetime(2026, 1, 1, 23, 30)) and maj_auto.dans_fenetre(r, dt.datetime(2026, 1, 1, 5, 0))
    assert not maj_auto.dans_fenetre(r, dt.datetime(2026, 1, 1, 12, 0))
    assert maj_auto.dans_fenetre({"fenetre_debut": "", "fenetre_fin": ""}, dt.datetime(2026, 1, 1, 12, 0))


def test_reglage_persiste_defauts_et_validation(tmp_path, depots):
    auto, *_ = monter(tmp_path, depots)
    assert maj_auto.REGLAGE["actif"] is False and maj_auto.REGLAGE["delai_min"] == 30
    with pytest.raises(Invalide):
        auto.regler({"delai_min": 0})
    with pytest.raises(Invalide):
        auto.regler({"fenetre_debut": "22:00"})
    auto.regler({"delai_min": 45, "fenetre_debut": "22:00", "fenetre_fin": "06:00"})
    relu = json.loads((tmp_path / "etat" / "maj_auto.json").read_text(encoding="utf-8"))
    assert relu["reglage"]["delai_min"] == 45


def test_le_gel_empeche_tout_nouveau_tour_et_se_leve(config, vault, faux):
    sem = Moteur(config, vault, {"faux": faux})._sem
    assert sem.peut_demarrer()
    sem.geler()
    assert not sem.peut_demarrer()
    sem.degeler()
    assert sem.peut_demarrer()


def test_revenir_refuse_une_empreinte_invalide(depots):
    from orchestrateur import mise_a_jour
    with pytest.raises(ErreurOrch):
        mise_a_jour.revenir(depots[1], "--hard")
