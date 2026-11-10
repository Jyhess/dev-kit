"""Tests of plugins/core/scripts/shared_rules.py, the session-start hook, on throwaway projects."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "plugins" / "core" / "scripts" / "shared_rules.py"
RULES = ROOT / "plugins" / "core" / "rules" / "shared-rules.md"
HOOKS_JSON = ROOT / "plugins" / "core" / "hooks" / "hooks.json"
MARKER = "## Shared rules\n\n- Shared rules: `~/.dev-kit/rules/shared-rules.md`.\n"


def run_hook(project, *extra):
    result = subprocess.run([sys.executable, str(HOOK), "--project", str(project), *extra],
                            capture_output=True, text=True, encoding="utf-8")
    return result.returncode, json.loads(result.stdout) if result.stdout.strip() else None


class SharedRulesHookTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / "sample"
        self.project.mkdir()

    def test_marker_section_injects_the_whole_rules_file(self):
        (self.project / "AGENTS.md").write_text(f"# Sample\n\n{MARKER}\n## Commands\n\n- `make`\n", encoding="utf-8")
        code, output = run_hook(self.project)
        self.assertEqual(code, 0)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(output["hookSpecificOutput"]["additionalContext"], RULES.read_text(encoding="utf-8"))
        self.assertNotIn("systemMessage", output)

    def test_legacy_claude_md_with_the_marker(self):
        (self.project / "CLAUDE.md").write_text(f"# Sample\n\n{MARKER}", encoding="utf-8")
        code, output = run_hook(self.project)
        self.assertIn("## Git", output["hookSpecificOutput"]["additionalContext"])

    def test_no_marker_section_prints_nothing(self):
        (self.project / "AGENTS.md").write_text("# Sample\n\n## Git\n\n- Shared rules are copied here.\n",
                                                encoding="utf-8")
        self.assertEqual(run_hook(self.project), (0, None))

    def test_no_instructions_prints_nothing(self):
        self.assertEqual(run_hook(self.project), (0, None))

    def test_edited_rules_file_is_read_at_each_start(self):
        (self.project / "AGENTS.md").write_text(MARKER, encoding="utf-8")
        rules = self.project.parent / "rules.md"
        rules.write_text("# Shared rules\n\n- New rule.\n", encoding="utf-8")
        self.assertEqual(run_hook(self.project, "--rules", str(rules))[1]["hookSpecificOutput"]["additionalContext"],
                         "# Shared rules\n\n- New rule.\n")
        rules.write_text("# Shared rules\n\n- Edited rule.\n", encoding="utf-8")
        self.assertIn("Edited rule", run_hook(self.project, "--rules", str(rules))[1]
                      ["hookSpecificOutput"]["additionalContext"])

    def test_missing_rules_file_warns_without_blocking(self):
        (self.project / "AGENTS.md").write_text(MARKER, encoding="utf-8")
        code, output = run_hook(self.project, "--rules", str(self.project / "missing.md"))
        self.assertEqual(code, 0)
        self.assertNotIn("hookSpecificOutput", output)
        self.assertEqual(len(output["systemMessage"].splitlines()), 1)


class SharedRulesFileTest(unittest.TestCase):
    def test_fits_the_hook_output_cap(self):
        self.assertLess(len(RULES.read_text(encoding="utf-8")), 10_000)

    def test_hook_runs_on_every_session_start(self):
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        matchers = [entry["matcher"] for entry in hooks
                    if any("shared_rules.py" in hook["command"] for hook in entry["hooks"])]
        self.assertEqual(matchers, ["startup|resume|clear|compact"])


if __name__ == "__main__":
    unittest.main()
