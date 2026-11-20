# AGENTS.md — GoldenBrain

Point d'entrée des agents IA (Claude Code, Codex, OpenCode, Copilot, Antigravity, Gemini CLI…), qu'ils **pilotent** GoldenBrain ou **travaillent dans ce dépôt**.

## Piloter GoldenBrain

Mode d'emploi complet, vérifié sur un serveur d'essai : section « Pour un agent IA » de `docs/GUIDE.md` (ou `python orch.py guide`). L'essentiel :

1. **Serveur** : `./lancer.sh` (Linux, macOS) ou `lancer.cmd` (Windows) ; vérifier par `curl -s http://127.0.0.1:8300/api/etat`. Autre port : `export ORCH_URL=http://127.0.0.1:<port>`.
2. **Commande** : `python orch.py arbre | chercher | lire | rapprochement | creer | dire | relancer | proposer | renommer | telegram | …` depuis la racine du dépôt (`-h` sur chacune).
3. **API** : JSON sur `http://127.0.0.1:8300/api/…` ; toute écriture porte l'en-tête `X-Orchestrateur: 1` (sinon 403).
4. **Règles** : rapprocher avant de créer (`rapprochement`, `chercher`) ; jamais de changement de statut, de validation ni d'acceptation de proposition sans accord humain ; une tâche « Moi » (`executant: humain`) n'accepte aucun tour d'agent ; la structure se change par `proposer`, jamais à la main ; aucun envoi, publication, paiement ni suppression sans accord écrit.

Exemple minimal :

```bash
python orch.py rapprochement "Rédiger la note de version"
python orch.py creer "Rédiger la note de version" \
  --description "Résumer les changements de la semaine ; preuve : la note existe dans le vault."
python orch.py lire 2026-11-19-rediger-la-note-de-version
```

## Travailler dans ce dépôt

1. **Contrat de session** : `CLAUDE.md` — commandes canoniques, règles, zones dangereuses, publication.
2. **Architecture** : `docs/ARCHITECTURE.md` (modules, invariants `INV-*`, contrats) et `docs/CODE_MAP.md` (fichier → rôle → invariants → tests).
3. **Porte unique avant tout commit** : `python scripts/check.py`. Interface : `python scripts/check_ui.py`. Toute évolution visible met `docs/GUIDE.md` à jour dans le même commit (INV-GUIDE-1) et porte, dans son message d'enregistrement, une ligne `Nouveauté: <ce qui change pour l'utilisateur, en langage courant>` : elle alimente `CHANGELOG.md` et les notes de version (INV-NOUV-1).
