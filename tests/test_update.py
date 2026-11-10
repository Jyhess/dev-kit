"""Tests of plugins/core/scripts/update.py on throwaway Git repositories."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "plugins" / "core" / "scripts" / "update.py"
sys.path.insert(0, str(UPDATE.parent))
import update  # noqa: E402


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def commit(repo, name):
    (Path(repo) / name).write_text(name, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-q", "-m", name)


def run_update(repo):
    result = subprocess.run([sys.executable, str(UPDATE), "--repo", str(repo)],
                            capture_output=True, text=True, encoding="utf-8")
    return result.returncode, json.loads(result.stdout)["systemMessage"] if result.stdout.strip() else None


class UpdateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Git objects are read-only on Windows
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        self.author = self.tmp / "author"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.author)], check=True,
                       capture_output=True)
        git(self.author, "checkout", "-q", "-b", "main")
        commit(self.author, "first")
        git(self.author, "push", "-q", "-u", "origin", "main")
        self.clone = self.tmp / "clone"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.clone)], check=True)

    def test_up_to_date_prints_nothing(self):
        self.assertEqual(run_update(self.clone), (0, None))

    def test_fast_forwards_new_commits(self):
        commit(self.author, "second")
        commit(self.author, "third")
        git(self.author, "push", "-q")
        code, message = run_update(self.clone)
        self.assertEqual(code, 0)
        self.assertIn("2 commits", message)
        self.assertEqual(git(self.clone, "rev-parse", "HEAD"), git(self.author, "rev-parse", "HEAD"))

    def test_unreachable_remote_warns_and_changes_nothing(self):
        git(self.clone, "remote", "set-url", "origin", str(self.tmp / "missing.git"))
        head = git(self.clone, "rev-parse", "HEAD")
        code, message = run_update(self.clone)
        self.assertEqual(code, 0)
        self.assertIn("hors ligne", message)
        self.assertEqual(git(self.clone, "rev-parse", "HEAD"), head)

    def test_diverged_clone_warns_and_changes_nothing(self):
        commit(self.author, "remote-side")
        git(self.author, "push", "-q")
        commit(self.clone, "local-side")
        head = git(self.clone, "rev-parse", "HEAD")
        code, message = run_update(self.clone)
        self.assertEqual(code, 0)
        self.assertIn("divergé", message)
        self.assertEqual(git(self.clone, "rev-parse", "HEAD"), head)

    def test_merged_branch_goes_back_to_the_default_branch(self):
        git(self.clone, "checkout", "-q", "-b", "feature")
        commit(self.author, "second")
        git(self.author, "push", "-q")
        code, message = run_update(self.clone)
        self.assertEqual(code, 0)
        self.assertIn("retour sur main", message)
        self.assertIn("1 commit", message)
        self.assertEqual(git(self.clone, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(git(self.clone, "rev-parse", "HEAD"), git(self.author, "rev-parse", "HEAD"))

    def test_merged_branch_without_local_default_branch_creates_it(self):
        git(self.clone, "checkout", "-q", "-b", "feature")
        git(self.clone, "branch", "-q", "-D", "main")
        code, message = run_update(self.clone)
        self.assertIn("retour sur main", message)
        self.assertEqual(git(self.clone, "rev-parse", "--abbrev-ref", "main@{u}"), "origin/main")

    def test_unmerged_branch_warns_and_changes_nothing(self):
        git(self.clone, "checkout", "-q", "-b", "feature")
        commit(self.clone, "work")
        head = git(self.clone, "rev-parse", "HEAD")
        code, message = run_update(self.clone)
        self.assertEqual(code, 0)
        self.assertIn("« feature », pas sur main", message)
        self.assertEqual(git(self.clone, "rev-parse", "--abbrev-ref", "HEAD"), "feature")
        self.assertEqual(git(self.clone, "rev-parse", "HEAD"), head)

    def test_merged_branch_with_local_changes_warns_and_changes_nothing(self):
        git(self.clone, "checkout", "-q", "-b", "feature")
        (self.clone / "first").write_text("edited", encoding="utf-8")
        code, message = run_update(self.clone)
        self.assertIn("pas sur main", message)
        self.assertEqual(git(self.clone, "rev-parse", "--abbrev-ref", "HEAD"), "feature")
        self.assertEqual((self.clone / "first").read_text(encoding="utf-8"), "edited")

    def test_folder_without_upstream_prints_nothing(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertEqual(run_update(plain), (0, None))



class TotalTimeTest(unittest.TestCase):
    """Every git call hangs SLOW_S seconds on a fake clock: the whole update stays under the hook's timeout."""
    SLOW_S = 6

    def setUp(self):
        self.clock = 0.0
        originals = (update.subprocess.run, update.time.monotonic, sys.argv)
        self.addCleanup(self.restore, originals)
        update.subprocess.run = self.slow_git
        update.time.monotonic = lambda: self.clock
        sys.argv = ["update.py", "--repo", "clone"]

    @staticmethod
    def restore(originals):
        update.subprocess.run, update.time.monotonic, sys.argv = originals

    def slow_git(self, command, timeout=None, **kwargs):
        self.clock += min(self.SLOW_S, timeout)
        if timeout < self.SLOW_S:
            raise subprocess.TimeoutExpired(command, timeout)
        out = {"HEAD": "main", "origin/HEAD": "origin/main", "@{u}": "origin/main"}.get(command[-1], "3")
        return subprocess.CompletedProcess(command, 0, out, "")

    def test_slow_git_calls_are_cut_at_the_total_limit(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as end:
            update.main()
        self.assertEqual(end.exception.code, 0)
        self.assertLessEqual(self.clock, update.TOTAL_TIMEOUT_S)
        self.assertIn("interrompue", json.loads(output.getvalue())["systemMessage"])


if __name__ == "__main__":
    unittest.main()
