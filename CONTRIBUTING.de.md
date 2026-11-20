# Mitwirken

[English](CONTRIBUTING.md) · [Français](CONTRIBUTING.fr.md) · Deutsch · [Español](CONTRIBUTING.es.md)

Danke für Ihr Interesse. Kleine Korrekturen können direkt als Pull Request kommen; für alles Größere eröffnen Sie bitte zuerst ein Issue, damit wir uns über das Vorgehen einigen. Die [Roadmap](ROADMAP.de.md) zeigt, wo Hilfe am meisten willkommen ist.

## Bevor Sie beginnen
In dieser Reihenfolge lesen:
1. `CLAUDE.md` — der Arbeitsvertrag: kanonische Befehle, Regeln, gefährliche Zonen.
2. `docs/ARCHITECTURE.md` — Module, Verträge und die Invarianten `INV-*`, die nie verletzt werden dürfen.
3. `docs/CODE_MAP.md` — jede Datei, ihre Rolle, die Invarianten, die sie trägt, und ihre Tests.

Code, Bezeichner, Beschriftungen der Oberfläche und Entwurfsdokumente sind auf Französisch; Issues und Pull Requests können auf Englisch, Französisch, Deutsch oder Spanisch verfasst werden.

## Wo mitwirken
Die bevorzugten Erweiterungspunkte fügen eine Fähigkeit hinzu, ohne den Kern anzufassen:
- **Harness-Adapter** — einen neuen Kommandozeilen-Agenten-Harness unterstützen: ein Modul in `src/orchestrateur/harnais/`, das den gemeinsamen Durchlaufvertrag umsetzt, plus ein Eintrag im Register `HARNAIS`. Die vorhandenen Adapter und ihre aufgezeichneten Testdaten (`tests/donnees/`) dienen als Vorlage.
- **Konnektoren** — Aufgaben von anderswo hereinholen (Messaging, E-Mail, Scanner…) über die lokale HTTP-API oder den Befehl `orch`, nie durch Schreiben ins vault an GoldenBrain vorbei.
- **Übersetzungen** — die Begrüßungsdokumente (README, CONTRIBUTING, SECURITY, ROADMAP) gibt es in vier Sprachen, sie müssen übereinstimmen; die Übersetzung der Oberfläche steht auf der Roadmap.
- **Aufgaben- und Projektvorlagen** — Frontmatter-Vorlagen (`[vault.gabarit_tache]`) und Beispiele für `contexte.md` für gängige Projektarten, mit fiktivem Inhalt.

## Regeln
- Keine neue Abhängigkeit; Oberfläche ohne Build-Schritt (natives HTML, CSS, JS).
- Ein Modul ≤ 500 Zeilen mit Kopf (Rolle, Grenzen, getragene Invarianten); ein Kommentar sagt, warum, und nennt die betroffene Invariante.
- Tests schreiben nie in ein echtes vault (temporärer Ordner) und starten nie einen echten Harness (Attrappen-Adapter).
- Jede Korrektur bringt ihren Regressionstest mit; die Dokumentation ändert sich im selben Commit wie der Code.
- **Keine personenbezogenen Daten** (INV-PUB-1): kein Name, keine E-Mail-Adresse, kein Pfad Ihres Rechners, kein Auszug aus einem echten vault oder Gespräch, keine Sitzungskennung, kein Token. Nur fiktive Testdaten. Kopieren Sie `.sensible.exemple` nach `.sensible` und tragen Sie Ihre eigenen Muster ein: Das Gate weist sie zurück.

## Der Weg eines Beitrags
1. **Zuerst ein Ticket.** Eröffnen Sie ein Issue mit dem passenden Formular (*Bug report* oder *Feature request*); eine Frage gehört in die Discussions. In der Anwendung öffnet *Einstellungen → Installation und Version → Problem melden* das Formular mit bereits eingetragener Version und System. Labels: `bug`, `évolution` (Erweiterung), `à trier` (zu sichten) sowie `bon premier ticket` (gutes erstes Ticket) oder `aide bienvenue` (Hilfe willkommen) für Tickets, die sich an Neue richten.
2. **Ein Branch.** Forken Sie das Repository und arbeiten Sie auf einem nach dem Ticket benannten Branch (`fix/123-kurzer-titel`).
3. **Ein Pull Request** gegen `main` dieses Repositorys, mit Verweis auf das Ticket (`Fixes #123`).
4. **Automatische Prüfungen** (GitHub Actions): das Gate unter Linux und Windows sowie die DCO-Signatur. Beide müssen grün sein.
5. **Automatische Durchsicht.** Ein KI-Prüfer liest den Diff (Sicherheit, Invarianten `INV-*`, Tests, Umfang) und kommentiert mit P1 (blockierend), P2 (nachbessern), P3 (optional). Er führt Ihren Code nie aus und führt nie zusammen: Er informiert einen Maintainer, der entscheidet.
6. **Übernahme.** Das Projekt wird in einem Repository der Maintainer entwickelt, dessen Spiegel dieses ist. Nach der Annahme überträgt ein Maintainer Ihre Änderung dorthin, Autorschaft und Signatur bleiben erhalten; der nächste grüne Build veröffentlicht dieses Repository neu, und Ihr Pull Request wird mit einem Link auf den veröffentlichten Commit geschlossen. Er wird also geschlossen statt zusammengeführt — Ihr Beitrag ist dennoch enthalten.

Betatester folgen dem Branch `beta`: siehe [BETA.de.md](BETA.de.md).

## Gate
`python scripts/check.py` muss vor dem Einreichen grün sein: Tests, Strukturprüfungen, Code-Karte, Veröffentlichungsschutz. Die kontinuierliche Integration führt dasselbe Gate unter Linux und Windows bei jedem Pull Request aus. Die Oberflächenszenarien (`python scripts/check_ui.py`, Playwright) laufen nur lokal.

## Commits signieren (DCO)
Beiträge werden unter dem [Developer Certificate of Origin](https://developercertificate.org/) angenommen: Mit der Signatur bestätigen Sie, dass Sie die Änderung geschrieben haben oder sie unter der Lizenz des Projekts einreichen dürfen. Signieren Sie jeden Commit mit `git commit -s`, das eine Zeile `Signed-off-by: Ihr Name <ihre@adresse>` anfügt. Eine Contributor License Agreement (CLA) gibt es nicht. Die kontinuierliche Integration lehnt einen Pull Request mit einem unsignierten Commit ab.

Ein Pull Request = ein Thema; Commit-Nachrichten im Imperativ. Eine sichtbare Änderung ergänzt die Nachricht um eine Zeile `Nouveauté: <was sich für die Nutzer ändert, in einfachen Worten>`: Sie erscheint in `CHANGELOG.md` und in den Versionshinweisen.

## Lizenz
GoldenBrain steht unter der Apache License 2.0 (`LICENSE`). Ihre Beiträge stehen unter denselben Bedingungen.
