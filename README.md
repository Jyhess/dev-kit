# dev-kit

How Jyhess works with AI coding agents: the shared rules, workflows, Claude Code plugins and scripts they reuse across their projects with Claude Code and Codex. It is a Claude Code plugin marketplace named `jyhess`, loaded in place from a local clone.

It is opinionated and made for their own setup: conversations in French and code and docs in English, two machines (Windows and macOS), GitHub, a private work-journal repository. It is published to share the methods; take what fits, fork it, or read it for ideas. Scope and decisions: [docs/scoping.md](docs/scoping.md).

What it does, in short:

- **Clarify before building**: `/core:clarify` questions a subject in rounds (goal, business, implementation) and hunts inconsistencies before any design.
- **Same conventions everywhere**: `/core:project-init` equips a project with the shared `AGENTS.md`, plugins, Git hooks, CI, PR checks, architecture checks and domain glossary.
- **Guard rails checked by tools, not by memory**: pre-push verification, PR description and structure checks, auto-merge of low-risk PRs, architecture rules as tests ([docs/architecture-rules.md](docs/architecture-rules.md)).
- **Small sessions**: hooks that warn when a session's context grows, and measurement of where tokens go ([docs/token-usage.md](docs/token-usage.md)).

## Plugins

| Plugin | Enabled | Contents |
|---|---|---|
| `core` | in the user configuration, everywhere | `/core:clarify` (question a subject in rounds, three levels); `/core:project-init` (set up or equip a project: `AGENTS.md`, `CLAUDE.md`, plugins, `.gitattributes`, `.gitignore`, pre-push hook and CI, GitHub repository, work journal); `/core:pilot` (steer a theme, one sub-session per ticket); `/core:ask` (questions with choices in one form); hooks that fast-forward this clone at session start, inject the shared rules and a project's vocabulary rules, and warn when a session's context grows |
| `dev-journal` | in the user configuration, everywhere | the hourly work journal ([docs/dev-journal.md](docs/dev-journal.md)): a hook that asks about working hours no machine has logged; `/dev-journal:hourly`, run by an hourly scheduled task, writes the entries from local sessions and commits and pushes them to the user's private journal repository |
| `tracking-linear` | per project (Linear) | `/tracking-linear:linear`: implement a ticket up to the PR, split a step into tickets, reviews and decisions with the points done and the work journal's hours for the period (`scripts/journal_time.py`) |
| `tracking-github-issues` | per project (GitHub issues) | `/tracking-github-issues:github-issues`: the same flow on GitHub issues, without points or time |
| `docs-wiki-github` | per project (GitHub wiki) | `/docs-wiki-github:wiki-github`: structure, file names, links and index page of a wiki kept as a GitHub repository; link checker `scripts/check_md_links.py` |
| `docs-folder` | per project (`docs/`) | `/docs-folder:docs`: pages of `docs/` in English, updated from the project's update table (`docs/update-table.md`) |
| `writing` | in the user configuration, everywhere | `/writing:com`: professional communications (LinkedIn, announcements, professional mails) drafted in the user's voice from their profile `voice.md` in the private dev-journal clone (layout: `skills/com/voice.example.md`), then refined with Humanizer in Claude Code or a voice pass in Codex; also tells whether a text was reworked by AI |

The `SKILL.md` workflows are also exposed to Codex from the same source. `scripts/install.py` links them into `$CODEX_HOME/skills` (default `~/.codex/skills`) as `dev-kit-<plugin>-<skill>`, and removes its former links that no longer match a skill; on Windows it uses directory junctions when symbolic links are unavailable. Skills reach their scripts from the clone's root, recorded as `root` in `~/.dev-kit/config.json`. It also links `~/.dev-kit/rules` to `plugins/core/rules`, for the shared rules. `AGENTS.md` is the canonical shared instruction file. The root `CLAUDE.md` imports it with `@AGENTS.md`.

## Install on a machine

The work journal needs a Git repository of your own: pass its URL once with `--journal-url`, or the installer skips the journal. To try a plugin alone, add the marketplace and install the plugin by hand (`/plugin marketplace add Jyhess/dev-kit`, then `/plugin install core@jyhess`).

Requirements: `git`, `python3`, Claude Code (the CLI on `PATH`, or the desktop app). Codex is optional; when present, the installer exposes the shared skills to it.

```bash
git clone https://github.com/Jyhess/dev-kit.git
cd dev-kit
python3 scripts/install.py
```

