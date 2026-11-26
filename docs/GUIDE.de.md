# GoldenBrain-Anleitung

Aktualisiert am 2026-11-26.

GoldenBrain ist ein Steuerpult: Sie übergeben Aufgaben an KI-Agenten (Claude Code, Codex, OpenCode, Copilot, Antigravity), und jede Aufgabe wird an ihrem Platz in Ihrem Vault (einem Ordner mit Markdown-Notizen) abgelegt. GoldenBrain organisiert und beaufsichtigt; der Agent arbeitet in seiner eigenen Unterhaltung, die Sie jederzeit wieder aufnehmen können.

Diese Anleitung lesen Sie in der Anwendung (Schaltfläche „?“ oben rechts), im Code-Ordner (`docs/GUIDE.md`) oder über einen Agenten (`python orch.py guide`). Jeder Abschnitt beantwortet drei Fragen: wozu es dient, wie man vorgeht, was man wissen sollte. In der Anwendung zeigt das Feld „In der Anleitung suchen“ nur die Abschnitte an, die das Wort enthalten; das „?“ neben dem Titel von Einstellungen, Team und Entscheidungen öffnet direkt den zugehörigen Abschnitt; ein Abschnitt lässt sich über seinen Link teilen (`#guide=reglages`).

## Installieren {#installer}

Zwei Wege: **mit einem Klick** (ohne Eingabeaufforderung und ohne Python-Installation: alles ist enthalten) oder **von Hand** aus dem Code (Linux, Windows siehe unten). In beiden Fällen brauchen Sie anschließend einen Vault (einen Ordner mit Markdown-Notizen, Obsidian oder nicht; GoldenBrain startet auch ohne) und mindestens einen KI-Assistenten (siehe „KI-Assistenten verbinden“).

### Mit einem Klick {#en-un-clic}

Wozu es dient: GoldenBrain wie eine gewöhnliche Anwendung installieren. Python, seine Komponenten und (unter Windows) Git sind eingebettet; sonst wird auf dem Computer nichts verändert, und es werden keine Administratorrechte verlangt (außer beim .deb-Paket, das von der Softwareverwaltung installiert wird).

- **Windows**: `GoldenBrain-installation.exe` herunterladen (Seite der GoldenBrain-Versionen auf GitHub), doppelklicken und den drei Bildschirmen folgen. GoldenBrain startet am Ende und danach über das Startmenü. Windows kann „Unbekannter Herausgeber“ melden (nicht signiertes Installationsprogramm): „Weitere Informationen“, dann „Trotzdem ausführen“.
- **Linux (Debian, Ubuntu)**: `goldenbrain_<version>_amd64.deb` herunterladen, doppelklicken (Softwareverwaltung) oder `sudo apt install ./goldenbrain_*.deb`. GoldenBrain erscheint im Anwendungsmenü und startet auch mit dem Befehl `goldenbrain`.
- **Linux (andere) und macOS**: einmalig in eine Eingabeaufforderung (Terminal unter macOS) kopieren und einfügen:
  `curl -fsSL https://github.com/Greal-dev/goldenbrain/raw/main/installation/installer.sh | bash`
  Die Installation dauert zwei bis drei Minuten, legt den Menüeintrag an (Linux) bzw. `GoldenBrain` im Ordner „Programme“ Ihres Benutzerkontos (macOS) und startet dann GoldenBrain. Git ist erforderlich: Unter macOS die vom System angebotenen Werkzeuge akzeptieren und den Befehl dann erneut ausführen.
- **macOS, ohne Eingabeaufforderung**: `GoldenBrain-macos-arm64.zip` herunterladen (neuere Macs; `x86_64` für Intel-Macs), öffnen und GoldenBrain in „Programme“ ziehen. Da die Anwendung nicht signiert ist, erfolgt der erste Start per Rechtsklick → „Öffnen“ (oder Systemeinstellungen → Datenschutz & Sicherheit → „Dennoch öffnen“).

So funktioniert es: Bei jedem Start öffnet sich der Browser mit GoldenBrain; läuft GoldenBrain auf diesem Computer noch nicht, wird es dabei gestartet (ein zweiter Klick startet kein zweites). Beim ersten Start wird die Anwendung in Ihren persönlichen Ordner kopiert (`~/.local/share/goldenbrain/app`, `~/Library/Application Support/GoldenBrain/app` oder `%LOCALAPPDATA%\GoldenBrain\app`): Diese Kopie bringt das „Update mit einem Klick“ auf den neuesten Stand, und sie behält Ihre Einstellungen (`config.toml`).

Gut zu wissen: Die Installation spricht die Sprache des Systems (Französisch, Englisch, Deutsch oder Spanisch; Englisch für jede andere Sprache) und überträgt sie beim ersten Start in `config.toml` (`[interface] langue`), damit GoldenBrain in derselben Sprache startet; eine vorhandene `config.toml` wird nie verändert. Neu installieren oder deinstallieren berührt weder diese Kopie noch den Vault. Das Startprotokoll ist `lancement.log` im Datenordner (Linux, macOS). Um die Installationsprogramme selbst zu bauen: `python scripts/construire_deb.py`, `construire_windows.py` (Inno Setup unter wine), `construire_macos.py`; jede heruntergeladene Komponente wird anhand ihres Fingerabdrucks geprüft (`installation/versions.txt`). Jede auf der Versionsseite veröffentlichte Version enthält die vier Installationsprogramme, jedes Mal neu gebaut, und eine Notiz auf Englisch, Französisch, Spanisch und Deutsch (`python scripts/publier_version.py`, von der Veröffentlichung gestartet).

### Linux {#linux}

Von Hand, aus dem Code (Entwickler). Sie brauchen Git und Python 3.12 oder neuer.


1. Voraussetzungen (Debian, Ubuntu): `sudo apt install git python3 python3-venv`
2. Code holen: `git clone https://github.com/Greal-dev/goldenbrain.git ~/goldenbrain && cd ~/goldenbrain`
3. Eigenes Python: `python3 -m venv ~/.venvs/goldenbrain`
4. Abhängigkeiten: `~/.venvs/goldenbrain/bin/pip install fastapi uvicorn pyyaml` (Entwickler, für die Tests: `pip install ".[test]"`)
5. Dieses Python festlegen: `echo ~/.venvs/goldenbrain/bin/python > python.local`
6. Erster Start: `./lancer.sh`, dann http://127.0.0.1:8300 öffnen

Der erste Start erzeugt `config.toml`, die nur Ihre Abweichungen enthält (alles Übrige stammt aus `config.exemple.toml`).

### Windows {#windows}

Von Hand, aus dem Code (Entwickler).

1. Git und Python 3.12 (python.org) installieren; den Pfad von `python.exe` notieren.
2. Code holen: `git clone https://github.com/Greal-dev/goldenbrain.git goldenbrain`
3. Abhängigkeiten: `python -m pip install fastapi uvicorn pyyaml` (Entwickler, für die Tests: `pip install ".[test]"`)
4. Ist `python` im PATH nicht der richtige Interpreter, den vollständigen Pfad in die erste Zeile einer Datei `python.local` im Stammordner schreiben.
5. Erster Start: Doppelklick auf `lancer.cmd`. Die Seite http://127.0.0.1:8300 öffnet sich.

### Wo der Vault liegt

Standardmäßig: `~/Documents/Vault`. Liegt er woanders, tragen Sie das in `config.toml` ein:

```toml
[vault]
racine = "~/chemin/vers/mon-vault"
```

**Ohne diese Datei anzufassen**: Beim ersten Start öffnet GoldenBrain vor jedem anderen Bildschirm „Ihr zweites Gehirn einrichten“ im Vollbild. Dort wählen Sie den Ordner (eintippen oder mit „Durchsuchen“ durch Ihre Ordner gehen): Ein vorhandener Markdown- oder Obsidian-Vault wird an Ort und Stelle übernommen, ohne Kopie; ein fehlender oder leerer Ordner wird zu einem neuen zweiten Gehirn, erst bei Ihrer Bestätigung angelegt. Ein nicht vorhandener, nicht beschreibbarer oder relativer Ordner oder einer, der schon von einer anderen Instanz bedient wird, wird mit Begründung abgelehnt. Ein Ordnerwechsel schreibt nur den Schlüssel `[vault] racine` in `config.toml` neu; danach startet GoldenBrain von selbst auf dem neuen Vault neu, beim aktuellen Ordner startet nichts neu. Es folgen die Wahl des KI-Assistenten und dann der Vorschlag für Rollen und Projekte (oder die Demonstration); vor Ihrer Bestätigung wird nichts geschrieben. „Später“ lässt einen Hinweis „Zweites Gehirn einrichten“ stehen. Wieder öffnen: Einstellungen → „Installation und Version“ → „Mein zweites Gehirn neu einrichten“.

Ein vorhandener Obsidian-Vault passt unverändert: `racine` darauf richten (siehe „Ihr zweites Gehirn organisieren“). Ein leerer oder fehlender Ordner erhält beim Willkommensassistenten, nach Ihrer Bestätigung, eine Grundablage.

Port belegt: `[serveur]`, dann `port = 8301`. Nach jeder Änderung an `config.toml` neu starten.

### Dienst beim Systemstart (Linux) {#service-au-demarrage-linux}

GoldenBrain startet mit der Sitzung von selbst und startet nach einem Update neu.

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/goldenbrain.service <<'FIN'
[Unit]
Description=GoldenBrain

[Service]
WorkingDirectory=%h/goldenbrain
ExecStart=/bin/bash lancer.sh
Restart=on-failure

[Install]
WantedBy=default.target
FIN
systemctl --user daemon-reload
systemctl --user enable --now goldenbrain
```

- Auch ohne Anmeldung starten: `loginctl enable-linger "$USER"`.
- Protokoll: `journalctl --user -u goldenbrain -f`. Anhalten: `systemctl --user stop goldenbrain`.
- `WorkingDirectory` muss auf den Code-Ordner zeigen (`%h` = Ihr persönlicher Ordner).

### KI-Assistenten verbinden {#connecter-les-harnais}

Ein KI-Assistent ist das Programm, das über eine Eingabeaufforderung verwendet wird und den Agenten arbeiten lässt. GoldenBrain sucht es im PATH; mindestens einer wird gebraucht, **installiert und angemeldet**.

| KI-Assistent | Installieren | Anmelden |
|---|---|---|
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` (macOS, Linux) · `irm https://claude.ai/install.ps1 \| iex` (Windows) | `claude`, dann `/login` |
| Codex | `npm install -g @openai/codex` | `codex login` |
| GitHub Copilot CLI | `npm install -g @github/copilot` | `copilot login` |
| OpenCode | `npm install -g opencode-ai` | siehe dessen Dokumentation |
| Antigravity (`agy`) | siehe dessen Dokumentation | aus der Anwendung |

