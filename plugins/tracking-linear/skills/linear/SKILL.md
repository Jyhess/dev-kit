---
name: linear
description: Track a project in Linear with the Linear MCP tools — implement a ticket up to the PR, split a step or a feature into tickets, create a task, validation or decision, report a documentation change into Linear, prepare a step review or a decision point. Use for any Linear ticket identifier (ABC-…) or any request to create, split, order, estimate or review tickets of a project tracked in Linear.
---

# Tracking in Linear

Write tickets in the language of the project's documentation, with the matching templates: [templates.fr.md](templates.fr.md) or [templates.en.md](templates.en.md).

## Project settings

Read them in the project's `AGENTS.md`: workspace and team (ticket prefix), what projects and milestones stand for, label groups, reference tickets for estimates, where the documentation describes each step (goal, budget, "validated if" criteria), the code repository linked to Linear, the work journal folder. When one is missing, ask the user and propose to add it to `AGENTS.md`.

Git, pull request, provisional values and known limitations rules: the project's `AGENTS.md`.

## Rules

- **Documentation describes the why and the what; Linear tracks.** Projects and milestones link to their documentation page. Neither copies the other beyond what the templates ask: a ticket's choices stay in the ticket; a step's page only gets the decisions that change its goal or criteria, or span several steps.
- **Hierarchy**: project (a phase, up to a decision point) → milestone (a step or a decision point) → ticket → sub-ticket, only under a Feature parent. Otherwise use relations: *blocked by* for order, *related to* for a bug and its original ticket.
- **One type per ticket**, a label of the Type group: Implementation (1 ticket = 1 branch = 1 PR), Feature (parent of sub-tickets, no PR), Bug (defect found after the merge), Improvement (refactoring or tuning, business behaviour unchanged), Investigation (an unknown to remove first), Task (work without code), Validation (a test session with users), Review (end of a step), Decision (a decision point). Plus the project's other label groups.
- **Estimates**: complexity points on the Fibonacci scale 1, 2, 3, 5, 8, always by comparison with the reference tickets. Every ticket but a Feature parent is estimated; above 5 points, it becomes a Feature parent with Implementation sub-tickets.
- **Criteria**: business criteria as "Given / when / then" with verifiable values, `[manuel]` (or `[manual]`) for what is judged by hand; technical criteria verifiable by a command or by reading the code.
- **Definition of Ready**: every number or threshold the code needs is in the ticket; edge cases are listed (extreme values, sustained durations, repetitions, errors); every business criterion is a Given / when / then with values, or is `[manual]`; the implementation notes leave no open question, follow the project's robustness-by-design rules and list the architecture changes the user approved, or say there is none. Check it when creating or splitting a ticket (it sets the mark) and when starting it; when it fails, list what is missing and propose the shared `clarify` skill; a parallel session does not start the ticket.
- **Ready mark**: the label `Prêt` in a French project, `ready` otherwise (`save_issue`); states are unchanged. A missing label: offer to create it (`create_issue_label`) with the user's agreement.
- **Small results**: `save_issue` returns the saved ticket: do not fetch it again; give `get_issue` and `list_issues` only the `fields` the step needs (`title`, `status`, `estimate`…).
- **States**: Backlog → Todo → In Progress → To review → Done, plus Canceled. With the GitHub integration, opening the PR moves the ticket to To review and merging it to Done.
- **Bugs**: found while reviewing a PR, fixed in that PR; after the merge, a Bug ticket in the current step's milestone, related to the original ticket.
- **Linear failing**: when the Linear MCP or `linear_order.py` fails, read https://linearstatus.com/ and report its incident (component, status, since), or that it shows none, with the error.
- **Time**: tickets carry no time spent; the work journal is the only record of time, and velocity is measured in points.

## Implement a ticket

