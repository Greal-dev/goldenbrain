# CODE_MAP — fichier → rôle → invariants → tests

Carte du dépôt. Les invariants `INV-*` sont **définis** dans `docs/ARCHITECTURE.md` ; cette carte dit quels fichiers les portent.
La porte (`scripts/check.py`) contrôle cette carte : tout fichier de `src/`, `web/`, `scripts/`, `tests/` et `orch.py` y figure
(une ligne, chemin en code), aucune ligne ne désigne un fichier absent, chaque `INV-*` cité dans un module de `src/` figure sur sa ligne
et est défini dans ARCHITECTURE. Un fichier ajouté, supprimé ou qui cite un nouvel invariant sans mise à jour d'ici rend la porte rouge.

Colonnes : **INV-\*** = invariants cités dans le fichier ; **Tests** = fichiers de `tests/` qui l'exercent (sans préfixe = `tests/`, `ui/…` = `tests/ui/`).
Un fichier sans test dédié est exercé par l'intermédiaire des routes et du moteur ; la mention « — » l'avoue.
Les tests d'interface (`ui/`) se lancent à part : `python scripts/check_ui.py`.

## Backend (`src/orchestrateur/`)

| Fichier | Rôle | INV-* cités | Tests |
|---|---|---|---|
| `src/orchestrateur/__init__.py` | Orchestrateur : pilotage de tâches confiées à des agents IA, adossé à un vault Markdown. | — | — |
| `src/orchestrateur/__main__.py` | Point d'entrée : `python -m orchestrateur` démarre uvicorn sur 127.0.0.1 (plus `executeurs.ecoute`). | INV-API-1, INV-DISTANT-1, INV-DISTANT-7, INV-INSTANCE-1, INV-VERSION-1 | `test_appareils.py`, `ui/serveur.py`, `ui/scenario_fumee.py` (lancement réel) |
| `src/orchestrateur/alignement.py` | Alignement physique : les dossiers des conteneurs suivent l'arbre. | INV-ALIGN-1, INV-ALIGN-2, INV-ALIGN-3, INV-ALIGN-4, INV-ARBRE-1, INV-ARBRE-2, INV-VAULT-2 | `test_alignement.py`, `test_geste.py`, `test_reduction.py` |
| `src/orchestrateur/api.py` | API HTTP de l'orchestrateur (FastAPI) : routes JSON, flux SSE, garde locale, statiques `web/`. | INV-FROID-1, INV-ACCUEIL-1, INV-REACTIVITE-1, INV-AGENTSCC-1, INV-ALIGN-2, INV-API-1, INV-APPRENDRE-1, INV-ARBRE-2, INV-COMPACT-1, INV-CONTROLE-1, INV-DISTANT-1, INV-DISTANT-2, INV-DISTANT-5, INV-DISTANT-6, INV-ECO-1, INV-ETOILE-1, INV-EXEC-1, INV-EXEC-10, INV-EXEC-11, INV-EXEC-5, INV-EXEC-8, INV-EXECUTANT-1, INV-FEU-1, INV-GUIDE-1, INV-INSTALL-1, INV-JARD-1, INV-LANGUE-1, INV-MAJ-3, INV-MANAGER-1, INV-MODELES-1, INV-NATIF-1, INV-ORDO-1, INV-ORDO-2, INV-PILOTAGE-1, INV-POSTE-1, INV-RAPPROCHEMENT-1, INV-REGROUPE-1, INV-REGROUPE-2, INV-RENOMMER-1, INV-RESULTAT-1, INV-RETOUR-1, INV-ROUTINE-1, INV-ROUTINE-3, INV-ROUTINE-5, INV-SIMULT-1, INV-TELEGRAM-1, INV-TRACE-1, INV-TRAVAUX-1, INV-TRAVAUX-2, INV-VALID-2, INV-VAULT-3, INV-VERROU-1, INV-VERSION-1, INV-VERSION-2, INV-VIGIE-1, INV-VIGIE-2, INV-CHAINE-1, INV-CHAINE-4, INV-COMPAGNON-1, INV-PWA-2, INV-PROP-1, INV-REPRISE-1, INV-MAIN-1, INV-MAIN-4, INV-APPAIRAGE-2 | `test_api.py`, `test_demi_verrou.py`, `test_equipe.py`, `test_moteurs.py`, `test_temps.py`, `test_version.py`, `test_feux_verts.py` |
| `src/orchestrateur/api_interface.py` | Mode simple / avancé : routes `/api/interface`, garde des familles débrayées (409), persistance de `[interface]` | INV-INTERFACE-1, INV-INTERFACE-2, INV-LANGUE-1, INV-STATUT-1, INV-VAULT-2, INV-PROP-1, INV-DISCUSSION-2 | `test_interface.py`, `ui/scenario_interface.py` |
| `src/orchestrateur/api_arbre.py` | Routes `/api/arbre` et `/api/alignement` : arbre, gestes, plan et application des déplacements. | INV-ALIGN-2, INV-ARBRE-2, INV-INTEG-1, INV-ROUTINE-5, INV-VERROU-1, INV-RATTACHER-1, INV-REPRISE-1, INV-MAIN-1, INV-MAIN-5, INV-FROID-1 | `test_arbre.py`, `test_alignement.py`, `test_geste.py`, `test_demi_verrou.py` |
| `src/orchestrateur/api_main.py` | Routes « à qui la main » : `/api/taches/{id}/ia`, `/api/lots/ia`, `/api/main` ; geste humain seul. | INV-MAIN-4, INV-MAIN-5, INV-ORDO-1, INV-VERROU-1 | `test_attente_muette.py` |
| `src/orchestrateur/attente_muette.py` | Renvoi borné d'un tour sans conclusion, puis demande humaine nommée. | INV-MAIN-2, INV-MAIN-3, INV-EXEC-1, INV-EXEC-12, INV-EXEC-8 | `test_attente_muette.py` |
| `src/orchestrateur/etat_main.py` | Lecture calculée des quatre états (IA, file, humain, terminé), phrase et geste ; compteurs « À moi » (trois catégories), veille et groupes. | INV-MAIN-1, INV-MAIN-4, INV-MAIN-6, INV-MAIN-7, INV-LIEN-2, INV-DECISIONS-3, INV-EXEC-7, INV-INTEG-2, INV-PILOTAGE-1, INV-STATUT-1, INV-POSTE-1 | `test_attente_muette.py` |
| `src/orchestrateur/api_maj.py` | Routes `/api/mise-a-jour` : état du retard sur la branche de diffusion, « Quoi de neuf », mise à jour d'un clic. | INV-MAJ-1, INV-MAJ-3, INV-MAJ-4, INV-NOUV-1, INV-SIGNAL-1, INV-VERSION-1, INV-VERSION-2, INV-VERSION-3, INV-FROID-1 | `test_mise_a_jour.py`, `test_version.py`, `test_collaboratif.py` |
| `src/orchestrateur/maj_auto.py` | Mise à jour automatique : gel des tours, pause sûre, avance rapide, redémarrage unique, retour arrière, bandeau. | INV-EXEC-1, INV-EXEC-6, INV-EXEC-9, INV-MAJ-1, INV-MAJ-3, INV-MAJ-4, INV-VERSION-1 | `test_maj_auto.py`, `test_collaboratif.py` |
| `src/orchestrateur/api_poste.py` | Routes `/api/poste` : lire (avec la file), réserver (ou attendre en file), annuler, libérer. | INV-API-1, INV-POSTE-1 | `test_poste.py` |
| `src/orchestrateur/api_executeurs.py` | Routes `/api/executeurs` : annonce, travail (long-poll), événements, vue, jetons, appairage ; refus des requêtes distantes sans jeton (hors échange d'un code). | INV-ACCUEIL-1, INV-API-1, INV-APPAIRAGE-1, INV-DISTANT-1, INV-DISTANT-3, INV-INSTALL-1, INV-INSTALL-4 | `test_executeurs.py`, `test_appairage.py`, `ui/scenario_executeurs.py` |
| `src/orchestrateur/accueil.py` | Accueil : plan proposé (casquettes, opérations, projets, tâches, notes, laissés de côté) à partir des sources cochées, avec la source de chaque élément ; sans écriture. | INV-ACCUEIL-1, INV-ACCUEIL-2, INV-ACCUEIL-4, INV-ACCUEIL-5 | `test_accueil.py` |
| `src/orchestrateur/accueil_sources.py` | Accueil : lecteurs en lecture seule (historiques Claude Code et Codex, dossier désigné, vault en place). | INV-ACCUEIL-1 | `test_accueil.py` |
| `src/orchestrateur/accueil_ecriture.py` | Accueil : revalidation du plan et écriture en ajout seulement (contextes, tâches reprenables, notes liées). | INV-ACCUEIL-3, INV-ACCUEIL-5, INV-VAULT-1, INV-VAULT-2 | `test_accueil.py` |
| `src/orchestrateur/squelette.py` | Accueil : vault de départ (dossiers d'un second cerveau, note « Lisez-moi ») proposé au seul vault vide, écrit en ajout après validation. | INV-ACCUEIL-5 | `test_accueil.py`, `ui/scenario_accueil.py` |
| `src/orchestrateur/api_accueil.py` | Routes `/api/accueil` : état, proposition, validation, « plus tard » ; inclut les premiers pas. | INV-ACCUEIL-1, INV-CERVEAU-1, INV-ACCUEIL-2, INV-REFLEXES-1 | `test_accueil.py`, `ui/scenario_accueil.py` |
| `src/orchestrateur/cerveau.py` | Second cerveau d'un poste : état, examen d'un dossier candidat, navigation, écriture de la seule clé `[vault] racine`. | INV-ACCUEIL-1, INV-CERVEAU-1, INV-CERVEAU-2, INV-INSTANCE-1 | `test_cerveau.py`, `ui/scenario_cerveau.py` |
| `src/orchestrateur/api_cerveau.py` | Routes `/api/accueil/cerveau` : état, examiner, dossiers, appliquer, plus tard. | INV-ACCUEIL-1, INV-CERVEAU-1, INV-CERVEAU-2, INV-VERSION-1 | `test_cerveau.py` |
| `web/cerveau.js` | Écran plein écran « Configurer votre second cerveau », rappel « Plus tard », réglage « Reconfigurer ». | INV-CERVEAU-1 | `ui/scenario_cerveau.py` |
| `tests/ui/scenario_cerveau.py` | Premier lancement sur poste neuf (vault absent, vide, garni), vault ailleurs, sélecteur, refus, « Plus tard », Réglages. | INV-CERVEAU-1, INV-CERVEAU-2 |  |
| `src/orchestrateur/assistant_absent.py` | Garde à la création lancée : assistant absent du poste, dit avec diagnostic (lequel manque, lesquels sont prêts) sauf bascule de quota possible. | INV-PREMIERS-PAS-2, INV-QUOTA-1 | `test_premier_lancement.py`, `ui/scenario_premier_lancement.py` |
| `web/accueil.js` | Accueil en 3 écrans (choisir, relire avec glisser-déposer, valider) et bouton « Relancer l'accueil » des Réglages. | INV-ACCUEIL-2, INV-WEB-1 | `ui/scenario_accueil.py` |
| `web/apprendre.js` | Mode « Apprendre » : section des Réglages, menu « Apprendre » d'une tâche, tous les libellés en tête de module. | INV-APPRENDRE-1 | `ui/scenario_apprendre.py` |
| `web/lignes.js` | Carte « Lignes », sélecteur et pastille de nature, dialogue de rangement (409), réglage « Rangement ». | INV-LIGNES-1, INV-NATURE-1, INV-PLAFOND-1 | `ui/scenario_lignes.py` |
| `web/lignes.css` | Lignes, pastille de nature, réglage de rangement. | INV-LIGNES-1 | — |
| `web/livrables.js` | Pastille « Livrables (n) » de l'en-tête et volet (filtre, recherche, attendus, déclaration). | INV-LIVRABLES-1, INV-DETAIL-1 | `test_livrables.py` |
| `web/livrables.css` | Volet des livrables, pastille. | INV-LIVRABLES-1 | — |
| `web/lecteur.js` | Lecteur de fichiers : volet de lecture (Markdown, texte, tableaux, HTML isolé, images, PDF), ouverture dans l'application, adresse `#f=`. | INV-LECTEUR-1 | `scenario_lecteur.py` |
| `web/lecteur-reglages.js` | Section Réglages du lecteur : dossiers lisibles, extensions lecteur/application. | INV-LECTEUR-1 | — |
| `web/lecteur.css` | Volet du lecteur, plein écran, feuille au téléphone. | INV-LECTEUR-1 | — |
| `web/apprendre.css` | Encadré d'explication du mode « Apprendre » et points à retenir. | INV-APPRENDRE-1 | — |
| `web/accueil.css` | Mise en page de l'accueil. | — | — |
| `tests/test_config_concurrente.py` | Écritures simultanées de sections de config.toml : aucune section perdue, aucun temporaire résiduel. | INV-INTERFACE-2 | — |
| `tests/test_accueil.py` | Accueil : proposition sans écriture, sources désactivables, ajout sans écrasement, plan corrigé revalidé, vault en place. | — | — |
| `tests/ui/scenario_accueil.py` | Accueil : parcours en 3 écrans, rien d'écrit avant validation, relance sans écrasement (poste factice). | — | — |
| `tests/test_premier_lancement.py` | Premier lancement : assistant choisi respecté en mode simple, assistant absent dit avec diagnostic, relevé Claude Code débrayé par défaut, npm sous Linux via sudo. | INV-PREMIERS-PAS-2 | — |
| `tests/ui/scenario_premier_lancement.py` | Vault vide : état vide guidé, un seul parcours, confirmation de la revue, avertissement à la première tâche. | INV-ACCUEIL-1 | — |
| `tests/ui/scenario_second_cerveau.py` | Accueil sur vault vide : classement de départ proposé, rien d'écrit avant validation, dossiers, Lisez-moi et contextes créés ; captures. | INV-ACCUEIL-5 |  |
| `src/orchestrateur/premiers_pas.py` | Premiers pas : assistants IA du poste (installé, connecté, pilotable), commande à copier et page officielle ; routes `/api/accueil/premiers-pas`. | INV-ACCUEIL-1, INV-PREMIERS-PAS-1 | `test_premiers_pas.py`, `ui/scenario_premiers_pas.py` |
| `src/orchestrateur/modeles.py` | Modèles de tâches : un fichier Markdown par modèle dans `modeles/`, servis par `GET /api/modeles`. | INV-LANGUE-1, INV-MODELES-1 | `test_modeles.py`, `ui/scenario_premiers_pas.py` |
| `web/premiers-pas.js` | Premiers pas en 2 écrans (assistants IA, tâche de démonstration), puis l'accueil ; bouton « Revoir les premiers pas » des Réglages. | INV-PREMIERS-PAS-1, INV-WEB-1 | `ui/scenario_premiers_pas.py` |
| `web/modeles.js` | Galerie de modèles du formulaire « Nouvelle tâche » : un clic pré-remplit titre et description. | INV-MODELES-1, INV-WEB-1 | `ui/scenario_premiers_pas.py` |
| `src/orchestrateur/reflexes.py` | Bloc de réflexes GoldenBrain dans les consignes des assistants IA : texte par langue, bornes, état, aperçu (diff), écriture atomique. | INV-REFLEXES-1 | `test_reflexes.py` |
| `src/orchestrateur/api_reflexes.py` | Routes `/api/accueil/reflexes` (état, appliquer, plus tard) et `POST /api/taches/{id}/traces`. | INV-ACCUEIL-1, INV-REFLEXES-1, INV-TRACE-1, INV-VAULT-1 | `test_reflexes.py` |
| `src/orchestrateur/cli_reflexes.py` | Commandes `orch reflexes` (état, aperçu, `--accord`) et `orch tracer`. | INV-REFLEXES-1, INV-TRACE-1 | `test_reflexes.py` |
| `web/reflexes.js` | « Réflexes de l'agent » : état par assistant, aperçu, Accepter / Plus tard / Retirer (Réglages > Agents, premiers pas). | INV-REFLEXES-1, INV-WEB-1 | `ui/scenario_premiers_pas.py` |
| `tests/test_reflexes.py` | Réflexes : pose et retrait sans toucher au reste, CRLF, états, accord exigé, routes, traçage. | — | — |
| `tests/test_cerveau.py` | Second cerveau : état, examen d'un dossier, écriture de la seule clé `racine` (fins de ligne, accents), routes. | INV-CERVEAU-1, INV-CERVEAU-2 | — |
| `tests/test_premiers_pas.py` | Premiers pas : état des assistants sur un poste factice, proposition au seul premier lancement, routes. | — | — |
| `tests/test_modeles.py` | Modèles : lecture, tri, fichiers invalides écartés, modèles livrés, route. | — | — |
| `tests/ui/scenario_premiers_pas.py` | Premiers pas jusqu'à la démonstration terminée ; modèle qui pré-remplit « Nouvelle tâche » (captures). | — | — |
| `src/orchestrateur/installation.py` | Assistant d'installation d'un PC exécuteur : catalogue d'étapes, diagnostic, étape sur accord, repli administrateur, parcours terminal et appairage. | INV-INSTALL-1, INV-INSTALL-2, INV-INSTALL-3 | `test_installation.py` |
| `src/orchestrateur/api_installation.py` | Routes `/api/installation` : diagnostic, une étape à la fois sur accord, appairage. | INV-API-1, INV-DISTANT-1, INV-APPAIRAGE-1, INV-INSTALL-1, INV-INSTALL-2, INV-INSTALL-3 | `test_installation.py`, `ui/scenario_installation.py` |
| `web/installation.js` | Section Réglages « Ajouter ce PC comme exécuteur » : étapes, commande montrée, confirmation, sortie, instructions, appairage. | INV-INSTALL-1, INV-INSTALL-2, INV-INSTALL-3 | `ui/scenario_installation.py` |
| `tests/test_encodage.py` | Portabilité Windows : le contrôle de la porte refuse tout encodage implicite ; le dépôt est conforme ; deux tests clés passent sous un poste non UTF-8. | — | — |
| `tests/test_installation_un_clic.py` | Installation « un clic » : empreintes épinglées, téléchargement altéré refusé, graine recopiée sans écraser la copie existante, port du lanceur Windows, icônes (rien n'est téléchargé). | INV-PAQUET-1, INV-PAQUET-2 | — |
| `tests/test_publier_version.py` | Publication d'une version : note en quatre langues dans l'ordre, repli sur le français, traduction hors rôle ou personnelle écartée, étiquette datée, version précédente par son arbre. | INV-NOUV-1, INV-PUB-1 | — |
| `tests/test_installation.py` | Assistant d'installation : accord exact, repli, clavier fermé, parcours, routes fermées à distance (faux poste). | — | — |
| `tests/ui/scenario_captures.py` | Captures et vidéo du README sur un vault de démonstration fictif, quatre langues (arbre, tâche, en cours, graphe ; `demo-<l>.webm`), harnais factice ; en porte : français seul, pauses écourtées. | INV-PUB-1 | — |
| `tests/ui/demo_vault.py` | Vault de démonstration fictif en quatre langues (atelier, maison, club) et scènes jouées par le harnais factice (`GB_DEMO`). | INV-PUB-1 | — |
| `tests/ui/scenario_installation.py` | Réglages : refus du dialogue, accord, accord erroné, appairage refusé (poste factice). | — | — |
| `tests/ui/scenario_rapprochement.py` | Nouvelle tâche : suggestions au fil de la saisie, « Compléter celle-ci », refus doux puis « Créer quand même ». | INV-RAPPROCHEMENT-1 | — |
| `tests/ui/scenario_etiquettes.py` | Étiquettes : ajout dans « Détails », puce dans l'arbre, consigne de réglage. | INV-ETIQUETTE-1, INV-ETIQUETTE-3 | — |
| `src/orchestrateur/appairage.py` | Appairage d'un exécuteur : code court à usage unique, durée limitée, essais limités, échangé contre un jeton. | INV-APPAIRAGE-1 | `test_appairage.py` |
| `src/orchestrateur/appareils.py` | Appareils distants (téléphone) : code d'appairage à usage unique, jetons d'appareil hachés, révocation, journal des connexions. | INV-DISTANT-5, INV-DISTANT-6, INV-DISTANT-8 | `test_appareils.py`, `ui/scenario_appareils.py` |
| `src/orchestrateur/api_appareils.py` | Garde des requêtes distantes (jeton d'appareil, Origin, réservé au poste, gestes à risque) et routes `/api/appareils`. | INV-API-1, INV-DISTANT-1, INV-DISTANT-5, INV-DISTANT-6, INV-DISTANT-7, INV-DISTANT-8, INV-LANGUE-1, INV-APPAIRAGE-2 | `test_appareils.py`, `test_telegram.py`, `ui/scenario_appareils.py` |
| `src/orchestrateur/compagnon.py` | Instantané du compagnon mobile : projection à liste blanche de l'arbre, des décisions et des travaux ; empreinte. | INV-COMPAGNON-1 | `test_compagnon.py` |
| `src/orchestrateur/api_compagnon.py` | Route `GET /api/compagnon/instantane` (ETag, 304, no-store). | INV-COMPAGNON-1, INV-DISTANT-6, INV-PWA-2 | `test_compagnon.py` |
| `web/compagnon.js` | Vue « Accueil » du téléphone (à décider, en cours, arbre allégé) ; stockage local optionnel de l'instantané. | INV-PWA-2, INV-COMPAGNON-1 | `ui/scenario_compagnon.py` |
| `web/travail.js` | Vue « Travail en cours » du téléphone : tâches épinglées et chat par tâche (routes existantes). | INV-COMPAGNON-2, INV-DISTANT-6 | `ui/scenario_compagnon.py` |
| `web/epingles.js` | Épinglage de tâches propre à l'appareil (localStorage, identifiants seulement). | INV-COMPAGNON-2 | `ui/scenario_compagnon.py` |
| `web/compagnon.css` | Mise en page de la vue « Accueil » du compagnon mobile. | INV-PWA-2 | `ui/scenario_compagnon.py` |
| `src/orchestrateur/qr.py` | Code QR (mode octet, correction M, versions 1 à 10) rendu en SVG ou PNG, calculé sur le poste. | INV-DISTANT-5, INV-APPAIRAGE-2 | `test_appareils.py`, `test_telegram.py` |
| `src/orchestrateur/lignes.py` | Lignes de tâche : ajouter, cocher, retirer, promouvoir, tâche → ligne. | INV-LIGNES-1, INV-VAULT-1 | `test_lignes.py` |
| `src/orchestrateur/livrables.py` | Livrables : déclarer, annoncer, relever d'office (traces, lignes), agréger la descendance, ouvrir un fichier du poste. | INV-LIVRABLES-1, INV-RESULTAT-1, INV-VAULT-1 | `test_livrables.py` |
| `src/orchestrateur/rangement.py` | Nature déduite, propositions de rangement, parents en excès. | INV-PLAFOND-1, INV-NATURE-1, INV-RAPPROCHEMENT-1 | `test_lignes.py` |
| `src/orchestrateur/config_rangement.py` | Réglage `[rangement]`. | INV-PLAFOND-1, INV-NATURE-1 | `test_lignes.py` |
| `src/orchestrateur/api_lignes.py` | Routes lignes, nature, `/api/rangement`. | INV-LIGNES-1, INV-NATURE-1, INV-PLAFOND-1 | `test_lignes.py`, `ui/scenario_lignes.py` |
| `src/orchestrateur/lecteur.py` | Lecteur de fichiers : registre des formats, racines lisibles, résolution sûre, pages de texte, brut isolé, ouverture au poste. | INV-LECTEUR-1, INV-RESULTAT-1 | `test_lecteur.py` |
| `src/orchestrateur/config_lecteur.py` | Réglage `[lecteur]` : dossiers, extensions lecteur/application. | INV-LECTEUR-1 | `test_lecteur.py` |
| `src/orchestrateur/api_lecteur.py` | Routes `/api/lecteur/*` (info, page, brut ; ouvrir, dossier, réglages réservés au poste). | INV-LECTEUR-1, INV-API-1 | `test_lecteur.py` |
| `src/orchestrateur/api_livrables.py` | Routes `/api/livrables` et `/api/taches/{id}/livrables…`. | INV-LIVRABLES-1, INV-API-1 | `test_livrables.py` |
| `src/orchestrateur/cli_divers.py` | Aides de la commande `orch` : détection du harnais natif, Microsoft 365, agents de Claude Code. | INV-NATIF-1 | `test_cli.py` |
| `src/orchestrateur/cli_erreurs.py` | `ErreurCli` (refus lisible, code 1) et `ParseurFr` (argparse en français, conseil des guillemets). | INV-LANGUE-1 | `test_audit_cli.py` |
| `src/orchestrateur/cli_lignes.py` | `orch ligne` et rendu des gestes de rangement. | INV-LIGNES-1, INV-NATURE-1, INV-PLAFOND-1 | `test_lignes.py` |
| `src/orchestrateur/apprendre.py` | Mode « Apprendre » : réglage `[apprendre]`, consigne ajoutée aux agents, priorité du réglage de tâche. | INV-APPRENDRE-1, INV-LANGUE-1 | `test_apprendre.py` |
| `src/orchestrateur/config_compactage.py` | Section `[compactage]` (extraite de `config` pour respecter la limite de 500 lignes). | INV-COMPACT-1 | `test_compactage.py` |
| `src/orchestrateur/config_distant.py` | Sections `[executeurs]` et `[distant]` de la configuration, validées au chargement. | INV-DISTANT-1, INV-DISTANT-5, INV-DISTANT-7, INV-PWA-2, INV-COMPAGNON-1 | `test_appareils.py`, `test_executeurs.py` |
| `src/orchestrateur/api_notes.py` | Routes `/api/vault/*` : parcourir, lire, chercher, résoudre, écrire, créer, mentions, graphe. | INV-ALIGN-2, INV-API-1, INV-GRAPHE-1, INV-NOTE-1, INV-NOTE-2, INV-NOTE-3, INV-VERROU-1 | `test_api_notes.py`, `test_projet_par_note.py`, `test_demi_verrou.py` |
| `src/orchestrateur/api_codespace.py` | Routes du codespace d'une tâche : état, gestes, lieu d'exécution. | INV-API-1, INV-CODESPACE-2, INV-VAULT-1 | `test_codespace.py` |
| `src/orchestrateur/api_routines.py` | Routes `/api/routines` : liste, création, détail, programme et pause, « Exécuter maintenant ». | INV-API-1, INV-ROUTINE-1, INV-ROUTINE-2, INV-ROUTINE-3 | `test_routines.py` |
| `src/orchestrateur/api_chaines.py` | Routes `/api/chaines` : modèles (liste, enregistrement, retrait), lancement, exécutions, validation et reprise, ajustements. | INV-API-1, INV-CHAINE-1, INV-CHAINE-2, INV-CHAINE-3 | `test_chaines.py` |
| `src/orchestrateur/codespace.py` | Rattachement d'une tâche à un codespace : déclaration, état, gestes, lieu d'exécution. | INV-CODESPACE-1, INV-CODESPACE-2 | `test_codespace.py` |
| `src/orchestrateur/api_pilotage.py` | Routes du chat de projet : `/api/pilotage` (trouver, créer au premier message et soumettre). | INV-PILOTAGE-1 | `test_pilotage.py` |
| `src/orchestrateur/api_feux.py` | Routes du feu vert lié à une version (`/api/feux-verts`). | INV-API-1, INV-FEU-1 | `test_feux_verts.py` |
| `src/orchestrateur/api_economie.py` | Routes `/api/economie` (lire, régler, persister) et moteur prévu d'une tâche avec bascule proposée. | INV-ECO-1 | `test_economie.py` |
| `src/orchestrateur/api_simultanes.py` | Routes `/api/simultanes` (lire, régler, persister clé par clé) et « Reprendre maintenant ». | INV-SIMULT-1, INV-VAULT-2 | `test_simultanes.py` |
| `src/orchestrateur/api_apprendre.py` | Routes `/api/apprendre` (réglage général) et `/api/taches/{id}/apprendre` (réglage de tâche). | INV-APPRENDRE-1 | `test_apprendre.py`, `ui/scenario_apprendre.py` |
| `src/orchestrateur/verrou_config.py` | Verrou commun des lecture-modification-écriture de `config.toml` (décorateur). | INV-INTERFACE-2 | `test_config_concurrente.py` |
| `src/orchestrateur/api_compactage.py` | Routes `/api/compactage` : seuil général (lire, régler, persister) et vue de mesure. | INV-COMPACT-1 | `test_compactage.py`, `ui/scenario_compactage.py` |
| `src/orchestrateur/api_integration.py` | Routes `/api/integration` : branche d'intégration et seuil de la pastille (lire, régler, persister). | INV-INTEG-1 | `test_integration.py`, `ui/scenario_integration.py` |
| `src/orchestrateur/api_retour.py` | Routes de la conversation d'une tâche (messages reliés à leur tour), « Modifier » un message (plan, renvoi) et versions archivées. | INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3, INV-EXEC-7, INV-EXEC-8 | `test_retour.py`, `test_api.py`, `test_echec_tour.py`, `ui/scenario_modifier.py` |
| `src/orchestrateur/api_styles.py` | Feuille de styles unique `/style-tout.css` : concatène `web/styles.liste` à la demande (une requête au lieu de dix-huit), revalidée par ETag. | INV-REACTIVITE-1 | `test_styles.py` |
| `src/orchestrateur/agents_cc.py` | Agents de Claude Code : inventaire (lecture seule), regroupement des doublons, rattachement proposé, gestes, relevé périodique. | INV-AGENTSCC-1 | `test_agents_cc.py` |
| `src/orchestrateur/api_decisions.py` | Routes de la page « Décisions » : liste des décisions en attente, gestes par lot, réglage de la pastille. | INV-AGENTSCC-1, INV-DECISIONS-1, INV-EVITABLE-1, INV-SCAN-1 | `test_decisions.py`, `test_scan.py` |
| `src/orchestrateur/decisions.py` | Page « Décisions » : sources réunies, question extraite, tri par le classement de l'ordonnancement, lots de gestes, consigne « Faire documenter ». | INV-AGENTSCC-1, INV-DECISIONS-1, INV-DECISIONS-2, INV-DECISIONS-3, INV-EVITABLE-1, INV-EXEC-5, INV-ROUTINE-4, INV-SCAN-1, INV-VALID-2, INV-PROP-1 | `test_decisions.py`, `test_scan.py` |
| `src/orchestrateur/api_temps.py` | Routes du temps : vue « Aujourd'hui » et pose d'échéance / priorité d'une tâche. | INV-API-1, INV-DECISIONS-3, INV-NATURE-1, INV-PLAFOND-1, INV-RAPPROCHEMENT-1, INV-TEMPS-1, INV-VAULT-1, INV-MAIN-4, INV-ETIQUETTE-1 | `test_temps.py` |
| `src/orchestrateur/api_titre.py` | Route du renommage : changer le titre affiché d'une tâche sans toucher à son identifiant. | INV-API-1, INV-RENOMMER-1, INV-VAULT-1 | `test_renommer.py` |
| `src/orchestrateur/arbre.py` | Arbre libre au-dessus des tâches : construction, fil d'Ariane, gestes « déplacer » et « monter ». | INV-ARBRE-1, INV-ARBRE-2, INV-EXECUTANT-1, INV-PILOTAGE-1, INV-VAULT-1, INV-LIGNES-1, INV-NATURE-1, INV-ETIQUETTE-1 | `test_arbre.py`, `test_geste.py`, `test_alignement.py`, `test_pilotage.py` |
| `src/orchestrateur/evitable.py` | Pastille « évitable ? » : critères sans IA, seuil réglable, réglage persisté. | INV-EVITABLE-1, INV-VAULT-2, INV-VALID-2 | `test_evitable.py` |
| `src/orchestrateur/catalogue.py` | Catalogue des moteurs : harnais disponibles, modèles proposés, découverte « auto » en cache. | — | `test_moteurs.py` |
| `src/orchestrateur/cli.py` | Commande `orch` : client HTTP de l'API, à l'usage des agents. | INV-DECISIONS-1, INV-DISTANT-1, INV-ECO-1, INV-EQUIPE-1, INV-EXEC-5, INV-EXECUTANT-1, INV-EXECUTANT-2, INV-FEU-1, INV-GUIDE-1, INV-INSTALL-1, INV-INTERFACE-3, INV-LIEN-1, INV-M365-1, INV-MSG-1, INV-NATIF-1, INV-PILOTAGE-1, INV-POSTE-1, INV-RAPPROCHEMENT-1, INV-REFLEXES-1, INV-REGROUPE-2, INV-RENOMMER-1, INV-TELEGRAM-2, INV-TRACE-1, INV-CHAINE-3, INV-PLAFOND-1, INV-RATTACHER-1, INV-LIEN-2, INV-PROP-1, INV-LIGNES-1, INV-ETIQUETTE-3 | `test_cli.py`, `test_temps.py`, `test_feux_verts.py`, `test_pilotage.py`, `test_m365.py` |
| `src/orchestrateur/executeur.py` | `orch executeur` : client d'un autre PC — annonce, relevé des ordres, dépôt cloné, harnais local, événements renvoyés jusqu'à accusé ; saisie du code d'appairage, jeton gardé hors dépôt. | INV-APPAIRAGE-1, INV-INSTALL-4, INV-DISTANT-1, INV-DISTANT-3, INV-DISTANT-4 | `test_executeurs.py`, `test_appairage.py` |
| `src/orchestrateur/executeurs.py` | Exécuteurs côté chef : jetons hachés, annonces, répartition des tours, adaptateur `HarnaisDistant`, perte et retour ; porte l'appairage. | INV-APPAIRAGE-1, INV-INSTALL-4, INV-DISTANT-1, INV-DISTANT-2, INV-DISTANT-3, INV-DISTANT-4, INV-MOTEUR-1 | `test_executeurs.py`, `test_appairage.py`, `ui/scenario_executeurs.py` |
| `src/orchestrateur/console.py` | Console GoldenBrain en terminal (`orch console`) et ouverture de son onglet. | INV-CONSOLE-1 | `test_console.py`, `ui/scenario_console.py` |
| `src/orchestrateur/config.py` | Chargement de `config.toml` en dataclasses. | INV-AGENTSCC-1, INV-COMPACT-1, INV-CONTROLE-1, INV-DISCUSSION-2, INV-DISTANT-1, INV-ECO-1, INV-ECO-2, INV-INTERFACE-1, INV-JARD-2, INV-LANGUE-1, INV-POSTE-1, INV-PUB-1, INV-QUOTA-1, INV-RESEAU-1, INV-SIMULT-1, INV-STATUT-1, INV-VALID-2, INV-VAULT-4, INV-VIGIE-1, INV-PROP-1 | `test_config.py`, `test_interface.py` |
| `src/orchestrateur/consigne_tri.py` | Consigne par défaut de l'assistant Telegram : instruction / contenu, état, création ou mise à jour d'une tâche proche, gestes à confirmer, choix, interdits (texte seul, sorti de config.py). | INV-RAPPROCHEMENT-1, INV-TELEGRAM-1, INV-TELEGRAM-3, INV-TELEGRAM-4 | `test_telegram.py` |
| `src/orchestrateur/conseil.py` | Avis d'un agent rapide avant de promouvoir une tâche ou de réduire un projet. | INV-EXEC-4, INV-INTERFACE-1, INV-MOTEUR-1, INV-MOTEUR-2 | `test_conseil.py`, `test_bugs_usage.py`, `test_roles.py` |
| `src/orchestrateur/equipe.py` | Équipe de personas : un fichier Markdown par persona (frontmatter + Mandat + Focus). | INV-VAULT-2 | `test_equipe.py` |
| `src/orchestrateur/feux_verts.py` | Feu vert lié à une version : demande, verdict du contrôleur, vérification par sha exact. | INV-FEU-1, INV-MSG-1, INV-VAULT-1 | `test_feux_verts.py` |
| `src/orchestrateur/fiches.py` | Lecture et réécriture d'UN fichier de tâche. | INV-APPRENDRE-1, INV-CHAINE-1, INV-DECISIONS-3, INV-EXEC-3, INV-EXECUTANT-1, INV-EXECUTANT-2, INV-LIGNES-1, INV-ROUTINE-2, INV-VAULT-1, INV-VAULT-2, INV-VAULT-4, INV-LIVRABLES-1 | `test_fiches.py` |
| `src/orchestrateur/geste.py` | Geste d'arbre sur un projet ou une opération : le dossier se déplace (le dossier fait foi). | INV-ALIGN-1, INV-ALIGN-3, INV-ARBRE-2 | `test_geste.py` |
| `src/orchestrateur/guide.py` | Guide d'utilisation : registre des sections attendues, contrôle de complétude (porte), route `GET /api/guide`. | INV-GUIDE-1, INV-LANGUE-1 | `test_guide.py`, `ui/scenario_guide.py` |
| `src/orchestrateur/langues.py` | Traduction des messages du serveur destinés à l'utilisateur : `t(cle, langue, **params)` sur les dictionnaires de `web/langues/`, langue réglée du processus, ligne de langue des consignes d'agent. | INV-LANGUE-1 | `test_langues.py`, `test_langues_serveur.py` |
| `src/orchestrateur/harnais/__init__.py` | Protocole d'un harnais et registre des adaptateurs. | INV-COMPACT-1, INV-TRAVAUX-1 | `test_harnais_cli.py`, `test_moteurs.py` |
| `src/orchestrateur/harnais/claude.py` | Adaptateur Claude Code : lancer un tour en `claude -p`, lire un transcript. | INV-CODESPACE-1, INV-COMPACT-1, INV-EXEC-3, INV-MCP-1, INV-NATIF-1, INV-RETOUR-1, INV-SESSION-1, INV-TRAVAUX-1 | `test_mcp.py`, `test_claude.py`, `test_claude_bruit.py`, `test_claude_hook.py`, `test_claude_tour.py`, `test_harnais_cli.py`, `test_retour.py` |
| `src/orchestrateur/harnais/agy.py` | Adaptateur Antigravity (`agy`) : un tour en `agy --output-format stream-json`, reprise par `--conversation` | INV-EXEC-3 | `test_agy.py` |
| `src/orchestrateur/harnais/distant.py` | Codespace par `gh` : liste, résolution, enveloppe `gh codespace ssh` d'un harnais distant. | INV-CODESPACE-1 | `test_codespace.py` |
| `src/orchestrateur/harnais/codex.py` | Adaptateur Codex CLI : un tour en `codex exec --json`, reprise par `codex exec resume <id>`. | INV-CODESPACE-1, INV-COMPACT-1, INV-EXEC-3, INV-TRAVAUX-1 | `test_harnais_cli.py`, `test_moteurs.py` |
| `src/orchestrateur/harnais/suivi.py` | Lecture des sous-agents et de la liste d'étapes dans le flux de Claude Code, OpenCode et Codex → `Evenement("suivi")`. | INV-TRAVAUX-1 | `test_travaux.py` |
| `src/orchestrateur/harnais/copilot.py` | Adaptateur GitHub Copilot CLI : un tour en `copilot -p … --output-format=json`, reprise par `--resume=<id>`. | INV-ECO-2, INV-EXEC-3 | `test_harnais_copilot.py` |
| `src/orchestrateur/harnais/opencode.py` | Adaptateur OpenCode : un tour en `opencode run --format json`, reprise par `-s <id>`. | INV-EXEC-3, INV-QUOTA-2, INV-TRAVAUX-1, INV-VIGIE-1 | `test_harnais_cli.py` |
| `src/orchestrateur/harnais/processus.py` | Processus d'un harnais en ligne de commande : résolution de l'exécutable, flux JSON par ligne, arrêt. | — | `test_harnais_cli.py` |
| `src/orchestrateur/index_notes.py` | Index des notes en mémoire : recherche plein texte, résolution, liens entrants, mentions non liées. | INV-GRAPHE-1, INV-NOTE-1, INV-NOTE-4 | `test_notes.py`, `test_graphe.py` |
| `src/orchestrateur/graphe.py` | Graphe du second cerveau (notes, tâches, conteneurs) en cache ; local et global filtré, plafonné. | INV-GRAPHE-1, INV-GRAPHE-2, INV-ETIQUETTE-3 | `test_graphe.py` |
| `src/orchestrateur/telegram_appairage.py` | Commande Telegram `/appairer` : code d'appareil ouvert par le connecteur, envoyé en image QR et lien, limité à 3 par 10 min. | INV-APPAIRAGE-2, INV-DISTANT-5 | `test_telegram.py` |
| `src/orchestrateur/telegram.py` | Connecteur Telegram : lecture longue, liste blanche, pièces et note de capture, tâche de tri (conversation), retours, routage des réponses, question en attente, boutons Valider / Renvoyer, fil commun avec le volet, commande `/appairer` | INV-APPAIRAGE-2, INV-EXEC-7, INV-MANAGER-1, INV-NOTE-1, INV-TELEGRAM-1, INV-TELEGRAM-2, INV-TELEGRAM-3, INV-TELEGRAM-4, INV-TELEGRAM-5, INV-VAULT-2 | `test_telegram.py` |
| `src/orchestrateur/telegram_connexion.py` | Connexion guidée d'un bot : discussions reconnues par `getUpdates` sans consommer, webhook actif détecté et levé, message de bienvenue, transcription d'une note vocale | INV-TELEGRAM-1, INV-TELEGRAM-2, INV-TELEGRAM-5 | `test_telegram.py` |
| `src/orchestrateur/telegram_assistant.py` | Assistant Telegram : étiquettes instruction / contenu, dernière tâche évoquée, lien d'interface, claviers de choix et de geste, application d'un geste confirmé, `/nouveau`, tâches proches d'une instruction (via `rapprochement`) | INV-DECISIONS-3, INV-LANGUE-1, INV-MANAGER-1, INV-RAPPROCHEMENT-1, INV-TELEGRAM-3, INV-TELEGRAM-4, INV-VAULT-3 | `test_telegram_assistant.py` |
| `src/orchestrateur/coffre.py` | Secrets du poste : variable d'environnement ou fichier du dossier de données (DPAPI sous Windows, 0600 ailleurs) | INV-TELEGRAM-2 | `test_telegram.py` |
| `src/orchestrateur/telegram_jeton.py` | Saisie sécurisée du jeton dans un terminal du poste (getpass, getMe, coffre) et ouverture du terminal (Windows, Linux, macOS) | INV-INSTALL-1, INV-TELEGRAM-2 | `test_telegram_jeton.py` |
| `src/orchestrateur/manager.py` | Volet « manager » : fil commun de l'assistant (journal, instruction du volet, bouton du volet), état dans le dossier de données | INV-MANAGER-1, INV-TELEGRAM-3, INV-TELEGRAM-4 | `test_manager.py` |
| `src/orchestrateur/api_manager.py` | Routes `/api/manager` : fil, message, bouton | INV-API-1, INV-MANAGER-1, INV-TELEGRAM-3 | `test_manager.py` |
| `src/orchestrateur/api_telegram.py` | Routes `/api/telegram` : réglages (section `[telegram]`), essai, reconnaissance, webhook, issue d'un envoi, question | INV-INSTALL-1, INV-INTERFACE-2, INV-NOTE-1, INV-TELEGRAM-1, INV-TELEGRAM-2, INV-TELEGRAM-5, INV-VAULT-3 | `test_telegram.py`, `ui/scenario_telegram.py` |
| `src/orchestrateur/etoile.py` | Invitation unique à mettre une étoile GitHub : usage cumulé, report, refus, sonde publique du dépôt. | INV-ETOILE-1 | `test_etoile.py` |
| `src/orchestrateur/api_etoile.py` | Routes `/api/etoile` : état, usage, réponse, réglage. | INV-API-1, INV-ETOILE-1 | `test_etoile.py` |
| `src/orchestrateur/resultat.py` | Voir le résultat : fichiers, site local et dossier produits par une tâche, ouverture par le système. | INV-RESULTAT-1, INV-LANGUE-1 | `test_resultat.py` |
| `src/orchestrateur/api_resultat.py` | Routes `/api/taches/{id}/resultat` : liste et ouverture (poste seulement). | INV-API-1, INV-RESULTAT-1 | `test_resultat.py` |
| `src/orchestrateur/jardinage.py` | Jardinage : revue de cohérence périodique, confiée à une tâche permanente. | INV-INTERFACE-1, INV-JARD-1, INV-JARD-2, INV-PLAFOND-1, INV-ETIQUETTE-3 | `test_jardinage.py`, `test_interface.py` |
| `src/orchestrateur/programme.py` | Programme d'une routine : écriture lisible ou cron à cinq champs → prochaine échéance (heure locale). | INV-ROUTINE-2 | `test_routines.py` |
| `src/orchestrateur/cli_chaines.py` | Commande `orch chaine` : plan, sauter, ajouter, dédoubler, changer une consigne (motif obligatoire). | INV-CHAINE-3 | `test_chaines.py` |
| `src/orchestrateur/routines.py` | Routines programmées : création, planificateur (échéances, rattrapage, jamais deux exécutions), pause, historique, annotation de l'arbre, échecs pour « Décisions ». | INV-ROUTINE-1, INV-ROUTINE-2, INV-ROUTINE-3, INV-ROUTINE-4, INV-ROUTINE-5, INV-VAULT-1 | `test_routines.py`, `ui/scenario_routines.py` |
| `src/orchestrateur/chaines.py` | Modèles de chaîne : lecture bornée des fichiers Markdown (intégrés `chaines/`, vault `_meta/chaines/`), écriture, retrait. Modèles intégrés : dossier `chaines/` du dépôt (Réponse à un appel d'offres, Article ou contenu), traduits sous `chaines/<langue>/`. | INV-CHAINE-2, INV-VAULT-1, INV-CHAINE-4, INV-LANGUE-1 | `test_chaines.py` |
| `src/orchestrateur/chaines_execution.py` | Exécution des chaînes : tâche parente et tâches de phase, enchaînement en série sur la fin des tours, validation humaine, reprise, ajustements de l'IA, surveillance d'un dossier. | INV-CHAINE-1, INV-CHAINE-3, INV-CHAINE-4, INV-VAULT-1, INV-REGROUPE-1 | `test_chaines.py` |
| `src/orchestrateur/scan.py` | Scan du système : préconisations d'optimisation (doublon, sommeil, sans place) classées par gain et par effort, déposées en propositions. | INV-SCAN-1 | `test_scan.py` |
| `src/orchestrateur/liens.py` | Liens fonctionnels entre tâches : `alimente` (orienté), `prerequis` (orienté, bloquant) et `voir_aussi` (symétrique). | INV-INTEG-2, INV-LIEN-1, INV-ORDO-1, INV-VAULT-1 | `test_liens.py`, `test_ordonnancement.py`, `test_propositions.py` |
| `src/orchestrateur/ordonnancement.py` | Ordonnancement de la file : attente des prérequis, classement unique a→e (créneau et pause), rang et motif publiés. | INV-EXEC-6, INV-ORDO-1, INV-ORDO-2 | `test_ordonnancement.py` |
| `src/orchestrateur/mise_a_jour.py` | Mise à jour de GoldenBrain depuis la branche de diffusion : contrôle, avance rapide, bascule de canal stable/bêta, commande. | INV-MAJ-1, INV-MAJ-2, INV-MAJ-3, INV-MAJ-4, INV-VERSION-2 | `test_mise_a_jour.py`, `test_collaboratif.py` |
| `src/orchestrateur/signalement.py` | Adresses des formulaires de ticket du dépôt public, pré-remplies de la version et du système. | INV-SIGNAL-1 | `test_collaboratif.py` |
| `src/orchestrateur/nouveautes.py` | Journal des nouveautés : entrées grand public tirées de l'historique git, `CHANGELOG.md`, « Quoi de neuf ». | INV-NOUV-1, INV-PUB-1 | `test_nouveautes.py`, `test_mise_a_jour.py` |
| `src/orchestrateur/echecs.py` | Message du système d'un tour en échec ; quota reconnu, heure de reprise. | INV-EXEC-1, INV-EXEC-8, INV-RESEAU-1, INV-REPRISE-1 | `test_echec_tour.py` |
| `src/orchestrateur/moteur.py` | Moteur d'exécution : files par tâche, tours, journal, fiche, messages, propositions. | INV-AGENTSCC-1, INV-ALIGN-2, INV-APPRENDRE-1, INV-COMPACT-1, INV-CONTROLE-1, INV-DECISIONS-2, INV-DECISIONS-3, INV-DISTANT-2, INV-ECO-1, INV-ECO-2, INV-EQUIPE-1, INV-EXEC-1, INV-EXEC-10, INV-EXEC-11, INV-EXEC-12, INV-EXEC-2, INV-EXEC-3, INV-EXEC-4, INV-EXEC-5, INV-EXEC-6, INV-EXEC-7, INV-EXEC-8, INV-EXEC-9, INV-EXECUTANT-1, INV-EXECUTANT-2, INV-INCIDENT-1, INV-INTERFACE-1, INV-LIEN-1, INV-MOTEUR-1, INV-MOTEUR-2, INV-MSG-1, INV-MSG-2, INV-NATIF-1, INV-ORDO-1, INV-ORDO-2, INV-PILOTAGE-1, INV-PILOTAGE-2, INV-PILOTAGE-3, INV-POSTE-1, INV-QUOTA-1, INV-REGROUPE-2, INV-REGROUPE-3, INV-RESEAU-1, INV-RETOUR-1, INV-RETOUR-3, INV-SESSION-1, INV-SIMULT-1, INV-TRANSFO-1, INV-TRAVAUX-1, INV-VALID-2, INV-VERROU-1, INV-REPRISE-1, INV-MAIN-2, INV-MAIN-4, INV-ETIQUETTE-3 | `test_moteur.py`, `test_bugs_usage.py`, `test_moteurs.py`, `test_revues.py`, `test_propositions.py`, `test_interface.py`, `test_roles.py` |
| `src/orchestrateur/m365.py` | Connecteur Microsoft 365 Copilot : code d'appareil, Work IQ Chat (`demander`), Retrieval (`contexte`), lecture seule. | INV-M365-1, INV-M365-2, INV-M365-3 | `test_m365.py` |
| `src/orchestrateur/natif.py` | Interface native du harnais : la tâche ouverte dans un onglet du terminal, relais à la fermeture. | INV-CODESPACE-2, INV-EXEC-6, INV-EXEC-7, INV-NATIF-1, INV-SESSION-1 | `test_natif.py`, `test_codespace.py` |
| `src/orchestrateur/quota.py` | Quota épuisé : comptes écartés jusqu'à leur reprise, choix du secours, bascule unique d'un tour de tâche. | INV-QUOTA-1, INV-ECO-1, INV-EXEC-10, INV-MOTEUR-1 | `test_quota.py` |
| `src/orchestrateur/incidents.py` | Incidents : cause lisible d'un échec ou arrêt, action menée, geste proposé ; persistance et exposition. | INV-INCIDENT-1 | `test_quota.py`, `ui/scenario_incidents.py` |
| `src/orchestrateur/reveil.py` | Réveil automatique sur quota épuisé : relance planifiée et persistée, annulation, journal de l'échec d'un tour. | INV-EXEC-8, INV-EXEC-10, INV-INCIDENT-1, INV-QUOTA-1, INV-EXEC-11, INV-EXEC-2, INV-EXEC-9, INV-NATIF-1 | `test_reveil_quota.py`, `test_echec_tour.py` |
| `src/orchestrateur/notes.py` | Notes du vault : chemins sûrs, liens, lecture et écriture d'une note. | INV-ALIGN-2, INV-NOTE-1, INV-NOTE-2, INV-NOTE-3, INV-VAULT-2 | `test_notes.py`, `test_api_notes.py` |
| `src/orchestrateur/controle.py` | Contrôle requis (R2) : commande `controle:` du contexte, lancée à la fin d'un tour déclaré `terminee` sous réservation du poste ; verdict persisté, référence de l'état vérifié, péremption. | INV-CONTROLE-1, INV-EXEC-6, INV-EXEC-7, INV-POSTE-1 | `test_controle.py` |
| `src/orchestrateur/poste.py` | Réservation du poste pendant une porte lourde : titulaire unique, persistance, expiration, file d'attente ordonnée, attente des tâches `epreuves: lourdes`. | INV-DISTANT-2, INV-EXECUTANT-1, INV-ORDO-1, INV-ORDO-2, INV-POSTE-1, INV-RESEAU-1 | `test_poste.py`, `ui/scenario_poste.py` |
| `src/orchestrateur/poste_ram.py` | Mesure de la RAM et du processeur du poste ; suspension, reprise et vidage de la mémoire de travail d'un arbre de processus (ctypes ; `/proc/meminfo` ailleurs). | INV-SIMULT-1, INV-TRAVAUX-2, INV-VIGIE-1 | `test_simultanes.py` (poste simulé), essai réel `scripts/essai_pause_ram.py` |
| `src/orchestrateur/propositions.py` | Propositions d'agent : persistance et gestes d'acceptation (INV-EXEC-5). | INV-ARBRE-2, INV-EXEC-5, INV-INTERFACE-3, INV-JARD-2, INV-SCAN-1, INV-RENOMMER-2, INV-RATTACHER-1, INV-DEJAFAIT-1, INV-LIEN-2, INV-INTEG-2, INV-NATURE-1, INV-PLAFOND-1, INV-RAPPROCHEMENT-1, INV-PROP-1, INV-LIGNES-1, INV-ETIQUETTE-2, INV-ETIQUETTE-3 | `test_propositions.py`, `test_audit_cli.py`, `test_moteur.py`, `test_scan.py` |
| `src/orchestrateur/annulation.py` | Annulation d'un geste de routine appliqué d'office : état antérieur, restauration. | INV-PROP-1, INV-VAULT-1 | `test_gestes_office.py` |
| `src/orchestrateur/lot_statuts.py` | Changement en bloc (statut, échéance, parent) : plan validé avant écriture, tout ou rien, trace, annulation. | INV-LOT-1, INV-VERROU-1, INV-VAULT-4, INV-EXEC-11, INV-ETIQUETTE-1 | `test_lot_statuts.py` |
| `src/orchestrateur/api_lots.py` | Routes `/api/lots` et `/api/lots/{id}/annuler` ; refus des requêtes d'agent. | INV-LOT-1, INV-DISTANT-7, INV-ETIQUETTE-1 | `test_lot_statuts.py` |
| `src/orchestrateur/rattachement.py` | Garde-fous et geste « rattacher » un lot de tâches sous un parent. | INV-RATTACHER-1, INV-PLAFOND-1, INV-NATURE-1, INV-VERROU-1 | `test_rattachement.py` |
| `src/orchestrateur/propagation.py` | Propagation `alimente` en fin de tour réussi (partie du moteur). | INV-LIEN-1, INV-MSG-1, INV-MSG-2 | `test_moteur.py`, `test_liens.py` |
| `src/orchestrateur/regroupement.py` | Exécution par tâche ou regroupée sous la mère : réglage hérité, règle automatique, acheminement, fiche d'une sous-tâche, repère. | INV-REGROUPE-1, INV-REGROUPE-2, INV-REGROUPE-3, INV-CONTROLE-1, INV-EXEC-10, INV-EXEC-7, INV-SIMULT-1, INV-ORDO-2, INV-VAULT-1 | `test_regroupement.py`, `ui/scenario_execution.py` |
| `src/orchestrateur/api_execution.py` | Routes `/api/execution` et `/api/taches/{id}/fiche-regroupee`. | INV-REGROUPE-1, INV-REGROUPE-2 | `test_regroupement.py` |
| `src/orchestrateur/depot.py` | Dossier de travail d'une tâche : dépôt déclaré par son projet, repli sur la table des projets externes. | INV-CONTROLE-1, INV-DEPOT-1, INV-INTEG-2 | `test_depot.py` |
| `src/orchestrateur/recherche.py` | Recherche plein texte des tâches : titre, fiche, fil d'Ariane. | INV-PILOTAGE-1, INV-ETIQUETTE-3 | `test_recherche.py` |
| `src/orchestrateur/rapprochement.py` | Rapprochement avant création : tâches proches, score et seuil fort, mesure des créations évitées. | INV-RAPPROCHEMENT-1, INV-RAPPROCHEMENT-2, INV-PILOTAGE-1, INV-ETIQUETTE-3 | `test_rapprochement.py` |
| `src/orchestrateur/api_rapprochement.py` | Routes du rapprochement et garde de `POST /api/taches` (409 + candidates, forcer, compléter, mesure). | INV-INTEG-2, INV-RAPPROCHEMENT-1, INV-RAPPROCHEMENT-2, INV-NATURE-1, INV-PLAFOND-1, INV-ETIQUETTE-2 | `test_rapprochement.py` |
| `src/orchestrateur/etiquettes.py` | Étiquettes libres : normalisation, lecture/écriture de `etiquettes:`, registre des consignes, tâches liées par étiquette, texte joint au tour. | INV-ETIQUETTE-1, INV-ETIQUETTE-2, INV-ETIQUETTE-3, INV-PILOTAGE-1, INV-VAULT-1 | `test_etiquettes.py` |
| `src/orchestrateur/api_etiquettes.py` | Routes `/api/etiquettes` (liste, consigne, renommer/fusionner, supprimer) et `POST /api/taches/{id}/etiquettes` (agent : étiquette connue seulement). | INV-ETIQUETTE-1, INV-ETIQUETTE-2, INV-LOT-1 | `test_etiquettes.py` |
| `src/orchestrateur/cli_etiquettes.py` | `orch etiqueter <id> +mot -mot`, `orch etiquettes`, rendu des étiquettes dans `lire` et `arbre`. | INV-ETIQUETTE-2, INV-ETIQUETTE-3 | `test_etiquettes.py` |
| `src/orchestrateur/pilotage.py` | Chat de projet : tâche de pilotage d'un nœud, amorçage de chaque tour, remontée des descendantes. | INV-PILOTAGE-1, INV-PILOTAGE-2, INV-PILOTAGE-3, INV-VAULT-3 | `test_pilotage.py` |
| `src/orchestrateur/references.py` | Réécriture des références à des chemins déplacés (dossiers ou fichiers) dans un texte. | — | `test_references.py` |
| `src/orchestrateur/reprise_auto.py` | Reprise d'office d'un tour interrompu (RAM, redémarrage, erreur d'API passagère) : compte, plafond de trois, signalement. | INV-REPRISE-1, INV-REPRISE-2, INV-SIMULT-1 | `test_reprise_auto.py`, `test_audit_poste.py` |
| `src/orchestrateur/etape.py` | Enregistrement d'étape : arbre de travail et branche notés à l'arrêt, rappelés à la reprise ; consigne de commit d'étape. | INV-REPRISE-2 | `test_reprise_auto.py` |
| `src/orchestrateur/prechauffage.py` | Préchauffage du premier écran au démarrage (index, arbre, état global, catalogue des moteurs, contrôle de mise à jour), lecture seule, bornée. | INV-FROID-1 | `test_prechauffage.py`, `ui/scenario_reactivite.py` |
| `src/orchestrateur/reprise.py` | Reprise d'un tour interrompu (par incident) et file persistée : automatique après un redémarrage du serveur, ou sur « Relancer ». | INV-EXEC-1, INV-EXEC-9, INV-REPRISE-1 | `test_reprise.py`, `test_api.py`, `test_moteur.py` |
| `src/orchestrateur/relance_fiche.py` | Fiche absente ≠ question : une relance automatique de la fiche, puis `bloque` motivé ; compteur. | INV-EXEC-12 | `test_moteur.py` |
| `src/orchestrateur/points.py` | Points de restauration du code : instantané git hors branche avant un tour, plan à blanc, restauration tout ou rien. | INV-RETOUR-3 | `test_retour.py` |
| `src/orchestrateur/retour.py` | Modifier un message envoyé : tours d'une tâche, plan, retour au point ou repli par transcription, archive de la fin, versions, point avant chaque tour. | INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3 | `test_retour.py`, `ui/scenario_modifier.py` |
| `src/orchestrateur/vigie.py` | Signe de vie des tours : écoute des événements, phrase d'activité, silence, exploration prolongée, raison d'attente, gestes (attendre, arrêter un descendant). | INV-EXEC-6, INV-SIMULT-1, INV-TRAVAUX-1, INV-VIGIE-1, INV-VIGIE-2 | `test_vigie.py`, `ui/scenario_vigie.py` |
| `src/orchestrateur/diagnostic.py` | Diagnostic d'un tour silencieux : descendants (CIM `Win32_Process`), processeur, phrase (hook, commande, modèle) ; arrêt d'un processus sur geste. | INV-VIGIE-1 | `test_vigie.py` (processus simulés) |
| `src/orchestrateur/api_vigie.py` | Routes `/api/taches/{id}/vigie` et enrichissement de `GET /etat` (`signe`, `raison`, `alertes_vigie`) ; `GET /api/incidents`. | INV-INCIDENT-1, INV-VIGIE-1, INV-VIGIE-2 | `test_vigie.py`, `test_quota.py` |
| `src/orchestrateur/api_travaux.py` | Écran « En cours » : `GET /api/travaux` (tours, sous-agents, avancement, file et raison, routines à venir, incidents ouverts) ; pause et reprise d'un tour à la main. | INV-TRAVAUX-1, INV-TRAVAUX-2 | `test_travaux.py`, `ui/scenario_travaux.py` |
| `src/orchestrateur/reseau.py` | Coupures réseau : classement des erreurs, sonde DNS+TCP tracée, gel des tours, reprise spontanée au retour (cadence 2 puis 5 min, sonde immédiate au réveil de veille), fournisseur seul en panne, durée de gel mesurée. | INV-EXEC-1, INV-EXEC-6, INV-INCIDENT-1, INV-ORDO-2, INV-POSTE-1, INV-RESEAU-1, INV-RESEAU-2, INV-RESEAU-3, INV-RESEAU-4 | `test_reseau.py`, `ui/scenario_reseau.py` |
| `src/orchestrateur/simultanes.py` | Agents simultanés : créneaux des tours (nombre fixe, optimisation, plafond de RAM), veille, pause et reprise, repli par remise en file. | INV-ALIGN-2, INV-EXEC-1, INV-EXEC-6, INV-MAJ-3, INV-ORDO-2, INV-POSTE-1, INV-SIMULT-1, INV-TRAVAUX-2, INV-REPRISE-1 | `test_simultanes.py`, `test_ordonnancement.py`, `test_verrou_deplacement.py` |
| `src/orchestrateur/compactage.py` | Compactage automatique : seuil et héritage, fenêtres par modèle, repli par ordre de compactage, journal de mesure et sa synthèse. | INV-COMPACT-1, INV-CONTROLE-1, INV-DISTANT-2, INV-ECO-1, INV-MCP-1 | `test_compactage.py`, `test_mcp.py` |
| `src/orchestrateur/revues.py` | Revues et validation : tours de persona, avis, renvois, verdict du validateur. | INV-ALIGN-2, INV-EQUIPE-1, INV-EXEC-4, INV-EXEC-5, INV-EXECUTANT-1, INV-INCIDENT-1, INV-MOTEUR-1, INV-MOTEUR-2, INV-VALID-1, INV-VALID-2 | `test_revues.py`, `test_roles.py` |
| `src/orchestrateur/roles.py` | Moteurs par rôle : quel harnais et quel modèle pour un tour assistant ou temporaire (repli journalisé) ; rôle `notes` en famille rapide par défaut | INV-ECO-1, INV-EXECUTANT-3, INV-MOTEUR-1, INV-MOTEUR-2, INV-QUOTA-1 | `test_roles.py`, `test_api.py`, `test_economie.py`, `test_notes_ia.py` |
| `src/orchestrateur/integration.py` | Pastille « intégration en retard » : branches gb/* citées par la fiche, lecture git seule, cache en arrière-plan. | INV-INTEG-1 | `test_integration.py` |
| `src/orchestrateur/instrumentation.py` | Instrumentation : attentes avant lancement (file, prérequis, poste, réseau, créneau), RSS et petits-fils du fils en fin de tour (`/proc`), contexte borné à la fenêtre. | INV-COMPACT-1, INV-POSTE-1, INV-ORDO-1, INV-RESEAU-2, INV-RESEAU-4 | `test_instrumentation.py` |
| `src/orchestrateur/session_perdue.py` | Repli d'une reprise sur une session inconnue du harnais : une relance en conversation neuve. | INV-SESSION-1 | `test_session_perdue.py` |
| `src/orchestrateur/sessions.py` | Mémoire des sessions par harnais, préambule de reprise, conversation relue dans les journaux. | INV-ECO-1, INV-EXEC-4, INV-EXEC-8, INV-PILOTAGE-3, INV-REGROUPE-2 | `test_moteurs.py`, `test_echec_tour.py` |, `test_pilotage.py`
| `src/orchestrateur/temps.py` | Le temps d'une tâche : échéance, priorité, retard, groupes de la vue « Aujourd'hui ». | INV-DECISIONS-3, INV-PILOTAGE-1, INV-TEMPS-1, INV-VAULT-1, INV-MAIN-4 | `test_temps.py` |, `test_pilotage.py`
| `src/orchestrateur/conso.py` | Mesure : jetons et coût par tour, fenêtres de quota par source (registres d'adaptateurs), cumul sur 31 jours. | INV-ECO-2 | `test_economie.py` |
| `src/orchestrateur/economie.py` | Curseur Performance ↔ Économie : profil → famille (intégration/fusion/rejeu de porte : modèle borné, délégué), alerte de contexte, escalade, curseur, mode intelligent, équilibrage, bascule proposée, motif. | INV-ECO-1, INV-ECO-2, INV-QUOTA-1 | `test_economie.py` |
| `src/orchestrateur/instrumentation.py` | Instrumentation : attentes avant lancement (file, prérequis, poste, réseau, créneau), RSS et petits-fils du fils en fin de tour (`/proc`), contexte borné à la fenêtre. | INV-COMPACT-1, INV-POSTE-1, INV-ORDO-1, INV-RESEAU-2, INV-RESEAU-4 | `test_instrumentation.py` |
| `src/orchestrateur/transformations.py` | Transformations assistées : promotion sur place avec découpage, réduction avec contraction. | INV-ALIGN-1, INV-ALIGN-2, INV-TRANSFO-1, INV-VAULT-2 | `test_transformations.py`, `test_reduction.py` |
| `src/orchestrateur/validation_auto.py` | Validation automatique par périmètre : réglage hérité, exclusions, relecteur indépendant, préalables, revue IA, journal, échantillon, « Rouvrir ». | INV-CONTROLE-1, INV-EXEC-5, INV-EXECUTANT-1, INV-VALID-1, INV-VALID-2, INV-VAULT-1 | `test_validation_auto.py`, `ui/scenario_validation_auto.py` |
| `src/orchestrateur/api_validation.py` | Routes `/api/validation-auto` : réglage d'un conteneur, réouverture. | INV-VALID-2 | `test_validation_auto.py` |
| `src/orchestrateur/vault.py` | Index du vault : tâches, conteneurs, création, déplacement (promotion : `transformations`). | INV-EXECUTANT-2, INV-PILOTAGE-1, INV-STATUT-1, INV-VAULT-1, INV-VAULT-2, INV-VAULT-3, INV-VAULT-4, INV-RENOMMER-1, INV-NATURE-1 | `test_vault.py`, `test_verrou.py`, `test_pilotage.py` |
| `src/orchestrateur/version.py` | Version du code servi : empreinte au démarrage, empreinte sur disque, redémarrage demandé ou différé. | INV-MAJ-3, INV-VERSION-1, INV-VERSION-2, INV-VERSION-3 | `test_version.py` |
| `src/orchestrateur/executant.py` | Curseur « Moi / IA » : champ `executant`, refus des tours et écritures d'agent sur une tâche menée par l'humain, notes de l'utilisateur (bloc géré), amorce des tours, « Confier la suite ». | INV-EXEC-9, INV-EXECUTANT-1, INV-EXECUTANT-2, INV-VAULT-1, INV-LIGNES-1 | `test_executant.py` |
| `src/orchestrateur/api_executant.py` | Routes `/api/taches/{id}/executant`, `/notes`, `/notes/{n}`, `/notes/ia`, `/confier`. | INV-EXECUTANT-1, INV-EXECUTANT-2, INV-EXECUTANT-3, INV-VAULT-1, INV-MAIN-5 | `test_executant.py`, `test_notes_ia.py` |
| `src/orchestrateur/notes_ia.py` | Bouton « IA » des notes : résumer, corriger, synthétiser la portée choisie, en proposition avec coût (aucune écriture). | INV-ECO-1, INV-ECO-2, INV-EXEC-4, INV-EXECUTANT-3, INV-MOTEUR-2 | `test_notes_ia.py` |
| `src/orchestrateur/verrou.py` | Verrous : occupation des tâches par un agent (seule définition), demi-verrou des gestes humains (409 `Occupee`), verrou des déplacements de dossiers | INV-ALIGN-2, INV-NATIF-1, INV-VERROU-1, INV-REGROUPE-3 | `test_demi_verrou.py`, `test_verrou_deplacement.py` |

## Interface (`web/`)

| Fichier | Rôle | INV-* cités | Tests |
|---|---|---|---|
| `web/alignement-plan.js` | dialogue du plan d'alignement (déplacements, réécritures avec exemples, références externes, avertissements), | INV-ALIGN-1, INV-ARBRE-2 | chargement par `ui/scenario_fumee.py` seulement |
| `web/alignement.js` | alignement des dossiers sur l'arbre — pastille du bandeau, panneau des écarts (cases à cocher), appel du plan. | INV-FROID-1 | chargement par `ui/scenario_fumee.py` seulement |
| `web/api.js` | client de l'API HTTP (/api) et flux SSE avec reconnexion ; rejeu avec `forcer` après confirmation d'un 409 `occupee`. | INV-API-1, INV-LANGUE-1, INV-VERROU-1, INV-VERSION-1 | `ui/scenario_fumee.py` (arbre, tâche, conversation) |
| `web/app.js` | point d'entrée — chargements, flux SSE, bannière d'erreurs, aiguillage du volet droit. | — | `ui/scenario_fumee.py` (arbre, tâche, conversation) |
| `web/arbre.js` | volet gauche — arbre repliable, pastille de statut courte, clavier, glisser-déposer ; applique `filtres.js`. | INV-ARBRE-2 | `ui/scenario_fumee.py` (arbre, tâche, conversation) |
| `web/decisions.js` | page « Décisions » du volet droit — une carte par décision, question en clair, gestes sur place, lot de validations. | INV-DECISIONS-1, INV-ROUTINE-4, INV-PROP-1 | `ui/scenario_decisions.py` |
| `web/decisions-agents.js` | Lignes « Agent Claude Code » de la page Décisions : choix rattacher / créer / ignorer, lot. | INV-AGENTSCC-1 | `ui/scenario_agents_cc.py` |
| `web/evitable.js` | section « Pastille « évitable ? » » des Réglages : activée, seuil. | INV-EVITABLE-1 | `ui/scenario_evitable.py` |
| `web/decisions.css` | Page « Décisions » : cartes, groupes de projet repliables, barre de lot. | — | `ui/scenario_decisions.py` |
| `web/aujourdhui.js` | vue « Aujourd'hui » du volet droit — en retard, dues aujourd'hui, dues dans les sept jours, puis « À moi ». | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/bandeau.js` | bandeau haut — tours en cours, compteurs (dont « Aujourd'hui »), déroulant des propositions, recherche, nouvelle tâche. | INV-DEROULANT-1 | chargement par `ui/scenario_fumee.py` seulement |
| `web/apercus.js` | aperçus déroulants de la barre haute (Aujourd'hui, Décisions, À moi, En cours) et pastille « Infos » des bandeaux d'information. | INV-DEROULANT-1 | `ui/scenario_deroulant.py` |
| `web/cascade.js` | vue en cascade du volet droit — sous-arbre des tâches en tableau indenté repliable, | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/conseil.js` | avis d'un agent rapide avant une promotion ou une réduction — attente annulable, dialogue « L'agent déconseille… ». | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/conversation.js` | rendu de la conversation d'une tâche — messages, tours, étapes à la demande, activité en direct. | INV-WEB-1 | `ui/scenario_fumee.py` (arbre, tâche, conversation), `ui/scenario_modifier.py` |
| `web/barre.css` | niveaux de repli de la barre haute : icônes, repère masqué, recherche resserrée, « + ». | INV-BARRE-1 | `ui/scenario_barre_haute.py` |
| `web/discussion.css` | mode discussion : grille à rail, barre d'une rangée, menu déroulant, notes en intercalaire | INV-DISCUSSION-1, INV-BARRE-1 | `ui/scenario_discussion.py` |
| `web/bandeaux.js` | Pile des bandeaux d'information : un seul à la fois (le plus urgent), les autres derrière « +N », détail au toucher. | INV-REACTIVITE-1 | `ui/scenario_reactivite.py` |
| `web/bandeaux.css` | Bandeaux sur une ligne tronquée, compteur « +N », cibles compactes au téléphone. | INV-REACTIVITE-1 | `ui/scenario_reactivite.py` |
| `web/paresseux.js` | Chargement à la demande (`import()`) des écrans, de la fiche de tâche et des services de fond : le premier affichage ne charge que ce qu'il montre. | INV-REACTIVITE-1 | `ui/scenario_reactivite.py` |
| `web/styles.liste` | Liste ordonnée des feuilles de style servies d'un tenant par `/style-tout.css`. | INV-REACTIVITE-1 | `test_styles.py` |
| `web/discussion.js` | mode discussion : barre haute d'une rangée, rail de l'arbre, menu, « Tout afficher » (disposition mémorisée par poste). | INV-DISCUSSION-1 | `ui/scenario_discussion.py` |
| `web/volet_largeur.js` | largeur réglable du volet des tâches : poignée tirée à la souris, au doigt ou au clavier, mémorisée par navigateur | INV-DISCUSSION-1 | `ui/scenario_accueil_rangee.py` |
| `web/deroulant.js` | composant déroulant unique : survol à délai d'intention, clic, clavier, toucher, Échap, clic extérieur, épingle ; `intention()` partagée par les rails. | INV-DEROULANT-1 | `ui/scenario_deroulant.py` |
| `web/deroulant.css` | mise en page du déroulant : panneau flottant, épingle, aperçus d'une ligne, feuille du bas au téléphone | INV-DEROULANT-1 | `ui/scenario_deroulant.py` |
| `web/detail.js` | volet droit — tâche sélectionnée (en-tête, actions, fiche, corps, conversation, saisie). | — | `ui/scenario_fumee.py` (arbre, tâche, conversation), `ui/scenario_console.py`, `ui/scenario_modifier.py` |
| `web/notes_tache.js` | panneau « Notes » de la tâche : liste datée en Markdown, ajout, « Modifier » ; repli des deux panneaux. | INV-EXECUTANT-2 | `ui/scenario_executant.py` |
| `web/notes_ia.js` | barre « IA » du panneau Notes : portée (sélection ou tout), proposition avec différence, Remplacer / Insérer / Annuler, annulation après application. | INV-EXECUTANT-3 | `ui/scenario_executant.py` |
| `web/executant.js` | curseur « 👤 Moi / 🤖 IA » de la tâche, pastille 👤, dialogue « Confier la suite ». | INV-EXECUTANT-1 | `ui/scenario_executant.py` |
| `web/modifier.js` | « Modifier » un message envoyé ou « Répondre à partir d'ici » sur une réponse de l'IA (plan, avertissement, case code, renvoi) et versions précédentes de la conversation. | INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3, INV-WEB-1 | `ui/scenario_modifier.py` |
| `web/dialogue.js` | boîte de dialogue à formulaire (<dialog> natif), réutilisée par tous les formulaires. | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/dom.js` | fabrique de nœuds DOM sûre (jamais d'innerHTML ici), libellés et temps relatif. | — | `ui/scenario_fumee.py` (arbre, tâche, conversation) |
| `web/equipe.js` | page « Équipe » du volet droit — personas : liste, création, édition, désactivation, retrait. | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/favicon.svg` | Icône | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/filtres.css` | Pastille de statut, barre de filtres et en-têtes de groupe. Mêmes variables de thème que style.css. | INV-ROUTINE-5 | `ui/scenario_filtres.py` |
| `web/lot.js` | Cases à cocher, Maj+clic, tout sélectionner, barre de changement en bloc, confirmation et annulation. | INV-LOT-1 | `ui/scenario_lot_statuts.py` |
| `web/etiquettes.js` | Étiquettes : puces, carte de « Détails » (saisie, complétion), réglage (consigne, renommer, annuler). | INV-ETIQUETTE-1, INV-ETIQUETTE-3 | `ui/scenario_etiquettes.py` |
| `web/main.js` | Pastille d'état unique, phrase, boutons « Confier à l'IA » / « Renvoyer à l'IA » avec consigne. | INV-MAIN-1, INV-MAIN-5 | `test_attente_muette.py` |
| `web/filtres.js` | barre de filtres combinables (statut, priorité, échéance, casquette/projet, harnais, IA, à moi), regroupement (statut, priorité, projet, échéance), tri priorité puis échéance, compteur, mémoire du navigateur. | INV-ROUTINE-5 | `ui/scenario_filtres.py` |
| `web/statut.js` | choix du statut d'une tâche : liste unique (détail : `<select>` ; arbre et cascade : menu sur la pastille), écriture par la route du détail, refus en ligne, bandeau « Annuler ». | — | `ui/scenario_statut_ligne.py` |
| `web/statut.css` | Pastille cliquable, menu des statuts, refus en ligne, bandeau d'annulation. | — | `ui/scenario_statut_ligne.py` |
| `web/filtres.css` | Pastille de statut, barre de filtres et en-têtes de groupe. Mêmes variables de thème que style.css. | — | `ui/scenario_filtres.py` |
| `web/filtres.js` | barre de filtres combinables (statut, priorité, échéance, casquette/projet, harnais, IA, à moi), regroupement (statut, priorité, projet, échéance), tri priorité puis échéance, compteur, mémoire du navigateur. | — | `ui/scenario_filtres.py` |
| `web/glisser.js` | arbre libre, code partagé par le volet gauche et la cascade — glisser-déposer, « monter d'un niveau », | INV-ARBRE-2, INV-WEB-1 | chargement par `ui/scenario_fumee.py` seulement |
| `web/routines.js` | Routines dans l'interface : pastille d'horloge de l'arbre, formulaire de création, bloc du détail (programme, pause, « Exécuter maintenant », historique). | INV-ROUTINE-2, INV-ROUTINE-5 | `ui/scenario_routines.py` |
| `web/chaines.js` | Chaînes dans l'interface : bouton « Chaînes », liste et éditeur des modèles (phases ajoutables, supprimables, réordonnables), « Lancer la chaîne sur… », bloc du détail d'une tâche parente ou de phase (phases et états, validation humaine, reprise, ajustements de l'IA). | INV-CHAINE-1, INV-CHAINE-3, INV-CHAINE-4 | `ui/scenario_chaines.py` |
| `web/manager.js` | Volet « manager » à droite : fil, saisie, boutons Confirmer / Annuler / choix, état mémorisé, chargé à l'ouverture seulement | INV-MANAGER-1, INV-WEB-1 | `ui/scenario_manager.py` |
| `web/manager.css` | Mise en page du volet « manager » : troisième colonne, par-dessus sous 900 px, plein écran sur téléphone | — | `ui/scenario_manager.py` |
| `web/telegram.js` | Section « Telegram » des Réglages : assistant en 6 étapes (bot, jeton par terminal sécurisé ou champ de repli, nom, discussion reconnue, webhook, test), aide à côté, réglages avancés repliés | INV-INSTALL-1, INV-TELEGRAM-2, INV-WEB-1 | `ui/scenario_telegram.py` |
| `web/telegram-aide.js` | Étapes de l'assistant Telegram et texte du panneau d'aide (quoi, pourquoi, si ça bloque) | INV-WEB-1 | `ui/scenario_telegram.py` |
| `web/etoile.js` | Invitation à l'étoile GitHub (fenêtre) et son interrupteur des Réglages. | INV-ETOILE-1 | `ui/scenario_etoile.py` |
| `web/resultat.js` | Bouton « Voir le résultat » et liste des éléments à ouvrir. | INV-RESULTAT-1 | `ui/scenario_resultat.py` |
| `web/interface.js` | État « interface » (mode simple / avancé, familles débrayées, politique des propositions) et ses applications à l'écran ; repli de la barre haute par niveaux | INV-INTERFACE-1, INV-WEB-1, INV-BARRE-1 | `ui/scenario_interface.py`, `ui/scenario_barre_haute.py` |
| `web/guide.js` | Écran « Guide » : rendu de `docs/GUIDE.md`, sommaire cliquable, recherche dans la page, ancres par section ; bouton « ? » contextuel. | INV-GUIDE-1, INV-LANGUE-1 | `ui/scenario_guide.py` |
| `web/langues.js` | Traduction de l'interface : langue réglée (ou détectée au premier lancement puis mémorisée), chargement de son seul dictionnaire, `t()`, `tn()`, `traduireDom()` (data-t*), `changerLangue()` (recharge la page). | INV-LANGUE-1 | `test_langues.py`, `ui/scenario_langues.py` |
| `web/garnir.js` | Insère des éléments DOM (lien, gras, code) dans une phrase traduite à la place de ses `{x}`, sans jamais passer par `innerHTML`. | INV-LANGUE-1 | `ui/scenario_langues.py` |
| `web/langues/fr.json` | Dictionnaire des libellés source (clés plates à points, triées), partagé par l'interface et le serveur. | INV-LANGUE-1 | `test_langues.py` |
| `web/langues/en.json` | Dictionnaire des libellés (clés plates à points, triées), partagé par l'interface et le serveur. | INV-LANGUE-1 | `test_langues.py` |
| `web/langues/de.json` | Dictionnaire des libellés (clés plates à points, triées), partagé par l'interface et le serveur. | INV-LANGUE-1 | `test_langues.py` |
| `web/langues/es.json` | Dictionnaire des libellés (clés plates à points, triées), partagé par l'interface et le serveur. | INV-LANGUE-1 | `test_langues.py` |
| `web/index.html` | Page unique : charge les modules ES | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/info.js` | ligne d'information flottante (#info-geste) partagée par les gestes d'arbre, la promotion et la réduction. | INV-WEB-1 | chargement par `ui/scenario_fumee.py` seulement |
| `web/liens.js` | liens fonctionnels d'une tâche — carte « Liens » du volet droit et dialogue « Lier… » (recherche de la cible). | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/lot7.css` | Styles du serveur à jour, des étapes à la demande, du rattachement, de la promotion et de la réduction (mêmes variables de thème que style.css) | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/maj.js` | bandeau « Une mise à jour est disponible » (branche de diffusion en avance sur le dépôt local, ou bascule de canal), son « Quoi de neuf » et geste « Mettre à jour ». | INV-MAJ-1, INV-MAJ-4, INV-NOUV-1 | chargement par `ui/scenario_fumee.py` seulement |
| `web/md.js` | rendu Markdown maison — notes du vault, fiches et conversations d'agents. Frontières : renvoie du HTML. | INV-WEB-1 | `ui/scenario_fumee.py` (arbre, tâche, conversation) |
| `web/codespace.js` | bloc « codespace » de l'en-tête d'une tâche : état, VS Code, navigateur, arrêt, réglage « Où ». | — | `ui/scenario_codespace.py` |
| `web/moteur.js` | sélecteur de moteur (harnais + modèle) d'une tâche, d'après GET /harnais. | INV-MOTEUR-1 | chargement par `ui/scenario_fumee.py` seulement |
| `web/note-edition.js` | éditeur de texte brut d'une note (textarea à chasse fixe), enregistrement, protection des modifications, conflit 409. | INV-NOTE-2 | chargement par `ui/scenario_fumee.py` seulement |
| `web/note-gestes.js` | gestes sur les notes qui passent par un formulaire — créer, renommer / déplacer. | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/note-vue.js` | volet droit — lecture d'une note (fil d'Ariane, propriétés, corps rendu, liens entrants, mentions non liées, boutons). | INV-NOTE-4 | `ui/scenario_notes.py`, `ui/scenario_graphe.py` |
| `web/notes-liees.js` | bloc « Notes liées » du détail d'une tâche (cite, mentionnée par, mentions non liées). | INV-NOTE-4 | `ui/scenario_graphe.py` |
| `web/graphe.js` | volet droit — vue graphe en canvas (local, global filtré, recherche, clic d'ouverture). | INV-GRAPHE-2 | `ui/scenario_graphe.py` |
| `web/notes.css` | Lots 5 et 6 — notes du vault, recherche, alignement. Mêmes variables de thème que style.css. | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/notes.js` | volet gauche, onglets « Tâches » / « Notes » et arborescence des dossiers du vault (un niveau par requête). | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/pilotage.js` | accès à la conversation d'un conteneur depuis sa vue en cascade (bouton « Conversation », premier message). | INV-PILOTAGE-1 | `ui/scenario_pilotage.py` |
| `web/execution.js` | réglage « Exécution » d'une tâche mère ou d'un conteneur ; motif de la décision sur une sous-tâche. | INV-REGROUPE-1 | `ui/scenario_execution.py` |
| `web/ponts.js` | ponts entre tâches et notes — clic sur un wikilink ou un chemin de note (fiches, conversations, notes), | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/propositions.js` | propositions d'agent groupées par tâche émettrice, une ligne chacune (accepter / refuser), partagées par le panneau, l'accueil et la page Décisions. | INV-EXEC-5, INV-PROP-2 | `ui/scenario_propositions_compactes.py` |
| `web/propositions.css` | Propositions compactes : groupe replié d'une ligne, ligne de 30 px, boutons icônes. | INV-PROP-2 | `ui/scenario_propositions_compactes.py` |
| `web/recherche.js` | champ de recherche du bandeau — filtre de l'arbre des tâches (existant) + liste déroulante à deux groupes | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/resultats.js` | page de résultats de la recherche plein texte dans les notes (volet droit) — extraits, termes surlignés, n° de ligne. | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/revues.js` | carte « Revues » d'une tâche (dernier avis par persona) et dialogue « Solliciter… ». | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/reglages.css` | Mode simple / avancé : une famille débrayée masque ses éléments (classes posées sur `<body>` par `interface.js`) ; groupes repliables, résumés et recherche des Réglages | INV-REGLAGES-1 | `ui/scenario_interface.py`, `ui/scenario_reglages.py` |
| `web/reglages.js` | Page « Réglages » du volet droit : six groupes repliables par intention avec résumé d'état, ancre `#reglages/<section>`, recherche ; bascule Simple / Avancé, thème, un interrupteur par famille, politique des propositions | INV-REGLAGES-1, INV-PROP-1 | `ui/scenario_reglages.py`, `ui/scenario_interface.py`, `ui/scenario_design.py` |
| `web/economie.js` | Section « Performance ↔ Économie de jetons » des Réglages, repère de l'en-tête, moteur prévu et bascule dans le détail | INV-ECO-1, INV-ECO-2 | `ui/scenario_economie.py` |
| `web/incidents.js` | Panneau « Incidents » du bandeau (jauge par compte, liste) et bandeau de cause dans la conversation | INV-INCIDENT-1 | `ui/scenario_incidents.py` |
| `web/vigie.js` | Ligne d'activité de la tâche ouverte, alertes du bandeau (silence, exploration), gestes | INV-VIGIE-1, INV-VIGIE-2 | `ui/scenario_vigie.py` |
| `web/travaux.js` | Écran « En cours » : cartes des tours (dernière action, avancement, aides), file, routines, incidents ; ouvrir, pause, arrêt confirmé ; libellés regroupés | INV-TRAVAUX-1, INV-TRAVAUX-2 | `ui/scenario_travaux.py` |
| `web/simultanes.js` | Section « Agents simultanés » des Réglages : trois modes exclusifs, état mesuré du poste et des pauses | INV-SIMULT-1 | `ui/scenario_simultanes.py` |
| `web/executeurs.js` | Section « PC connectés » des Réglages : exécuteurs, mémoire, tours en cours ou en attente, code d'appairage, jeton montré une fois, révocation, état des prérequis par PC et bouton Réparer | INV-APPAIRAGE-1, INV-DISTANT-1, INV-DISTANT-4, INV-INSTALL-4 | `ui/scenario_executeurs.py` |
| `web/appareils.js` | Section « Appareils » des Réglages : état de l'accès distant, avertissement sans HTTPS, code QR de Tailscale, « Ajouter un téléphone » (code QR), liste, révocation, journal | INV-DISTANT-5, INV-DISTANT-6, INV-DISTANT-7, INV-DISTANT-8 | `ui/scenario_appareils.py` |
| `web/appairer.html` | Page d'appairage ouverte par le code QR : échange le code du fragment contre le cookie, puis ouvre l'interface | INV-DISTANT-5 | `test_appareils.py`, `ui/scenario_appareils.py` |
| `web/appairer.js` | Page d'appairage ouverte par le code QR : échange le code du fragment contre le cookie, puis ouvre l'interface | INV-DISTANT-5 | `test_appareils.py`, `ui/scenario_appareils.py` |
| `web/compactage.js` | Section « Compactage automatique » des Réglages : seuil et plafond, mécanisme par harnais, vue de mesure. | INV-COMPACT-1 | `ui/scenario_compactage.py` |
| `web/integration.js` | Pastille « intégration en retard » de l'arbre et section « Intégration des branches » des Réglages. | INV-INTEG-1 | `ui/scenario_integration.py` |
| `web/store.js` | état partagé de l'interface et petit bus d'événements (découple les modules). | — | `ui/scenario_fumee.py` (arbre, tâche, conversation) |
| `web/style.css` | GoldenBrain — interface. Sobre, dense, sans dégradé. Jetons de design (couleurs `light-dark()`, rayons, espacements, durée), thème clair/sombre, écran étroit (≤ 900 px), repère « IA au travail ». | INV-VERROU-1 | `ui/scenario_demi_verrou.py`, `ui/scenario_design.py` |
| `web/theme.js` | Applique le thème choisi (`orch.theme` en localStorage) avant le premier rendu ; script classique bloquant, la CSP interdisant le script en ligne | — | `ui/scenario_design.py`, `ui/scenario_affichage.py` |
| `web/affichage.css` | Affichage par défaut « sobre éditorial », chargé en dernier : filets fins, titres à empattement, barre haute sombre et ses menus au thème de la page, action à l'encre | INV-AFFICHAGE-1 | `test_affichage.py`, `ui/scenario_affichage.py` |
| `web/ecrans.css` | Cohérence de mise en page entre écrans (audit L4) : bandeau en deux rangées, gouttière commune, Guide, modale « Nouvelle tâche » bornée, colonnes du tableau | — | `ui/scenario_ecrans_audit.py` |
| `web/telephone.css` | Mise en page téléphone (≤ 480 px) : une colonne, barre basse, tâche en plein écran avec onglets Conversation / Notes, cibles tactiles ≥ 44 px ; écrans sans survol | — | `ui/scenario_telephone.py` |
| `web/telephone.js` | Usage au téléphone : barre basse (Tâches, Décisions, Recherche, Réglages), écran liste ou détail (`body[data-ecran]`), enregistrement du service worker | INV-PWA-1 | `ui/scenario_telephone.py` |
| `web/sw.js` | Service worker de l'application installable : réseau d'abord, cache des seuls fichiers statiques de même origine | INV-PWA-1 | `ui/scenario_telephone.py` |
| `web/manifest.json` | Manifeste de l'application installable (`standalone`, icônes, couleurs) | — | `ui/scenario_telephone.py` |
| `web/icone-192.png` | Icône 192 px de l'application installable, rendue depuis `favicon.svg` | — | `ui/scenario_telephone.py` |
| `web/icone-512.png` | Icône 512 px de l'application installable, rendue depuis `favicon.svg` | — | `ui/scenario_telephone.py` |
| `web/temps.css` | Le temps : colonnes Échéance et Priorité, retard, édition en place, vue « Aujourd'hui ». Mêmes variables de thème que style.css. | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/temps.js` | le temps d'une tâche côté interface — libellés d'échéance et de priorité, cellules, tri, édition en place. | — | chargement par `ui/scenario_fumee.py` seulement |
| `web/renommer.js` | Renommer une tâche depuis sa fiche : clic sur le titre, champ éditable (Entrée valide, Échap annule). | INV-RENOMMER-1, INV-WEB-1 | `ui/scenario_renommer.py` |
| `web/transfo.js` | promotion d'une tâche en projet (avec découpage par l'agent) et réduction d'un projet en tâche (avec contraction). | INV-TRANSFO-1 | chargement par `ui/scenario_fumee.py` seulement |
| `web/verrou.js` | demi-verrou côté interface — repère « IA au travail », compteur « IA : n » des ancêtres, dialogue de confirmation d'un 409 `occupee`. | INV-VERROU-1 | `ui/scenario_demi_verrou.py` |
| `web/version.js` | serveur à jour — bandeau persistant quand le code sur disque est plus récent que celui qui tourne, | INV-VERSION-1 | chargement par `ui/scenario_fumee.py` seulement |
| `web/maj-auto.js` | Mise à jour : canal stable/bêta et mode automatique (Réglages), bandeaux, battement d'activité | INV-MAJ-3, INV-MAJ-4 | `ui/scenario_maj_auto.py` |
| `web/signaler.js` | Réglages → « Signaler un problème ou proposer une idée » : liens vers les formulaires GitHub pré-remplis | INV-SIGNAL-1 | `test_collaboratif.py` (adresses) |

## Scripts et racine

| Fichier | Rôle | INV-* cités | Tests |
|---|---|---|---|
| `orch.py` | Point d'entrée de la commande `orch` (lance `orchestrateur.cli`) | — | `test_cli.py` (le client, pas le lanceur) |
| `scripts/revue_contributions.py` | Revue des contributions par IA : demandes à relire, dossier de revue (diff en texte), commentaire P1/P2/P3 publié sur confirmation | INV-REVUE-1 | `test_collaboratif.py` |
| `scripts/etiquettes.py` | Étiquettes standard du dépôt public (`gh label create --force`), `--essai` pour voir sans envoyer | — | `test_collaboratif.py` |
| `scripts/check.py` | Porte unique : pytest + contrôles de structure et de cette carte + garde de publication (INV-PUB-1) + syntaxe des modules `web/*.js` (node --check en .mjs) + encodage explicite de toute lecture/écriture texte | INV-LANGUE-1 | — (la porte se vérifie elle-même : sortie rouge si un contrôle échoue) |
| `scripts/dictionnaires.py` | Contrôle des dictionnaires (mêmes clés et paramètres, clés citées existantes, aucun libellé en dur dans `web/`) ; outil `ajouter` / `normaliser` / `reste` des traducteurs. | INV-LANGUE-1 | `test_langues.py` |
| `scripts/langues_exceptions.txt` | Libellés visibles volontairement hors dictionnaire, chacun motivé. | INV-LANGUE-1 | — |
| `scripts/construction.py` | Briques communes des constructions « un clic » : composants épinglés et vérifiés, Python portable, dépendances de la plateforme cible, graine git, icônes ICO/ICNS ; lanceurs, gabarits et composants épinglés dans `installation/`. | INV-PAQUET-1, INV-PAQUET-2 | `test_installation_un_clic.py` |
| `scripts/construire_deb.py` | Construit `build/goldenbrain_<version>_amd64.deb` (Debian, Ubuntu) : Python embarqué sous `/opt/goldenbrain`, graine, menu, icônes (hors porte). | INV-PAQUET-1 | essai réel (fiche de la tâche) |
| `scripts/construire_windows.py` | Construit `build/GoldenBrain-installation.exe` : Python et MinGit portables, graine CRLF, Inno Setup sous wine (hors porte). | INV-PAQUET-1 | essai sous wine (fiche de la tâche) |
| `scripts/construire_macos.py` | Construit `build/GoldenBrain-macos-<arch>.zip` (GoldenBrain.app non signée) (hors porte). | INV-PAQUET-1 | `test_installation_un_clic.py` (icône) |
| `scripts/publier_version.py` | Publie une version GitHub : construit les quatre installateurs, note en anglais, français, espagnol, allemand (nouveautés depuis la version précédente, retrouvée par son arbre), `gh release create` seulement avec `--envoyer` (hors porte). | INV-NOUV-1, INV-PUB-1 | `test_publier_version.py` |
| `scripts/check_ui.py` | Lance les scénarios d'interface sur le vrai serveur (hors porte) | — | `ui/scenario_fumee.py` |
| `scripts/captures.py` | Captures et vidéo du README : rejoue `ui/scenario_captures.py` dans les quatre langues et dépose images et vidéos dans `docs/captures/` (hors porte) | — | `ui/scenario_captures.py` |
| `scripts/verrou.py` | Verrou d’exemplaire unique (fcntl/msvcrt) : une seule porte d’interface à la fois | — | `test_arbre_verrou.py` |
| `scripts/porte.py` | Porte complète avec reçu signé de l'arbre testé (`lancer`) et son contrôle (`verifier`), pour que la CI ne rejoue pas une suite déjà validée | INV-PORTE-1 | `test_porte_recu.py` |
| `tests/test_porte_recu.py` | Reçu de porte : arbre exact, signature, 24 h, arbre sale, porte rouge | INV-PORTE-1 | — |
| `scripts/nouveautes.py` | Nouveautés d'une version publiée : `CHANGELOG.md`, note de version, commande `gh release create` (exécutée seulement avec `--envoyer`) | INV-NOUV-1 | `test_nouveautes.py` |
| `tests/test_arbre_verrou.py` | Arrêt de l’arbre (petit-fils tué) et verrou de check_ui | — | — |
| `scripts/essai_pause_ram.py` | Essai réel sur le poste (hors porte) : un agent factice suspendu puis repris, mémoire de travail mesurée avant et après | INV-SIMULT-1 | — |
| `scripts/epreuve_alignement.py` | Épreuve réelle (hors porte) : alignement d'un dossier sur une copie partielle du vault | INV-ARBRE-2 | — |
| `scripts/epreuve_revue.py` | Épreuve réelle (hors porte, payante) : revue planifiée de cohérence | — | — |
| `scripts/epreuve_persona.py` | Épreuve réelle de la validation par persona (hors porte, payante) | — | — |

## Tests (`tests/`)

| Fichier | Rôle | INV-* cités | Tests |
|---|---|---|---|
| `tests/conftest.py` | Fixtures : vault temporaire, configuration de test, harnais factice (jamais de vrai claude). | — | — |
| `tests/test_alignement.py` | alignement physique : dossiers attendus, écarts, plan, application tout ou rien. | INV-ALIGN-2, INV-ARBRE-2 | — |
| `tests/test_api.py` | API via TestClient : garde INV-API-1, formes JSON, 400/404/409, flux d'un tour. | INV-API-1, INV-EXEC-1, INV-VAULT-3 | — |
| `tests/test_affichage.py` | Affichage par défaut : contrastes AA clair et sombre (barre haute comprise), accent unique et dérivés, action à l'encre, sobriété de la surcouche, plus de direction d'essai. | INV-AFFICHAGE-1 | — |
| `tests/test_styles.py` | Feuille unique : toute feuille de `web/` est dans la liste, `index.html` n'en cite qu'une, assemblage ordonné et ETag. | INV-REACTIVITE-1 | — |
| `tests/test_api_notes.py` | Routes `/api/vault/*` via TestClient : formes, erreurs, écriture, SSE, fichiers. | INV-ALIGN-2, INV-NOTE-3, INV-VERROU-1 | — |
| `tests/test_agy.py` | Adaptateur Antigravity (`agy`) : faux exécutable Python (jamais le vrai CLI) et extraits réels | — | — |
| `tests/test_arbre.py` | arbre libre : chemins `A > B`, conteneur sous conteneur, cycles, gestes, INV-ARBRE-1. | INV-ARBRE-1, INV-ARBRE-2, INV-VAULT-1 | — |
| `tests/test_bugs_usage.py` | Défauts relevés à l'usage (14/11) : INV-EXEC-6, INV-EXEC-7, mandat sans tour, conversation. | INV-EXEC-6, INV-EXEC-7 | — |
| `tests/test_mcp.py` | MCP strict par défaut : argv avec et sans `--strict-mcp-config` selon réglage et frontmatter. | INV-MCP-1 | — |
| `tests/test_claude.py` | Adaptateur Claude : flux stream-json (faux exécutable Python, jamais le vrai claude), transcript. | — | — |
| `tests/test_claude_bruit.py` | Le transcript Claude ne présente pas à l'utilisateur les messages que le harnais s'adresse à lui-même. | — | — |
| `tests/test_claude_hook.py` | Un hook de fin de session fait écrire à l'agent un second message : il n'est pas la réponse. | — | — |
| `tests/test_codespace.py` | Codespace : déclaration, état, gestes, exécution distante claude et codex, harnais absent (faux `gh` Python). | INV-CODESPACE-1, INV-CODESPACE-2 | — |
| `tests/test_claude_tour.py` | Texte de fin de tour de l'adaptateur Claude : le tour entier, pas le seul dernier message. | — | — |
| `tests/test_console.py` | Console en terminal contre un vrai serveur et le harnais factice : message visible côté API, fermeture sans arrêt du tour, `/arret`, onglet `wt`. | INV-CONSOLE-1 | — |
| `tests/test_m365.py` | Connecteur Microsoft 365 contre un serveur HTTP factice : code d'appareil, jeton chiffré et renouvelé, réponse et citations, extraits, lecture seule, désactivé par défaut, jeton hors dépôt. | INV-M365-1, INV-M365-2, INV-M365-3 | — |
| `tests/test_audit_cli.py` | Audit L2 : erreurs, plafonds et codes de sortie de `orch`, propositions et gestes (un test par constat). | — | — |
| `tests/test_cli.py` | Commande `orch` : requêtes émises, sauts incrémentés, délégation, rendu texte, code de retour. | — | — |
| `tests/test_config.py` | Chargement de la configuration : fusion des écarts sur l'exemple. | — | — |
| `tests/test_contraste_bordures.py` | `--bord-fort` à 3:1 contre les fonds dans les deux thèmes (WCAG 1.4.11). | — | — |
| `tests/test_conseil.py` | avis d'un agent rapide (`POST /conseil`), jamais d'écriture dans le vault. | — | — |
| `tests/test_equipe.py` | Équipe (fichiers de personas, filtre de déclenchement) et leurs routes. | INV-EQUIPE-1, INV-VAULT-4 | — |
| `tests/test_feux_verts.py` | Feu vert lié à une version (INV-FEU-1) : demande, accord, refus, sha exact, vérification. | INV-FEU-1 | — |
| `tests/test_garde_publication.py` | INV-PUB-1 : la garde reconnaît adresses, chemins de poste, identifiants de session, jetons ; admet les exemples fictifs ; lit `.sensible` ; avertit s'il manque. | INV-PUB-1 | — |
| `tests/test_fiches.py` | INV-VAULT-1 / INV-VAULT-2 : édition ligne à ligne, restitution octet pour octet, bloc fiche. | INV-VAULT-1, INV-VAULT-2 | — |
| `tests/test_geste.py` | INV-ARBRE-2 — le dossier fait foi : lecture de l'arbre par les dossiers, geste = vrai déplacement. | INV-ALIGN-3, INV-ARBRE-2 | — |
| `tests/test_harnais_copilot.py` | Adaptateur Copilot (faux exécutable) : argv, session choisie, reprise, modèle, prompt, arrêt, absence | INV-EXEC-3 | — |
| `tests/test_guide.py` | Guide : route en texte brut, `orch guide`, porte rouge si une section, une ancre ou la date manque. | INV-GUIDE-1 | — |
| `tests/test_langues.py` | Quatre langues : parité des dictionnaires, `t()` du serveur, détection d'un libellé en dur, réglage persisté, consigne d'agent, guides traduits. | INV-LANGUE-1 | — |
| `tests/test_langues_serveur.py` | Messages du serveur dans la langue réglée : erreur d'API, incident, accueil, Telegram (allemand). | INV-LANGUE-1 | — |
| `tests/test_harnais_cli.py` | Adaptateurs codex et opencode (faux exécutables Python, jamais les vrais CLI), Claude --model, | — | — |
| `tests/test_interface.py` | Mode simple / avancé : drapeaux par famille, routes en 409, persistance de `[interface]` | — | — |
| `tests/test_lignes.py` | Lignes, nature, plafond, rangement, jardinier, CLI, réflexes. | INV-LIGNES-1, INV-NATURE-1, INV-PLAFOND-1 | — |
| `tests/ui/scenario_livrables.py` | Pastille, volet, déclaration, attendu, agrégation parent, filtre. | INV-LIVRABLES-1, INV-DETAIL-1 | — |
| `tests/test_lecteur.py` | Lecteur : registre, traversée, liens symboliques, hors racines, isolement HTML, refus distant et agent, réglages. | INV-LECTEUR-1 | — |
| `tests/ui/scenario_lecteur.py` | Interface : clic sur un .md, un .html (isolé), un .docx (application). | INV-LECTEUR-1 | — |
| `tests/test_livrables.py` | Livrables : relevé d'office, dédoublonnage, agrégation parent, fichier disparu, distant, CLI. | INV-LIVRABLES-1 | — |
| `tests/ui/scenario_lignes.py` | Carte Lignes, nature, plafond et 409 de rangement. | INV-LIGNES-1, INV-NATURE-1, INV-PLAFOND-1 | — |
| `tests/test_apprendre.py` | Mode « Apprendre » : consigne seulement si actif, réglage de tâche prioritaire, champ de fiche `retenir`, routes. | INV-APPRENDRE-1 | — |
| `tests/test_statut_retour.py` | Statut de retour réglable : défaut neutre, nom invalide refusé, ancien nom déclaré reconnu, nom inconnu jamais pris pour le retour, nom transmis à l'interface. | INV-STATUT-1 | — |
| `tests/test_jardinage.py` | Jardinage : échéances (INV-JARD-1), tâche permanente, état persistant, configuration, plafond (INV-JARD-2). | INV-JARD-1, INV-JARD-2 | — |
| `tests/test_routines.py` | Routines avec horloge factice : analyse du programme, échéance, rattrapage unique ou aucun, jamais deux exécutions, pause, contexte neuf, échec dans « Décisions », API et arbre annoté. | INV-ROUTINE-1, INV-ROUTINE-2, INV-ROUTINE-3, INV-ROUTINE-4, INV-ROUTINE-5 | — |
| `tests/test_chaines.py` | Chaînes : lecture bornée des modèles (intégrés, vault, traduits), exécution en série, validation humaine, reprise, ajustements journalisés, surveillance d'un dossier, API et commande `orch chaine`. | INV-CHAINE-1, INV-CHAINE-2, INV-CHAINE-3, INV-CHAINE-4 | — |
| `tests/test_scan.py` | Scan du système : règles, classement gain puis effort, propositions toujours en attente, pas de reproposition, route. | INV-SCAN-1 | — |
| `tests/test_liens.py` | Liens fonctionnels (alimente, voir_aussi), INV-VAULT-1 sur ces clés, propagation INV-LIEN-1. | INV-LIEN-1, INV-MSG-1, INV-MSG-2, INV-VAULT-1 | — |
| `tests/test_ordonnancement.py` | Prérequis bloquant puis libéré seul, cycle refusé, ordre a→e et motifs, créneau au premier du classement, pause du moins prioritaire. | INV-ORDO-1, INV-ORDO-2 | — |
| `tests/test_mise_a_jour.py` | Mise à jour en un geste : INV-MAJ-1 (avance rapide seule, refus clairs), INV-MAJ-2 (git sans shell). | INV-MAJ-1, INV-MAJ-2 | — |
| `tests/test_collaboratif.py` | Cadre collaboratif : bascule de canal et refus, signalement sans donnée personnelle, formulaires et étiquettes accordés, outil de revue (rien publié sans confirmation). | INV-MAJ-4, INV-SIGNAL-1, INV-REVUE-1 | — |
| `tests/test_nouveautes.py` | Journal des nouveautés (INV-NOUV-1) : entrées, CHANGELOG.md, « Quoi de neuf », script de publication. | INV-NOUV-1 | — |
| `tests/test_maj_auto.py` | Mise à jour automatique : séquence complète, pause sûre ou attente, échec et retour arrière, une tentative par version, fenêtre horaire. | INV-MAJ-3 | — |
| `tests/test_session_perdue.py` | INV-SESSION-1 : « No conversation found with session ID » ne fait jamais échouer un tour. | INV-SESSION-1 | — |
| `tests/test_attente_muette.py` | Pas d'attente muette : lecture d'état, renvoi borné, gestes humains seuls. | INV-MAIN-1, INV-MAIN-2, INV-MAIN-3, INV-MAIN-4, INV-MAIN-5, INV-MAIN-6, INV-MAIN-7 | — |
| `tests/test_prechauffage.py` | Préchauffage du premier écran : caches remplis, jamais bloquant. | INV-FROID-1 | — |
| `tests/test_moteur.py` | Tours (INV-EXEC-1..5), messages entre tâches (INV-MSG-1), propositions. | INV-EXEC-1, INV-EXEC-2, INV-EXEC-4, INV-MSG-1, INV-VERROU-1 | — |
| `tests/test_moteurs.py` | Moteurs par tâche : clé `modele`, changement de harnais (sessions.json, préambule, retour), | INV-MOTEUR-1 | — |
| `tests/test_graphe.py` | Mentions non liées et graphe : nœuds, arêtes, local, filtres, plafond, cache invalidé à l'écriture. | INV-NOTE-4, INV-GRAPHE-1, INV-GRAPHE-2 | — |
| `tests/test_etiquettes.py` | Étiquettes : normalisation, contexte agent, rapprochement, renommage annulable, pose en bloc, refus d'agent, bornage des liens, recherche. | INV-ETIQUETTE-1, INV-ETIQUETTE-2, INV-ETIQUETTE-3 | — |
| `tests/test_notes.py` | Notes du vault : chemins sûrs, extraction et résolution des liens, index incrémental. | — | — |
| `tests/test_controle.py` | INV-CONTROLE-1 : échec puis correction puis modification (périmé), sans contrôle, déclaration non terminée, dossier hors dépôt, commande introuvable, délai, tâche permanente, persistance. | INV-CONTROLE-1 | — |
| `tests/test_pilotage.py` | Chat de projet : création au premier message, unicité, masquage, amorçage, seuil, création et lancement d'une enfant par `orch`, remontée sans tour. | INV-PILOTAGE-1, INV-PILOTAGE-2, INV-PILOTAGE-3 | — |
| `tests/test_regroupement.py` | Exécution regroupée : règle automatique (cas types), héritage et réglage, acheminement vers la mère, fiche écrite par la mère seule, repère, bascule, `orch fiche`. | INV-REGROUPE-1, INV-REGROUPE-2, INV-REGROUPE-3 | — |
| `tests/test_poste.py` | INV-POSTE-1 : réservation, titulaire unique, expiration, persistance, file d'attente du poste, file des tâches lourdes, libération d'office, routes, CLI. | INV-POSTE-1 | — |
| `tests/test_projet_par_note.py` | Un projet créé depuis les notes (sa fiche `contexte.md`) accepte des tâches tout de suite. | — | — |
| `tests/test_propositions.py` | Propositions enrichies : motif, types lier / operation / tache / perimetre, échec d'acceptation. | — | — |
| `tests/test_gestes_office.py` | Gestes de routine d'office, journal, annulation, reste à faire en ligne. | INV-PROP-1, INV-LIGNES-1 | — |
| `tests/test_lot_statuts.py` | Lot : tout ou rien, exclusion des occupées, annulation, trace, aperçu, refus d'agent, geste distant. | INV-LOT-1 | — |
| `tests/test_rattachement.py` | Proposition « rattacher » : lot, détachement, cycle, tâche occupée, autre projet, plafond, natures. | INV-RATTACHER-1, INV-PLAFOND-1, INV-NATURE-1 | — |
| `tests/test_depot.py` | Dossier de travail : projet avec dépôt, sans dépôt, descendant, table, dépôt absent, tour du moteur. | INV-DEPOT-1 | — |
| `tests/test_recherche.py` | Recherche : sans casse ni accents, tous les mots, titre / fiche / fil d'Ariane, ouvertes d'abord. | — | — |
| `tests/test_rapprochement.py` | Rapprochement : doublon → 409 + candidates, forcer, compléter, mesure, titre sans parenté, closes récentes, rendu CLI. | INV-RAPPROCHEMENT-1, INV-RAPPROCHEMENT-2 | — |
| `tests/test_reduction.py` | réduction d'un projet en tâche (archivage tout ou rien, mandat de contraction). | — | — |
| `tests/test_reprise.py` | Reprise d'un tour interrompu (INV-EXEC-1) — anomalie A3 de la recette du 15/11 ; file restaurée, double redémarrage (INV-EXEC-9). | INV-EXEC-1, INV-EXEC-9 | — |
| `tests/test_reprise_auto.py` | Reprise automatique et enregistrement d'étape (INV-REPRISE-1, INV-REPRISE-2) — tour coupé par la mémoire, arrêt humain, plafond de trois, erreur d'API passagère, arbre de travail retrouvé. | INV-REPRISE-1, INV-REPRISE-2 | — |
| `tests/test_economie.py` | Curseur (INV-ECO-1, INV-ECO-2) : défaut explicite, profil, escalade, curseur, rythme et hystérésis, équilibrage, moteur imposé, bascule proposée, mesure, routes. | INV-ECO-1, INV-ECO-2 | — |
| `tests/test_quota.py` | Bascule unique, jamais en boucle, moteur imposé, attente désactivée, compte épuisé, revue secourue, guet du journal OpenCode, diagnostic Linux, incidents et API. | INV-QUOTA-1, INV-QUOTA-2, INV-INCIDENT-1 | — |
| `tests/test_repli_harnais.py` | Harnais non installé : cause « absent » (jamais « réseau »), geste nommé, jamais choisi ni équilibré, bascule unique ; file d'une tâche bloquée retenue puis rejouée ; « Me reconnaître » sans second lecteur Telegram. | INV-QUOTA-1, INV-INCIDENT-1, INV-EXEC-11, INV-TELEGRAM-5 | — |
| `tests/test_vigie.py` | Signe de vie : phrases, silence d'un harnais muet, diagnostic d'un enfant bloquant simulé, gestes, exploration, raisons d'attente, API. | INV-VIGIE-1, INV-VIGIE-2 | — |
| `tests/test_travaux.py` | Écran « En cours » : lecture du flux des trois harnais, suivi borné de la vigie, API (tours, file, pause, reprise). | INV-TRAVAUX-1, INV-TRAVAUX-2 | — |
| `tests/test_reseau.py` | Coupures réseau : classement, gel des départs, reprise au retour (sonde factice), cadence, réveil de veille, une seule reprise, fournisseur seul en panne. | INV-RESEAU-1, INV-RESEAU-2, INV-RESEAU-3 | — |
| `tests/test_appairage.py` | Appairage : code à usage unique, expiration, essais limités, garde de l'interface distante, échange de bout en bout, jeton jamais affiché | INV-APPAIRAGE-1 | — |
| `tests/test_executeurs.py` | Exécuteurs distants : jetons, refus sans jeton, annonce, répartition, épinglage, conversation qui ne change pas de PC, perte et retour, vault par l'API (faux exécuteur dans le processus). | INV-DISTANT-1, INV-DISTANT-2, INV-DISTANT-3, INV-DISTANT-4 | — |
| `tests/test_appareils.py` | Accès distant du téléphone : 401 sans jeton (API, SSE, pages), révocation, code expiré ou réutilisé, verrou, Origin et Host étrangers, réservé au poste, gestes à risque, cookie, écoute jamais joker, code QR. | INV-DISTANT-5, INV-DISTANT-6, INV-DISTANT-7, INV-DISTANT-8 | — |
| `tests/test_audit_poste.py` | Audit L1 : régulation RAM sans oscillation, titulaire du poste épargné, instance unique par vault, arrêt des processus détachés. | INV-INSTANCE-1, INV-POSTE-1, INV-SIMULT-1 | — |
| `tests/test_simultanes.py` | Agents simultanés (INV-SIMULT-1) : modes, démarrage sous plafond, pause puis reprise, repli par arrêt et file, réglage par l'API. | INV-SIMULT-1 | — |
| `tests/test_compactage.py` | INV-COMPACT-1 : fenêtres et seuil, héritage, argument Codex et variable Claude, mesures lues des flux, repli par ordre de compactage, journal de mesure, routes. | INV-COMPACT-1 | — |
| `tests/test_integration.py` | INV-INTEG-1 : branches citées, dépôt git temporaire (non contenue / fusionnée / sous le seuil), cache, jamais bloquant, route. | INV-INTEG-1 | — |
| `tests/test_integration_lien.py` | INV-INTEG-2 : création reliée à l'intégration déclarée, projet sans déclaration, enfant non doublé, cible absente non bloquante. | INV-INTEG-2 | — |
| `tests/test_instrumentation.py` | Attente du poste et de la file mesurée (horloge factice), RSS et petits-fils (/proc factice), contexte borné, une ligne par sonde, durée de gel, arrêt de la veille. | INV-COMPACT-1, INV-RESEAU-4 | — |
| `tests/test_retour.py` | Retour arrière (INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3) : retour natif (point de reprise), repli par transcription, « Répondre à partir d'ici », premier message, archive et versions, refus pendant un tour, option Claude, points git et restauration tout ou rien. | INV-RETOUR-1, INV-RETOUR-2, INV-RETOUR-3 | — |
| `tests/test_references.py` | moteur de réécriture des références (`references.py`) : règles 1 à 4 et cas pièges. | — | — |
| `tests/test_revues.py` | statuts déclarés, revues de personas, validation (INV-EQUIPE-1, INV-VALID-1). | INV-EQUIPE-1, INV-EXEC-4, INV-VALID-1, INV-VAULT-4 | — |
| `tests/test_echec_tour.py` | Échec de tour visible : codex `turn.failed`, agy/opencode, quota, message du système, repère effacé au succès | INV-EXEC-8 | — |
| `tests/test_reveil_quota.py` | Réveil sur quota : heure de reprise, relance, 8 essais, arrêt, « Reprendre maintenant », redémarrage | INV-EXEC-9 | — |
| `tests/test_roles.py` | Moteurs par rôle : résolution, repli journalisé (INV-MOTEUR-2), compteurs, application au conseil, aux personas, aux mandats et au jardinage | INV-MOTEUR-1, INV-MOTEUR-2 | — |
| `tests/test_agents_cc.py` | Agents de Claude Code : inventaire, doublons, rattachement par session / titre / dossier, gestes, reprise, relevé. | INV-AGENTSCC-1 | — |
| `tests/test_evitable.py` | Pastille « évitable ? » : défaut, critères, seuil, désactivation, exclusion sensible, routes. | INV-EVITABLE-1 | — |
| `tests/test_decisions.py` | Page « Décisions » : agrégation des sources, extraction de la question, tri, lots, fermetures de revue. | INV-DECISIONS-1, INV-EXEC-5 | — |
| `tests/test_etoile.py` | INV-ETOILE-1 : seuil, Plus tard, refus, dépôt privé, réglage, essai, routes. | INV-ETOILE-1 | — |
| `tests/test_resultat.py` | INV-RESULTAT-1 : relevé (fiche, dernier tour, index, dossier), bornes, exécutables, ouverture, garde du poste. | INV-RESULTAT-1 | — |
| `tests/test_telegram.py` | Connecteur Telegram contre un faux serveur local : liste blanche, texte, photo, document, voix, tâche de tri, issue, réponse routée, question libre en attente, compte rendu à boutons (Valider clôt, Renvoyer), `creer --lancer --mission`, reprise, jeton masqué, réglages. | INV-TELEGRAM-1, INV-TELEGRAM-2, INV-TELEGRAM-3 | — |
| `tests/test_temps.py` | Le temps : échéance, priorité, retard, vue « Aujourd'hui », propositions, CLI. | INV-EXEC-5, INV-TEMPS-1 | — |
| `tests/test_renommer.py` | Renommage : titre seul réécrit, route, CLI, proposition « renommer », consignes des agents. | INV-RENOMMER-1, INV-RENOMMER-2 | — |
| `tests/test_transformations.py` | promotion sur place, mandat de découpage (INV-TRANSFO-1), proposition « projet ». | INV-TRANSFO-1 | — |
| `tests/test_validation_auto.py` | INV-VALID-2 : héritage, exclusions, relecteur, clôture puis journal et Rouvrir, refus motivés, échantillon, manuelle, réglage par l'API. | INV-VALID-2 | — |
| `tests/test_executant.py` | INV-EXECUTANT-1 : humain → aucun tour, ni revue ni validation, orch refusé sauf lien ; INV-EXECUTANT-2 : notes ajoutées et éditées sans toucher au reste, jamais par un agent, amorce (notes, état, plafond) ; « Confier la suite » ; retour à l'humain. | INV-EXECUTANT-1, INV-EXECUTANT-2, INV-VAULT-1 | — |
| `tests/test_notes_ia.py` | INV-EXECUTANT-3 : seule la portée part au modèle, rien n'est écrit, coût rendu, mode Moi, refus d'agent, erreurs lisibles, application puis annulation, rôle `notes` économique par défaut. | INV-EXECUTANT-3 | — |
| `tests/test_vault.py` | Index, arbre, création, déplacement, promotion, verrou paperclip (INV-VAULT-2/3/4). | INV-VAULT-2, INV-VAULT-3 | — |
| `tests/test_verrou.py` | Verrou Paperclip (INV-VAULT-4) levé par configuration, sans toucher aux fichiers. | INV-VAULT-4 | — |
| `tests/test_natif.py` | INV-NATIF-1 : ouverture (session préparée, messages en file), fermeture en plein tour (reprise puis file), fiche relue, refus, relais réel (PID, code), attente d'un vrai processus. | — | — |
| `tests/test_demi_verrou.py` | INV-VERROU-1 : occupation, descendance, routes gardées (409 `occupee` / `forcer`), messages et arrêt libres, INV-ALIGN-2 non outrepassé, `occupees` de l'état. | INV-ALIGN-2, INV-VERROU-1 | — |
| `tests/test_verrou_deplacement.py` | INV-ALIGN-2 : un déplacement de dossier ne bloque que les tours qui touchent ce dossier ; acceptation d'une proposition « operation » sous le même verrou | INV-ALIGN-2, INV-ARBRE-2, INV-EXEC-5 | — |
| `tests/test_version.py` | INV-VERSION-1 (empreinte, `a_jour`, `perime` des 404, `POST /redemarrer`). | INV-API-1, INV-VERSION-1 | — |
| `tests/ui/conftest.py` | Fixtures des scénarios d'interface : vrai serveur sur vault temporaire (journal dans `serveur.log`, jamais un tuyau), navigateur Playwright. | — | `ui/scenario_porte.py` |
| `tests/ui/harnais_factice.py` | Harnais factice des tests d'interface : joue un tour scénarisé (« [lent N] » : tour de N secondes ; « [echec] » ; « [bavard] » : 64 Ko sur la sortie d'erreur ; « [journaux] » : session sans transcript ; `<texte>…</texte>` : proposition du bouton « IA » des notes ; `GB_DEMO` : scènes de démonstration par message), ne lance jamais un vrai agent. | — | — |
| `tests/ui/scenario_filtres.py` | Scénario des filtres : pastille de statut, filtres combinés et compteur, regroupement, tri, mémoire du navigateur, focus clavier | — | — |
| `tests/ui/scenario_lot_statuts.py` | Scénario du filtre de statut partagé (adresse, volet et vue principale) et du changement en bloc (Maj+clic, confirmation, annulation). | INV-LOT-1 | — |
| `tests/ui/scenario_guide.py` | Scénario du guide : « ? » de l'en-tête, sommaire, recherche, « ? » contextuel de Réglages, lien `#guide=<ancre>`. | INV-GUIDE-1 | — |
| `tests/ui/scenario_langues.py` | Scénario des langues : en, de, es basculées par Réglages, écrans principaux parcourus, aucune valeur française de `fr.json` visible ; captures accueil et tâche dans les quatre langues (`GB_CAPTURES_LANGUES`, hors porte). | INV-LANGUE-1 | — |
| `tests/ui/scenario_routines.py` | Scénario des routines : création depuis le bandeau, horloge dans l'arbre, « Exécuter maintenant » avec issue et historique, pause, filtre « Routines ». | INV-ROUTINE-5 | — |
| `tests/ui/scenario_chaines.py` | Scénario des chaînes : modèles intégrés visibles, création d'un modèle à deux phases, lancement sur un projet, phases et état dans le détail de la parente. | INV-CHAINE-1, INV-CHAINE-2 | — |
| `tests/ui/scenario_renommer.py` | Scénario du renommage : clic sur le titre, Échap, Entrée, proposition acceptée sur la page Décisions. | INV-RENOMMER-1, INV-RENOMMER-2 | — |
| `tests/ui/scenario_rattacher.py` | Lot « rattacher » : une carte dans Décisions, acceptée d'un clic. | INV-RATTACHER-1 | — |
| `tests/ui/scenario_porte.py` | Régression de la porte d'interface : un serveur qui journalise abondamment reste joignable (tuyau non lu, 15/11). | — | — |
| `tests/ui/scenario_statut_ligne.py` | Scénario du changement de statut depuis l'arbre et la cascade : menu, verrou, refus en ligne, annulation, clavier | — | — |
| `tests/ui/scenario_fumee.py` | Scénario de fumée : l'interface charge sans erreur, l'arbre s'affiche, un tour factice aboutit (fiche rendue, conversation relue). | — | — |
| `tests/ui/aides_arbre.py` | Aides communes aux scénarios d'arbre, de tâche et de glisser-déposer | — | — |
| `tests/ui/scenario_arbre_cascade.py` | Scénarios d'arbre (volet gauche) et de cascade (volet droit) : hiérarchie, replis, clavier, bascule, filtres | — | — |
| `tests/ui/scenario_glisser.py` | Scénarios de glisser-déposer (volet gauche et cascade) : dépôt admis, refusé, menu tâche sur tâche, annulation, clavier | — | — |
| `tests/ui/scenario_agents_cc.py` | Agents de Claude Code dans Décisions : doublons regroupés, proposition modifiée, lot appliqué. | INV-AGENTSCC-1 | — |
| `tests/ui/scenario_evitable.py` | Pastille « évitable ? » : Réglages puis Décisions, motif, seuil, désactivation. | INV-EVITABLE-1 | — |
| `tests/ui/scenario_propositions_compactes.py` | Propositions compactes : six propositions de deux tâches, hauteurs repliées et dépliées au panneau, à l'accueil et aux Décisions ; refus par icône, « Tout refuser ». | INV-PROP-2 | — |
| `tests/ui/scenario_decisions.py` | Page « Décisions » : adresse directe, question visible, réponse et acceptation sur place, fermetures cochées, filtre rapides, lot de validations. | INV-DECISIONS-1 | — |
| `tests/ui/scenario_design.py` | Système visuel : thème sombre choisi dans Réglages, persistant au rechargement, retour au thème du système ; écran étroit (390 px) en une colonne, un écran à la fois (Réglages par la barre basse), sans débordement. | — | — |
| `tests/ui/scenario_telephone.py` | Profil mobile : liste, tâche en plein écran (onglets), envoi d'un message, validation d'une décision par la barre basse ; application installable sans cache des données. | INV-PWA-1 | — |
| `tests/ui/scenario_console.py` | Bouton « Console GoldenBrain » : offert sans session, demande l'onglet `orch console <id>` (aucun onglet réel : `console.lancer` neutralisé par `ui/serveur.py`). | INV-CONSOLE-1 | — |
| `tests/ui/scenario_tache_conversation.py` | Scénarios de tâche et de conversation : en-tête, tour de l'agent, étapes à la demande, changement de parent | INV-EXEC-3 | — |
| `tests/ui/scenario_alignement.py` | Scénarios de l'alignement : pastille et panneau des écarts, plan (simulation), application, conflit | — | — |
| `tests/ui/scenario_poste.py` | Scénario du poste : bandeau « Poste réservé », tâche lourde « En attente du poste », départ après « Libérer » | — | — |
| `tests/ui/scenario_ordonnancement.py` | Scénario de l'ordonnancement : lien « a pour prérequis » posé par « Lier… », « En attente de : … » puis départ seul, rang et motif dans « En file » et sur la tâche | — | — |
| `tests/ui/scenario_a_moi.py` | « À moi » en trois pastilles : comptes, validation en lot et annulation. | INV-MAIN-4, INV-MAIN-6, INV-MAIN-7 | — |
| `tests/ui/scenario_ecrans_audit.py` | Audit L4 : fil sans « ? »/_meta, libellé « À valider », bandeau, colonnes DE/ES, gouttières, modale, graphe cadré, mobile | — | — |
| `tests/ui/scenario_barre_haute.py` | Barre haute : aucun élément hors fenêtre à 1366, 1280 et 1024 px (discussion et complète, fr et de, pire cas), libellés des pastilles « À moi » | INV-BARRE-1 | — |
| `tests/ui/scenario_accueil_rangee.py` | Accueil sur une rangée : barre haute ≤ 48 px sans tâche ouverte, pas de rangée « En direct », filtre de statut sur la ligne du titre, première ligne du tableau dans le premier quart ; fiche : un titre long reste lisible | INV-DISCUSSION-1 | — |
| `tests/ui/scenario_discussion.py` | Mode discussion : conversation ≥ 70 % de l'écran, rail de l'arbre (survol, clic, clavier), menu, notes en intercalaire, « Tout afficher », choix mémorisés | INV-DISCUSSION-1 | — |
| `tests/ui/scenario_deroulant.py` | Déroulant unique : délai d'intention, clic, Échap, clic extérieur, épingle, clavier, toucher, feuille du bas ; mode discussion sans zone permanente | INV-DEROULANT-1 | — |
| `tests/ui/scenario_reactivite.py` | Budget de réactivité sur vault chargé : premier affichage, ouverture d'une tâche, intercalaires, frappe, défilement, événement d'une autre tâche, requêtes en double. | INV-REACTIVITE-1 | — |
| `tests/ui/charge.py` | Peuple un vault de charge (260 tâches, 150 décisions, fil de 200 messages) pour `scenario_reactivite.py`. | INV-REACTIVITE-1 | — |
| `tests/ui/scenario_detail_allege.py` | Ouverture de tâche allégée : hauteur au-dessus des messages ≤ 15 % (bureau, téléphone, trois langues), « Détails » à un clic, choix mémorisé | INV-DETAIL-1 | — |
| `tests/ui/scenario_graphe.py` | Scénarios du second cerveau : mentions non liées, notes liées d'une tâche, graphe local et global filtré, clic d'ouverture | — | — |
| `tests/ui/scenario_notes.py` | Scénarios des notes : lecture, édition, conflit d'édition (409) | — | — |
| `tests/ui/scenario_pilotage.py` | Chat de projet : sélection d'un projet → sa conversation ; premier message → tâche créée par `orch creer`, visible dans l'arbre ; conversation unique et masquée | INV-PILOTAGE-1 | — |
| `tests/ui/scenario_execution.py` | Exécution regroupée : motif affiché sur une sous-tâche, réglage de la mère puis du conteneur. | INV-REGROUPE-1 | — |
| `tests/ui/scenario_transformations.py` | Scénarios de promotion (tâche → projet) et de réduction (projet → tâche) | — | — |
| `tests/ui/scenario_validation_auto.py` | Scénario : réglage « automatique » d'un projet depuis sa note, section « Clos automatiquement » et « Rouvrir » | — | — |
| `tests/ui/scenario_executant.py` | Scénario : curseur Moi, journal, pastille, filtre « Qui la mène », « Confier la suite » ; bouton « IA » des notes (sélection, Synthétiser, Insérer, Annuler) | — | — |
| `tests/ui/scenario_version.py` | Scénarios des bandeaux de version : « serveur à mettre à jour » et « mise à jour disponible » | — | — |
| `tests/ui/scenario_telegram.py` | Réglages → Telegram : réglages avancés, puis assistant de bout en bout (accueil, bot, jeton saisi par la commande réelle, nom, webhook levé, discussion, test, fin) contre un faux Telegram | INV-TELEGRAM-1, INV-TELEGRAM-2, INV-TELEGRAM-4 |  |
| `tests/ui/faux_telegram.py` | Faux serveur de l'API Telegram pour les scénarios d'interface (getMe, webhook, getUpdates, sendMessage) | INV-TELEGRAM-1 | `ui/scenario_telegram.py` |
| `tests/test_telegram_jeton.py` | Saisie du jeton : jamais affiché, refus sans écriture, commande exacte, route du terminal (accord, poste seul), émulateurs Linux, CLI | INV-TELEGRAM-2, INV-INSTALL-1 | — |
| `tests/test_manager.py` | Volet « manager » : instruction sans Telegram, geste qui attend Confirmer (une seule fois), fil commun avec Telegram, `/nouveau`, API (garde, vide, bouton périmé). | INV-MANAGER-1, INV-TELEGRAM-3 | — |
| `tests/ui/scenario_manager.py` | Volet « manager » : ouverture mémorisée, message envoyé, réponse à boutons confirmée, fermeture ; captures bureau et téléphone. | INV-MANAGER-1 | — |
| `tests/test_telegram_assistant.py` | Assistant contre le faux serveur Telegram : instruction / contenu, transfert, réponse d'état avec lien, geste confirmé ou annulé, choix à boutons, correction, ordre de paiement, `/nouveau`, CLI, tâches proches d'une instruction. | INV-RAPPROCHEMENT-1, INV-TELEGRAM-3, INV-TELEGRAM-4 | — |
| `tests/ui/scenario_etoile.py` | Fenêtre à trois boutons, réponses, rien quand non due, interrupteur des Réglages. | — | — |
| `tests/ui/scenario_resultat.py` | Message sans résultat, puis liste (site local, index.html, dossier de travail). | — | — |
| `tests/ui/scenario_interface.py` | Scénario du mode simple / avancé : bascule depuis Réglages, notions masquées, rebranchement d'une famille | — | — |
| `tests/ui/scenario_codespace.py` | Scénario du codespace d'une tâche : bloc absent sans déclaration ; état, gestes, réglage « Où » | — | — |
| `tests/ui/scenario_economie.py` | Scénario des Réglages « Performance ↔ Économie » : curseur, famille par défaut, repère d'en-tête, persistance relue | — | — |
| `tests/ui/scenario_incidents.py` | Scénario des incidents : quota épuisé, cause dans la conversation, panneau « Incidents » et jauge du compte | — | — |
| `tests/ui/scenario_vigie.py` | Scénario du signe de vie : phrase d'activité, tour silencieux signalé au bandeau et dans la tâche, « Attendre » puis « Arrêter le tour » | — | — |
| `tests/ui/scenario_travaux.py` | Scénario de l'écran « En cours » : aides, avancement, dernière action, pause, reprise, arrêt confirmé ; capture | — | — |
| `tests/ui/scenario_reseau.py` | Scénario des coupures réseau : bandeau « Réseau perdu », état « En attente du réseau », reprise au retour du point d'accès sondé | INV-RESEAU-1, INV-RESEAU-2 | — |
| `tests/ui/scenario_simultanes.py` | Scénario des Réglages « Agents simultanés » : choix du mode, plafond en Go, persistance relue | — | — |
| `tests/ui/scenario_maj_auto.py` | Mise à jour automatique : réglage persistant, bandeaux de préparation, de fin et d'incident | — | — |
| `tests/ui/scenario_affichage.py` | Affichage par défaut : barre haute sombre en clair et en sombre, menus au thème de la page, budgets d'écran au bureau et au téléphone, focus visible | INV-AFFICHAGE-1 | — |
| `tests/ui/scenario_reglages.py` | Réglages regroupés : groupes repliables mémorisés, résumés d'état, ancre `#reglages/<section>`, recherche, saisie conservée au redessin | INV-REGLAGES-1 | — |
| `tests/ui/scenario_executeurs.py` | Scénario des Réglages « PC connectés » : appairage par code, jeton montré une fois, annonce, révocation | — | — |
| `tests/ui/scenario_appareils.py` | Scénario des Réglages « Appareils » : ajouter un téléphone (code QR), échange, appareil listé, révocation | — | — |
| `tests/ui/scenario_copilot.py` | Sélecteur de moteur : Copilot proposé, grisé avec son motif s'il n'est pas installé | INV-MOTEUR-1 | — |
| `tests/ui/scenario_apprendre.py` | Scénario du mode « Apprendre » : interrupteur général persisté, réglage de tâche, encadrés dans la conversation, points à retenir dans la fiche, inactif sans effet | INV-APPRENDRE-1 | — |
| `tests/ui/scenario_compactage.py` | Scénario des Réglages « Compactage automatique » : seuil et plafond écrits et relus, mécanisme par harnais, vue de mesure alimentée par un tour | — | — |
| `tests/ui/scenario_integration.py` | Pastille « intégration en retard » : visible sur une tâche terminée à branche non fusionnée, levée après fusion ; réglage dans Réglages | — | — |
| `tests/ui/scenario_modifier.py` | Scénarios « Modifier un message » et « Répondre à partir d'ici » : avertissement, case code, renvoi, conversation tronquée, version précédente consultable. | — | — |
| `tests/ui/scenario_demi_verrou.py` | Scénarios du demi-verrou : repère « IA au travail » en direct, « IA : n » des ancêtres, confirmation d'un changement de statut | — | — |
| `tests/ui/serveur.py` | Lanceur du VRAI serveur pour les tests d'interface : `python tests/ui/serveur.py <config.toml>`. | — | — |
| `tests/ui/univers.py` | Vault temporaire et configuration des tests d'interface. | — | — |
| `tests/donnees/codex-derive-outil.jsonl` | Flux JSON enregistré d'un tour codex (donnée de test) | — | `test_harnais_cli.py` |
| `tests/donnees/codex-quota.jsonl` | Flux JSON d'un tour codex en échec : quota épuisé (`turn.failed`) | — | `test_echec_tour.py` |
| `tests/donnees/codex-erreur.jsonl` | Flux JSON enregistré d'un tour codex (donnée de test) | — | `test_harnais_cli.py` |
| `tests/donnees/codex-premier.jsonl` | Flux JSON enregistré d'un tour codex (donnée de test) | — | `test_harnais_cli.py` |
| `tests/donnees/codex-reprise-modele.jsonl` | Flux JSON enregistré d'un tour codex (donnée de test) | — | `test_harnais_cli.py` |
| `tests/donnees/agy-erreur.jsonl` | Flux JSON enregistré d'un tour agy en erreur (donnée de test) | — | `test_agy.py` |
| `tests/donnees/agy-premier.jsonl` | Flux JSON enregistré d'un tour agy d'un premier tour (donnée de test) | — | `test_agy.py` |
| `tests/donnees/agy-reprise-outil.jsonl` | Flux JSON enregistré d'un tour agy de reprise avec outil (donnée de test) | — | `test_agy.py` |
| `tests/donnees/opencode-derive.jsonl` | Flux JSON enregistré d'un tour opencode (donnée de test) | — | `test_harnais_cli.py` |
| `tests/donnees/opencode-erreur.jsonl` | Flux JSON enregistré d'un tour opencode (donnée de test) | — | `test_harnais_cli.py` |
| `tests/donnees/opencode-outil.jsonl` | Flux JSON enregistré d'un tour opencode (donnée de test) | — | `test_harnais_cli.py` |
| `tests/donnees/opencode-reprise.jsonl` | Flux JSON enregistré d'un tour opencode (donnée de test) | — | `test_harnais_cli.py` |
| `tests/README.md` | Mode d'emploi des tests : installation (httpx), porte, encodage, `PYTEST_DEBUG_TEMPROOT` si Temp verrouillé (Windows) | — | — |
| `tests/ui/README.md` | Mode d'emploi des scénarios d'interface | — | — |
| `tests/test_compagnon.py` | Compagnon mobile : instantané en liste blanche (ni corps de fiche ni chemin), ETag et 304, bornes, `hors_ligne`, refus sans appareil appairé ou révoqué. | INV-COMPAGNON-1, INV-PWA-2, INV-DISTANT-6 | — |
| `tests/ui/scenario_compagnon.py` | Accueil du téléphone (Pixel 7) : à décider, rien gardé par défaut, aperçu gardé sans corps de fiche, poste injoignable daté, effacement. | INV-PWA-2, INV-COMPAGNON-1 | — |
