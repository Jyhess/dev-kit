"""Tests of plugins/core/scripts/context_size.py on throwaway transcripts."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "core" / "scripts" / "context_size.py"
spec = importlib.util.spec_from_file_location("context_size", SCRIPT)
context_size = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context_size)

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
W, L = context_size.WARN, context_size.LIMIT


def call(tokens, when=NOW, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain, "timestamp": when.isoformat().replace("+00:00", "Z"),
            "message": {"usage": {"input_tokens": 2, "cache_creation_input_tokens": 1000,
                                  "cache_read_input_tokens": tokens - 1002, "output_tokens": 500}}}


class ContextSizeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.transcript = self.dir / "session.jsonl"
        self.state = self.dir / "state"
        self.entries = [{"type": "user", "message": {"content": "hi"}}]

    def add(self, *entries):
        self.entries.extend(entries)
        self.transcript.write_text("".join(json.dumps(e) + "\n" for e in self.entries), encoding="utf-8")

    def hook(self, event="PostToolUse", source=None, now=NOW):
        hook_input = {"hook_event_name": event, "session_id": "s1", "transcript_path": str(self.transcript)}
        if source:
            hook_input["source"] = source
        return context_size.run(hook_input, self.state, now)

    def test_small_context_says_nothing(self):
        self.add(call(80_000))
        self.assertIsNone(self.hook())

    def test_each_level_warns_once(self):
        self.add(call(W + 1_000))
        first = self.hook()
        self.assertIn(f"{(W + 1_000) // 1000}k", first["hookSpecificOutput"]["additionalContext"])
        self.assertIn("ask them whether to hand over", first["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(first["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertEqual(len(first["systemMessage"].splitlines()), 1)
        self.add(call(W + 20_000))
        self.assertIsNone(self.hook("UserPromptSubmit"))
        self.add(call(L + 5_000))
        self.assertIn("recommending to hand over", self.hook()["hookSpecificOutput"]["additionalContext"])
        self.add(call(L + 60_000))
        self.assertIsNone(self.hook())

    def test_jump_past_the_limit_warns_with_the_limit_only(self):
        self.add(call(L + 30_000))
        self.assertIn("recommending to hand over", self.hook()["hookSpecificOutput"]["additionalContext"])
        self.add(call(L + 40_000))
        self.assertIsNone(self.hook())

    def test_levels_rearm_under_the_warning_level(self):
        self.add(call(W + 10_000))
        self.assertIsNotNone(self.hook())
        self.add(call(60_000))
        self.assertIsNone(self.hook())
        self.add(call(W + 5_000))
        self.assertIsNotNone(self.hook())

    def test_compaction_hides_the_previous_size(self):
        self.add(call(W + 10_000), {"type": "system", "subtype": "compact_boundary"})
        self.assertIsNone(self.hook())

    def test_subagent_calls_are_ignored(self):
        self.add(call(50_000), call(W + 30_000, sidechain=True))
        self.assertIsNone(self.hook())

    def test_resume_after_the_cache_expired_with_a_big_context(self):
        self.add(call(120_000, NOW - timedelta(hours=14)))
        result = self.hook("SessionStart", "resume")
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("14h", result["hookSpecificOutput"]["additionalContext"])

    def test_resume_without_cost_says_nothing(self):
        self.add(call(120_000, NOW - timedelta(minutes=30)))
        self.assertIsNone(self.hook("SessionStart", "resume"))
        self.add(call(90_000, NOW - timedelta(hours=14)))
        self.assertIsNone(self.hook("SessionStart", "resume"))
        self.add(call(120_000, NOW - timedelta(hours=14)))
        self.assertIsNone(self.hook("SessionStart", "startup"))

    def test_resume_remembers_the_level(self):
        self.add(call(W + 20_000, NOW - timedelta(hours=3)))
        self.assertIsNotNone(self.hook("SessionStart", "resume"))
        self.assertIsNone(self.hook("UserPromptSubmit"))

    def test_last_call_beyond_the_tail_is_found(self):
        self.add(call(160_000), {"type": "user", "message": {"content": "x" * (context_size.TAIL + 10)}})
        self.assertEqual(context_size.last_call(self.transcript)[0], 160_000)

    def test_a_big_transcript_is_read_from_its_tail_only(self):
        # PostToolUse runs it after every tool call: its cost must not grow with the transcript.
        filler = {"type": "user", "message": {"content": "x" * 10_000}}
        self.add(*[filler] * 2_000, call(160_000))  # 20 MB
        start = time.perf_counter()
        self.assertIsNone(self.hook())
        self.assertLess(time.perf_counter() - start, 0.5)

    def test_missing_transcript_says_nothing(self):
        self.assertIsNone(context_size.run({"hook_event_name": "PostToolUse",
                                            "transcript_path": str(self.dir / "none.jsonl")}, self.state, NOW))


class ContextSizeScriptTest(unittest.TestCase):
    def run_script(self, stdin, tmp):
        env = dict(os.environ, TMP=tmp, TEMP=tmp, TMPDIR=tmp)
        return subprocess.run([sys.executable, str(SCRIPT)], input=stdin, capture_output=True, env=env)

    def test_prints_one_json_object_and_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "t.jsonl"
            transcript.write_text(json.dumps(call(context_size.LIMIT + 10_000, datetime.now(timezone.utc))) + "\n", encoding="utf-8")
            hook_input = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "abc",
                                     "transcript_path": str(transcript)}).encode()
            result = self.run_script(hook_input, tmp)
            self.assertEqual(result.returncode, 0)
            self.assertIn(f"{(context_size.LIMIT + 10_000) // 1000}k", json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(self.run_script(hook_input, tmp).stdout, b"")

    def test_bad_input_never_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script(b"not json", tmp)
            self.assertEqual((result.returncode, result.stdout), (0, b""))


if __name__ == "__main__":
    unittest.main()
