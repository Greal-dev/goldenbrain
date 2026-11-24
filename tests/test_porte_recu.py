"""Reçu de porte (INV-PORTE-1) : la CI ne rejoue pas ce que l'intégration vient de valider, ni sur parole."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import porte  # noqa: E402


def _depot(tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    for c in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *c], cwd=d, check=True)
    (d / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=d, check=True)
    subprocess.run(["git", "commit", "-qm", "un"], cwd=d, check=True)
    return d


def _recu(tmp_path, d, **kw):
    etat = tmp_path / "etat"
    porte.ecrire_recu(etat, porte.arbre(d), "c", {"tests": "3 passed"}, kw.pop("motifs", True), **kw)
    return etat


def test_recu_valable_pour_l_arbre_exact_dispense_la_ci(tmp_path):
    d = _depot(tmp_path)
    ok, _ = porte.controler(_recu(tmp_path, d), porte.arbre(d))
    assert ok


def test_recu_d_un_autre_arbre_ne_dispense_pas_la_ci(tmp_path):
    d = _depot(tmp_path)
    etat = _recu(tmp_path, d)
    (d / "a.txt").write_text("b", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "deux"], cwd=d, check=True)
    assert not porte.controler(etat, porte.arbre(d))[0]


def test_recu_recopie_vers_un_autre_arbre_est_rejete(tmp_path):
    d = _depot(tmp_path)
    etat = _recu(tmp_path, d)
    (etat / "recus" / ("0" * 40 + ".json")).write_text(
        (etat / "recus" / f"{porte.arbre(d)}.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert not porte.controler(etat, "0" * 40)[0]


def test_recu_ecrit_a_la_main_sans_la_cle_est_rejete(tmp_path):
    d = _depot(tmp_path)
    etat = _recu(tmp_path, d)
    f = etat / "recus" / f"{porte.arbre(d)}.json"
    recu = json.loads(f.read_text(encoding="utf-8"))
    recu["resume"]["tests"] = "9999 passed"
    f.write_text(json.dumps(recu), encoding="utf-8")
    ok, motif = porte.controler(etat, porte.arbre(d))
    assert not ok and "signature" in motif


def test_recu_de_plus_de_24_h_force_un_passage_complet(tmp_path):
    d = _depot(tmp_path)
    etat = _recu(tmp_path, d, maintenant=1_000_000.0)
    assert porte.controler(etat, porte.arbre(d), maintenant=1_000_000.0 + 23 * 3600)[0]
    assert "ancien" in porte.controler(etat, porte.arbre(d), maintenant=1_000_000.0 + 25 * 3600)[1]


def test_recu_sans_motifs_personnels_ne_dispense_pas_la_ci(tmp_path):
    d = _depot(tmp_path)
    assert not porte.controler(_recu(tmp_path, d, motifs=False), porte.arbre(d))[0]


def test_porte_verte_sur_arbre_modifie_n_ecrit_aucun_recu(tmp_path, monkeypatch):
    d = _depot(tmp_path)
    (d / "a.txt").write_text("modifié", encoding="utf-8")
    monkeypatch.setattr(porte, "_passer", lambda dossier, script: (0, "3 passed"))
    etat = tmp_path / "etat"
    assert porte.lancer(d, etat) == 0
    assert not (etat / "recus").exists()


def test_porte_rouge_n_ecrit_aucun_recu(tmp_path, monkeypatch):
    d = _depot(tmp_path)
    monkeypatch.setattr(porte, "_passer", lambda dossier, script: (1, "1 failed"))
    assert porte.lancer(d, tmp_path / "etat") == 1
    assert not (tmp_path / "etat" / "recus").exists()


def test_porte_verte_sur_arbre_propre_ecrit_un_recu_verifiable(tmp_path, monkeypatch):
    d = _depot(tmp_path)
    monkeypatch.setattr(porte, "_passer", lambda dossier, script: (0, "12 passed"))
    etat = tmp_path / "etat"
    assert porte.lancer(d, etat) == 0
    assert porte.controler(etat, porte.arbre(d))[0]
