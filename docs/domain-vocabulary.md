# Scoping of the domain vocabulary rule

> Started 2026-11-02 with the `clarify` skill. Status: levels 1, 2 and 3 validated.

## Level 1 — Goal

Give every project managed by dev-kit a single domain vocabulary, recorded in a glossary that is the reference for Claude, the documentation, the code and the user interface: no synonyms, a French ↔ English mapping, stable terms on screen, and a Claude that knows the terms from the start of each session.

Problems addressed: synonyms and drift between code, documentation and interface; French ↔ English translation (French wiki, English code); onboarding of Claude; consistency of the words shown to the player or user.

Success criteria, all `[manuel]`:

- over one month of use, Claude introduces no new domain term without first proposing it for the glossary;
- when the user or a document uses a synonym, Claude points it out and proposes the glossary term;
- every glossary term has its French and English equivalents, and the code uses the English term;
- an existing project gets a first glossary in less than 15 minutes.

Minimal version: a Vocabulary section of `AGENTS.md` written by `project-init`, a convention for the glossary file, and `clarify` checking vocabulary against the glossary. When equipping an existing project, `project-init` extracts candidate terms from the code and documentation and submits them to the user (resolution of I1: the 15-minute criterion needs a producer of the first glossary, and a dedicated skill was ruled out).

Out of scope: tactical DDD (aggregates, repositories, factories); bounded contexts (one glossary per project).

Budget: half a day.

## Level 2 — Business

Answers:

- **Location**: the glossary follows the project's documentation choice: `docs/glossary.md`, or a glossary page of the wiki, in the wiki's language.
- **Entry**: French term, English term (the one used in code), short definition in the documentation's language, forbidden synonyms, and the displayed term in French and English when it differs from the domain term (code `hit_points`, interface "PV").
- **Domain term**: a notion the rules, the player or the user talk about; technical terms (cache, handler, layer names) are not recorded.
- **Interface languages**: the glossary covers French and English only; other languages live in the translation files, which follow the English term.
- **New term**: Claude proposes the full entry and uses the term only after the user's agreement.
- **Renaming**: the former term becomes a forbidden synonym; Claude proposes a ticket that renames code and documentation in a dedicated commit.
- **Existing code**: a forbidden synonym outside the task is left untouched, mentioned at the end of the task, with a ticket proposed.
- **Conversation**: Claude points out every synonym the user uses, with the glossary term.
- **Loading**: an index of the glossary is in context from the start of each session; when it cannot be found (wiki clone missing), a one-line warning, and the session is not blocked.
- **First glossary**: when equipping an existing project, `project-init` asks rounds of interactive questions on ambiguous terms only; the others appear in the full glossary shown before writing, and the user's agreement on the files (C1) approves them as a whole (resolution of I2: "propose, then wait" against direct addition).
- **`clarify`**: its vocabulary check compares answers with the glossary and puts every gap in the inconsistencies block; at each gate, new terms decided during the scoping are proposed for the glossary.

Hypothesis: a glossary stays under about 150 terms, so its context cost is acceptable — confirmed by the size of the largest project's glossary after extraction.

### Acceptance criteria

- **V1 — New term.** Given a project with a glossary, when Claude needs a notion missing from it, then it proposes the full entry and uses the term only after the user's agreement. `[manuel]`
- **V2 — Synonym in conversation.** When the user's message contains a forbidden synonym, then Claude gives the glossary term, at every occurrence. `[manuel]`
- **V3 — Synonym in writing.** Claude never writes a forbidden synonym in code, documentation, tickets or commits. `[manuel]`
- **V4 — Existing code.** Given a forbidden synonym outside the task's scope, then Claude leaves it, mentions it at the end of the task and proposes a ticket. `[manuel]`
- **V5 — Renaming.** When a term changes, then the former one becomes a forbidden synonym and Claude proposes a renaming ticket (code and documentation, dedicated commit). `[manuel]`
- **V6 — New project.** When `project-init` creates a project, then it writes the vocabulary section of `AGENTS.md` and an empty glossary at the place given by the documentation choice (wiki or `docs/`).
- **V7 — Existing project.** When `project-init` equips an existing project, then it asks rounds of questions on ambiguous terms, shows the full glossary before writing, and the whole takes less than 15 minutes. `[manuel for the duration]`
- **V8 — Loading.** Given a new session, then the glossary index (every term and its forbidden synonyms, no definitions) is in context without being asked for; when it cannot be found, a one-line warning is shown and the session is not blocked.
- **V9 — `clarify`.** When an answer uses a term missing from the glossary or a forbidden synonym, then it appears in the inconsistencies block; at each gate, new terms are proposed for the glossary. `[manuel]`

## Level 3 — Implementation

### Decisions

| Decision | Reason |
|---|---|
| The hook injects a glossary index, not the glossary: no definitions, no displayed terms; beyond 10,000 characters (Claude Code's cap on hook output) it truncates and warns in one line; `init_project.py` removes the former `@<glossary>` import from `CLAUDE.md` | the index is enough to use the right words and costs half the glossary; an external `@` import needs an approval that desktop sessions never show, and fails from worktrees |
| New answer keys: `glossary` (default `docs/glossary.md`, or `../<name>-wiki/Glossaire.md`, `Glossary.md` for an English wiki) and `glossary_entries`, rendered by the script; an existing glossary is never overwritten; a missing wiki clone gives a `note:` line | the wiki path was not among the answers; deterministic output, tested like C1 and C3 |
| Glossary format: one table `FR \| EN (code) \| UI FR \| UI EN \| Definition \| Forbidden synonyms`, sorted by the term in the documentation's language | compact in context |
| `core` hook `vocabulary.py` on `startup\|resume\|clear\|compact`: reads the glossary path in the Vocabulary section of `AGENTS.md` (or a legacy `CLAUDE.md`); none → no output; otherwise injects the behaviour rules (V1–V5, English text kept in the plugin) and the index, plus a one-line warning when the glossary is missing; always exits 0 | a fix to the rules reaches every project without copying; rules stay after `/clear` and `/compact` |
| A relative glossary path is resolved against the session folder, then against the main checkout (`git rev-parse --git-common-dir`) | `../<name>-wiki/…` is found from worktrees |
| Codex reads the glossary named in `AGENTS.md` at the start of each task involving domain concepts | Codex has no session-start hook |
| `vocabulary_check.py` (whole word, ignoring case and accents): forbidden synonyms on the added lines as a pre-commit warning; forbidden synonyms and unused terms in the glossary report of each Review, where the AI also proposes the missing terms | checked by a tool, never blocking |
| `project-init` asks the glossary path, then extracts the first glossary of an existing project; `clarify` checks vocabulary against the glossary and proposes new terms at each gate | minimal version of level 1 |

Hypothesis: an `@` import outside the repository (`@../project-wiki/Glossary.md`) loads after a single approval — refuted: the approval dialog is never shown in desktop sessions, so the import was silently skipped.

### Tests

- Hook, first failing test: missing glossary → rules and warning, exit 0. Then: glossary present → rules only; no vocabulary section → no output; "Vocabulaire" title recognised.
- `init_project` (V6): new `docs/` project → section and empty `docs/glossary.md`; wiki project → wiki path; existing `AGENTS.md` → section appended; `glossary_entries` rendered; existing glossary kept.
- Manual: V1–V5, V7 (duration), V9.

The other projects get their glossary when next equipped by `project-init`, outside this budget.
