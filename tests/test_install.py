"""Tests of scripts/install.py with a fake runner standing for the claude and git CLIs."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install  # noqa: E402


class FakeMachine:
    """Records commands and answers them like a machine in the given state."""

    def __init__(self, marketplace=False, plugins=(), hooks=False):
        self.marketplaces = {"jyhess", "humanizer"} if marketplace else set()
        self.plugins, self.hooks = set(plugins), hooks
        self.calls = []

    def __call__(self, cmd):
        cmd = list(cmd)
        self.calls.append(cmd)
        out = ""
        if cmd[1:4] == ["plugin", "marketplace", "list"]:
            out = json.dumps([{"name": m} for m in sorted(self.marketplaces)])
        elif cmd[1:3] == ["plugin", "list"]:
            out = json.dumps([{"id": p} for p in sorted(self.plugins)])
        elif cmd[1:4] == ["plugin", "marketplace", "add"]:
            self.marketplaces.add("humanizer" if cmd[4] == "blader/humanizer" else "jyhess")
        elif cmd[1:3] == ["plugin", "install"]:
            self.plugins.add(cmd[3])
        elif cmd[0] == "git" and cmd[-1] == "core.hooksPath":
            out = ".githooks" if self.hooks else ""
        elif cmd[0] == "git":
            self.hooks = True
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def changes(self):
        return [c for c in self.calls if "list" not in c and c[-1] != "core.hooksPath"]


class InstallTest(unittest.TestCase):
    def test_fresh_machine_gets_marketplace_plugin_and_hooks(self):
        machine = FakeMachine()
        done = install.install(machine, "claude", ROOT)
        self.assertEqual(len(done), 7)
        self.assertEqual(machine.changes(), [
            ["claude", "plugin", "marketplace", "add", str(ROOT), "--scope", "user"],
            ["claude", "plugin", "marketplace", "add", "blader/humanizer", "--scope", "user"],
            ["claude", "plugin", "install", "core@jyhess", "--scope", "user"],
            ["claude", "plugin", "install", "dev-journal@jyhess", "--scope", "user"],
            ["claude", "plugin", "install", "writing@jyhess", "--scope", "user"],
            ["claude", "plugin", "install", "humanizer@humanizer", "--scope", "user"],
            ["git", "-C", str(ROOT), "config", "core.hooksPath", ".githooks"],
        ])

    def test_second_run_changes_nothing(self):
        machine = FakeMachine()
        install.install(machine, "claude", ROOT)
        machine.calls.clear()
        self.assertEqual(install.install(machine, "claude", ROOT), [])
        self.assertEqual(machine.changes(), [])

    def test_failed_command_raises(self):
        def failing(cmd):
            return subprocess.CompletedProcess(list(cmd), 1, "", "boom")
        with self.assertRaises(RuntimeError):
            install.install(failing, "claude", ROOT)


def recorder(calls):
    def runner(cmd):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(list(cmd), 0, "", "")
    return runner


class SetupJournalTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        self.dev = self.home / "dev"
        self.journal = self.dev / "dev-journal"
        (self.journal / ".git").mkdir(parents=True)
        self.calls = []

    def setup(self, url=None):
        return install.setup_journal(recorder(self.calls), self.home, self.journal, "windows", url)

    def config(self):
        return json.loads((self.home / ".dev-journal" / "config.json").read_text(encoding="utf-8"))

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_existing_config_is_kept_and_a_second_run_does_nothing(self):
        self.write(self.home / ".dev-journal" / "config.json", {"machine": "mac", "start": "2026-10-31"})
        done, notes = self.setup()
        self.assertEqual(self.config(), {"machine": "mac", "start": "2026-10-31"})
        self.assertEqual(done, [])
        self.assertEqual(self.calls, [])
        self.assertTrue(any("create the hourly journal task" in n for n in notes))

    def test_new_machine_clones_the_given_journal_and_records_its_url(self):
        (self.journal / ".git").rmdir()
        done, _ = self.setup("https://example.com/me/journal.git")
        self.assertEqual(self.calls[0][:4], ["git", "clone", "--quiet", "https://example.com/me/journal.git"])
        self.assertEqual(self.config()["machine"], "windows")
        self.assertEqual(self.config()["journal_url"], "https://example.com/me/journal.git")
        self.assertEqual(len(done), 2)

    def test_configured_url_is_cloned_without_the_option(self):
        (self.journal / ".git").rmdir()
        self.write(self.home / ".dev-journal" / "config.json",
                   {"machine": "mac", "start": "2026-10-31", "journal_url": "git@example.com:me/j.git"})
        done, _ = self.setup()
        self.assertEqual(self.calls[0][3], "git@example.com:me/j.git")
        self.assertEqual(len(done), 1)

    def test_no_journal_configured_skips_it_with_a_note(self):
        (self.journal / ".git").rmdir()
        done, notes = self.setup()
        self.assertEqual((done, self.calls), ([], []))
        self.assertFalse((self.home / ".dev-journal" / "config.json").exists())
        self.assertEqual(len(notes), 1)
        self.assertIn("--journal-url", notes[0])

    def test_url_given_to_an_existing_install_is_recorded_without_cloning(self):
        self.write(self.home / ".dev-journal" / "config.json", {"machine": "mac", "start": "2026-10-31"})
        self.setup("https://example.com/me/journal.git")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.config(), {"machine": "mac", "start": "2026-10-31",
                                         "journal_url": "https://example.com/me/journal.git"})

    def test_existing_hourly_task_is_recognised(self):
        task = self.home / ".claude" / "scheduled-tasks" / "journal" / "SKILL.md"
        task.parent.mkdir(parents=True)
        task.write_text("[dev-journal] /dev-journal:hourly", encoding="utf-8")
        _, notes = self.setup()
        self.assertEqual(notes, [])

    def test_machine_name(self):
        self.assertEqual(install.machine_name("darwin"), "mac")
        self.assertEqual(install.machine_name("win32"), "windows")


if __name__ == "__main__":
    unittest.main()
