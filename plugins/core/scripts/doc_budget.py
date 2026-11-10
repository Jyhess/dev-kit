#!/usr/bin/env python3
"""Warn about Markdown files over their size budget.

    python3 doc_budget.py --staged    # pre-commit: the .md files of the commit
    python3 doc_budget.py             # every tracked .md file

Budgets (1 kB = 1,000 bytes): AGENTS.md and CLAUDE.md 5 kB, README.md and
SKILL.md 10 kB, other docs 15 kB. A repository adjusts them in
`.doc-budgets.json` at its root: {"pattern": bytes}, where a pattern matches
the file's path or, without "/", its name (fnmatch); its entries come before
the defaults, first match wins.

Never blocks: always exits 0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

DEFAULTS = {"AGENTS.md": 5_000, "CLAUDE.md": 5_000, "README.md": 10_000, "SKILL.md": 10_000, "*.md": 15_000}
CONFIG = ".doc-budgets.json"


def git(folder: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def budgets(project: Path) -> dict[str, int]:
    try:
        own = json.loads((project / CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        own = {}
    return {**{k: int(v) for k, v in own.items()}, **{k: v for k, v in DEFAULTS.items() if k not in own}}


def budget(path: str, limits: dict[str, int]) -> int | None:
    name = PurePosixPath(path).name
    return next((limit for pattern, limit in limits.items()
                 if fnmatch(path if "/" in pattern else name, pattern)), None)


def warnings(project: Path, staged: bool) -> list[str]:
    if staged:
        listed = git(project, "diff", "--cached", "--name-only", "--diff-filter=AMR", "-z") or ""
    else:
        listed = git(project, "ls-files", "-z") or ""
    limits = budgets(project)
    found = []
    for path in filter(None, listed.split("\0")):
        if not path.lower().endswith(".md"):
            continue
        size = git(project, "cat-file", "-s", f":{path}")
        limit = budget(path, limits)
        if size and limit is not None and int(size) > limit:
            found.append(f"warning: doc budget: {path} is {int(size):,} bytes, over its {limit:,}-byte budget"
                         " (write what is needed to act, nothing else)")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, default=Path("."), help="project folder (default: current folder)")
    parser.add_argument("--staged", action="store_true", help="check the .md files of the staged changes only")
    args = parser.parse_args()
    project = Path((git(args.project, "rev-parse", "--show-toplevel") or str(args.project)).strip())
    for line in warnings(project, args.staged):
        print(line)
    sys.exit(0)


if __name__ == "__main__":
    main()
