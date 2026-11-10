"""Tests of plugins/dev-journal/scripts/dev_journal.py on throwaway repositories."""

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "dev-journal" / "scripts"))
import dev_journal  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                           "-c", "init.defaultBranch=main", "-C", str(repo), *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def commit(repo: Path, message: str) -> None:
    name = f"{repo.name}-{len(list(repo.glob('*.txt')))}.txt"
    (repo / name).write_text(message, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


class DevJournalTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dev = Path(tmp.name)
        self.journal = self.dev / "dev-journal"
        self.journal.mkdir()
        self.start = dev_journal.now() - dt.timedelta(hours=1)
        self.end = dev_journal.now() + dt.timedelta(hours=1)

    def two_clones(self):
        """A bare remote with two clones standing for the two machines."""
        remote = self.dev / "remote" / "sample.git"
        remote.mkdir(parents=True)
        git(remote, "init", "-q", "--bare")
        clones = []
        for machine in ("mac", "windows"):
            git(self.dev, "clone", "-q", str(remote), machine)
            clones.append(self.dev / machine)
        return clones

    def test_only_commits_made_on_this_machine_count(self):
        mac, windows = self.two_clones()
        commit(mac, "Made on the Mac")
        git(mac, "push", "-q", "origin", "HEAD:main")
        git(windows, "pull", "-q", "origin", "main")
        commit(windows, "Made on Windows")
        commit(windows, "Journal windows 2026-11-01 18:13")
        subjects = [c["subject"] for c in dev_journal.scan_commits([windows], self.start, self.end)]
        self.assertEqual(subjects, ["Made on Windows"])

    def test_rebased_and_amended_commits_count_once(self):
        mac, windows = self.two_clones()
        commit(windows, "First draft")
        git(windows, "commit", "-q", "--amend", "-m", "Final")
        commit(mac, "Made on the Mac")
        git(mac, "push", "-q", "origin", "HEAD:main")
        git(windows, "pull", "-q", "--rebase", "origin", "main")
        subjects = sorted(c["subject"] for c in dev_journal.scan_commits([windows], self.start, self.end))
        self.assertEqual(subjects, ["Final", "First draft"])

    def test_commits_outside_the_window_are_left_out(self):
        _, windows = self.two_clones()
        commit(windows, "Made on Windows")
        later = self.end + dt.timedelta(hours=2)
        self.assertEqual(dev_journal.scan_commits([windows], self.end, later), [])

    def test_missing_repository_is_skipped(self):
        self.assertEqual(dev_journal.scan_commits([self.dev / "missing"], self.start, self.end), [])

    def test_project_is_the_github_repository_name(self):
        _, windows = self.two_clones()
        self.assertEqual(dev_journal.project_name(str(windows)), "sample")
        git(windows, "remote", "set-url", "origin", "git@github.com:Jyhess/atelier-wiki.git")
        dev_journal.project_name.cache_clear()
        self.assertEqual(dev_journal.project_name(str(windows)), "atelier-wiki")
        plain = self.dev / "notes"
        plain.mkdir()
        self.assertEqual(dev_journal.project_name(str(plain)), "notes")

    def test_watched_repositories_are_relative_to_the_dev_folder(self):
        self.assertEqual(dev_journal.add_watched(self.journal, ["shop", "dev-kit"]), ["shop", "dev-kit"])
        self.assertEqual(dev_journal.add_watched(self.journal, ["Shop", "stellar"]), ["stellar"])
        data = json.loads((self.journal / "repos.json").read_text(encoding="utf-8"))
        self.assertEqual(data["repos"], ["dev-kit", "shop", "stellar"])
        self.assertEqual(data["format_version"], 1)
        self.assertEqual(dev_journal.watched_repos(self.journal)[0], self.dev / "dev-kit")

    def test_relative_name_refuses_folders_outside_the_dev_folder(self):
        self.assertEqual(dev_journal.relative_name(self.journal, self.dev / "games" / "chess"), "games/chess")
        with self.assertRaises(ValueError):
            dev_journal.relative_name(self.journal, self.dev.parent / "elsewhere")

    def test_register_commits_and_pushes_the_list(self):
        remote = self.dev / "remote" / "dev-journal.git"
        remote.mkdir(parents=True)
        git(remote, "init", "-q", "--bare")
        clone = self.dev / "clone"
        git(self.dev, "clone", "-q", str(remote), "clone")
        commit(clone, "Initial")
        git(clone, "push", "-q", "origin", "HEAD:main")
        git(clone, "config", "user.name", "Test")
        git(clone, "config", "user.email", "test@example.com")
        self.assertEqual(dev_journal.register(clone, [self.dev / "stellar"]), ["stellar"])
        self.assertEqual(dev_journal.register(clone, [self.dev / "stellar"]), [])
        self.assertIn("Watch stellar", git(remote, "log", "--format=%s", "main"))

    def test_entries_round_trip(self):
        day = dt.date(2026, 11, 2)
        path = dev_journal.day_file(self.journal, day, "windows")
        self.assertEqual(path, self.journal / "journal" / "2026-S45" / "2026-11-02-windows.md")
        entries = {14: (["dev", "atelier"], "Import CSV (ABC-21)."), 15: (["❓", "atelier"], "")}
        dev_journal.write_entries(path, day, "windows", entries)
        self.assertEqual(dev_journal.parse_entries(path), entries)
        self.assertTrue(dev_journal.is_unknown(entries[15][0]))

    def test_notes_are_kept_apart_from_the_entries(self):
        day = dt.date(2026, 11, 2)
        path = dev_journal.day_file(self.journal, day, "windows")
        entries = {14: (["dev", "atelier"], "Import CSV (ABC-21).")}
        dev_journal.write_entries(path, day, "windows", entries)
        dev_journal.add_note(path, day, "windows", "16:05", "atelier", "Idée de post :\n  les exports CSV.")
        dev_journal.add_note(path, day, "windows", "09:30", "dev-kit", "Pourquoi les notes.")
        self.assertEqual(dev_journal.parse_entries(path), entries)
        self.assertEqual(dev_journal.parse_notes(path), ["- 09:30 · dev-kit · Pourquoi les notes.",
                                                         "- 16:05 · atelier · Idée de post : les exports CSV."])
        self.assertTrue(path.read_text(encoding="utf-8").endswith(
            "## Notes\n\n- 09:30 · dev-kit · Pourquoi les notes.\n- 16:05 · atelier · Idée de post : les exports CSV.\n"))

    def test_writing_an_entry_keeps_the_notes(self):
        day = dt.date(2026, 11, 2)
        path = dev_journal.day_file(self.journal, day, "windows")
        dev_journal.add_note(path, day, "windows", "10:15", "atelier", "Bloqué sur les encodages.")
        dev_journal.write_entries(path, day, "windows", {10: (["dev", "atelier"], "Parseur.")})
        self.assertEqual(dev_journal.parse_notes(path), ["- 10:15 · atelier · Bloqué sur les encodages."])
        self.assertEqual(dev_journal.parse_entries(path), {10: (["dev", "atelier"], "Parseur.")})

    def test_invalid_notes_are_refused(self):
        day = dt.date(2026, 11, 2)
        path = dev_journal.day_file(self.journal, day, "windows")
        for time, text in (("9:30", "x"), ("24:00", "x"), ("10:60", "x"), ("10:00", "  \n ")):
            with self.assertRaises(ValueError):
                dev_journal.add_note(path, day, "windows", time, "atelier", text)
        self.assertFalse(path.exists())

    def test_a_note_does_not_fill_a_gap(self):
        day = dev_journal.now().date() - dt.timedelta(days=1)
        while day.weekday() not in dev_journal.WORK_DAYS:
            day -= dt.timedelta(days=1)
        path = dev_journal.day_file(self.journal, day, "windows")
        dev_journal.add_note(path, day, "windows", "10:15", "atelier", "Note.")
        cfg = {"journal": self.journal, "start": day.isoformat()}
        self.assertIn(10, [h for d, h, _ in dev_journal.gaps(cfg) if d == day])

    def test_sessions_of_the_journal_itself_are_ignored(self):
        transcripts = self.dev / "projects"
        (transcripts / "p").mkdir(parents=True)
        ts = dev_journal.now().astimezone(dt.timezone.utc).isoformat()

        def session(name, prompt):
            record = {"type": "user", "timestamp": ts, "cwd": str(self.dev),
                      "message": {"content": prompt}}
            (transcripts / "p" / f"{name}.jsonl").write_text(json.dumps(record), encoding="utf-8")

        session("work", "Corrige le parseur")
        session("task", "[dev-journal] /dev-journal:hourly")
        found = dev_journal.scan_sessions(self.start, self.end, transcripts)
        self.assertEqual([s["session"] for s in found], ["work"])


    def write_session(self, transcripts, name, *prompts):
        ts = dev_journal.now().astimezone(dt.timezone.utc).isoformat()
        records = [{"type": "user", "timestamp": ts, "cwd": str(self.dev), "message": {"content": p}}
                   for p in prompts]
        path = transcripts / "p" / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return path

    def test_transcript_summaries_are_cached_until_the_file_changes(self):
        transcripts = self.dev / "projects"
        path = self.write_session(transcripts, "work", "Corrige le parseur")
        reads = []
        summarize = dev_journal.summarize_transcript
        self.addCleanup(setattr, dev_journal, "summarize_transcript", summarize)
        dev_journal.summarize_transcript = lambda p: reads.append(p.name) or summarize(p)
        cache = {}
        first = dev_journal.scan_sessions(self.start, self.end, transcripts, cache)
        cache = json.loads(json.dumps(cache))  # as saved in state.json
        self.assertEqual(dev_journal.scan_sessions(self.start, self.end, transcripts, cache), first)
        self.assertEqual(reads, ["work.jsonl"])
        self.write_session(transcripts, "work", "Corrige le parseur", "Puis les tests")
        found = dev_journal.scan_sessions(self.start, self.end, transcripts, cache)
        self.assertEqual(reads, ["work.jsonl", "work.jsonl"])
        self.assertEqual([len(h["prompts"]) for h in found[0]["hours"].values()], [2])
        path.unlink()
        dev_journal.scan_sessions(self.start, self.end, transcripts, cache)
        self.assertEqual(cache, {})

    def test_cached_scan_gives_the_same_sessions(self):
        transcripts = self.dev / "projects"
        self.write_session(transcripts, "work", "Corrige le parseur", "Puis les tests")
        self.write_session(transcripts, "task", "[dev-journal] /dev-journal:hourly")
        plain = dev_journal.scan_sessions(self.start, self.end, transcripts)
        cache = {}
        dev_journal.scan_sessions(self.start, self.end, transcripts, cache)
        cached = dev_journal.scan_sessions(self.start, self.end, transcripts, json.loads(json.dumps(cache)))
        self.assertEqual(cached, plain)
        self.assertEqual([s["session"] for s in plain], ["work"])

    def test_pull_runs_in_a_detached_process(self):
        mac, windows = self.two_clones()
        commit(windows, "entry")
        git(windows, "push", "-q", "origin", "HEAD:main")
        git(mac, "fetch", "-q")
        git(mac, "checkout", "-q", "-B", "main", "origin/main")
        commit(windows, "later entry")
        git(windows, "push", "-q", "origin", "HEAD:main")
        state = self.dev / "state.json"
        self.addCleanup(setattr, dev_journal, "STATE", dev_journal.STATE)
        dev_journal.STATE = state
        synchronous = dev_journal.git
        self.addCleanup(setattr, dev_journal, "git", synchronous)
        dev_journal.git = None  # the hook itself runs no git command
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)  # the pull outlives the hook on purpose
            dev_journal.pull(mac)
        dev_journal.git = synchronous
        self.assertIn("last_pull", json.loads(state.read_text(encoding="utf-8")))
        deadline = dt.datetime.now() + dt.timedelta(seconds=20)
        while "later entry" not in git(mac, "log", "-1", "--format=%s") and dt.datetime.now() < deadline:
            subprocess.run([sys.executable, "-c", "import time; time.sleep(0.2)"])
        self.assertEqual(git(mac, "log", "-1", "--format=%s").strip(), "later entry")

    def test_recent_pull_is_not_repeated(self):
        state = self.dev / "state.json"
        self.addCleanup(setattr, dev_journal, "STATE", dev_journal.STATE)
        dev_journal.STATE = state
        dev_journal.save_json(state, {"last_pull": dev_journal.now().isoformat()})
        spawned = []
        self.addCleanup(setattr, dev_journal, "detach", dev_journal.detach)
        dev_journal.detach = spawned.append
        dev_journal.pull(self.journal)
        self.assertEqual(spawned, [])

    def test_journal_and_json_files_are_written_with_lf_only(self):
        day = dt.date(2026, 11, 2)
        path = dev_journal.day_file(self.journal, day, "windows")
        dev_journal.write_entries(path, day, "windows", {14: (["dev", "atelier"], "Ligne 1\nLigne 2")},
                                  ["- 10:15 · atelier · Note."])
        dev_journal.save_json(self.dev / "state.json", {"asked": ["a", "b"]})
        for written in (path, self.dev / "state.json"):
            self.assertNotIn(b"\r\n", written.read_bytes(), written.name)

class UnconfiguredHookTest(unittest.TestCase):
    def test_hook_is_silent_on_a_machine_without_a_journal(self):
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "HOME": home, "USERPROFILE": home}
            result = subprocess.run([sys.executable, str(ROOT / "plugins" / "dev-journal" / "scripts" / "dev_journal.py"),
                                     "check"], input="{}", capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
