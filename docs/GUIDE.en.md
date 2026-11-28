# GoldenBrain guide

Updated on 2026-11-28.

GoldenBrain is a control station: you hand tasks to AI agents (Claude Code, Codex, OpenCode, Copilot, Antigravity), each filed in its proper place in your vault (a folder of Markdown notes). GoldenBrain organises and supervises; the agent works in its own conversation, which you can pick up again at any time.

This guide can be read in the application (the “?” button at the top right), in the code folder (`docs/GUIDE.md`) or by an agent (`python orch.py guide`). Each section answers three questions: what it is for, how to do it, what to know. In the application, the “Search the guide” field keeps only the sections that contain the word; the “?” next to the title of Settings, Team and Decisions opens their section directly; a section can be shared by its link (`#guide=reglages`).

## Install {#installer}

Two routes: **in one click** (no command prompt and no Python to install: everything is supplied), or **by hand** from the code (Linux, Windows below). Either way you then need a vault (a folder of Markdown notes, Obsidian or not; GoldenBrain starts without one) and at least one AI assistant (see “Connect the AI assistants”).

### In one click {#en-un-clic}

What it is for: installing GoldenBrain like an ordinary application. Python, its components and (on Windows) Git are bundled; nothing else is changed on the computer and no administrator rights are requested (except the .deb package, which the software centre installs).

- **Windows**: download `GoldenBrain-installation.exe` (GoldenBrain releases page on GitHub), double-click it, follow the three screens. GoldenBrain starts at the end, then from the Start menu. Windows may warn “unknown publisher” (unsigned installer): “More info” then “Run anyway”.
- **Linux (Debian, Ubuntu)**: download `goldenbrain_<version>_amd64.deb`, double-click it (software centre) or `sudo apt install ./goldenbrain_*.deb`. GoldenBrain appears in the applications menu and also starts with the `goldenbrain` command.
- **Linux (others) and macOS**: copy and paste into a command prompt (Terminal on macOS), just once:
  `curl -fsSL https://github.com/Greal-dev/goldenbrain/raw/main/installation/installer.sh | bash`
  Installation takes two to three minutes, creates the menu entry (Linux) or `GoldenBrain` in your account’s Applications folder (macOS), then starts GoldenBrain. Git is required: on macOS, accept the tools the system offers, then run the command again.
- **macOS, without a command prompt**: download `GoldenBrain-macos-arm64.zip` (recent Macs; `x86_64` for Intel Macs), open it, drag GoldenBrain into Applications. As the application is not signed, the first launch is done by right-click → Open (or System Settings → Privacy & Security → “Open Anyway”).

How it works: each launch opens the browser on GoldenBrain, starting GoldenBrain on this computer if it is not running yet (a second click does not start a second one). On first launch, the application is copied into your personal folder (`~/.local/share/goldenbrain/app`, `~/Library/Application Support/GoldenBrain/app` or `%LOCALAPPDATA%\GoldenBrain\app`): this copy is what the “One-click update” moves forward, and it keeps your settings (`config.toml`).

Good to know: the installation speaks the system language (French, English, German or Spanish; English for any other language) and, on first launch, copies it into `config.toml` (`[interface] langue`) so that GoldenBrain opens in the same language; an existing `config.toml` is never modified. Reinstalling or uninstalling never touches this copy or the vault. The startup log is `lancement.log` in the data folder (Linux, macOS). To build the installers yourself: `python scripts/construire_deb.py`, `construire_windows.py` (Inno Setup under wine), `construire_macos.py`; each downloaded component is checked against its fingerprint (`installation/versions.txt`). Every version published on the releases page carries the four installers, rebuilt each time, and a note in English, French, Spanish and German (`python scripts/publier_version.py`, run by the publication).

### Linux {#linux}

By hand, from the code (developers). You need Git and Python 3.12 or later.


1. Prerequisites (Debian, Ubuntu): `sudo apt install git python3 python3-venv`
2. Get the code: `git clone https://github.com/Greal-dev/goldenbrain.git ~/goldenbrain && cd ~/goldenbrain`
3. Dedicated Python: `python3 -m venv ~/.venvs/goldenbrain`
4. Dependencies: `~/.venvs/goldenbrain/bin/pip install fastapi uvicorn pyyaml` (developers, for the tests: `pip install ".[test]"`)
5. Point to that Python: `echo ~/.venvs/goldenbrain/bin/python > python.local`
6. First launch: `./lancer.sh`, then open http://127.0.0.1:8300

The first launch creates `config.toml`, which contains only your differences (everything else comes from `config.exemple.toml`).

### Windows {#windows}

By hand, from the code (developers).

1. Install Git and Python 3.12 (python.org); note the path of `python.exe`.
2. Get the code: `git clone https://github.com/Greal-dev/goldenbrain.git goldenbrain`
3. Dependencies: `python -m pip install fastapi uvicorn pyyaml` (developers, for the tests: `pip install ".[test]"`)
4. If the `python` on the PATH is not the right interpreter, write its full path on the first line of a `python.local` file at the root of the folder.
5. First launch: double-click `lancer.cmd`. The page http://127.0.0.1:8300 opens.

### Where the vault is

By default: `~/Documents/Vault`. To put it elsewhere, write it in `config.toml`:

```toml
[vault]
racine = "~/path/to/my-vault"
```

**Without touching that file**: on first launch, before any other screen, GoldenBrain opens “Configure your second brain” full screen. There you pick the folder (type it, or “Browse” to walk through your folders): an existing Markdown or Obsidian vault is used in place, without copying; a missing or empty folder becomes a new second brain, created only when you confirm. A nonexistent, non-writable or relative folder, or one already served by another instance, is refused with the reason. Changing folder rewrites only the `[vault] racine` key of `config.toml`, then GoldenBrain restarts by itself on the new vault; keeping the current folder restarts nothing. Next come the choice of AI assistant, then the proposal of roles and projects (or the demonstration); nothing is written before you confirm. “Later” leaves a “Second brain to set up” banner. To reopen it: Settings → “Installation and version” → “Reconfigure my second brain”.

An existing Obsidian vault works as it is: point `racine` at it (see “Organise your second brain”). An empty or missing folder receives a starter filing system, from the welcome screen and after your confirmation.

Port already in use: `[serveur]` then `port = 8301`. Restart after every change to `config.toml`.

### Service at startup (Linux) {#service-au-demarrage-linux}

GoldenBrain starts by itself with your session, and restarts after an update.

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

- Start even without a session being opened: `loginctl enable-linger "$USER"`.
- Log: `journalctl --user -u goldenbrain -f`. Stop: `systemctl --user stop goldenbrain`.
- `WorkingDirectory` must point to the code folder (`%h` = your personal folder).

### Connect the AI assistants {#connecter-les-harnais}

An AI assistant is the program, used from a command prompt, that makes the agent work. GoldenBrain looks for it in the PATH; you need at least one, installed **and signed in**.

