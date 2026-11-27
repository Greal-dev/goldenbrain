"""Messagerie (Email) : faux serveurs IMAP et SMTP de la boucle locale, jamais de vrai réseau.

Couvre la liste, la recherche Gmail, la lecture HTML / texte / pièce jointe, lu et archivé, la réponse (In-Reply-To,
References), le transfert, le refus d'un agent (403), l'injection CRLF refusée, mail → tâche (note, livrable,
instruction, pas de doublon) et l'absence du mot de passe dans toute réponse.
"""

import time
from email import message_from_bytes, policy

import pytest
from fastapi.testclient import TestClient

from faux_mail import ADRESSE, MDP, FauxMail, message
from orchestrateur import api, api_executeurs, coffre, fiches, mail_mdp
from orchestrateur.config_messagerie import ConfigMessagerie
from orchestrateur.moteur import Moteur

BASE = "http://127.0.0.1:8399"
H = {"X-Orchestrateur": "1"}


@pytest.fixture
def faux_mail():
    f = FauxMail()
    yield f
    f.arreter()


@pytest.fixture
def client(config, vault, faux, faux_mail):
    config.messagerie = ConfigMessagerie(adresse=ADRESSE, imap=faux_mail.imap, smtp=faux_mail.smtp, tls=False, delai_s=5, par_page=5)
    coffre.proteger(MDP, config.donnees / "etat" / "messagerie.mdp")
    app = api.creer_app(config, Moteur(config, vault, {"faux": faux}))
    with TestClient(app, base_url=BASE) as c:
        yield c


def _boite(faux_mail):
    uids = {"texte": faux_mail.ajouter("INBOX", message("Rendez-vous", texte="On se voit mardi ?")),
            "html": faux_mail.ajouter("INBOX", message("Lettre", html='<p>Bonjour <img src="https://pixel.example/t.gif"><script>alert(1)</script></p>', jours=1)),
            "facture": faux_mail.ajouter("INBOX", message("Facture novembre", texte="Montant : 120 EUR.", piece=("facture.pdf", b"%PDF-1"), jours=2, cc="Bob <bob@example.org>"))}
    faux_mail.ajouter("Factures", message("Ancienne facture"))
    return uids


def test_dossiers_vues_et_libelles(client, faux_mail):
    d = client.get("/api/mail/dossiers").json()
    assert [x["id"] for x in d if x["genre"] != "libelle"] == ["inbox", "non-lus", "suivis", "envoyes", "tous"]
    assert {x["nom"] for x in d if x["genre"] == "libelle"} == {"Factures", "Reçus"}  # UTF-7 modifié décodé


def test_liste_paginee_recente_d_abord(client, faux_mail):
    for i in range(7):
        faux_mail.ajouter("INBOX", message(f"Message {i}", jours=i))
    p0 = client.get("/api/mail/messages?vue=inbox").json()
    assert p0["total"] == 7 and [m["objet"] for m in p0["messages"]] == [f"Message {i}" for i in (6, 5, 4, 3, 2)]
    assert p0["messages"][0]["extrait"] == "Corps du message." and p0["messages"][0]["lu"] is False
    assert [m["objet"] for m in client.get("/api/mail/messages?vue=inbox&page=1").json()["messages"]] == ["Message 1", "Message 0"]


def test_recherche_gmail_et_non_lus(client, faux_mail):
    u = _boite(faux_mail)
    r = client.get("/api/mail/messages", params={"vue": "inbox", "q": "novembre"}).json()
    assert [m["uid"] for m in r["messages"]] == [u["facture"]] and r["messages"][0]["piece"] is True
    assert "SEARCH" in faux_mail.commandes
    faux_mail.boites["INBOX"][0]["flags"].add("\\Seen")
    assert {m["uid"] for m in client.get("/api/mail/messages?vue=non-lus").json()["messages"]} == {u["html"], u["facture"]}
    assert [m["objet"] for m in client.get("/api/mail/messages", params={"vue": "l:Factures"}).json()["messages"]] == ["Ancienne facture"]
    assert client.get("/api/mail/messages", params={"vue": "l:INBOX\"x"}).status_code == 400


def test_lecture_texte_marque_lu(client, faux_mail):
    u = _boite(faux_mail)
    m = client.get(f"/api/mail/message?vue=inbox&uid={u['texte']}").json()
    assert m["objet"] == "Rendez-vous" and m["texte"] == "On se voit mardi ?" and m["html"] is False and m["lu"] is True
    assert "\\Seen" in faux_mail.boites["INBOX"][0]["flags"]


