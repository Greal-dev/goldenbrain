# Roadmap

English · [Français](ROADMAP.fr.md) · [Deutsch](ROADMAP.de.md) · [Español](ROADMAP.es.md)

Three horizons, no fixed dates. Each horizon starts only when the previous one holds up in daily use. Every entry gives its intent, the acceptance criterion, the extension point it touches and a size (S: a few days, M: one to two weeks, L: more). **Contributions welcome** marks entries that suit an outside contributor; open an issue before starting so the approach can be agreed.

Principles that every entry keeps: one local server per workstation; the vault's files are the only source of truth; each task is the native conversation of a harness, resumed as is; no second task database, no cloud service required.

## Horizon 1 — Reliable daily steering

**R1 — Result and trial in the task card** · S · core (task card, « À moi » view) · **delivered**
- Intent: a finished task states its result: link to the deliverable or useful passage, available check (or its explicit absence), trial scenario with expected result. Sending a task back states expected vs observed and resumes the same conversation.
- Accepted when: opening a finished task from « À moi », its deliverable and trial are clear without rereading the thread; sending back an anomaly keeps the same task and session; a missing link stays visible as missing.

**R2 — Completion conditioned by the required check** · M · core (engine) + project templates · **delivered** (see `docs/GUIDE.md`: `controle:` in the project's `contexte.md`)
- Intent: when a project declares a check, a bounded verifier records verdict, date, reference of the checked result and log; a missing, failed or stale check prevents a conclusive "done". Human validation stays separate. No workflow engine, no check imposed on every task.
- Accepted when: an incorrect result keeps the task open with its cause; a corrected result shows the log and checked version; a later change makes the old verdict stale; a task without a required check never shows a fictitious positive proof.

**R3 — Return to the attention view** · S · web interface · **contributions welcome**
- Intent: remember filters, selection, folded nodes and scroll position; keep parents and context when opening a conversation; hide only empty secondary views.
- Accepted when: after filtering, unfolding a project, opening a conversation, coming back and reloading, filters and context are kept and a new error remains findable.

**R4 — Readable handoff between tasks** · S · core + web interface
- Intent: next to existing links, show the source task's title, state, situation and result; for a turn, show origin of the message, reason, last state and error from the log. Computed on read; no copy, no competing status.
- Accepted when: from a fed task, the source and its result are understandable without browsing several threads; changing the source updates the reading without copying its card.

**R5 — Context provided and history accessible** · S · harness adapters + web interface · **contributions welcome**
- Intent: show the paths passed to the harness, their role and the turn date, then current and previous session references. Say "provided to the agent", not "read by the agent". Open the native history or report it unavailable; never copy transcripts into the vault.
- Accepted when: after correcting a note and resuming, current note and past references are findable; missing history is reported; no transcript is added to the vault.

**R6 — Propagation on useful progress** · M · core (links)
- Intent: notify fed tasks only when business state, result or artifact version actually changed; keep, per destination, the last useful transmission and its delivery state; keep the hop limit.
- Accepted when: a turn without change wakes nothing; a modified deliverable at the same path triggers one useful notification; nothing repeats after a restart; a failed delivery stays visible and resumable.

**R7 — Derivation whose lineage survives a restart** · M · core + harness adapters
- Intent: keep origin task and session, target, derivation mode and handoff state before the first launch; links navigable both ways; a harness unable to fork says so.
- Accepted when: a validated derivation survives a restart with its origin; the native fork is used when available; a harness without fork support gives an explained refusal.

**R8 — Capture and resume without losing a draft** · S · web interface · **contributions welcome**
- Intent: keyboard access to task creation; an unsent message survives switching tasks within the open tab; no new date parser.
- Accepted when: a draft is intact after switching tasks and back; no duplicate task is created; a word like "Friday" in a title sets no due date without an explicit choice.

**Hardening** · S each · core + tests · **contributions welcome** (good first issues)
- Server-side hop counter and per-turn agent token; configurable idle timeout for a silent turn; bounds on event-stream subscribers and queues; modification-time check before writing a note; delimiting and capping vault text injected into agent instructions.
- Missing tests: saturation of simultaneous agents, maximum turn duration, hops end to end, event-stream reconnection.
- Accepted when: each item has its regression test and the gate stays green.

**Terminal console: native harness functions** · M · console + harness adapters · **contributions welcome**
- Intent: in the terminal console, Esc interrupts a turn and keeps the conversation; preview of changed files; model switch; plan mode (think without modifying); image paste — per harness, where the harness supports it.
- Accepted when: each function works or is explicitly reported unavailable for each supported harness.

Horizon 1 is reached when, after a week of use, an operator follows five to seven pieces of work from the tree, the vault is up to date without reminders, two tasks have exchanged results, a restructuring was validated in one gesture, every accepted result has an explicit trial, and no technical authorization was waited for.

## Horizon 2 — Absorb routines and inputs

**Recurring tasks** · M · core (engine) · **delivered** (Routines)
- Intent: a permanent task wakes up on schedule in the same conversation; next wake-up visible; skip and suspension explicit; a single catch-up after downtime.
- Accepted when: no duplicate, no silent restart of an interrupted turn, and the next wake-up is always visible.

**Connectors** · M each · connectors · Telegram **delivered**; others **contributions welcome**
- Intent: route an incoming message (messaging app, mail digest, scanned document) to the right task, or create a classified task linked to an action. A mail that needs an answer becomes a draft, never a sent message.
- Accepted when: each input lands in exactly one task, through the local API, with its source referenced; nothing is sent on the user's behalf.

**Procedure templates** · S · project templates · **contributions welcome**
- Intent: templates for procedures that are really repeated (frontmatter, sections, required check).
- Accepted when: a template creates a task that passes the gate's checks and needs no manual fix.

A routine is automated only after about two weeks of successful manual or assisted use.

## Horizon 3 — A maintainable local product for others

**Onboarding with a neutral example** · M · project templates + documentation · **contributions welcome**
- Intent: a new user starts from a fictitious example vault, connects one harness, and runs capture → work → trial → resume alone.
- Accepted when: an outside user does it without help and finds their files usable outside GoldenBrain.

**Installation and update on other systems** · L · core + launch scripts · Linux **delivered**; macOS **contributions welcome**
- Intent: install and update on Linux and macOS as on Windows (launch scripts, process control), without losing configuration.
- Accepted when: the gate passes on the three systems and an update keeps `config.toml` and local state.

**Interface translation** · L · web interface + translations · **contributions welcome**
- Intent: the interface, currently in French, offers English, German and Spanish.
- Accepted when: switching language changes every label without changing any vault key or value.

**More harness adapters** · M each · harness adapters · **contributions welcome**
- Intent: support further command-line agent harnesses through the common turn contract.
- Accepted when: the adapter passes the shared harness tests with recorded, fictitious test data.

## Not planned
Teams, seats and fine-grained permissions; cloud, co-editing or home-made synchronization; workflow builders or query languages; a new agent platform or capability catalog; a Git forge, merges or deployments inside the product; canvas or block editor; productivity scores or agent performance dashboards; copying a task for each occurrence. GoldenBrain stays a local cockpit for one operator, on top of plain files and native harnesses.