Gut zu wissen: Ein fehlender KI-Assistent erscheint mit Begründung als „nicht verfügbar“ in der Auswahl „Motor“ einer Aufgabe. Sein Pfad oder seine Argumente werden in `config.toml` im Abschnitt `[harnais.<nom>]` eingestellt (Vorlage: `config.exemple.toml`).

Wissenswert: Für die Installationen über `npm` wird Node.js benötigt; die Anwendung bietet die Installation an (Startseite) und meldet sich nie für Sie an.

**Achtung — ohne Rückfrage**: Standardmäßig startet GoldenBrain die Agenten mit Argumenten, die jede Freigabe-Abfrage entfernen (`--dangerously-skip-permissions` für Claude Code und Antigravity, `--dangerously-bypass-approvals-and-sandbox` für Codex, `--auto` für OpenCode, `--allow-all-tools --no-ask-user` für Copilot), ab Ihrem Benutzerordner, sofern die Aufgabe keinen anderen nennt. Ein Agent kann Ihre Dateien daher ohne Rückfrage lesen, ändern oder löschen. Probieren Sie es zuerst mit einer harmlosen Anweisung; diese Argumente lassen sich in `config.toml` ändern (`[harnais.<Name>]`, Vorlage: `config.exemple.toml`); siehe `SECURITY.md`.

## Erste Schritte {#premiers-pas}

Zehn Minuten, ohne weitere Einrichtung.

0. **Beim allerersten Start** öffnet sich in zwei Schritten ein Fenster „Willkommen bei GoldenBrain“. *Ihr KI-Assistent*: die Liste der erkannten KI-Assistenten (Claude Code, Codex, Copilot, OpenCode, Antigravity), jeweils „bereit“, „installiert, Anmeldung erforderlich“ oder „nicht installiert“. Bei einem fehlenden Assistenten nennt „So installieren Sie ihn“ die offizielle Seite und den Befehl, den Sie in eine Eingabeaufforderung kopieren (Schaltfläche „Kopieren“); installieren Sie ihn und klicken Sie dann auf „Erneut prüfen“. GoldenBrain installiert selbst nichts. *Erste Aufgabe*: „Demo starten“ erstellt und startet eine kleine Aufgabe (der Assistent stellt sich vor und schlägt drei Ideen vor, ohne etwas auf dem Rechner zu verändern); die Antwort kommt in der Regel nach ein bis zwei Minuten. „Überspringen“ oder „Später“ schließt das Fenster und öffnet den Willkommensbildschirm. Um es erneut zu sehen: Einstellungen → „Installation und Version“ → „Erste Schritte erneut ansehen“.
1. **Eine Aufgabe erstellen**: „Neue Aufgabe“ (oben). Ein Titel genügt; die Beschreibung hilft dem Agenten. Oben im Formular stehen **fertige Vorlagen** (eine kleine Website erstellen, eine Excel- oder CSV-Tabelle auswerten, einen Brief verfassen, eine wiederkehrende Aufgabe automatisieren, Dokumente zusammenfassen, einen Begriff lernen): Ein Klick füllt Titel und Beschreibung aus, die Sie an den mit „[zu ergänzen]“ markierten Stellen vervollständigen; vor „Erstellen“ wird nichts angelegt. Eine Vorlage hinzufügen: eine `.md`-Datei im Ordner `modeles/` von GoldenBrain ablegen (Kopf mit `titre`, `resume`, `ordre`; der Text darunter ist der Auftrag). Um eine mitgelieferte Vorlage anzupassen, kopieren Sie sie unter einem anderen Namen: Ein Update kann mitgelieferte Dateien ersetzen. Projekt: „Eingang (Standard)“ belassen, wenn Sie nicht wissen, wo die Aufgabe abgelegt werden soll. Während der Eingabe werden ähnliche offene Aufgaben angezeigt: „Diese ergänzen“ fügt Ihre Anfrage dort hinzu, statt eine weitere anzulegen; existiert eine sehr ähnliche Aufgabe, wird das Erstellen sanft abgelehnt, und „Trotzdem erstellen“ setzt sich darüber hinweg.
2. **Sie starten**: beim Erstellen „Sofort starten“ ankreuzen oder unten in der Aufgabe eine erste Nachricht schreiben (Strg+Eingabe sendet).
3. **Der Unterhaltung folgen**: Die Aufgabe öffnet sich rechts; die Antworten des Agenten erscheinen live. Die obere Leiste listet die laufenden und wartenden Arbeitssitzungen.
4. **Antworten oder korrigieren**: unten schreiben; dieselbe Unterhaltung geht weiter.
5. **Bestätigen**: Meldet der Agent die Aufgabe als „Abgeschlossen“, wartet sie auf Ihr „Bestätigen“ oder „Zurücksenden …“ (mit einer Begründung, die an den Agenten zurückgeht).
6. **Entscheidungen**: Die Schaltfläche „Entscheidungen“ (oben) bündelt alles, was auf Ihre Handlung wartet: zu bestätigende Aufgaben, Fragen der Agenten, Vorschläge zu Ablage und Verknüpfungen, darunter die des Gärtners (der Konsistenzprüfung: Sie macht nur Vorschläge und schreibt nie von sich aus; `plafond` in `[jardinage]` begrenzt ihre Zahl pro Durchgang, standardmäßig 7).

Gut zu wissen: Eine neue Installation steht im Modus **Einfach** (Projekte, Aufgaben, Unterhaltung, Status, Bestätigen). Einstellungen → „Erweitert“ zeigt alles Übrige.

## Ihr zweites Gehirn organisieren {#organiser-votre-second-cerveau}

Der Vault ist Ihr **zweites Gehirn**: gewöhnliche Notizen (Markdown-Dateien), die GoldenBrain, Sie und die KI lesen und anreichern. Er ist in drei Ebenen gegliedert: **Rollen → Projekte → Aufgaben**.

- **Rollen („casquettes“)**: Ihre großen Lebensbereiche, wenige und dauerhafte. Beispiel: „Beruf“, „Familie“, „Quartiersverein“.
- **Projekte**: ein zu erreichendes Ergebnis innerhalb einer Rolle, mit einem Ende. Beispiel: unter „Familie“ „Umzug“; unter „Beruf“ „Website der Kanzlei“. Mehrere Projekte derselben Rolle lassen sich bei Bedarf in einem **Vorhaben** („Schuljahr 2027“) zusammenfassen.
- **Aufgaben**: eine konkrete Handlung in einem Projekt, der KI oder Ihnen selbst übertragen. Beispiel: „Drei Angebote von Umzugsunternehmen vergleichen“. Eine Aufgabe, die wächst, wird zum Projekt.

**Die Ordner des Start-Vaults** (vom Willkommensassistenten angelegt, wenn der Vault leer ist, nach Ihrer Bestätigung; die Demo-Aufgabe der ersten Schritte, in `_meta/` abgelegt, zählt nicht): `Casquettes/` (die Rollen und ihre Projekte), `Projets/` (aus einer Aufgabe entstandene Projekte), `Inbox/` (der Eingangskorb), `Ressources/` (was mehreren Projekten dient: Merkblätter, Vorlagen, Kontakte), `Archives/` (was erledigt ist oder ruht) und die Notiz `Lisez-moi.md`, die die Methode zusammenfasst.

**Wie die KI ihn nutzt**:
- **Vor jeder Aufgabe** liest der Agent die Datei `contexte.md` des Projekts (Ziel, Anhaltspunkte, Hinweise für die KI): Ein paar treffende Zeilen dort sind besser als eine lange, bei jeder Aufgabe wiederholte Anweisung.
- Die **Notizen** des Projekts (`notes/`) und diejenigen, die Sie mit `[[Name der Notiz]]` verknüpfen, geben ihm den Hintergrund der Sache.
- Der **Graph** (Reiter „Notizen“, Schaltfläche „Graph“) zeigt, was verbunden ist und was isoliert bleibt.
- Der **KI-Gärtner** schlägt Verknüpfungen und Ablagen vor; er schreibt nichts ohne Ihre Zustimmung.

**Bewährte Vorgehensweisen**:
1. **Schnell erfassen, später ablegen**: Im Zweifel kommt alles nach `Inbox/`; eine Sortierung pro Woche genügt.
2. **Eine Aufgabe = ein erwartetes Ergebnis** („Den Brief an das Rathaus verfassen“), nie ein Thema („Rathaus“).
3. **`contexte.md` aktuell halten**: zwei oder drei Zeilen, neu gelesen, wenn das Projekt den Kurs ändert.
4. **Archivieren statt löschen**: `Archives/` bewahrt den Verlauf, ohne zu stören.

**Sie haben bereits einen Obsidian-Vault**: Richten Sie `[vault] racine` darauf (siehe „Wo der Vault liegt“), starten Sie dann den Willkommensassistenten und kreuzen Sie „Mein vorhandenes Markdown-Vault“ an. Er wird an Ort und Stelle unverändert übernommen: Es wird kein Ordner hinzugefügt, keine Notiz überschrieben, der Ordner `.obsidian` wird ignoriert, und die Verknüpfungen `[[…]]` funktionieren in beiden Werkzeugen.

## Funktionen je Bildschirm {#fonctions-par-ecran}

### Projekte übernehmen {#reprise-de-vos-projets}

