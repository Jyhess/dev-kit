---
name: project-init
description: Set up a new project, or equip an existing one, with the user's shared conventions: instructions, plugins, Git hooks and CI, glossary, GitHub repository, work journal. Use when the user starts a project, says "nouveau projet", "initialise", "mets en place le projet", or asks to bring an existing project (meteo, stellar…) to the shared conventions.
---

# Set up or equip a project

The project is the current working directory unless they name another folder.

The script that writes the files is `<dev-kit>/plugins/core/scripts/init_project.py`. Run it with `python3`. `<dev-kit>` is the dev-kit clone, the `root` of `~/.dev-kit/config.json` (in Claude Code, the plugin's base directory `<dev-kit>/plugins/<plugin>` works too).

## 1. Read what exists

Before asking anything, read the folder: `README*`, `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `.gitignore`, `.gitattributes`, `.githooks/`, `.github/workflows/`, the build files (`package.json`, `Cargo.toml`, `build.gradle*`, `pyproject.toml`, `manifest.json`…), `git remote -v`. Derive from them the name, purpose, audience, stack and the build, test and verification commands. An empty folder is a new project.

## 2. Ask one round

Ask with the interactive question tool when the current agent provides one; otherwise ask with concise numbered options in chat. Batch the questions in as few calls as possible (four at most), put the recommended option first and label it "(Recommandé)". Ask only what the files do not answer; when a file suggests an answer, offer it as the recommended option and say where it comes from.

| Topic | Options |
|---|---|
| Name, purpose and audience | the values read in the files, or "Autre" to type them |
| Stack and commands (build, tests, verification run by the pre-push hook) | the values read in the files |
| Documentation | GitHub wiki (`wiki-github`, large projects) · `docs/` folder (`docs-folder`, small projects) · none |
| Tracking | Linear (`linear`, large projects) · GitHub issues (`github-issues`, small projects) · none |
| Languages | defaults (chat French, documentation and code English, wiki French) · exceptions; `AGENTS.md` and `CLAUDE.md` stay in English |
| GitHub repository | create a private repository with `gh` · already exists · none |
| Verification | pre-push hook · hook and GitHub Actions CI (with the PR template and its check, dev-kit's `docs/pr-description.md`) · none |
| Auto-merge (GitHub repository only) | merge low-risk pull requests by themselves and label the others `to test`, `to acknowledge` or `to review` (`auto_merge`, recommended with a GitHub repository) · no |
| Architecture (recommended) | the checked architecture of the stack found (a `*.csproj`, a Cargo workspace, a Gradle build, a `pyproject.toml`, a `package.json` or JS/TS sources), with its fields proposed from the code (`architecture`; fields per stack in the script's docstring: .NET test and main csproj; Python `roots` to cover only some of several packages (all by default) and `runner` when no `uv.lock` or `poetry.lock` tells it; Rust `exclude`, e.g. xtask; Kotlin `module` when several modules have sources (one is covered), and `root`; JS/TS `roots`, e.g. `["src", "app"]`) · none |
| Design principles | the Design section of `AGENTS.md` and the `docs/design/` pages, for a repository with code · none, for a repository without code such as a wiki (`"design": false`) |
| Tools kept (default: all denied) | the tools of `DENIED_TOOLS` in the script the project uses (`keep_tools`): the built-in browser `mcp__Claude_Browser` for a web app, others on demand; the connectors of `~/.dev-kit/config.json` go to `settings.local.json`, `linear` kept with Linear tracking |
| Glossary path | `docs/glossary.md` for `docs/` · `../<name>-wiki/Glossaire.md` for a wiki (`Glossary.md` if the wiki is in English) · an existing glossary found in the files · none, for a project without domain vocabulary (`"glossary": null`: no glossary, no Vocabulary section) |

Large projects take a wiki and Linear; small ones (stellar) take `docs/` and GitHub issues.

## 2b. Extract the glossary (existing project without one)

The glossary holds the domain terms: the notions the rules, the player or the user talk about, not technical terms. Read the code (type, class and module names), the documentation and the interface texts, and list the domain notions with, for each one, the French and English terms (the English one is the code's), the displayed terms when they differ, a one-line definition, and the synonyms found for it.

- Ask about the **ambiguous** notions only — several words for one notion, one word for several notions, a French term with no clear English counterpart — in rounds of interactive questions, the proposed term first and labelled "(Recommandé)".
- The other notions go in as proposed: The user approves them with the whole plan in step 3, where the full glossary is shown.
- Aim for the whole step to take under 10 minutes; past about 150 notions, keep the most central and say so.

## 3. Show the plan

Write the answers to a JSON file in the scratchpad (keys: `name`, `purpose`, `audience`, `stack`, `docs`, `tracking`, `languages`, `commands`, `verify`, `ci`, `auto_merge`, `glossary`, `glossary_entries`, `design`, `keep_tools`, `architecture`; see the script's docstring), then list the changes without making them:

```bash
python3 "<dev-kit>/plugins/core/scripts/init_project.py" <project dir> <answers.json>
```

Show the user every `to do:` line and every `note:` line. For existing `AGENTS.md` and `CLAUDE.md` files, say which sections or import will be added, and that a former `@<glossary>` import is removed from `CLAUDE.md` (the `core` hook injects the glossary index instead). A section or Communication bullet identical to a past template copy of the shared rules is removed, since the `## Shared rules` section replaces it; a differing one is kept as a local deviation and its diff is shown as a `note:`; other sections are never changed or removed. When the glossary is created with entries, show it as a table. Wait for their agreement before writing anything.

## 4. Apply

```bash
python3 "<dev-kit>/plugins/core/scripts/init_project.py" <project dir> <answers.json> --apply
```

Then, if the user asked for a GitHub repository: make the first commit (English message, one commit), then `gh repo create Jyhess/<name> --private --source <project dir> --push`. Never create a public repository. Then run the `--apply` command again: once the GitHub repository exists, the script turns on its automatic deletion of head branches after merge, and creates the ready label below.

With `architecture`, run the steps of the `note: architecture, after apply:` line in order; the verification must pass, and the user sees the architecture file.

The ready label (`Prêt` for French documentation, `ready` otherwise) marks the tickets ready to implement. With GitHub issues, the script creates it once the GitHub repository exists: run the `--apply` command again after `gh repo create`. With Linear, create it in the team with the Linear tools (`create_issue_label`) unless it exists. Do not create a GitHub Project board.

## 5. Hand over

Tell the user, in a few lines:

- the files created or changed;
- the `note:` lines: plugins not available yet, a project not registered in the work journal (journal not cloned, folder outside the dev folder), a glossary not created (wiki not cloned), a glossary page to add to the wiki's index, a ready label or the automatic deletion of merged branches not set up yet, rebase merging to allow or check for auto-merge, shared instructions in an existing `CLAUDE.md` that may be consolidated into `AGENTS.md`;
- for a glossary outside the repository (wiki), that the wiki needs its own commit;
- that the project's Claude Code plugins load at the next session, or after `/reload-plugins`;
- with auto-merge, what it merges by itself and what goes to review (dev-kit's `docs/auto-merge.md`), and that it acts from the first pull request opened after the workflow reaches the default branch;
- with `architecture`, the components of the architecture file, and that a new component or dependency now fails until it is declared (an architecture change they approve);
- the sections of `AGENTS.md` still to complete (marked "to be completed").
