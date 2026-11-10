#!/usr/bin/env python3
"""Inject the domain vocabulary rules and the glossary index, run by the core plugin at session start.

The glossary path is declared in the "Vocabulary" (or "Vocabulaire") section
of the project's AGENTS.md or legacy CLAUDE.md; this hook adds the rules that
go with it and a compact index of the glossary (French term, English term,
forbidden synonyms), so that a fix to them reaches every project without
copying. The definitions stay in the glossary, read on demand. A relative path
is resolved against the project, then against the main checkout of its
repository, so that `../<name>-wiki/…` also works from a worktree.

Never blocks the session: it always exits 0, prints nothing for a project
without a vocabulary section, and otherwise prints one JSON object: the rules
and the index as `additionalContext`, plus a one-line `systemMessage` (shown to
the user) when the glossary cannot be found or the index is truncated.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_paths  # noqa: E402

TITLES = {"vocabulary", "vocabulaire"}
# Claude Code caps each hook output string at 10,000 characters (beyond it, only a
# file path and a 2,000-character preview reach Claude): https://code.claude.com/docs/en/hooks
CAP = 10_000

RULES = """\
Domain vocabulary. The project's glossary (`{path}`) is the reference for every domain term: \
the notions the rules, the player or the user talk about, not technical terms.
- Use only glossary terms, in code (the English term), documentation, tickets and commits; never write a forbidden synonym.
- Read the glossary when you need a definition, before proposing a new term, and during `/core:clarify`.
- A domain notion missing from the glossary: propose its full entry (French term, English term, displayed terms \
when they differ, definition, forbidden synonyms) and use it only after the user agrees.
- Every time the user uses a forbidden synonym, point it out and give the glossary term.
- A forbidden synonym in existing code outside the task: leave it, mention it at the end of the task and propose a ticket.
- A glossary term that changes: the former term becomes a forbidden synonym; propose a ticket that renames code \
and documentation in a dedicated commit."""
INDEX_TITLE = "\n\nGlossary index (French = English in code; after ≠, forbidden synonyms):"
TRUNCATED = "\n- … {count} more terms: read the glossary."


@dataclass
class Term:
    fr: str
    en: str
    synonyms: list[str]

    def index_line(self) -> str:
        line = f"\n- {self.fr} = {self.en}"
        return line + (f" ≠ {', '.join(self.synonyms)}" if self.synonyms else "")


def glossary_path(instructions: str) -> str | None:
    """Path named in the vocabulary section, supporting old `@` imports."""
    for part in re.split(r"(?m)^(?=## )", instructions):
        if part.startswith("## ") and part.splitlines()[0][3:].strip().lower() in TITLES:
            found = re.search(r"(?m)^\s*(?:-\s*)?@(\S+)", part)
            if found:
                return found.group(1)
            found = re.search(r"(?mi)^\s*-\s*.*?\b(?:at|à)\s+`([^`]+)`", part)
            return found.group(1) if found else None
    return None


def declared_path(project: Path) -> str | None:
    """Glossary path of the project's AGENTS.md, else of its legacy CLAUDE.md."""
    for name in ("AGENTS.md", "CLAUDE.md"):
        instructions = project / name
        if instructions.is_file():
            path = glossary_path(instructions.read_text(encoding="utf-8"))
            if path:
                return path
    return None


def find_glossary(project: Path, path: str) -> Path | None:
    """The glossary, relative to the project, else to the main checkout (a sibling wiki seen from a worktree)."""
    for base in (project, git_paths.main_clone(project)):
        if base is not None and (base / Path(path).expanduser()).is_file():
            return base / Path(path).expanduser()
    return None


def parse_glossary(text: str) -> list[Term]:
    """Rows of the glossary table: French | English (code) | … | Forbidden synonyms."""
    terms = []
    rows = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    for row in rows[1:]:  # the first row is the header
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row.strip().strip("|"))]
        if len(cells) < 2 or set("".join(cells)) <= set("-: "):
            continue
        synonyms = [s.strip() for s in cells[-1].split(",") if s.strip()] if len(cells) >= 6 else []
        if cells[0] or cells[1]:
            terms.append(Term(cells[0], cells[1], synonyms))
    return terms


def context(path: str, terms: list[Term]) -> tuple[str, int]:
    """The rules and as much of the index as fits in the cap; the number of terms left out."""
    text = RULES.format(path=path) + (INDEX_TITLE if terms else "")
    for kept, term in enumerate(terms):
        line = term.index_line()
        if len(text) + len(line) + len(TRUNCATED.format(count=len(terms))) > CAP:
            return text + TRUNCATED.format(count=len(terms) - kept), len(terms) - kept
        text += line
    return text, 0


def output(project: Path) -> dict | None:
    path = declared_path(project)
    if path is None:
        return None
    glossary = find_glossary(project, path)
    terms = parse_glossary(glossary.read_text(encoding="utf-8")) if glossary else []
    text, left_out = context(path, terms)
    result: dict = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    if glossary is None:
        result["systemMessage"] = f"vocabulaire : glossaire introuvable ({path}), les termes du projet ne sont pas chargés."
    elif left_out:
        result["systemMessage"] = (f"vocabulaire : index du glossaire tronqué ({left_out} termes sur {len(terms)} "
                                   f"au-delà de {CAP} caractères).")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")),
                        help="project folder (default: $CLAUDE_PROJECT_DIR, else the current folder)")
    args = parser.parse_args()
    try:
        result = output(args.project)
    except (OSError, ValueError) as exc:
        result = {"systemMessage": f"vocabulaire : fichier de consignes illisible ({exc})."}
    if result:
        print(json.dumps(result))  # ASCII escapes: safe whatever the console encoding
    sys.exit(0)


if __name__ == "__main__":
    main()