- **Wozu es dient**: beim ersten Start das Vorhandene (Projekte, Agenten-Unterhaltungen, Vault) übernehmen, statt mit einem leeren Baum zu beginnen.
- **So geht es**: drei Schritte, „Auswählen“, „Durchsehen“, „Bestätigen“. Die gewünschten Quellen ankreuzen (ein paar Fragen, ein bezeichneter Ordner, Ihre Unterhaltungen mit Claude Code oder Codex, Ihr Markdown-Vault), dann „Struktur vorschlagen“; die vorgeschlagenen Elemente umbenennen, abwählen oder verschieben; „Bestätigen“ schreibt, „Meinen Baum öffnen“ beendet. „Später“ schließt, ohne etwas zu schreiben.
- **Leerer Vault**: Die Fragen sind von vornherein angekreuzt („Ihre wichtigsten Rollen (durch Kommas getrennt)“, „Ihre laufenden Projekte (durch Kommas getrennt)“); der Schritt „Durchsehen“ schlägt zusätzlich eine „Grundablage“ vor (Ordner `Casquettes/`, `Projets/`, `Inbox/`, `Ressources/`, `Archives/` und die Notiz `Lisez-moi.md`), die sich abwählen lässt. Jedes Projekt erhält eine zu ergänzende Datei `contexte.md` (Ziel, Anhaltspunkte, Hinweise für die KI). Die Schaltfläche „?“ öffnet „Ihr zweites Gehirn organisieren“ in einem neuen Reiter.
- **Gut zu wissen**: nur lokales Lesen, nichts verlässt den Rechner, und es wird kein Modell aufgerufen. Nichts wird überschrieben; eine übernommene Aufgabe setzt ihre ursprüngliche Unterhaltung fort. Einstellungen → „Willkommensassistenten neu starten“ schlägt nur vor, was fehlt. Beim ersten Start folgt der Willkommensbildschirm den ersten Schritten (siehe „Erste Schritte“); haben Sie die Demo gestartet, öffnet er sich nicht mehr von selbst: „Willkommensassistenten neu starten“ öffnet ihn wieder.

### Baum und Listen {#arbre-et-listes}

- **Wozu es dient**: alle Aufgaben an ihrem Platz (Rollen, Vorhaben, Projekte, Aufgaben) und ihren Zustand sehen.
- **So geht es**: linke Spalte, Reiter „Aufgaben“; „Offen“ oder „Alle“. In der Mitte die Gesamtansicht als Kaskade (Status, Aktivität, Fälligkeit, Priorität); ein Klick auf einen Statuszähler filtert. „Bei mir“ zeigt nur, was auf Ihre Handlung wartet. Die Suche (Taste `/`) findet Aufgaben und Notizen.
- **Übernahme überfällig**: Eine abgeschlossene Aufgabe, deren Bericht eine noch nicht in die Hauptversion übernommene Version `gb/*` nennt, erhält mehrere Stunden nach ihrer letzten Speicherung ein oranges Etikett. Hauptversion und tolerierte Verzögerung: Einstellungen → „Übernahme der Versionen“.
- **Ablegen**: eine Aufgabe oder ein Projekt unter ein anderes Element ziehen; „Eine Ebene nach oben — Umschalt+←“; Taste `m` zum Verschieben per Tastatur; jede Handlung lässt sich 10 s lang rückgängig machen.
- **Gut zu wissen**: Der Ordner ist maßgeblich. Ein Projekt zu verschieben verschiebt tatsächlich seinen Ordner, nach einem zu genehmigenden Plan („Anwenden“) und einem Wiederherstellungspunkt des Vaults (git).

### Aufgabe {#tache}

- **Wozu es dient**: die Unterhaltung eines Agenten über eine bestimmte Arbeit und ihr Bericht (was erledigt ist, Ergebnis, wie man es ausprobiert, was noch bleibt).
- **Schlankere Ansicht**: Die Kopfzeile besteht aus einer Zeile (Titel, Status, Ausführungszustand, „Ergebnis“, „Freigeben“ / „Zurückschicken“ bzw. „Anhalten“ / „Neu starten“), der Gesprächsverlauf nimmt den Rest des Bildschirms ein. Die Schaltfläche „Details“ klappt alles Übrige auf: Pfad und übergeordnete Aufgabe, Ich / KI, Motor, Fälligkeit, Wirtschaftlichkeit, Zeilen, Links, Prüfungen, Karte, Text, Aktionen. Ihre Wahl (standardmäßig eingeklappt) bleibt gespeichert. Eine Warnung (Störung, Pause, fehlgeschlagene Kontrolle) erscheint als einzelne Pille, weitere als „+N“; ein Klick öffnet „Details“.
- **So geht es**: Kopf der Aufgabe: Status, KI-Assistent und Modell (die nächste Nachricht geht mit ihnen hinaus), Fälligkeit, Priorität. Unten schreiben, dann Strg+Eingabe. „Anhalten“ unterbricht die Arbeitssitzung; „Eigene Oberfläche des KI-Assistenten“ öffnet dieselbe Unterhaltung in einer Eingabeaufforderung, mit der eigenen Oberfläche des Assistenten; „GoldenBrain-Konsole“ verfolgt sie von einer Eingabeaufforderung aus.
- **Umbenennen**: Klicken Sie auf den Titel der Aufgabe, er wird zu einem Feld; Enter speichert, Escape bricht ab. Nur der Titel ändert sich: Kennung, Vault-Datei, Verknüpfungen und Unterhaltung bleiben gleich, und der neue Titel erscheint überall (Baum, Suche, Telegram, Übersicht). Ein Agent tut dasselbe mit `orch renommer <id> "<Titel>"`. Das Verlassen des Feldes („Fertig“ der Telefontastatur, Tippen daneben) speichert ebenfalls.
- **Ich / KI**: Der Schalter im Kopf zeigt, wer die Aufgabe führt. „👤 Ich“: Kein Agent arbeitet daran (Unterhaltung ausgegraut, weder Prüfung noch automatische Bestätigung); die Aufgabe trägt im Baum ein Etikett. „🤖 KI“: „Übergeben“ gibt dem Agenten die Hand zurück, der Ihre Notizen erhält.
- **Notizen**: Bereich neben der Unterhaltung (jeder lässt sich einklappen). Datierte Notizen in Markdown, die nur Sie hinzufügen und ändern; der Agent liest sie, ohne sie zu schreiben. KI-Schaltfläche: „Zusammenfassen“, „Korrigieren“ oder „Verdichten“, als Vorschlag, den Sie anwenden oder verwerfen. Am Telefon werden die beiden Bereiche übereinandergestapelt.
- **Ergebnis ansehen**: Die Schaltfläche öffnet, was der Assistent erstellt hat, mit der gewohnten Anwendung Ihres Computers: eine im Bericht genannte oder in der letzten Arbeitssitzung geschriebene Datei, eine Website (im Bericht genannte lokale Adresse oder `index.html` des Arbeitsordners) oder den Arbeitsordner. Bei einem einzigen Ergebnis öffnet es sich sofort; bei mehreren erscheint eine Liste zur Auswahl. Wird nichts gefunden, sagt es Ihnen eine Meldung. Nur auf dem Rechner verfügbar (vom Telefon aus abgelehnt); ein Programm oder Skript wird nie gestartet: Stattdessen öffnet sich sein Ordner.
- **Lernen**: Das Menü „Lernen“ im Kopf legt fest, ob der KI-Assistent erklärt, was er tut, nur für diese Aufgabe; standardmäßig folgt es den Einstellungen. Die Erklärungen erscheinen in blauen Kästen in der Unterhaltung, und der Bericht endet mit „Was Sie mitnehmen können“ (drei Punkte).
- **Weitere Handlungen**: „Verknüpfen …“ (Voraussetzung, speist, siehe auch), „Daraus erstellen“ (benachbarte Aufgabe), „Zum Projekt hochstufen“, „Anfragen …“ (Meinung eines Experten des Teams).
- **Gut zu wissen**: Status: Nicht begonnen → In Arbeit → Wartet (ein Mensch wird gebraucht) oder Abgeschlossen → Bestätigt. „Blockiert“ meldet das technische Scheitern einer Arbeitssitzung. Ein Projekt kann eine Prüfung verlangen (`controle:` in seiner `contexte.md`), bevor eine Aufgabe auf „Abgeschlossen“ wechselt. Im Vault wird „Wartet“ als `statut: retour-humain` geschrieben; ein Vault, der einen anderen Namen verwendet, deklariert ihn in `config.toml`: `[vault]`, dann `statut_retour = "<nom>"`.

### Labels {#etiquettes}

- **Wozu**: kurze, von Hand an eine Aufgabe gesetzte Wörter (`#bank`, `#kunde-x`), die der KI sagen, welche Aufgaben zusammengehören. Getrennt von den Vault-Tags (geschlossenes Vokabular, nie angetastet): der Schlüssel `etiquettes:` der Notiz.
- **Setzen**: in den „Details“ der Aufgabe, Karte „Labels“: Wort tippen, Eingabe zum Hinzufügen (Vervollständigung aus bereits verwendeten Labels), Klick auf einen Chip entfernt ihn. Der Baum zeigt die ersten zwei. Sammelweise setzen/entfernen: Leiste „n ausgewählt“, Felder „+ Label“ und „− Label“.
- **Filtern und suchen**: „Filter und Gruppierung“ → Label (kombinierbar mit dem Status) und „Nach Label“; die Suche findet `#Wort`; der Graph filtert sie wie Tags.
- **Die KI lenken**: Der Agent erhält die Labels seiner Aufgabe, ihre Anweisung und die anderen Aufgaben mit demselben Label; der Abgleich vor dem Anlegen gewichtet ein gemeinsames Label; eine vorgeschlagene Verknüpfung zweier etikettierter Aufgaben ohne gemeinsames Label wird abgelehnt. Ein Agent legt kein Label an: er schlägt es vor (Entscheidungen), Sie akzeptieren.
- **Anweisungen, umbenennen, zusammenführen**: Einstellungen → Agenten und Ressourcen → Labels. Die Anweisung (600 Zeichen) wird dem Kontext jedes Agenten beigefügt, der an einer etikettierten Aufgabe arbeitet. Umbenennen auf ein vorhandenes Wort führt zusammen; „Rückgängig“ stellt die Notizen wieder her.
- **Regeln**: Kleinbuchstaben, ohne Akzent und Leerzeichen (`-`), 30 Zeichen, 12 pro Aufgabe. Terminal: `orch etiqueter <id> +Wort -Wort`, `orch etiquettes`.

