#!/usr/bin/env python3
"""Set up a new project or equip an existing one, from the answers of /core:project-init.

    python3 init_project.py <project dir> <answers.json>            # list the changes
    python3 init_project.py <project dir> <answers.json> --apply    # make them

Existing files are completed, never overwritten: missing AGENTS.md sections
are appended, CLAUDE.md imports AGENTS.md, missing design principle pages
(docs/design/, which AGENTS.md points to) are created, missing .gitignore / .gitattributes
lines are added (Python entries when there is a pyproject.toml), enabledPlugins keys are merged (the desktop app's
anthropic-skills plugin is disabled unless the project already sets it), and the
unused tools of DENIED_TOOLS are added to permissions.deny, REQUIRED_TOOLS removed from it, ALLOWED_TOOLS added to permissions.allow. The claude.ai
connectors of the local ~/.dev-kit/config.json ({"connectors": {name: "mcp__<id>"}};
their ids belong to the account, not to dev-kit) are denied in the unversioned
.claude/settings.local.json of the main clone, which Claude Code also reads from worktrees;
run from a worktree, the work journal and a glossary outside the repository also use the main clone. Created Git
hooks are added to the index as executable, since chmod does nothing on Windows. A second
run with the same answers changes nothing.

Once the GitHub repository exists, the script turns on its automatic deletion of
merged head branches and, for GitHub issues tracking, creates the ready label
(Definition of Ready): run it again after `gh repo create`.

Answers (JSON): name, purpose, audience, stack (strings); docs ("wiki-github",
"docs-folder" or "none"); tracking ("linear", "github-issues" or "none");
languages ({"chat", "docs", "code", "wiki"}: "fr" or "en", defaults fr/en/en/fr;
AGENTS.md and CLAUDE.md are in English whatever they say);
commands ({label: command}); verify (command run before each push and in CI, or null);
ci (bool, needs verify: the Verify workflow, the PR template and its check);
auto_merge (bool: copy the workflow that merges low-risk pull requests by itself,
see dev-kit's docs/auto-merge.md); glossary (path relative to the project, default docs/glossary.md, or ../<name>-wiki/Glossaire.md for a wiki, Glossary.md when the
wiki is in English; null for a project without domain vocabulary: no glossary and no Vocabulary section); glossary_entries (list of {fr, en, ui_fr, ui_en, definition,
synonyms}, written only when the glossary is created); design (bool, default true; false for a
repository without code, such as a wiki: no Design section and no docs/design/ pages); keep_tools (DENIED_TOOLS
entries or connector names the project uses and keeps, e.g. ["mcp__Claude_Browser"];
the "linear" connector is kept when tracking is "linear"); architecture ({"stack": "dotnet", "rust", "kotlin", "python" or "js", inferred
from *.csproj, a Cargo workspace, a Gradle build, pyproject.toml, or package.json / JS-TS sources when absent, and the stack's
fields}: the architecture file,
.github/scripts/architecture.py appended to verify, the Architecture section of AGENTS.md;
a note and none of them when the stack's project or package is not found).
- dotnet: {"project": test csproj, "main": main csproj, default project,
  "folder": folder of ArchitectureTest.cs, default the test csproj's}: docs/architecture.puml
  and ArchitectureTest.cs for the test framework of TEST_FRAMEWORKS.
- python: {"roots": root packages, default every package of src/ or of the top ("root": one package),
  "runner": prefix running the project environment, default from uv.lock or poetry.lock}:
  .importlinter, whose `allowed` contracts the script writes after apply (see the note);
  existing import-linter contracts are kept and nothing is set up.
- rust: {"exclude": crates that are not components, e.g. xtask}: for a
  Cargo workspace only, docs/architecture.puml, whose crates and arrows the script writes
  after apply (see the note); a diagram of another stack is kept and nothing is set up.
- kotlin: {"module": Gradle module folder, default the only one with Kotlin or Java sources
  under src/main ("." for the root project; several: a note, one module covered), "root": root package, default the
  common package of those sources, "folder": test sources folder of the module, default src/test/kotlin or
  src/test/java}: docs/architecture.puml, ArchitectureTest.kt for the JUnit version of the build file, ArchUnit
  as a test dependency and the diagram as a test input in the module's build file; a diagram of another stack
  is kept and nothing is set up.
- js: {"roots": folders whose sub-folders are the components, "." for the
  repository, default those of JS_ROOTS holding sources, else "."; "exclude": folders not
  checked}: for a package.json at the root, or JS/TS sources and no package.json at all,
  docs/architecture.json, .dependency-cruiser.cjs, a minimal package.json when there is
  none, node_modules/ in .gitignore and `npm ci` before the verification in verify.yml; the
  script writes the components after apply (see the note). package.json files only in
  sub-folders (a monorepo), an architecture file of another stack or an existing
  dependency-cruiser configuration: a note and nothing set up.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Callable

PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATES = PLUGIN / "templates"
# Past texts of the template sections now in plugins/core/rules/shared-rules.md, ${placeholders} kept, and of the
# generic Communication bullets, from the history of AGENTS.md, AGENTS.en/fr.md and CLAUDE.en/fr.md (frozen data).
SHARED_HISTORY = Path(__file__).resolve().parent / "shared_rules_history.json"
MARKETPLACE_FILE = PLUGIN.parents[1] / ".claude-plugin" / "marketplace.json"
MARKETPLACE = "jyhess"
sys.path.insert(0, str(PLUGIN.parent / "dev-journal" / "scripts"))
import dev_journal  # noqa: E402
import git_paths  # noqa: E402

DEFAULT_LANGUAGES = {"chat": "fr", "docs": "en", "code": "en", "wiki": "fr"}
DOCS_PLUGINS = {"wiki-github": "docs-wiki-github", "docs-folder": "docs-folder"}
TRACKING_PLUGINS = {"linear": "tracking-linear", "github-issues": "tracking-github-issues"}
# Plugins switched off in coding projects, unless the project already sets them: the
# desktop app's anthropic-skills (docx, pptx, xlsx, pdf…) costs ~1.7k tokens of skills
# listing per session and is not used there (dev-kit#33).
DISABLED_PLUGINS = ("anthropic-skills@inline",)
# Tools and connectors denied by default: a bare name or an MCP server prefix in
# permissions.deny removes the definition from every request, not only the call
# (dev-kit#32, docs/token-usage.md). Connectors come from LOCAL_CONFIG instead.
DENIED_TOOLS = {
    "Artifact": "Artifact pages (9.4k tokens)",
    "mcp__Claude_Browser": "built-in browser (5.6k)",
    "Workflow": "multi-agent workflows",
    "ScheduleWakeup": "/loop pacing",
    "SuggestPluginInstall": "plugin suggestions",
    "SuggestSkills": "skill suggestions",
    "SearchPlugins": "plugin catalog search",
    "SendUserFile": "file cards",
    "mcp__claude-in-chrome": "Claude in Chrome",
}
# Tools the shared rules need (the `ask` form): removed from a project's permissions.deny.
REQUIRED_TOOLS = ("mcp__visualize",)
# Tool calls the shared rules make without the user's approval, added to permissions.allow:
# the PR's auto-fix, which the auto mode classifier refuses otherwise.
ALLOWED_TOOLS = ("mcp__ccd_pr__set_monitor",)
# Machine-local configuration, outside every repository: {"connectors": {name: "mcp__<id>"}}.
LOCAL_CONFIG = Path.home() / ".dev-kit" / "config.json"
LINEAR_CONNECTOR = "linear"  # connector name kept for projects tracked in Linear

# AGENTS.md and CLAUDE.md are in English whatever the documentation language: shorter, and one template
# to keep within its budget.
LANGUAGE_NAMES = {"fr": "French", "en": "English"}
INSTRUCTIONS = {
    "wiki_line": "\n- The wiki is in {wiki}.",
    "docs": {"wiki-github": "Documentation lives in the project's GitHub wiki repository.",
             "docs-folder": "Documentation lives in `docs/`; no wiki. Before committing, check `docs/update-table.md`.",
             "none": "No documentation beyond the README."},
    "tracking": {"linear": "Tasks are tracked in Linear (team and labels: to be completed).",
                 "github-issues": "Tasks are GitHub issues of this repository.",
                 "none": "No task tracker."},
    "no_commands": "- (to be completed)",
    "verification": ("- The pre-push hook (`.githooks/`) runs `{verify}`; never bypass it.\n"
                     "- When it fails, squash each fix into the commit it corrects: `git commit --fixup <sha>`, then "
                     "`git -c sequence.editor=: rebase -i --autosquash --autostash origin/<default branch>`."),
    "no_verification": "- (to be completed)",
    "architecture": {
        "dotnet": ("- Components and their allowed dependencies: `docs/architecture.puml`, checked by `{test}` "
                   "(ArchUnitNET, with the tests) and by `.github/scripts/architecture.py` (every namespace "
                   "declared). Run both to check a change."),
        "python": ("- Components (the `__init__` and the children of {packages}) and those each may import: the `allowed` "
                   "contracts of `.importlinter`, checked by `{check}` (every component declared, then "
                   "import-linter); `{check} --write` rewrites them from the code."),
        "rust": ("- Components (the crates of the Cargo workspace) and their allowed dependencies: "
                 "`docs/architecture.puml`; a `<<restricted>>` crate may depend only on the external crates drawn. "
                 "Checked by `{check}`; `{check} --write` rewrites crates and arrows from the code."),
        "kotlin": ("- Components (each package right under `{root}`) and their allowed dependencies: "
                   "`docs/architecture.puml`, checked by `{test}` (ArchUnit, with the unit tests: `{gradle_test}`) and "
                   "by `.github/scripts/architecture.py` (every package declared). Run both to check a change. Rewrite "
                   "them from the code: `{check} --write` (components), then `ARCHITECTURE_DIAGRAM=write "
                   "{gradle_test}` (arrows).\n"
                   "- Declare dependencies in the version catalog `gradle/libs.versions.toml`, not as coordinates in "
                   "the build files."),
        "js": ("- Components (each folder right under a root) and those each may import: `docs/architecture.json`, "
               "checked with dependency-cruiser by `{check}`; `{check} --write` rewrites it from the code."),
    },
    "architecture_cycles": ("- The allowed dependencies form no cycle between components: `.github/scripts/architecture.py` "
                            "fails on one that its architecture file does not admit as an `allowed cycle`."),
}
# The glossary keeps the language of the documentation (or of the wiki).
GLOSSARY_HEADINGS = {
    "en": ("Glossary", ["French", "English (code)", "Displayed (FR)", "Displayed (EN)", "Definition",
                        "Forbidden synonyms"]),
    "fr": ("Glossaire", ["Français", "Anglais (code)", "Affiché (FR)", "Affiché (EN)", "Définition",
                         "Synonymes interdits"]),
}
GLOSSARY_FIELDS = ["fr", "en", "ui_fr", "ui_en", "definition", "synonyms"]
READY_LABELS = {"fr": ("Prêt", "Respecte la définition de prêt"), "en": ("ready", "Meets the Definition of Ready")}
READY_COLOR = "0e8a16"
# Shared design principles: a page of principles linking to one page per topic, read before designing.
PRINCIPLES_FOLDER = "docs/design"
PRINCIPLES_PAGES = ("principles.md", "errors.md", "robustness.md")


@dataclass
class Change:
    description: str
    apply: Callable[[], None]


def render(template: str, **values: str) -> str:
    return Template((TEMPLATES / template).read_text(encoding="utf-8")).substitute(values)


def write(path: Path, text: str) -> Callable[[], None]:
    def do() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return do


def languages(answers: dict) -> dict[str, str]:
    """The languages of the answers, completed with the defaults."""
    return {**DEFAULT_LANGUAGES, **answers.get("languages", {})}


def read_json(path: Path):
    """A JSON file, which a Windows editor may have saved with a byte order mark."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def instruction_values(answers: dict) -> dict[str, str]:
    langs = languages(answers)
    p = INSTRUCTIONS
    commands = answers.get("commands") or {}
    verify = verify_command(answers)
    return dict(
        name=answers["name"], purpose=answers.get("purpose", ""),
        audience=answers.get("audience", ""), stack=answers.get("stack", ""),
        chat=LANGUAGE_NAMES[langs["chat"]], docs=LANGUAGE_NAMES[langs["docs"]], code=LANGUAGE_NAMES[langs["code"]],
        wiki_line=p["wiki_line"].format(wiki=LANGUAGE_NAMES[langs["wiki"]])
        if answers.get("docs") == "wiki-github" else "",
        commands="\n".join(f"- `{cmd}` — {label}" for label, cmd in commands.items()) or p["no_commands"],
        docs_where=p["docs"][answers.get("docs", "none")],
        tracking_where=p["tracking"][answers.get("tracking", "none")],
        verification=p["verification"].format(verify=verify) if verify else p["no_verification"],
        glossary=glossary_path(answers),
        principles=f"{PRINCIPLES_FOLDER}/{PRINCIPLES_PAGES[0]}",
        architecture=p["architecture"][stack_name(architecture)].format(**vars(architecture), check=architecture.check,
                                                          packages=getattr(architecture, "packages", ""))
        + "\n" + p["architecture_cycles"] if (architecture := answers.get("architecture")) else "",
    )


