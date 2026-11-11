# PR description check

Every pull request, opened by Claude, Codex or by hand, follows `.github/pull_request_template.md`. The workflow `.github/workflows/pr-description.yml` (`PR description`) checks it, with the structural changes of the diff, on every non-draft pull request opened, edited or updated, and turns red when it fails; the auto-merge workflow (`docs/auto-merge.md`) runs the same check and never merges a pull request whose description fails. The check reads the form, not whether the content is true.

## Rules

Once the `<!-- -->` comments are removed (the template's guidance lives in them):

| Part | Rule |
|---|---|
| Ticket | `Fixes #12`, `Closes ABC-12`, `Refs owner/repo#12`, an issue URL…, or `No ticket: <reason>` (two words at least; label `no ticket`, informational) |
| `## What was done` | required, not empty, not N/A |
| `## Test results` | required, not empty; `N/A: <reason>` allowed (two words at least) |
| `## Manual checks` | optional, label `to test` |
| `## Values to validate`, `## Assumptions`, `## Known limitations` | optional, label `to acknowledge` |
| `## Architecture changes` | optional, label `to review`; required when the diff has a structural change (below) |
| Placeholders | outside code, a line made only of `TODO`, `TBD`, `...` or `…`, or `<n>`, `<ID>`, `<…>`, `<reason>` fails |

An optional section that does not apply is deleted, heading included: present, it must have content (not N/A). A `[manual]` / `[manuel]` marker anywhere outside code also gives `to test`. Headings are in English in every project, case-insensitive; other sections are free. Headings inside code fences do not count.

## Structural changes

The AI works inside the existing architecture; a change of that architecture is approved by the user, never introduced silently. `.github/scripts/structure.py` finds in the diff (since the merge base) the structural changes:

| Signal | Files |
|---|---|
| Architecture file changed | `docs/architecture.*`, `*ArchitectureTest*`, `.importlinter`, `.dependency-cruiser.*`, `.github/scripts/architecture.py` (`docs/architecture-rules.md`), plus `architecture_patterns` |
| Manifest added, removed or changed | `*.csproj`, `*.sln`, `package.json`, `pyproject.toml`, `requirements*.txt`, `Cargo.toml`, `go.mod`, `project.godot`, `*.gemspec`, `Gemfile`, plus `manifest_patterns`; lock files do not count. A changed `*.csproj`, `package.json`, `pyproject.toml`, `requirements*.txt` or `project.godot` counts only when its dependencies change, listed in the signal: `.csproj` SDKs (version included), target frameworks, package, project, assembly and framework references; `package.json` dependency sections and workspaces; `pyproject.toml` project, optional, group, build and Poetry dependencies; requirement names and option lines; `project.godot` `config_version`, engine features, .NET assembly name, autoloads and enabled editor plugins (main scene, input actions, layer names and engine settings do not count). Versions of a dependency, comments, properties and build targets do not count; a manifest that cannot be read counts |
| Top-level folder added or removed | hidden folders included |
| Public interface changed or removed | C#: a `public interface` whose header or a member is changed or removed, or the interface removed or renamed; added members and interfaces, comments, formatting and moves between files do not count. Python: a top-level function, class, constant or re-exported name (`from a import x [as y]`, whatever `a` is) that another non-test file imports, whose signature, bases, decorators or public method changes (a constant's value does not count; a re-export counts by its name only, a switch between definition and re-export is a change), or which is removed, renamed or moved to another module; additions, bodies, comments, docstrings and formatting do not count. Rust: a `pub trait` under a `src/` folder, named `crate::module::Name` (crate = folder holding `src/`, module = path under it), whose header or a member signature changes, or which is removed, renamed or moved to another module; additions, default method bodies, comments and formatting do not count. Kotlin (`.kt`): a public `interface`, `fun interface` or `sealed interface`, by the C# rules, except that, unlike C#, a member's body (`{…}`, `= expr`, getter) and private members do not count, and string literals do (a changed `@GET("…")` URL counts) |

Without an `## Architecture changes` section, the check fails and lists the signals; with it, each signal is a `to review` reason and the pull request is never auto-merged. The section's presence is enough. A new component folder deeper than the top level, or a new dependency between components, shows through the architecture file once the project has one. A `public interface` nested in a non-public type, or a `pub trait` in a private module, still counts; Rust `pub use` re-exports, macro-generated traits and `#[path]` are ignored. A Python import resolves to every file of that module name, in any folder; dynamic imports (`importlib`, `__import__`) are not seen, nor class attribute order, default presence, `self.x` attributes set in methods, nested classes, re-exported modules (`import a`, `from . import a`) or star re-exports (`from a import *`). A project extends the patterns in `.github/auto-merge.json`, with the syntax of `test_patterns` (`docs/auto-merge.md`); dev-kit adds `.claude-plugin/marketplace.json`, its list of plugins:

```json
{"architecture_patterns": ["docs/components.yml"], "manifest_patterns": ["deps.edn"]}
```

Check a description before opening the pull request (`--base` also reads the structural changes of `HEAD`):

```bash
python3 .github/scripts/pr_description.py body.md --base origin/main
```

## Why this design

- **One template, one check, for every author.** The tracking skills and the AGENTS templates point to the template; the CI catches a pull request that skipped it, whoever opened it.
- **`pull_request`, not `pull_request_target`.** The check runs on the pull request that introduces or changes it. A pull request could weaken its own check, but it touches `.github/` and goes to review, and auto-merge judges with the default branch's copy of `pr_description.py`.
- **Optional sections are deleted, not N/A.** Their presence sets the labels, so a `## Values to validate: N/A` would send every pull request to the user.
- **Signals from paths, interfaces from content.** File names and folders are the same in every language. A manifest also holds build settings (a `.csproj` holds MSBuild targets), so the common ones are read for their dependency names only: a parser per format (`DEPENDENCY_EXTRACTORS`, `xml`, `json`, `tomllib`), the others count on any change. Only interfaces need the content: one extractor per language (`INTERFACE_EXTRACTORS`), fed with every non-test file of its extension at the merge base and at head, since a Python interface is defined by its importers in other files; interfaces are compared by qualified name so that formatting is no change (in Rust the module path is part of the name, so a move to another module is a removal); no compiler (Roslyn would need .NET in CI), Python's own `ast` where the language ships one.
- **Red, not blocking.** GitHub Free has no branch protection: the red check shows the problem and stops auto-merge; a manual merge stays possible.

## Installation

`core:project-init` copies the template, the workflow and the scripts `pr_description.py` and `structure.py` with the answer `ci`; the answer `auto_merge` also copies both scripts, which `auto_merge.py` imports. The templates are `plugins/core/templates/pull_request_template.md`, `github-workflows/pr-description.yml`, `github-scripts/pr_description.py` and `github-scripts/structure.py`; dev-kit's own copies must stay identical (checked by `tests/test_auto_merge.py`).
