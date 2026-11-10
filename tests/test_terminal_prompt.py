"""End-to-end tests of terminal/starship.toml: the prompt starship prints in throwaway repositories."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "terminal" / "starship.toml"
STARSHIP = shutil.which("starship")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TIME = re.compile(r"^\d{2}:\d{2} ")
WINDOWS_ENV = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def commit(repo: Path, name: str) -> None:
    (repo / name).write_text(name, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name)


@unittest.skipUnless(STARSHIP, "starship is not installed")
class PromptTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()  # macOS: /var is a link to /private/var
        remote = self.home / "remote.git"
        git(self.home, "init", "-q", "--bare", "-b", "main", str(remote))
        self.repo = self.home / "dvp" / "dev-kit"
        git(self.home, "clone", "-q", str(remote), str(self.repo))
        git(self.repo, "checkout", "-q", "-b", "main")
        commit(self.repo, "a")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        self.other = self.home / "other"
        git(self.home, "clone", "-q", str(remote), str(self.other))

    def prompt(self, cwd: Path, status: int = 0) -> str:
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "STARSHIP_CONFIG": str(CONFIG),
               "STARSHIP_CACHE": str(self.home / ".cache"), "GIT_CONFIG_GLOBAL": os.devnull,
               # Windows: starship takes ~ from USERPROFILE, and git needs the system variables
               "USERPROFILE": str(self.home),
               **{k: os.environ[k] for k in WINDOWS_ENV if k in os.environ}}
        out = subprocess.run([STARSHIP, "prompt", f"--status={status}", "--terminal-width=200"], cwd=cwd,
                             env=env, check=True, capture_output=True, text=True).stdout
        text = ANSI.sub("", out).strip()
        self.assertRegex(text, TIME)
        return TIME.sub("HH:MM ", text)

    def test_behind_ahead_and_counters(self):
        commit(self.other, "b")
        commit(self.other, "c")
        git(self.other, "push", "-q")
        git(self.repo, "fetch", "-q")
        commit(self.repo, "d")
        (self.repo / "staged").write_text("x", encoding="utf-8")
        git(self.repo, "add", "staged")
        (self.repo / "a").write_text("changed", encoding="utf-8")
        (self.repo / "d").write_text("changed", encoding="utf-8")
        for name in ("u1", "u2", "u3"):
            (self.repo / name).write_text(name, encoding="utf-8")
        self.assertEqual(self.prompt(self.repo), "HH:MM dev-kit main ↓2 ↑1 +1 ~2 ?3 %")

    def test_deleted_file_counter(self):
        (self.repo / "a").unlink()
        self.assertEqual(self.prompt(self.repo), "HH:MM dev-kit main ✓ -1 %")

    def test_up_to_date_and_clean(self):
        self.assertEqual(self.prompt(self.repo), "HH:MM dev-kit main ✓ %")

    def test_up_to_date_with_modified_files(self):
        commit(self.repo, "b")
        git(self.repo, "push", "-q")
        (self.repo / "a").write_text("changed", encoding="utf-8")
        (self.repo / "b").write_text("changed", encoding="utf-8")
        self.assertEqual(self.prompt(self.repo), "HH:MM dev-kit main ✓ ~2 %")

    def test_sub_folder_shows_the_path_from_the_repository(self):
        sub = self.repo / "plugins" / "core"
        sub.mkdir(parents=True)
        self.assertEqual(self.prompt(sub), "HH:MM dev-kit/plugins/core main ✓ %")

    def test_outside_a_repository(self):
        if sys.platform == "win32":
            # starship takes the home folder from Windows itself, not from the environment
            tmp = tempfile.TemporaryDirectory(dir=Path.home(), ignore_cleanup_errors=True)
            self.addCleanup(tmp.cleanup)
            folder = Path(tmp.name) / "dvp"
            folder.mkdir()
            self.assertEqual(self.prompt(folder), f"HH:MM ~/{Path(tmp.name).name}/dvp %")
        else:
            self.assertEqual(self.prompt(self.home / "dvp"), "HH:MM ~/dvp %")

    def test_failed_command_shows_its_exit_code(self):
        self.assertEqual(self.prompt(self.repo, status=1), "HH:MM dev-kit main ✓ 1 %")

    def test_detached_head_shows_the_short_hash(self):
        head = git(self.repo, "rev-parse", "--short", "HEAD")
        git(self.repo, "checkout", "-q", "--detach")
        self.assertEqual(self.prompt(self.repo), f"HH:MM dev-kit {head} %")

    def test_conflict_counter(self):
        commit(self.other, "conflict")
        git(self.other, "push", "-q")
        (self.repo / "conflict").write_text("mine", encoding="utf-8")
        git(self.repo, "add", "conflict")
        git(self.repo, "commit", "-q", "-m", "mine")
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t", "pull", "-q",
                        "--no-rebase"], capture_output=True)
        self.assertIn(" !1", self.prompt(self.repo))


if __name__ == "__main__":
    unittest.main()
