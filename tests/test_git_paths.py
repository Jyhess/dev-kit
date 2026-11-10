"""Tests of plugins/core/scripts/git_paths.py: the main clone of a repository."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "core" / "scripts"))
import git_paths  # noqa: E402

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com"]


class MainCloneTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.repo = self.tmp / "dépôt café"
        subprocess.run(GIT + ["init", "-q", str(self.repo)], check=True)
        subprocess.run(GIT + ["-C", str(self.repo), "commit", "-q", "--allow-empty", "-m", "init"], check=True)

    def test_main_clone_of_the_clone_itself(self):
        self.assertEqual(git_paths.main_clone(self.repo), self.repo)

    def test_main_clone_of_a_worktree_with_a_non_ascii_path(self):
        worktree = self.repo / ".claude" / "worktrees" / "tâche"
        subprocess.run(GIT + ["-C", str(self.repo), "worktree", "add", "-q", str(worktree)], check=True)
        self.assertEqual(git_paths.main_clone(worktree), self.repo)

    def test_outside_a_repository_is_none(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        self.assertIsNone(git_paths.main_clone(outside))

    def test_missing_folder_is_none(self):
        self.assertIsNone(git_paths.main_clone(self.tmp / "missing"))


if __name__ == "__main__":
    unittest.main()
