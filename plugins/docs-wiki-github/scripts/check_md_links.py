#!/usr/bin/env python3
"""Check the links and folders of a Markdown wiki read in GitHub.

    python3 check_md_links.py [wiki dir]

Reports every relative link whose target does not exist, every absolute link
starting with `/`, every Obsidian link `[[…]]` and every folder without a
`README.md`. Hidden folders are skipped, and so is code (fenced blocks and
inline code). Exits with 1 when something is to fix.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys
import urllib.parse
from pathlib import Path

LINK = re.compile(r"\]\(\s*(<[^>]*>|[^)\s]+)")
OBSIDIAN = re.compile(r"\[\[[^\]]+\]\]")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def prose_lines(text: str):
    """Yield (line number, line) outside fenced blocks, without inline code."""
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        m = FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else fence or m.group(1)
            continue
        if not fence:
            yield number, INLINE_CODE.sub("", line)


def link_problems(root: Path, page: Path) -> list[str]:
    rel = page.relative_to(root).as_posix()
    problems = []
    for number, line in prose_lines(page.read_text(encoding="utf-8")):
        where = f"{rel}:{number}"
        for m in OBSIDIAN.finditer(line):
            problems.append(f"{where}: Obsidian link {m.group(0)}")
        for m in LINK.finditer(line):
            link = m.group(1).strip("<>")
            target = link.split("#")[0]
            if not target or SCHEME.match(target):
                continue
            if target.startswith("/"):
                problems.append(f"{where}: absolute link {link}")
                continue
            path = posixpath.normpath(posixpath.join(posixpath.dirname(rel), urllib.parse.unquote(target)))
            if path.startswith("..") or not (root / path).exists():
                problems.append(f"{where}: broken link {link}")
    return problems


def check(root: Path) -> list[str]:
    problems = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        folder = Path(folder)
        if "README.md" not in files:
            problems.append(f"{folder.relative_to(root).as_posix()}/: no README.md")
        for name in sorted(files):
            if name.endswith(".md"):
                problems += link_problems(root, folder / name)
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wiki", type=Path, nargs="?", default=Path("."))
    args = parser.parse_args()
    problems = check(args.wiki.resolve())
    sys.stdout.reconfigure(errors="replace")  # accented names on a Windows console
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
