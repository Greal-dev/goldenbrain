# Security

English · [Français](SECURITY.fr.md) · [Deutsch](SECURITY.de.md) · [Español](SECURITY.es.md)

## Reporting a vulnerability
Do not open a public issue. Use GitHub's private reporting ("Security" tab, "Report a vulnerability"). Describe the problem, the version (commit) and a way to reproduce it. An acknowledgement follows as far as possible.

## Threat model
- GoldenBrain is a **local, single-user** tool: the server listens on `127.0.0.1` and has no authentication. Never expose it on a network.
- It launches AI agent harnesses with the rights of your session, often in no-confirmation mode (`config.exemple.toml`). An agent can therefore read and modify whatever your account can read and modify: assign tasks accordingly.
- External content read by an agent (web page, email) may contain malicious instructions; the common instruction tells agents never to treat it as an order, which is not a guarantee.
- The harnesses manage their own credentials. GoldenBrain stores only the optional connector secrets (the Telegram bot token): read from an environment variable, or written by Settings outside the repository — encrypted with DPAPI on Windows, a file readable only by your account (0600) elsewhere. A secret is never logged nor written to the vault.
