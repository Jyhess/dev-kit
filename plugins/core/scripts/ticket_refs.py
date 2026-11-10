#!/usr/bin/env python3
"""Find ticket references in a project's files: git links lines to tickets, not the files.

    python3 ticket_refs.py            # pre-push: every tracked file, exits 1 on a reference
    python3 ticket_refs.py --staged   # pre-commit: the added lines, a warning, exits 0

A reference is a GitHub one: `#12`, `owner/repo#12`, or a `github.com/<owner>/<repo>/issues/12`
or `/pull/12` URL. Not references: a number starting with 0 or followed by `.<digit>` (`#0.1.0`),
an HTML entity (`&#12;`), a URL fragment (`page#12`, `/#12`). A line containing `TODO` may cite
an open ticket; the TODO goes when the ticket is resolved.

Examples are excluded by `.ticket-refs-ignore` at the repository root, one path pattern per line
(`#` starts a comment): `dir/` for a folder, a pattern with `/` for a path from the root, one
without for a file name anywhere, `*` and `?` wildcards. Without it nothing is excluded.
"""

from __future__ import annotations

import argparse
import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vocabulary_check import git, read_text, staged_lines, tracked_files  # noqa: E402

IGNORE_FILE = ".ticket-refs-ignore"
REFERENCE = re.compile(
    r"https?://github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+"
    r"|(?<![\w./:-])[\w.-]+/[\w.-]+#[1-9]\d*\b"
    r"|(?<![\w&#/$.-])#[1-9]\d*(?!\w|\.\d)")


def ignore_patterns(project: Path) -> list[str]:
    path = project / IGNORE_FILE
    if not path.is_file():
        return []
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line]


def ignored(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/"):
            if path.startswith(pattern.lstrip("/")):
                return True
        elif "/" in pattern:
            if fnmatchcase(path, pattern.lstrip("/")):
                return True
        elif fnmatchcase(path.rsplit("/", 1)[-1], pattern):
            return True
    return False


def references(text: str) -> list[str]:
    return [] if "TODO" in text else REFERENCE.findall(text)


def find(lines: dict[str, list[tuple[int, str]]], patterns: list[str]) -> list[str]:
    """`path:line: references` for each line holding one, outside the ignored paths."""
    found = []
    for path, numbered in sorted(lines.items()):
        if path == IGNORE_FILE or ignored(path, patterns):
            continue
        for number, text in numbered:
            if refs := references(text):
                found.append(f"{path}:{number}: {', '.join(refs)}")
    return found


def tree_lines(project: Path, patterns: list[str]) -> dict[str, list[tuple[int, str]]]:
    lines = {}
    for file in tracked_files(project):
        path = file.relative_to(project).as_posix()
        if ignored(path, patterns):
            continue
        text = read_text(file)
        if text is not None:
            lines[path] = list(enumerate(text.splitlines(), 1))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, default=Path("."), help="project folder (default: current folder)")
    parser.add_argument("--staged", action="store_true", help="warn about the added lines of the staged changes")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    project = Path((git(args.project, "rev-parse", "--show-toplevel") or str(args.project)).strip())
    patterns = ignore_patterns(project)
    lines = staged_lines(project) if args.staged else tree_lines(project, patterns)
    found = find(lines, patterns)
    if args.staged:
        for place in found:
            print(f"warning: ticket reference: {place}")
        sys.exit(0)
    if found:
        print("Ticket references in the files (git links lines to tickets; a TODO line may cite an open one; "
              f"examples go in {IGNORE_FILE}):")
        print("\n".join(f"- {place}" for place in found))
        sys.exit(1)


if __name__ == "__main__":
    main()