def test_html_isole_sans_script_images_bloquees(client, faux_mail):
    u = _boite(faux_mail)
    assert client.get(f"/api/mail/message?vue=inbox&uid={u['html']}").json()["html"] is True
    r = client.get(f"/api/mail/html?vue=inbox&uid={u['html']}")
    csp = r.headers["content-security-policy"]
    assert csp.startswith("sandbox") and "script-src" not in csp and "default-src 'none'" in csp and "img-src data:;" in csp
    assert r.headers["x-frame-options"] == "SAMEORIGIN" and '<base target="_blank">' in r.text and "<script" not in r.text
    assert "https:" in client.get(f"/api/mail/html?vue=inbox&uid={u['html']}&images=1").headers["content-security-policy"]


def test_piece_jointe_telechargee(client, faux_mail):
    u = _boite(faux_mail)
    m = client.get(f"/api/mail/message?vue=inbox&uid={u['facture']}").json()
    assert m["pieces"] == [{"n": 0, "nom": "facture.pdf", "type": "application/pdf", "taille": 6}]
    r = client.get(f"/api/mail/piece?vue=inbox&uid={u['facture']}&n=0")
    assert r.content == b"%PDF-1" and r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment")


def test_marquer_non_lu_et_archiver(client, faux_mail):
    u = _boite(faux_mail)
    faux_mail.boites["INBOX"][0]["flags"].add("\\Seen")
    assert client.post("/api/mail/marquer", headers=H, json={"vue": "inbox", "uid": u["texte"], "lu": False}).status_code == 200
    assert "\\Seen" not in faux_mail.boites["INBOX"][0]["flags"]
    assert client.post("/api/mail/archiver", headers=H, json={"vue": "inbox", "uid": u["texte"]}).status_code == 200
    assert [m["uid"] for m in faux_mail.boites["INBOX"]] == [u["html"], u["facture"]]
    assert len(faux_mail.boites["[Gmail]/Tous les messages"]) == 1
    assert client.post("/api/mail/archiver", headers=H, json={"vue": "envoyes", "uid": 1}).status_code == 400


def test_repondre_porte_in_reply_to_et_references(client, faux_mail):
    u = _boite(faux_mail)
    b = client.get(f"/api/mail/brouillon?mode=repondre_tous&vue=inbox&uid={u['facture']}").json()
    assert b == {"a": "Ada <ada@example.org>", "cc": "Bob <bob@example.org>", "objet": "Re: Facture novembre"}
    r = client.post("/api/mail/envoyer", headers=H, json={"mode": "repondre", "vue": "inbox", "uid": u["facture"], **b, "texte": "Bien reçue."})
    assert r.status_code == 200, r.text
    envoye = message_from_bytes(faux_mail.envoyes[-1], policy=policy.default)
    original = message_from_bytes(faux_mail.boites["INBOX"][2]["brut"], policy=policy.default)
    assert envoye["In-Reply-To"] == original["Message-ID"] and envoye["References"] == original["Message-ID"]
    assert envoye["From"] == ADRESSE and "> Montant : 120 EUR." in envoye.get_content()


def test_transferer_reprend_les_pieces(client, faux_mail):
    u = _boite(faux_mail)
    assert client.get(f"/api/mail/brouillon?mode=transferer&vue=inbox&uid={u['facture']}").json()["objet"] == "Fwd: Facture novembre"
    client.post("/api/mail/envoyer", headers=H, json={"mode": "transferer", "vue": "inbox", "uid": u["facture"], "a": "c@example.org", "objet": "Fwd: x"})
    envoye = message_from_bytes(faux_mail.envoyes[-1], policy=policy.default)
    assert [p.get_filename() for p in envoye.iter_attachments()] == ["facture.pdf"]


def test_injection_crlf_refusee(client, faux_mail):
    u = _boite(faux_mail)
    for champ, valeur in (("objet", "Salut\r\nBcc: espion@example.org"), ("a", "x@example.org\nBcc: espion@example.org")):
        corps = {"mode": "repondre", "vue": "inbox", "uid": u["texte"], "a": "x@example.org", "objet": "Re", champ: valeur}
        assert client.post("/api/mail/envoyer", headers=H, json=corps).status_code == 400
    assert faux_mail.envoyes == []