| AI assistant | Install | Sign in |
|---|---|---|
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` (macOS, Linux) · `irm https://claude.ai/install.ps1 \| iex` (Windows) | `claude`, then `/login` |
| Codex | `npm install -g @openai/codex` | `codex login` |
| GitHub Copilot CLI | `npm install -g @github/copilot` | `copilot login` |
| OpenCode | `npm install -g opencode-ai` | see its documentation |
| Antigravity (`agy`) | see its documentation | from the application |

Good to know: a missing AI assistant appears as “unavailable”, with the reason, in a task’s “Engine” choice. Its path or arguments are set in `config.toml`, section `[harnais.<nom>]` (template: `config.exemple.toml`).

Good to know: Node.js is needed for the `npm` installs; the application offers to install them (Home screen) and never logs in for you.

**Warning — no confirmation**: by default GoldenBrain launches agents with the arguments that remove every permission prompt (`--dangerously-skip-permissions` for Claude Code and Antigravity, `--dangerously-bypass-approvals-and-sandbox` for Codex, `--auto` for OpenCode, `--allow-all-tools --no-ask-user` for Copilot), from your home folder unless the task names another one. An agent can therefore read, change or delete your files without asking. Try it first on a harmless instruction; these arguments can be changed in `config.toml` (`[harnais.<name>]`, template: `config.exemple.toml`); see `SECURITY.md`.

## First steps {#premiers-pas}

Ten minutes, with nothing more to configure.

0. **On the very first launch**, a “Welcome to GoldenBrain” window opens in two steps. *Your AI assistant*: the list of recognised AI assistants (Claude Code, Codex, Copilot, OpenCode, Antigravity), each “ready”, “installed, sign-in needed” or “not installed”. For a missing assistant, “How to install it” gives the official page and the command to copy into a command prompt (“Copy” button); install it, then “Check again”. GoldenBrain installs nothing itself. *First task*: “Start the demo” creates and starts a small task (the assistant introduces itself and suggests three ideas, changing nothing on the computer); the answer usually arrives within a minute or two. “Skip” or “Later” closes the window and opens the welcome screen. To see it again: Settings → “Installation and version” → “Replay the first steps”.
1. **Create a task**: “New task” (at the top). A title is enough; the description helps the agent. At the top of the form, **ready-to-use templates** (build a small website, analyse an Excel or CSV spreadsheet, write a letter, automate a repetitive task, summarise documents, learn a concept): one click fills in the title and the description, which you then complete where marked “[to be completed]”; nothing is created before “Create”. To add a template: drop an `.md` file into GoldenBrain’s `modeles/` folder (header `titre`, `resume`, `ordre`; the text below is the mission). To adapt a supplied template, copy it under another name: an update may replace the supplied files. Project: leave “Inbox (default)” if you do not know where to file it. No suitable project? The last option, “＋ New project…”, shows “Project name” and “Inside” (the existing project it is created under): “Create” creates the project, which inherits the role, then files the task in it. The form opens at the top of the screen and fits the window: if it is long, it scrolls, and “Cancel / Create” stay visible at the bottom. **From the tree** (on the left, with the mouse): hovering over a list shows a line at its foot — under a role, “＋ New project” (a name is enough; the project appears at once, clicking it offers its first task); under a project, “＋ New project” (sub-project) and “＋ New task” (form with that project already chosen); under a task that groups others, “＋ New task” (filed under it). With the keyboard, these lines appear under the list of the focused line (Tab to reach them); on a phone, use “New task”. While you type, nearby open tasks are shown: “Complete this one” adds your request to it instead of creating another; if a very similar task exists, creation is gently refused and “Create anyway” overrides it.
2. **Start it**: tick “Start right away” when creating, or write a first message at the bottom of the task (Ctrl+Enter sends).
3. **Follow the conversation**: the task opens on the right; the agent’s replies appear live. The bar at the top lists the work sessions in progress and in the queue.
4. **Reply or correct**: write at the bottom; the same conversation carries on.
5. **Approve**: when the agent declares itself “Finished”, the task awaits your “Approve” or “Send back…” (with a reason passed to the agent).
6. **Decisions**: the “Decisions” button (at the top) gathers everything that awaits your action: tasks to approve, agents’ questions, filing and link suggestions, including those of the gardener (the consistency review: it only suggests, never writes on its own; `plafond` in `[jardinage]` caps their number per pass, 7 by default).

Good to know: a new installation is in **Simple** mode (projects, tasks, conversation, status, approve). Settings → “Advanced” shows everything else.

## Organise your second brain {#organiser-votre-second-cerveau}

The vault is your **second brain**: ordinary notes (Markdown files) that GoldenBrain, you and the AI read and enrich. It is arranged on three levels: **roles → projects → tasks**.

- **Roles**: your main areas of life, few and lasting. Example: “Work”, “Family”, “Neighbourhood association”.
- **Projects**: a result to achieve within a role, with an end. Example: under “Family”, “Moving house”; under “Work”, “Firm’s website”. Several projects of the same role can be grouped if needed into an **operation** (“Back to school 2027”).
- **Tasks**: a precise action within a project, handed to the AI or to yourself. Example: “Compare three quotes from moving companies”. A task that grows becomes a project.

**The folders of the starter vault** (created by the welcome screen if the vault is empty, after your confirmation; the first-steps demonstration task, stored in `_meta/`, does not count): `Casquettes/` (the roles and their projects), `Projets/` (projects born from a task), `Inbox/` (the arrival box), `Ressources/` (what serves several projects: practical sheets, templates, contacts), `Archives/` (what is finished or dormant), and the note `Lisez-moi.md`, which summarises the method.

**How the AI uses it**:
- **Before each task**, the agent reads the project’s `contexte.md` file (goal, landmarks, instructions for the AI): a few accurate lines there are worth more than a long instruction repeated at every task.
- The project’s **notes** (`notes/`) and those you link with `[[Name of the note]]` give it the substance of the matter.
- The **graph** (“Notes” tab, “Graph” button) shows what is linked and what remains isolated.
- The **AI gardener** suggests links and filing; it writes nothing without your agreement.

**Good practices**:
1. **Capture fast, file later**: when in doubt, everything goes into `Inbox/`; one sort per week is enough.
2. **One task = one expected result** (“Write the letter to the town hall”), never a theme (“Town hall”).
3. **Keep `contexte.md` up to date**: two or three lines, reread when the project changes course.
4. **Archive rather than delete**: `Archives/` keeps the history without cluttering.

**You already have an Obsidian vault**: point `[vault] racine` at it (see “Where the vault is”), then start the welcome screen and tick “My existing Markdown vault”. It is taken over in place, as it is: no folder is added, no note is rewritten, the `.obsidian` folder is ignored, and the `[[…]]` links work in both tools.

## Features by screen {#fonctions-par-ecran}

### Import your projects {#reprise-de-vos-projets}

