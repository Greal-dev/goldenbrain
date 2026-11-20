# Orchestrateur — contrat de session

Surface de pilotage de tâches confiées à des agents IA, adossée à un vault Markdown.
L'orchestrateur pilote ; il n'exécute rien : chaque tâche est une conversation d'un harnais natif.

## À lire d'abord
0. `docs/GUIDE.md` (ou `python orch.py guide`) — ce que voit et fait l'utilisateur, écran par écran ; section « Pour un agent IA ».
1. `docs/ARCHITECTURE.md` — carte des modules, invariants `INV-*`, contrats (API, harnais, fiche).
2. `config.exemple.toml` — tout ce qui dépend du vault ou du poste.

## Commandes canoniques
- Python 3.12 avec FastAPI, uvicorn, PyYAML, et pour les tests pytest et httpx (`pip install .[test]` ; TestClient l'exige — sans lui la collecte échoue) ; ne rien installer d'autre. Les lanceurs (`.cmd`, `.sh`) lisent son chemin dans `python.local` (non suivi), sinon `python` du PATH.
- Gate unique : `python scripts/check.py` (tests + contrôles) — doit être vert avant tout commit.
- Interface : `python scripts/check_ui.py` (Playwright, vrai serveur, vault temporaire, harnais factice ; hors porte rapide) — voir `tests/ui/README.md`.
- Lancer : `lancer.cmd` (Windows) ou `./lancer.sh` (Linux) (le Python embarqué ignore `PYTHONPATH` : le script ajoute `src` lui-même), puis http://127.0.0.1:8300. `config.toml` se copie de `config.exemple.toml`.
- Commande des agents : `python orch.py …` (jamais par un `.cmd` : espaces du chemin et guillemets).

## Règles
- Code et identifiants en français ; libellés et messages via les dictionnaires `web/langues/{fr,en,de,es}.json`, source `fr` (INV-LANGUE-1) : `t()` côté interface, `langues.t()` côté serveur ; une clé ajoutée l'est dans les quatre langues (`python scripts/dictionnaires.py ajouter <lot.json>`) ; vocabulaire grand public et stabilité des clés : `docs/VOCABULAIRE.md`.
- Aucune dépendance nouvelle ; interface sans étape de build (HTML, CSS, JS natifs).
- Le vault est la seule base de données. Les tests n'écrivent jamais dans le vrai vault : vault temporaire (`tmp_path`).
- Les tests ne lancent jamais un vrai harnais : adaptateur factice.
- Portabilité Windows : toute lecture/écriture texte (`read_text`, `write_text`, `open`, `subprocess` en `text=True`) porte `encoding="utf-8"` ; la porte le contrôle.
- Module ≤ 500 lignes, en-tête de module (rôle, frontières, invariants portés), commentaire = pourquoi + `INV-*`.
- Un invariant cité dans le code doit exister dans `docs/ARCHITECTURE.md`.
- Guide tenu à jour (INV-GUIDE-1) : une évolution visible (écran, bouton, réglage, commande, installation) n'est « faite » que si `docs/GUIDE.md` (section et date « Mis à jour le ») change dans le même commit ; un écran nouveau s'inscrit au registre `guide.SECTIONS`, que la porte vérifie.
- Nouveautés (INV-NOUV-1) : une évolution visible porte dans son message d'enregistrement une ligne `Nouveauté: <ce qui change pour l'utilisateur, en langage courant>` ; `CHANGELOG.md` est produit par la CI (`scripts/nouveautes.py`), jamais écrit à la main.

## Publication
- INV-PUB-1 : aucun fichier suivi ne contient de donnée personnelle (nom, adresse, chemin de poste, projets réels, identifiants de session, jetons). `scripts/check.py` le contrôle ; motifs personnels dans `.sensible` (non suivi, gabarit `.sensible.exemple`). Le réglage personnel vit dans `config.toml` et `python.local`, jamais dans le dépôt.

## Zones dangereuses
- `fiches.py` : INV-VAULT-1 (ne jamais reformater le frontmatter de l'utilisateur). Le bloc géré est le dernier `debut` seul sur sa ligne suivi de son `fin` ; un marqueur cité dans la prose n'est jamais une borne.
- `harnais/claude.py` : processus Windows — prompt par stdin, arrêt de l'arbre de processus (`taskkill /T /F`).
