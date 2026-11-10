#!/usr/bin/env python3
"""Check the project's code and docs against its domain glossary.

    python3 vocabulary_check.py --staged    # pre-commit: forbidden synonyms on the added lines
    python3 vocabulary_check.py             # Review report: forbidden synonyms and unused terms

The glossary is found like the `vocabulary.py` session hook does. Matching is by
whole word (plural s or x allowed, es after s/x/z/ch/sh), ignoring case and accents; identifiers are
split (`flightAssist`, `flight_assist` → "flight assist"). Docs are Markdown and
text files, code is every other tracked text file; the glossary itself is left
out. With --staged, only the files of the commit are read (commit messages are
not); otherwise the glossary's repository is read too when it is outside the
project (a wiki). An unused term is one whose English term appears in no code
and whose French term appears in no doc.

Never blocks: always exits 0, prints nothing for a project without a glossary.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vocabulary  # noqa: E402

DOC_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}


def normalize(text: str) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|_", " ", text)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return text.casefold()


def pattern(term: str) -> re.Pattern | None:
    words = normalize(term).split()
    if not words:
        return None
    # "es" only after a sibilant ("box" → "boxes"): otherwise "fil" would match "files"
    plural = r"(?:s|es|x)?" if re.search(r"(?:s|x|z|ch|sh)$", words[-1]) else r"(?:s|x)?"
    return re.compile(r"(?<!\w)" + r"[\s-]+".join(map(re.escape, words)) + plural + r"(?!\w)")


@dataclass
class Synonym:
    text: str
    term: vocabulary.Term
    regex: re.Pattern


@dataclass
class Checker:
    """Forbidden synonyms, and the glossary terms masked before looking for them ("fuel tank" is not "tank")."""
    synonyms: list[Synonym]
    terms: list[re.Pattern]

    @classmethod
    def of(cls, terms: list[vocabulary.Term]) -> Checker:
        valid = sorted({t for term in terms for t in (term.fr, term.en) if t.strip()}, key=len, reverse=True)
        found = []
        for term in terms:
            for text in term.synonyms:
                # a qualified synonym ("tir (pour l'objet)") depends on the meaning: left to the Review
                if "(" not in text and normalize(text) not in map(normalize, valid) and (regex := pattern(text)):
                    found.append(Synonym(text, term, regex))
        return cls(found, [p for p in map(pattern, valid) if p])

    def hits(self, text: str) -> list[Synonym]:
        normalized = normalize(text)
        if not any(s.regex.search(normalized) for s in self.synonyms):
            return []
        for term in self.terms:
            normalized = term.sub("#", normalized)
        return [s for s in self.synonyms if s.regex.search(normalized)]


def git(folder: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def staged_lines(project: Path) -> dict[str, list[tuple[int, str]]]:
    """Added lines of the staged changes: {path: [(line number, text)]}."""
    # core.quotePath=false: non-ASCII paths as they are, not quoted with octal escapes.
    diff = git(project, "-c", "core.quotePath=false", "diff", "--cached", "-U0", "--no-color", "--no-ext-diff",
               "--diff-filter=AMR") or ""
    lines: dict[str, list[tuple[int, str]]] = {}
    path, number = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            # git ends the name with a TAB when it holds a space
            path = line[6:].rstrip("\t") if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            number = int(re.search(r"\+(\d+)", line).group(1))
        elif line.startswith("+") and path:
            lines.setdefault(path, []).append((number, line[1:]))
            number += 1
    return lines


def tracked_files(folder: Path) -> list[Path]:
    listed = git(folder, "ls-files", "-z")
    if listed is None:
        return []
    return [folder / name for name in listed.split("\0") if name]


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def find_synonyms(lines: dict[str, list[tuple[int, str]]], checker: Checker) -> list[tuple[Synonym, str]]:
    """(synonym, path:line) of each forbidden synonym found."""
    return [(synonym, f"{path}:{number}") for path, numbered in lines.items() for number, text in numbered
            for synonym in checker.hits(text)]


def describe(synonym: Synonym) -> str:
    return f"\"{synonym.text}\" → {synonym.term.fr} ({synonym.term.en})"


def is_doc(path: str) -> bool:
    return Path(path).suffix.lower() in DOC_SUFFIXES


def report(project: Path, glossary: Path, terms: list[vocabulary.Term]) -> str:
    roots = [project]
    glossary_root = git(glossary.parent, "rev-parse", "--show-toplevel")
    if glossary_root and Path(glossary_root.strip()).resolve() != project.resolve():
        roots.append(Path(glossary_root.strip()))
    files: dict[str, str] = {}
    for root in roots:
        for path in tracked_files(root):
            if path.resolve() == glossary.resolve():
                continue
            text = read_text(path)
            if text is not None:
                label = path.relative_to(root).as_posix() if root == project else f"{root.name}/{path.relative_to(root).as_posix()}"
                files[label] = text
    lines = {label: list(enumerate(text.splitlines(), 1)) for label, text in files.items()}
    places: dict[str, list[str]] = {}
    for synonym, place in find_synonyms(lines, Checker.of(terms)):
        places.setdefault(describe(synonym), []).append(place)
    code = "\n".join(normalize(t) for label, t in files.items() if not is_doc(label))
    docs = "\n".join(normalize(t) for label, t in files.items() if is_doc(label))
    unused = []
    for term in terms:
        en, fr = pattern(term.en), pattern(term.fr)
        if not (en and en.search(code)) and not (fr and fr.search(docs)):
            unused.append(f"{term.fr} ({term.en})")
    out = [f"Forbidden synonyms ({len(places)}):"]
    for synonym, found in sorted(places.items(), key=lambda item: -len(item[1])):
        shown = ", ".join(found[:5]) + (", …" if len(found) > 5 else "")
        out.append(f"- {synonym}: {len(found)} line{'s' if len(found) > 1 else ''} ({shown})")
    out += [f"Unused terms, proposed for removal ({len(unused)}):"] + [f"- {u}" for u in unused]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, default=Path("."), help="project folder (default: current folder)")
    parser.add_argument("--staged", action="store_true", help="check the added lines of the staged changes only")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    project = Path((git(args.project, "rev-parse", "--show-toplevel") or str(args.project)).strip())
    try:
        path = vocabulary.declared_path(project)
        glossary = vocabulary.find_glossary(project, path) if path else None
        terms = vocabulary.parse_glossary(glossary.read_text(encoding="utf-8")) if glossary else []
    except (OSError, ValueError) as exc:
        print(f"warning: vocabulary: glossary unreadable ({exc})")
        sys.exit(0)
    if not terms:
        sys.exit(0)
    if args.staged:
        lines = {p: numbered for p, numbered in staged_lines(project).items()
                 if (project / p).resolve() != glossary.resolve()}
        for synonym, place in find_synonyms(lines, Checker.of(terms)):
            print(f"warning: vocabulary: {place}: {describe(synonym)}")
    else:
        print(report(project, glossary, terms))
    sys.exit(0)


if __name__ == "__main__":
    main()
