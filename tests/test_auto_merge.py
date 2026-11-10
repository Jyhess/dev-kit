"""Tests of the auto-merge decision script (plugins/core/templates/github-scripts/auto_merge.py)."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "plugins" / "core" / "templates"
sys.path.insert(0, str(TEMPLATES / "github-scripts"))
import auto_merge  # noqa: E402
import pr_description  # noqa: E402
from auto_merge import FileChange, Hunk  # noqa: E402


def reasons(*files, config=None):
    return auto_merge.review_reasons(list(files), config or {})


BODY = "Fixes #1\n## What was done\nA fix.\n## Test results\nAll pass.\n"


def pull_request(author="owner", head_repo="owner/repo"):
    return {"user": {"login": author}, "head": {"repo": head_repo and {"full_name": head_repo}}}


def decide(*files, body=BODY, pr=None):
    return auto_merge.decide(pr or pull_request(), "owner/repo", list(files), pr_description.check(body), {})


def changed(path, removed=(), added=(), status="M"):
    return FileChange(path, status, [Hunk(list(removed), list(added))])


class FileRulesTest(unittest.TestCase):
    def test_source_changes_pass(self):
        self.assertEqual(reasons(changed("src/app.py", ["x = 1"], ["x = 2"]), changed("src/new.py", status="A")), [])

    def test_lines_added_to_tests_and_markdown_pass(self):
        self.assertEqual(reasons(changed("tests/test_app.py", [], ["def test_more(): pass"]),
                                 changed("README.md", [], ["New paragraph."])), [])

    def test_changed_test_line_goes_to_review(self):
        self.assertEqual(reasons(changed("tests/test_app.py", ["assert x == 1"], ["assert x"])),
                         ["tests/test_app.py: existing lines of a test file removed or changed"])

    def test_removed_test_line_goes_to_review(self):
        self.assertTrue(reasons(changed("app_test.go", ["\tcheck(t)"], [])))

    def test_changed_markdown_line_goes_to_review(self):
        self.assertEqual(reasons(changed("docs/rules.md", ["Ten points."], ["Five points."])),
                         ["docs/rules.md: existing lines of a Markdown file removed or changed"])

    def test_whole_comment_line_changes_pass(self):
        for old, new in (("# old", "# new"), ("  // old", "  // new"), ("/// old", "/// new"),
                         ("/* old", "/* new"), (" * old", " * new"), (" */", " */")):
            with self.subTest(old=old):
                self.assertEqual(reasons(changed("tests/test_app.py", [old], [new])), [])

    def test_comment_replaced_by_more_comments_and_code_passes(self):
        self.assertEqual(reasons(changed("FooTest.cs", ["// old"], ["// new", "// more", "Assert.True(x);"])), [])

    def test_comment_replaced_by_code_goes_to_review(self):
        self.assertTrue(reasons(changed("tests/test_app.py", ["# assert later"], ["assert x"])))

    def test_code_replaced_by_comment_goes_to_review(self):
        self.assertTrue(reasons(changed("tests/test_app.py", ["assert x"], ["# assert x"])))

    def test_removed_comment_without_replacement_goes_to_review(self):
        self.assertTrue(reasons(changed("tests/test_app.py", ["# old note"], [])))

    def test_end_of_line_comment_is_not_a_comment_line(self):
        self.assertTrue(reasons(changed("tests/test_app.py", ["x = 1  # one"], ["x = 1  # uno"])))

    def test_markdown_comments_are_html_comments_not_headings(self):
        self.assertEqual(reasons(changed("README.md", ["<!-- old -->"], ["<!-- new -->"])), [])
        self.assertTrue(reasons(changed("README.md", ["# Old title"], ["# New title"])))

    def test_deleted_file_goes_to_review(self):
        self.assertEqual(reasons(changed("src/old.py", ["x = 1"], [], status="D")), ["src/old.py: deleted"])

    def test_type_change_goes_to_review(self):
        self.assertEqual(reasons(changed("src/link", status="T")), ["src/link: changed type"])

    def test_ci_hooks_and_config_go_to_review_even_when_added(self):
        for path in (".github/workflows/x.yml", ".githooks/pre-commit", ".github/auto-merge.json",
                     ".github/scripts/auto_merge.py"):
            with self.subTest(path=path):
                self.assertEqual(reasons(changed(path, status="A")),
                                 [f"{path}: CI, hooks or auto-merge configuration"])

    def test_agent_instructions_go_to_review_even_lines_added(self):
        for path in ("AGENTS.md", "CLAUDE.md", "sub/AGENTS.md"):
            with self.subTest(path=path):
                self.assertEqual(reasons(changed(path, [], ["- new rule"])), [f"{path}: agent instructions"])

    def test_agent_configuration_goes_to_review_even_when_added(self):
        for path in ("plugins/core/skills/clarify/SKILL.md", "SKILL.md", "plugins/core/hooks/hooks.json",
                     "hooks/hooks.json", ".claude/settings.json", ".claude/settings.local.json",
                     ".claude-plugin/marketplace.json", "plugins/core/.claude-plugin/plugin.json"):
            for status, hunk in (("A", Hunk()), ("M", Hunk([], ["more"]))):
                with self.subTest(path=path, status=status):
                    self.assertEqual(reasons(FileChange(path, status, [hunk])),
                                     [f"{path}: agent instructions or configuration"])

    def test_files_named_like_agent_configuration_elsewhere_pass(self):
        self.assertEqual(reasons(changed("docs/skill.md", [], ["x"]), changed("hooks.json", [], ["x"]),
                                 changed("src/hooks/other.json", [], ["x"]), changed("settings.json", [], ["x"]),
                                 changed("docs/claude-plugin.md", [], ["x"])), [])

    def test_skip_marker_added_to_an_existing_test_file_goes_to_review(self):
        for path, line in (("tests/test_app.py", "@unittest.skip('later')"),
                           ("tests/test_app.py", "    @unittest.skipIf(True, 'x')"),
                           ("tests/test_app.py", "    raise unittest.SkipTest('x')"),
                           ("tests/test_app.py", "        self.skipTest('x')"),
                           ("tests/test_app.py", "skip = unittest.skip('x')"),
                           ("tests/test_app.py", "@pytest.mark.skip"),
                           ("tests/test_app.py", "    pytest.skip('x')"),
                           ("FooTest.cs", "    [Ignore(\"later\")]"),
                           ("FooTest.cs", "[Ignore]"),
                           ("FooTest.cs", "    [Fact(Skip = \"later\")]"),
                           ("tests/FooTest.kt", "    @Disabled"),
                           ("tests/FooTest.java", "@Ignore"),
                           ("tests/app.rs", "#[ignore]"),
                           ("app.spec.ts", "  it.skip('works', () => {"),
                           ("app.spec.ts", "describe.skip('suite', () => {"),
                           ("app.spec.ts", "test.skip('works', () => {"),
                           ("app.spec.ts", "  xit('works', () => {"),
                           ("app.spec.ts", "xdescribe('suite', () => {"),
                           ("tests/test_app.py", "        return"),
                           ("app.spec.ts", "    return;")):
            with self.subTest(line=line):
                self.assertEqual(reasons(changed(path, [], [line])),
                                 [f"{path}: test skip marker added: {line.strip()}"])

    def test_skip_marker_in_a_new_test_file_passes(self):
        self.assertEqual(reasons(FileChange("tests/test_new.py", "A", [Hunk([], ["@unittest.skip('x')"])])), [])

    def test_lines_that_only_look_like_skip_markers_pass(self):
        for line in ("    return value", "    exit()", "    skipped = 0", "    edit('x')", "    # ignore this"):
            with self.subTest(line=line):
                self.assertEqual(reasons(changed("tests/test_app.py", [], [line])), [])

    def test_new_test_and_markdown_files_pass(self):
        self.assertEqual(reasons(changed("tests/test_new.py", status="A"), changed("docs/new.md", status="A")), [])

    def test_changed_binary_test_file_goes_to_review(self):
        self.assertTrue(reasons(FileChange("tests/data/image.png", "M", [], True)))

    def test_no_changed_file_goes_to_review(self):
        self.assertEqual(reasons(), ["no changed file"])


class TestFilesTest(unittest.TestCase):
    def test_default_patterns(self):
        patterns = auto_merge.test_patterns({})
        for path in ("tests/x.py", "src/tests/data.json", "test_app.py", "pkg/app_test.go", "FooTest.cs",
                     "FooTests.cs", "src/app.spec.ts"):
            with self.subTest(path=path):
                self.assertTrue(auto_merge.is_test_file(path, patterns))
        for path in ("src/app.py", "tests.py", "src/contest.py", "latest_tests.cs", "tests"):
            with self.subTest(path=path):
                self.assertFalse(auto_merge.is_test_file(path, patterns))

    def test_config_extends_the_patterns(self):
        config = {"test_patterns": ["e2e/", "*.feature", "src/fixtures/*.json"]}
        self.assertTrue(reasons(changed("e2e/login.ts", ["a"], ["b"]), config=config))
        self.assertTrue(reasons(changed("specs/login.feature", ["a"], ["b"]), config=config))
        self.assertTrue(reasons(changed("src/fixtures/game.json", ["a"], ["b"]), config=config))
        self.assertEqual(reasons(changed("src/game.json", ["a"], ["b"]), config=config), [])

    def test_missing_config_is_empty(self):
        self.assertEqual(auto_merge.load_config(ROOT / "no-such-file.json"), {})


class DecisionTest(unittest.TestCase):
    def test_safe_pull_request_gets_no_label(self):
        self.assertEqual(decide(changed("src/a.py")), {})

    def test_file_rules_give_to_review(self):
        self.assertEqual(decide(changed("src/a.py", status="D")), {"to review": ["src/a.py: deleted"]})

    def test_description_labels_add_to_file_labels(self):
        body = BODY + "## Manual checks\n- [manual] Reads well.\n## Architecture changes\nNew module.\n"
        labels = decide(changed("AGENTS.md"), body=body)
        self.assertEqual(set(labels), {"to test", "to review"})
        self.assertEqual(labels["to review"], ["description: section Architecture changes",
                                               "AGENTS.md: agent instructions"])

    def test_pull_request_of_another_author_goes_to_review(self):
        self.assertEqual(decide(changed("src/a.py"), pr=pull_request(author="stranger")),
                         {"to review": ["opened by stranger, not by the repository owner owner"]})

    def test_pull_request_from_a_fork_goes_to_review(self):
        self.assertEqual(decide(changed("src/a.py"), pr=pull_request(head_repo="owner-fork/repo")),
                         {"to review": ["head branch in owner-fork/repo, not in owner/repo"]})

    def test_pull_request_from_a_deleted_fork_goes_to_review(self):
        self.assertEqual(decide(changed("src/a.py"), pr=pull_request(head_repo=None)),
                         {"to review": ["head branch in a deleted repository, not in owner/repo"]})

    def test_owner_is_compared_without_case(self):
        self.assertEqual(decide(changed("src/a.py"), pr=pull_request(author="Owner", head_repo="Owner/Repo")), {})

    def test_no_ticket_label_does_not_hold(self):
        labels = decide(changed("src/a.py"), body=BODY.replace("Fixes #1", "No ticket: quick CI fix"))
        self.assertEqual(list(labels), ["no ticket"])
        self.assertFalse(any(name in labels for name in auto_merge.HOLD_LABELS))


class GitDiffTest(unittest.TestCase):
    """changed_files on a real repository."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")
        return self.git("rev-parse", "HEAD")

    def test_diff_is_read_per_file_since_the_merge_base(self):
        self.write("tests/test_a.py", "# header\nassert 1\n")
        self.write("src/old.py", "x = 1\n")
        self.write("docs/é space.md", "Text\n")
        base = self.commit()
        self.git("checkout", "-q", "-b", "feature")
        self.write("tests/test_a.py", "# new header\nassert 1\nassert 2\n")
        (self.repo / "src" / "old.py").unlink()
        self.write("docs/é space.md", "Text\nMore\n")
        self.write("assets/logo.png", "\0binary")
        head = self.commit()
        self.git("checkout", "-q", "main")
        self.write("src/main_only.py", "y = 1\n")
        main = self.commit()

        files = {f.path: f for f in auto_merge.changed_files(main, head, self.repo)}
        self.assertEqual(set(files), {"tests/test_a.py", "src/old.py", "docs/é space.md", "assets/logo.png"})
        self.assertEqual(files["src/old.py"].status, "D")
        self.assertEqual(files["assets/logo.png"].status, "A")
        self.assertTrue(files["assets/logo.png"].binary)
        self.assertEqual([(h.removed, h.added) for h in files["tests/test_a.py"].hunks],
                         [(["# header"], ["# new header"]), ([], ["assert 2"])])
        self.assertEqual(auto_merge.review_reasons(list(files.values()), {}), ["src/old.py: deleted"])
        self.assertNotEqual(base, main)


