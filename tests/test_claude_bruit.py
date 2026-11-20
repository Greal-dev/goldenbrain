"""Le transcript Claude ne présente pas à l'utilisateur les messages que le harnais s'adresse à lui-même."""

import json

from orchestrateur.harnais.claude import HarnaisClaude


def test_notification_de_tache_de_fond_n_est_pas_un_message_de_l_utilisateur(tmp_path):
    dossier = tmp_path / "projects" / "C--Users-utilisateur"
    dossier.mkdir(parents=True)
    lignes = [
        {"type": "user", "message": {"content": "Où en est le portail ?"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Je cherche."}]}},
        {"type": "user", "message": {"content": "<task-notification>\n<task-id>x</task-id>\n</task-notification>"}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "<system-reminder>rappel</system-reminder>"}]}},
        {"type": "user", "message": {"content": "Stop hook feedback:\nLIAGE"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Voici la réponse."}]}},
    ]
    (dossier / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lignes), encoding="utf-8")
    msgs = HarnaisClaude({"transcripts": str(tmp_path / "projects")}).transcript("s", 50)
    assert [(m.role, m.texte) for m in msgs] == [
        ("utilisateur", "Où en est le portail ?"), ("assistant", "Je cherche."),
        ("assistant", "Voici la réponse.")]
