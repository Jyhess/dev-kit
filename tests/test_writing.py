"""Tests of where the writing:com skill finds the user's voice profile (plugins/writing/skills/com/)."""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "writing" / "skills" / "com"
sys.path.insert(0, str(ROOT / "plugins" / "dev-journal" / "scripts"))
import dev_journal  # noqa: E402


class VoiceProfileTest(unittest.TestCase):
    def test_skill_path_leads_to_the_dev_journal_clone(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        path = re.search(r"`<dev folder>/(dev-journal/voice\.md)`, `<dev folder>` being the parent of `<dev-kit>`", text)
        self.assertIsNotNone(path, "SKILL.md must give the profile's path from the dev-kit clone")
        expected = (dev_journal.JOURNAL_REPO / "voice.md").resolve()
        self.assertEqual((ROOT.parent / path.group(1)).resolve(), expected)

    def test_only_the_example_profile_is_in_dev_kit(self):
        profiles = sorted(p.name for p in (ROOT / "plugins" / "writing").rglob("voice*.md"))
        self.assertEqual(profiles, ["voice.example.md"])


if __name__ == "__main__":
    unittest.main()