### Gesprächsmodus {#mode-discussion}

- **Wozu**: Sobald eine Aufgabe geöffnet ist, nimmt das Gespräch den Großteil des Bildschirms ein (über 70 % eines 1366×768-Bildschirms). Nichts wird entfernt: Alles bleibt einen Handgriff entfernt.
- **So geht es**: Die obere Leiste passt in eine Zeile (Logo, Zähler, Suche, „In Arbeit“, „Neue Aufgabe“, „Menü“). „Menü“ (Darüberfahren oder Klick, Alt+M) klappt Team, Konsistenzprüfung, Routine, Ketten, Einstellungen, Manager und die Anleitung auf. Der Aufgabenbaum klappt links zu einer Leiste zusammen: Darüberfahren zeigt eine Vorschau, ein Klick heftet ihn an (Alt+T). Die Notizen klappen rechts zu einem Reiter mit ihrer Anzahl zusammen: Ein Klick öffnet sie (Alt+N). „Alles anzeigen“ (im „Menü“, Alt+D) stellt die vollständige Ansicht wieder her; „Gesprächsmodus“ kehrt zurück. Jede Wahl wird pro Rechner gemerkt; beim ersten Mal erklärt eine Sprechblase alles. Auf dem Telefon ändert sich nichts.
- **Gut zu wissen**: Beim Öffnen erscheinen zuerst die letzten Beiträge, danach der Anfang des Verlaufs. Der Hinweis „Ihr zweites Gehirn ist noch nicht eingerichtet“ erscheint nicht mehr, wenn der Vault schon Notizen enthält.

### Entscheidungen {#decisions}

- **Wozu es dient**: ein einziger Ort, um alles zu entscheiden, was auf einen Menschen wartet.
- **So geht es**: Schaltfläche „Entscheidungen“. Für jedes Element: „Bestätigen“, „Zurücksenden …“, dem Agenten antworten, verschieben (Datum), einen Vorschlag „Annehmen“ oder „Ablehnen“. Der KI-Gärtner (Kohärenzprüfung) und die Agenten schlagen hier auch vor, eine Aufgabe **umzubenennen**, deren Titel nicht sagt, worum es eigentlich geht („„Vereinsverkäufe“ in „API/MCP Vereinsverkäufe“ umbenennen“, mit Begründung): automatisch angewendet (Routineschritt), rückgängig unter „Automatisch angewendet“. Mehrere angekreuzte Aufgaben werden in einem Zug bestätigt. Routineschritte der Agenten (verknüpfen, unterordnen, verschieben, umbenennen, Frist, Aufgabe unter ihrer) warten nicht mehr auf Sie: Sie werden automatisch angewendet, in den „Traces“ der Aufgabe vermerkt und sieben Tage unter „Automatisch angewendet“ unten auf der Seite aufgeführt, jeweils mit „Rückgängig“. Was zu entscheiden bleibt (schließen, Projekt oder Vorhaben machen, Umfang ändern), wird nach sendender Aufgabe in einem eingeklappten Eintrag „Vorschläge von …“ gruppiert: „Alle annehmen“ oder „Alle ablehnen“, oder aufgeklappt eine Zeile je Vorschlag, Grund beim Überfahren oder Aufklappen.
- **Gut zu wissen**: Die automatischen Abschlüsse der letzten 7 Tage stehen dort unter „Automatisch abgeschlossen“, jeweils mit „Wieder öffnen“. Das Etikett „vermeidbar?“ weist auf eine Frage oder Bestätigung hin, die der Agent allein hätte entscheiden können (reine Information, nichts wird verändert); Einstellungen → „Etikett „vermeidbar?““ schaltet es aus oder stellt seine Schwelle ein.

### Wer am Zug ist: vier Zustände {#la-main}

- **Wozu**: keine Aufgabe wartet stumm. Jede offene Aufgabe trägt eine einzige berechnete Markierung mit einem Satz, der den Grund nennt: „Die KI arbeitet“, „In der Warteschlange“ (der Grund wird genannt: Speicher, gleichzeitige Agenten, reservierter Arbeitsplatz, Quota oder Assistent nicht verfügbar, Routine, benannte Abhängigkeit, Pause; ebenso die Fortsetzung), „Menschliche Aktion nötig“ (was von Ihnen erwartet wird, in einem Satz, mit der Geste vor Ort) oder „Erledigt“.
- **Vorgehen**: bei einer Aufgabe mit menschlicher Aktion oder nie gestarteter Aufgabe öffnet die Schaltfläche „An die KI übergeben“ (oder „An die KI zurückgeben“) eine optionale Anweisung und schickt die Aufgabe dann in die Warteschlange. Dieselbe Geste in den Listen, in Heute und, für mehrere Aufgaben, in der Leiste der Sammelbearbeitung (zuerst Vorschau).
- **Gut zu wissen**: Der Zähler der oberen Leiste gliedert sich in drei Aufklapp-Chips: „Zu bestätigen“, „Fragen“ und „Von Ihnen zu erledigen“ (die ältesten zuerst). Unter „Zu bestätigen“ mehrere Aufgaben ankreuzen und „Auswahl bestätigen“: eine einzige, widerrufbare Geste; das Überfahren einer Zeile zeigt Ergebnis und Probe. Eine Aufgabe, die Sie selbst ausführen (Anruf, Anwalt, Bank, Unterschrift), heißt „von Ihnen zu erledigen“: „An die KI übergeben“ bleibt auf ihrer Seite verfügbar, wird in Listen aber nie vorgeschlagen. Von der KI nie gestartete Aufgaben lassen sich mit einem Klick übergeben, zählen aber nicht; eine Dauer-Aufgabe oder eine Gruppe ohne eigene Arbeit heißt „Vorerst erledigt“ (eine Gruppe sagt „3 für Sie, 2 für die KI“). Nach einem Neustart wird der erste Bildschirm (Engines, Updates, Baum) vorbereitet, bevor Anfragen angenommen werden. Jeder Chip trägt Beschriftung und Zähler („Zu bestätigen 86“); nichts überlagert sich und nichts wird abgeschnitten; in einem schmalen Fenster klappt die Leiste sich selbst ein, der Reihe nach: Neben-Chips (Heute, Entscheidungen, Vorschläge, Vorfälle, Ordner abzugleichen, Infos) auf Symbol und Zahl (das Überfahren nennt die Beschriftung), Marker „Intelligent“ ausgeblendet, diese Chips ins „Menü“ verschoben, Suche auf eine Lupe verkleinert, dann „Bei mir“ als Symbole; „Neue Aufgabe“ und „Menü“ bleiben vollständig. Ein Agent muss jeden Durchlauf abschließen (erledigt oder eine präzise Bitte): sonst schickt GoldenBrain ihn höchstens zweimal mit „schließe ab“ zurück, danach kommt die Aufgabe mit „der Agent hat nicht abgeschlossen“ zu Ihnen. Eine Lieferung, die auf ihre Zusammenführung wartet, heißt „Integration läuft“, kein Warten auf Sie. Nur Sie übergeben eine Aufgabe an die KI, ein Agent kann das nicht. Die Vault-Status bleiben die Grunddaten; nichts wird von selbst geändert. Auf dem Telefon löst das Antippen der Markierung in der Aufgabe dasselbe aus wie die Schaltfläche.

### Heute {#aujourd-hui}

- **Wozu es dient**: wissen, was jetzt zu tun ist.
- **So geht es**: Schaltfläche „Heute“ (mit der Zahl der überfälligen Aufgaben). Gruppen: überfällig, heute fällig, innerhalb von sieben Tagen fällig, bei mir; jede nach Priorität sortiert.
- **Gut zu wissen**: Fälligkeit (`echeance: JJJJ-MM-TT`) und Priorität (`priorite: haute | moyenne | basse`) werden im Kopf der Aufgabe oder beim Erstellen gesetzt.

### Laufend {#en-cours}

- **Wozu es dient**: auf einen Blick sehen, was Ihre KI-Assistenten gerade tun und was wartet.
- **So geht es**: In der oberen Leiste auf „Laufend“ klicken (mit Zähler; Adresse `#en-cours`). Für jeden arbeitenden Assistenten: die Aufgabe und ihr Projekt, der Assistent und sein Modell, seit wann, was er tut („führt die Tests aus“, „schreibt build.py“, „hat 3 Dateien geändert“), der Fortschritt seiner Schrittliste, sofern er eine führt, und die von ihm gestarteten Helfer mit Zustand und Dauer. Handlungen: „Öffnen“, „Pausieren“, dann „Fortsetzen“, „Anhalten“ (mit Rückfrage). Darunter: die wartenden Aufgaben und ihr Grund (Speicher, Nutzungskontingent, Voraussetzungen, Rang), die anstehenden Routinen, die offenen Störungen.
- **Gut zu wissen**: Der Bildschirm aktualisiert sich von selbst, wenn ein Assistent vorankommt; bei geschlossenem Bildschirm läuft nichts. Die gestarteten Helfer werden bei Claude Code und OpenCode verfolgt, der Fortschritt bei Claude Code, OpenCode und Codex. Eine manuelle Pause friert den Assistenten ein, ohne etwas zu verlieren; er macht nur mit „Fortsetzen“ weiter (die Speicherregelung rührt ihn nicht an).

### Mobiler Begleiter {#compagnon}
- **Laufende Arbeit**: Tippen Sie auf den Stern ★ einer Aufgabe (Baum oder „In Arbeit“ auf dem Startbildschirm), um sie auf diesem Smartphone anzuheften; die Schaltfläche „Laufende Arbeit“ (`#travail`) zeigt nur diese Aufgaben, jede öffnet ihren Chat: die Unterhaltung mit dem Agenten der Aufgabe und ein Nachrichtenfeld, gesendet wie im vollen Bildschirm. Das Anheften ist eine Einstellung des Smartphones (auf dem Rechner wird nichts geschrieben); der Chat braucht den Rechner online. Status und Struktur ändern sich nur über die üblichen Aktionen.

