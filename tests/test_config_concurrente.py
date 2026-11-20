"""Écritures simultanées de sections de config.toml (INV-INTERFACE-2)."""
import threading
import tomllib

from orchestrateur.api_interface import remplacer_section
from orchestrateur.api_simultanes import ecrire_cles


def test_ecritures_simultanees_de_sections_ne_perdent_aucune_section(tmp_path):
    chemin = tmp_path / "config.toml"
    chemin.write_text("[vault]\nracine = \"x\"\n", encoding="utf-8")
    erreurs = []

    def boucle(fonction):
        try:
            for i in range(150):
                fonction(i)
        except Exception as e:  # noqa: BLE001
            erreurs.append(e)

    fils = [
        threading.Thread(target=boucle, args=(lambda i: remplacer_section(
            chemin, "telegram", [("actif", "true"), ("n", str(i))]),)),
        threading.Thread(target=boucle, args=(lambda i: ecrire_cles(
            chemin, "simultanes", {"garde_max": i}),)),
    ]
    for f in fils:
        f.start()
    for f in fils:
        f.join()

    assert not erreurs
    d = tomllib.loads(chemin.read_text(encoding="utf-8"))
    assert d["telegram"]["n"] == 149 and d["simultanes"]["garde_max"] == 149
    assert d["vault"]["racine"] == "x"
    assert list(tmp_path.iterdir()) == [chemin]
