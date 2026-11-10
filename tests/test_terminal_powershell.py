"""Tests of terminal/powershell/dev-kit.ps1 with pwsh: startup, aliases, .env.ps1 and the background fetch."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "terminal" / "powershell" / "dev-kit.ps1"
PWSH = shutil.which("pwsh")
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull}


def ps_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


@unittest.skipUnless(PWSH and sys.platform == "win32",
                     "the PowerShell configuration is for Windows (it uses cmd and hidden windows)")
class PowerShellConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()

    def pwsh(self, script: str) -> subprocess.CompletedProcess:
        command = f". {ps_path(CONFIG)}\n{script}"
        return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
                              env={**os.environ, **GIT_ENV}, capture_output=True, text=True,
                              encoding="utf-8", timeout=60)

    def out(self, script: str) -> str:
        result = self.pwsh(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.strip(), "")
        return result.stdout.strip()

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                              env={**os.environ, **GIT_ENV}).stdout.strip()

    def commit(self, repo: Path, name: str) -> None:
        (repo / name).write_text(name, encoding="utf-8")
        self.git(repo, "add", name)
        self.git(repo, "commit", "-q", "-m", name)

    def test_loads_without_error(self):
        self.assertEqual(self.out("'loaded'"), "loaded")

    def test_git_functions_win_over_the_builtin_aliases(self):
        out = self.out("(Get-Command gl).CommandType; (Get-Command gp).CommandType; ${function:gpf}.ToString().Trim()")
        self.assertEqual(out.splitlines(), ["Function", "Function", "git push --force-with-lease @args"])

    def test_shared_aliases_exist(self):
        out = self.out("'gr','gs','glog','grim','grum','up','down','logs' | ForEach-Object { (Get-Command $_).CommandType }")
        self.assertEqual(set(out.splitlines()), {"Function"})
        self.assertIn("up -d", self.out("${function:up}.ToString()"))

    def test_dotnet_aliases_only_in_a_dotnet_project(self):
        repo = self.tmp / "app"
        (repo / "src" / "deep").mkdir(parents=True)
        self.git(repo, "init", "-q")
        (repo / "app.sln").write_text("", encoding="utf-8")
        plain = self.tmp / "plain"
        plain.mkdir()
        out = self.out(f"""
            Set-Location {ps_path(repo / 'src' / 'deep')}; [bool](Get-Command dw -ErrorAction SilentlyContinue)
            ${{function:dt}}.ToString().Trim()
            Set-Location {ps_path(plain)}; [bool](Get-Command dw -ErrorAction SilentlyContinue)
            Push-Location {ps_path(repo)}; [bool](Get-Command dr -ErrorAction SilentlyContinue)
        """)
        self.assertEqual(out.splitlines(), ["True", "dotnet test @args", "False", "True"])

    def test_dotnet_project_file_outside_the_repository_does_not_count(self):
        (self.tmp / "outer.csproj").write_text("", encoding="utf-8")
        repo = self.tmp / "repo"
        repo.mkdir()
        self.git(repo, "init", "-q")
        out = self.out(f"Set-Location {ps_path(repo)}; [bool](Get-Command db -ErrorAction SilentlyContinue)")
        self.assertEqual(out, "False")

    def test_env_file_is_loaded_on_entering_its_folder(self):
        project = self.tmp / "project"
        project.mkdir()
        (project / ".env.ps1").write_text("$env:DEVKIT_TEST = 'loaded'\n", encoding="utf-8")
        out = self.out(f"Set-Location {ps_path(project)}; $env:DEVKIT_TEST; $env:DEVKIT_TEST = $null; "
                       f"Set-Location {ps_path(self.tmp)}; Push-Location {ps_path(project)}; $env:DEVKIT_TEST")
        self.assertEqual([line for line in out.splitlines() if "Loading" not in line], ["loaded", "loaded"])

    def test_changing_folder_keeps_the_last_exit_code(self):
        out = self.out(f"cmd /c exit 3; Set-Location {ps_path(self.tmp)}; $LASTEXITCODE")
        self.assertEqual(out, "3")

    def _repo_behind_remote(self, remote_url=None):
        remote = self.tmp / "remote.git"
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(remote))
        repo, other = self.tmp / "repo", self.tmp / "other"
        for clone in (repo, other):
            self.git(self.tmp, "clone", "-q", str(remote), str(clone))
            self.git(clone, "checkout", "-q", "-B", "main")
        self.commit(repo, "a")
        self.git(repo, "push", "-q", "-u", "origin", "main")
        self.git(other, "pull", "-q", "origin", "main")
        self.commit(other, "b")
        self.git(other, "push", "-q", "origin", "main")
        if remote_url:
            self.git(repo, "remote", "set-url", "origin", remote_url)
        fetch_head = repo / ".git" / "FETCH_HEAD"
        fetch_head.write_text("", encoding="utf-8")
        old = time.time() - 600
        os.utime(fetch_head, (old, old))
        return repo

    def test_stale_repository_is_fetched_in_the_background(self):
        repo = self._repo_behind_remote()
        self.out(f"Set-Location {ps_path(repo)}; Start-DevKitFetch")
        for _ in range(50):
            if self.git(repo, "rev-list", "--count", "HEAD..origin/main") == "1":
                break
            time.sleep(0.2)
        self.assertEqual(self.git(repo, "rev-list", "--count", "HEAD..origin/main"), "1")

    def test_unreachable_remote_stays_silent(self):
        repo = self._repo_behind_remote(remote_url=str(self.tmp / "missing.git"))
        self.assertEqual(self.out(f"Set-Location {ps_path(repo)}; Start-DevKitFetch; 'ok'"), "ok")


    def _feature_behind_origin(self):
        """A clone on `feature` with an uncommitted change, origin's main one commit ahead of it."""
        repo = self._repo_behind_remote()
        self.git(repo, "remote", "set-head", "origin", "main")
        self.git(repo, "checkout", "-q", "-b", "feature")
        self.commit(repo, "c")
        (repo / "a").write_text("edited", encoding="utf-8")
        return repo

    def test_grum_fetches_and_rebases_on_origin_default_branch_without_checkout(self):
        repo = self._feature_behind_origin()
        local_main = self.git(repo, "rev-parse", "main")
        self.pwsh(f"Set-Location {ps_path(repo)}; grum")
        self.assertEqual(self.git(repo, "rev-parse", "--abbrev-ref", "HEAD"), "feature")
        self.assertEqual(self.git(repo, "rev-parse", "HEAD~1"), self.git(repo, "rev-parse", "origin/main"))
        self.assertEqual(self.git(repo, "rev-parse", "main"), local_main)
        self.assertEqual((repo / "a").read_text(encoding="utf-8"), "edited")

    def test_grim_rebases_interactively_on_origin_default_branch(self):
        repo = self._feature_behind_origin()
        self.pwsh(f"$env:GIT_SEQUENCE_EDITOR = ':'; Set-Location {ps_path(repo)}; grim")
        self.assertEqual(self.git(repo, "rev-parse", "HEAD~1"), self.git(repo, "rev-parse", "origin/main"))
        self.assertEqual((repo / "a").read_text(encoding="utf-8"), "edited")

if __name__ == "__main__":
    unittest.main()
