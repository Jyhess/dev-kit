"""The main clone of a git repository, also seen from one of its worktrees.

Shared by the hooks and scripts that keep files in the main clone (the ignored
`.private-words`, `history/`, a wiki beside it). Git prints paths in UTF-8,
whatever the console encoding (cp1252 on Windows).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

TIMEOUT_S = 5


def main_clone(folder: Path) -> Path | None:
    """Working tree of the main clone of the repository holding `folder`; None outside a repository."""
    try:
        result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    common = Path(result.stdout.strip())
    return common.parent if result.returncode == 0 and common.name == ".git" else None
