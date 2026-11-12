# Shared rules

Rules shared by every project that opts in with a `## Shared rules` section in its `AGENTS.md`; a section of the project's `AGENTS.md` that contradicts them wins.

## Communication

- A question gets an answer, not an action: change files, tickets or remote state only on an explicit request; "Is it possible to…?" is a question: answer, propose, wait.
- Before designing anything non-trivial, use the shared clarification workflow.
- A single question with choices goes in the agent's interactive question tool (`AskUserQuestion`); several at once, or one with more than four options, in the form of the core skill `ask` (`show_widget`), its fallbacks when that tool is missing; an open question needing a long written answer stays in text.
- A warning or notice of a skill: a quote block whose first line is the emoji and a bold title (`> ⚠️ **Warning: budget exceeded**`), then the detail.
- An error or warning from a tool (command, hook, test, script): a heading `### 🛑 FAILURE: <tool>` or `### ⚠️ WARNING: <tool>` (non-blocking), then its raw output in a fenced code block.
- No GitHub alert blocks (`> [!WARNING]`): the desktop app shows them as plain text.
- Every ticket, issue, pull request, card, email or calendar event mentioned to the user is a Markdown link to its URL, everywhere (answers, question forms, reports, sub-sessions): `[KAT-290 title](url)`, `[#<n> title](url)`, `[card title](url)`. The URL comes from the item's tool (`url`, Trello `shortUrl`, calendar `htmlLink`, Gmail `https://mail.google.com/mail/u/0/#all/<threadId>`); unknown, read it with that tool before mentioning the item. The Writing rule below still keeps ticket references out of files.

## Writing

- Write what is needed to act, nothing else: no history (git keeps it), no paraphrase of the code, no copy of a ticket and no ticket reference (`#<n>`, `ABC-<n>`, an issue URL; the commit or PR links the ticket); a decision is its choice and its reason in one line.

## Context

- Every tool result stays in the context: ask only for what is needed (file ranges, `head`, `--stat`, `grep`, a tool's own filters).
- One ticket per session. When the context-size hook warns, finish the current work, then ask the user whether to hand over as it says.

## Provisional values

- A value the task does not give (threshold, duration, limit…) gets a provisional one in a named constant or config entry.
- List them under "Values to validate" in the draft PR, with the label `to acknowledge`, then ask the user about each: confirm, change, or defer. Confirmed or changed values go into the ticket and the code, and leave the list; a deferred one gets a ticket and stays listed; with none left, drop the label.

## Known limitations

- Anything deliberately left incomplete or simplified is written where it applies (README, doc, comment, or a TODO, the only line that may cite a ticket, removed when that ticket is resolved) and listed at the end of the task and in the PR; their tickets are created with the user's agreement.

## Manual checks

- The programs of a project are its `## Commands` lines labelled `Launch (gui)`, `Launch (terminal)` or `Launch (web <port>)`.
- When a task with `[manual]` / `[manuel]` criteria or a `## Manual checks` section ends, offer in the Claude desktop app's next-step box a "Lancer" button for the program the checks need (two at most), the one the task changed; give a launch command as a one-line bash block only for a `terminal` or `web` program, or outside the desktop app: a `gui` program's button is enough.
- On a click, run it from the task's worktree: `gui` as a background command, whose output you read on failure; `terminal` in a new tab of the Terminal panel; `web` as `terminal`, then open `http://localhost:<port>` in the built-in browser.
- No launch line: no button; offer to add one.

## Git

- One commit per feature, fix or change; commit messages in the language the project's "Communication and languages" section gives for code.
- Pull requests: once the task's verification passes, push its branch and open the PR as a draft (`gh pr create --draft`) without asking; in the Claude desktop app, turn on the PR's auto-fix (CI, conflicts, review comments), elsewhere say it is off. Only the user marks a PR ready (it may then be merged by itself): never `gh pr ready`. Any other push only when asked.
- A task's branch starts from the default branch and stays current with it: `git fetch`, then `git rebase --autostash origin/<default branch>`, when starting or resuming the task and before each push or PR (on the default branch: `git pull --rebase --autostash`). Never branch from another task's branch: work that depends on an unmerged branch or PR starts at once from the default branch, without that code and without asking, and is rebased once it is merged.
- Resolve and show mechanical conflicts (imports, lists, neighbouring lines); on a conflict of substance, `git rebase --abort` and describe it. A pushed branch goes back with `git push --force-with-lease`.
