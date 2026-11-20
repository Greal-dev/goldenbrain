"""Messages du serveur dans la langue réglée (INV-LANGUE-1) : un cas par famille (erreur d'API, incident, accueil, Telegram)."""

import pytest
from fastapi.testclient import TestClient

from orchestrateur import accueil, api, incidents, langues
from orchestrateur.moteur import Moteur
from orchestrateur.vault import Invalide
from test_telegram import _bouton, relever, tg  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def langue_source():
    yield
    langues.regler("fr")


def test_erreur_d_api_en_allemand(config, vault, faux):
    with TestClient(api.creer_app(config, Moteur(config, vault, {"faux": faux})), base_url="http://127.0.0.1:8399") as c:
        langues.regler("de")  # creer_app règle la langue de la configuration : on la change après
        r = c.get("/api/taches/fantome")
    assert r.status_code == 404 and r.json()["detail"] == "Unbekannte Aufgabe: fantome"


def test_incident_en_allemand():
    langues.regler("de")
    assert incidents.classer("Error: not logged in", "codex")[1:] == (
        "KI-Assistent nicht angemeldet",
        "Melden Sie sich in der Eingabeaufforderung beim KI-Assistenten an und starten Sie dann neu.")


def test_accueil_en_allemand():
    langues.regler("de")
    with pytest.raises(Invalide, match="^Wählen Sie mindestens eine Quelle aus$"):
        accueil.proposer(None, {})


def test_telegram_en_allemand(config, vault, faux, tg):  # noqa: F811
    async def compte_rendu(c):
        langues.regler("de")
        await c.question("mere", "Erledigt", boutons=True)
        _bouton(tg, 1, "valider", tg.envoyes[-1]["message_id"])
        await c.relever()

    relever(config, vault, faux, compte_rendu)
    toasts = [p for m, p in tg.requetes if m == "answerCallbackQuery"]
    assert toasts[-1]["text"] == "Aufgabe bestätigt."
