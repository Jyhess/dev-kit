"""Tests of plugins/core/scripts/private_words.py on a small repository."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "core" / "scripts"))
import git_paths  # noqa: E402
import private_words  # noqa: E402

ZERO = "0" * 40


class PrivateWordsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        self.list = self.tmp / "private-words.txt"
        self.list.write_text("# private projects\nSecretCo\n\nhush  # code name\nSociété\n", encoding="utf-8")
        self.shared = self.tmp / "dev-journal" / "private-words"
        self.real_shared_list = private_words.shared_list
        patcher = mock.patch.object(private_words, "shared_list", lambda: self.shared)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=T", "-c", "user.email=t@example.com",
                               *args], capture_output=True, text=True, check=True).stdout.strip()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, files, message="change"):
        for name, text in files.items():
            self.write(name, text)
            self.git("add", name)
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def run_check(self, refs=None, remote=None):
        """Exit code and errors; `refs` are the pre-push stdin lines, None for a run outside a push."""
        args = ["--repo", str(self.repo), "--list", str(self.list)]
        if remote is not None:
            args += ["--remote", remote]
        if refs is not None:
            args.append("--stdin-refs")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch("sys.stdin", io.StringIO("".join(refs or []))):
            code = private_words.main(args)
        return code, err.getvalue()

    def push_line(self, local, remote=ZERO, ref="refs/heads/main"):
        return f"{ref} {local} {ref} {remote}\n"

    def test_words_ignore_comments_blank_lines_and_case(self):
        self.assertEqual(private_words.read_words(self.list), ["secretco", "hush", "société"])

    def test_word_in_a_pushed_file_or_path_fails(self):
        sha = self.commit({"docs/a.md": "# A\n\nBuilt for SECRETCO.\n", "hush/b.txt": "nothing\n"})
        code, err = self.run_check([self.push_line(sha)])
        self.assertEqual(code, 1)
        self.assertIn(f"{sha[:12]} docs/a.md:3: secretco", err)
        self.assertIn(f"{sha[:12]} hush/b.txt: hush", err)

    def test_added_line_that_looks_like_a_diff_header_is_read(self):
        sha = self.commit({"a.md": "x\n++ hush\n"})
        code, err = self.run_check([self.push_line(sha)])
        self.assertEqual(code, 1)
        self.assertIn(f"{sha[:12]} a.md:2: hush", err)

    def test_word_in_the_path_of_a_binary_file_fails(self):
        (self.repo / "hush.bin").write_bytes(b"\x00\xff")
        self.git("add", "hush.bin")
        sha = self.commit({})
        code, err = self.run_check([self.push_line(sha)])
        self.assertEqual(code, 1)
        self.assertIn(f"{sha[:12]} hush.bin: hush", err)

    def test_word_removed_from_the_working_tree_only_still_fails(self):
        sha = self.commit({"a.md": "secretco\n"})
        self.write("a.md", "clean\n")
        code, err = self.run_check([self.push_line(sha)])
        self.assertEqual(code, 1)
        self.assertIn(f"{sha[:12]} a.md:1: secretco", err)

    def test_word_in_a_commit_message_fails(self):
        sha = self.commit({"a.md": "clean\n"}, "Fix for SecretCo")
        code, err = self.run_check([self.push_line(sha)])
        self.assertEqual(code, 1)
        self.assertIn(f"{sha[:12]} (message): secretco", err)

    def test_word_in_a_commit_hidden_by_a_later_one_fails(self):
        first = self.commit({"a.md": "secretco\n"})
        last = self.commit({"a.md": "clean\n"})
        code, err = self.run_check([self.push_line(last)])
        self.assertEqual(code, 1)
        self.assertIn(f"{first[:12]} a.md:1: secretco", err)

    def test_non_ascii_word_and_text_are_read_as_utf8(self):
        sha = self.commit({"a.md": "Fait pour la Société.\n"})
        code, err = self.run_check([self.push_line(sha)])
        self.assertEqual(code, 1)
        self.assertIn(f"{sha[:12]} a.md:1: société", err)

    def test_only_the_pushed_range_is_checked(self):
        old = self.commit({"a.md": "secretco\n"}, "hush")
        new = self.commit({"b.md": "clean\n"})
        self.assertEqual(self.run_check([self.push_line(new, old)]), (0, ""))

    def test_new_branch_skips_commits_on_a_remote_ref(self):
        old = self.commit({"a.md": "secretco\n"})
        self.git("update-ref", "refs/remotes/origin/main", old)
        new = self.commit({"b.md": "clean\n"})
        self.assertEqual(self.run_check([self.push_line(new, ref="refs/heads/topic")]), (0, ""))

    def test_unknown_remote_sha_checks_the_commits_on_no_remote_ref(self):
        sha = self.commit({"a.md": "secretco\n"})
        code, _ = self.run_check([self.push_line(sha, "1" * 40)])
        self.assertEqual(code, 1)

    def test_deleted_ref_is_skipped(self):
        sha = self.commit({"a.md": "secretco\n"})
        self.assertEqual(self.run_check([self.push_line(ZERO, sha)]), (0, ""))

    def test_outside_a_push_the_commits_of_head_on_no_remote_ref_are_checked(self):
        old = self.commit({"a.md": "secretco\n"})
        self.git("update-ref", "refs/remotes/origin/main", old)
        self.assertEqual(self.run_check(), (0, ""))
        sha = self.commit({"b.md": "hush\n"})
        code, err = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn(f"{sha[:12]} b.md:1: hush", err)

    def test_binary_files_and_removed_lines_are_not_read(self):
        self.commit({"a.md": "secretco\n"})
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        (self.repo / "blob.bin").write_bytes(b"\x00\xff\xfesecretco")
        self.git("add", "blob.bin")
        self.write("a.md", "clean\n")
        self.git("add", "a.md")
        self.git("commit", "-q", "-m", "binary")
        self.assertEqual(self.run_check(), (0, ""))

    def test_default_list_is_the_one_of_the_main_clone_also_from_a_worktree(self):
        self.commit({"a.md": "secretco\n"})
        worktree = self.tmp / "worktree"
        self.git("worktree", "add", "-q", str(worktree))
        self.assertEqual(private_words.default_list(worktree).resolve(), (self.repo / ".private-words").resolve())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(private_words.main(["--repo", str(worktree)]), 0)
            (self.repo / ".private-words").write_text("secretco\n", encoding="utf-8")
            self.assertEqual(private_words.main(["--repo", str(worktree)]), 1)

    def test_shared_list_is_in_the_journal_clone_next_to_the_dev_kit_main_clone(self):
        self.assertEqual(self.real_shared_list(),
                         git_paths.main_clone(ROOT).parent / "dev-journal" / "private-words")

    def test_shared_list_applies_to_every_project_with_its_own_list(self):
        self.shared.parent.mkdir()
        self.shared.write_text("Shared\n", encoding="utf-8")
        self.commit({"a.md": "shared\n", "b.md": "own\n"})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(private_words.main(["--repo", str(self.repo)]), 1)
            self.assertIn("a.md:1: shared", err.getvalue())
            (self.repo / ".private-words").write_text("own\n", encoding="utf-8")
            self.assertEqual(private_words.main(["--repo", str(self.repo)]), 1)
            self.assertIn("b.md:1: own", err.getvalue())

    def test_words_naming_the_project_itself_are_skipped(self):
        self.list.write_text("Repo\nMyApp\nhush\n", encoding="utf-8")
        self.git("remote", "add", "origin", "git@github.com:Owner/MyApp.git")
        sha = self.commit({"repo.md": "# MyApp\n\nRepo hush\n"}, "Start MyApp")
        code, err = self.run_check([self.push_line(sha)])
        self.assertEqual(code, 1)
        self.assertEqual(err.splitlines()[:-1], [f"{sha[:12]} repo.md:3: hush"])

    def test_own_names_are_the_main_clone_folder_and_the_origin_repository(self):
        self.commit({})
        worktree = self.tmp / "worktree"
        self.git("worktree", "add", "-q", str(worktree))
        self.assertEqual(private_words.own_names(worktree), {"repo"})
        for url in ("https://github.com/Owner/MyApp.git", "https://github.com/Owner/MyApp/",
                    "git@github.com:Owner/MyApp", r"C:\src\MyApp"):
            self.git("remote", "add", "origin", url)
            self.assertEqual(private_words.own_names(worktree), {"repo", "myapp"}, url)
            self.git("remote", "remove", "origin")

    def test_without_the_list_nothing_is_checked(self):
        self.commit({"a.md": "secretco\n"})
        self.list = self.tmp / "missing.txt"
        self.assertEqual(self.run_check(), (0, ""))

    def check_with_visibility(self, visibility, remote="origin"):
        """Exit code of a check of a commit with a private word, `gh` giving `visibility`; the URLs asked to `gh`."""
        self.commit({"a.md": "secretco\n"})
        self.git("remote", "add", "origin", "git@github.com:me/other.git")
        with mock.patch.object(private_words, "gh_visibility", return_value=visibility) as gh:
            code, _ = self.run_check(remote=remote)
        self.git("remote", "remove", "origin")
        return code, [c.args[0] for c in gh.call_args_list]

    def test_private_or_internal_github_remote_is_not_checked(self):
        for visibility in ("PRIVATE", "INTERNAL"):
            with self.subTest(visibility):
                self.assertEqual(self.check_with_visibility(visibility), (0, ["git@github.com:me/other.git"]))

    def test_public_or_unknown_visibility_is_checked(self):
        for visibility in ("PUBLIC", None):
            with self.subTest(visibility):
                self.assertEqual(self.check_with_visibility(visibility)[0], 1)

    def test_remote_given_as_a_url_is_asked_as_is(self):
        url = "https://github.com/me/pushed.git"
        self.assertEqual(self.check_with_visibility("PRIVATE", remote=url), (0, [url]))

    def test_remote_off_github_is_checked_without_asking_gh(self):
        self.assertEqual(self.check_with_visibility("PRIVATE", remote="/srv/repo.git"), (1, []))

    def test_gh_failure_or_timeout_gives_no_visibility(self):
        failed = subprocess.CompletedProcess([], 1, "", "not found")
        for outcome in (failed, subprocess.TimeoutExpired("gh", 1), OSError()):
            with self.subTest(outcome), mock.patch("shutil.which", return_value="gh"), \
                    mock.patch("subprocess.run", side_effect=[outcome]):
                self.assertIsNone(private_words.gh_visibility("https://github.com/me/x"))
        with mock.patch("shutil.which", return_value=None):
            self.assertIsNone(private_words.gh_visibility("https://github.com/me/x"))


if __name__ == "__main__":
    unittest.main()