def has_glossary(answers: dict) -> bool:
    """False when the answers say `"glossary": null`: a project without domain vocabulary."""
    return not ("glossary" in answers and answers["glossary"] is None)


def has_design(answers: dict) -> bool:
    """False when the answers say `"design": false`: a repository without code needs no design principles."""
    return answers.get("design", True) is not False


def agents_md(answers: dict) -> str:
    text = render("AGENTS.md", **instruction_values(answers))
    if not has_glossary(answers):
        text = re.sub(r"(?ms)^## Vocabulary\n.*?(?=^## |\Z)", "", text)
    if not has_design(answers):
        text = re.sub(r"(?ms)^## Design\n.*?(?=^## |\Z)", "", text)
    if not answers.get("architecture"):
        text = re.sub(r"(?ms)^## Architecture\n.*?(?=^## |\Z)", "", text)
    return text


def claude_md(answers: dict) -> str:
    return render("CLAUDE.md", **instruction_values(answers))


def glossary_language(answers: dict) -> str:
    langs = languages(answers)
    return langs["wiki"] if answers.get("docs") == "wiki-github" else langs["docs"]


def glossary_path(answers: dict) -> str:
    if answers.get("glossary"):
        return answers["glossary"]
    if answers.get("docs") == "wiki-github":
        return f"../{answers['name'].lower()}-wiki/{GLOSSARY_HEADINGS[glossary_language(answers)][0]}.md"
    return "docs/glossary.md"


def glossary(answers: dict) -> str:
    """The glossary page: a title and one table, sorted by the term in the glossary's language."""
    language = glossary_language(answers)
    title, headers = GLOSSARY_HEADINGS[language]

    def cells(entry: dict) -> list[str]:
        values = [", ".join(v) if isinstance(v, list) else str(v or "") for v in map(entry.get, GLOSSARY_FIELDS)]
        return [v.replace("|", "\\|") for v in values]

    entries = sorted(answers.get("glossary_entries") or [], key=lambda e: str(e.get(language, "")).casefold())
    rows = [headers, ["---"] * len(headers)] + [cells(e) for e in entries]
    return f"# {title}\n\n" + "".join("| " + " | ".join(row) + " |\n" for row in rows)


def plan_glossary(target: Path, answers: dict, main: Path) -> tuple[list[Change], list[str]]:
    """A glossary outside the repository (a wiki beside it) is found from the main clone `main`."""
    if not has_glossary(answers):
        return [], []
    relative = glossary_path(answers)
    path = target / relative
    outside = not path.resolve().is_relative_to(target)
    if outside:
        path = main / relative
    if path.exists():
        return [], []
    if outside and not path.parent.exists():
        return [], [f"{path.parent} does not exist (wiki not cloned?): glossary {relative} not created"]
    count = len(answers.get("glossary_entries") or [])
    notes = [f"add {path.name} to the wiki's Index page"] if answers.get("docs") == "wiki-github" else []
    return [Change(f"create the glossary {relative} ({count} term{'s' if count != 1 else ''})",
                   write(path, glossary(answers)))], notes


def sections(text: str) -> dict[str, str]:
    """Level-2 sections of a Markdown file: {lowercase title: section text}."""
    parts = re.split(r"(?m)^(?=## )", text)
    return {part.splitlines()[0][3:].strip().lower(): part for part in parts if part.startswith("## ")}


def normalized(section: str) -> str:
    return "\n".join(line.rstrip() for line in section.strip("\n").splitlines()) + "\n"


def is_past_version(text: str, versions: list[str]) -> bool:
    """True when the section is one of the versions, a `${placeholder}` matching any text within its line."""
    return any(re.fullmatch("[^\n]*".join(map(re.escape, re.split(r"\$\{\w+\}", version))), normalized(text))
               for version in versions)


def deviation(title: str, text: str, versions: list[str], values: dict[str, str]) -> str:
    """The section's diff against the closest past version, rendered with the project's answers."""
    rendered = [Template(version).safe_substitute(values) for version in versions]
    closest = max(rendered, key=lambda version: difflib.SequenceMatcher(None, version, normalized(text)).ratio())
    diff = difflib.unified_diff(closest.splitlines(), normalized(text).splitlines(), "shared rules", "AGENTS.md",
                                lineterm="", n=1)
    return f"AGENTS.md: section {title} kept as a local deviation from the shared rules, which it overrides:\n" + \
        "\n".join(diff)


