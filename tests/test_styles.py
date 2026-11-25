"""Feuille de styles unique (INV-REACTIVITE-1) : /style-tout.css assemble web/styles.liste, sans en oublier une."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrateur import api_styles

WEB = Path(__file__).resolve().parent.parent / "web"


def client(web=WEB):
    app = FastAPI()
    app.include_router(api_styles.routes(web))
    return TestClient(app)


def test_toute_feuille_du_dossier_web_est_dans_la_liste():
    """Symptôme évité : une feuille ajoutée sans l'inscrire à styles.liste disparaîtrait de l'écran (plus de lien dans index.html)."""
    hors_liste = sorted({f.name for f in WEB.glob("*.css")} - set(api_styles.feuilles(WEB)))
    assert not hors_liste, f"feuilles absentes de web/styles.liste : {hors_liste}"


def test_index_ne_cite_que_la_feuille_unique():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert html.count('rel="stylesheet"') == 1 and "style-tout.css" in html


def test_la_feuille_unique_concatene_dans_l_ordre_et_se_revalide(tmp_path):
    (tmp_path / "styles.liste").write_text("# commentaire\na.css\nb.css\nabsente.css\n", encoding="utf-8")
    (tmp_path / "a.css").write_text("a { color: red }", encoding="utf-8")
    (tmp_path / "b.css").write_text("b { color: blue }", encoding="utf-8")
    c = client(tmp_path)
    r = c.get("/style-tout.css")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")
    assert r.text.index("a { color: red }") < r.text.index("b { color: blue }")
    assert c.get("/style-tout.css", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
    (tmp_path / "b.css").write_text("b { color: green }", encoding="utf-8")
    assert "green" in c.get("/style-tout.css").text