The script is idempotent. It registers the clone as the `jyhess` marketplace and installs `core`, `dev-journal` and `writing` in the user configuration, with `humanizer` from the blader/humanizer marketplace, then points the clone's Git hooks at `.githooks`. It also links shared skills into Codex's user skill directory, clones the journal repository given by `--journal-url` next to dev-kit and writes `~/.dev-journal/config.json`; the hourly scheduled task is created by hand in the desktop app (see [docs/dev-journal.md](docs/dev-journal.md)). If the Claude CLI is neither on `PATH` nor in the desktop app's folder, set `CLAUDE_CLI` to its path.

To set up the Codex links without installing Claude Code plugins, run:

```bash
python3 scripts/install_codex.py
```

## Updates

At each session start, `core` runs `git pull --ff-only` on this clone. A pulled change takes effect at the next session, or right away with `/reload-plugins`. Offline, or when the clone has diverged, it shows a one-line warning and changes nothing. A clone left on another branch than `main` would receive no update: once that branch is merged and the clone has no local change, the hook goes back to `main`; otherwise it warns at each session start. A change made locally in the clone is active at the next session, with no push.

## Shared rules

The generic project rules (asking before acting, writing, context, provisional values, known limitations, Git) live only in [plugins/core/rules/shared-rules.md](plugins/core/rules/shared-rules.md). A project opts in with a `## Shared rules` section in its `AGENTS.md`, written by `/core:project-init`: the `core` hook injects the file at session start, `/clear` and `/compact`, and Codex reads it through `~/.dev-kit/rules`. A section of the project's `AGENTS.md` that contradicts them wins. On an existing project, `/core:project-init` removes the copies identical to a past template version and shows the others' diffs. The hook reads the clone's file: a change made on a dev-kit branch applies once merged and pulled.

## Domain vocabulary

Each project has a glossary of its domain terms (French, English for the code, displayed terms, definition, forbidden synonyms), written by `/core:project-init` and named in the "Vocabulary" section of its `AGENTS.md`. Claude Code reads `AGENTS.md` through `CLAUDE.md`; the `core` hook injects the vocabulary rules and an index of the glossary at session start, `/clear` and `/compact`, and Claude reads the glossary itself for a definition. Codex reads the shared instruction file and glossary when a workflow calls for domain vocabulary. Scoping: [docs/domain-vocabulary.md](docs/domain-vocabulary.md).

## Terminal (macOS and Windows)

`terminal/` holds the shared terminal configuration: `starship.toml`, the prompt shared by both machines (time, folder from the repository root, branch, ↓↑ or ✓, `+ ~ - ? !` counters, exit code), `zsh/dev-kit.zsh` for macOS and `powershell/dev-kit.ps1` for Windows (PowerShell 7). Both give the same Git aliases (`gr gs gl glog gp gpf grim grum`), Docker Compose aliases (`up down logs`), .NET aliases only in .NET projects (`dw db dc dt dr`) and a background `git fetch` every 5 minutes at most.

```bash
python3 scripts/install_terminal.py
```

- **macOS**: sources `dev-kit.zsh` from `~/.zshrc` once and lists the missing dependencies (oh-my-zsh, its two external plugins, starship, direnv) with the command to install each. Machine-specific lines (`PATH`, nvm, direnv hook) stay in `~/.zshrc`.
- **Windows**: installs the missing PowerShell modules for the current user (posh-dotnet, posh-git, PSKubectlCompletion, DockerCompletion, npm-completion, WslInterop), lists starship with its winget command, and dot-sources `dev-kit.ps1` from `$PROFILE` once. `dev-kit.ps1` also keeps the PSReadLine settings, the WSL commands and the loading of a folder's `.env.ps1` on entering it. It removes PowerShell's built-in `gl` and `gp` aliases, which would hide the Git functions.

## Development

```bash
python3 -m unittest discover -s tests
```

`python3 scripts/check_projects.py [project dir …]` checks that no project keeps a local copy of a shared skill (by default, the repositories watched by the work journal).

`python3 scripts/token_usage.py [--since YYYY-MM-DD] [--save]` sums the token usage of the local Claude Code transcripts per session, project, model and kind of session, and shows what each session loads at start; `--save` keeps the report in the git-ignored `history/token-usage/<date>.md` of the main clone. Findings and leads: [docs/token-usage.md](docs/token-usage.md).

The pre-push hook (`.githooks/pre-push`) runs `claude plugin validate .`, `plugins/core/scripts/private_words.py` (refuses pushed commits whose message, paths or added lines hold a word of `private-words` in the private `dev-journal` clone (shared) or the project's git-ignored `.private-words`, except words naming the project; nothing checked without it or for private repos), `plugins/core/scripts/ticket_refs.py` (ticket references; examples in `.ticket-refs-ignore`) and the tests; the pre-commit hook only prints non-blocking warnings. The `version` field is deliberately absent from the manifests: Claude Code plugins loaded in place from a local clone are not versioned, so `validate` warns about it.

## Licence

MIT, see [LICENSE](LICENSE).
