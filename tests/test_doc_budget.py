"""Tests of plugins/core/scripts/doc_budget.py on throwaway Git repositories."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET = ROOT / "plugins" / "core" / "scripts" / "doc_budget.py"


class DocBudgetTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        self.git("init", "-q")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                        *args], check=True, capture_output=True)

    def write(self, name, size):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)

    def run_budget(self, *args):
        result = subprocess.run([sys.executable, str(BUDGET), "--project", str(self.project), *args],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_staged_files_over_their_budget_are_warned(self):
        self.write("AGENTS.md", 5_001)
        self.write("README.md", 9_000)
        self.write("plugins/x/SKILL.md", 10_500)
        self.write("docs/guide.md", 15_001)
        self.write("big.txt", 50_000)
        self.git("add", "-A")
        out = self.run_budget("--staged")
        self.assertEqual(len(out), 3)
        self.assertIn("AGENTS.md is 5,001 bytes, over its 5,000-byte budget", out[0] + out[1] + out[2])
        self.assertTrue(any("plugins/x/SKILL.md" in line and "10,000-byte" in line for line in out))
        self.assertTrue(any("docs/guide.md" in line and "15,000-byte" in line for line in out))

    def test_only_the_files_of_the_commit_are_checked(self):
        self.write("CLAUDE.md", 6_000)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "big")
        self.write("notes.md", 100)
        self.git("add", "-A")
        self.assertEqual(self.run_budget("--staged"), [])
        self.assertEqual(len(self.run_budget()), 1)  # every tracked file

    def test_repository_adjusts_its_budgets(self):
        (self.project / ".doc-budgets.json").write_text(json.dumps({"docs/scoping.md": 40_000, "AGENTS.md": 8_000}),
                                                        encoding="utf-8")
        self.write("docs/scoping.md", 30_000)
        self.write("AGENTS.md", 7_000)
        self.write("docs/other.md", 16_000)
        self.git("add", "-A")
        out = self.run_budget("--staged")
        self.assertEqual(len(out), 1)
        self.assertIn("docs/other.md", out[0])


if __name__ == "__main__":
    unittest.main()
