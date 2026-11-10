"""Tests of plugins/core/scripts/ticket_refs.py on throwaway Git repositories."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "plugins" / "core" / "scripts" / "ticket_refs.py"
sys.path.insert(0, str(CHECK.parent))
import ticket_refs  # noqa: E402


class ReferencesTest(unittest.TestCase):
    def test_references_are_found(self):
        for line in ("see #81", "(#81)", "fixed in #81.", "Jyhess/dev-kit#12",
                     "https://github.com/Jyhess/dev-kit/issues/12", "http://github.com/a/b/pull/3"):
            with self.subTest(line=line):
                self.assertTrue(ticket_refs.references(line))

    def test_non_references_are_left(self):
        for line in ("# TODO(#81): cover several modules", "TODO: see Jyhess/dev-kit#12", "version #0.1.0",
                     "id#0.1.0", "&#12;", "page.html#12", "https://example.com/#12", "https://example.com/docs/page.html#12", "color #000", "#12.5",
                     "$#1", "step #n", "## 12 heading", "a #12x b"):
            with self.subTest(line=line):
                self.assertEqual(ticket_refs.references(line), [])

    def test_ignored_patterns(self):
        patterns = ["tests/", "/docs/pr-*.md", "SKILL.md"]
        self.assertTrue(ticket_refs.ignored("tests/test_a.py", patterns))
        self.assertTrue(ticket_refs.ignored("docs/pr-description.md", patterns))
        self.assertTrue(ticket_refs.ignored("plugins/core/skills/pilot/SKILL.md", patterns))
        self.assertFalse(ticket_refs.ignored("docs/architecture.md", patterns))
        self.assertFalse(ticket_refs.ignored("src/tests/a.py", patterns))


class TicketRefsScriptTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / "sample"
        self.project.mkdir()
        self.git("init", "-q")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                        *args], check=True, capture_output=True)

    def write(self, path, text):
        (self.project / path).parent.mkdir(parents=True, exist_ok=True)
        (self.project / path).write_text(text, encoding="utf-8")
        self.git("add", path)

    def run_check(self, *args):
        result = subprocess.run([sys.executable, str(CHECK), "--project", str(self.project), *args],
                                capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout

    def test_tree_reference_is_refused_with_its_place(self):
        self.write("docs/a.md", "# A\n\nOne module (see #81).\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("docs/a.md:3: #81", out)

    def test_clean_tree_passes(self):
        self.write("src/a.py", "# TODO(#81): several modules\nVERSION = '#0.1.0'\n")
        self.assertEqual(self.run_check(), (0, ""))

    def test_ignored_files_are_not_read(self):
        self.write("tests/test_a.py", "BODY = 'Fixes #12'\n")
        self.write(".github/pull_request_template.md", "<!-- Fixes #12 -->\n")
        self.write(ticket_refs.IGNORE_FILE, "# examples\ntests/\npull_request_template.md\n")
        self.assertEqual(self.run_check(), (0, ""))

    def test_untracked_files_are_not_read(self):
        (self.project / "notes.md").write_text("see #81\n", encoding="utf-8")
        self.assertEqual(self.run_check(), (0, ""))

    def test_staged_reference_is_a_warning(self):
        self.write("a.md", "line\n")
        self.git("commit", "-q", "-m", "init")
        (self.project / "a.md").write_text("line\nsee #81\n", encoding="utf-8")
        self.git("add", "a.md")
        code, out = self.run_check("--staged")
        self.assertEqual(code, 0)
        self.assertIn("warning: ticket reference: a.md:2: #81", out)

    def test_staged_ignored_file_gives_no_warning(self):
        self.write(ticket_refs.IGNORE_FILE, "tests/\n")
        self.write("tests/a.py", "'Fixes #12'\n")
        self.assertEqual(self.run_check("--staged"), (0, ""))


if __name__ == "__main__":
    unittest.main()