def without_shared_copies(text: str, values: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """The text without the verbatim copies of past shared rules; what was removed; the deviations kept."""
    history = json.loads(SHARED_HISTORY.read_text(encoding="utf-8"))
    bullets = set(history["communication_bullets"])
    kept, removed, deviations, bullet_count = [], [], [], 0
    for part in re.split(r"(?m)^(?=## )", text):
        title = part.splitlines()[0][3:].strip() if part.startswith("## ") else ""
        versions = history["sections"].get(title.lower())
        if versions and is_past_version(part, versions):
            removed.append(title)
            continue
        if versions:
            deviations.append(deviation(title, part, versions, values))
        elif title.lower().startswith("communication"):
            lines = part.splitlines(keepends=True)
            part = "".join(line for line in lines if line.rstrip() not in bullets)
            bullet_count += len(lines) - len(part.splitlines())
        kept.append(part)
    if bullet_count:
        removed.append(f"{bullet_count} Communication bullet{'s' if bullet_count > 1 else ''}")
    return "".join(kept), removed, deviations


def plan_agents_md(target: Path, answers: dict) -> tuple[list[Change], list[str]]:
    """Create AGENTS.md, or complete it: verbatim copies of shared rules give way to the Shared rules section."""
    path = target / "AGENTS.md"
    wanted = agents_md(answers)
    if not path.exists():
        return [Change("create AGENTS.md", write(path, wanted))], []
    current = path.read_text(encoding="utf-8")
    remaining, removed, deviations = without_shared_copies(current, instruction_values(answers))
    existing = sections(remaining)
    missing = [(title, text) for title, text in sections(wanted).items() if title not in existing]
    if not missing and not removed:
        return [], deviations
    merged = remaining.rstrip("\n") + "\n" + "".join("\n" + text.rstrip("\n") + "\n" for _, text in missing)
    done = [f"remove the copies of the shared rules: {', '.join(removed)}"] if removed else []
    if missing:
        done.append(f"add the sections {', '.join(text.splitlines()[0][3:] for _, text in missing)}")
    return [Change(f"AGENTS.md: {'; '.join(done)} (other sections kept as they are)", write(path, merged))], deviations


def plan_principles(target: Path, answers: dict) -> list[Change]:
    """The shared design principles AGENTS.md points to; an existing page is the project's own and is kept."""
    if not has_design(answers):
        return []
    return [Change(f"create {PRINCIPLES_FOLDER}/{page}",
                   write(target / PRINCIPLES_FOLDER / page, (TEMPLATES / "design" / page).read_text(encoding="utf-8")))
            for page in PRINCIPLES_PAGES if not (target / PRINCIPLES_FOLDER / page).exists()]


def plan_claude_md(target: Path, answers: dict) -> list[Change]:
    path = target / "CLAUDE.md"
    wanted = claude_md(answers)
    if not path.exists():
        return [Change("create CLAUDE.md (imports AGENTS.md)", write(path, wanted))]
    current = path.read_text(encoding="utf-8")
    # The vocabulary hook injects a glossary index: a former import of the whole glossary goes.
    glossary_import = rf"(?m)^@{re.escape(glossary_path(answers))}[ \t]*(?:\r?\n|$)\n?"
    merged = re.sub(glossary_import, "", current)
    done = ["remove the glossary import (the vocabulary hook gives its index)"] if merged != current else []
    if not re.search(r"(?m)^@AGENTS\.md\s*$", merged):
        merged = "@AGENTS.md\n\n" + merged.lstrip("\n")
        done.insert(0, "import AGENTS.md")
    if not done:
        return []
    return [Change(f"CLAUDE.md: {', '.join(done)} (existing instructions kept as they are)", write(path, merged))]


def attribute_names(line: str) -> tuple[str, set[str]]:
    """A .gitattributes line's pattern and the names of the attributes it sets, unsets or unspecifies."""
    pattern, *attributes = line.split()
    return pattern, {attribute.lstrip("-!").split("=", 1)[0] for attribute in attributes}


def line_present(line: str, current: list[str], attributes: bool) -> bool:
    """Whether the file already has the line, or a line that decides it otherwise.

    Later lines win in .gitattributes and .gitignore, so an appended line would override the project's:
    an existing line of the same pattern that sets each of its attributes (`* text=auto eol=lf` for
    `* text=auto`, `* -text` too: the project's choice), or a .gitignore negation `!<line>`, counts.
    """
    if line in current:
        return True
    if not attributes:
        return "!" + line in current
    pattern, names = attribute_names(line)
    return any(not other.startswith("#") and attribute_names(other)[0] == pattern
               and names <= attribute_names(other)[1] for other in current if other)


def plan_lines(target: Path, filename: str, template: str, extra: str = "") -> list[Change]:
    """Create the file from its template and extra lines, or add the lines it lacks under their comments.

    Missing `*` catch-all lines go at the top: later lines win, so after specific patterns
    (`*.exe binary`) they would override them. The other lines are appended.
    """
    path = target / filename
    wanted = (TEMPLATES / template).read_text(encoding="utf-8") + extra
    if not path.exists():
        return [Change(f"create {filename}", write(path, wanted))]
    current = path.read_text(encoding="utf-8")
    have = [line.strip() for line in current.splitlines()]
    missing, top, lines, comment = [], [], [], None
    for line in wanted.splitlines():
        if line.startswith("#"):
            comment = line
        elif line.strip() and not line_present(line.strip(), have, filename == ".gitattributes"):
            block = top if line.split()[0] == "*" else lines
            if comment and comment not in block:
                block.append(comment)
            missing.append(line)
            block.append(line)
    if not missing:
        return []
    merged = current.rstrip("\n")
    if lines:
        merged += "\n\n" + "\n".join(lines)
    if top:
        merged = "\n".join(top) + "\n\n" + merged
    return [Change(f"{filename}: add {', '.join(missing)}", write(path, merged + "\n"))]


def available_plugins() -> set[str]:
    try:
        catalog = read_json(MARKETPLACE_FILE)
    except (OSError, ValueError):
        return set()
    return {entry["name"] for entry in catalog.get("plugins", [])}


def local_connectors(config: Path) -> dict[str, str]:
    """Connector name -> MCP server prefix, from the local configuration (empty when absent)."""
    try:
        connectors = read_json(config).get("connectors", {})
    except (OSError, ValueError):
        return {}
    return {name: prefix for name, prefix in connectors.items() if str(prefix).startswith("mcp__")}


def plan_connectors(target: Path, answers: dict, config: Path) -> tuple[list[Change], list[str]]:
    """Deny the local connectors in the settings.local.json of `target`, the main clone."""
    connectors = local_connectors(config)
    if not connectors:
        return [], [f"no connector in {config}: claude.ai connectors are not denied"]
    keep = set(answers.get("keep_tools", [])) | ({LINEAR_CONNECTOR} if answers.get("tracking") == "linear" else set())
    path = target / ".claude" / "settings.local.json"
    settings = read_json(path) if path.exists() else {}
    deny = settings.get("permissions", {}).get("deny", [])
    denied = [prefix for name, prefix in connectors.items()
              if name not in keep and prefix not in keep and prefix not in deny]
    if not denied:
        return [], []
    settings.setdefault("permissions", {}).setdefault("deny", []).extend(denied)
    verb = "update" if path.exists() else "create"
    return [Change(f"{verb} .claude/settings.local.json (deny {len(denied)} connectors)",
                   write(path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n"))], []


def plan_settings(target: Path, answers: dict, available: set[str]) -> tuple[list[Change], list[str]]:
    wanted = [plugins[answers[key]] for key, plugins in (("docs", DOCS_PLUGINS), ("tracking", TRACKING_PLUGINS))
              if answers.get(key) in plugins]
    notes = [f"plugin {p}@{MARKETPLACE} is not available yet: enable it once it exists"
             for p in wanted if p not in available]
    ids = [f"{p}@{MARKETPLACE}" for p in wanted if p in available]
    path = target / ".claude" / "settings.json"
    settings = read_json(path) if path.exists() else {}
    enabled = settings.setdefault("enabledPlugins", {})
    new = [i for i in ids if enabled.get(i) is not True]
    off = [i for i in DISABLED_PLUGINS if i not in enabled]
    keep = set(answers.get("keep_tools", []))
    deny = settings.get("permissions", {}).get("deny", [])
    denied = [t for t in DENIED_TOOLS if t not in keep and t not in deny]
    allowed = [t for t in REQUIRED_TOOLS if t in deny]
    allow = settings.get("permissions", {}).get("allow", [])
    granted = [t for t in ALLOWED_TOOLS if t not in allow]
    if not new and not off and not denied and not allowed and not granted:
        return [], notes
    for i in new:
        enabled[i] = True
    for i in off:
        enabled[i] = False
    if denied:
        settings.setdefault("permissions", {}).setdefault("deny", []).extend(denied)
    if allowed:
        settings["permissions"]["deny"] = [t for t in settings["permissions"]["deny"] if t not in allowed]
    if granted:
        settings.setdefault("permissions", {}).setdefault("allow", []).extend(granted)
    verb = "update" if path.exists() else "create"
    actions = (([f"enable {', '.join(new)}"] if new else []) + ([f"disable {', '.join(off)}"] if off else [])
               + ([f"deny {len(denied)} unused tools"] if denied else [])
               + ([f"allow {', '.join(allowed + granted)}"] if allowed or granted else []))
    return [Change(f"{verb} .claude/settings.json ({'; '.join(actions)})",
                   write(path, json.dumps(settings, indent=2, ensure_ascii=False) + "\n"))], notes


# Architecture: an architecture file checked by .github/scripts/architecture.py, which the
# verification runs. Each stack has its class (STACKS): how the answer is completed, what is created, the check.
ARCHITECTURE_SCRIPT = ".github/scripts/architecture.py"
ARCHITECTURE_TEMPLATE = {ARCHITECTURE_SCRIPT: "github-scripts/architecture.py"}
DIAGRAM = "docs/architecture.puml"
EMPTY_DIAGRAM = "@startuml\n@enduml\n"
ARCHUNIT_PACKAGE = "TngTech.ArchUnitNET"
SKIPPED_FOLDERS = {"bin", "obj"}
IMPORTLINTER = ".importlinter"
IMPORTLINTER_PACKAGE = "import-linter"
# Lock file -> (runner of the project environment, command adding import-linter to the dev dependencies).
PYTHON_TOOLS = {"uv.lock": ("uv run", f"uv add --dev {IMPORTLINTER_PACKAGE}"),
                "poetry.lock": ("poetry run", f"poetry add --group dev {IMPORTLINTER_PACKAGE}")}
PYTHON_MANIFESTS = ("pyproject.toml", "setup.py", "setup.cfg")
CARGO_MANIFEST = "Cargo.toml"
CARGO_WORKSPACE = re.compile(r"(?m)^\s*\[workspace\]")
DIAGRAM_STACK = re.compile(r"(?m)^'\s*stack:\s*(\S+)")
# Top-level folders never proposed as the root package.
NOT_PACKAGES = {"tests", "test", "docs", "scripts", "tools"}
ARCHITECTURE_JSON = "docs/architecture.json"
DEPCRUISE_CONFIG = ".dependency-cruiser.cjs"
DEPCRUISE_CONFIGS = (".dependency-cruiser.js", DEPCRUISE_CONFIG, ".dependency-cruiser.mjs", ".dependency-cruiser.json")
DEPCRUISE_PACKAGE = "dependency-cruiser"
PACKAGE_JSON = "package.json"
JS_SOURCES = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx"}
JS_SKIPPED = {"node_modules"}
# Default roots of a JS/TS project, when they hold sources (Expo Router: app/).
JS_ROOTS = ("src", "app")
JS_GITIGNORE = "\n# Node.js dependencies\nnode_modules/\n"
JS_CI_INSTALL = "      - run: npm ci\n"
PYTHON_GITIGNORE = "\n# Python builds, caches and virtual environments\n*.egg-info/\n__pycache__/\n.venv/\n"
GRADLE_BUILD_FILES = ("build.gradle.kts", "build.gradle")
GRADLE_SETTINGS = ("settings.gradle.kts", "settings.gradle")
GRADLE_SKIPPED = {"build", "buildSrc", "node_modules"}
JVM_SOURCES = (".kt", ".java")
JVM_PACKAGE = re.compile(r"(?m)^\s*package\s+([A-Za-z_][\w.]*)")
VERSION_CATALOG = "gradle/libs.versions.toml"
ARCHUNIT_ARTIFACT = "com.tngtech.archunit:archunit"
# Latest stable ArchUnit when written (provisional).
ARCHUNIT_VERSION = "1.5.1"
ANDROID_PLUGIN = re.compile(r"com\.android\.|plugins\.android\.")
TOP_LEVEL_DEPENDENCIES = re.compile(r"(?m)^dependencies\s*\{[^\n]*\n")


@dataclass(frozen=True)
class TestFramework:
    package: str  # prefix of its package references, case-insensitive
    using: str
    class_attribute: str
    test_attribute: str


TEST_FRAMEWORKS = [
    TestFramework("xunit", "using Xunit;", "", "[Fact]"),
    TestFramework("NUnit", "using NUnit.Framework;", "[TestFixture]", "[Test]"),
    TestFramework("MSTest", "using Microsoft.VisualStudio.TestTools.UnitTesting;", "[TestClass]", "[TestMethod]"),
    TestFramework("gdUnit4", "using GdUnit4;", "[TestSuite]", "[TestCase]"),
]


@dataclass(frozen=True)
class JUnit:
    dependency: re.Pattern  # its dependency in a build file or a version catalog
    test_import: str


# JUnit 5 first: a project moving from 4 to 5 may still have the vintage junit:junit.
JUNITS = [JUnit(re.compile(r"junit-jupiter"), "import org.junit.jupiter.api.Test"),
          JUnit(re.compile(r"""junit:junit|group\s*=\s*["']junit["']"""), "import org.junit.Test")]


class ArchitectureBase:
    """The check every stack shares; a stack running it in its own environment overrides it."""

    @property
    def check(self) -> str:
        return f"python3 {ARCHITECTURE_SCRIPT}"


@dataclass(frozen=True)
class DotnetArchitecture(ArchitectureBase):
    project: str  # test csproj, relative to the project
    test: str  # path of ArchitectureTest.cs
    root: str  # root namespace of the main project
    assembly: str  # assembly of the main project
    namespace: str  # namespace of ArchitectureTest.cs
    exclude: tuple[str, ...]  # folders whose code is not checked (tests, Compile Remove)
    framework: TestFramework | None
    has_package: bool


@dataclass(frozen=True)
class PythonArchitecture(ArchitectureBase):
    roots: tuple[str, ...]  # root packages
    runner: str  # prefix running a command in the project environment ("uv run", or empty)
    install: str | None  # command adding import-linter, None when no lock file tells how

    @property
    def check(self) -> str:
        return f"{self.runner} python {ARCHITECTURE_SCRIPT}".strip()

    @property
    def packages(self) -> str:
        """The root packages, as the AGENTS.md section names them."""
        return ("package " if len(self.roots) == 1 else "packages ") + ", ".join(f"`{r}`" for r in self.roots)


@dataclass(frozen=True)
class RustArchitecture(ArchitectureBase):
    exclude: tuple[str, ...]  # workspace crates that are not components


@dataclass(frozen=True)
class KotlinArchitecture(ArchitectureBase):
    module: str  # folder of the Gradle module, "." for the root project
    build_file: str  # its build.gradle(.kts), relative to the project
    root: str  # root package
    test: str  # path of ArchitectureTest.kt
    framework: JUnit | None
    has_package: bool  # ArchUnit is already in the build file
    gradle_test: str  # command running the module's unit tests

    @property
    def sources(self) -> str:
        return ("" if self.module == "." else self.module + "/") + "src/main/"


@dataclass(frozen=True)
class JsArchitecture(ArchitectureBase):
    roots: tuple[str, ...]  # folders whose sub-folders are the components, "." for the repository
    exclude: tuple[str, ...]  # folders whose code is not checked
    package_json: bool  # a package.json exists at the root
    has_package: bool  # dependency-cruiser is already a dependency


Architecture = DotnetArchitecture | PythonArchitecture | RustArchitecture | KotlinArchitecture | JsArchitecture
# The `stack` of the architecture answer -> its class; INSTRUCTIONS["architecture"] and PLANNERS have an entry for each
# (checked by tests/test_init_project.py).
STACKS = {"dotnet": DotnetArchitecture, "python": PythonArchitecture, "rust": RustArchitecture,
          "kotlin": KotlinArchitecture, "js": JsArchitecture}


def verify_command(answers: dict) -> str | None:
    """The verification, followed by the architecture check when the project has an architecture."""
    verify = answers.get("verify")
    architecture = answers.get("architecture")
    return f"{verify} && {architecture.check}" if verify and architecture else verify


def is_js(answers: dict) -> bool:
    """The project gets the JS/TS architecture: its dependencies are installed by npm."""
    return isinstance(answers.get("architecture"), JsArchitecture)


def is_python(target: Path, answers: dict) -> bool:
    """A Python project: the Python architecture, or a pyproject.toml without it."""
    return isinstance(answers.get("architecture"), PythonArchitecture) or (target / "pyproject.toml").is_file()


def stack_name(architecture: Architecture) -> str:
    return next(name for name, cls in STACKS.items() if isinstance(architecture, cls))


def csproj_value(text: str, tag: str) -> str | None:
    found = re.search(rf"<{tag}>\s*([^<]+?)\s*</{tag}>", text)
    return found.group(1) if found else None


def csproj_files(target: Path) -> list[Path]:
    return [p for p in target.rglob("*.csproj")
            if not any(part.startswith(".") or part in SKIPPED_FOLDERS for part in p.relative_to(target).parts[:-1])]


def is_cargo_workspace(target: Path) -> bool:
    manifest = target / CARGO_MANIFEST
    return manifest.is_file() and bool(CARGO_WORKSPACE.search(manifest.read_text(encoding="utf-8")))


def js_files(target: Path) -> tuple[list[str], list[str]]:
    """The package.json files and the JS/TS sources of the project (relative, with /), outside node_modules and
    hidden folders."""
    manifests, sources = [], []
    for folder, dirs, files in os.walk(target):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in JS_SKIPPED)
        for name in sorted(files):
            relative = (Path(folder) / name).relative_to(target).as_posix()
            if name == PACKAGE_JSON:
                manifests.append(relative)
            elif Path(name).suffix in JS_SOURCES and not name.startswith("."):
                sources.append(relative)
    return manifests, sources


def is_gradle(target: Path) -> bool:
    return any((target / name).is_file() for name in GRADLE_SETTINGS + GRADLE_BUILD_FILES)


def jvm_sources(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix in JVM_SOURCES and p.is_file()) if folder.is_dir() else []


def gradle_modules(target: Path) -> list[str]:
    """The folders (relative, "." for the root project) holding a Gradle build file and Kotlin or Java sources under
    src/main, outside build output and hidden folders."""
    found = []
    for folder, dirs, files in os.walk(target):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in GRADLE_SKIPPED)
        if any(name in files for name in GRADLE_BUILD_FILES) and jvm_sources(Path(folder) / "src" / "main"):
            found.append(Path(folder).relative_to(target).as_posix())
    return found


def infer_stack(target: Path) -> str | None:
    """The stack of the project; a Cargo.toml without [workspace] (e.g. a Python extension) is not Rust."""
    if csproj_files(target):
        return "dotnet"
    if is_cargo_workspace(target):
        return "rust"
    if is_gradle(target):
        return "kotlin"
    if any((target / m).is_file() for m in PYTHON_MANIFESTS):
        return "python"
    if any(js_files(target)):
        return "js"
    return None


def resolve_dotnet(target: Path, given: dict) -> tuple[DotnetArchitecture | None, list[str]]:
    if not csproj_files(target):
        return None, ["architecture: no .NET project (*.csproj) found, nothing set up"]
    project = given["project"]
    main = given.get("main", project)
    for path in (project, main):
        if not (target / path).is_file():
            return None, [f"architecture: {path} not found, nothing set up"]
    project_text = (target / project).read_text(encoding="utf-8-sig")
    main_text = (target / main).read_text(encoding="utf-8-sig")
    main_dir, project_dir = Path(main).parent, Path(project).parent
    folder = Path(given.get("folder", project_dir.as_posix()))
    root = csproj_value(main_text, "RootNamespace") or Path(main).stem
    exclude = [folder] if folder != main_dir else []
    if project != main and project_dir not in exclude:
        exclude.append(project_dir)
    exclude += [main_dir / f for f in re.findall(r'<Compile\s+Remove="([^"*]+?)/\*\*"', main_text)]
    packages = re.findall(r'<PackageReference\s+Include="([^"]+)"', project_text)
    framework = next((f for f in TEST_FRAMEWORKS if any(p.lower().startswith(f.package.lower()) for p in packages)),
                     None)
    return DotnetArchitecture(
        project=project, test=(folder / "ArchitectureTest.cs").as_posix(), root=root,
        assembly=csproj_value(main_text, "AssemblyName") or Path(main).stem,
        namespace=(root + ".Tests") if project == main else
        (csproj_value(project_text, "RootNamespace") or Path(project).stem),
        exclude=tuple(e.as_posix() + "/" for e in exclude if e != Path(".")), framework=framework,
        has_package=any(p.lower() == ARCHUNIT_PACKAGE.lower() for p in packages)), []


def python_packages(target: Path) -> list[str]:
    """The candidate root packages: the packages of src/, else the top-level ones."""
    for base in (target / "src", target):
        found = sorted(d.name for d in base.glob("*/") if (d / "__init__.py").is_file()
                       and not d.name.startswith(".") and d.name not in NOT_PACKAGES)
        if found:
            return found
    return []


def existing_contracts(target: Path) -> str | None:
    """The file holding import-linter contracts not written by project-init, if any."""
    contracts = target / IMPORTLINTER
    if contracts.is_file():
        ours = re.search(r"(?m)^;\s*stack:\s*python\b", contracts.read_text(encoding="utf-8"))
        return None if ours else IMPORTLINTER
    for name, section in (("pyproject.toml", "[tool.importlinter"), ("setup.cfg", "[importlinter")):
        if (target / name).is_file() and section in (target / name).read_text(encoding="utf-8"):
            return name
    return None


def resolve_python(target: Path, given: dict) -> tuple[PythonArchitecture | None, list[str]]:
    existing = existing_contracts(target)
    if existing:
        return None, [f"architecture: {existing} already holds import-linter contracts, kept as they are; "
                      "nothing set up"]
    packages = python_packages(target)
    roots = tuple(given.get("roots") or ([given["root"]] if given.get("root") else packages))
    if not roots:
        return None, ["architecture: no Python package (folder with __init__.py) found, nothing set up"]
    for root in roots:
        if root not in packages:
            return None, [f"architecture: package {root} not found (src/{root}/ or {root}/ with __init__.py), "
                          "nothing set up"]
    lock = next((name for name in PYTHON_TOOLS if (target / name).is_file()), None)
    runner, install = PYTHON_TOOLS[lock] if lock else ("", None)
    return PythonArchitecture(roots=roots, runner=given.get("runner", runner), install=install), []


def foreign_diagram(target: Path, stack: str) -> list[str]:
    """A note when docs/architecture.puml exists and belongs to another stack: it is kept and nothing is set up."""
    diagram = target / DIAGRAM
    if diagram.is_file() and stack not in DIAGRAM_STACK.findall(diagram.read_text(encoding="utf-8")):
        return [f"architecture: {DIAGRAM} already exists without `' stack: {stack}`, kept as it is; nothing set up"]
    return []


def resolve_rust(target: Path, given: dict) -> tuple[RustArchitecture | None, list[str]]:
    if not (target / CARGO_MANIFEST).is_file():
        return None, ["architecture: no Cargo.toml found, nothing set up"]
    if not is_cargo_workspace(target):
        return None, ["architecture: single crate (no [workspace] in Cargo.toml): its components would be modules, "
                      "not checked; nothing set up"]
    if note := foreign_diagram(target, "rust"):
        return None, note
    return RustArchitecture(exclude=tuple(given.get("exclude", ()))), []


def common_package(packages: list[str]) -> str:
    """The deepest package holding all the given ones, "" when they share none."""
    common = packages[0].split(".") if packages else []
    for package in packages[1:]:
        parts = package.split(".")
        while common != parts[:len(common)]:
            common.pop()
    return ".".join(common)


def resolve_kotlin(target: Path, given: dict) -> tuple[KotlinArchitecture | None, list[str]]:
    if not is_gradle(target):
        return None, ["architecture: no Gradle build (settings.gradle(.kts) or build.gradle(.kts)) found, nothing set up"]
    if note := foreign_diagram(target, "kotlin"):
        return None, note
    modules = gradle_modules(target)
    module = given.get("module") or (modules[0] if len(modules) == 1 else None)
    if module is None:
        # TODO(#1): cover several Gradle modules.
        return None, ["architecture: " + (
            f"several Gradle modules with sources ({', '.join(modules)}): set `module` to one, the others are not "
            "covered yet" if modules else
            "no Gradle module with Kotlin or Java sources under src/main found, nothing set up")]
    if module not in modules:
        return None, [f"architecture: module {module} not found (build.gradle(.kts) and Kotlin or Java sources under "
                      "src/main), nothing set up"]
    folder = target / module
    build_file = next(folder / name for name in GRADLE_BUILD_FILES if (folder / name).is_file())
    build_text = build_file.read_text(encoding="utf-8")
    packages = [found.group(1) for path in jvm_sources(folder / "src" / "main")
                if (found := JVM_PACKAGE.search(path.read_text(encoding="utf-8-sig")))]
    # The common package of the sources, not the Android `namespace`, which need not hold the code; `root` overrides.
    root = given.get("root") or common_package(packages)
    if not root:
        return None, [f"architecture: no common package in {module}/src/main: set `root`, nothing set up"]
    test_folder = given.get("folder") or next(
        (f for f in ("src/test/kotlin", "src/test/java") if (folder / f).is_dir()), "src/test/kotlin")
    catalog = target / VERSION_CATALOG
    catalog_text = catalog.read_text(encoding="utf-8") if catalog.is_file() else ""
    framework = (next((j for j in JUNITS if j.dependency.search(build_text)), None)
                 or next((j for j in JUNITS if j.dependency.search(catalog_text)), None))
    task = "testDebugUnitTest" if ANDROID_PLUGIN.search(build_text) else "test"
    gradle = "./gradlew" if (target / "gradlew").is_file() else "gradle"
    prefix = "" if module == "." else ":" + module.replace("/", ":") + ":"
    return KotlinArchitecture(
        module=module, build_file=build_file.relative_to(target).as_posix(), root=root,
        test=(Path(module) / test_folder / root.replace(".", "/") / "ArchitectureTest.kt").as_posix(),
        framework=framework, has_package="archunit" in build_text.lower(),
        gradle_test=f"{gradle} {prefix}{task}"), []


def js_architecture_file(target: Path) -> str | None:
    """The stack named by docs/architecture.json ("" when it names none or cannot be read), None without the file."""
    file = target / ARCHITECTURE_JSON
    if not file.is_file():
        return None
    try:
        content = read_json(file)
    except ValueError:
        return ""
    return str(content.get("stack", "")) if isinstance(content, dict) else ""


def resolve_js(target: Path, given: dict) -> tuple[JsArchitecture | None, list[str]]:
    manifests, sources = js_files(target)
    package_json = PACKAGE_JSON in manifests
    if manifests and not package_json:
        return None, [f"architecture: {', '.join(manifests)} but no package.json at the root: a monorepo, not "
                      "supported; nothing set up"]
    if not package_json and not sources:
        return None, ["architecture: no package.json nor JS/TS source found, nothing set up"]
    stack = js_architecture_file(target)
    if stack is not None and stack != "js":
        return None, [f"architecture: {ARCHITECTURE_JSON} already exists without `\"stack\": \"js\"`, kept as it is; "
                      "nothing set up"]
    configs = [name for name in DEPCRUISE_CONFIGS if (target / name).exists()]
    if configs and stack is None:
        return None, [f"architecture: {configs[0]} already exists, kept as it is; nothing set up"]
    roots = given.get("roots") or [r for r in JS_ROOTS if any(s.startswith(r + "/") for s in sources)] or ["."]
    missing = [r for r in roots if not (target / r).is_dir()]
    if missing:
        return None, [f"architecture: root {', '.join(missing)} not found, nothing set up"]
    package = read_json(target / PACKAGE_JSON) if package_json else {}
    has_package = any(DEPCRUISE_PACKAGE in package.get(key, {}) for key in ("devDependencies", "dependencies"))
    return JsArchitecture(roots=tuple(roots), exclude=tuple(given.get("exclude", ())), package_json=package_json,
                          has_package=has_package), []


RESOLVERS = {"dotnet": resolve_dotnet, "python": resolve_python, "rust": resolve_rust, "kotlin": resolve_kotlin,
             "js": resolve_js}


def resolve_architecture(target: Path, answers: dict) -> tuple[Architecture | None, list[str]]:
    """The architecture answer completed from the project files, or None with a note when it cannot apply."""
    given = answers.get("architecture")
    if not given:
        return None, []
    stack = given.get("stack") or infer_stack(target)
    if stack is None:
        return None, ["architecture: no .NET (*.csproj), Rust (Cargo workspace), Kotlin (Gradle), Python "
                      "(pyproject.toml) or JS/TS project found, nothing set up"]
    if stack not in STACKS:
        return None, [f"architecture: stack {stack} not supported ({', '.join(STACKS)}), nothing set up"]
    return RESOLVERS[stack](target, given)


def create_architecture_file(target: Path, relative: str, text: str,
                             written: str = "components") -> list[Change]:
    """Create the architecture file unless it exists; the script writes its content after apply."""
    if (target / relative).exists():
        return []
    return [Change(f"create {relative} ({written} written after apply, see the note)", write(target / relative, text))]


def after_apply(steps: list[str]) -> str:
    """The note listing what to run once the changes are applied."""
    return "architecture, after apply: " + "; then ".join(steps)


def diagram_header(answers: dict, architecture: DotnetArchitecture) -> str:
    return (f"' Components of {answers['name']}: one per namespace under the root, one arrow per allowed dependency.\n"
            f"' Checked by {architecture.test} (ArchUnitNET) and {ARCHITECTURE_SCRIPT} (every namespace declared).\n"
            f"' Rewrite them from the code: python3 {ARCHITECTURE_SCRIPT} --write (components), then\n"
            "' ARCHITECTURE_DIAGRAM=write dotnet test (arrows), then review.\n"
            "' stack: dotnet\n"
            f"' root: {architecture.root}\n"
            f"' exclude: {' '.join(architecture.exclude)}\n")


def plan_dotnet(target: Path, answers: dict, architecture: DotnetArchitecture) -> tuple[list[Change], list[str]]:
    changes = create_architecture_file(target, DIAGRAM, diagram_header(answers, architecture) + EMPTY_DIAGRAM)
    notes = []
    framework = architecture.framework
    if framework is None:
        notes.append(f"architecture: no known test framework in {architecture.project} "
                     f"({', '.join(f.package for f in TEST_FRAMEWORKS)}): ArchitectureTest.cs not created")
    elif not (target / architecture.test).exists():
        test = render("ArchitectureTest.cs", framework_using=framework.using + "\n", namespace=architecture.namespace,
                      root=architecture.root, assembly=architecture.assembly,
                      class_attribute=framework.class_attribute + "\n" if framework.class_attribute else "",
                      test_attribute=framework.test_attribute)
        changes.append(Change(f"create {architecture.test}", write(target / architecture.test, test)))
    steps = ([] if architecture.has_package else [f"dotnet add {architecture.project} package {ARCHUNIT_PACKAGE}"]) + [
        f"python3 {ARCHITECTURE_SCRIPT} --write (writes the components of {DIAGRAM} from the namespaces)",
        f"ARCHITECTURE_DIAGRAM=write dotnet test {architecture.project} (writes the arrows from the compiled code)",
        "dotnet test and the verification must pass; show the diagram to the user"]
    notes.append(after_apply(steps))
    return changes, notes


def contracts_header(answers: dict, architecture: PythonArchitecture) -> str:
    return ("; stack: python\n"
            f"; Components of {answers['name']}: one `allowed` contract per child of a root package, listing the "
            "components it may import.\n"
            f"; Checked by {ARCHITECTURE_SCRIPT} (every child declared, then import-linter).\n"
            f"; Rewrite the contracts from the code: {architecture.check} --write, then review.\n"
            "[importlinter]\n" + (f"root_package = {architecture.roots[0]}\n" if len(architecture.roots) == 1
                                   else "root_packages =\n" + "".join(f"    {r}\n" for r in architecture.roots)))


def plan_python(target: Path, answers: dict, architecture: PythonArchitecture) -> tuple[list[Change], list[str]]:
    changes = create_architecture_file(target, IMPORTLINTER, contracts_header(answers, architecture), "contracts")
    notes = []
    if architecture.install is None:
        notes.append(f"architecture: no uv.lock or poetry.lock: add {IMPORTLINTER_PACKAGE} to the project's "
                     "development dependencies")
    steps = ([architecture.install] if architecture.install else []) + [
        f"{architecture.check} --write (writes the contracts of {IMPORTLINTER})",
        "the verification must pass; show the contracts to the user"]
    notes.append(after_apply(steps))
    return changes, notes


def rust_diagram_header(answers: dict, architecture: RustArchitecture) -> str:
    return ("' stack: rust\n"
            f"' Components of {answers['name']}: one per crate of the Cargo workspace, one arrow per allowed "
            "dependency (normal and build, not dev).\n"
            "' A <<restricted>> crate may depend only on the external crates drawn (<<external>>); "
            "the others are free.\n"
            f"' Checked by {ARCHITECTURE_SCRIPT}. Rewrite the crates and arrows from the code: {architecture.check} "
            "--write, then review.\n"
            f"' exclude: {' '.join(architecture.exclude)}\n")


def plan_rust(target: Path, answers: dict, architecture: RustArchitecture) -> tuple[list[Change], list[str]]:
    changes = create_architecture_file(target, DIAGRAM, rust_diagram_header(answers, architecture) + EMPTY_DIAGRAM,
                                       "crates")
    steps = [f"{architecture.check} --write (writes the crates and arrows of {DIAGRAM})",
             "show the diagram to the user and mark with them the crates that are <<restricted>> (their external "
             "dependencies are an allowlist)", f"{architecture.check} --write again (draws their external crates)",
             "the verification must pass"]
    return changes, [after_apply(steps)]


def kotlin_diagram_header(answers: dict, architecture: KotlinArchitecture) -> str:
    return ("' stack: kotlin\n"
            f"' Components of {answers['name']}: one per package right under the root, one arrow per allowed "
            "dependency.\n"
            f"' Checked by {architecture.test} (ArchUnit) and {ARCHITECTURE_SCRIPT} (every package declared).\n"
            f"' Rewrite them from the code: {architecture.check} --write (components), then\n"
            f"' ARCHITECTURE_DIAGRAM=write {architecture.gradle_test} (arrows), then review.\n"
            f"' root: {architecture.root}\n"
            f"' sources: {architecture.sources}\n")


def gradle_test_setup(text: str, groovy: bool, has_package: bool) -> str | None:
    """The build file with ArchUnit as a test dependency and the diagram and ARCHITECTURE_DIAGRAM as inputs of the
    tests, so that Gradle does not skip them as up to date when either changes; None when nothing is missing."""
    quote = "'" if groovy else '"'
    updated = text
    if not has_package:
        coordinates = f"{quote}{ARCHUNIT_ARTIFACT}:{ARCHUNIT_VERSION}{quote}"
        dependency = f"    testImplementation {coordinates}\n" if groovy else f"    testImplementation({coordinates})\n"
        block = TOP_LEVEL_DEPENDENCIES.search(updated)
        updated = (updated[:block.end()] + dependency + updated[block.end():] if block
                   else updated.rstrip("\n") + "\n\ndependencies {\n" + dependency + "}\n")
    if DIAGRAM not in updated:
        tasks = "tasks.withType(Test).configureEach {" if groovy else "tasks.withType<Test>().configureEach {"
        updated = (updated.rstrip("\n") + "\n\n// ArchitectureTest reads docs/architecture.puml and ARCHITECTURE_DIAGRAM: "
                   f"rerun the tests when either changes.\n{tasks}\n"
                   f"    inputs.file(rootProject.file({quote}{DIAGRAM}{quote}))\n"
                   f"    inputs.property({quote}architectureDiagram{quote}, "
                   f"providers.environmentVariable({quote}ARCHITECTURE_DIAGRAM{quote}).orElse({quote}{quote}))\n}}\n")
    return None if updated == text else updated


def plan_kotlin(target: Path, answers: dict, architecture: KotlinArchitecture) -> tuple[list[Change], list[str]]:
    changes = create_architecture_file(target, DIAGRAM, kotlin_diagram_header(answers, architecture) + EMPTY_DIAGRAM)
    notes = []
    if architecture.framework is None:
        notes.append(f"architecture: no JUnit 4 or 5 dependency in {architecture.build_file} or {VERSION_CATALOG}: "
                     "ArchitectureTest.kt not created")
    elif not (target / architecture.test).exists():
        test = render("ArchitectureTest.kt", root=architecture.root, test_import=architecture.framework.test_import)
        changes.append(Change(f"create {architecture.test}", write(target / architecture.test, test)))
    build_file = target / architecture.build_file
    updated = gradle_test_setup(build_file.read_text(encoding="utf-8"), build_file.suffix == ".gradle",
                                architecture.has_package)
    if updated is not None:
        added = ([] if architecture.has_package else [f"ArchUnit {ARCHUNIT_VERSION} test dependency"]) + [
            "diagram as test input"]
        changes.append(Change(f"update {architecture.build_file} ({', '.join(added)})", write(build_file, updated)))
    steps = [f"{architecture.check} --write (writes the components of {DIAGRAM} from the packages)",
             f"ARCHITECTURE_DIAGRAM=write {architecture.gradle_test} (writes the arrows from the compiled code)",
             f"{architecture.gradle_test} and the verification must pass; show the diagram to the user"]
    notes.append(after_apply(steps))
    return changes, notes


def npm_name(name: str) -> str:
    """A valid npm package name for the project."""
    return re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-._") or "project"


def plan_js(target: Path, answers: dict, architecture: JsArchitecture) -> tuple[list[Change], list[str]]:
    content = {"stack": "js",
               "comment": f"Components of {answers['name']}: each folder right under a root, with the components it "
                          f"may import. Checked by {ARCHITECTURE_SCRIPT} (dependency-cruiser). Rewrite the "
                          f"components from the code: {architecture.check} --write, then review.",
               "roots": list(architecture.roots), "exclude": list(architecture.exclude), "components": {}}
    changes = create_architecture_file(target, ARCHITECTURE_JSON,
                                       json.dumps(content, indent=2, ensure_ascii=False) + "\n")
    notes = []
    changes += copy_templates(target, {DEPCRUISE_CONFIG: "dependency-cruiser.cjs"})
    if not architecture.package_json:
        package = {"name": npm_name(answers["name"]), "private": True}
        changes.append(Change(f"create {PACKAGE_JSON} (to install {DEPCRUISE_PACKAGE})",
                              write(target / PACKAGE_JSON, json.dumps(package, indent=2) + "\n")))
    workflow = target / ".github" / "workflows" / "verify.yml"
    if workflow.is_file() and "npm ci" not in workflow.read_text(encoding="utf-8"):
        notes.append("architecture: add `- run: npm ci` before the verification in .github/workflows/verify.yml")
    steps = ([] if architecture.has_package else [f"npm install --save-dev {DEPCRUISE_PACKAGE}"]) + [
        f"{architecture.check} --write (writes the components of {ARCHITECTURE_JSON})",
        f"the verification must pass; show {ARCHITECTURE_JSON} to the user"]
    notes.append(after_apply(steps))
    return changes, notes


PLANNERS = {DotnetArchitecture: plan_dotnet, PythonArchitecture: plan_python, RustArchitecture: plan_rust,
            KotlinArchitecture: plan_kotlin, JsArchitecture: plan_js}


def plan_architecture(target: Path, answers: dict) -> tuple[list[Change], list[str]]:
    architecture = answers.get("architecture")
    if not architecture:
        return [], []
    changes, notes = PLANNERS[type(architecture)](target, answers, architecture)
    changes += copy_templates(target, ARCHITECTURE_TEMPLATE)
    hook = target / PRE_PUSH
    if hook.is_file() and architecture.check not in hook.read_text(encoding="utf-8"):
        notes.append(f"architecture: add `{architecture.check}` to the verification in .githooks/pre-push "
                     "(and .github/workflows/verify.yml)")
    return changes, notes


def private_words_notes(target: Path) -> list[str]:
    """An existing pre-push hook is never rewritten: say when it lacks the private-words check of the template."""
    hook = target / PRE_PUSH
    if hook.is_file() and "private_words.py" not in hook.read_text(encoding="utf-8"):
        return ["add the private_words.py check of dev-kit's templates/pre-push to .githooks/pre-push; it reads the "
                "pushed refs on stdin (--stdin-refs): if the hook also reads them, capture them first "
                "(REFS=\"$(cat)\") and pass them to both (printf '%s\\n' \"$REFS\" | ...)"]
    return []


def git(target: Path, *args: str) -> subprocess.CompletedProcess:
    """A git command run in the project, its output captured."""
    return subprocess.run(["git", "-C", str(target), *args], capture_output=True, text=True, encoding="utf-8")


def write_hook(target: Path, relative: str, text: str) -> Callable[[], None]:
    """Write a Git hook, executable on this machine and, through the index, on every clone: chmod does nothing on
    Windows. plan_git's `git init` comes first, so the repository exists when the hook is written."""
    def do() -> None:
        path = target / relative
        write(path, text)()
        path.chmod(path.stat().st_mode | 0o111)
        result = git(target, "update-index", "--add", "--chmod=+x", relative)
        if result.returncode != 0:
            raise RuntimeError(f"git update-index --chmod=+x {relative} failed: {result.stderr.strip()}")
    return do


def plan_verification(target: Path, answers: dict) -> list[Change]:
    verify = answers.get("verify")
    if not verify:
        return []
    changes = []
    if not (target / PRE_PUSH).exists():
        changes.append(Change(f"create {PRE_PUSH}",
                              write_hook(target, PRE_PUSH, render("pre-push", verify=verify_command(answers)))))
    # The verification runs before each push; a pre-commit hook that still runs it is replaced by the warnings.
    pre_commit = target / PRE_COMMIT
    warnings = render("pre-commit")
    if not pre_commit.exists():
        changes.append(Change(f"create {PRE_COMMIT}", write_hook(target, PRE_COMMIT, warnings)))
    elif verify in pre_commit.read_text(encoding="utf-8"):
        changes.append(Change(f"update {PRE_COMMIT} (warnings only, the verification moves to pre-push)",
                              write_hook(target, PRE_COMMIT, warnings)))
    if answers.get("ci"):
        workflow = target / ".github" / "workflows" / "verify.yml"
        if not workflow.exists():
            changes.append(Change("create .github/workflows/verify.yml",
                                  write(workflow, render("github-workflows/verify.yml", verify=verify_command(answers),
                                                         install=JS_CI_INSTALL if is_js(answers) else ""))))
    return changes


PRE_PUSH = ".githooks/pre-push"
PRE_COMMIT = ".githooks/pre-commit"
# The scripts checking a PR description, which auto_merge.py imports (checked by tests/test_init_project.py).
PR_SCRIPTS = {".github/scripts/pr_description.py": "github-scripts/pr_description.py",
              ".github/scripts/structure.py": "github-scripts/structure.py"}
# The PR template and its check (dev-kit's docs/pr-description.md), copied with ci.
PR_CHECK_FILES = {".github/pull_request_template.md": "pull_request_template.md",
                  ".github/workflows/pr-description.yml": "github-workflows/pr-description.yml", **PR_SCRIPTS}
AUTO_MERGE_FILES = {".github/workflows/auto-merge.yml": "github-workflows/auto-merge.yml",
                    ".github/scripts/auto_merge.py": "github-scripts/auto_merge.py", **PR_SCRIPTS}


def github_files(answers: dict) -> dict[str, str]:
    """The PR check (with ci, which needs verify) and auto-merge files; the scripts they share are copied once."""
    files = dict(PR_CHECK_FILES) if answers.get("ci") and answers.get("verify") else {}
    return {**files, **AUTO_MERGE_FILES} if answers.get("auto_merge") else files


def copy_templates(target: Path, files: dict[str, str]) -> list[Change]:
    """Copy the templates to the paths that do not exist yet."""
    return [Change(f"create {path}", write(target / path, (TEMPLATES / template).read_text(encoding="utf-8")))
            for path, template in files.items() if not (target / path).exists()]


def plan_auto_merge(answers: dict, repository: dict | None) -> list[str]:
    """Check that the repository allows rebase merging, which auto-merge needs (its files: github_files)."""
    if not answers.get("auto_merge"):
        return []
    if repository is None:
        return ["auto-merge needs rebase merging allowed in the GitHub repository settings: "
                "check it once the repository exists"]
    if repository.get("rebaseMergeAllowed") is not True:
        return ["auto-merge needs rebase merging: allow it in the GitHub repository settings (General > Pull Requests)"]
    return []


def git_config(target: Path) -> str:
    return git(target, "config", "--local", "core.hooksPath").stdout.strip()


def plan_git(target: Path, answers: dict) -> list[Change]:
    changes = []
    is_repo = (target / ".git").exists()
    if not is_repo:
        changes.append(Change("git init (branch main)", lambda: subprocess.run(
            ["git", "-C", str(target), "init", "-q", "-b", "main"], check=True)))
    if answers.get("verify") and (not is_repo or git_config(target) != ".githooks"):
        changes.append(Change("point Git hooks at .githooks", lambda: subprocess.run(
            ["git", "-C", str(target), "config", "core.hooksPath", ".githooks"], check=True)))
    return changes


def run_gh(target: Path, *args: str) -> str | None:
    """Output of a gh command run in the project, or None when gh is missing or fails."""
    try:
        result = subprocess.run(["gh", *args], cwd=target, capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def ready_label(answers: dict) -> tuple[str, str]:
    """Name and description of the label that marks a ticket ready, in the documentation's language."""
    return READY_LABELS[languages(answers)["docs"]]


def has_github_remote(target: Path) -> bool:
    return (target / ".git").exists() and "github.com" in git(target, "remote", "-v").stdout


def github_repository(target: Path, gh: Callable[..., str | None]) -> dict | None:
    """The settings of the GitHub repository this script reads, None when gh is unavailable or fails."""
    output = gh(target, "repo", "view", "--json", "rebaseMergeAllowed,deleteBranchOnMerge")
    try:
        return json.loads(output) if output is not None else None
    except ValueError:
        return None


def plan_ready_label(target: Path, answers: dict, gh: Callable[..., str | None],
                     on_github: bool) -> tuple[list[Change], list[str]]:
    name, description = ready_label(answers)
    if answers.get("tracking") == "linear":
        return [], [f"create the label {name} in the Linear team unless it exists (Definition of Ready)"]
    if answers.get("tracking") != "github-issues":
        return [], []
    listed = gh(target, "label", "list", "--json", "name", "--limit", "1000") if on_github else None
    if listed is None:
        return [], [f"GitHub label {name} not created (no GitHub repository, or gh unavailable): "
                    "run the script again once the repository exists"]
    if name.casefold() in {label["name"].casefold() for label in json.loads(listed)}:
        return [], []

    def create() -> None:
        if gh(target, "label", "create", name, "--description", description, "--color", READY_COLOR) is None:
            raise RuntimeError(f"gh label create {name} failed")
    return [Change(f"create the GitHub label {name} (Definition of Ready)", create)], []


def plan_branch_deletion(target: Path, gh: Callable[..., str | None],
                         repository: dict | None) -> tuple[list[Change], list[str]]:
    """Turn on GitHub's deletion of head branches once their pull request is merged."""
    if repository is None:
        return [], ["automatic deletion of merged branches not turned on (no GitHub repository, or gh unavailable): "
                    "run the script again once the repository exists"]
    if repository.get("deleteBranchOnMerge") is True:
        return [], []

    def enable() -> None:
        if gh(target, "api", "-X", "PATCH", "repos/{owner}/{repo}", "-F", "delete_branch_on_merge=true") is None:
            raise RuntimeError("gh api PATCH delete_branch_on_merge failed")
    return [Change("turn on the GitHub deletion of head branches after merge", enable)], []


def plan_journal(target: Path, journal: Path) -> tuple[list[Change], list[str]]:
    if not (journal / ".git").exists():
        return [], ["the work journal (dev-journal) is not cloned on this machine: project not registered; "
                    "run dev-kit's scripts/install.py"]
    try:
        name = dev_journal.relative_name(journal, target)
    except ValueError:
        return [], [f"{target} is outside the dev folder {journal.parent}: not registered in the work journal"]
    if name.casefold() in {r.casefold() for r in dev_journal.watched_names(journal)}:
        return [], []
    return [Change(f"watch {name} in the work journal (repos.json of {journal}, commit and push)",
                   lambda: dev_journal.register(journal, [target]))], []


def plan(target: Path, answers: dict, journal: Path = dev_journal.JOURNAL_REPO,
         available: set[str] | None = None,
         gh: Callable[..., str | None] = run_gh,
         local_config: Path = LOCAL_CONFIG) -> tuple[list[Change], list[str]]:
    """Changes to make, and notes for the user."""
    target = target.resolve()
    # From a worktree, what lives outside the repository's tracked files goes to the main clone: the
    # unversioned local settings, the journal entry, a wiki beside the clone.
    main = git_paths.main_clone(target) or target
    architecture, architecture_notes = resolve_architecture(target, answers)
    answers = {**answers, "architecture": architecture}
    architecture_changes, more_notes = plan_architecture(target, answers)
    architecture_notes += more_notes + private_words_notes(target)
    settings, notes = plan_settings(target, answers, available_plugins() if available is None else available)
    connector_changes, connector_notes = plan_connectors(main, answers, local_config)
    settings += connector_changes
    notes += connector_notes
    journal_changes, journal_notes = plan_journal(main, journal)
    glossary_changes, glossary_notes = plan_glossary(target, answers, main)
    on_github = has_github_remote(target)
    repository = github_repository(target, gh) if on_github else None
    label_changes, label_notes = plan_ready_label(target, answers, gh, on_github)
    merge_notes = plan_auto_merge(answers, repository)
    branch_changes, branch_notes = plan_branch_deletion(target, gh, repository)
    agents_changes, agents_notes = plan_agents_md(target, answers)
    changes = (plan_git(target, answers) + agents_changes + plan_principles(target, answers)
               + plan_claude_md(target, answers)
               + settings + glossary_changes
               + plan_lines(target, ".gitattributes", "gitattributes")
               + plan_lines(target, ".gitignore", "gitignore", (JS_GITIGNORE if is_js(answers) else "")
                            + (PYTHON_GITIGNORE if is_python(target, answers) else ""))
               + plan_verification(target, answers) + copy_templates(target, github_files(answers))
               + architecture_changes + branch_changes
               + label_changes + journal_changes)
    claude_file = target / "CLAUDE.md"
    if claude_file.is_file():
        claude_body = re.sub(r"(?m)^@\S+\s*$", "", claude_file.read_text(encoding="utf-8")).strip()
        if claude_body and not claude_body.startswith("## Claude Code"):
            notes.append("existing CLAUDE.md content was preserved; review it for shared sections that can move to AGENTS.md")
    return changes, notes + agents_notes + glossary_notes + architecture_notes + merge_notes + branch_notes + label_notes + journal_notes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", type=Path)
    parser.add_argument("answers", type=Path)
    parser.add_argument("--apply", action="store_true", help="make the changes (default: only list them)")
    parser.add_argument("--journal", type=Path, default=dev_journal.JOURNAL_REPO,
                        help="dev-journal clone (default: next to dev-kit)")
    args = parser.parse_args()
    answers = read_json(args.answers)
    if args.apply:
        args.target.mkdir(parents=True, exist_ok=True)
    changes, notes = plan(args.target, answers, args.journal)
    if not changes:
        print("Nothing to change.")
    for change in changes:
        print(("done: " if args.apply else "to do: ") + change.description)
        if args.apply:
            change.apply()
    for note in notes:
        print("note: " + note)
    sys.exit(0)


if __name__ == "__main__":
    main()
