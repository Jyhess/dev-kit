"""Tests of plugins/tracking-linear/scripts/journal_time.py on a throwaway journal."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "tracking-linear" / "scripts"))
import journal_time  # noqa: E402

WINDOWS = """## 2026-11-02 · windows

### 14:00–15:00 · dev · atelier
Branchement du parseur sur le modèle de composants (ABC-21).
Impasse sur les encodages.

### 15:00–16:00 · ❓ · atelier
Session de 4 min sur ABC-21, trop courte pour conclure.

### 16:00–17:00 · dev · dev-kit
Correction de #12.
"""

MAC = """## 2026-11-03 · mac

### 09:00–10:00 · cadrage · Atelier · déclaré
Cadrage de ABC-22.

### 10:00–11:00 · dev · atelier
Suite de ABC-22.
"""

LATER = "### 09:00–10:00 · dev · atelier\nABC-23.\n"


class JournalTimeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        week = Path(tmp.name) / "journal" / "2026-S45"
        week.mkdir(parents=True)
        (week / "2026-11-02-windows.md").write_text(WINDOWS, encoding="utf-8")
        (week / "2026-11-03-mac.md").write_text(MAC, encoding="utf-8")
        (week / "2026-11-09-mac.md").write_text(LATER, encoding="utf-8")
        (week / "synthese.md").write_text("### 09:00–10:00 · dev · atelier\nABC-21\n", encoding="utf-8")
        self.journal = Path(tmp.name)

    def time(self, since="2026-11-02", until="2026-11-06", project="atelier"):
        return journal_time.time_for(self.journal, project, date.fromisoformat(since), date.fromisoformat(until))

    def test_counts_the_project_hours_of_the_period(self):
        result = self.time()
        self.assertEqual(result["hours"], 3)
        self.assertEqual(result["by_category"], {"cadrage": 1, "dev": 2})

    def test_bounds_are_included(self):
        self.assertEqual(self.time(since="2026-11-03", until="2026-11-09")["hours"], 3)

    def test_other_projects_are_not_counted(self):
        self.assertEqual(self.time(project="dev-kit")["hours"], 1)

    def test_unknown_entries_are_listed_but_not_counted(self):
        unknown = self.time()["unknown"]
        self.assertEqual([(u["day"], u["hour"], u["machine"]) for u in unknown],
                         [("2026-11-02", "15:00", "windows")])


    def week(self) -> Path:
        return self.journal / "journal" / "2026-S45"

    def test_an_hour_logged_by_both_machines_counts_once(self):
        (self.week() / "2026-11-03-windows.md").write_text(
            "## 2026-11-03 · windows\n\n### 10:00–11:00 · dev · atelier\nSuite de ABC-22 sur le PC.\n\n"
            "### 11:00–12:00 · ❓ · atelier\n\n", encoding="utf-8")
        (self.week() / "2026-11-03-mac.md").write_text(
            MAC + "\n### 11:00–12:00 · dev · atelier\nFin de ABC-22.\n", encoding="utf-8")
        result = self.time()
        self.assertEqual(result["hours"], 4)
        self.assertEqual(result["by_category"], {"cadrage": 1, "dev": 3})
        self.assertEqual([(u["day"], u["hour"]) for u in result["unknown"]], [("2026-11-02", "15:00")])

    def test_notes_are_not_part_of_the_last_entry(self):
        (self.week() / "2026-11-04-mac.md").write_text(
            "## 2026-11-04 · mac\n\n### 09:00–10:00 · ❓ · atelier\n\n## Notes\n\n- 10:15 · atelier · Appel.\n",
            encoding="utf-8")
        unknown = [u for u in self.time()["unknown"] if u["day"] == "2026-11-04"]
        self.assertEqual(unknown, [{"day": "2026-11-04", "hour": "09:00", "machine": "mac", "text": ""}])

if __name__ == "__main__":
    unittest.main()
