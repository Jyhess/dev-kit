---
name: github-issues
description: Track a small project in GitHub issues with `gh` — implement an issue up to the PR, split a feature into issues, create a bug, an investigation or a task. No points and no time in the issues (the work journal measures time). Use for any request about issues (#12, "crée une issue", "découpe en issues") in a project tracked in GitHub issues.
---

# Tracking in GitHub issues

Write issues in the language of the project's documentation, with the templates below (headings translated for a French project: Contexte, Comportement attendu, Critères d'acceptance métier, Critères d'acceptance technique, Hors périmètre, Notes d'implémentation, Étapes pour reproduire, Corrigé si, Question, Durée maximale, Livrable, À faire, Fini quand).

Use `gh` on the project's repository (`gh repo view` gives it). Never put Linear-style points or a time section in an issue.

The Git, pull request, provisional values and known limitations rules are those of the project's `AGENTS.md`; this skill does not repeat them.

## Rules

- **One issue = one branch = one PR** for code. Larger work becomes a parent issue whose body lists its sub-issues as a task list (`- [ ] #12`).
- **Type** in the title's wording or a label when the repository has type labels (`bug`, `enhancement`…); do not create labels without asking.
- **Order**: a `Blocked by #n` line at the end of the body for each dependency. When the repository has a linked Project, its board is the reference: the next issue is the top of its Ready column. Otherwise numbers give the order: create issues in the order they will be done.
- **Definition of Ready**: every number or threshold the code needs is in the issue; edge cases are listed (extreme values, sustained durations, repetitions, errors); every business criterion is a Given / when / then with values, or is `[manual]`; the implementation notes leave no open question, follow the project's robustness-by-design rules and list the architecture changes the user approved, or say there is none. Check it when creating or splitting an issue (it sets the mark) and when starting it; when it fails, list what is missing and propose the shared `clarify` skill; a parallel session does not start the issue.
- **Ready mark**: the label `Prêt` in a French project, `ready` otherwise, and the Ready column of the linked Project (see below). When the label is missing, offer to create it (`gh label create`) with the user's agreement.
- **Criteria**: business criteria as "Given / when / then" with verifiable values, `[manuel]` (or `[manual]`) for what is judged by hand; technical criteria verifiable by a command or by reading the code.
- **Bugs**: found while reviewing a PR, fixed in that PR; after the merge, a new issue that links the original one.

## Templates

Implementation:

```markdown
## Context
## Expected behaviour
## Business acceptance criteria
- Given …, when …, then …
- [manual] …
## Technical acceptance criteria
- End-to-end tests for each automatable business criterion.
## Out of scope
## Implementation notes
```

Bug: `## Steps to reproduce`, `## Observed behaviour`, `## Expected behaviour`, `## Fixed when` (an end-to-end test reproduces the bug, then passes after the fix).
Investigation: `## Question`, `## Leads`, `## Time box` (a duration), `## Deliverable`.
Task: `## Context`, `## To do` (checkboxes), `## Done when`.

## Implement an issue

1. Read the issue (`gh issue view <n> --comments`). Check the Definition of Ready. If a criterion is ambiguous, ask before coding (the shared `clarify` skill for anything substantial).
2. Name the branch `<n>-<short-slug>`, unless the project's `AGENTS.md` says to commit on the default branch.
3. Develop test-first: each automatable business criterion becomes a test written before the code. Respect the technical criteria and the out of scope. An architecture change the issue does not list as approved stops the work: submit it to the user first. Prove each regression test by seeing it fail with the defect it targets reintroduced.
4. Rebase, then run the project's verification: every automatable criterion passes.
5. Open the draft PR. Title = the issue's title; body = the repository's PR template (`.github/pull_request_template.md`) filled in, with `Fixes #<n>` and only the optional sections that apply (among them the architecture changes approved in the issue); the `PR description` check turns red on a missing or empty section: check it first with `python3 .github/scripts/pr_description.py <body file>`. On the default branch, put `Refs #<n>` in the commit message instead, and `Fixes #<n>` only when every criterion is met.
6. Ask the user about each provisional value and known limitation, as `AGENTS.md` says; their tickets are issues.
7. Comment on the issue with what was noticed out of scope, and propose a new issue for it instead of doing it.
8. Remind the user of the `[manuel]` criteria to check.

## Glossary report

When the user asks for a review of a milestone or a period, and the project has a glossary, add to it:

- forbidden synonyms and unused terms (proposed for removal): output of `python3 <dev-kit>/plugins/core/scripts/vocabulary_check.py` run in the project, `<dev-kit>` being the dev-kit clone, the `root` of `~/.dev-kit/config.json` (in Claude Code, the plugin's base directory `<dev-kit>/plugins/<plugin>` works too);
- missing terms: domain notions used in the code and docs but absent from the glossary, each with its full proposed entry.

## Split a feature into issues

1. Read the documentation and the existing open issues (`gh issue list`).
2. List the issues needed (implementation, investigations for the unknowns, tasks without code), each with its template.
3. Present the split to the user (titles, order, dependencies) and wait for their agreement.
4. Create them in order (`gh issue create --title … --body-file …`), then add the `Blocked by` lines that point to issues created later (`gh issue edit`). Mark ready the ones that meet the Definition of Ready.
5. Give the user the list with the links.

## Mark an issue ready

1. `gh issue edit <n> --add-label <label>`.
2. Find the linked Project: `gh api graphql -f query='query($o:String!,$r:String!){repository(owner:$o,name:$r){projectsV2(first:5){nodes{id number title}}}}' -f o=<owner> -f r=<repo>`. None: stop here.
3. Add the issue to it, which gives its item id (the existing one if it is already there): `gh project item-add <number> --owner <owner> --url <issue url> --format json`.
4. Read the Status field id and its Ready option id: `gh project field-list <number> --owner <owner> --format json`.
5. Move the item: `gh api graphql -f query='mutation($p:ID!,$i:ID!,$f:ID!,$v:String!){updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$v}}){projectV2Item{id}}}' -f p=<project id> -f i=<item id> -f f=<field id> -f v=<option id>`.

If gh lacks the `project` scope, keep the label and tell the user to run `gh auth refresh -s project`.
