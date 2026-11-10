---
name: pilot
description: Steer a theme as its pilot session — one sub-session per ticket, the theme's state in a parent ticket, from the start of the theme to its close. Use when the user passes a ticket or project with sub-tickets to steer, asks for a pilot session ("session de pilotage", "pilote ce thème"), asks "t'en es où ?" in a pilot, when a sub-session of the pilot ends, or when the context-size hook asks a pilot to hand over.
---

# Pilot a theme

A **pilot** session steers one **theme**: it does not implement tickets itself; it starts one **sub-session** per ticket, follows their PRs, and keeps the theme's state in a **parent ticket**. Keep the pilot's own context small: read summaries, PR and CI status, not diffs or transcripts.

## Tools

- **Tracking**: the project's `AGENTS.md` names its tracking tool; use the matching skill (`tracking-github-issues` or `tracking-linear`) for its rules, templates and Definition of Ready.
- **Sessions** (Claude desktop app): `mcp__ccd_session_mgmt__list_sessions` with `{"linked": true}` lists the sub-sessions with their id, state and branch; `mcp__ccd_session__start_session` starts one; `mcp__ccd_session_mgmt__archive_session` archives one; `SendMessage` with a session's `local_…` id reaches it. A sub-session's end arrives as a note quoting its report.
- **PRs and CI**: `gh pr view <n> --json state,mergedAt,reviewDecision,statusCheckRollup,url` and `gh pr checks <n>`.
- **Outside the desktop app** (CLI, Codex: no session tools): follow the work through the parent ticket and `gh`; to start a sub-session, give the user a brief to paste into a new session; never archive. Say so once when the pilot starts.

## Parent ticket

The parent's body (or description) is the theme's **current state**, rewritten at each change, never appended to:

```markdown
## Goal
<one or two sentences>

## Tickets
- [ ] #12 <title> — <state: ready / clarifying / in progress / PR #n / waiting for the user> — after #11
- [x] #11 <title>

## Open sub-sessions
- #12: <session title> (`local_…`), branch `<branch>`, PR #n

## Next steps
- <what comes next, in order>
```

- Remove what becomes useless: finished sub-sessions, past next steps, resolved questions. Keep a finished ticket as a ticked line only.
- Comment the parent only at a pilot hand-over (see [Close the pilot](#close-the-pilot)).
- **GitHub issues**: the parent is an issue; its tickets are a task list `- [ ] #n` (no native sub-issues).
- **Linear**: a ticket with sub-tickets keeps the state in its body (`save_issue`); a project keeps it in its description (`save_project`) and its hand-over is a status update (`save_status_update`). With nothing passed, propose a Feature ticket in the current milestone.

Translate the headings for a French project (Objectif, Tickets, Sous-sessions ouvertes, Prochaines étapes).

## Start a theme

1. Read the item the user passes (a ticket with sub-tickets, a project) or ask for the theme. Read the parent and each ticket's state, order, dependencies and ready mark.
2. Without a parent, propose one: title, goal, existing tickets to attach, new tickets to create, order and dependencies. Create or update it only after the user's agreement, with the tracking skill's templates.
3. Ask once: "Archiver d'office les sous-sessions finies sans rien à faire, pour ce pilote ?" the user's yes holds for this pilot only; record it in the parent's Next steps so a later pilot asks again.
4. Then [start the next tickets](#start-the-next-tickets).

## Start the next tickets

1. Pick the ready tickets whose blockers are merged or have a branch or PR, at most 4, and no two that touch the same files. A ticket that fails the Definition of Ready can still be started: its sub-session clarifies it first.
2. Submit the list to the user (ticket, why now, whether it needs clarifying). Start nothing before their agreement, except a ticket of the parent's agreed order that only waited for its blocker's branch or PR: start it at once, without that code (the Git rule of the project's instruction file).
3. Start one sub-session per ticket: `start_session` with `context: "fresh"`, `use_worktree: true`, and a brief:
   - the ticket's link and the project;
   - "Clarify it with `core:clarify` (levels 2 and 3) before implementing" when the Definition of Ready fails, else "The ticket is ready";
   - "Implement it with the `<tracking skill>` skill, up to the PR";
   - "Start your final report with exactly one end-of-session case: Finished, nothing left / Finished, follow-ups created (list them) / Finished, manual steps left (list them) / Not finished, waiting for the user (review, answer or merge)";
   - "When the context-size hook asks you to hand over, comment the ticket and hand over on the same branch".
4. Update the parent: ticket states, open sub-sessions.

The pilot never clarifies a ticket itself: clarifying fills the pilot's context.

## End-of-session summary

Each time a sub-session ends a turn with a final report (often a merged PR):

1. Check its case against the facts: PR state and CI, ticket state, tickets it created. A report that says "finished" with an unmerged PR is "Not finished, waiting for the user".
2. Tell the user plainly, first line: **<ticket> — <case>**, then the list the case calls for, with links:
   - **Fini, rien à faire**: PR merged, ticket closed, nothing left.
   - **Fini, suites créées**: PR merged; the follow-up tickets, added to the parent.
   - **Fini, étapes manuelles restantes**: PR merged; each manual step the user must do (check in the app, configure a machine, release…).
   - **Pas fini, attend l'utilisateur**: what they must do — review, answer the session's question, merge — and where.
3. Update the parent.
4. **Fini, rien à faire**: archive the sub-session if the user said yes at the start of this pilot, else propose to archive it. Other cases: archive only on the user's yes.
5. [Start the next tickets](#start-the-next-tickets), without waiting for the PR's merge.

A note about a turn that only asked a question or reported progress is not an end: relay the question, if any, and wait.

## Status ("t'en es où ?")

Refresh first: `list_sessions` (linked), each open PR's state and CI, the parent. Then answer in this order:

1. **Prochains tickets prêts**: the next ready tickets with no open blocker.
2. **Sous-sessions**: one line each — ticket, state (working / waiting for the user / finished), PR, CI.
3. **À faire pour toi**, by type, each with its link: review, vérification manuelle, merge, réponse.

Nothing for the user: say so in one line.

## Archive

Archive a sub-session only when its case is "Fini, …" and its PR is merged or it had none. Never archive a working session, one waiting for the user, or one whose branch has unmerged commits. Remove archived sessions from the parent's Open sub-sessions.

## Close the pilot

When the user asks, or when the context-size hook asks the pilot to hand over:

1. Refresh as for the status.
2. Rewrite the parent's state.
3. Comment the parent (Linear project: status update) with the hand-over: what this pilot finished, the sub-sessions still open (title, `local_…` id, branch, PR, what they wait for), the next steps, and whether the user allowed automatic archiving.
4. Archive the finished sub-sessions (see [Archive](#archive)). Leave the others running: the next pilot follows them through their PRs and reaches them with `SendMessage` by id; their notes keep reaching this pilot only.
5. Give the user the theme's summary: tickets done, open, next; what they must do.
6. If the theme goes on, propose a new pilot: `start_session` with `initiation: "own_initiative"`, `context: "fresh"`, and a brief "Pilot the theme <parent link> with the `core:pilot` skill; read the parent and its last hand-over comment first." Outside the desktop app, give the user that brief to paste.
