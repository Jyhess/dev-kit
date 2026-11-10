---
name: clarify
description: Question the user in rounds about a project, a feature, a ticket, a plan or an idea until no doubt, ambiguity or inconsistency is left, at three successive levels (goal, business, implementation), and actively hunt for contradictions with what was said, written or built before. Use before designing, splitting or implementing anything non-trivial, or when the user asks to "cadrer", "challenger", "cuisiner", "griller", stress-test or clarify a subject.
---

# Clarify a subject

Before designing, splitting or implementing, question the user until nothing is left unclear, unsaid or contradictory. The subject is given as an argument (ticket, page, feature, idea); without one, ask for it.

## Three levels, in order

1. **Goal**: why we do it, for whom, and how we know it succeeded.
2. **Business**: what the user of the product sees and does, as verifiable criteria.
3. **Implementation**: how we build it.

Move to the next level only when the current one has no open question, no unresolved inconsistency, and its summary is validated by the user. If an answer calls a validated level into question, say so and go back to that level instead of working around it.

## Rounds

Map the subject as a **decision tree**: each decision opens the decisions that depend on it. The **frontier** is every decision whose prerequisites are settled, the questions that can be asked now without guessing at answers not heard yet.

Each round asks the whole frontier at once, in one inline HTML form (`show_widget`): every question stacked, each with its choices (single choice, multiple choice or free text) and a free-text field for another answer, and one submit button that sends every answer in one message (`sendPrompt`), each prefixed by its question's header. Without that tool, use the agent's interactive question tool (at most four questions per call: split the frontier into consecutive calls, inconsistencies first); without either, show concise numbered options in chat and wait for the user's reply:

- Inconsistencies come first, one question each: the two statements and their sources in the question, the proposed resolution as the first option.
- Each question has a short header, two to four options, and the recommended option first, labelled "(Recommandé)", with its reason in one line in its description. The user can always type another answer.
- Before the form, give in one or two lines of text the context the options do not carry (facts looked up, what the round decides).
- A question that depends on another question of the same round waits for the next round.

After each round's answers, recompute the frontier and ask the next round. Open questions that need a long written answer (a goal statement, an example) may still be asked in text.

## Facts are mine, decisions are the user's

- **Read before asking**: the project's `AGENTS.md`, its docs or wiki, its tickets, and at level 3 its code. Ask only what these sources do not answer, and cite the source when an answer comes from them.
- When a question needs a fact (a file, a value, a behaviour of the code), look it up, with a sub-agent if the search is long. Only the questions downstream of a running search wait for it; ask the rest of the frontier now.
- Never decide in the user's place: put each decision to them, with a recommendation.

## Hunting inconsistencies

At every round, before writing the questions, check the new answers against:

- **each other**: two answers of the same round that cannot both hold;
- **earlier answers and validated levels**: a business rule that defeats the goal, an implementation choice that breaks a business criterion;
- **the written sources**: docs, wiki, specs, tickets, `AGENTS.md` / `CLAUDE.md`, decision history;
- **the code**: an assumed behaviour that the code does not have, an existing mechanism that already does it differently;
- **the vocabulary**: one word for two notions, two words for one notion, a word used elsewhere with another meaning; when the project has a glossary named in the "Vocabulary" section of `AGENTS.md` or `CLAUDE.md`, every domain term missing from it and every forbidden synonym it lists;
- **the numbers**: budgets, thresholds, sizes or durations that do not add up (a 2-day task inside a 1-day budget, a limit lower than the expected volume).

Each inconsistency goes in the "Incohérences" block at the top of the next round, with both sources and a proposed resolution. It blocks its level's gate until the user settles it. Never resolve one silently, even when the answer seems obvious.

## Questioning rules

- **Refuse vagueness**: follow up on "à peu près", "assez", "rapide", "ça dépend", "on verra" until getting a value, a threshold, an example, or the explicit decision to postpone.
- **"Je ne sais pas" is an answer**: record it as a hypothesis with what will confirm it, or as an investigation (question, time box, deliverable).
- **Keep the doubt register** and show it at each gate, and every three rounds or so.

```markdown
### Registre — <subject>, level <n>
**Décidé**
- <decision> (reason)
**Hypothèses**
- <hypothesis> — confirmed by: <measure, test, user session>
**Incohérences ouvertes**
- <I…>
**Ouvert**
- <question>
**Reporté**
- <topic> → <ticket, later step>
```

## Level contents

**Goal** — the problem and for whom; the measure and threshold that prove success; what happens if we do not do it and the minimal version that would suffice; what is explicitly out of scope; the time budget.
Gate: a goal in two or three sentences, at least one measurable success criterion, an out of scope and a budget.

**Business** — what the user sees, does and feels, starting from a concrete situation; nominal cases, then edge cases (extreme values, concurrency, network, invalid input), then failure cases; values and tolerances; what can only be judged by hand, and by whom; what belongs to another ticket or step.
Gate: each expected behaviour is a "Étant donné / quand / alors" criterion with verifiable values, or is marked `[manuel]`.

**Implementation** — what already exists and is reused, where the code goes, what is forbidden by the architecture; technical decisions (alternatives, criterion, choice); unknowns that prevent estimating, each turned into an investigation; one end-to-end test per automatable business criterion and the first test that must fail; performance if it matters; the split into tickets (one ticket = one PR) with estimates and dependencies.
Gate: each automatable business criterion has its planned test, each ticket has its type, estimate and dependencies, and the architecture changes are approved.

**Architecture changes** — a new component, a changed responsibility, a new dependency or interface between components, or a changed architecture rule. The level's summary lists them in a "Changements d'architecture" block, and one question asks the user to approve them; for each, propose where it goes in the project's architecture documentation. With none, the summary says so in one line and no question is asked. Approved changes go into the ticket. On a refusal, stop clarifying and discuss that architecture point with the user until they restart clarify.

Adapt the depth to the subject: a whole project or step goes through the three levels; a ticket mostly checks its link to the goal at level 1, then levels 2 and 3; a free idea stops at level 1 if it is postponed.

## Writing the result

Nothing stays only in the conversation. At each gate, present the level's summary, wait for the user's agreement, then write it where the project keeps such things: the project's `AGENTS.md` names its documentation (wiki or `docs/`) and its tracking tool (Linear, GitHub issues…) and the skills that go with them. If no `AGENTS.md` exists, use `CLAUDE.md`; if neither names a location, ask where to write.

A ticket's business and technical choices go into the ticket. The documentation only gets what changes a step's goal or acceptance criteria, or spans several steps; the glossary still gets every new term.

When the project has a glossary, each gate also lists the domain terms decided during the level and missing from it, each as a full entry (French, English, displayed terms when they differ, definition, forbidden synonyms); with the user's agreement, add them to the glossary along with the summary.

At the end, give the links of the pages and tickets written, the hypotheses still to confirm, and the next step (splitting into tickets, or implementation).