1. Read the ticket (`get_issue`), its relations and the documentation page of its step. Check the Definition of Ready. If a criterion is ambiguous or contradicts the documentation, ask before coding (the shared `clarify` skill for anything substantial).
2. Move the ticket to In Progress; its branch takes the name Linear gives (`gitBranchName`).
3. Develop test-first: each automatable business criterion becomes an end-to-end test written before the code. Respect every technical criterion and the out of scope. An architecture change the ticket does not list as approved stops the work: submit it to the user first. Prove each regression test by seeing it fail with the defect it targets reintroduced.
4. Rebase, then run the project's verification: every automatable criterion passes.
5. Open the draft PR. Title: the ticket's title. Description: the repository's PR template (`.github/pull_request_template.md`) filled in, with `Fixes <ID>` and only the optional sections that apply (among them the architecture changes approved in the ticket); the `PR description` check turns red on a missing or empty section: check it first with `python3 .github/scripts/pr_description.py <body file>`.
6. Ask the user about each provisional value and known limitation, as `AGENTS.md` says; their tickets are Linear tickets.
7. Comment on the ticket (`save_comment`): the PR link, what the AI found hard, and what was noticed out of scope, with a ticket proposed for it instead of doing it.
8. List the `[manuel]` criteria to check.

## Split a step into tickets

1. Read the step's documentation page and the pages it cites.
2. List the existing tickets of the milestone (`list_issues`), the Review included.
3. List the tickets needed: implementation, investigations for the unknowns, tasks without code, validations with users.
4. Write each ticket with its type's template; estimate each by comparison with the reference tickets.
5. Present the split to the user (titles, types, estimates, order) and wait for agreement.
6. Create the tickets. For each: team, project, milestone, labels, estimate, `assignee: me`, state Backlog (Todo for the current step). Then put them in the order to do, the first on top (see [Order the tickets](#order-the-tickets)).
7. Set the `blockedBy` relations once all are created; the Review is blocked by every ticket of the step. Then check each ticket against the Definition of Ready and mark the ones that meet it.
8. A step page that still lists cards or tasks gets a link to the Linear project and milestone instead.
9. Give the links of the tickets created.

## Create a task, a validation or a decision

1. Find the project and milestone concerned (admin work and decision points may have their own).
2. Write the ticket with its type's template. For a Decision, copy the decision point's criteria from the documentation and set its date as `dueDate`.
3. Estimate it, and create it once its content is agreed; mark it ready if it meets the Definition of Ready.

## Report a documentation change into Linear

- **Calendar dates**: target dates of milestones (`save_milestone`), start and end dates of projects (`save_project`), due dates of Decision tickets.
- **Budget of a step**: the milestone description and the Time section of the Review ticket.
- **"Validated if" criteria** or criteria of a decision point: the checkboxes of the Review or Decision ticket.
- **Item removed from scope**: Canceled, or the project's "postponed" label and out of the project.

Then list the Linear changes.

## Prepare a review or a decision point

1. List the milestone's tickets (`list_issues`), with their state and estimate.
2. Take the project's hours of the step's period from the journal (below): from the step's start (the day after the previous Review is done, or the project's start) to today; ask the user when unclear.
3. Compute: points done, journal hours, hours per point, gap to the documented budget. Above 1.5 times the budget, say so; above 2 times, remind the user to shrink the scope or change the roadmap.
4. Prefill the Time section of the Review and the Data section of a Decision. Leave to the user the AI, difficulties, "validated if" and decision sections, with elements proposed from the tickets' comments.
5. If the decision changes the calendar or budgets, propose the documentation updates.

## Order the tickets

The Linear MCP cannot change the manual order. After a split, a replanning (tickets added, removed or reprioritised), or when the user asks, run (`<dev-kit>`: the `root` of `~/.dev-kit/config.json`; in Claude Code, the plugin's base directory `<dev-kit>/plugins/<plugin>` works too):

```bash
python3 "<dev-kit>/plugins/tracking-linear/scripts/linear_order.py" reorder <ID> <ID> [<ID> …]
```

It puts the tickets in this order at the first one's place; the team's other tickets do not move. It sets both manual orders Linear keeps; `--dry-run` changes nothing. It reads the user's personal key from `LINEAR_API_KEY`; without it, it prints where to create and set it: relay that to the user, and never ask for the key nor write it in a file or a command. Tell the user which tickets moved.

## Time from the work journal

The journal counts one entry per hour, tagged with its project. Run:

```bash
python3 "<dev-kit>/plugins/tracking-linear/scripts/journal_time.py" <journal folder> <project> --since <YYYY-MM-DD> [--until <YYYY-MM-DD>]
```

The journal folder is the dev-journal clone, next to dev-kit; the project is the journal entries' `--project` name. It prints the hours per category and lists the `❓` entries without counting them: the user says whether they count, and confirms or corrects the total before it goes in the Review.