- **Wozu**: vom Smartphone aus auf einen Blick sehen, was auf Ihre Entscheidung wartet, was arbeitet, und den Projektbaum (nur lesen, mit einer Ausnahme: eine vom Agenten erledigte Aufgabe freigeben oder zurückgeben, online und nach Bestätigung).
- **So geht's**: Der Zugriff läuft über das private Tailscale-Netz und ein gekoppeltes Smartphone (Einstellungen → Geräte; Schritt für Schritt: `docs/TELEPHONE.md`). Auf dem Smartphone die Schaltfläche « Start » der unteren Leiste (Adresse `#compagnon`): « Zu entscheiden » (die Frage jeder Entscheidung), « Laufend » (Assistenten bei der Arbeit), dann « Projekte und Aufgaben » (ein Projekt antippen, « ‹ » geht eine Ebene hoch). Eine Entscheidung oder Aufgabe antippen öffnet sie im gewohnten Bildschirm. Auf dem Startbildschirm installiert, öffnet die App direkt diese Startseite; eine freizugebende Entscheidung ist eine einzige Karte, deren Schaltflächen „Freigeben“ und „Zurückgeben“ im selben Rahmen liegen. Scheitert die Kopplung mangels Netz, wiederholt die Schaltfläche „Erneut versuchen“ sie, ohne den Code neu zu scannen. Optional: `resume = true` in `[distant]` zeigt auf dem Telefon eine Zusammenfassung (140 Zeichen) des Ergebnisses einer freizugebenden Aufgabe; der Text verlässt den Rechner, wird nie offline gespeichert und ist standardmäßig aus. Auf kleinen Bildschirmen stapelt sich die Seite „Entscheidungen“: Titel in voller Breite, größere Schaltflächen. Der Hinweis „Update verfügbar“ erscheint nicht auf dem Telefon (das Update erfolgt am Rechner).
- **Gut zu wissen**: Der Bildschirm aktualisiert sich selbst, solange er offen ist, und zeigt, ob er verbunden ist oder Daten von einem bestimmten Zeitpunkt zeigt. Offline ist optional und standardmäßig aus: `hors_ligne = true` unter `[distant]` in `config.toml` setzen, dann « Offline-Vorschau auf diesem Gerät behalten » ankreuzen; gespeichert werden nur Titel, Status und Entscheidungen, 7 Tage lang, nie der Inhalt von Karten oder Gesprächen. Die Vorschau wird beim Sperren des Geräts oder mit « Daten dieses Geräts löschen » gelöscht. Offline sind Aktionen deaktiviert: sie brauchen den Rechner. Ohne Verbindung sagt der Bildschirm es („Offline · Daten vom …“); ein fehlgeschlagener Vorgang nennt, dass nichts geändert wurde.

### Notizen {#notes}

- **Wozu es dient**: den ganzen Vault durchsuchen und ändern, ohne GoldenBrain zu verlassen.
- **So geht es**: linke Spalte, Reiter „Notizen“ (Modus Erweitert). „Neue Notiz“; „Ändern“ (Taste `e`, Strg+S speichert); „Umbenennen / verschieben …“ schreibt die Verknüpfungen um.
- **Gut zu wissen**: Hat sich die Notiz anderswo geändert (Obsidian, ein Agent), wird das Speichern abgelehnt, und Ihnen werden beide Fassungen angeboten. Dataview-Blöcke werden nicht ausgeführt.
- **Graph**: Schaltfläche „Graph“ im Reiter „Notizen“ (globaler Graph: Notizen, Aufgaben, Ordner und ihre Verknüpfungen, Filter nach Rolle, Projekt, Typ, Schlagwort, Zeitraum); Schaltfläche „Graph“ einer Aufgabe oder „Lokaler Graph“ einer Notiz (einstellbare Tiefe). Ein Klick auf ein Element öffnet die Notiz oder die Aufgabe.

### Datenbanken {#bases}

- **Wozu**: einen Notizordner wie eine Datenbank ansehen, wie in Notion: eine Notiz pro Zeile, die Eigenschaften ihres Kopfes (Frontmatter) als Spalten — Beträge, Daten, Kontrollkästchen, Listen, Links.
- **So geht's**: Reiter „Notizen“, mit der Maus über einen Ordner fahren und ▦ „Als Tabelle anzeigen“ klicken (oder Taste `t` auf dem Ordner). Ein Klick auf eine Spaltenüberschrift sortiert (zweimal: umgekehrt); unter jeder Überschrift filtern (enthaltener Text, Zahl Minimum und Maximum, Datum zwischen zwei Grenzen, Kästchen ja oder nein, Listenwert); „Gruppieren nach“ einer Spalte zeigt eine Zwischensumme je Gruppe; das Menü am Fuß einer Spalte wählt die Berechnung (Summe, Durchschnitt, Min, Max, Anzahl ausgefüllter Werte, verschiedener Werte, angehakter Kästchen); „Spalten“ blendet aus oder wieder ein. Ein Klick auf eine Zeile öffnet die Notiz, ein Klick auf einen Link `[[…]]` die Zielnotiz. Strg+K bietet „Datenbank: <Ordner>“ für kürzlich geöffnete Datenbanken an; die Adresse `#base=<Ordner>` lässt sich teilen.
- **Gut zu wissen**: nur lesend — an Ihren Notizen wird nichts geändert. Nur die Notizen des Ordners selbst werden gelesen (nicht seine Unterordner), höchstens 5.000. Der Typ einer Spalte ergibt sich aus ihren Werten; eine Spalte mit gemischten Werten gilt als Text. Die Ansichtseinstellungen werden je Ordner in diesem Browser gespeichert.

### Dateileser {#lecteur-de-fichiers}

- **Wozu**: eine Datei lesen, ohne GoldenBrain zu verlassen, über jeden Link (Verlauf, Karte, Zeilen, Spuren, Ergebnisse, Notizen).
- **Vorgehen**: Link anklicken. Markdown, Text, Protokolle, CSV-Tabellen, JSON/YAML/XML, Code, HTML, Bilder und PDF öffnen sich in einem Bereich (Esc schließt, „Vollbild“, „Pfad kopieren“, „Quelltext anzeigen“ für Markdown). Andere Formate (Word, Excel, Archive, Medien …) öffnen sich nach Bestätigung in ihrer Anwendung. Die Adresse `#f=<Pfad>` lässt sich teilen.
- **Wissenswert**: HTML erscheint in einem isolierten Rahmen, ohne Skript und ohne Zugriff auf GoldenBrain, und ohne externe Ressourcen, solange Sie „Externe Ressourcen zulassen“ nicht ankreuzen. Lesbar sind nur der Vault, die Arbeitsordner der Aufgaben, deklarierte Ergebnisse und in den Einstellungen › Funktionen › Dateileser hinzugefügte Ordner. Von einem entfernten Gerät: nur Vault und Ergebnisse, nie das Öffnen einer Anwendung.

### Routinen {#routines}

- **Wozu es dient**: eine Anweisung, die ein Agent zu einer festen Uhrzeit ausführt (tägliche Durchsicht, wöchentliche Erhebung).
- **So geht es**: Schaltfläche „Routine“ (Uhr, oben). Titel, Anweisung, Zeitplan („chaque jour 08:00“, „en semaine 18:00“, „lundi,jeudi 09:30“, „toutes les 2 h de 8 h à 20 h“ oder ein Cron-Ausdruck; die Formulierung wird auf Französisch erwartet), Projekt, Unterhaltung (dieselbe oder bei jeder Ausführung eine neue), Nachholen eines verpassten Termins. In der Routine: „Pausieren“, „Jetzt ausführen“, Verlauf der Ausführungen. Eine vorhandene Aufgabe wird mit „In Routine umwandeln“ an Ort und Stelle zur Routine (dieselbe Notiz, dieselbe Unterhaltung); „Routine entfernen“ macht sie wieder gewöhnlich.
- **Gut zu wissen**: Eine Routine trägt im Baum eine Uhr; sie läuft nie zweimal gleichzeitig und geht durch dieselbe Warteschlange wie die Aufgaben.

### Abläufe {#chaines}

