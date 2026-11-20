"""Chargement de la configuration : fusion des écarts sur l'exemple."""

from orchestrateur.config import _fusionner


def test_config_fusionne_les_ecarts_sur_l_exemple():
    base = {"a": {"x": 1, "y": 2}, "b": 3, "c": {"z": [1]}}
    assert _fusionner(base, {"a": {"y": 9}, "c": {"z": []}, "d": 4}) == {
        "a": {"x": 1, "y": 9}, "b": 3, "c": {"z": []}, "d": 4}
    assert base["a"]["y"] == 2  # la base n'est pas modifiée


def test_racine_du_vault_en_tilde_designe_le_dossier_personnel(tmp_path):
    from pathlib import Path

    from orchestrateur.config import charger
    (tmp_path / "config.toml").write_text('[vault]\nracine = "~/Vault"\ntaches = []\n', "utf-8")
    assert charger(tmp_path / "config.toml").vault.racine == Path.home() / "Vault"  # INV-PUB-1
