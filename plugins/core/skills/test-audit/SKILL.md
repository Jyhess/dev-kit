---
name: test-audit
description: Audit a project's whole existing test suite against its test rules (`docs/design/tests.md`) — tests through a slow dependency that re-test a lower layer, use it by convenience or hold logic that belongs elsewhere, duplicate checks, tests to merge, costly setups rebuilt several times, flat test folders — then propose a split of the fixes into tickets, created only with the user's agreement. Changes no file. Use when the user asks to audit, review or clean up a test suite ("audite les tests", "revue de la suite de tests").
---

# Audit a test suite

A one-off pass over a suite written before the project's test rules. The audit reads; it changes no file of the project. Its outputs are a list of findings and a proposed split into tickets.

## Before starting

1. Read the rules: the project's `docs/design/tests.md`; when it has none, the copy in the dev-kit clone, `<dev-kit>/plugins/core/templates/design/tests.md` (`<dev-kit>` is the `root` of `~/.dev-kit/config.json`; in Claude Code, the plugin's base directory `<dev-kit>/plugins/core` works too), and say that the project lacks it.
2. Read the project's `AGENTS.md`: its test commands, its tracker ("Documentation and tracking"), its layout.
3. Map the layers: list the slow dependencies the project uses (engine, UI framework, browser, database, network, cloud, external process), the pure modules, the adapters, and the test folders with the layer each one exercises. A large suite is read folder by folder, in subagents when available, each returning its findings in the format below, not the files.

## What to look for

For each test file, against the layer map:

| Kind | Finding |
|---|---|
| Re-test | A test through a slow dependency checks a result a lower layer already checks, or could check. |
| Convenience | A test starts a slow dependency it does not need: the code under test runs without it. |
| Misplaced logic | Business logic is tested through a slow dependency because it lives in an adapter or a UI script instead of a pure module; or an adapter holds logic it should not. The fix moves the code, then the test. |
| Missing layer suite | A layer has no suite of its own, or is validated only through the layers above it. |
| Duplicate | The same check appears in several tests or several layers; it stays once, in the lowest layer that can make it. |
| Merge | Several tests build the same setup and each read part of it; they become one test, or share one setup. |
| Costly setup | A scene, a database, a browser page or a process is built again for each test that reads it, where one build would serve them all. |
| Flat tree | A test folder mixes layers, or the tree does not mirror the layers. |

Measure what helps rank, in one run of the suite whose report is written outside the project (a temporary folder):

- the time per test, with the framework's per-test durations or its machine-readable report (`pytest --durations=0`, `python -m unittest --durations=0` from Python 3.12, `go test -json`, a JUnit XML or JSON reporter for Jest, Vitest or GUT); read only the slowest ones, sorted with a short script;
- the time per folder, summed from it, or from the summary when the framework gives no per-test time;
- the number of slow setups per file.

The slowest tests (the 20 slowest, or those over 1 s) are each read: each one gets a finding of the table, or the reason it is slow by necessity.

Only the suite is judged: a code defect seen in passing goes to a separate "Out of scope" list.

## Report the findings

One line per finding, grouped by kind, most costly first:

```markdown
- `tests/ui/test_board.gd:42` `test_score_after_merge` — Re-test: checks the merge score through the scene; `tests/core/test_merge.gd` already does. Fix: remove.
```

Each line gives the place (file and line or test name), the kind, why, and the fix (remove, move to a layer, merge with, build once, move the logic to a module, split the folder). End with the slowest tests (name, time, finding or reason), the time per folder, the count per kind and the out-of-scope list.

## Propose the tickets

Group the fixes into tickets so that each runs in one session and leaves the suite green:

- One ticket per area of the code or test folder, with all its kinds of fixes together (removal, merge, shared setup), rather than one ticket per finding or per kind.
- Moving logic out of an adapter is its own ticket when it changes production code, before the tickets that move its tests.
- Restructuring a flat tree comes first when the other tickets would move files into the new tree; otherwise last.
- Each ticket lists its findings (the report lines), its order and dependencies, and is done when the suite passes and its findings are gone.

Present the split (titles, content, order) and wait for the user's agreement. Then create the tickets in the project's tracker with its tracking skill (`tracking-linear:linear`, `tracking-github-issues:github-issues`), in order, and give the list of links. Without agreement, nothing is created.
