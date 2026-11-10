#!/usr/bin/env python3
"""Check that no project keeps a local copy of a shared skill.

    python3 scripts/check_projects.py [project dir …]

Without arguments, checks the repositories watched by the work journal
(`repos.json` of the dev-journal clone, next to dev-kit). A project fails when
one of its local skills (`.claude/skills/` or `.agents/skills/`) has the name
of a dev-kit skill, or a former name of one (`cadrage` became `clarify`). Exits
with 1 when a project fails.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "dev-journal" / "scripts"))
import dev_journal  # noqa: E402

FORMER_NAMES = {"cadrage": "clarify"}
NAME = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


def skill_name(skill_md: Path) -> str:
    m = NAME.search(skill_md.read_text(encoding="utf-8"))
    return m.group(1) if m else skill_md.parent.name


def shared_skills(root: Path = ROOT) -> dict[str, str]:
    """{skill name: plugin:skill} for every skill of the dev-kit plugins."""
    shared = {}
    for skill_md in sorted(root.glob("plugins/*/skills/*/SKILL.md")):
        name = skill_name(skill_md)
        shared[name] = f"{skill_md.parents[2].name}:{name}"
    for former, name in FORMER_NAMES.items():
        if name in shared:
            shared[former] = shared[name]
    return shared


def copies(project: Path, shared: dict[str, str]) -> list[str]:
    problems = []
    patterns = (".claude/skills/*/SKILL.md", ".agents/skills/*/SKILL.md")
    for skill_md in sorted(path for pattern in patterns for path in project.glob(pattern)):
        for name in {skill_md.parent.name, skill_name(skill_md)}:
            if name in shared:
                problems.append(f"{project}: local skill {name} duplicates /{shared[name]}")
                break
    return problems


def journal_projects(journal: Path = dev_journal.JOURNAL_REPO) -> list[Path]:
    return [p for p in dev_journal.watched_repos(journal) if p.is_dir()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("projects", type=Path, nargs="*")
    args = parser.parse_args()
    projects = args.projects or journal_projects()
    if not projects:
        sys.exit("no project to check: pass project folders, or register them in the work journal")
    shared = shared_skills()
    problems = [p for project in projects for p in copies(project, shared)]
    for problem in problems:
        print(problem)
    print(f"{len(projects)} project(s) checked, {len(problems)} copy(ies) of a shared skill")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