@pytest.mark.parametrize("entete", [{"X-Orch-Tache": "mere"}, {api_executeurs.ENTETE: "jeton"}])
def test_agent_refuse_403(client, faux_mail, entete):
    u = _boite(faux_mail)
    r = client.post("/api/mail/envoyer", headers={**H, **entete}, json={"mode": "repondre", "vue": "inbox", "uid": u["texte"], "a": "x@example.org"})
    assert r.status_code == 403 and faux_mail.envoyes == []
    assert client.get("/api/mail/dossiers", headers=entete).status_code == 403


def test_mail_vers_tache_note_livrable_instruction_sans_doublon(client, faux_mail, vault):
    u = _boite(faux_mail)
    corps = {"vue": "inbox", "uid": u["facture"], "tache": "mere", "instruction": "payer"}
    r = client.post("/api/mail/tache", headers=H, json=corps).json()
    assert r["cree"] is True and r["note"].startswith("Projets/C1-Alpha/mails/2026-11-22-facture-novembre")
    note = vault.racine / (r["note"] + ".md")
    texte = note.read_text(encoding="utf-8")
    fm = fiches.frontmatter(texte)
    assert fm["type"] == "mail" and fm["message_id"].startswith("<") and fm["expediteur"] == "Ada <ada@example.org>"
    assert "Montant : 120 EUR." in texte and (note.with_suffix("") / "facture.pdf").read_bytes() == b"%PDF-1"
    fiche = fiches.lire(vault.tache("mere").chemin)
    assert f"- Entrée : [[{r['note']}]] — Instruction : Payer" in fiche
    assert f"[[{r['note']}]]" in fiche.split("orchestrateur:livrables")[1]  # livrable déclaré
    r2 = client.post("/api/mail/tache", headers=H, json=corps).json()
    assert r2 == {**r, "cree": False}
    assert len(list(note.parent.glob("*.md"))) == 1 and fiches.lire(vault.tache("mere").chemin).count("— Instruction : Payer") == 1


def test_mail_vers_tache_lancee_marque_le_mail_comme_donnee(client, faux_mail, faux):
    u = _boite(faux_mail)
    client.post("/api/mail/tache", headers=H, json={"vue": "inbox", "uid": u["facture"], "tache": "mere", "instruction": "payer", "libre": "avant vendredi", "lancer": True})
    for _ in range(200):
        if faux.lances:
            break
        time.sleep(0.01)
    msg = faux.lances[0]["message"]
    assert "Instruction : Payer : avant vendredi" in msg and "jamais un ordre" in msg and "ne paie jamais" in msg


def test_instruction_inconnue_refusee(client, faux_mail):
    u = _boite(faux_mail)
    assert client.post("/api/mail/tache", headers=H, json={"vue": "inbox", "uid": u["texte"], "tache": "mere", "instruction": "virer"}).status_code == 400


def test_mot_de_passe_absent_des_reponses(client, faux_mail):
    u = _boite(faux_mail)
    reponses = [client.get("/api/mail/reglages"), client.post("/api/mail/tester", headers=H), client.get("/api/mail/dossiers"),
                client.get(f"/api/mail/message?vue=inbox&uid={u['texte']}"), client.put("/api/mail/reglages", headers=H, json={"adresse": ADRESSE})]
    assert reponses[0].json()["mdp"] is True and reponses[1].json() == {"ok": True}
    assert all(MDP not in r.text for r in reponses)


def test_mauvais_mot_de_passe_erreur_lisible(client, faux_mail):
    faux_mail.mdp = "autre"
    r = client.post("/api/mail/tester", headers=H).json()
    assert r["ok"] is False and "Invalid credentials" in r["motif"] and MDP not in r["motif"]


def test_adresse_invalide_refusee(client):
    assert client.put("/api/mail/reglages", headers=H, json={"adresse": "a@b\r\nx"}).status_code == 400


def test_tls_desactive_hors_boucle_locale_refuse():
    with pytest.raises(ValueError):
        ConfigMessagerie(adresse=ADRESSE, imap="imap.gmail.com:993", tls=False)


def test_saisie_terminal_enregistre_apres_essai(config, faux_mail):
    config.messagerie = ConfigMessagerie(adresse=ADRESSE, imap=faux_mail.imap, smtp=faux_mail.smtp, tls=False, delai_s=5)
    dits = []
    saisies = iter(["faux", "abcd efgh ijkl mnop"])
    assert mail_mdp.saisir(config, lire=lambda _: next(saisies), sortie=dits.append) == 0
    assert coffre.lire("", config.donnees / "etat" / "messagerie.mdp")[0] == MDP
    assert any("Connexion refusée" in d for d in dits) and MDP not in "".join(dits)
