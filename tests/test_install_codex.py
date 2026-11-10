"""Tests of the Codex skill links and the clone root entry (scripts/install_codex.py)."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install_codex  # noqa: E402


def make_skill(root: Path, plugin: str, skill: str) -> Path:
    folder = root / "plugins" / plugin / "skills" / skill
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: {skill}\n---\n", encoding="utf-8")
    return folder


class CodexLinksTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.clone = base / "dev-kit"
        self.skills_dir = base / "codex" / "skills"
        self.note = make_skill(self.clone, "dev-journal", "note")
        self.docs = make_skill(self.clone, "docs-folder", "docs")

    def install(self):
        return install_codex.install(self.clone, self.skills_dir)

    def test_links_skills_under_prefixed_names(self):
        self.install()
        self.assertEqual(sorted(p.name for p in self.skills_dir.iterdir()),
                         ["dev-kit-dev-journal-note", "dev-kit-docs-folder-docs"])
        self.assertTrue((self.skills_dir / "dev-kit-dev-journal-note" / "SKILL.md").is_file())

    def test_second_run_changes_nothing(self):
        self.install()
        self.assertEqual(self.install(), [])

    def test_renamed_skill_drops_the_dangling_link(self):
        self.install()
        self.note.rename(self.note.with_name("jot"))
        messages = self.install()
        self.assertEqual(sorted(p.name for p in self.skills_dir.iterdir()),
                         ["dev-kit-dev-journal-jot", "dev-kit-docs-folder-docs"])
        self.assertTrue(any("dev-kit-dev-journal-note" in m and "removed" in m for m in messages), messages)

    def test_former_unprefixed_links_into_the_clone_are_removed(self):
        self.skills_dir.mkdir(parents=True)
        (self.skills_dir / "note").symlink_to(self.note, target_is_directory=True)
        self.install()
        self.assertFalse(os.path.lexists(self.skills_dir / "note"))

    def test_entries_not_pointing_into_the_clone_are_kept(self):
        self.skills_dir.mkdir(parents=True)
        elsewhere = self.clone.parent / "other-skill"
        elsewhere.mkdir()
        (self.skills_dir / "other").symlink_to(elsewhere, target_is_directory=True)
        (self.skills_dir / "gone").symlink_to(self.clone.parent / "missing", target_is_directory=True)
        (self.skills_dir / "mine").mkdir()
        (self.skills_dir / "dev-kit-dev-journal-note").mkdir()
        messages = self.install()
        for name in ("other", "gone", "mine", "dev-kit-dev-journal-note"):
            self.assertTrue(os.path.lexists(self.skills_dir / name), name)
        self.assertTrue(any("kept existing" in m for m in messages), messages)

    def test_junction_runs_mklink_without_a_shell_and_reports_its_stderr(self):
        error = subprocess.CalledProcessError(1, "mklink", stderr="Access is denied.")
        with mock.patch.object(install_codex, "windows", return_value=True), \
                mock.patch.object(Path, "symlink_to", side_effect=OSError("no privilege")), \
                mock.patch.object(install_codex.subprocess, "run", side_effect=error) as run:
            messages = self.install()
        args, kwargs = run.call_args
        self.assertEqual(args[0][:4], ["cmd", "/c", "mklink", "/J"])
        self.assertNotIn("shell", kwargs)
        self.assertTrue(any("Access is denied." in m for m in messages), messages)


class RecordRootTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name) / ".dev-kit" / "config.json"
        self.clone = Path(tmp.name) / "dev-kit"

    def test_writes_the_root(self):
        install_codex.record_root(self.clone, self.config)
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8")), {"root": str(self.clone.resolve())})

    def test_keeps_the_other_entries_and_is_idempotent(self):
        self.config.parent.mkdir()
        self.config.write_text(json.dumps({"connectors": {"linear": "mcp__x"}, "root": "/old"}), encoding="utf-8")
        self.assertTrue(install_codex.record_root(self.clone, self.config))
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8")),
                         {"connectors": {"linear": "mcp__x"}, "root": str(self.clone.resolve())})
        self.assertEqual(install_codex.record_root(self.clone, self.config), [])

    def test_unreadable_config_is_an_error_not_overwritten(self):
        self.config.parent.mkdir()
        self.config.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            install_codex.record_root(self.clone, self.config)
        self.assertEqual(self.config.read_text(encoding="utf-8"), "{not json")


class RulesLinkTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.clone = base / "dev-kit"
        self.rules = self.clone / "plugins" / "core" / "rules"
        self.rules.mkdir(parents=True)
        (self.rules / "shared-rules.md").write_text("# Shared rules\n", encoding="utf-8")
        self.link = base / ".dev-kit" / "rules"

    def test_rules_file_resolves_to_the_clone_and_a_second_run_changes_nothing(self):
        self.assertTrue(install_codex.link_rules(self.clone, self.link))
        self.assertEqual((self.link / "shared-rules.md").resolve(), (self.rules / "shared-rules.md").resolve())
        self.assertEqual(install_codex.link_rules(self.clone, self.link), [])

    def test_link_to_a_former_clone_is_replaced(self):
        former = self.clone.parent / "former" / "rules"
        former.mkdir(parents=True)
        self.link.parent.mkdir()
        install_codex.create_link(self.link, former)
        install_codex.link_rules(self.clone, self.link)
        self.assertTrue(install_codex.same_target(self.link, self.rules))
        self.assertTrue(former.is_dir())

    def test_real_folder_is_kept_with_a_warning(self):
        self.link.mkdir(parents=True)
        messages = install_codex.link_rules(self.clone, self.link)
        self.assertTrue(any(m.startswith("warning:") for m in messages), messages)
        self.assertFalse(install_codex.link_target(self.link))


class SkillPathsTest(unittest.TestCase):
    def test_no_skill_climbs_out_of_its_folder(self):
        offenders = [f"{path.relative_to(ROOT)}:{n}"
                     for path in ROOT.glob("plugins/*/skills/**/*.md")
                     for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                     if re.search(r"\.\./\.\.|<base dir>/\.\.", line)]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
