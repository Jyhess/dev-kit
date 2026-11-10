#!/usr/bin/env python3
"""Fast-forward the local dev-kit clone, run by the core plugin at session start.

The marketplace is the local clone, loaded in place: pulling it is how a fix
pushed from another machine arrives. Never blocks the session: it always exits
0, prints nothing when the clone is up to date, and otherwise prints one
`systemMessage` (shown to the user) as JSON.

Every git call is cut once TOTAL_TIMEOUT_S have passed since the start, so the
hook ends before Claude Code's own timeout (30 s in hooks.json).

A clone left on another branch than origin's default one would silently stop
receiving updates: when that branch is merged and the clone clean, it goes back
to the default branch; otherwise it says so at each session start.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

FETCH_TIMEOUT_S = 15
TOTAL_TIMEOUT_S = 25  # under the hook's 30 s timeout, with room for Python's start
deadline: float | None = None  # time.monotonic() value past which no git call runs; set by main()


def git(repo: Path, *args: str, timeout: float = 10) -> subprocess.CompletedProcess:
    if deadline is not None:
        timeout = min(timeout, deadline - time.monotonic())
        if timeout <= 0:
            raise subprocess.TimeoutExpired(["git", *args], 0)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout, env=env)


OFFLINE = "dev-kit : mise à jour impossible (hors ligne ?), la version locale est utilisée."
TOO_LONG = (f"dev-kit : mise à jour interrompue au bout de {TOTAL_TIMEOUT_S} s, la version locale est utilisée. "
            "Vérifie la copie locale (git status) si ce message revient.")
DIVERGED = ("dev-kit : la copie locale a divergé ou a des modifications en conflit, "
            "rien n'a été mis à jour. Synchronise-la à la main.")


def fetched(repo: Path) -> bool:
    try:
        return git(repo, "fetch", "--quiet", timeout=FETCH_TIMEOUT_S).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def commits(count: int) -> str:
    return f"{count} commit{'s' if count > 1 else ''}"


def updated(count: int, prefix: str = "dev-kit mis à jour") -> str:
    return f"{prefix} ({commits(count)}) : actif à la prochaine session, ou tout de suite avec /reload-plugins."


def default_branch(repo: Path) -> str | None:
    """`origin/main` when origin's default branch is known, else None."""
    ref = git(repo, "rev-parse", "--abbrev-ref", "origin/HEAD")
    return ref.stdout.strip() if ref.returncode == 0 and ref.stdout.strip() != "origin/HEAD" else None


def leave_branch(repo: Path, branch: str, remote: str) -> str | None:
    """The clone is on another branch than the default one, so it would never receive updates.

    A branch already merged into the default one, in a clean clone, is left for the
    default branch; otherwise the clone is left as it is, with a warning.
    """
    if not fetched(repo):
        return OFFLINE
    name = remote.split("/", 1)[1]
    behind = int(git(repo, "rev-list", "--count", f"HEAD..{remote}").stdout.strip() or 0)
    merged = git(repo, "merge-base", "--is-ancestor", "HEAD", remote).returncode == 0
    clean = not git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if not (merged and clean):
        return (f"dev-kit est sur « {branch} », pas sur {name} : les mises à jour ne sont pas récupérées "
                f"({commits(behind)} de retard sur {remote}). Repasse sur {name} une fois ce travail fusionné.")
    has_local = git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}").returncode == 0
    switch = ["checkout", "--quiet", name] if has_local else ["checkout", "--quiet", "-b", name, "--track", remote]
    if git(repo, *switch).returncode != 0:
        return DIVERGED
    if git(repo, "merge", "--ff-only", "--quiet", remote).returncode != 0:
        return DIVERGED
    return updated(behind, f"dev-kit : « {branch} » étant fusionnée, retour sur {name}")


def update(repo: Path) -> str | None:
    """Return the message to show the user, or None when there is nothing to say."""
    head = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if head.returncode != 0:
        return None  # not a git clone
    remote = default_branch(repo)
    if remote and head.stdout.strip() != remote.split("/", 1)[1]:
        return leave_branch(repo, head.stdout.strip(), remote)
    if git(repo, "rev-parse", "--abbrev-ref", "@{u}").returncode != 0:
        return None  # no upstream: nothing to pull from
    if not fetched(repo):
        return OFFLINE
    behind = int(git(repo, "rev-list", "--count", "HEAD..@{u}").stdout.strip() or 0)
    if behind == 0:
        return None
    if git(repo, "merge", "--ff-only", "--quiet", "@{u}").returncode != 0:
        return DIVERGED
    return updated(behind)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3],
                        help="dev-kit clone (default: the clone that contains this script)")
    args = parser.parse_args()
    global deadline
    deadline = time.monotonic() + TOTAL_TIMEOUT_S
    try:
        message = update(args.repo)
    except subprocess.TimeoutExpired:
        message = TOO_LONG
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        message = f"dev-kit : mise à jour impossible ({exc})."
    if message:
        print(json.dumps({"systemMessage": message}))  # ASCII escapes: safe whatever the console encoding
    sys.exit(0)


if __name__ == "__main__":
    main()
