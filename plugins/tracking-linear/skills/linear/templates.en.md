# Ticket templates (English)

One template per type. Tickets of a project whose documentation is in English use these templates.

## Implementation

```markdown
## Context
Why this ticket, and the documentation page concerned.

## Expected behaviour
What the user sees or does, in a few lines.

## Business acceptance criteria
- Given …, when …, then …
- [manual] Criterion judged by using the product (feel, readability, fun).

## Technical acceptance criteria
- Architecture constraints: where the code goes, what is reused, what is forbidden.
- End-to-end tests for each automatable business criterion.
- Performance on the reference machine, if relevant.
- Build without warnings.

## Out of scope
What another ticket will do.

## Implementation notes
Leads, files concerned, open questions.
```

## Feature (parent)

```markdown
## Context

## Business acceptance criteria
- Given …, when …, then …

## Sub-tickets
The Implementation tickets it is made of.
```

## Bug

```markdown
## Steps to reproduce
1. …

## Observed behaviour

## Expected behaviour

## Fixed when
- An end-to-end test reproduces the bug, then passes after the fix.
```

## Improvement

```markdown
## Context

## Change
What changes, without changing the business behaviour.

## Technical acceptance criteria
- …
- The existing tests pass unchanged.
```

## Investigation

```markdown
## Question

## Leads

## Time box
N points. Beyond it, take the best option found.

## Deliverable
Documented choice, throwaway prototype…
```

## Task and Validation

```markdown
## Context

## To do
- [ ] …

## Done when
```

For a Validation, "To do" says what is tested and with whom, and a `## Feedback` section collects the feedback.

## Review

```markdown
## Time
- Budget:
- Journal hours for the period:
- Points done:

## What the AI did well

## What the AI did badly

## Difficulties

## Step validation
- [ ] "Validated if" criteria of the step, copied from the documentation.

## Decisions and adjustments

## Glossary report
- Forbidden synonyms and unused terms (proposed for removal): output of `python3 <dev-kit>/plugins/core/scripts/vocabulary_check.py` run in the project.
- Missing terms: domain notions used in the code and docs but absent from the glossary, each with its full proposed entry.
```

`<dev-kit>` is the dev-kit clone, the `root` of `~/.dev-kit/config.json` (in Claude Code, the plugin's base directory `<dev-kit>/plugins/<plugin>` works too).

## Decision

```markdown
## Criteria
- [ ] Criteria of the decision point, copied from the documentation.

## Data

## Decision

## Next steps
```
