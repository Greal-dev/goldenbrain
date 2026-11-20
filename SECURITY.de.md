# Sicherheit

[English](SECURITY.md) · [Français](SECURITY.fr.md) · Deutsch · [Español](SECURITY.es.md)

## Eine Schwachstelle melden
Eröffnen Sie kein öffentliches Ticket. Nutzen Sie die private Meldung von GitHub (Reiter „Security“, „Report a vulnerability“). Beschreiben Sie das Problem, die Version (Commit) und eine Möglichkeit, es zu reproduzieren. Eine Empfangsbestätigung folgt nach Möglichkeit.

## Bedrohungsmodell
- GoldenBrain ist ein **lokales Einzelnutzer**-Werkzeug: Der Server lauscht auf `127.0.0.1` und hat keine Authentifizierung. Setzen Sie ihn niemals einem Netzwerk aus.
- Es startet KI-Agenten-Harnesses mit den Rechten Ihrer Sitzung, oft im Modus ohne Bestätigung (`config.exemple.toml`). Ein Agent kann also alles lesen und ändern, was Ihr Konto lesen und ändern kann: Vertrauen Sie ihm Aufgaben entsprechend an.
- Ein von einem Agenten gelesener externer Inhalt (Webseite, E-Mail) kann bösartige Anweisungen enthalten; die gemeinsame Anweisung verlangt, ihn nie als Befehl zu behandeln, ohne dass dies eine Garantie wäre.
- Die Harnesses verwalten ihre eigenen Zugangsdaten. GoldenBrain speichert nur die optionalen Geheimnisse der Konnektoren (das Token des Telegram-Bots): aus einer Umgebungsvariable gelesen oder von den Einstellungen außerhalb des Repositorys geschrieben — unter Windows mit DPAPI verschlüsselt, sonst als nur für Ihr Konto lesbare Datei (0600). Ein Geheimnis wird nie protokolliert noch in den Vault geschrieben.
