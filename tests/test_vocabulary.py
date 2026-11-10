"""Tests of plugins/core/scripts/vocabulary.py on throwaway projects."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCABULARY = ROOT / "plugins" / "core" / "scripts" / "vocabulary.py"


def run_hook(project):
    result = subprocess.run([sys.executable, str(VOCABULARY), "--project", str(project)],
                            capture_output=True, text=True, encoding="utf-8")
    return result.returncode, json.loads(result.stdout) if result.stdout.strip() else None


class VocabularyHookTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / "sample"
        self.project.mkdir()

    def claude_md(self, title="Vocabulary", path="docs/glossary.md"):
        (self.project / "CLAUDE.md").write_text(
            f"# Sample\n\n## {title}\n\n- The domain glossary:\n@{path}\n\n## Git\n\n- Push only when asked.\n",
            encoding="utf-8")

    def test_missing_glossary_gives_the_rules_and_a_warning(self):
        self.claude_md()
        code, output = run_hook(self.project)
        self.assertEqual(code, 0)
        self.assertIn("forbidden synonym", output["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("docs/glossary.md", output["systemMessage"])
        self.assertEqual(len(output["systemMessage"].splitlines()), 1)

    def test_present_glossary_gives_the_rules_only(self):
        self.claude_md()
        (self.project / "docs").mkdir()
        (self.project / "docs" / "glossary.md").write_text("# Glossary\n", encoding="utf-8")
        code, output = run_hook(self.project)
        self.assertEqual(code, 0)
        self.assertIn("docs/glossary.md", output["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("systemMessage", output)

    def test_no_vocabulary_section_prints_nothing(self):
        (self.project / "CLAUDE.md").write_text("# Sample\n\n## Git\n\n@docs/other.md\n", encoding="utf-8")
        self.assertEqual(run_hook(self.project), (0, None))

    def test_no_claude_md_prints_nothing(self):
        self.assertEqual(run_hook(self.project), (0, None))

    def test_french_title_and_path_outside_the_repository(self):
        wiki = self.project.parent / "sample-wiki"
        wiki.mkdir()
        (wiki / "Glossaire.md").write_text("# Glossaire\n", encoding="utf-8")
        self.claude_md("Vocabulaire", "../sample-wiki/Glossaire.md")
        code, output = run_hook(self.project)
        self.assertEqual(code, 0)
        self.assertIn("../sample-wiki/Glossaire.md", output["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("systemMessage", output)

    def glossary(self, rows, folder=None):
        folder = folder or self.project / "docs"
        folder.mkdir(parents=True, exist_ok=True)
        table = ["| French | English (code) | Displayed (FR) | Displayed (EN) | Definition | Forbidden synonyms |",
                 "| --- | --- | --- | --- | --- | --- |"] + [f"| {row} |" for row in rows]
        (folder / "glossary.md").write_text("# Glossary\n\n" + "\n".join(table) + "\n", encoding="utf-8")

    def test_index_lists_terms_and_synonyms_without_definitions(self):
        self.claude_md()
        self.glossary(["Vaisseau | ship | | | A long definition. | astronef, nef",
                       "Coque | hull | | | Protects \\| encloses. | "])
        code, output = run_hook(self.project)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("\n- Vaisseau = ship ≠ astronef, nef\n- Coque = hull", context)
        self.assertNotIn("A long definition", context)
        self.assertNotIn("systemMessage", output)

    def test_index_over_the_cap_is_truncated_with_a_warning(self):
        self.claude_md()
        self.glossary([f"Terme {i} | term {i} | | | Definition. | synonyme {i}" for i in range(600)])
        code, output = run_hook(self.project)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(code, 0)
        self.assertLessEqual(len(context), 10_000)
        self.assertIn("more terms: read the glossary", context)
        self.assertIn("tronqué", output["systemMessage"])
        self.assertEqual(len(output["systemMessage"].splitlines()), 1)

    def test_wiki_beside_the_main_checkout_is_found_from_a_worktree(self):
        self.claude_md("Vocabulaire", "../sample-wiki/glossary.md")
        self.glossary(["Vaisseau | ship | | | Def. | astronef"], self.project.parent / "sample-wiki")
        git = ["git", "-C", str(self.project), "-c", "user.name=Test", "-c", "user.email=test@example.com"]
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "init"], check=True)
        worktree = self.project / ".claude" / "worktrees" / "task"
        subprocess.run(git + ["worktree", "add", "-q", str(worktree)], check=True)
        code, output = run_hook(worktree)
        self.assertIn("- Vaisseau = ship ≠ astronef", output["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("systemMessage", output)

    def test_agents_md_path_is_used(self):
        (self.project / "AGENTS.md").write_text(
            "# Sample\n\n## Vocabulary\n\n- The domain glossary is at `docs/glossary.md`. Read it.\n",
            encoding="utf-8")
        self.glossary(["Vaisseau | ship | | | Def. | "])
        code, output = run_hook(self.project)
        self.assertIn("- Vaisseau = ship", output["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
