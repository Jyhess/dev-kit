#!/usr/bin/env python3
"""Inject dev-kit's shared rules, run by the core plugin at session start.

A project opts in with a `## Shared rules` section in its AGENTS.md (or legacy
CLAUDE.md); this hook then adds plugins/core/rules/shared-rules.md to the
context, read at each start, so that a fix to the rules reaches every project
without copying. Codex reads the same file through ~/.dev-kit/rules, linked by
scripts/install_codex.py.

Never blocks the session: it always exits 0, prints nothing for a project
without the section, and otherwise prints one JSON object: the rules as
`additionalContext`, or a one-line `systemMessage` (shown to the user) when
they cannot be read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

RULES = Path(__file__).resolve().parents[1] / "rules" / "shared-rules.md"
MARKER = re.compile(r"(?mi)^## Shared rules\s*$")


def opted_in(project: Path) -> bool:
    """True when the project's AGENTS.md, else its legacy CLAUDE.md, has the marker section."""
    for name in ("AGENTS.md", "CLAUDE.md"):
        instructions = project / name
        if instructions.is_file() and MARKER.search(instructions.read_text(encoding="utf-8")):
            return True
    return False


def output(project: Path, rules: Path) -> dict | None:
    if not opted_in(project):
        return None
    try:
        text = rules.read_text(encoding="utf-8")
    except OSError as exc:
        return {"systemMessage": f"règles partagées : fichier illisible ({rules}), non chargées ({exc.strerror})."}
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")),
                        help="project folder (default: $CLAUDE_PROJECT_DIR, else the current folder)")
    parser.add_argument("--rules", type=Path, default=RULES, help="shared rules file (default: the plugin's)")
    args = parser.parse_args()
    try:
        result = output(args.project, args.rules)
    except (OSError, ValueError) as exc:
        result = {"systemMessage": f"règles partagées : fichier de consignes illisible ({exc})."}
    if result:
        print(json.dumps(result))  # ASCII escapes: safe whatever the console encoding
    sys.exit(0)


if __name__ == "__main__":
    main()
