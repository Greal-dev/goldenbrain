# Vocabulaire grand public et règle des clés

Mis à jour le 2026-11-23. Tout texte montré à l'utilisateur (dictionnaires `web/langues/*.json`, guides) parle la langue de tout le monde, pas celle des développeurs. Identifiants, clés de dictionnaire, clés de configuration, routes d'API, noms de commandes et statuts du vault ne changent jamais.

## Glossaire

| Terme de développeur | fr (source) | en | de | es |
|---|---|---|---|---|
| harnais | assistant IA | AI assistant | KI-Assistent | asistente de IA |
| tour (d'agent) | séance de travail | work session | Arbeitssitzung | sesión de trabajo |
| branche | version | version | Version | versión |
| porte (gate, check.py) | vérification | check | Prüfung | comprobación |
| commit | enregistrement | saved change | gespeicherte Änderung | cambio guardado |
| fusion, merge, intégration de branche | intégration à la version principale | merge into the main version | Übernahme in die Hauptversion | integración en la versión principal |
| arbre de travail, worktree | copie de travail | working copy | Arbeitskopie | copia de trabajo |
| dépôt, repo | dossier du code | code folder | Code-Ordner | carpeta del código |
| pousser, push | publier en ligne | publish online | online veröffentlichen | publicar en línea |
| diff | modifications | changes | Änderungen | cambios |
| prompt, consigne système | consigne | instructions | Anweisungen | instrucciones |
| session (de harnais) | conversation | conversation | Unterhaltung | conversación |
| contexte, compaction | mémoire de la conversation, résumé de la conversation | conversation memory, conversation summary | Gesprächsgedächtnis, Gesprächszusammenfassung | memoria de la conversación, resumen de la conversación |
| jetons, tokens | volume de texte | amount of text | Textmenge | cantidad de texto |
| quota | crédit d'utilisation | usage allowance | Nutzungskontingent | crédito de uso |
| effort (de modèle) | niveau de réflexion | thinking level | Denktiefe | nivel de reflexión |
| exécuteur (distant) | ordinateur d'appoint | helper computer | Hilfsrechner | ordenador auxiliar |
| terminal, CLI | invite de commandes | command prompt | Eingabeaufforderung | símbolo del sistema |
| frontmatter | en-tête de la note | note header | Notizkopf | encabezado de la nota |
| log | journal | log | Protokoll | registro |
| processus, PID | programme en cours | running program | laufendes Programm | programa en ejecución |
| serveur (local) | GoldenBrain (sur cet ordinateur) | GoldenBrain (on this computer) | GoldenBrain (auf diesem Computer) | GoldenBrain (en este ordenador) |
| endpoint, API (dans un message) | service | service | Dienst | servicio |
| timeout, expiration | délai dépassé | took too long | Zeitüberschreitung | tiempo agotado |
| persona | expert de l'équipe | team expert | Experte des Teams | experto del equipo |
| tags | étiquettes | tags | Schlagwörter | etiquetas |
| dériver (une tâche, une conversation) | créer à partir de, copier | create from this, copy | daraus erstellen, kopieren | crear a partir de, copiar |
| hériter | comme la tâche mère | same as the parent task | wie die übergeordnete Aufgabe | como la tarea madre |
| point de restauration (sans le mot « git ») | point de restauration | restore point | Wiederherstellungspunkt | punto de restauración |
| RAM | mémoire de l'ordinateur | computer memory | Speicher des Computers | memoria del ordenador |
| appels d'outils | actions | actions | Aktionen | acciones |
| état (du code) non référencé | version du code non repérée | code version not identified | Codeversion nicht erfasst | versión del código no identificada |
| jeton d'accès (d'un ordinateur d'appoint) | clé d'accès | access key | Zugangsschlüssel | clave de acceso |
| chef (ordinateur qui répartit les tâches) | ordinateur principal | main computer | Hauptrechner | ordenador principal |
| repli (moteur de secours) | solution de repli, assistant de secours | fallback, fallback assistant | Ersatzlösung, Ersatz-Assistent | solución de reserva, asistente de reserva |
| webhook (liaison d'un bot) | liaison automatique | automatic link | automatische Verbindung | enlace automático |
| jeton d'un bot Telegram | clé d'accès | access key | Zugangsschlüssel | clave de acceso |
| pipeline, workflow (programme tiers) | automatisme | automation | Automatisierung | automatización |
| renvoi (d'une tâche à l'agent) | renvoi à l'agent | return to the agent | Rückgabe an den Agenten | devolución al agente |
| conteneur (dossier de tâches) | dossier | folder | Ordner | carpeta |
| nœud (de l'arbre) | élément | item | Element | elemento |
| sauts (entre agents) | transmissions entre agents | hand-offs between agents | Weitergaben zwischen Agenten | traspasos entre agentes |
| révoqué (appareil) | dont l'accès a été retiré | whose access was withdrawn | dessen Zugang entzogen wurde | cuyo acceso fue retirado |
| déterministe | automatique | automatic | automatisch | automático |
| fenêtre (de crédit d'utilisation) | période | period | Zeitraum | período |

Termes constants : tâche = task / Aufgabe / tarea ; projet = project / Projekt / proyecto ; casquette = role / Rolle / rol ; opération = operation / Vorhaben / operación ; Réglages = Settings / Einstellungen / Ajustes ; Décisions = Decisions / Entscheidungen / Decisiones ; Aujourd'hui = Today / Heute / Hoy ; Notes = Notes / Notizen / Notas ; Équipe = Team / Team / Equipo ; agent = agent / Agent / agente ; vault = vault / Vault / vault ; fiche = summary / Bericht / ficha.
Vouvoiement partout : « vous », « Sie », « usted » ; ton neutre en anglais.
Tout autre terme de développeur rencontré : le remplacer par le mot courant le plus simple et l'ajouter à ce tableau.

## Stabilité des clés

Une clé publiée sur `gb/langues` ne se renomme ni ne se supprime : seule sa **valeur** change. Les autres tâches s'y branchent en parallèle.

## Ajouter un écran (marche à suivre)

1. Importer : `import { t, tn, LOCALE } from './langues.js'` ; `t('ecran.cle', { nom: valeur })`, `tn('ecran.cle', n)` pour l'accord au nombre (`<cle>.un`, `<cle>.plusieurs`, `{n}`).
2. Préfixe : le nom de l'écran ou du module (`detail.`, `reglages.`…), clés plates à points, littérales (jamais calculées), phrases entières avec paramètres `{x}` (jamais de morceaux concaténés). Ne pas nommer `t` une variable locale ; dates et nombres avec `LOCALE`.
3. Ajouter les clés : lot JSON `{"cle": {"fr": "…", "en": "…", "de": "…", "es": "…"}}` hors du dépôt, puis `python scripts/dictionnaires.py ajouter <lot.json>` (écrit les quatre fichiers triés).
4. Vérifier : `python scripts/dictionnaires.py reste web/x.js` liste ce qui reste en dur ; viser 0 (la porte contrôle tout `web/`). Un faux positif visible se motive dans `scripts/langues_exceptions.txt`.

## « Accueil » : un seul sens

« Accueil » désigne uniquement l'écran d'accueil du téléphone (compagnon mobile). L'importation des projets existants s'appelle « Reprise de vos projets » (en : Import your projects) ; la fenêtre du tout premier lancement, « Bienvenue dans GoldenBrain » (premiers pas). Clés : `accueil.*` (reprise, historique), `premiers-pas.*`, `compagnon.*`.
