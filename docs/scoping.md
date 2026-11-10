# Scoping of dev-kit

## Level 1 — Goal

A public GitHub repository, made for the user's projects and shared as a showcase of their methods, that centralises what Claude Code and Codex load (shared rules and portable workflows, plus tool-specific hooks, plugins and configuration), with templates and tooling scripts, for the user's projects, private ones and public ones (stellar, meteo). Codex is supported at the same level as Claude Code for shared rules and workflows; each tool keeps its own integration where their mechanisms differ.

Success criteria:

- no skill or shared workflow is copied into a project: each has one source in dev-kit, available to both tools from the dev-kit clone;
- a fix to a shared skill reaches every project with no copy;
- a new project gets its instructions for both tools, its plugins and its `.gitattributes` in less than 15 minutes with `project-init`, which completes existing instructions without overwriting them.

Minimal version: the marketplace, `clarify`, `project-init`, `tracking-linear`, `docs-wiki-github`, then removal of the skills duplicated in the largest project. Phase 2: global development configuration (IDE, terminals, tools run by hand), started with the terminals of the Mac and Windows.

Out of scope: libraries (code run by the applications); our own MCP servers; the Achille project (inspiration only); reproducing Claude-only hooks or plugins in Codex when Codex has no equivalent; Codex session transcripts in the work journal; Claude's Humanizer plugin in Codex.

Budget: none, assumed. Time spent goes into the work journal ([dev-journal.md](dev-journal.md)).

| Decision | Reason |
|---|---|
| Repository and folder `dev-kit`, marketplace `jyhess` | the name must survive phase 2; renaming would break every project's `settings.json` |
| Public repository, MIT licence; private data (secrets, local paths, private projects, time and activity, private life) stays out of it: machine-local values in `~/.dev-kit/` or git-ignored files, refused at pre-push by `private_words.py` on public repositories | sharing and showcase; anyone may reuse it with attribution |
| MCP servers only as configuration of third-party servers inside plugins, pinned versions, secrets in environment variables | context, security and startup costs stay under control; own servers would be code to maintain |
| Clarifying questions are asked in rounds (whole frontier at once) | The user's preference |
| French with the user; English for documentation, skills, code, comments and commits; wikis in French unless stated otherwise; a project's local skills follow its documentation's language | The user's defaults |
| `.gitattributes`: `* text=auto`, without `eol=lf` | LF in the repository, native CRLF working copies on Windows for every editor |
| File formats: every published version stays readable; unpublished development versions may be dropped without a converter; every format carries a header (program, versions, creation date…) | users' files never break; dev versions are not worth the code |
| Errors: lower layers return typed errors, never display text; the interface translates each kind, exhaustively where the language allows | context survives translation; a missing translation is a compile error, not a silent fallback |
| Per project, `project-init` asks for a GitHub wiki or `docs/`, and for Linear or GitHub issues | large projects need a wiki and a tracker; small ones do with `docs/` and issues |

## Level 2 — Business

- **Machines**: Windows and macOS.
- **Questions of `project-init`**: name, purpose and audience; stack and commands; wiki, `docs/` or none; Linear, GitHub issues or none; exceptions to the default languages; private GitHub repository with `gh`; pre-push hook and CI; auto-merge; checked architecture; tools kept; glossary path.
- **Journal**: the watched repositories are `repos.json` in the journal repository, paths relative to the dev folder, shared by both machines; commits pulled from the other machine and the journal's sync commits are not local activity.

### Acceptance criteria

- **C1 — New project.** Given an empty folder, when the user runs `/project-init`, then it asks one round of questions, lists the files it will create and writes nothing before their agreement; it then creates `AGENTS.md`, a `CLAUDE.md` importer, `.claude/settings.json` with the chosen plugins, `.gitattributes` (`* text=auto`), `.gitignore` with Vim's backup files (`*~`, `*.un~`, `*.swp`, `*.swo`), and if asked the CI, the pre-push hook and the private GitHub repository; it registers the project in the journal's `repos.json`, committed and pushed.
- **C2 — Duration.** Initialising a small existing project takes less than 15 minutes from the command to the first commit. `[manuel]`
- **C3 — Existing project.** Given a project with its own instructions, when the user runs `/project-init`, then it asks only what the files do not answer, shows each change before writing it and removes no section without saying so.
- **C4 — Shared fix.** Given a fix pushed from one machine, when a session starts in any project on either machine, then the new version is active with no command; checked with a test skill whose text changes between two commits.
- **C5 — Offline.** Given no network, when a session starts, then it uses the last version received, shows a one-line warning and is not blocked.
- **C6 — Revert.** No project pins a version: a breaking fix is fixed forward or reverted in dev-kit, and reaches every project as in C4.
- **C7 — No copy.** No local skill of a project has the name of a shared skill; a project completes a shared skill with a short local skill or an instruction section; a dev-kit check script verifies it.
- **C8 — Duplication removed.** No project or project wiki contains a copy of `cadrage` or `linear`; at most short local skills in French remain.
- **C9 — Generic rule.** When a local rule proves generic, Claude proposes to move it into dev-kit and does not do it on its own. `[manuel]`
- **C10 — `clarify`.** Each round is the whole frontier asked with interactive questions (recommended option first, at most four per call); inconsistencies come first and block the level's gate. `[manuel]`
- **C11 — Tracking.** `tracking-linear` applies the generic Linear rules; tickets carry points but no time, velocity is measured in points, and reviews take the project's hours for the period from the journal; `tracking-github-issues` follows the same flow (issue, branch, PR with `Fixes #n`, `[manuel]` criteria recalled) without points or time. `[manuel]`
- **C12 — Two systems.** Every dev-kit script or hook runs on Windows and macOS with Python 3; the pre-push hook checks them on each machine, CI on Linux.
- **C13 — Journal labels.** Work in dev-kit, the journal included, is logged under `--project dev-kit`, category `organisation` or `cadrage`. `[manuel]`
- **C14 — Shared workflows.** Every portable workflow is discoverable in Codex and Claude Code from the dev-kit clone; workflows with a platform-specific dependency are identified as such.
- **C15 — Instructions for both tools.** C1 and C3 apply to `AGENTS.md` and `CLAUDE.md` alike.
- **C16 — Codex journal.** Codex can use the journal workflow for commit activity; session collection stays Claude-specific.
- **C17 — Writing.** The writing workflow works in Codex with its own reformulation step, without Humanizer.
- **C18 — Platform-specific behaviour.** Claude-only hooks and plugin behaviour stay Claude-specific unless a Codex equivalent is found and scoped separately.

