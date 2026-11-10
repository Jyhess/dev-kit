# dev-kit — shared project instructions

Shared practices, workflows, plugins and scripts reused across the user's projects, private ones and public ones (stellar, meteo). Scope and decisions: `docs/scoping.md`.

Audience: the user (Jyhess), and readers of their methods. Stack: Python 3 scripts and Claude Code plugins, on Windows and macOS.

## Communication and languages

- Talk to the user in French.
- Documentation and skills are in English; code, comments and commit messages are in English.

## Shared rules

- Shared rules: `~/.dev-kit/rules/shared-rules.md`; Claude Code gets them from the core plugin, other agents read the file at session start; a section of this file that contradicts them wins.

## Commands

- `python3 -m unittest discover -s tests` — Tests
- `sh .githooks/pre-push` — Verification (private words, ticket references, plugin manifests, tests)
- `python3 plugins/core/scripts/doc_budget.py` — Markdown size budgets

## Documentation and tracking

- Documentation lives in `docs/`; no wiki. The README lists the plugins and the scripts.
- Tasks are GitHub issues of `Jyhess/dev-kit`.
- Time spent is recorded in the work journal (plugin `dev-journal`, `docs/dev-journal.md`), under `--project dev-kit`.

## Design

- Before designing or changing code, read `docs/design/principles.md` (errors, robustness by design); the generated projects get a copy of `plugins/core/templates/design/`.

## Layout

- `.claude-plugin/marketplace.json` lists the plugins of the `jyhess` marketplace, each in `plugins/<name>/`, loaded in place from the local clone: no `version` field.
- Scripts and hooks are Python 3, called as `python3`, and run on Windows and macOS; each states its role in its docstring.
- `plugins/core/templates/` is what `project-init` writes into a project; dev-kit's `.githooks/`, `.github/` workflows, scripts and PR template are copies of it (`docs/auto-merge.md`, `docs/pr-description.md`).
- No private data in tracked files: local values go in `~/.dev-kit/config.json` (connector ids, clone `root`) or the private words refused at pre-push (`private-words` of the `dev-journal` clone, shared; the ignored `.private-words`, this project's own) and `history/`.

## Verification

- The pre-push hook (`.githooks/`) runs `sh .githooks/pre-push`; never bypass it. CI (`.github/workflows/verify.yml`) runs it and the `tests/test_*_template.py` end-to-end tests on Linux only; Windows is covered by the pre-push hook on the user's Windows machine. The pre-commit hook only prints non-blocking warnings.
- When it fails, squash each fix into the commit it corrects: `git commit --fixup <sha>`, then `git -c sequence.editor=: rebase -i --autosquash --autostash origin/main`.