- **What it is for**: on first launch, taking over what already exists (projects, agent conversations, vault) instead of starting from an empty tree.
- **How to do it**: three steps, “Choose”, “Review”, “Confirm”. Tick the sources you want (a few questions, a designated folder, your Claude Code or Codex conversations, your Markdown vault), then “Suggest a structure”; rename, untick or drag the suggested items; “Confirm” writes, “Open my tree” finishes. “Later” closes without writing anything.
- **Empty vault**: the questions are ticked by default (“Your main roles (separated by commas)”, “Your current projects (separated by commas)”); the “Review” step also suggests a “Starter filing system” (folders `Casquettes/`, `Projets/`, `Inbox/`, `Ressources/`, `Archives/` and the note `Lisez-moi.md`), which can be unticked. Each project receives a `contexte.md` sheet to complete (goal, landmarks, instructions for the AI). The “?” button opens “Organise your second brain” in a new tab.
- **Good to know**: local reading only, nothing leaves the computer and no model is called. Nothing is overwritten; a task taken over continues its original conversation. Settings → “Restart the welcome” only suggests what is missing. On first launch, the welcome screen follows the first steps (see “First steps”); if you started the demo, it no longer opens by itself: “Restart the welcome” reopens it.

### Tree and lists {#arbre-et-listes}

- **What it is for**: seeing all the tasks in their place (roles, operations, projects, tasks) and their state.
- **How to do it**: left pane, “Tasks” tab; “Open” or “All”. In the centre, the cascade overview (status, activity, due date, priority); a click on a status counter filters. “For me” keeps only what awaits your action. Search (the `/` key) finds tasks and notes.
- **Merge overdue**: a finished task whose summary cites a `gb/*` version not yet merged into the main version, several hours after its last save, carries an orange badge. Main version and tolerated delay: Settings → “Merging versions”.
- **Filing**: drag a task or a project under another item; “Move up one level” (Shift+←); the `m` key moves with the keyboard; every action can be undone for 10 s.
- **Good to know**: the folder is the reference. Moving a project really moves its folder, after a plan to approve (“Apply”) and a restore point of the vault (git).

### Task {#tache}

