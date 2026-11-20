"""Un hook de fin de session fait écrire à l'agent un second message : il n'est pas la réponse."""

import json

from orchestrateur.harnais.claude import HarnaisClaude


def test_reponse_au_hook_de_fin_n_est_pas_la_reponse_finale(tmp_path):
    dossier = tmp_path / "projects" / "C--Users-utilisateur"
    dossier.mkdir(parents=True)
    lignes = [
        {"type": "user", "message": {"content": "Découpe le projet."}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Quatre tickets.\n<decoupage>…</decoupage>"}]}},
        {"type": "user", "message": {"content": "Stop hook feedback:\nLIAGE TÂCHE"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "LIAGE-TÂCHE: none"}]}},
        {"type": "user", "message": {"content": "Merci."}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "De rien."}]}},
    ]
    (dossier / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lignes), encoding="utf-8")
    msgs = HarnaisClaude({"transcripts": str(tmp_path / "projects")}).transcript("s", 50)
    assert [(m.role, m.texte[:14], m.secondaire) for m in msgs] == [
        ("utilisateur", "Découpe le pro", False), ("assistant", "Quatre tickets", False),
        ("assistant", "LIAGE-TÂCHE: n", True), ("utilisateur", "Merci.", False),
        ("assistant", "De rien.", False)]
