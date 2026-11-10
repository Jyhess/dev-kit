#!/usr/bin/env python3
"""Install dev-kit on this machine. Idempotent: run it again at will.

Run it from the dev-kit clone (`python3 scripts/install.py`). It:
1. registers the clone as the `jyhess` marketplace in the user configuration,
   so its plugins are loaded in place and updated by `git pull`;
2. installs the `core`, `dev-journal` and `writing` plugins in the user
   configuration, and `humanizer` from the blader/humanizer marketplace, which
   `writing` relies on;
3. records the clone in ~/.dev-kit/config.json (`root`), where skills find
   their scripts, and links shared skills into Codex's user skill directory;
4. points the clone's Git hooks at `.githooks` (pre-push checks);
5. sets up the work journal when one is configured: clones the repository
   given by `--journal-url` (or the `journal_url` of ~/.dev-journal/config.json)
   as `dev-journal` next to dev-kit, writes the config. An existing clone is
   used as it is. Without either, the journal is skipped. The hourly scheduled
   task is created in the desktop app by hand: the script says when it is
   missing.

The Claude Code CLI is looked up on PATH, then in $CLAUDE_CLI, then in the
copy bundled with the desktop app.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

MARKETPLACE = "jyhess"
HUMANIZER = "humanizer"
PLUGINS = ("core@jyhess", "dev-journal@jyhess", "writing@jyhess", "humanizer@humanizer")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "dev-journal" / "scripts"))
import dev_journal  # noqa: E402
import install_codex  # noqa: E402

HOURLY_PROMPT = f"{dev_journal.MARKER} Lance le skill /dev-journal:hourly et suis-le, sans poser de question."
HOURLY_TASK = (f'prompt "{HOURLY_PROMPT}", schedule "5 10-19 * * 1-5" '
               "(5 past each hour, 10:05 to 19:05, Monday to Friday), no notification")

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


def run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, encoding="utf-8")


def find_claude() -> str | None:
    """Path of the Claude Code CLI, or None."""
    found = shutil.which("claude") or os.environ.get("CLAUDE_CLI")
    if found:
        return found
    bases = [Path(os.environ.get("LOCALAPPDATA", "")) / "Claude-Data",  # Windows desktop app
             Path.home() / "Library" / "Application Support" / "Claude"]  # macOS desktop app
    candidates = [p for base in bases if base.is_dir()
                  for p in base.glob("**/claude-code/*/*/claude*") if p.name in ("claude", "claude.exe")]
    return str(max(candidates, key=lambda p: p.stat().st_mtime)) if candidates else None


def listed(runner: Runner, claude: str, *args: str) -> list:
    result = runner([claude, *args, "--json"])
    if result.returncode != 0:
        raise RuntimeError(f"`claude {' '.join(args)}` failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "[]")


def install(runner: Runner, claude: str, root: Path) -> list[str]:
    """Bring this machine to the installed state; return what was done."""
    done = []
    marketplaces = {m.get("name") for m in listed(runner, claude, "plugin", "marketplace", "list")}
    for name, source in ((MARKETPLACE, str(root)), (HUMANIZER, "blader/humanizer")):
        if name not in marketplaces:
            check(runner([claude, "plugin", "marketplace", "add", source, "--scope", "user"]))
            done.append(f"marketplace {name} added from {source}")
    installed = json.dumps(listed(runner, claude, "plugin", "list"))
    for plugin_id in PLUGINS:
        if plugin_id not in installed:
            check(runner([claude, "plugin", "install", plugin_id, "--scope", "user"]))
            done.append(f"plugin {plugin_id} installed")
    hooks = runner(["git", "-C", str(root), "config", "core.hooksPath"])
    if hooks.stdout.strip() != ".githooks":
        check(runner(["git", "-C", str(root), "config", "core.hooksPath", ".githooks"]))
        done.append("Git hooks pointed at .githooks")
    return done


def machine_name(platform: str = sys.platform) -> str:
    return {"darwin": "mac", "win32": "windows"}.get(platform, platform)


def setup_journal(runner: Runner, home: Path, journal: Path, machine: str,
                  url: str | None = None) -> tuple[list[str], list[str]]:
    """Bring the work journal of this machine to the installed state; return what was done, and notes.

    `url` is the journal repository to clone; it defaults to the `journal_url` of the config.
    An existing clone is used as it is, whatever its remote.
    """
    done, notes = [], []
    state = home / ".dev-journal"
    config = dev_journal.load_json(state / "config.json", None) or {}
    url = url or config.get("journal_url")
    if not (journal / ".git").exists():
        if not url:
            notes.append("work journal skipped: run again with --journal-url <URL of your journal repository>"
                         " to set it up (see docs/dev-journal.md)")
            return done, notes
        check(runner(["git", "clone", "--quiet", url, str(journal)]))
        done.append(f"journal repository cloned into {journal}")
    wanted = {"machine": machine, "start": dt.date.today().isoformat(), **config}
    if url:
        wanted["journal_url"] = url
    if wanted != config:
        dev_journal.save_json(state / "config.json", wanted)
        done.append(f"{state / 'config.json'} written (machine {wanted['machine']})")
    tasks = {p: p.read_text(encoding="utf-8") for p in (home / ".claude" / "scheduled-tasks").glob("*/SKILL.md")}
    if not any(dev_journal.MARKER in text for text in tasks.values()):
        notes.append(f"create the hourly journal task in the desktop app: {HOURLY_TASK}")
    return done, notes


def check(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--journal-url", help="Git URL of your work journal repository (dev-journal plugin)")
    args = parser.parse_args()
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 or later is required.")
    if not shutil.which("git"):
        sys.exit("git is not on PATH.")
    claude = find_claude()
    if not claude:
        sys.exit("Claude Code CLI not found: install it, or set CLAUDE_CLI to its path.")
    try:
        done = install(run, claude, ROOT)
        done.extend(install_codex.record_root(ROOT))
        done.extend(install_codex.install(ROOT))
        done.extend(install_codex.link_rules(ROOT))
        journal_done, notes = setup_journal(run, Path.home(), dev_journal.JOURNAL_REPO, machine_name(),
                                            args.journal_url)
    except (RuntimeError, ValueError, OSError) as exc:
        sys.exit(f"Installation failed: {exc}")
    done += journal_done
    print("\n".join(done) if done else "Already installed, nothing to do.")
    for note in notes:
        print("note: " + note)


if __name__ == "__main__":
    main()