## Level 3 — Implementation

| Decision | Reason |
|---|---|
| Each machine registers its dev-kit clone as a marketplace in its user configuration; projects only declare `enabledPlugins` | the dev folder differs between machines (`dvp` on the Mac, `dev` on Windows) |
| The clone is loaded in place (no cache, no `version`); a session-start hook runs `git pull --ff-only` and warns in one line when offline | edits are testable without pushing; a pull takes effect at the next session or after `/reload-plugins` |
| Plugins `core` (clarify, project-init and pilot skills; update, vocabulary and context-size hooks), `dev-journal` and `writing` in the user configuration; `tracking-linear`, `tracking-github-issues`, `docs-wiki-github`, `docs-folder` enabled per project | one plugin per choice made by `project-init` |
| Generic Linear rules and templates live in `tracking-linear`; a project's wiki keeps only its specifics and links to the plugin | no duplication |
| Project specifics are French instruction sections (Documentation, Tracking) read by the plugins | a few lines of configuration need no local skill |
| dev-kit is the public repository `Jyhess/dev-kit`; its tasks are its GitHub issues | small project rule; the other machine needs a remote |
| Verification: `claude plugin validate` and the Python tests in a pre-push hook, and in CI on Linux only | macOS and Windows runners cost 10x and 2x Linux on private repositories; the pre-push hook covers each machine |
| `python3` is mandatory on every machine; hooks call `python3` | one hook command for both machines |
| `scripts/install.py`, idempotent, run once per machine, installs the marketplace, `core`, `dev-journal`, `writing` and the `humanizer` plugin | `project-init` needs `core` first |
| `project-init` asks the questions; `init_project.py` fills `templates/` and writes only with `--apply` | deterministic output, so C1 and C3 are tested |
| `AGENTS.md` is the shared instruction file; `CLAUDE.md` imports it with `@AGENTS.md`, then adds Claude-only instructions; the `core` hook injects the glossary index | Codex reads `AGENTS.md` natively; an `@` import of a glossary outside the repository is silently skipped |
| `install.py` links shared skill folders into `$CODEX_HOME/skills` (`~/.codex/skills`), with directory junctions on Windows when symlinks are unavailable | Codex reads user skills there; links reflect edits in the clone |
| `project-init` needs no project-specific Codex settings | skills are user-level |
| Existing `CLAUDE.md` sections are kept; `project-init` reports those that may duplicate `AGENTS.md` | never remove project instructions silently |
| The vocabulary hook reads the glossary path from `AGENTS.md` or a legacy `CLAUDE.md`; Codex reads the glossary at the start of domain tasks | keeps Claude's behaviour and gives the path to Codex |
| Generic `AGENTS.md` rules (Writing, Context, Provisional values, Known limitations, Git) live only in `plugins/core/rules/shared-rules.md`; a project opts in with a `## Shared rules` section, Claude gets them from a `core` SessionStart hook, Codex reads them through `~/.dev-kit/rules` linked by `install.py`; a project section wins over them; `project-init` removes verbatim copies | a fix reaches every project at its next session, no copy |

### Work journal (`dev-journal` plugin)

| Decision | Reason |
|---|---|
| Its hook is installed by `install.py` | one install path for both machines |
| The hourly task is the `/dev-journal:hourly` skill; each machine's scheduled task is one sentence starting with `[dev-journal]` | one text, no per-machine paths |
| The data repository is a private one of the user's own, given once by `install.py --journal-url`, apart from dev-kit | entries stay private; dev-kit is public |
| The dev folder is the parent of the dev-journal clone, next to dev-kit; `~/.dev-journal/config.json` keeps only `machine` and `start` | `dvp` and `dev` with no setting |
| Local commits are read from the reflogs; sync commits `Journal <machine> …` are left out | pulled commits never count as local actions |
| An entry's project is the GitHub repository name (`origin`) or the folder name; a wiki repository is its own project; `--project` is required | reviews sum a project's hours over a period |
