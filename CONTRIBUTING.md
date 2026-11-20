# Contributing

English · [Français](CONTRIBUTING.fr.md) · [Deutsch](CONTRIBUTING.de.md) · [Español](CONTRIBUTING.es.md)

Thank you for your interest. Small fixes can go straight to a pull request; for anything larger, open an issue first so we can agree on the approach. The [roadmap](ROADMAP.md) lists the work where help is most welcome.

## Before you start
Read, in this order:
1. `CLAUDE.md` — the working contract: canonical commands, rules, dangerous zones.
2. `docs/ARCHITECTURE.md` — modules, contracts, and the invariants `INV-*` that must never break.
3. `docs/CODE_MAP.md` — every file, its role, the invariants it carries and its tests.

The code, identifiers, interface labels and design documents are in French; issues and pull requests may be written in English, French, German or Spanish.

## Where to contribute
The preferred extension points let you add a capability without touching the core:
- **Harness adapter** — support a new command-line agent harness: one module in `src/orchestrateur/harnais/` implementing the common turn contract, plus one entry in the `HARNAIS` registry. Use the existing adapters and their recorded test data (`tests/donnees/`) as models.
- **Connectors** — bring tasks in from elsewhere (messaging, mail, scanner…) through the local HTTP API or the `orch` command, never by writing to the vault behind GoldenBrain's back.
- **Translations** — the welcome documents (README, CONTRIBUTING, SECURITY, ROADMAP) exist in four languages and must stay aligned; translating the interface is a roadmap item.
- **Task and project templates** — frontmatter templates (`[vault.gabarit_tache]`) and `contexte.md` examples for common kinds of projects, with fictitious content.

## Rules
- No new dependency; interface without a build step (native HTML, CSS, JS).
- A module ≤ 500 lines with its header (role, boundaries, invariants carried); a comment says why and cites the invariant concerned.
- Tests never write to a real vault (temporary folder) and never launch a real harness (fake adapter).
- Every fix comes with its regression test; documentation changes in the same commit as the code.
- **No personal data** (INV-PUB-1): no name, email address, path from your machine, excerpt of a real vault or conversation, session identifier or token. Fictitious test data only. Copy `.sensible.exemple` to `.sensible` and add your own patterns: the gate will refuse them.

## How a contribution travels
1. **An issue first.** Open an issue with the form that fits (*Bug report* or *Feature request*); a question goes to Discussions. In the app, *Settings → Installation and version → Report a problem* opens the form with the version and system filled in. Labels: `bug`, `évolution`, `à trier` (to triage), and `bon premier ticket` (good first issue) or `aide bienvenue` (help wanted) for issues open to newcomers.
2. **A branch.** Fork the repository and work on a branch named after the issue (`fix/123-short-title`).
3. **A pull request** against `main` on this repository, linking the issue (`Fixes #123`).
4. **Automatic checks** (GitHub Actions): the gate on Linux and Windows, and the DCO sign-off. Both must be green.
5. **Automatic review.** An AI reviewer reads the diff (security, `INV-*` invariants, tests, scope) and comments with P1 (blocking), P2 (should fix), P3 (optional) findings. It never runs your code and never merges; it informs a maintainer, who decides.
6. **Landing.** The project is developed in a maintainers' repository that this public one mirrors. Once accepted, a maintainer applies your change there with your authorship and sign-off preserved; the next green build republishes this repository, and your pull request is closed with a link to the published commit. It is therefore closed rather than merged — your contribution is in all the same.

Beta testers follow the `beta` branch: see [BETA.md](BETA.md).

## Gate
`python scripts/check.py` must be green before you submit: tests, structure checks, code map, publication guard. Continuous integration runs the same gate on Linux and Windows on every pull request. The interface scenarios (`python scripts/check_ui.py`, Playwright) run locally only.

## Sign your commits (DCO)
Contributions are accepted under the [Developer Certificate of Origin](https://developercertificate.org/): by signing off, you certify that you wrote the change or have the right to submit it under the project's license. Add the sign-off to every commit with `git commit -s`, which appends a line `Signed-off-by: Your Name <your@email>`. There is no contributor license agreement. Continuous integration rejects a pull request containing an unsigned commit.

One pull request = one subject; commit messages in the imperative mood. A visible change adds a line `Nouveauté: <what changes for the user, plain words>` to its message: it appears in `CHANGELOG.md` and the release notes.

## License
GoldenBrain is licensed under the Apache License 2.0 (`LICENSE`). Your contributions are licensed under the same terms.