- **Wozu es dient**: mehrere der KI übertragene Arbeitsphasen für denselben Ordner aneinanderreihen (z. B. Antwort auf eine Ausschreibung: Analyse, Nutzenversprechen, Lösung, Ausarbeitung, Durchsicht), wobei jede Phase vom Ergebnis der vorigen ausgeht.
- **So geht es**: Schaltfläche „Abläufe“ (oben): Liste der Vorlagen, mitgelieferte („Réponse à un appel d'offres“, „Article ou contenu“) und persönliche, abgelegt in `_meta/chaines/` des Vaults; „Neuer Ablauf“ oder „Bearbeiten“: Titel, Zusammenfassung, gemeinsamer Kontext, überwachter Ordner und Projekt (optional), dann die Phasen (Titel, Anweisungen, Eingabedokumente, erwartetes Ergebnis, KI-Assistent, KI-Modell, Kästchen „Menschliche Freigabe nach dieser Phase“), die sich hinzufügen, löschen und umordnen lassen; „Entfernen“ (persönliche Vorlagen, mit Bestätigung). Manueller Start: „Starten“ in der Liste oder ⛓ an einem Projekt: Vorlage, Projekt, zu bearbeitender Ordner, optionaler Titel. Es entsteht eine übergeordnete Aufgabe mit einer Aufgabe je Phase; ihre Detailansicht zeigt die nummerierten Phasen mit Zustand, einen Link zu jeder, den Zustand des Ablaufs und einen etwaigen Fehler. „Freigeben und fortfahren“ setzt nach einer Phase mit menschlicher Freigabe fort; „Fortsetzen“ startet die fehlgeschlagene Phase neu.
- **Gut zu wissen**: Die Phasen laufen nacheinander, nie parallel. Bei einem überwachten Ordner startet jeder neue Unterordner den Ablauf, ohne bereits vorhandene nachzuholen. Die KI kann die kommenden Phasen an den tatsächlichen Ordner anpassen (überspringen, hinzufügen, verdoppeln, Anweisungen ändern): jede Anpassung wird in der Detailansicht mit ihrer Begründung angezeigt.

### Team {#equipe}

- **Wozu es dient**: Experten (spezialisierte Sichtweisen), die abgeschlossene Aufgaben durchsehen.
- **So geht es**: Schaltfläche „Team“ (Modus Erweitert), „Neuer Experte“: Name, Auftrag (was er prüft), Schwerpunkt (was er zuerst prüft), Auslöser (immer, nach Filter oder auf Anfrage), KI-Assistent und Modell. Aus einer Aufgabe heraus: „Anfragen …“.
- **Gut zu wissen**: Ein Experte gibt eine Meinung ab; er bestätigt nicht, außer mit der Einstellung `[validation] mode = "persona"`.

### Einstellungen {#reglages}

- **Wozu es dient**: Oberfläche und Motor einstellen, ohne eine Datei zu bearbeiten.
- **So geht es**: Schaltfläche „Einstellungen“. Sechs einklappbare Gruppen, jede mit ihrem Zustand in einer Zeile als Titel: Anzeige (Sprache, Detailgrad, Design, Einladung zum Stern), Angezeigte Funktionen, Agenten und Ressourcen (Agenten gleichzeitig, Leistung oder Sparsamkeit, Zusammenfassung langer Unterhaltungen, Lernmodus, KI-Assistenten je Rolle), Freigabe und Vorschläge (Vorschläge der Agenten, Etiketten „vermeidbar?“ und „Übernahme überfällig“), Verbindungen (Telegram, Telefon und weitere Geräte, Hilfsrechner), Installation und Version (Update: Kanal und automatischer Modus, ein Problem melden, erste Schritte erneut ansehen, Willkommensassistenten neu starten). Ein Klick auf einen Titel öffnet oder schließt ihn; geöffnete Gruppen werden von Besuch zu Besuch behalten. Das Feld „Einstellung suchen“ öffnet die betreffende Gruppe (z. B. „Speicher“, „Telegram“). Direktlink zu einem Abschnitt: `#reglages/telegram`, `#reglages/simultanes`, `#reglages/economie`, `#reglages/compactage`, `#reglages/appareils`, `#reglages/executeurs`, `#reglages/installation`, `#reglages/premiers-pas` …
- **Sprache**: Français, English, Deutsch oder español. Beim ersten Start übernimmt GoldenBrain die Sprache des Browsers; Einstellungen → Anzeige → Sprache (oder der erste Bildschirm des Willkommensassistenten) ändert sie, und die Seite lädt neu. Sie gilt für die Bildschirme, die Meldungen, die „?“-Hilfe (Anleitung in der gewählten Sprache) und die Antworten der Agenten; Ordnernamen, Status des Vaults und Befehle ändern sich nicht.
- **Vorschläge**: Einstellungen → Freigabe und Vorschläge. Zwei Familien von Schritten zum Ankreuzen: „Automatisch angewendet“ (standardmäßig: verknüpfen, unterordnen, verschieben, umbenennen, Frist, Aufgabe unter der des Agenten) und „Zu entscheiden“ (schließen, Projekt, Vorhaben, Umfang, Aufgabe anderswo). Ein abgewählter Schritt geht zurück zu den Entscheidungen; die Einstellung „Zu entscheidende Schritte“ (zeigen, annehmen, ignorieren) gilt nur für die zweite Familie. Der Gärtner und der System-Scan schlagen immer nur vor.
- **Lernmodus**: Einstellungen → Agenten und Ressourcen → Lernmodus. Ist er aktiv, erklärt der KI-Assistent bei jedem Schritt in ein oder zwei einfachen Sätzen, was er tut und warum, und schließt mit „Was Sie mitnehmen können“. Kosten: etwas mehr Text bei jeder Arbeitssitzung, also etwas mehr verbrauchtes Nutzungskontingent. Ist er aus, ändert sich nichts.
- **Reflexe des Agenten**: Einstellungen → Agenten und Ressourcen → Reflexe des Agenten (und am Ende der ersten Schritte). GoldenBrain schlägt vor, den Anweisungen jedes KI-Assistenten auf dem Rechner (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md` …) einige Reflexe hinzuzufügen: jede Arbeit einer Aufgabe zuordnen (zuerst fortsetzen, sonst anlegen), erstellte oder geänderte Dokumente im Aufgabenblatt festhalten, Aufgaben, Dokumente und Notizen verknüpfen, das Ergebnis notieren. Für jeden Assistenten: der Zustand (fehlt, aktuell, ältere Version, von Hand geändert), „Änderung ansehen“ (hinzugefügte oder entfernte Zeilen), dann „Annehmen“, „Später“ oder „Entfernen“. Ohne diesen Klick wird nichts geschrieben; der Block steht zwischen zwei Markierungen, der Rest der Datei bleibt unberührt. Nach einem Update, das die Reflexe ändert, kommt der Vorschlag wieder.
- **GitHub-Stern**: Nach einigen Stunden Nutzung, und nur wenn GoldenBrain auf GitHub öffentlich ist, bietet ein einmaliges Fenster „Stern vergeben“, „Später“ oder „Nicht mehr fragen“ an; Einstellungen → Anzeige schaltet es aus.
- **Gut zu wissen**: Die Oberfläche schreibt nur in `config.toml`. Die übrigen Schlüssel (Vault, KI-Assistenten, Anweisung der Agenten) werden in dieser Datei eingestellt, nach dem Muster von `config.exemple.toml`. Eine laufende Eingabe geht nicht mehr verloren, wenn ein Agent im Hintergrund arbeitet. Die Ränder von Feldern und Schaltflächen erreichen in beiden Designs einen Kontrast von 3:1 gegenüber dem Hintergrund (WCAG 1.4.11).

### Update mit einem Klick {#mise-a-jour-d-un-clic}

- **Wozu es dient**: auf die neueste Version wechseln, ohne Eingabeaufforderung.
- **So geht es**: Erscheint die Leiste „Ein Update ist verfügbar“, auf „Aktualisieren“ klicken; die Seite wartet auf den Neustart und lädt dann neu. Ohne die Oberfläche (Windows): Doppelklick auf `mettre-a-jour.cmd`.
- **Gut zu wissen**: Abgelehnt, solange ein Agent arbeitet (danach erneut versuchen) oder wenn Dateien von GoldenBrain von Hand geändert wurden. Der Ordner rückt nur vor, ohne je Änderungen zu vermischen; `config.toml`, `etat`, `journal` und `equipe` werden nie angetastet. Quelle: die Hauptversion (`main`) des öffentlichen Code-Ordners https://github.com/Greal-dev/goldenbrain (das Remote `origin` eines Klons), einstellbar über `[mise_a_jour] branche` und `distant`.
- **Was ist neu**: Die Leiste trägt „Was ist neu?“; ein Klick klappt die Neuerungen der wartenden Version in einfacher Sprache auf. Das Versionsprotokoll ist `CHANGELOG.md` im Hauptordner des Codes (in einem Klon des öffentlichen Repositorys nicht vorhanden; auf Französisch); jede öffentliche Version hat außerdem ihre Notiz auf der Seite „Releases“ des öffentlichen Code-Ordners (abonnieren: „Watch“ → „Custom“ → „Releases“, oder der Feed https://github.com/Greal-dev/goldenbrain/releases.atom).
- **Versionshinweise**: Auf der Seite „Releases“ steht der Hinweis in der Sprache der Seite; ohne Übersetzung melden die englische, spanische und deutsche Fassung „Hinweise auf Französisch“, statt Französisch unter einem fremden Titel auszugeben.
- **Stabiler oder Beta-Kanal**: Einstellungen → „Installation und Version“ → „Update“ → „Kanal“. „Beta“ folgt der Version `beta` des öffentlichen Code-Ordners (Testversionen, vor `main`); die Leiste bietet dann „zum Beta-Kanal wechseln“ an, und die Schaltfläche „Aktualisieren“ wechselt die Version und startet GoldenBrain neu. Zurück zu „Stabil“ geht genauso. Abgelehnt, wenn der Code von Hand geändert wurde oder von einer anderen Version als `main` oder `beta` aus; der Vault wird nie angetastet. Gibt es die Version `beta` im öffentlichen Code-Ordner (noch) nicht, sagt GoldenBrain das in einem Satz, stellt den Kanal auf „Stabil“ zurück und ändert nichts. Zum Testen und Rückmelden: Seite „Beta-Tester werden“ (`BETA.md`).
- **Ein Problem melden oder eine Idee vorschlagen**: Einstellungen → „Installation und Version“ → „Ein Problem melden oder eine Idee vorschlagen“. Die Links öffnen im Browser das GitHub-Formular des öffentlichen Projekts, in dem Version (Kennung, Datum, Kanal) und System bereits ausgefüllt sind — sonst nichts: kein Name, kein Pfad, kein Vault-Inhalt. GoldenBrain sendet nichts; Sie lesen es durch und senden es selbst ab (GitHub-Konto erforderlich). „Eine Frage stellen“ öffnet die Discussions.
- **Automatisches Update**: Einstellungen → „Installation und Version“ → „Update“ → „Ein verfügbares Update selbstständig anwenden“ (standardmäßig ausgeschaltet). Während der Vorbereitung startet keine neue Arbeitssitzung; laufende Sitzungen werden beendet, und eine Sitzung, die die eingestellte Frist überschreitet, wird erst an einem sicheren Wiederaufnahmepunkt unterbrochen (und danach fortgesetzt). Zeitfenster optional; das Update wartet außerdem, bis Sie die Oberfläche nicht mehr berühren. Ein Fehler erscheint in einer Leiste, mit der nötigen Handlung.
- **Während einer Arbeitssitzung neu starten**: Wird „Neu starten“ abgelehnt, weil Arbeitssitzungen laufen, wird „GoldenBrain neu starten, sobald die Arbeitssitzungen beendet sind“ angeboten (nur GoldenBrain, nie der Computer); das Warten lässt sich über dieselbe Leiste abbrechen.

### Manager {#manager}

- **Wozu es dient**: mit einem allgemeinen Agenten sprechen, der alle Aufgaben steuert – „Was steht bei mir an?“, „Wie weit ist X?“, ein Thema übergeben (er leitet es an die passende Aufgabe oder das passende Projekt weiter oder legt eine Aufgabe an), aktualisieren, nachfassen, zwei Doppelungen zusammenführen.
- **So geht es**: Schaltfläche „Manager“ in der oberen Leiste; der Bereich öffnet sich rechts, auf jedem Bildschirm, und bleibt auch nach dem Neuladen offen. Schreiben, dann Eingabe (Umschalt+Eingabe: neue Zeile). „ד schließt ihn; auf dem Telefon füllt er den Bildschirm und „← Zurück“ schließt ihn.
- **Gut zu wissen**: Es ist der Telegram-Assistent, in derselben Unterhaltung: Was auf der einen Seite geschrieben wird, ist auf der anderen zu lesen (Hinweis „über Telegram“), und `/nouveau` beginnt für beide eine neue Unterhaltung. Eine Änderung von Status, Fälligkeit oder Priorität wartet auf Ihr „Bestätigen“ (im Bereich oder in Telegram, nur einmal); eine Umstrukturierung läuft über Entscheidungen. Der Bereich funktioniert ohne Telegram und lädt nichts, solange er geschlossen ist. Der Verlauf behält die letzten 200 Nachrichten und lädt sich nach einer Unterbrechung selbst neu; er springt nur zur neuesten Nachricht, wenn Sie bereits unten gelesen haben.

### Telegram {#telegram}

- **Wozu es dient**: eine Idee, ein Foto oder eine Sprachnachricht vom Telefon senden; daraus wird eine abgelegte Aufgabe.
- **So geht es**: Einstellungen → Verbindungen → Telegram; ein Assistent führt Schritt für Schritt. Mit @BotFather einen Bot erstellen („Ich habe meinen Bot und seinen Zugangsschlüssel“); seinen Zugangsschlüssel eingeben („Den Zugangsschlüssel in einer geschützten Eingabeaufforderung eingeben“ oder ersatzweise im Browser); den Namen des Bots bestätigen („Ja, das ist mein Bot“); dem Bot in Telegram schreiben, dann „Mich erkennen“ und Ihre Unterhaltung ankreuzen; „Testnachricht senden“, dann „Ja, abschließen und Telegram aktivieren“.
- **Gut zu wissen**: Der Zugangsschlüssel wird im Tresor des Computers abgelegt und nie wieder angezeigt. Nur ein Programm kann einen Bot abhören: jeden anderen Leser zuvor beenden. Wer auf die Nachricht „Aufgabe erstellt: …“ antwortet, schreibt an diese Aufgabe. Ein Auftrag, der einer offenen Aufgabe ähnelt, führt dazu, dass deren Aktualisierung vorgeschlagen wird statt einer neuen Aufgabe. „Antworten“ auf eine Nachricht des Assistenten übermittelt ihm den zitierten Text (ein Zitat, nie ein Befehl) und die Aufgabe, von der er sprach.

### Hilfsrechner {#executeurs-distants}

- **Wozu es dient**: Agenten auf anderen Computern arbeiten lassen; der Vault und die Oberfläche bleiben auf dem Hauptrechner.
- **So geht es**: Die Computer über Tailscale verbinden; auf dem Hauptrechner in `config.toml`: `[executeurs]`, dann `ecoute = "<Tailscale-Adresse des Hauptrechners>"`, neu starten; Einstellungen → Verbindungen → „Hilfsrechner“ → „Computer koppeln“ liefert einen kurzen Code. Auf dem anderen Computer: `python orch.py executeur --serveur http://<Adresse des Hauptrechners>:8300 --code <Code>` oder Einstellungen → „Diesen Computer zum Hilfsrechner machen“.
- **Gut zu wissen**: Details, Pannen und Test: `docs/EXECUTEURS.md`. GoldenBrain niemals im Internet freigeben.

## Fehlerbehebung {#depannage}

| Symptom | Wahrscheinliche Ursache | Vorgehen |
|---|---|---|
| Die Seite http://127.0.0.1:8300 antwortet nicht | GoldenBrain angehalten | `./lancer.sh` oder `lancer.cmd` neu starten; unter systemd `systemctl --user status goldenbrain` |
| `ModuleNotFoundError: fastapi` beim Start | Falsches Python | Erste Zeile von `python.local` prüfen, Abhängigkeiten mit diesem Python neu installieren |
| „Address already in use“ | Port belegt | `[serveur] port = 8301` in `config.toml` |
| Der Baum ist leer | Vault nicht gefunden | `[vault] racine` in `config.toml`, dann neu starten |
| KI-Assistent „nicht verfügbar“ | Programm nicht im PATH oder nicht angemeldet | Installieren, anmelden (siehe „KI-Assistenten verbinden“) |
| Störung „KI-Assistent nicht installiert“ | Ein KI-Assistent aus `[credits]` ist auf diesem Computer nicht installiert | Nichts Dringendes: Die Arbeitssitzung wird einmal mit dem nächsten Assistenten aus `[credits]` neu gestartet, und der Ausgleich wählt den fehlenden nicht mehr. Den Assistenten installieren (siehe „KI-Assistenten verbinden“) oder aus `[credits]` entfernen |
| Aufgabe „Blockiert“ | Technisches Scheitern der Arbeitssitzung | Die Ursache in der Unterhaltung lesen, dann eine Nachricht schreiben; eine unterbrochene Sitzung wird mit „Erneut ausführen“ fortgesetzt. Die während der Blockade eingegangenen Nachrichten (Telegram, andere Agenten) warten in der Schlange und gehen der Reihe nach hinaus, sobald Sie schreiben, den Motor wechseln oder den Status ändern (abgeschlossene Aufgabe: Sie entfallen) |
| Aufgabe „Wartet auf den Rechner“ | Ein aufwendiger Test hat den Rechner reserviert | Warten (der Rang in der Warteschlange wird an der Aufgabe und in der Leiste angezeigt) oder in der Leiste „Rechner reserviert“ auf „Freigeben“ klicken |
| „Ein Update ist verfügbar“ lässt sich nicht anwenden | Agent bei der Arbeit oder Datei von GoldenBrain geändert | Nach der Arbeitssitzung erneut versuchen; `git status` im Ordner |
| Leiste „Neu starten“ | GoldenBrain wurde aktualisiert, läuft aber noch in der alten Version | „Neu starten“ klicken |
| Ein Claude-Code-Agent sieht seine MCP-Server nicht (Browser …) | Standardmäßig kein MCP-Server pro Arbeitssitzung (Speicherersparnis) | `mcp: heritage` im Kopf der Notiz der Aufgabe oder `[harnais.claude] mcp = "heritage"` in `config.toml` |
| „Verbindung verloren …“ | GoldenBrain neu gestartet oder angehalten | Ein paar Sekunden warten; sonst neu starten |

## Für einen KI-Agenten {#pour-un-agent-ia}

Zu lesen von jedem Agenten — Claude Code, Codex, OpenCode, Antigravity oder anderen —, der GoldenBrain steuert oder in seinem Repository arbeitet. GoldenBrain wird nicht über eine Bibliothek aufgerufen: Man spricht mit ihm über den Befehl `python orch.py` (vom Stammordner des Repositorys aus, nie über eine `.cmd`) oder über seine lokale API.

**1. Server starten und prüfen**

- Starten: `./lancer.sh` (Linux, macOS) oder `lancer.cmd` (Windows), im Stammordner des Repositorys.
- Prüfen: `curl -s http://127.0.0.1:8300/api/etat` antwortet mit einem JSON-Objekt (laufende Turns, Warteschlange, Entscheidungen). Eine verweigerte Verbindung: Der Server läuft nicht.
- Andere Adresse (in `config.toml` eingestellter Port, Testserver): Variable `ORCH_URL`, zum Beispiel `export ORCH_URL=http://127.0.0.1:8301`; `orch.py` liest sie.
- Ein von GoldenBrain gestarteter Agent erhält `ORCH_URL`, `ORCH_TACHE` (seine Aufgabe) und `ORCH_SAUTS`; `orch.py` nutzt sie, um seine Nachrichten zu signieren und die Weiterleitungen zu begrenzen.

- Jeden Durchlauf abschließen: erledigt (`terminee`), oder eine präzise menschliche Bitte in `prochain_pas` (`en_attente`), oder ein benanntes Warten. Ein Blatt „reste: …“ ohne Adressaten ist eine Anomalie: GoldenBrain schickt höchstens zweimal „schließe ab“ zurück, danach steht die Aufgabe auf „Menschliche Aktion nötig“. Ein Agent übergibt nie eine Aufgabe an die KI (403).

**2. `orch`-Befehle**

| Befehl | Wirkung |
|---|---|
| `guide` | diese Anleitung |
| `arbre` | Baum der offenen Aufgaben |
| `chercher "<Wörter>"` | verwandte Aufgaben |
| `lire <id>` | Bericht, Pfad, Platz, Status, Ausführung einer Aufgabe |
| `etiqueter <id> +Wort -Wort` | Labels setzen oder entfernen (Agent: nur vorhandene, kein Entfernen) |
| `etiquettes` | bekannte Labels, Nutzung und Anweisung |
| `conteneurs` | Container, in die eine Aufgabe abgelegt werden kann |
| `rapprochement ["<Titel>"]` | Aufgaben, die einem Titel nahekommen; ohne Titel: vermiedene Erstellungen |
| `creer "<Titel>" --description "<mindestens ein Satz>"` | eine Aufgabe erstellen (`--conteneur`, `--parent`, `--lancer`, `--mission`); abgelehnt, wenn eine sehr ähnliche offene Aufgabe existiert: sie ergänzen (`dire`) oder erzwingen (`--nouvelle`) |
| `dire <id> "<Nachricht>"` | an die Aufgabe schreiben: Ihr Agent erhält es im nächsten Turn (startet ihn, wenn er frei ist) |
| `renommer <id> "<Titel>"` | den Titel einer Aufgabe ändern (Kennung und Datei unverändert) |
| `relancer <id>` | eine gescheiterte oder unterbrochene Aufgabe neu starten; eine durch den Arbeitsspeicher, einen Neustart oder einen vorübergehenden Dienstfehler unterbrochene Sitzung läuft von selbst weiter (höchstens dreimal, „unterbrochen (automatische Wiederaufnahme in der Warteschlange)“), danach geht die Aufgabe an Sie zurück; ein von Ihnen verlangter Stopp setzt nie von selbst fort. Speichern Sie bei jeder Etappe einen Zwischenstand auf Ihrem Zweig: die Wiederaufnahme findet Arbeitsbaum und Zweig |
| `arreter <id>` | den laufenden Turn anhalten |
| `deleguer "<Titel>" "<Briefing>"` | eine Arbeit an eine von GoldenBrain gestartete Unteraufgabe übergeben |
| `proposer deplacer\|rattacher\|projet\|operation\|ticket\|tache\|lier\|perimetre\|echeance\|fermer\|renommer …` | eine Strukturänderung vorschlagen (`--motif`, Pflicht bei `renommer`) ; `rattacher <id> <parent|racine> [--aussi <id>…]` ordnet einen Stapel Aufgaben in EINEM Vorschlag unter einer Eltern-Aufgabe ein (oder löst sie zum Projekt hin), abgelehnt bei Zyklus, laufender Aufgabe, anderem Projekt, Obergrenze 10 oder gemischten Arbeitsarten; der Mensch nimmt mit einem Klick an. Im einfachen Modus werden Vorschläge ignoriert (Einstellungen > Vorschläge der Agenten); eine Geste, deren Wirkung schon besteht, wird nicht hinterlegt, und wird sie vor der Annahme erreicht, gilt sie ohne Fehler als „bereits erledigt“ Routineschritte (Einstellungen > Vorschläge) werden automatisch angewendet und sind unter Entscheidungen rückgängig zu machen; ein `tache`-Vorschlag eines Agenten wird eine Zeile seiner Aufgabe. |
| `solliciter <persona> "<Frage>"` | Meinung eines Personas des Teams |
| `telegram "<Text>"` | Nachricht an den Nutzer auf Telegram (`--validation`, `--choix`); setzt den konfigurierten Bot voraus |
| `poste reserver "<Grund>"` / `poste liberer` | den Rechner während eines aufwendigen Tests reservieren; ist er belegt, auf die Reihe warten (`--attente <min>`, Standard 30) ; ohne laufende Prüfung verfällt die Reservierung nach 20 Min.; nie mit `pgrep -f` auf ein Muster der eigenen Anweisung warten: Vordergrund oder PID |
| `chaine plan\|sauter\|ajouter\|dedoubler\|consigne …` | den Ablauf der Aufgabe an den tatsächlichen Ordner anpassen: `plan` zeigt ihn; eine Phase überspringen, hinzufügen, verdoppeln oder ihre Anweisungen ändern (nur kommende Phasen), immer mit `--motif`: die Anpassung wird protokolliert und dem Nutzer angezeigt |
| `feu-vert demander\|accorder\|refuser\|verifier <40-Zeichen-sha> [Text] [--a <Aufgabe des Prüfers>] …` | an eine Version gebundene Freigabe (vollständiger 40-Zeichen-Hash); braucht `ORCH_TACHE` |
| `agents-cc [--relever]` | die Claude-Code-Agenten dieses Rechners bündeln und einer Aufgabe zuordnen |
| `reevaluer` | die automatische Validierung für Aufgaben erneut ausführen |
| `console <id> [--url]` | eine Aufgabe verfolgen und ihr vom Terminal aus schreiben |
| `rattacher <envoi> <id>` | eine Telegram-Nachricht einer bestehenden Aufgabe zuordnen (nicht zu verwechseln mit `proposer rattacher`, das Aufgaben unter einer übergeordneten einordnet) |
| `m365 connecter\|demander\|contexte` | Unternehmenswissen von Microsoft 365 Copilot (wenn aktiviert) |
| `telegram-jeton [--pause]` | das Token des Telegram-Bots eingeben, ohne es anzuzeigen (Tresor des Rechners) |
| `jeton-executeur <nom> [--revoquer]` | das Token eines Hilfsrechners erstellen oder widerrufen |
| `executeur [installer]` | diesen PC zum Ausführer eines führenden GoldenBrain machen |
| `fiche` | Ergebniskarte und vorgeschlagener Status eines gebündelten Laufs |
| `natif <fichier>` | Relais der nativen Oberfläche (von GoldenBrain gestartet, nicht von Hand) |
| `poste etat` | sehen, wer den Rechner belegt |

`python orch.py <Befehl> -h` nennt die Optionen jedes Befehls.

**3. REST-API** (http://127.0.0.1:8300, JSON). Jeder Schreibzugriff trägt den Header `X-Orchestrateur: 1`; ohne ihn antwortet der Server mit 403 (Schutz gegen eine fremde Webseite).

| Route | Wirkung |
|---|---|
| `GET /api/etat` | Zustand des Rechners: laufende Turns, Warteschlange, Entscheidungen, Vorschläge |
| `GET /api/arbre` | Baum der Aufgaben |
| `GET /api/recherche?q=<Wörter>` | suchen |
| `GET /api/taches/{id}` | eine Aufgabe (Status, Bericht, Notizen, Ausführung) |
| `POST /api/taches` | erstellen: `titre`, `description`, und wahlweise `conteneur`, `parent`, `lancer`, `mission`, `harnais`, `modele`, `echeance`, `priorite`, `forcer` (eine sehr ähnliche Aufgabe übergehen), `groupe` |
| `POST /api/taches/{id}/messages` | an die Aufgabe schreiben: `texte` (und `de`: die ID der schreibenden Aufgabe) |
| `POST /api/taches/{id}/statut` | einen Status setzen: `statut` — menschliche Handlung, siehe die Regeln |
| `POST /api/taches/{id}/notes` | eine Notiz des Menschen hinzufügen: `texte` |
| `POST /api/taches/{id}/executant` | `executant`: `humain` (Ich) oder `ia` |
| `POST /api/taches/{id}/relancer` | neu starten |
| `GET /api/propositions` · `POST /api/propositions` | auflisten · vorschlagen: `type`, `tache`, `valeur`, `motif` |
| `POST /api/propositions/{n}/accepter` · `…/refuser` | entscheiden — menschliche Handlung |
| `POST /api/propositions/{n}/annuler` | automatisch angewendeten Schritt rückgängig machen — menschliche Handlung |
| `GET /api/guide[?langue=fr\|en\|de\|es]` | diese Anleitung, als reiner Text (`orch guide` liefert nur Französisch) |
| `GET /api/evenements` | Ereignisstrom (SSE) |

**4. Regeln**

- **Abgleichen vor dem Erstellen**: zuerst `chercher` oder `rapprochement "<Titel>"`; eine ähnliche Aufgabe wird ergänzt (`dire`), statt verdoppelt zu werden.
- **Integration**: In einem Projekt mit `integration:` verknüpfen `creer` und `deleguer` die neue Aufgabe automatisch mit der Integrationsaufgabe (`alimente`); sonst setzt eine Aufgabe, die einen Branch liefert, diese Verknüpfung direkt (`proposer lier <id> alimente <Integration>`): Eine `alimente`-Verknüpfung zu einer Dauer-Aufgabe ist ein Routineschritt, wird sofort angewandt und in den „Traces“ der Aufgabe vermerkt, nie in Entscheidungen wartend gelassen; andere Verknüpfungen folgen der Vorschlagsrichtlinie. Seit dem 24.11. ist jede vorgeschlagene Verknüpfung standardmäßig ein Routineschritt (Einstellungen > Vorschläge).
- **Nie ein Statuswechsel ohne Zustimmung eines Menschen**: Ein Agent setzt nicht `fait`, nimmt keinen Vorschlag an, bestätigt keine Aufgabe; er liefert seinen Bericht, und der Mensch bestätigt. Die Routen `statut`, `valider`, `accepter` sind Handlungen der Oberfläche.
- **Aufgaben „Ich“** (`executant: humain`): Der Mensch führt sie; GoldenBrain lehnt dort jeden Turn und jeden Schreibzugriff eines Agenten ab, außer Zeilen und Verknüpfungen (ein Agent kann sie lesen und etwas vorschlagen); „Übergeben“ ist die menschliche Handlung, die sie an die KI zurückgibt.
- Der Vault ist die einzige Datenbank; nie das Frontmatter einer Notiz umformatieren.
- Nie selbst einen Ordner verschieben: vorschlagen (`orch proposer`), der Mensch nimmt an.
- Kein Versand, keine Veröffentlichung, keine Zahlung und keine Löschung ohne schriftliche Zustimmung des Nutzers.
- Ein von GoldenBrain gestarteter Agent beendet jede Antwort mit dem Block `<fiche>`, der in der erhaltenen Anweisung beschrieben ist.

**5. Durchgängige Beispiele**

Eine Aufgabe wiederfinden oder erstellen, dann übergeben:

```bash
python orch.py rapprochement "Versionshinweise verfassen"
python orch.py creer "Versionshinweise verfassen" \
  --description "Die Änderungen der Woche zusammenfassen; Nachweis: Die Notiz existiert im Vault."
python orch.py lire 2026-11-19-versionshinweise-verfassen
python orch.py dire 2026-11-19-versionshinweise-verfassen "Beginne mit dem Git-Protokoll der Woche."
```

Dasselbe über die API:

```bash
curl -s http://127.0.0.1:8300/api/etat
curl -s -X POST http://127.0.0.1:8300/api/taches \
  -H 'X-Orchestrateur: 1' -H 'Content-Type: application/json' \
  -d '{"titre": "Versionshinweise verfassen", "description": "Die Änderungen der Woche zusammenfassen; Nachweis: Die Notiz existiert im Vault."}'
curl -s "http://127.0.0.1:8300/api/recherche?q=versionshinweise"
curl -s -X POST http://127.0.0.1:8300/api/taches/2026-11-19-versionshinweise-verfassen/notes \
  -H 'X-Orchestrateur: 1' -H 'Content-Type: application/json' -d '{"texte": "Den Ton nüchtern halten."}'
```

Eine Ablage vorschlagen, statt sie vorzunehmen:

```bash
python orch.py proposer deplacer 2026-11-19-versionshinweise-verfassen Projets/C1-Site \
  --motif "Die Versionshinweise gehören zur Website"
```

Die Kennung einer Aufgabe liefert `creer` (und `arbre`, `chercher`): Datum des Tages und Titel in Kleinbuchstaben.

**Weiterführend**: `docs/ARCHITECTURE.md` (Module, Invarianten `INV-*`, Verträge), `docs/CODE_MAP.md` (Dateikarte), `CLAUDE.md` (Regeln des Repositorys).
