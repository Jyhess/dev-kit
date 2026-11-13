"""Tests of terminal/zsh/dev-kit.zsh with zsh: .NET aliases and the background fetch."""

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "terminal" / "zsh" / "dev-kit.zsh"
ZSH = shutil.which("zsh")
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull}


@unittest.skipUnless(ZSH, "zsh is not installed")
class ZshConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()

    def zsh(self, script: str) -> subprocess.CompletedProcess:
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), **GIT_ENV}
        return subprocess.run([ZSH, "-fc", f"source {CONFIG}\n{script}"], env=env, capture_output=True,
                              text=True, timeout=30)

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                              env={**os.environ, **GIT_ENV}).stdout.strip()

    def commit(self, repo: Path, name: str) -> None:
        (repo / name).write_text(name, encoding="utf-8")
        self.git(repo, "add", name)
        self.git(repo, "commit", "-q", "-m", name)

    # .NET aliases

    def test_dotnet_aliases_only_in_a_dotnet_project(self):
        repo = self.home / "app"
        (repo / "src" / "Web").mkdir(parents=True)
        self.git(repo, "init", "-q")
        (repo / "App.sln").write_text("", encoding="utf-8")
        result = self.zsh(f"cd {repo}/src/Web; alias db; whence -w dc\ncd {self.home}; whence -w db || echo none")
        self.assertEqual(result.stdout.splitlines(), ["db='dotnet build'", "dc: alias", "db: none", "none"])

    def test_parent_dotnet_project_outside_a_repository_does_not_count(self):
        (self.home / "app" / "src").mkdir(parents=True)
        (self.home / "app" / "App.csproj").write_text("", encoding="utf-8")
        result = self.zsh(f"cd {self.home}/app; whence -w dt\ncd {self.home}/app/src; whence -w dt || true")
        self.assertEqual(result.stdout.splitlines(), ["dt: alias", "dt: none"])

    def test_shared_aliases(self):
        result = self.zsh("alias gpf; whence -w up grum")
        self.assertEqual(result.stdout.splitlines(),
                         ["gpf='git push --force-with-lease'", "up: function", "grum: function"])

    def feature_behind_origin(self) -> Path:
        """A clone on `feature` with an uncommitted change, origin's main one commit ahead of it."""
        repo = self.clone_behind()
        self.git(repo, "remote", "set-head", "origin", "main")
        self.git(repo, "checkout", "-q", "-b", "feature")
        self.commit(repo, "c")
        (repo / "a").write_text("edited", encoding="utf-8")
        return repo

    def test_grum_fetches_and_rebases_on_origin_default_branch_without_checkout(self):
        repo = self.feature_behind_origin()
        local_main = self.git(repo, "rev-parse", "main")
        result = self.zsh(f"cd {repo}; grum")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(repo, "rev-parse", "--abbrev-ref", "HEAD"), "feature")
        self.assertEqual(self.git(repo, "rev-parse", "HEAD~1"), self.git(repo, "rev-parse", "origin/main"))
        self.assertEqual(self.git(repo, "rev-parse", "main"), local_main)
        self.assertEqual((repo / "a").read_text(encoding="utf-8"), "edited")

    def test_grim_rebases_interactively_on_origin_default_branch(self):
        repo = self.feature_behind_origin()
        result = self.zsh(f"cd {repo}; GIT_SEQUENCE_EDITOR=: grim")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(repo, "rev-parse", "HEAD~1"), self.git(repo, "rev-parse", "origin/main"))
        self.assertEqual((repo / "a").read_text(encoding="utf-8"), "edited")

    # Background fetch

    def clone_behind(self) -> Path:
        remote = self.home / "remote.git"
        self.git(self.home, "init", "-q", "--bare", "-b", "main", str(remote))
        repo, other = self.home / "repo", self.home / "other"
        self.git(self.home, "clone", "-q", str(remote), str(repo))
        self.git(repo, "checkout", "-q", "-b", "main")
        self.commit(repo, "a")
        self.git(repo, "push", "-q", "-u", "origin", "main")
        self.git(self.home, "clone", "-q", str(remote), str(other))
        self.commit(other, "b")
        self.git(other, "push", "-q")
        return repo

    def behind(self, repo: Path) -> int:
        return int(self.git(repo, "rev-list", "--count", "HEAD..@{u}"))

    def age_fetch_head(self, repo: Path, minutes: int) -> None:
        head = repo / ".git" / "FETCH_HEAD"
        head.touch()
        old = time.time() - minutes * 60
        os.utime(head, (old, old))

    def test_stale_fetch_head_fetches_in_the_background(self):
        repo = self.clone_behind()
        self.age_fetch_head(repo, 6)
        result = self.zsh(f"cd {repo}; _devkit_fetch")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        deadline = time.time() + 10
        while self.behind(repo) == 0 and time.time() < deadline:
            time.sleep(0.2)
        self.assertEqual(self.behind(repo), 1)

    def test_recent_fetch_head_does_not_fetch(self):
        repo = self.clone_behind()
        self.age_fetch_head(repo, 1)
        self.zsh(f"cd {repo}; _devkit_fetch")
        time.sleep(1)
        self.assertEqual(self.behind(repo), 0)

    def test_unreachable_remote_is_silent_and_instant(self):
        repo = self.clone_behind()
        self.git(repo, "remote", "set-url", "origin", str(self.home / "gone.git"))
        start = time.time()
        result = self.zsh(f"cd {repo}; _devkit_fetch")
        self.assertLess(time.time() - start, 2)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_outside_a_repository_does_nothing(self):
        result = self.zsh(f"cd {self.home}; _devkit_fetch; echo done")
        self.assertEqual((result.stdout, result.stderr), ("done\n", ""))

    # Terminal title

    def test_title_names_the_project_and_the_folder(self):
        (self.home / "Documents").mkdir()
        shop = self.home / "dev" / "shop"
        (shop / "ci" / "ci-runners").mkdir(parents=True)
        self.git(shop, "init", "-q")
        worktree = self.home / "dev" / "shop_main"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
        folders = [shop, shop / "ci" / "ci-runners", worktree, self.home / "Documents", self.home, "/usr"]
        result = self.zsh("\n".join(f"cd {f}; _devkit_title" for f in folders))
        self.assertEqual(result.stdout.splitlines(),
                         ["shop", "shop : ci-runners", "shop_main", "~/Documents", "~", "/usr"])

    def test_title_is_written_at_each_prompt(self):
        result = self.zsh(f"cd {self.home}; _devkit_set_title; print; print -l $precmd_functions")
        self.assertEqual(result.stdout.splitlines()[0], "\x1b]0;~\a")
        self.assertIn("_devkit_set_title", result.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
