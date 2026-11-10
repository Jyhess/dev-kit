"""Tests of scripts/check_projects.py on throwaway projects."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_projects  # noqa: E402


def skill(project: Path, folder: str, name: str) -> None:
    path = project / ".claude" / "skills" / folder / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\nname: {name}\ndescription: test\n---\n\n# Test\n", encoding="utf-8")


class CheckProjectsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.shared = check_projects.shared_skills()

    def test_shared_skills_come_from_the_plugins(self):
        self.assertEqual(self.shared["clarify"], "core:clarify")
        self.assertEqual(self.shared["linear"], "tracking-linear:linear")
        self.assertEqual(self.shared["wiki-github"], "docs-wiki-github:wiki-github")
        self.assertEqual(self.shared["cadrage"], "core:clarify")

    def test_project_without_local_skills_passes(self):
        self.assertEqual(check_projects.copies(self.project, self.shared), [])

    def test_own_local_skill_passes(self):
        skill(self.project, "godot-scenes", "godot-scenes")
        self.assertEqual(check_projects.copies(self.project, self.shared), [])

    def test_copy_of_a_shared_skill_fails(self):
        skill(self.project, "linear", "linear")
        self.assertEqual(check_projects.copies(self.project, self.shared),
                         [f"{self.project}: local skill linear duplicates /tracking-linear:linear"])

    def test_former_name_and_renamed_folder_fail(self):
        skill(self.project, "cadrage", "cadrage")
        skill(self.project, "wiki", "wiki-github")
        problems = check_projects.copies(self.project, self.shared)
        self.assertEqual(len(problems), 2)
        self.assertIn("/core:clarify", problems[0])
        self.assertIn("/docs-wiki-github:wiki-github", problems[1])

    def test_projects_come_from_the_journal(self):
        journal = self.tmp / "dev-journal"
        journal.mkdir()
        (journal / "repos.json").write_text(json.dumps({"repos": ["project", "missing"]}), encoding="utf-8")
        self.assertEqual(check_projects.journal_projects(journal), [self.project])
        self.assertEqual(check_projects.journal_projects(self.tmp / "nowhere"), [])


if __name__ == "__main__":
    unittest.main()