- **What it is for**: an agent’s conversation about a precise piece of work, and its summary (what is done, result, how to try it, what remains).
- **Lighter opening**: the header fits on one line (title, status, run state, “Result”, “Approve” / “Send back” or “Stop” / “Retry” as the case may be) and the conversation thread takes the rest of the screen. The “Details” button unfolds everything else: breadcrumb and parent, Me / AI, engine, due date, economy, lines, links, reviews, sheet, body, actions. Your choice (folded by default) is remembered. An alert (incident, pause, failed check) shows as one pill, any others as “+N”; one click opens “Details”.
- **How to do it**: task header: status, AI assistant and model (the next message goes out with them), due date, priority. At the bottom, write then Ctrl+Enter. “Stop” interrupts the work session; “AI assistant’s native interface” opens the same conversation in a command prompt, with the assistant’s own interface; “GoldenBrain console” follows it from a command prompt.
- **Rename**: click the task title, it becomes a field; Enter saves, Escape cancels. Only the title changes: the identifier, the vault file, the links and the conversation stay the same, and the new title appears everywhere (tree, search, Telegram, dashboard). An agent does the same with `orch renommer <id> "<title>"`. Leaving the field (the phone keyboard's “Done”, tapping elsewhere) also saves.
- **Me / AI**: the switch in the header says who leads the task. “👤 Me”: no agent works on it (conversation greyed out, no automatic review or approval); the task carries a badge in the tree. “🤖 AI”: “Hand over” gives control back to the agent, which receives your notes.
- **Notes**: panel beside the conversation (each one folds away). Dated notes, in Markdown, added and edited by you alone; the agent reads them without writing them. AI button: “Summarise”, “Correct” or “Synthesise”, a suggestion to apply or cancel. On a phone, the two panels stack.
- **See the result**: the button opens what the assistant produced, with your computer’s usual application: a file cited in the summary or written during the last work session, a website (local address cited in the summary, or the `index.html` of the working folder) or the working folder. A single result: it opens at once; several: a list to choose from. Nothing found: a message tells you so. Available on the computer only (refused from a phone); a program or a script is never run: its folder opens instead.
- **Learn**: the “Learn” menu in the header makes the AI assistant explain (or not) what it is doing, for this task only; by default it follows the Settings. The explanations appear in blue boxes in the conversation, and the summary ends with “What you can take away” (three points).
- **Other actions**: “Link…” (prerequisite, feeds, see also), “Create from this” (neighbouring task), “Promote to project”, “Ask…” (opinion of a team expert).
- **Delete**: “Delete…”, at the bottom of a task's “Details”, or in the header of a project's view (next to “Reduce to one task”). A window warns that deletion is permanent (the note is erased from the second brain), counts the sub-tasks (for a project: tasks, sub-projects, other files in the folder) and asks what to do with them: delete them too, or move them to a project or to a task that groups others (by default, the parent). “Delete permanently” stays greyed out until “I understand this cannot be undone” is ticked. From a project, only its `contexte.md` note and its tasks are erased: every other note or attachment (contracts, sub-folders) is stored intact in `Archives/supprimes/<date>/`, and a moved sub-project keeps its whole folder. Links, parents and deliverables that pointed to the deleted task are removed from the other tasks. Refused while an agent works on a task concerned (stop it first), and for a role folder, `_meta` or the inbox folder. No recycle bin: the vault's daily git backup is the only way back. An agent cannot delete.
- **Good to know**: statuses: Not started → In progress → Waiting (a human is needed) or Finished → Approved. “Blocked” signals the technical failure of a work session. A project may require a check (`controle:` in its `contexte.md`) before a task can become “Finished”. In the vault, “Waiting” is written `statut: retour-humain`; a vault that uses another name declares it in `config.toml`: `[vault]` then `statut_retour = "<name>"`.

### Labels {#etiquettes}

- **What for**: short words set by hand on a task (`#bank`, `#client-x`) that tell the AI which tasks belong together. Distinct from vault tags (closed vocabulary, never touched): the `etiquettes:` key of the note.
- **Set**: in the task's "Details", "Labels" card: type a word, Enter to add (completion on labels already in use), click a chip to remove it. The tree shows the first two. Bulk set/remove: the "n selected" bar, "+ label" and "− label" fields.
- **Filter and search**: "Filters and grouping" → Label (combinable with status) and "By label" (one group per label with its count, a task shows under each of its labels; clicking the group opens the label's view); search finds `#word`; the graph filters them like tags.
- **Create a label and file existing tasks**: Ctrl+K → "New label…", or the "New label" button of a label's view: a name, an optional instruction. The new label's view opens with "Find tasks" already run: open tasks and routines from every role whose title or record comes close (simple synonyms included: "finances" finds bank, rent, CAF, receipt, statement…), the likeliest ticked, the reason under each line. "Refine with AI" has the fast assistant sort up to 80 tasks (one minute at most); if it fails, the local ranking stays and a message says so. "Label the n selected" files them at once; "Undo this change" removes them.
- **Steer the AI**: the agent receives its task's labels, their instruction and the other tasks sharing one; the match before creation weighs a shared label; a proposed link between two labelled tasks with no shared label is refused. An agent never creates a label: it proposes it (Decisions), you accept.
- **Instructions, rename, merge**: Settings → Agents and resources → Labels. The instruction (600 characters) is attached to the context of any agent working on a labelled task. Renaming to an existing word merges; "Undo" restores the notes.
- **Rules**: lowercase, no accent or space (`-`), 30 characters, 12 per task. Terminal: `orch etiqueter <id> +word -word`, `orch etiquettes`.

### Discussion mode {#mode-discussion}

- **What it is for**: as soon as a task is open, the conversation takes most of the screen (over 70% of a 1366×768 screen). Nothing is removed: everything stays one gesture away.
- **How to do it**: the top bar fits on one row (logo, counters, search, “In progress”, “New task”, “Menu”). “Menu” (hover or click, Alt+M) drops down Team, Consistency review, Routine, Chains, Settings, Manager and the guide. The task tree folds into a rail on the left: hover for a preview, click to pin it (Alt+T). The notes fold into a tab on the right showing their count: click to open them (Alt+N). “Show everything” (in “Menu”, Alt+D) restores the full layout; “Discussion mode” goes back. Each choice is remembered per computer; a bubble explains it on first use. On a phone nothing changes.
- **Good to know**: on opening, the latest exchanges appear first, the start of the history afterwards. The reminder “Your second brain is not configured yet” no longer appears once the vault already holds notes.

### Decisions {#decisions}

- **What it is for**: a single place to settle everything that awaits a human.
- **How to do it**: “Decisions” button. For each item: “Approve”, “Send back…”, reply to the agent, postpone (date), “Accept” or “Decline” a suggestion. The AI gardener (consistency review) and the agents also suggest **renaming** a task whose title does not say what it is really about (“Rename “club sales” to “club sales API/MCP””, with its reason): applied automatically (routine step), it can be undone from “Applied automatically”. Several ticked tasks can be approved at once. Agents' routine steps (link, attach, move, rename, due date, task created under theirs) no longer wait for you: they are applied automatically, noted in the task's “Traces” and listed for seven days under “Applied automatically”, at the bottom of the page, each with “Undo”. What remains to decide (close, make a project or an operation, change a scope) is grouped by sending task into one folded entry “Proposals from …”: “Accept all” or “Decline all”, or, once unfolded, one line per proposal, reason on hover or unfold.
- **Good to know**: the automatic closures of the last 7 days appear there under “Closed automatically”, each with “Reopen”. The “avoidable?” badge flags a question or an approval that the agent could have settled alone (information only, nothing is changed); Settings → “Avoidable?” badge switches it off or sets its threshold.

### Who has the ball: four states {#la-main}

- **What it is for**: no task waits silently. Every open task carries one computed badge, with a sentence saying why: "The AI is working", "Queued" (the reason is stated: memory, simultaneous agents, reserved workstation, quota or assistant unavailable, routine, named dependency, pause; and when it resumes), "Human action needed" (what is expected of you, in one sentence, with the gesture on the spot) or "Done".
- **How**: on a task awaiting human action or never started, the "Hand to the AI" (or "Send back to the AI") button opens an optional instruction, then sends the task to the queue. Same gesture in lists, in Today and, for several tasks at once, in the bulk-edit bar ("Hand to the AI", preview first).
- **Good to know**: The top-bar counter is split into three dropdown chips: "To validate", "Questions" and "Yours to do" (oldest first). In "To validate", tick several tasks then "Validate the selection": one undoable gesture; hovering a row shows its result and how to try it. A task you carry out yourself (call, lawyer, bank, signature) reads "yours to do": "Hand to the AI" stays available on its page but is never suggested in lists. Tasks the AI never started can be handed over in one click but do not count; a permanent task or a group with no work of its own reads "Done for now" (a group says "3 for you, 2 for the AI"). After a restart, the first screen (engines, updates, tree) is prepared before requests are accepted. Each chip carries its label and count ("To validate 86"); nothing overlaps or is clipped; in a narrow window the bar folds itself, in order: secondary chips (Today, Decisions, Proposals, Incidents, folder to align, Info) down to icon and number (hovering gives the label), the "Intelligent" marker hidden, those chips moved into "Menu", the search reduced to a magnifier, then "Mine" as icons; "New task" and "Menu" stay whole. An agent must conclude every turn (done, or one precise request): otherwise GoldenBrain sends it back "conclude" at most twice, then the task returns to you with "the agent did not conclude". A delivery awaiting merge reads "integration under way", not a wait on you. Only you hand a task to the AI: an agent cannot. Vault statuses remain the underlying data; nothing is changed on its own. On a phone, tapping the badge in the task header does the same as the button.

### Today {#aujourd-hui}

- **What it is for**: knowing what to do now.
- **How to do it**: “Today” button (with the number of overdue tasks). Groups: overdue, due today, due within seven days, for me; each sorted by priority.
- **Good to know**: the due date (`echeance: AAAA-MM-JJ`) and the priority (`priorite: haute | moyenne | basse`) are set in the task header or when it is created.

### In progress {#en-cours}

- **What it is for**: seeing at a glance what your AI assistants are doing right now, and what is waiting.
- **How to do it**: click “In progress” (followed by the number), in the top bar (address `#en-cours`). For each assistant at work: the task and its project, the assistant and its model, since when, what it is doing (“runs the tests”, “writes build.py”, “changed 3 files”), the progress of its list of steps when it keeps one, and the helpers it started with their state and duration. Actions: “Open”, “Pause” then “Resume”, “Stop” (confirmation requested). Below: the waiting tasks and their reason (memory, usage allowance, prerequisite, queue position), the upcoming routines, the open incidents.
- **Good to know**: the screen updates by itself when an assistant progresses; nothing runs while it is closed. The helpers started are tracked for Claude Code and OpenCode; progress, for Claude Code, OpenCode and Codex. A manual pause freezes the assistant without losing anything; it resumes only on “Resume” (memory regulation does not touch it).

### Mobile companion {#compagnon}
- **Work in progress**: tap a task’s star ★ (tree or “In progress” on Home) to pin it on this phone; the Home screen’s “Work in progress” button (`#travail`) lists only those tasks, and each opens its chat: the conversation with the task’s agent and a message box, sent just as from the full screen. Pinning is a phone setting (nothing is written on the computer); chat needs the computer online. Status and structure only change through the usual actions.

- **What it is for**: check from your phone, at a glance, what awaits your decision, what is working, and the project tree (read-only, except one action: approve or send back a task finished by its agent, online and after confirmation).
- **How to**: access goes through the private Tailscale network and a paired phone (Settings → Devices; step by step: `docs/TELEPHONE.md`). On the phone, the « Home » button of the bottom bar (address `#compagnon`): « To decide » (each decision's question), « In progress » (assistants at work), then « Projects and tasks » (tap a project to open it, « ‹ » to go up). Tapping a decision or a task opens it in the usual screen. Installed on the home screen, the app opens straight on this Home; a decision to approve is a single card, with its “Approve” and “Send back” buttons in the same frame. If pairing fails for lack of network, the page's “Try again” button replays it without rescanning the code. Optional: `resume = true` in `[distant]` adds a 140-character summary of a task's result to the phone card; this text leaves the computer, is never kept offline, and is off by default. On a small screen the Decisions page stacks: full-width title, larger buttons. The “update available” strip does not appear on the phone (updating is done from the computer).
- **Good to know**: the screen refreshes by itself while open, and tells whether it is connected or showing data from a given time. Offline use is optional and off by default: set `hors_ligne = true` under `[distant]` in `config.toml`, then tick « Keep an offline preview on this device »; only titles, statuses and decisions are kept, for 7 days, never the content of notes or conversations. The preview is erased when the device is revoked or with « Erase this device's data ». Offline, actions are disabled: they need the computer. When offline the screen says so (“Offline · data from …”); a failed action states that nothing changed.

### Notes {#notes}

- **What it is for**: browsing and editing the whole vault without leaving GoldenBrain.
- **How to do it**: left pane, “Notes” tab (Advanced mode). “New note”; “Edit” (the `e` key, Ctrl+S saves); “Rename / move…” rewrites the links.
- **Good to know**: if the note has changed elsewhere (Obsidian, an agent), saving is refused and both versions are offered to you. Dataview blocks are not run.
- **Graph**: “Graph” button of the “Notes” tab (global graph: notes, tasks, folders and their links, filters by role, project, type, tag, period); “Graph” button of a task or “Local graph” of a note (adjustable depth). A click on an item opens the note or the task.

### Databases {#bases}

- **What it is for**: view a folder of notes as a database, Notion-style: one note per row, the properties of its header (frontmatter) as columns — amounts, dates, checkboxes, lists, links.
- **How to**: "Notes" tab, hover a folder and click ▦ "View as table" (or press `t` on the folder). Click a header to sort (twice: reverse order); filter under each header (text contained, number minimum and maximum, dates between two bounds, checkbox yes or no, list value); "Group by" a column shows a subtotal per group; the menu at the foot of a column chooses the calculation (sum, average, min, max, count of filled values, of distinct values, of checked boxes); "Columns" hides or shows again. Clicking a row opens the note, clicking a `[[…]]` link opens the target note. Ctrl+K offers "Database: <folder>" for recently opened databases; the address `#base=<folder>` can be shared.
- **Good to know**: read-only — nothing is changed in your notes. Only the notes of the folder itself are read (not its subfolders), at most 5,000. A column's type is inferred from its values; a column with mixed values reads as text. View settings are remembered per folder, in this browser.

### File reader {#lecteur-de-fichiers}

- **What it is for**: reading a file without leaving GoldenBrain, from any link (thread, card, lines, traces, deliverables, notes).
- **How**: click the link. Markdown, text, logs, CSV tables, JSON/YAML/XML, code, HTML, images and PDF open in a panel (Esc closes, “Full screen”, “Copy path”, “View source” for Markdown). Other formats (Word, Excel, archives, media…) open in their own application, with a confirmation. The `#f=<path>` address can be shared.
- **Good to know**: HTML is shown in an isolated frame, with no script and no access to GoldenBrain, and no external resource until you tick “Allow external resources”. Only the vault, task work folders, declared deliverables and folders added in Settings › Features › File reader can be read. From a remote device: vault and deliverables only, and never opening an application.

### Routines {#routines}

- **What it is for**: an instruction run by an agent at a fixed time (daily review, weekly report).
- **How to do it**: “Routine” button (clock, at the top). Title, instruction, schedule (“chaque jour 08:00”, “en semaine 18:00”, “lundi,jeudi 09:30”, “toutes les 2 h de 8 h à 20 h”, or a cron expression; the wording is expected in French), project, conversation (the same or a new one at each run), catch-up of a missed due time. In the routine: “Pause”, “Run now”, history of runs. An existing task becomes a routine in place with “Turn into a routine” (same note, same conversation); “Remove the routine” makes it an ordinary task again.
- **Good to know**: a routine carries a clock in the tree; it never runs twice at the same time and goes through the same queue as tasks.

### Chains {#chaines}

- **What it is for**: running several work phases handed to the AI on the same folder (e.g. answering a call for tenders: analysis, value proposition, solution, writing, review), each phase starting from the result of the previous one.
- **How to do it**: “Chains” button (at the top): list of models, built-in (“Réponse à un appel d'offres”, “Article ou contenu”) and personal ones, stored in `_meta/chaines/` of the vault; “New chain” or “Edit”: title, summary, shared context, watched folder and project (optional), then the phases (title, instructions, input documents, expected deliverable, AI assistant, AI model, “Human approval after this phase” box), which can be added, deleted and reordered; “Remove” (personal models, with confirmation). Manual start: “Start” in the list, or ⛓ on a project: model, project, folder to process, optional title. A parent task is created, with one task per phase; its detail shows the numbered phases with their state, a link to each, the chain state and any error. “Approve and continue” resumes after a phase with human approval; “Resume” restarts the failed phase.
- **Good to know**: phases run one at a time, never in parallel. With a watched folder, each new subfolder starts the chain, without catching up on those already there. The AI may adapt the upcoming phases to the real folder (skip, add, duplicate, change instructions): every adjustment is shown in the detail, with its reason.

### Team {#equipe}

- **What it is for**: experts (specialised viewpoints) who review finished tasks.
- **How to do it**: “Team” button (Advanced mode), “New expert”: name, mandate (what they examine), focus (what they check first), trigger (always, on a filter, or on request), AI assistant and model. From a task: “Ask…”.
- **Good to know**: an expert gives an opinion; it does not approve, unless the setting `[validation] mode = "persona"` is used.

### Settings {#reglages}

- **What it is for**: adjusting the interface and the engine without editing a file.
- **How to do it**: “Settings” button. Six collapsible groups, each titled with its state in one line: Display (language, level of detail, theme, star invitation), Features shown, Agents and resources (agents at the same time, performance or economy, summary of long conversations, Learn mode, AI assistants per role), Approval and suggestions (agents’ suggestions, “avoidable?” and “merge overdue” badges), Connections (Telegram, phone and other devices, helper computers), Installation and version (update: channel and automatic mode, report a problem, replay the first steps, restart the welcome). Clicking a title opens or closes it; the open groups are remembered from one visit to the next. The “Search a setting” field opens the relevant group (e.g. “memory”, “Telegram”). Direct link to a section: `#reglages/telegram`, `#reglages/simultanes`, `#reglages/economie`, `#reglages/compactage`, `#reglages/appareils`, `#reglages/executeurs`, `#reglages/installation`, `#reglages/premiers-pas`…
- **Language**: français, English, Deutsch or español. On first launch, GoldenBrain takes the browser’s; Settings → Display → Language (or the first screen of the welcome) changes it, and the page reloads. It applies to the screens, the messages, the “?” help (guide in the chosen language) and the agents’ replies; folder names, vault statuses and commands do not change.
- **Proposals**: Settings → Approval and proposals. Two families of steps, to tick: “Applied automatically” (by default: link, attach, move, rename, due date, task created under the agent's) and “To decide” (close, project, operation, scope, task elsewhere). Unticking a step sends it back to Decisions; the “Steps to decide” setting (show, accept, ignore) only applies to the second family. The gardener and the system scan always propose without applying anything.
- **Learn mode**: Settings → Agents and resources → Learn mode. When on, the AI assistant explains in one or two simple sentences what it is doing and why at each step, then ends with “What you can take away”. Cost: a little more text in each work session, so a little more of your usage allowance is used. When off, nothing changes.
- **Agent reflexes**: Settings → Agents and resources → Agent reflexes (and the end of the first steps). GoldenBrain offers to add a few reflexes to the instructions of each AI assistant on the computer (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`…): attach each piece of work to a task (resume first, otherwise create), record in the task sheet the documents created or modified, link tasks, documents and notes, write down the result. For each assistant: its state (missing, up to date, older version, edited by hand), “See the change” (lines added or removed), then “Accept”, “Later” or “Remove”. Nothing is written without that click; the block sits between two markers and the rest of the file is never touched. After an update that changes the reflexes, the offer comes back.
- **GitHub star**: after a few hours of use, and only if GoldenBrain is public on GitHub, a one-off window offers “Give a star”, “Later” or “Don’t ask again”; Settings → Display switches it off.
- **Good to know**: the interface writes only to `config.toml`. The other keys (vault, AI assistants, agents’ instructions) are set in that file, following `config.exemple.toml`. Text being typed is no longer lost when an agent works in the background. The borders of fields and buttons reach a 3:1 contrast against the background in both themes (WCAG 1.4.11).

### One-click update {#mise-a-jour-d-un-clic}

- **What it is for**: moving to the latest version without a command prompt.
- **How to do it**: when the “An update is available” banner appears, click “Update”; the page waits for the restart then reloads. Without the interface (Windows): double-click `mettre-a-jour.cmd`.
- **Good to know**: refused while an agent is working (try again afterwards) or if GoldenBrain files have been modified by hand. The folder only moves forward, never mixing in modifications; `config.toml`, `etat`, `journal` and `equipe` are never touched. Source: the main version (`main`) of the public code folder https://github.com/Greal-dev/goldenbrain (the `origin` remote of a clone), adjustable with `[mise_a_jour] branche` and `distant`.
- **What's new**: the banner carries “What's new?”; a click unfolds the new features of the pending version, in plain language. The version log is `CHANGELOG.md` at the root of the code folder (absent from a clone of the public repository; in French); each public version also has its note on the “Releases” page of the public code folder (to subscribe: “Watch” → “Custom” → “Releases”, or the feed https://github.com/Greal-dev/goldenbrain/releases.atom).
- **Release notes**: on the “Releases” page the note is in the page's language; without a translation, the English, Spanish and German notes say “notes in French” rather than presenting French under a foreign title.
- **Stable or beta channel**: Settings → “Installation and version” → “Update” → “Channel”. “Beta” follows the `beta` version of the public code folder (trial versions, ahead of `main`); the banner then offers “switch to the beta channel” and the “Update” button changes version then restarts GoldenBrain. Going back to “Stable” works the same way. Refused if the code has been modified by hand, or from a version other than `main` or `beta`; the vault is never touched. If the `beta` version does not exist (yet) in the public code folder, GoldenBrain says so in one sentence, puts the channel back on “Stable” and touches nothing. To test and give feedback: the “Become a beta tester” page (`BETA.md`).
- **Report a problem or suggest an idea**: Settings → “Installation and version” → “Report a problem or suggest an idea”. The links open, in the browser, the public project’s GitHub form with the version (fingerprint, date, channel) and the system already filled in — nothing else: no name, no path, no vault content. GoldenBrain sends nothing; you read it over and send it yourself (GitHub account required). “Ask a question” opens Discussions.
- **Automatic update**: Settings → “Installation and version” → “Update” → “Apply an available update automatically” (off by default). No new work session starts during preparation; the sessions in progress finish, and a session that exceeds the set delay is cut (then resumed) only at a safe resumption point. Optional time window; the update also waits until you no longer touch the interface. A failure is shown in a banner, with the action to take.
- **Restart during a work session**: “Restart” refused because work sessions are in progress offers “Restart GoldenBrain as soon as the work sessions are finished” (GoldenBrain only, never the computer); the wait can be cancelled from the same banner.

### Manager {#manager}

- **What it is for**: talking with a general agent that oversees all your tasks — “What is waiting for me?”, “Where is X at?”, handing over a subject (it directs it to the right task or project, or creates one), updating, following up, bringing two duplicates together.
- **How to do it**: “Manager” button in the top bar; the panel opens on the right, on every screen, and stays open from one reload to the next. Type, then Enter (Shift+Enter: new line). “×” closes it; on a phone it fills the screen and “← Back” closes it.
- **Good to know**: it is the Telegram assistant, in the same conversation: what is written on one side can be read on the other (marked “via Telegram”), and `/nouveau` opens a fresh conversation for both. A change of status, due date or priority waits for your “Confirm” (in the panel or on Telegram, only once); a reorganisation goes through Decisions. The panel works without Telegram and loads nothing while it is closed. The thread keeps the last 200 messages and reloads by itself after a disconnection; it only scrolls to the newest message if you were already reading the bottom.

### Telegram {#telegram}

- **What it is for**: sending an idea, a photo or a voice note from the phone; it becomes a filed task.
- **How to do it**: Settings → Connections → Telegram; an assistant guides you step by step. Create a bot with @BotFather (“I have my bot and its access key”); enter its access key (“Enter the access key in a secure command prompt”, or in the browser as a fallback); confirm the bot’s name (“Yes, that is my bot”); write to the bot in Telegram, then “Recognise me” and tick your chat; “Send the test message”, then “Yes, finish and switch Telegram on”.
- **Good to know**: the access key is stored in the computer’s keychain and never shown again. Only one program can listen to a bot: stop any other reader first. Replying to the message “Task created: …” writes to that task. An order that resembles an open task prompts an update suggestion rather than a new task. “Reply” to an assistant message passes it the quoted text (a quotation, never an order) and the task it was talking about.

### Email {#email}

- **What it is for**: read your Gmail mailbox in GoldenBrain, reply, and turn an email into a task with an instruction (pay, investigate, save, study, reply, or your own).
- **How to**: first Settings → Connections → Email: your Gmail address, “Save”, then “Enter the app password” (a terminal opens; paste the sixteen-letter password created on Google's “App passwords” page, link in the section; two-step verification is required), then “Test the connection”. Then Menu → “Email” (or Ctrl+K “Email”, address `#mail`): folders on the left (Inbox, Unread, Starred, Sent, All mail, your labels), list in the middle (unread in bold, 📎 = attachment, “Newer” / “Older” pages), reading on the right. Search accepts Gmail syntax (`from:`, `has:attachment`, `after:`…), then Enter. On an email: “Reply”, “Reply all”, “Forward” (the message only leaves when you click “Send”), “Mark as read / unread”, “Hide” (from the Inbox: the email leaves the inbox without being deleted, “Undo” in the banner puts it back; it stays in “All Mail”), “Create a task” (choose the instruction, then the “New task” dialog opens, title = subject), “Link to a task” (choose the task and the instruction; “Start the agent right away” is ticked by default). The left pane has a third tab, “Mail”, next to “Tasks” and “Notes”: the Inbox as a list (unread in bold); a click opens the email in the Email page, and hovering a row offers “Hide”, “+ Task” and “Link” in one click. Attachments download in one click.
- **Good to know**: the attached email is filed as a note in the project folder (`mails/`), attachments next to it, and appears in the task's deliverables and “Entrées” section; attached twice, it is not duplicated. For the assistant, an email is data, never an order: only your instruction counts; “Pay” prepares the payment, never pays; no agent reads or sends email. HTML emails are shown without scripts or remote images (“Show images” to load them). The password stays in this PC's vault, never shown. From a remote device (phone), the Email page is not available.

### Helper computers {#executeurs-distants}

- **What it is for**: making agents work on other computers; the vault and the interface stay on the main computer.
- **How to do it**: link the computers with Tailscale; on the main computer, `config.toml`: `[executeurs]` then `ecoute = "<Tailscale address of the main computer>"`, restart; Settings → Connections → “Helper computers” → “Pair a computer” gives a short code. On the other computer: `python orch.py executeur --serveur http://<address of the main computer>:8300 --code <code>`, or Settings → “Make this computer a helper computer”.
- **Good to know**: details, faults and testing: `docs/EXECUTEURS.md`. Never expose GoldenBrain on the Internet.

## Troubleshooting {#depannage}

| Symptom | Probable cause | Action |
|---|---|---|
| The page http://127.0.0.1:8300 does not respond | GoldenBrain stopped | Run `./lancer.sh` or `lancer.cmd` again; under systemd, `systemctl --user status goldenbrain` |
| `ModuleNotFoundError: fastapi` at launch | Wrong Python | Check the first line of `python.local`, reinstall the dependencies with that Python |
| “Address already in use” | Port taken | `[serveur] port = 8301` in `config.toml` |
| The tree is empty | Vault not found | `[vault] racine` in `config.toml`, then restart |
| AI assistant “unavailable” | Program missing from the PATH or not signed in | Install, sign in (see “Connect the AI assistants”) |
| Incident “AI assistant not installed” | An AI assistant listed in `[credits]` is not installed on this computer | Nothing urgent: the work session is restarted once on the next assistant in `[credits]`, and load balancing no longer picks the missing one. Install the assistant (see “Connect the AI assistants”) or remove it from `[credits]` |
| Task “Blocked” | Technical failure of the work session | Read the cause in the conversation, then write a message; an interrupted session resumes with “Run again”. Messages received during the block (Telegram, other agents) wait in the queue and go out in order as soon as you write, change the engine or change the status (closed task: they are dropped) |
| Task “Waiting for the workstation” | A heavy test has reserved the workstation | Wait (the queue position is shown on the task and in the banner), or “Release” in the “Workstation reserved” banner |
| “An update is available” does not apply | Agent at work, or GoldenBrain file modified | Try again after the work session; `git status` in the folder |
| “Restart” banner | GoldenBrain updated, but still running the old version | Click “Restart” |
| A Claude Code agent does not see its MCP servers (browser…) | By default, no MCP server per work session (saves memory) | `mcp: heritage` in the header of the task’s note, or `[harnais.claude] mcp = "heritage"` in `config.toml` |
| “Connection lost…” | GoldenBrain restarted or stopped | Wait a few seconds; otherwise restart |

## For an AI agent {#pour-un-agent-ia}

To be read by any agent — Claude Code, Codex, OpenCode, Antigravity or other — that drives GoldenBrain or works in its repository. GoldenBrain is not called through a library: you talk to it with the `python orch.py` command (from the repository root, never through a `.cmd`) or through its local API.

**1. Start and check the server**

- Start: `./lancer.sh` (Linux, macOS) or `lancer.cmd` (Windows), at the repository root.
- Check: `curl -s http://127.0.0.1:8300/api/etat` answers with a JSON object (turns in progress, queue, decisions). A refused connection: the server is not running.
- Another address (port set in `config.toml`, test server): `ORCH_URL` variable, for example `export ORCH_URL=http://127.0.0.1:8301`; `orch.py` reads it.
- An agent launched by GoldenBrain receives `ORCH_URL`, `ORCH_TACHE` (its task) and `ORCH_SAUTS`; `orch.py` uses them to sign its messages and bound relays.

- Conclude every turn: done (`terminee`), or one precise human request in `prochain_pas` (`en_attente`), or a named wait. A "reste: …" sheet with nobody asked is an anomaly: GoldenBrain sends "conclude" back at most twice, then the task moves to "Human action needed". An agent never hands a task to the AI (403).

**2. `orch` commands**

| Command | Effect |
|---|---|
| `guide` | this guide |
| `arbre` | tree of open tasks |
| `chercher "<words>"` | related tasks |
| `lire <id>` | a task’s summary, path, place, status, execution |
| `etiqueter <id> +word -word` | set or remove labels (an agent: existing label only, no removal) |
| `etiquettes` | known labels, their use and instruction |
| `conteneurs` | containers in which a task can be filed |
| `rapprochement ["<title>"]` | tasks close to a title; without a title, creations avoided |
| `creer "<title>" --description "<at least one sentence>"` | create a task (`--conteneur`, `--parent`, `--lancer`, `--mission`); refused if a very similar open task exists: complete it (`dire`) or force (`--nouvelle`) |
| `dire <id> "<message>"` | write to the task: its agent receives it on the next turn (starts it if it is free) |
| `renommer <id> "<title>"` | change a task’s title (identifier and file unchanged) |
| `relancer <id>` | restart a failed or interrupted task; a session cut by the machine's memory, a restart or a transient service error resumes by itself (at most three times, “interrupted (automatic resume in the queue)”), then the task is handed back to you; a stop you asked for never resumes by itself. Commit a checkpoint on your branch at every milestone: the resume finds the working tree and the branch |
| `arreter <id>` | stop the turn in progress |
| `deleguer "<title>" "<brief>"` | hand a piece of work to a child task launched by GoldenBrain |
| `proposer deplacer\|rattacher\|projet\|operation\|ticket\|tache\|lier\|perimetre\|echeance\|fermer\|renommer …` | suggest a structure change (`--motif`, required for `renommer`) ; `rattacher <id> <parent|racine> [--aussi <id>…]` files a batch of tasks under a parent task (or detaches them to their project) in ONE proposal, refused on a cycle, a running task, another project, the ceiling of 10 or mixed kinds of work; the human accepts with a click. In simple mode, suggestions are ignored (Settings > Suggestions); a gesture whose effect is already in place is not filed, and if it becomes so before acceptance it is concluded as “already done” without error Routine steps (Settings > Proposals) are applied automatically and can be undone from Decisions; a `tache` proposal from an agent becomes a line of its task. |
| `solliciter <persona> "<question>"` | opinion of a team persona |
| `telegram "<text>"` | message to the user on Telegram (`--validation`, `--choix`); requires the bot to be configured |
| `poste reserver "<reason>"` / `poste liberer` | reserve the workstation during a heavy test; if it is taken, wait for your turn (`--attente <min>`, default 30) ; with no live gate for 20 min the reservation lapses on its own; never wait for a gate with `pgrep -f` on a pattern from your own instructions: foreground or PID |
| `chaine plan\|sauter\|ajouter\|dedoubler\|consigne …` | adapt the task's chain to the real folder: `plan` shows it; skip, add, duplicate a phase or change its instructions (upcoming phases only), always with `--motif`: the adjustment is logged and shown to the user |
| `feu-vert demander\|accorder\|refuser\|verifier <40-char sha> [text] [--a <controller task>] …` | green light tied to a version (full 40-character hash); needs `ORCH_TACHE` |
| `agents-cc [--relever]` | group this machine's Claude Code agents and attach them to a task |
| `reevaluer` | replay the automatic validation on tasks |
| `console <id> [--url]` | follow a task and write to it from the terminal |
| `rattacher <envoi> <id>` | attach a Telegram message to an existing task (not to be confused with `proposer rattacher`, which files tasks under a parent) |
| `m365 connecter\|demander\|contexte` | Microsoft 365 Copilot company knowledge (when enabled) |
| `telegram-jeton [--pause]` | enter the Telegram bot token without displaying it (machine vault) |
| `jeton-executeur <nom> [--revoquer]` | create or revoke the token of a helper computer |
| `executeur [installer]` | make this PC an executor of a lead GoldenBrain |
| `fiche` | card and proposed status of a grouped run |
| `natif <fichier>` | native-interface relay (started by GoldenBrain, not by hand) |
| `poste etat` | see who holds the workstation |

`python orch.py <command> -h` gives the options of each.

**3. REST API** (http://127.0.0.1:8300, JSON). Every write carries the `X-Orchestrateur: 1` header; without it, the server answers 403 (guard against a third-party web page).

| Route | Effect |
|---|---|
| `GET /api/etat` | workstation state: turns in progress, queue, decisions, suggestions |
| `GET /api/arbre` | task tree |
| `GET /api/recherche?q=<words>` | search |
| `GET /api/taches/{id}` | one task (status, summary, notes, execution) |
| `POST /api/taches` | create: `titre`, `description`, and optionally `conteneur`, `parent`, `lancer`, `mission`, `harnais`, `modele`, `echeance`, `priorite`, `forcer` (override a very close task), `groupe` |
| `POST /api/taches/{id}/messages` | write to the task: `texte` (and `de`: the id of the writing task) |
| `POST /api/taches/{id}/statut` | set a status: `statut` — human action, see the rules |
| `POST /api/taches/{id}/notes` | add a note from the human: `texte` |
| `POST /api/taches/{id}/executant` | `executant`: `humain` (Me) or `ia` |
| `POST /api/taches/{id}/relancer` | restart |
| `GET /api/propositions` · `POST /api/propositions` | list · suggest: `type`, `tache`, `valeur`, `motif` |
| `POST /api/propositions/{n}/accepter` · `…/refuser` | decide — human action |
| `POST /api/propositions/{n}/annuler` | undo an automatically applied step — human action |
| `GET /api/guide[?langue=fr\|en\|de\|es]` | this guide, as plain text (`orch guide` only serves French) |
| `GET /api/evenements` | event stream (SSE) |

**4. Rules**

- **Match before creating**: `chercher` or `rapprochement "<title>"` first; a close task is completed (`dire`) rather than duplicated.
- **Integration**: in a project that declares `integration:`, `creer` and `deleguer` link the new task to the integration task (`alimente`) automatically; elsewhere, a task that delivers a branch sets this link directly (`proposer lier <id> alimente <integration>`): an `alimente` link to a permanent task is a routine step, applied at once and noted in the task's “Traces”, never left waiting in Decisions; other links follow the proposals policy. Since 24/11, every proposed link is a routine step by default (Settings > Proposals).
- **Never change a status without human agreement**: an agent does not set `fait`, does not accept a suggestion, does not approve a task; it hands in its summary and the human approves. The `statut`, `valider` and `accepter` routes are interface actions.
- **“Me” tasks** (`executant: humain`): the human leads it; GoldenBrain refuses any agent turn and any agent write on it, except lines and links (an agent may read it and suggest); “Hand over” is the human action that gives it back to the AI.
- The vault is the only database; never reformat a note’s frontmatter.
- Never move a folder yourself: suggest it (`orch proposer`), the human accepts.
- No sending, publishing, payment or deletion without the user’s written agreement.
- An agent launched by GoldenBrain ends each reply with the `<fiche>` block described in the instruction it received.

**5. End-to-end examples**

Find or create a task, then hand it over:

```bash
python orch.py rapprochement "Write the release note"
python orch.py creer "Write the release note" \
  --description "Summarise the week's changes; proof: the note exists in the vault."
python orch.py lire 2026-11-19-write-the-release-note
python orch.py dire 2026-11-19-write-the-release-note "Start with the week's git log."
```

The same through the API:

```bash
curl -s http://127.0.0.1:8300/api/etat
curl -s -X POST http://127.0.0.1:8300/api/taches \
  -H 'X-Orchestrateur: 1' -H 'Content-Type: application/json' \
  -d '{"titre": "Write the release note", "description": "Summarise the week'"'"'s changes; proof: the note exists in the vault."}'
curl -s "http://127.0.0.1:8300/api/recherche?q=release%20note"
curl -s -X POST http://127.0.0.1:8300/api/taches/2026-11-19-write-the-release-note/notes \
  -H 'X-Orchestrateur: 1' -H 'Content-Type: application/json' -d '{"texte": "Keep the tone restrained."}'
```

Suggest a filing rather than doing it:

```bash
python orch.py proposer deplacer 2026-11-19-write-the-release-note Projets/C1-Site \
  --motif "the release note belongs to the website"
```

A task’s identifier is returned by `creer` (and by `arbre`, `chercher`): today’s date and the title in lowercase.

**Next**: `docs/ARCHITECTURE.md` (modules, `INV-*` invariants, contracts), `docs/CODE_MAP.md` (file map), `CLAUDE.md` (repository rules).