def verify_run(created_at, status="completed", conclusion="success"):
    return {"created_at": created_at, "status": status, "conclusion": conclusion}


class VerifyStateTest(unittest.TestCase):
    def test_no_run_yet_waits(self):
        self.assertEqual(auto_merge.verify_state([]), "waiting")

    def test_run_in_progress_waits(self):
        self.assertEqual(auto_merge.verify_state([verify_run("2026-11-04T10:00:00Z", "in_progress", None)]), "waiting")

    def test_latest_run_decides(self):
        old, new = "2026-11-04T10:00:00Z", "2026-11-04T11:00:00Z"
        self.assertEqual(auto_merge.verify_state([verify_run(new), verify_run(old, conclusion="failure")]), "success")
        self.assertEqual(auto_merge.verify_state([verify_run(old), verify_run(new, conclusion="failure")]), "failure")

    def test_cancelled_run_is_not_a_success(self):
        self.assertEqual(auto_merge.verify_state([verify_run("2026-11-04T10:00:00Z", conclusion="cancelled")]), "failure")


class EventPullRequestTest(unittest.TestCase):
    def setUp(self):
        self.fetched = []
        self.pulls = {}
        original = auto_merge.gh_json
        auto_merge.gh_json = lambda path: self.fetched.append(path) or self.pulls.get(path)
        self.addCleanup(setattr, auto_merge, "gh_json", original)

    def workflow_run(self, sha="abc", refs=((7, "abc"),)):
        return {"workflow_run": {"head_sha": sha,
                                 "pull_requests": [{"number": n, "head": {"sha": s}} for n, s in refs]}}

    def test_pull_request_event_is_used_as_is(self):
        pr = {"number": 3}
        self.assertIs(auto_merge.event_pull_request({"pull_request": pr}, "o/r"), pr)
        self.assertEqual(self.fetched, [])

    def test_verify_run_fetches_its_open_pull_request(self):
        pr = {"number": 7, "state": "open", "head": {"sha": "abc"}}
        self.pulls["repos/o/r/pulls/7"] = pr
        self.assertIs(auto_merge.event_pull_request(self.workflow_run(), "o/r"), pr)

    def test_verify_run_of_an_outdated_or_closed_pull_request_is_ignored(self):
        for pr in ({"number": 7, "state": "open", "head": {"sha": "def"}},
                   {"number": 7, "state": "closed", "head": {"sha": "abc"}}):
            with self.subTest(pr=pr):
                self.pulls["repos/o/r/pulls/7"] = pr
                self.assertIsNone(auto_merge.event_pull_request(self.workflow_run(), "o/r"))

    def test_verify_run_without_pull_request_is_ignored(self):
        self.assertIsNone(auto_merge.event_pull_request(self.workflow_run(refs=()), "o/r"))
        self.assertIsNone(auto_merge.event_pull_request(self.workflow_run(refs=((7, "old"),)), "o/r"))
        self.assertEqual(self.fetched, [])


class InstalledCopiesTest(unittest.TestCase):
    def test_dev_kit_runs_the_template_versions(self):
        for installed, template in ((".github/workflows/auto-merge.yml", "github-workflows/auto-merge.yml"),
                                    (".github/scripts/auto_merge.py", "github-scripts/auto_merge.py"),
                                    (".github/workflows/pr-description.yml", "github-workflows/pr-description.yml"),
                                    (".github/scripts/pr_description.py", "github-scripts/pr_description.py"),
                                    (".github/scripts/structure.py", "github-scripts/structure.py"),
                                    (".github/pull_request_template.md", "pull_request_template.md")):
            with self.subTest(file=installed):
                self.assertEqual((ROOT / installed).read_text(encoding="utf-8"),
                                 (TEMPLATES / template).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
