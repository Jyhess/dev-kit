# Auto-merge of low-risk pull requests

The user reviews every pull request, which makes them the bottleneck. The workflow `.github/workflows/auto-merge.yml` merges by itself the pull requests that cannot weaken the tests or rewrite the documentation and ask nothing of the user, and labels the others by what they ask: `to test`, `to acknowledge` or `to review`.

## What it does

On every non-draft pull request opened, reopened, updated, marked ready or edited, and whenever its `Verify` workflow completes, the script `.github/scripts/auto_merge.py` reads the diff and the description:

- the description fails the PR description check (`docs/pr-description.md`) → nothing is done: the `PR description` check is red, and editing the description runs the decision again;
- the repository owner opened it from a branch of the repository itself, every changed file passes and the description sets no label → rebase merge once `Verify` has passed on the head commit, then the branch is deleted;
- otherwise → the labels below (created if missing), reasons listed in the job summary.

When the repository has a `.github/workflows/verify.yml` (dev-kit's runs the pre-push checks on Linux), the merge waits for it:

- no run yet, or still running → nothing is done; the completion of `Verify` runs the workflow again (`workflow_run` trigger);
- the latest run of the head commit passed (every job) → merge;
- it failed or was cancelled → not merged and not labelled: the red check shows on the pull request, and the next push (or a re-run of the failed jobs) runs `Verify` and the decision again.

Without `verify.yml`, the merge trusts the local checks: the pre-push hook and the test results in the pull request description.

Agents open every pull request as a draft (`AGENTS.md`, Git). GitHub refuses to merge a draft and the workflow skips it, so marking it ready, which only the user does, is the go: the workflow then decides as above.

A pull request that already carries `to test`, `to acknowledge` or `to review` is never merged by the workflow: add one to hold it. The label `no ticket` (a `No ticket: <reason>` description) is informational and does not hold the merge.

## Rules

| Change | Decision |
|---|---|
| Pull request opened by anyone but the repository owner, or from a fork | `to review` |
| Source file added or changed | passes |
| Test file or `.md`: lines added | passes |
| Test file or `.md`: a whole comment line replaced by whole comment lines (`#`, `//`, `///`, lines of `/* */`; `<!-- -->` in Markdown, where `#` is a heading) | passes |
| Test file or `.md`: any other line removed or changed (end-of-line comments do not count) | `to review` |
| Existing test file: an added line that switches a test off (`@unittest.skip`, `unittest.skip(`, `skipTest(`, `SkipTest`, `pytest.skip`, `pytest.mark.skip`, `[Ignore]`, `Skip =`, `@Disabled`, `@Ignore`, `#[ignore]`, `it.skip`/`test.skip`/`describe.skip`, `xit(`/`xdescribe(`, or a bare `return`, which the diff, without context, cannot tell from the first statement of a test) | `to review` |
| Any deleted file, or a renamed one (seen as deleted and added) | `to review` |
| Anything under `.github/` or `.githooks/` (workflow, script, configuration `.github/auto-merge.json`) | `to review` |
| Any `AGENTS.md` or `CLAUDE.md` | `to review` |
| Agent instructions or configuration: any `SKILL.md`, `hooks/hooks.json`, `.claude/settings*.json`, or file under a `.claude-plugin/` folder, even added | `to review` |
| Description with an `## Architecture changes` section | `to review` |
| Structural change in the diff (`docs/pr-description.md`) | `to review` when declared; not declared, the description fails |
| Description with a `## Manual checks` section or a `[manual]` / `[manuel]` marker | `to test` |
| Description with a `## Values to validate`, `## Assumptions` or `## Known limitations` section | `to acknowledge` |

`to test` asks the user to run the product, `to acknowledge` to confirm something without running it, `to review` to read the change carefully; a pull request can carry several.

Test files: a path under a `tests/` folder, or a file named `test_*`, `*_test.*`, `*Test.cs`, `*Tests.cs`, `*.spec.*`. A project adds its own patterns in `.github/auto-merge.json`:

```json
{"test_patterns": ["e2e/", "*.feature", "src/fixtures/*.json"]}
```

A pattern ending in `/` is a folder name anywhere in the path, a pattern with a `/` is matched against the whole path, any other against the file name.

## Why this design

- **No approval, no native auto-merge.** The repositories are private on GitHub Free: no branch protection, rulesets or auto-merge. The workflow merges with the GitHub token instead.
- **`pull_request_target`.** The workflow, script and configuration come from the default branch, so a pull request cannot loosen the check that judges it. The pull request's code is diffed, never checked out or run.
- **Waiting through `workflow_run`, not polling.** The decision job ends as soon as it has nothing to do and runs again when `Verify` completes, so it uses no runner time while the `Verify` jobs queue. `workflow_run` also runs the default branch's workflow and script, so the second decision is as safe as the first. The decision reads the runs of `.github/workflows/verify.yml` (a workflow named `Verify`, as in the `project-init` template) for the pull request's head commit.
- **Owner's pull requests only.** On a public repository anyone can open a pull request, and the job holds a write token: a stranger's change to a script would otherwise be merged and then run on the user's machines (dev-kit's clone is fast-forwarded at each session start). The author (`user.login`) and head repository (`head.repo.full_name`) are in the pull request object of both triggers. A fork's `Verify` run lists no pull request, so a fork is judged only on `pull_request_target`.
- **A merge made with `GITHUB_TOKEN` starts no workflow.** GitHub does not run workflows for events caused by that token, so `verify` on `push: main` does not run after an auto-merge: the `Verify` run of the pull request's head commit is the only check of what lands. A GitHub App or a personal token would trigger them; not used.

## Installation

`core:project-init` copies the workflow and the scripts `auto_merge.py`, `pr_description.py` and `structure.py` (which it imports) into a project (answer `auto_merge`); with the answer `ci` it also writes the `verify.yml` the merge waits for, the PR template and its check. The templates are under `plugins/core/templates/` (`github-workflows/`, `github-scripts/`); dev-kit's own copies must stay identical to them (checked by `tests/test_auto_merge.py`). The repository must allow rebase merging (Settings > General > Pull Requests, on by default). The workflow acts from the first pull request opened after it reaches the default branch.
