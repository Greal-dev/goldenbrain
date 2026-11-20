"""Texte de fin de tour de l'adaptateur Claude : le tour entier, pas le seul dernier message."""

from orchestrateur.harnais.claude import _texte_du_tour


def test_decoupage_rendu_avant_la_reponse_au_hook_reste_lisible():
    textes = ["Quatre tickets.\n<decoupage>\n- titre: A\n</decoupage>\n<fiche>\nfait: x\n</fiche>",
              "LIAGE-TÂCHE: none"]
    tour = _texte_du_tour(textes, "LIAGE-TÂCHE: none")
    assert "<decoupage>" in tour and "<fiche>" in tour and tour.endswith("LIAGE-TÂCHE: none")


def test_message_unique_ou_resultat_distinct_inchanges():
    assert _texte_du_tour(["Fini."], "Fini.") == "Fini."
    assert _texte_du_tour(["a", "b"], "autre chose") == "autre chose"
    assert _texte_du_tour([], "seul") == "seul"
