#!/usr/bin/env python3
"""Refuse pushed commits that contain a private word. Run by the pre-push hook.

    python3 plugins/core/scripts/private_words.py [--stdin-refs] [--remote NAME] [--list FILE ...]

The check protects public repositories only: nothing is checked when the
pushed remote (`--remote`, a name or a URL, default `origin`) is a private or
internal GitHub repository, as `gh` tells. When its visibility cannot be known
(not GitHub, no `gh`, offline), it is checked.

The words come from two lists (one word per line, `#` starts a comment), so a
repository never names what it must not contain:

- `private-words` at the root of the private journal clone `dev-journal`,
  next to dev-kit's main clone: shared by every project and machine, kept
  current by the journal's pull;
- the git-ignored `.private-words` at the root of the project's main clone
  (found from worktrees too): the project's own words.

A word that names the project itself is skipped, so the shared list may name
private projects: the folder name of the project's main clone and the name of
its `origin` repository (`owner/name.git` gives `name`), compared without case.
Every other word is looked for, without case, in the message, the changed
paths and the added lines of every pushed commit. Without any list (CI)
nothing is checked.

With `--stdin-refs`, the pushed commits are read from the pre-push hook's stdin
(`<local ref> <local sha> <remote ref> <remote sha>` lines): the range
`<remote sha>..<local sha>`, or the commits on no remote ref for a new branch
(or a remote sha unknown here); a deleted ref is skipped. Without it (a run by
hand), the commits of HEAD on no remote ref are checked. Words already pushed
are not looked for again.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_paths  # noqa: E402

LIST_NAME = ".private-words"
SHARED_LIST = Path("dev-journal") / "private-words"
ZERO_SHA = re.compile(r"^0+$")
HUNK = re.compile(r"^@@ -\S+ \+(\d+)")
GITHUB_URL = re.compile(r"github\.com[:/]", re.IGNORECASE)
NOT_PUBLIC = {"PRIVATE", "INTERNAL"}
GH_TIMEOUT_SECONDS = 10


def git(repo: Path, *args: str, check: bool = True) -> str | None:
    """Output of git, decoded as UTF-8 whatever the locale; None when it fails and `check` is False."""
    result = subprocess.run(["git", "-C", str(repo), "-c", "core.quotePath=false", *args], capture_output=True)
    if result.returncode != 0:
        if check:
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
        return None
    return result.stdout.decode("utf-8", errors="replace")


def default_list(repo: Path) -> Path:
    """`.private-words` of the main clone, also when `repo` is a worktree."""
    return (git_paths.main_clone(repo) or repo) / LIST_NAME


def shared_list() -> Path | None:
    """`private-words` of the journal clone next to dev-kit's main clone; None outside a clone."""
    dev_kit = git_paths.main_clone(Path(__file__).resolve().parent)
    return dev_kit.parent / SHARED_LIST if dev_kit else None


def own_names(repo: Path) -> set[str]:
    """Names of the project: its main clone's folder and its `origin` repository, without case."""
    names = {(git_paths.main_clone(repo) or repo).resolve().name}
    url = git(repo, "remote", "get-url", "origin", check=False)
    if url and url.strip():
        names.add(re.sub(r"\.git$", "", re.split(r"[/:\\]", url.strip().rstrip("/"))[-1]))
    return {name.casefold() for name in names if name}


def gh_visibility(url: str) -> str | None:
    """`PUBLIC`, `PRIVATE` or `INTERNAL` of the GitHub repository at `url` by `gh`; None when `gh` cannot tell."""
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        result = subprocess.run([gh, "repo", "view", url, "--json", "visibility", "--jq", ".visibility"],
                                capture_output=True, text=True, timeout=GH_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def is_private(repo: Path, remote: str) -> bool:
    """True when the remote (a name, else a URL) is a private or internal GitHub repository; False if unknown."""
    url = (git(repo, "remote", "get-url", remote, check=False) or remote).strip()
    return bool(GITHUB_URL.search(url)) and gh_visibility(url) in NOT_PUBLIC


def read_words(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line.casefold() for line in lines if line]


def pushed_ranges(lines: list[str]) -> list[list[str]]:
    """`git rev-list` arguments of each pushed ref of the pre-push stdin lines."""
    ranges = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or ZERO_SHA.match(parts[1]):
            continue
        local, remote = parts[1], parts[3]
        ranges.append([local, "--not", "--remotes"] if ZERO_SHA.match(remote) else [f"{remote}..{local}"])
    return ranges


def commits(repo: Path, ranges: list[list[str]]) -> list[str]:
    """Commits of the ranges, each once; a range whose remote sha is unknown here falls back to no remote ref."""
    found: dict[str, None] = {}
    for args in ranges:
        out = git(repo, "rev-list", *args, check=False)
        if out is None:
            out = git(repo, "rev-list", args[0].split("..")[-1], "--not", "--remotes")
        found.update(dict.fromkeys(out.split()))
    return list(found)


def commit_findings(repo: Path, sha: str, words: list[str]) -> list[str]:
    """`sha path:line: word` for a word in an added line, `sha path: word` in a path, `sha (message): word`."""
    short = sha[:12]
    message = git(repo, "log", "-1", "--format=%B", sha).casefold()
    found = [f"{short} (message): {word}" for word in words if word in message]
    show = ("show", "--format=", "--no-renames", "--diff-merges=first-parent")
    for path in git(repo, *show, "--name-only", "--diff-filter=d", "-z", sha).split("\0"):
        found += [f"{short} {path}: {word}" for word in words if path and word in path.casefold()]
    diff = git(repo, *show, "--patch", "--unified=0", "--no-color", "--no-ext-diff", "--no-textconv", sha)
    path, number, header = "", 0, False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            header = True
        elif header and line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif match := HUNK.match(line):
            header, number = False, int(match.group(1))
        elif not header and line.startswith("+") and path:
            text = line[1:].casefold()
            found += [f"{short} {path}:{number}: {word}" for word in words if word in text]
            number += 1
    return found


def findings(repo: Path, words: list[str], ranges: list[list[str]]) -> list[str]:
    found = []
    for sha in commits(repo, ranges):
        found += commit_findings(repo, sha, words)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", type=Path, action="append",
                        help=f"word list, repeatable (default: {SHARED_LIST} and {LIST_NAME} of the main clone)")
    parser.add_argument("--stdin-refs", action="store_true", help="read the pushed refs of the pre-push stdin")
    parser.add_argument("--remote", default="origin", help="pushed remote, a name or a URL (default: origin)")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    lists = args.list or [path for path in (shared_list(), default_list(args.repo)) if path]
    own = own_names(args.repo)
    words = list(dict.fromkeys(word for path in lists for word in read_words(path) if word not in own))
    if not words:
        return 0
    if is_private(args.repo, args.remote):
        print(f"{args.remote} is a private repository: private words not checked", file=sys.stderr)
        return 0
    ranges = pushed_ranges(sys.stdin.read().splitlines()) if args.stdin_refs else [["HEAD", "--not", "--remotes"]]
    found = findings(args.repo, words, ranges)
    for line in found:
        print(line, file=sys.stderr)
    if found:
        names = ", ".join(str(path) for path in lists)
        print(f"private words of {names} found in pushed commits: rewrite them before pushing", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
