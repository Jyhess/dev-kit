"""Tests of the PR description check (plugins/core/templates/github-scripts/pr_description.py)."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "plugins" / "core" / "templates"
SCRIPT = TEMPLATES / "github-scripts" / "pr_description.py"
sys.path.insert(0, str(SCRIPT.parent))
import pr_description  # noqa: E402
from structure import Kind, Signal  # noqa: E402

GOOD = "Fixes #48\n\n## What was done\nA check.\n\n## Test results\n`python3 -m unittest`: 300 tests pass.\n"


def errors(body):
    return pr_description.check(body).errors


def labels(body):
    return pr_description.check(body).labels


class RequiredTest(unittest.TestCase):
    def test_complete_description_passes_without_label(self):
        self.assertEqual(errors(GOOD), [])
        self.assertEqual(labels(GOOD), {})

    def test_ticket_references(self):
        for line in ("Fixes #12", "Closes ABC-12", "fixed: #3", "Refs Jyhess/dev-kit#48", "Resolves ABC1-7",
                     "Fixes https://github.com/Jyhess/dev-kit/issues/48", "Part of the work. Refs #9"):
            with self.subTest(line=line):
                self.assertEqual(errors(GOOD.replace("Fixes #48", line)), [])

    def test_missing_or_unfilled_ticket_fails(self):
        for line in ("", "Fixes #", "Fixes #<n>", "Fixes abc-12", "See #12"):
            with self.subTest(line=line):
                self.assertTrue(any("ticket" in e for e in errors(GOOD.replace("Fixes #48", line))))

    def test_no_ticket_needs_a_reason_and_adds_its_label(self):
        body = GOOD.replace("Fixes #48", "No ticket: quick CI fix")
        self.assertEqual(errors(body), [])
        self.assertEqual(list(labels(body)), ["no ticket"])
        self.assertEqual(errors(GOOD.replace("Fixes #48", "No ticket: hotfix")),
                         ["`No ticket:` needs a reason of at least two words"])

    def test_missing_required_section_fails(self):
        self.assertEqual(errors("Fixes #1\n## What was done\nA fix.\n"), ["missing section `## Test results`"])
        self.assertEqual(errors("Fixes #1\n### What was done\nx\n## Test results\nok fine\n"),
                         ["missing section `## What was done`"])

    def test_headings_are_case_insensitive_and_may_end_with_a_colon(self):
        self.assertEqual(errors("Fixes #1\n## what was done:\nx\n## TEST RESULTS\nall pass\n"), [])

    def test_empty_required_section_fails(self):
        self.assertEqual(errors(GOOD.replace("A check.", "")), ["section `## What was done` is empty"])

    def test_test_results_may_be_na_with_a_reason(self):
        for na in ("N/A: documentation only", "n/a — docs only change", "None. Only comments changed"):
            with self.subTest(na=na):
                self.assertEqual(errors(GOOD.replace("`python3 -m unittest`: 300 tests pass.", na)), [])
        self.assertEqual(errors(GOOD.replace("`python3 -m unittest`: 300 tests pass.", "N/A")),
                         ["section `## Test results`: N/A needs a reason of at least two words"])

    def test_what_was_done_cannot_be_na(self):
        self.assertEqual(errors(GOOD.replace("A check.", "N/A: nothing much")),
                         ["section `## What was done` cannot be N/A"])

    def test_words_starting_like_na_are_content(self):
        self.assertEqual(errors(GOOD.replace("A check.", "None of the old rules changed.")), [])


class OptionalTest(unittest.TestCase):
    def test_optional_sections_set_their_labels(self):
        cases = {"Manual checks": "to test", "Values to validate": "to acknowledge",
                 "Assumptions": "to acknowledge", "Known limitations": "to acknowledge",
                 "Architecture changes": "to review"}
        for section, label in cases.items():
            with self.subTest(section=section):
                body = GOOD + f"\n## {section}\n- Something real.\n"
                self.assertEqual(errors(body), [])
                self.assertEqual(labels(body), {label: [f"description: section {section}"]})

    def test_present_optional_section_must_not_be_empty_nor_na(self):
        self.assertEqual(errors(GOOD + "## Assumptions\n<!-- what was assumed -->\n"),
                         ["section `## Assumptions` is empty: fill it, or delete it with its heading"])
        self.assertEqual(errors(GOOD + "## Known limitations\nNone.\n"),
                         ["section `## Known limitations` cannot be N/A: delete the section, heading included"])

    def test_manual_marker_anywhere_gives_to_test(self):
        for marker in ("[manual]", "[Manuel]"):
            with self.subTest(marker=marker):
                body = GOOD.replace("A check.", f"A check.\n- {marker} The board reads well.")
                self.assertEqual(labels(body), {"to test": ["description: [manual] criteria to check by hand"]})

    def test_manual_marker_in_code_is_a_mention(self):
        self.assertEqual(labels(GOOD.replace("A check.", "Reads `[manual]` markers.")), {})

    def test_other_sections_are_free(self):
        self.assertEqual(errors(GOOD + "## Screenshots\n"), [])


class PlaceholderTest(unittest.TestCase):
    def test_comments_are_ignored(self):
        body = "<!-- Fixes #1 -->\n" + GOOD.replace("Fixes #48", "") + "<!-- ## Manual checks\n[manual] x -->\n"
        self.assertEqual(errors(body), [errors(body)[0]])
        self.assertIn("ticket", errors(body)[0])
        self.assertEqual(labels(GOOD + "<!-- [manual] -->"), {})

    def test_unclosed_comment_hides_the_rest(self):
        self.assertEqual(errors(GOOD.replace("## Test results", "<!-- ## Test results")),
                         ["missing section `## Test results`"])

    def test_leftover_placeholders_fail(self):
        for text in ("TODO", "- TBD", "...", "…", "- [ ] todo", "Timeout: <n> s", "Fixes <ID>", "<reason>"):
            with self.subTest(text=text):
                self.assertIn("placeholder left (TODO, TBD, ..., <n>, <ID>, <reason>)",
                              errors(GOOD.replace("A check.", text)))

    def test_words_like_todo_in_a_sentence_pass(self):
        self.assertEqual(errors(GOOD.replace("A check.", "Removed the TODO list... and <br> tags.")), [])

    def test_placeholders_in_code_pass(self):
        for text in ("Accepts `No ticket: <reason>`.", "Example:\n```\nFixes #<n>\nTODO\n```\nDone."):
            with self.subTest(text=text):
                self.assertEqual(errors(GOOD.replace("A check.", text)), [])

    def test_headings_in_code_fences_do_not_count(self):
        body = GOOD.replace("A check.", "Example:\n```\n## Test results\n```")
        self.assertEqual(errors(body.replace("## Test results\n`python3", "Results\n`python3")),
                         ["missing section `## Test results`"])

    def test_crlf_bodies(self):
        self.assertEqual(errors(GOOD.replace("\n", "\r\n")), [])


class StructuralTest(unittest.TestCase):
    SIGNALS = [Signal(Kind.MANIFEST_ADDED, "server/package.json"), Signal(Kind.FOLDER_ADDED, "server/")]

    def test_undeclared_structural_change_fails_and_lists_the_signals(self):
        self.assertEqual(pr_description.check(GOOD, self.SIGNALS).errors, [
            "structural changes without a `## Architecture changes` section: "
            "server/package.json: manifest added; server/: top-level folder added"])

    def test_empty_or_commented_section_does_not_declare(self):
        for section in ("## Architecture changes\n", "## Architecture changes\n<!-- later -->\n"):
            with self.subTest(section=section):
                errors = pr_description.check(GOOD + section, self.SIGNALS).errors
                self.assertTrue(any(e.startswith("structural changes without") for e in errors), errors)

    def test_declared_structural_change_goes_to_review_with_each_signal(self):
        result = pr_description.check(GOOD + "## Architecture changes\nA new server component.\n", self.SIGNALS)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.labels, {"to review": ["description: section Architecture changes",
                                                       "diff: server/package.json: manifest added",
                                                       "diff: server/: top-level folder added"]})


class TemplateTest(unittest.TestCase):
    TEMPLATE = (TEMPLATES / "pull_request_template.md").read_text(encoding="utf-8")

    def test_untouched_template_fails(self):
        self.assertEqual(set(errors(self.TEMPLATE)), {
            "no ticket reference (`Fixes #12`, `Fixes ABC-12`, `Refs #12`) nor `No ticket: <reason>`",
            "section `## What was done` is empty", "section `## Test results` is empty",
            *(f"section `## {name}` is empty: fill it, or delete it with its heading"
              for name in pr_description.OPTIONAL)})

    def test_template_has_every_section(self):
        for name in (*pr_description.REQUIRED, *pr_description.OPTIONAL):
            self.assertIn(f"\n## {name}\n", self.TEMPLATE)


class CommandTest(unittest.TestCase):
    def run_script(self, *args, env=None, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              encoding="utf-8", env={**os.environ, **(env or {})}, cwd=cwd)

    def repository(self, tmp):
        """A repository whose HEAD adds a top-level folder; returns (base, head)."""
        def git(*args):
            return subprocess.run(["git", "-C", tmp, *args], check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.com")
        Path(tmp, "src").mkdir()
        Path(tmp, "src", "app.py").write_text("x\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        Path(tmp, "server").mkdir()
        Path(tmp, "server", "main.py").write_text("x\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "server")
        return git("rev-parse", "HEAD~1"), git("rev-parse", "HEAD")

    def test_file_argument_and_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp, "good.md"), Path(tmp, "bad.md")
            good.write_text(GOOD + "## Assumptions\nThe CI runs Python 3.\n", encoding="utf-8")
            bad.write_text("Nothing", encoding="utf-8")
            result = self.run_script(str(good))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("`to acknowledge`", result.stdout)
            self.assertEqual(self.run_script(str(bad)).returncode, 1)

    def test_event_and_summary(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            base, head = self.repository(tmp)
            event, summary = Path(tmp, "..", "event.json").resolve(), Path(tmp, "..", "summary.md").resolve()
            self.addCleanup(event.unlink, missing_ok=True)
            self.addCleanup(summary.unlink, missing_ok=True)
            event.write_text(f'{{"pull_request": {{"body": null, "base": {{"sha": "{base}"}}, '
                             f'"head": {{"sha": "{head}"}}}}}}', encoding="utf-8")
            result = self.run_script(env={"GITHUB_EVENT_PATH": str(event), "GITHUB_STEP_SUMMARY": str(summary)},
                                     cwd=tmp)
            self.assertEqual(result.returncode, 1)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("missing section `## What was done`", text)
            self.assertIn("server/: top-level folder added", text)

    def test_local_base_option_checks_the_diff_of_head(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            base, _ = self.repository(tmp)
            body = Path(tmp, "..", "body.md").resolve()
            self.addCleanup(body.unlink, missing_ok=True)
            body.write_text(GOOD, encoding="utf-8")
            self.assertEqual(self.run_script(str(body), cwd=tmp).returncode, 0)
            result = self.run_script(str(body), "--base", base, cwd=tmp)
            self.assertEqual(result.returncode, 1)
            self.assertIn("server/: top-level folder added", result.stdout)


if __name__ == "__main__":
    unittest.main()
