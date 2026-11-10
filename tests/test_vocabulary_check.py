"""Tests of plugins/core/scripts/vocabulary_check.py on throwaway Git repositories."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "plugins" / "core" / "scripts" / "vocabulary_check.py"
ROWS = ["Vaisseau | ship | | | Def. | astronef, nef",
        "Réservoir de carburant | fuel tank | | | Def. | ",
        "Vaisseau lourd | heavy ship | | | Def. | tank",
        "Projectile | projectile | | | Def. | tir (pour l'objet)",
        "Arène | arena | | | Def. | ",
        "Abonnements | subscriptions | | | Def. | fil",
        "Caisse | crate | | | Def. | box"]


class VocabularyCheckTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / "sample"
        (self.project / "docs").mkdir(parents=True)
        (self.project / "AGENTS.md").write_text(
            "# Sample\n\n## Vocabulary\n\n- The domain glossary is at `docs/glossary.md`.\n", encoding="utf-8")
        table = ["| French | English (code) | Displayed (FR) | Displayed (EN) | Definition | Forbidden synonyms |",
                 "| --- | --- | --- | --- | --- | --- |"] + [f"| {row} |" for row in ROWS]
        (self.project / "docs" / "glossary.md").write_text("# Glossary\n\n" + "\n".join(table) + "\n",
                                                          encoding="utf-8")
        self.git("init", "-q")
        self.commit("init")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                        *args], check=True, capture_output=True)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def write(self, name, text):
        (self.project / name).write_text(text, encoding="utf-8")

    def run_check(self, *args):
        result = subprocess.run([sys.executable, str(CHECK), "--project", str(self.project), *args],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_staged_forbidden_synonym_is_a_warning_on_its_added_line(self):
        self.write("game.py", "ship = 1\n")
        self.commit("code")
        self.write("game.py", "ship = 1\nAstronefs = 2  # an ASTRONEF\n")
        self.git("add", "-A")
        out = self.run_check("--staged")
        self.assertEqual(out.splitlines(), ['warning: vocabulary: game.py:2: "astronef" → Vaisseau (ship)'])

    def test_staged_files_with_non_ascii_names_or_spaces_are_read(self):
        self.write("docs/café.md", "Un astronef.\n")
        self.write("my notes.md", "Un astronef.\n")
        self.git("add", "-A")
        out = self.run_check("--staged")
        self.assertEqual(sorted(out.splitlines()), ['warning: vocabulary: docs/café.md:1: "astronef" → Vaisseau (ship)',
                                                    'warning: vocabulary: my notes.md:1: "astronef" → Vaisseau (ship)'])

    def test_accents_case_and_identifiers_are_ignored(self):
        self.write("notes.md", "Une NÉF passe.\n")
        self.write("Fleet.cs", "class HeavyShip { int Tank; }\n")
        self.git("add", "-A")
        out = self.run_check("--staged")
        self.assertIn("notes.md:1: \"nef\"", out)
        self.assertIn("Fleet.cs:1: \"tank\"", out)

    def test_a_glossary_term_containing_a_synonym_is_not_flagged(self):
        self.write("fuel.py", "fuel_tank = FuelTank()\nbig_fuel_tanks = []\n")
        self.git("add", "-A")
        self.assertEqual(self.run_check("--staged"), "")

    def test_whole_words_only_and_qualified_synonyms_left_out(self):
        self.write("notes.md", "Une nefaste idée, un tir réussi, un tanker.\n")
        self.git("add", "-A")
        self.assertEqual(self.run_check("--staged"), "")

    def test_plural_es_only_after_a_sibilant(self):
        self.write("files.py", "files = load_file(profile)  # profiles\n")
        self.write("notes.md", "Le fil des vidéos, les fils, two boxes.\n")
        self.git("add", "-A")
        out = self.run_check("--staged")
        self.assertEqual(out.splitlines(), ['warning: vocabulary: notes.md:1: "fil" → Abonnements (subscriptions)',
                                            'warning: vocabulary: notes.md:1: "box" → Caisse (crate)'])

    def test_glossary_and_removed_lines_are_not_checked(self):
        self.write("old.md", "astronef\n")
        self.commit("old")
        self.write("old.md", "ship\n")
        with (self.project / "docs" / "glossary.md").open("a", encoding="utf-8") as f:
            f.write("| Nef | nave | | | Def. | astronef |\n")
        self.git("add", "-A")
        self.assertEqual(self.run_check("--staged"), "")

    def test_report_lists_synonyms_and_unused_terms(self):
        self.write("ship.py", "ship = FuelTank()\ntank = 1\n")
        self.write("README.md", "L'arène est fermée. Un astronef.\n")
        self.commit("content")
        out = self.run_check()
        self.assertIn('- "astronef" → Vaisseau (ship): 1 line (README.md:1)', out)
        self.assertIn('- "tank" → Vaisseau lourd (heavy ship): 1 line (ship.py:2)', out)
        unused = out.split("Unused terms")[1]
        self.assertIn("Vaisseau lourd (heavy ship)", unused)
        self.assertIn("Projectile (projectile)", unused)
        self.assertNotIn("Arène", unused)  # French term in the docs
        self.assertNotIn("Réservoir", unused)  # English term in the code

    def test_project_without_glossary_prints_nothing(self):
        self.write("AGENTS.md", "# Sample\n")
        self.write("x.md", "astronef\n")
        self.git("add", "-A")
        self.assertEqual(self.run_check("--staged"), "")
        self.assertEqual(self.run_check(), "")


if __name__ == "__main__":
    unittest.main()
