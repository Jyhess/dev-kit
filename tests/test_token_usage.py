"""Tests of scripts/token_usage.py on a small fake transcript."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import token_usage  # noqa: E402

SECRET = "PROMPT-TEXT-THAT-MUST-NOT-LEAK"


def usage(read, write, output=10):
    return {"input_tokens": 2, "output_tokens": output, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write,
            "cache_creation": {"ephemeral_1h_input_tokens": write, "ephemeral_5m_input_tokens": 0}}


def assistant(msg_id, stamp, u, content=None):
    return {"type": "assistant", "timestamp": stamp, "cwd": "C:\\dev\\shop\\.claude\\worktrees\\shop-1",
            "message": {"id": msg_id, "model": "claude-opus-5-5", "usage": u, "content": content or []}}


def user(content, **extra):
    return {"type": "user", "message": {"role": "user", "content": content}, **extra}


def transcript():
    """A session: prompt, startup attachments, a skill, a tool result, an idle gap with a cache rebuild."""
    return [
        {"type": "api-request-shape", "shape": {"system": [{"type": "text", "text": "s" * 400}],
                                                "tools": [{"name": "Artifact", "description": "a" * 800},
                                                          {"name": "mcp__Claude_Browser__navigate"}]}},
        {"type": "attachment", "attachment": {"type": "instructions", "files": [
            {"path": "C:\\dev\\shop\\CLAUDE.md", "content": "c" * 4000}]}},
        {"type": "attachment", "attachment": {"type": "skill_listing", "content": "k" * 800}},
        user(f"{SECRET} implement ABC-1", origin={"kind": "human"}),
        assistant("m1", "2026-11-02T08:00:00Z", usage(0, 70_000),
                  [{"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "tracking-linear:linear"}}]),
        # Streamed copy of the same message: must count once.
        assistant("m1", "2026-11-02T08:00:00Z", usage(0, 70_000)),
        user([{"type": "tool_result", "tool_use_id": "t1", "content": "r" * 400}]),
        assistant("m2", "2026-11-02T08:01:00Z", usage(70_000, 1_000),
                  [{"type": "tool_use", "id": "t2", "name": "Edit", "input": {}}]),
        {"type": "attachment", "attachment": {"type": "skill_listing", "content": "late"}},
        user("next prompt", origin={"kind": "human"}),
        assistant("m3", "2026-11-02T10:00:00Z", usage(0, 260_000, output=100)),
        assistant("m0", "2026-10-30T10:00:00Z", usage(5, 5)),
        {"type": "assistant", "message": {"id": "x", "model": "<synthetic>", "usage": usage(9, 9)}},
    ]


def write(path: Path, records) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\nnot json\n", encoding="utf-8")
    return path


class TokenUsageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.since = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.path = write(self.root / "C--dev-shop" / "abc12345-0000.jsonl", transcript())
        self.session = token_usage.read_session(self.path, self.since)

    def test_streamed_copies_count_once_and_old_calls_are_skipped(self):
        u = self.session.usage
        self.assertEqual(u.calls, 3)
        self.assertEqual(u.cache_read, 70_000)
        self.assertEqual(u.cache_write_1h, 331_000)
        self.assertEqual(u.output, 120)

    def test_quota_units_weight_token_types(self):
        u = token_usage.Usage(input=10, output=10, cache_read=100, cache_write_5m=4, cache_write_1h=5)
        self.assertEqual(u.units, 10 + 50 + 10 + 5 + 10)

    def test_old_api_usage_without_split_counts_as_5_minute_cache(self):
        u = token_usage.usage_of({"cache_creation_input_tokens": 8})
        self.assertEqual((u.cache_write_5m, u.cache_write_1h), (8, 0))

    def test_session_shape(self):
        s = self.session
        self.assertEqual(s.project, "shop")
        self.assertEqual(s.kind, "implementation")
        self.assertEqual(s.start_context, 70_002)
        self.assertEqual(s.max_context, 260_002)
        self.assertEqual((s.rebuilds, s.rebuild_tokens), (1, 260_000))

    def test_startup_counts_attachments_before_the_first_answer_only(self):
        s = self.session
        self.assertEqual(s.instruction_chars["CLAUDE.md"], 4000)
        self.assertIn("skill_listing", s.startup_chars)
        self.assertLess(s.startup_chars["skill_listing"], 900)
        self.assertEqual(s.prefix_chars["tool:Artifact"], len(json.dumps({"name": "Artifact", "description": "a" * 800})))

    def test_tool_results_and_skill_cost(self):
        s = self.session
        self.assertEqual(s.tool_result_chars["Skill"], 400)
        self.assertEqual(s.skills["linear"], 1)
        # The skill runs from its call to the next prompt: m2 only (m1 is the call that invokes it).
        self.assertAlmostEqual(s.skill_units["linear"], token_usage.usage_of(usage(70_000, 1_000)).units)

    def test_project_of_folds_worktrees(self):
        self.assertEqual(token_usage.project_of("C:\\dev\\shop\\.claude\\worktrees\\x"), "shop")
        self.assertEqual(token_usage.project_of("/Users/j/dev/shop-wiki/"), "shop-wiki")

    def test_classify(self):
        c = token_usage.classify
        none = token_usage.Counter()
        self.assertEqual(c("<scheduled-task>[dev-journal] hourly", True, none, none), "journal")
        self.assertEqual(c("<scheduled-task>other", True, none, none), "scheduled")
        self.assertEqual(c("Relis la PR", False, token_usage.Counter(Edit=1), none), "review")
        self.assertEqual(c("clarify this", False, none, token_usage.Counter(clarify=1)), "clarification")
        self.assertEqual(c("what is it?", False, none, none), "question")

    def test_bucket(self):
        self.assertEqual(token_usage.bucket(10), "0k-50k")
        self.assertEqual(token_usage.bucket(150_000), "150k-200k")
        self.assertEqual(token_usage.bucket(900_000), "400k+")

    def test_report_shows_aggregates_but_no_prompt_text(self):
        sessions = token_usage.read_all(self.root, self.since)
        text = token_usage.report(sessions)
        self.assertIn("| shop | 1 | 3 |", text)
        self.assertIn("| Artifact |", text)
        self.assertIn("| linear | 1 |", text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(SECRET, token_usage.as_json(sessions))

    def test_save_writes_a_dated_report_in_the_history_folder(self):
        history = self.root / "history"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            token_usage.main(["--root", str(self.root), "--since", "2026-11-01", "--save", "--history", str(history)])
        self.assertIn("saved ", out.getvalue())
        [path] = history.glob("*.md")
        self.assertRegex(path.name, r"^\d{4}-\d{2}-\d{2}\.md$")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Token usage\n\nMeasured on "))
        self.assertIn(", since 2026-11-01.", text)
        self.assertIn("| shop | 1 | 3 |", text)
        self.assertNotIn(SECRET, text)

    def test_history_folder_is_in_the_main_clone(self):
        self.assertEqual(token_usage.history_dir().parts[-2:], ("history", "token-usage"))
        self.assertTrue((token_usage.history_dir().parents[1] / ".git").is_dir())

    def test_empty_session_is_ignored(self):
        path = write(self.root / "p" / "empty.jsonl", [user("hello")])
        self.assertIsNone(token_usage.read_session(path))


if __name__ == "__main__":
    unittest.main()
