"""Tests of plugins/core/scripts/init_project.py on throwaway folders."""

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "core" / "scripts"))
import doc_budget  # noqa: E402
import init_project  # noqa: E402

CONNECTORS = {"mail": "mcp__00000000-0000-0000-0000-000000000001",
              "drive": "mcp__00000000-0000-0000-0000-000000000002",
              "linear": "mcp__00000000-0000-0000-0000-000000000003"}
ANSWERS = {
    "name": "Sample",
    "purpose": "A sample project.",
    "audience": "The user",
    "stack": "Python 3",
    "docs": "docs-folder",
    "tracking": "github-issues",
    "commands": {"tests": "python3 -m unittest"},
    "verify": "python3 -m unittest",
    "ci": True,
}
# An AGENTS.md made from the former AGENTS.en.md template, with project sections around its shared copies.
PAST_AGENTS_MD = """# Sample — shared project instructions

Own intro.

## Communication and languages

- Talk to the user in French.
- A question gets an answer, not an action: change files, tickets or remote state only on an explicit request; "Is it possible to…?" is a question: answer, propose, wait.
- Ask clarifying questions with `/core:clarify` before designing anything non-trivial.

## Writing

- Write what is needed to act, nothing else: no history (git keeps it), no paraphrase of the code, no copy of a ticket (link it); a decision is its choice and its reason in one line.

## Tool results

- Every tool result stays in the context for the rest of the session: ask only for what is needed. Read \
a file range rather than the whole file once its size is known; trim command outputs (`head`, `--stat`, \
`--name-only`, `grep` filters, a tool's own field or format options).

## Delicate points

- Keep me.

## Git

- One commit per feature, fix or change; commit messages in English.
- Push only when asked.
"""
AVAILABLE = {"core", "docs-folder", "tracking-github-issues"}


class FakeGh:
    """Stands for gh on a GitHub repository holding `labels`."""

    def __init__(self, *labels, rebase="true", delete_branch="false"):
        self.labels = list(labels)
        self.rebase = rebase
        self.delete_branch = delete_branch

    def __call__(self, target, *args):
        if args == ("repo", "view", "--json", "rebaseMergeAllowed,deleteBranchOnMerge"):
            return json.dumps({"rebaseMergeAllowed": self.rebase.strip() == "true",
                               "deleteBranchOnMerge": self.delete_branch.strip() == "true"})
        if args == ("api", "-X", "PATCH", "repos/{owner}/{repo}", "-F", "delete_branch_on_merge=true"):
            self.delete_branch = "true\n"
            return "{}"
        if args[:2] == ("label", "list"):
            return json.dumps([{"name": name} for name in self.labels])
        if args[:2] == ("label", "create"):
            self.labels.append(args[2])
            return ""
        return None


class InitProjectTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / "sample"
        self.project.mkdir()
        self.journal = self.tmp / "dev-journal"
        self.gh = FakeGh()
        self.config = self.tmp / "dev-kit-config.json"
        self.config.write_text(json.dumps({"connectors": CONNECTORS}), encoding="utf-8")
        remote = self.tmp / "remote.git"
        for cmd in (["init", "-q", "--bare", str(remote)], ["clone", "-q", str(remote), str(self.journal)]):
            subprocess.run(["git", *cmd], capture_output=True, check=True)
        for key, value in (("user.name", "Test"), ("user.email", "test@example.com")):
            subprocess.run(["git", "-C", str(self.journal), "config", key, value], check=True)

    def plan(self, answers=ANSWERS):
        return init_project.plan(self.project, answers, self.journal, AVAILABLE, self.gh, self.config)

    def add_github_remote(self):
        subprocess.run(["git", "-C", str(self.project), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.project), "remote", "add", "origin",
                        "https://github.com/Jyhess/sample.git"], check=True)

    def apply(self, answers=ANSWERS):
        changes, notes = self.plan(answers)
        for change in changes:
            change.apply()
        return changes, notes

    def read(self, name):
        return (self.project / name).read_text(encoding="utf-8")

    def test_empty_folder_gets_every_file(self):
        self.apply()
        claude = self.read("CLAUDE.md")
        agents = self.read("AGENTS.md")
        self.assertTrue(claude.startswith("@AGENTS.md"))
        self.assertTrue(agents.startswith("# Sample — shared project instructions"))
        self.assertIn("Documentation lives in `docs/`; no wiki. Before committing, check `docs/update-table.md`.", agents)
        self.assertIn("Tasks are GitHub issues of this repository.", agents)
        self.assertIn("`python3 -m unittest`", agents)
        settings = json.loads(self.read(".claude/settings.json"))
        self.assertEqual(settings["enabledPlugins"],
                         {"docs-folder@jyhess": True, "tracking-github-issues@jyhess": True,
                          "anthropic-skills@inline": False})
        self.assertIn("* text=auto", self.read(".gitattributes"))
        self.assertNotIn("eol=lf\n*", self.read(".gitattributes").split("\n", 1)[0])
        for pattern in ("*~", "*.un~", "*.swp", "*.swo"):
            self.assertIn(pattern, self.read(".gitignore").splitlines())
        self.assertIn("python3 -m unittest", self.read(".githooks/pre-push"))
        self.assertNotIn("python3 -m unittest", self.read(".githooks/pre-commit"))
        self.assertIn("The pre-push hook (`.githooks/`) runs `python3 -m unittest`", agents)
        self.assertIn("git commit --fixup <sha>", agents)
        self.assertIn('vocabulary_check.py" --staged || true', self.read(".githooks/pre-commit"))
        self.assertIn('ticket_refs.py" --staged || true', self.read(".githooks/pre-commit"))
        self.assertIn('doc_budget.py" --staged || true', self.read(".githooks/pre-commit"))
        self.assertIn("run: python3 -m unittest", self.read(".github/workflows/verify.yml"))
        self.assertTrue((self.project / ".git").exists())
        hooks = subprocess.run(["git", "-C", str(self.project), "config", "core.hooksPath"],
                               capture_output=True, text=True).stdout.strip()
        self.assertEqual(hooks, ".githooks")

    def test_json_files_saved_with_a_byte_order_mark_are_read(self):
        bom = "﻿"
        self.config.write_text(bom + json.dumps({"connectors": CONNECTORS}), encoding="utf-8")
        for name in ("settings.json", "settings.local.json"):
            path = self.project / ".claude" / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(bom + json.dumps({"permissions": {"deny": ["Kept"]}}), encoding="utf-8")
        self.apply()
        for name in ("settings.json", "settings.local.json"):
            deny = json.loads(self.read(f".claude/{name}"))["permissions"]["deny"]
            self.assertEqual(deny[0], "Kept")
            self.assertGreater(len(deny), 1)

    def test_created_git_hooks_are_executable_in_the_index(self):
        self.apply()
        staged = subprocess.run(["git", "-C", str(self.project), "ls-files", "-s", ".githooks"],
                                capture_output=True, text=True, encoding="utf-8", check=True).stdout
        modes = {line.split("\t")[1]: line.split()[0] for line in staged.splitlines()}
        self.assertEqual(modes, {".githooks/pre-commit": "100755", ".githooks/pre-push": "100755"})

    def test_dry_run_writes_nothing(self):
        changes, _ = self.plan()
        self.assertTrue(changes)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertFalse((self.journal / "repos.json").exists())

    def test_second_run_changes_nothing(self):
        self.add_github_remote()
        self.apply()
        changes, notes = self.plan()
        self.assertEqual([c.description for c in changes], [])
        self.assertEqual(notes, [])

    def test_existing_claude_md_keeps_its_sections_and_imports_shared_instructions(self):
        original = "# Sample\n\nOwn intro.\n\n## Commands\n\n- `make` — own build\n\n## Delicate points\n\n- Keep me.\n"
        (self.project / "CLAUDE.md").write_text(original, encoding="utf-8")
        changes, _ = self.apply()
        claude = self.read("CLAUDE.md")
        self.assertTrue(claude.startswith("@AGENTS.md\n\n" + original.rstrip("\n")))
        self.assertNotIn("@docs/glossary.md", claude)
        self.assertEqual(claude.count("## Commands"), 1)
        agents = self.read("AGENTS.md")
        self.assertIn("## Communication and languages", agents)
        self.assertIn("## Shared rules", agents)
        self.assertIn("## Design", agents)
        description = next(c.description for c in changes if c.description.startswith("CLAUDE.md"))
        self.assertIn("import AGENTS.md", description)
        self.assertNotIn("Commands", description)

    def test_new_agents_md_points_to_the_shared_rules_instead_of_copying_them(self):
        self.apply()
        agents = self.read("AGENTS.md")
        self.assertIn("## Shared rules\n\n- Shared rules: `~/.dev-kit/rules/shared-rules.md`", agents)
        for copied in ("## Writing", "## Context", "## Provisional values", "## Known limitations", "## Git",
                       "A question gets an answer", "shared clarification workflow"):
            self.assertNotIn(copied, agents)
        self.assertIn("Talk to the user in French.", agents)

    def test_verbatim_copies_of_past_shared_sections_are_removed(self):
        (self.project / "AGENTS.md").write_text(PAST_AGENTS_MD, encoding="utf-8")
        changes, notes = self.plan()
        description = next(c.description for c in changes if c.description.startswith("AGENTS.md"))
        self.assertIn("remove the copies of the shared rules: Writing, Tool results, Git", description)
        self.assertIn("2 Communication bullets", description)
        self.assertIn("Shared rules", description)
        self.assertEqual(self.read("AGENTS.md"), PAST_AGENTS_MD)
        self.assertFalse(any("local deviation" in n for n in notes))
        self.apply()
        agents = self.read("AGENTS.md")
        for removed in ("## Writing", "## Tool results", "## Git", "A question gets an answer",
                        "Ask clarifying questions"):
            self.assertNotIn(removed, agents)
        for kept in ("Own intro.", "- Talk to the user in French.", "## Delicate points\n\n- Keep me.",
                     "## Shared rules"):
            self.assertIn(kept, agents)
        changes, _ = self.plan()
        self.assertFalse(any(c.description.startswith("AGENTS.md") for c in changes))

    def test_modified_shared_section_is_kept_and_shown_with_its_diff(self):
        modified = PAST_AGENTS_MD.replace("- Push only when asked.\n", "- Push only when asked.\n- Own git rule.\n")
        (self.project / "AGENTS.md").write_text(modified, encoding="utf-8")
        _, notes = self.apply()
        agents = self.read("AGENTS.md")
        self.assertIn("- Own git rule.", agents)
        self.assertNotIn("## Writing", agents)
        note = next(n for n in notes if "local deviation" in n)
        self.assertIn("AGENTS.md: section Git kept as a local deviation", note)
        self.assertIn("\n+- Own git rule.", note)
        self.assertNotIn("\n-- Push only when asked.", note)

    def test_existing_gitignore_gets_only_the_missing_patterns(self):
        (self.project / ".gitignore").write_text("node_modules/\n*.swp\n", encoding="utf-8")
        self.apply()
        lines = self.read(".gitignore").splitlines()
        self.assertEqual(lines[:2], ["node_modules/", "*.swp"])
        self.assertEqual(lines.count("*.swp"), 1)
        self.assertIn("*.un~", lines)

    def test_existing_gitignore_negation_is_not_overridden(self):
        (self.project / ".gitignore").write_text("*.swp\n!keep.swp\n!*.swo\n", encoding="utf-8")
        self.apply()
        lines = self.read(".gitignore").splitlines()
        self.assertNotIn("*.swo", lines)
        self.assertIn("*.un~", lines)

    def test_existing_catch_all_attributes_cover_the_template_one(self):
        (self.project / ".gitattributes").write_text("* text=auto eol=lf\n*.exe binary\n*.png binary\n",
                                                     encoding="utf-8")
        self.apply()
        lines = self.read(".gitattributes").splitlines()
        self.assertEqual(lines[:3], ["* text=auto eol=lf", "*.exe binary", "*.png binary"])
        self.assertEqual([line for line in lines if line.split()[:1] == ["*"]], ["* text=auto eol=lf"])

    def test_missing_catch_all_attributes_go_before_specific_patterns(self):
        (self.project / ".gitattributes").write_text("*.exe binary\n*.png binary\n", encoding="utf-8")
        self.apply()
        lines = [line for line in self.read(".gitattributes").splitlines() if line.strip()]
        self.assertEqual(lines[0], "* text=auto")
        self.assertLess(lines.index("* text=auto"), lines.index("*.exe binary"))
        self.assertIn("*.sh text eol=lf", lines)

    def test_existing_settings_keep_their_keys(self):
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "enabledPlugins": {"other@x": True}}),
            encoding="utf-8")
        self.apply()
        settings = json.loads(self.read(".claude/settings.json"))
        self.assertEqual(settings["permissions"]["allow"], ["Bash(ls)", *init_project.ALLOWED_TOOLS])
        self.assertEqual(settings["permissions"]["deny"], list(init_project.DENIED_TOOLS))
        self.assertTrue(settings["enabledPlugins"]["other@x"])
        self.assertTrue(settings["enabledPlugins"]["docs-folder@jyhess"])

    def test_anthropic_skills_is_disabled_unless_already_set(self):
        (self.project / ".claude").mkdir()
        path = self.project / ".claude" / "settings.json"
        path.write_text(json.dumps({"enabledPlugins": {"docs-folder@jyhess": True,
                                                       "tracking-github-issues@jyhess": True}}), encoding="utf-8")
        changes, _ = self.plan()
        self.assertTrue(any("disable anthropic-skills@inline" in c.description for c in changes))
        path.write_text(json.dumps({"enabledPlugins": {"docs-folder@jyhess": True,
                                                       "tracking-github-issues@jyhess": True,
                                                       "anthropic-skills@inline": True}}), encoding="utf-8")
        changes, _ = self.plan()
        self.assertFalse(any("disable" in c.description for c in changes))

    def test_unused_tools_are_denied_except_the_kept_ones(self):
        (self.project / ".claude").mkdir()
        path = self.project / ".claude" / "settings.json"
        path.write_text(json.dumps({"permissions": {"deny": ["Bash(rm:*)", "Artifact"]}}), encoding="utf-8")
        self.apply({**ANSWERS, "tracking": "linear", "keep_tools": ["mcp__Claude_Browser"]})
        deny = json.loads(path.read_text(encoding="utf-8"))["permissions"]["deny"]
        self.assertEqual(deny[:2], ["Bash(rm:*)", "Artifact"])
        self.assertEqual(deny.count("Artifact"), 1)
        self.assertNotIn("mcp__Claude_Browser", deny)
        self.assertIn("Workflow", deny)
        changes, _ = self.plan({**ANSWERS, "tracking": "linear", "keep_tools": ["mcp__Claude_Browser"]})
        self.assertFalse(any(".claude/settings.json" in c.description for c in changes))

    def test_required_tools_are_allowed_again(self):
        self.assertFalse(set(init_project.REQUIRED_TOOLS) & set(init_project.DENIED_TOOLS))
        (self.project / ".claude").mkdir()
        path = self.project / ".claude" / "settings.json"
        path.write_text(json.dumps({"permissions": {"deny": ["Artifact", "mcp__visualize"]}}), encoding="utf-8")
        changes, _ = self.plan()
        self.assertTrue(any("allow mcp__visualize" in c.description for c in changes))
        self.apply()
        deny = json.loads(path.read_text(encoding="utf-8"))["permissions"]["deny"]
        self.assertNotIn("mcp__visualize", deny)
        self.assertEqual(deny[0], "Artifact")

    def test_allowed_tools_are_added_once(self):
        self.apply()
        allow = json.loads(self.read(".claude/settings.json"))["permissions"]["allow"]
        self.assertEqual(allow, list(init_project.ALLOWED_TOOLS))
        changes, _ = self.plan()
        self.assertFalse(any(".claude/settings.json" in c.description for c in changes))

    def test_local_connectors_are_denied_in_local_settings_except_the_kept_ones(self):
        self.apply({**ANSWERS, "tracking": "linear", "keep_tools": ["mail"]})
        deny = json.loads(self.read(".claude/settings.local.json"))["permissions"]["deny"]
        self.assertEqual(deny, [CONNECTORS["drive"]])
        shared = json.loads(self.read(".claude/settings.json"))["permissions"]["deny"]
        self.assertFalse(any(prefix in shared for prefix in CONNECTORS.values()))
        changes, _ = self.plan({**ANSWERS, "tracking": "linear", "keep_tools": ["mail"]})
        self.assertFalse(any("settings.local.json" in c.description for c in changes))

    def test_no_local_config_denies_no_connector_and_says_so(self):
        self.config.unlink()
        changes, notes = self.apply()
        self.assertFalse((self.project / ".claude" / "settings.local.json").exists())
        self.assertTrue(any("connectors are not denied" in n for n in notes))

    def test_unavailable_plugin_is_reported_not_enabled(self):
        changes, notes = self.plan({**ANSWERS, "docs": "wiki-github"})
        self.apply({**ANSWERS, "docs": "wiki-github"})
        enabled = json.loads(self.read(".claude/settings.json"))["enabledPlugins"]
        self.assertNotIn("docs-wiki-github@jyhess", enabled)
        self.assertTrue(any("docs-wiki-github" in n for n in notes))

    def test_journal_registration_happens_once_and_is_pushed(self):
        _, notes = self.apply()
        self.assertEqual(json.loads((self.journal / "repos.json").read_text(encoding="utf-8"))["repos"], ["sample"])
        log = subprocess.run(["git", "-C", str(self.tmp / "remote.git"), "log", "--format=%s"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("Watch sample", log)
        self.assertFalse(any("journal" in n for n in notes))
        changes, _ = self.plan()
        self.assertFalse(any("work journal" in c.description for c in changes))

    def test_run_from_a_worktree_uses_the_main_clone_outside_the_repository(self):
        git = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "-C", str(self.project)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "init"], check=True)
        worktree = self.project / ".claude" / "worktrees" / "task"
        subprocess.run(git + ["worktree", "add", "-q", str(worktree)], check=True)
        wiki = self.tmp / "sample-wiki"
        wiki.mkdir()
        answers = {**ANSWERS, "docs": "wiki-github"}
        changes, notes = init_project.plan(worktree, answers, self.journal, AVAILABLE, self.gh, self.config)
        self.assertFalse(any("wiki not cloned" in n for n in notes))
        for change in changes:
            change.apply()
        self.assertEqual(json.loads((self.journal / "repos.json").read_text(encoding="utf-8"))["repos"], ["sample"])
        self.assertTrue((self.project / ".claude" / "settings.local.json").is_file())
        self.assertFalse((worktree / ".claude" / "settings.local.json").exists())
        self.assertTrue((wiki / "Glossaire.md").is_file())
        self.assertTrue((worktree / "AGENTS.md").is_file())

    def test_journal_not_cloned_is_a_note(self):
        changes, notes = init_project.plan(self.project, ANSWERS, self.tmp / "missing", AVAILABLE)
        self.assertFalse(any("work journal" in c.description for c in changes))
        self.assertTrue(any("not cloned" in n for n in notes))

    def test_french_documentation_still_gives_english_instructions(self):
        self.apply({**ANSWERS, "docs": "wiki-github", "languages": {"docs": "fr"}})
        self.assertTrue(self.read("CLAUDE.md").startswith("@AGENTS.md\n\n## Claude Code"))
        agents = self.read("AGENTS.md")
        self.assertTrue(agents.startswith("# Sample — shared project instructions"))
        self.assertIn("Documentation and skills are in French", agents)
        self.assertIn("The wiki is in French.", agents)

    def test_design_principles_are_created_and_existing_pages_kept(self):
        (self.project / "docs" / "design").mkdir(parents=True)
        (self.project / "docs" / "design" / "errors.md").write_text("# Own errors\n", encoding="utf-8")
        self.apply()
        self.assertIn("[errors.md](errors.md)", self.read("docs/design/principles.md"))
        self.assertEqual(self.read("docs/design/errors.md"), "# Own errors\n")
        self.assertIn("never by a comment", self.read("docs/design/robustness.md"))
        self.assertIn("read `docs/design/principles.md`", self.read("AGENTS.md"))

    def test_repository_without_code_gets_no_design_section_nor_pages(self):
        answers = {**ANSWERS, "design": False}
        self.apply(answers)
        agents = self.read("AGENTS.md")
        self.assertNotIn("## Design", agents)
        self.assertIn("## Verification", agents)
        self.assertFalse((self.project / "docs" / "design").exists())
        changes, _ = self.plan(answers)
        self.assertEqual(changes, [])

    def test_new_project_gets_a_vocabulary_section_and_an_empty_glossary(self):
        self.apply()
        agents = self.read("AGENTS.md")
        self.assertIn("## Vocabulary", agents)
        self.assertIn("`docs/glossary.md`", agents)
        glossary = self.read("docs/glossary.md")
        self.assertTrue(glossary.startswith("# Glossary"))
        self.assertIn("| French | English (code) | Displayed (FR) | Displayed (EN) | Definition | Forbidden synonyms |",
                      glossary)
        self.assertEqual(glossary.count("\n|"), 2)  # header and separator only

    def test_project_without_glossary_gets_no_vocabulary_section(self):
        self.apply({**ANSWERS, "glossary": None})
        self.assertNotIn("## Vocabulary", self.read("AGENTS.md"))
        self.assertFalse((self.tmp / "docs" / "glossary.md").exists())

    def test_wiki_project_gets_its_glossary_in_the_wiki(self):
        wiki = self.tmp / "sample-wiki"
        wiki.mkdir()
        changes, notes = self.apply({**ANSWERS, "docs": "wiki-github"})
        self.assertIn("`../sample-wiki/Glossaire.md`", self.read("AGENTS.md"))
        self.assertTrue((wiki / "Glossaire.md").read_text(encoding="utf-8").startswith("# Glossaire"))
        self.assertTrue(any("Index" in n for n in notes))

    def test_wiki_not_cloned_is_a_note(self):
        changes, notes = self.plan({**ANSWERS, "docs": "wiki-github"})
        self.assertFalse(any("Glossaire" in c.description for c in changes))
        self.assertTrue(any("../sample-wiki" in n for n in notes))

    def test_existing_claude_md_imports_agents_with_the_vocabulary_section(self):
        (self.project / "CLAUDE.md").write_text("# Sample\n\n## Git\n\n- Mine.\n", encoding="utf-8")
        self.apply({**ANSWERS, "glossary": "doc/terms.md"})
        self.assertTrue(self.read("CLAUDE.md").startswith("@AGENTS.md"))
        self.assertIn("## Vocabulary", self.read("AGENTS.md"))
        self.assertIn("`doc/terms.md`", self.read("AGENTS.md"))
        self.assertTrue((self.project / "doc" / "terms.md").exists())

    def test_former_glossary_import_is_removed_from_claude_md(self):
        original = "## Vocabulaire\n\n- Le glossaire.\n\n@../sample-wiki/Glossaire.md\n\n## Git\n\n- Mine.\n"
        (self.project / "CLAUDE.md").write_text("@AGENTS.md\n\n" + original, encoding="utf-8")
        changes, _ = self.apply({**ANSWERS, "docs": "wiki-github"})
        claude = self.read("CLAUDE.md")
        self.assertNotIn("@../sample-wiki/Glossaire.md", claude)
        self.assertIn("- Le glossaire.\n\n## Git\n\n- Mine.\n", claude)
        self.assertEqual(claude.count("@AGENTS.md"), 1)
        self.assertTrue(any("remove the glossary import" in c.description for c in changes))

    def test_glossary_entries_are_rendered_sorted(self):
        entries = [
            {"fr": "vaisseau", "en": "ship", "definition": "A modular craft.", "synonyms": ["navire", "nef"]},
            {"fr": "dégâts", "en": "damage", "ui_fr": "PV perdus", "definition": "Hull loss | per hit.",
             "synonyms": []},
        ]
        self.apply({**ANSWERS, "languages": {"docs": "fr"}, "glossary_entries": entries})
        lines = [l for l in self.read("docs/glossary.md").splitlines() if l.startswith("| ") and "---" not in l]
        self.assertEqual(lines[0], "| Français | Anglais (code) | Affiché (FR) | Affiché (EN) | Définition "
                                   "| Synonymes interdits |")
        self.assertEqual(lines[1], "| dégâts | damage | PV perdus |  | Hull loss \\| per hit. |  |")
        self.assertEqual(lines[2], "| vaisseau | ship |  |  | A modular craft. | navire, nef |")

    def test_existing_glossary_is_kept(self):
        (self.project / "docs").mkdir()
        (self.project / "docs" / "glossary.md").write_text("# Mine\n", encoding="utf-8")
        changes, _ = self.apply({**ANSWERS, "glossary_entries": [{"fr": "a", "en": "a"}]})
        self.assertEqual(self.read("docs/glossary.md"), "# Mine\n")
        self.assertFalse(any("glossary" in c.description for c in changes))

    def test_pre_commit_running_the_verification_moves_it_to_pre_push(self):
        hooks = self.project / ".githooks"
        hooks.mkdir()
        (hooks / "pre-commit").write_text("#!/bin/sh\nset -e\npython3 -m unittest\n", encoding="utf-8")
        changes, _ = self.apply()
        descriptions = [c.description for c in changes]
        self.assertIn("create .githooks/pre-push", descriptions)
        self.assertTrue(any(d.startswith("update .githooks/pre-commit") for d in descriptions))
        self.assertIn("python3 -m unittest", self.read(".githooks/pre-push"))
        self.assertNotIn("python3 -m unittest", self.read(".githooks/pre-commit"))
        self.assertIn('doc_budget.py" --staged || true', self.read(".githooks/pre-commit"))

    def test_pre_push_checks_private_words_and_an_existing_one_gets_a_note(self):
        _, notes = self.apply()
        self.assertIn('private_words.py" ${1:+--stdin-refs --remote $1}\nfi\n', self.read(".githooks/pre-push"))
        self.assertFalse(any("private_words.py" in n for n in notes))
        (self.project / ".githooks" / "pre-push").write_text("#!/bin/sh\nmake check\n", encoding="utf-8")
        _, notes = self.plan()
        note = next(n for n in notes if "private_words.py" in n)
        self.assertIn(".githooks/pre-push", note)
        self.assertIn('REFS="$(cat)"', note)
        self.assertIn("printf '%s\\n' \"$REFS\" |", note)
        self.assertIn("/.private-words", self.read(".gitignore").splitlines())

    def test_pre_commit_without_the_verification_is_kept(self):
        hooks = self.project / ".githooks"
        hooks.mkdir()
        (hooks / "pre-commit").write_text("#!/bin/sh\nmake lint\n", encoding="utf-8")
        changes, _ = self.apply()
        self.assertEqual(self.read(".githooks/pre-commit"), "#!/bin/sh\nmake lint\n")
        self.assertFalse(any("pre-commit" in c.description for c in changes))
        self.assertIn("python3 -m unittest", self.read(".githooks/pre-push"))

    def test_no_verify_means_no_hook_and_no_ci(self):
        self.apply({**ANSWERS, "verify": None})
        self.assertFalse((self.project / ".githooks").exists())
        self.assertFalse((self.project / ".github").exists())


    def test_auto_merge_copies_the_workflow_and_its_script(self):
        self.apply({**ANSWERS, "auto_merge": True})
        templates = ROOT / "plugins" / "core" / "templates"
        for path, template in (("workflows/auto-merge.yml", "github-workflows/auto-merge.yml"),
                               ("scripts/auto_merge.py", "github-scripts/auto_merge.py")):
            self.assertEqual(self.read(f".github/{path}"), (templates / template).read_text(encoding="utf-8"))
        changes, _ = self.plan({**ANSWERS, "auto_merge": True})
        self.assertFalse(any("auto" in c.description for c in changes))

    def test_ci_copies_the_pr_template_and_its_check(self):
        self.apply()
        templates = ROOT / "plugins" / "core" / "templates"
        for path, template in (("pull_request_template.md", "pull_request_template.md"),
                               ("workflows/pr-description.yml", "github-workflows/pr-description.yml"),
                               ("scripts/pr_description.py", "github-scripts/pr_description.py")):
            self.assertEqual(self.read(f".github/{path}"), (templates / template).read_text(encoding="utf-8"))
        self.assertFalse(any(name in c.description for c in self.plan()[0]
                             for name in ("pull_request_template", "pr-description", "pr_description")))

    def test_each_copied_script_comes_with_the_scripts_it_imports(self):
        scripts = ROOT / "plugins" / "core" / "templates" / "github-scripts"
        siblings = {path.stem for path in scripts.glob("*.py")}
        for name, files in (("PR_CHECK_FILES", init_project.PR_CHECK_FILES),
                            ("AUTO_MERGE_FILES", init_project.AUTO_MERGE_FILES)):
            copied = {Path(t).stem for t in files.values() if t.startswith("github-scripts/")}
            for script in copied:
                tree = ast.parse((scripts / f"{script}.py").read_text(encoding="utf-8"))
                imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                            for alias in node.names}
                imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
                with self.subTest(files=name, script=script):
                    self.assertLessEqual(imported & siblings, copied)

    def test_auto_merge_copies_the_checker_it_imports_once(self):
        descriptions = [c.description for c in self.plan({**ANSWERS, "auto_merge": True})[0]]
        self.assertEqual(descriptions.count("create .github/scripts/pr_description.py"), 1)
        descriptions = [c.description for c in self.plan({**ANSWERS, "ci": False, "auto_merge": True})[0]]
        self.assertEqual(descriptions.count("create .github/scripts/pr_description.py"), 1)
        self.assertNotIn("create .github/pull_request_template.md", descriptions)

    def test_auto_merge_checks_rebase_merging(self):
        answers = {**ANSWERS, "auto_merge": True}
        self.assertTrue(any("check it once the repository exists" in n for n in self.plan(answers)[1]))
        self.add_github_remote()
        self.assertFalse(any("rebase" in n for n in self.plan(answers)[1]))
        self.gh = FakeGh(rebase="false\n")
        self.assertTrue(any("allow it in the GitHub repository settings" in n for n in self.plan(answers)[1]))

    def test_no_auto_merge_by_default(self):
        changes, notes = self.plan()
        self.assertFalse(any("auto" in c.description for c in changes))
        self.assertFalse(any("rebase" in n for n in notes))

    def test_github_ready_label_waits_for_the_repository_then_is_created_once(self):
        changes, notes = self.plan()
        self.assertFalse(any("label" in c.description for c in changes))
        self.assertTrue(any("label ready not created" in n for n in notes))
        self.add_github_remote()
        changes, _ = self.plan()
        self.assertIn("create the GitHub label ready (Definition of Ready)", [c.description for c in changes])
        self.apply()
        self.assertEqual(self.gh.labels, ["ready"])
        changes, notes = self.plan()
        self.assertFalse(any("label" in c.description for c in changes))
        self.assertFalse(any("label" in n for n in notes))

    def test_branch_deletion_waits_for_the_repository_then_is_turned_on_once(self):
        description = "turn on the GitHub deletion of head branches after merge"
        changes, notes = self.plan()
        self.assertNotIn(description, [c.description for c in changes])
        self.assertTrue(any("deletion of merged branches not turned on" in n for n in notes))
        self.add_github_remote()
        changes, notes = self.plan()
        self.assertIn(description, [c.description for c in changes])
        self.assertFalse(any("merged branches" in n for n in notes))
        self.apply()
        self.assertEqual(self.gh.delete_branch, "true\n")
        self.assertNotIn(description, [c.description for c in self.plan()[0]])

    def test_french_project_gets_the_pret_label(self):
        self.add_github_remote()
        self.apply({**ANSWERS, "languages": {"docs": "fr"}})
        self.assertEqual(self.gh.labels, ["Prêt"])

    def test_existing_ready_label_is_kept(self):
        self.add_github_remote()
        self.gh = FakeGh("Ready")
        changes, _ = self.plan()
        self.assertFalse(any("label" in c.description for c in changes))

    def test_linear_ready_label_is_a_note(self):
        changes, notes = self.plan({**ANSWERS, "tracking": "linear"})
        self.assertFalse(any("label" in c.description for c in changes))
        self.assertTrue(any("label ready in the Linear team" in n for n in notes))

    # Architecture (.NET): docs/architecture.puml, ArchitectureTest.cs and the declaration check.

    def dotnet_project(self, test_package="xunit", single=False):
        """Shop/Shop.csproj and Shop.Tests/Shop.Tests.csproj, or one Shop.csproj with its tests in tests/."""
        def csproj(path, packages, extra=""):
            refs = "".join(f'    <PackageReference Include="{p}" Version="1.0" />\n' for p in packages)
            (self.project / path).parent.mkdir(parents=True, exist_ok=True)
            (self.project / path).write_text(f'<Project Sdk="Microsoft.NET.Sdk">\n{extra}  <ItemGroup>\n{refs}'
                                             '  </ItemGroup>\n</Project>\n', encoding="utf-8")
        packages = ["Microsoft.NET.Test.Sdk", test_package] if test_package else ["Microsoft.NET.Test.Sdk"]
        if single:
            csproj("Atelier.csproj", packages, '  <ItemGroup>\n    <Compile Remove="tools/**" />\n  </ItemGroup>\n')
            return {"project": "Atelier.csproj", "folder": "tests"}
        csproj("Shop/Shop.csproj", [], "  <PropertyGroup>\n    <RootNamespace>Acme.Shop</RootNamespace>\n"
                                        "    <AssemblyName>AcmeShop</AssemblyName>\n  </PropertyGroup>\n")
        csproj("Shop.Tests/Shop.Tests.csproj", packages)
        return {"project": "Shop.Tests/Shop.Tests.csproj", "main": "Shop/Shop.csproj"}

    def test_dotnet_project_gets_the_diagram_its_test_and_the_declaration_check(self):
        answers = {**ANSWERS, "architecture": self.dotnet_project()}
        changes, notes = self.apply(answers)
        described = "\n".join(c.description for c in changes)
        for path in ("docs/architecture.puml", "Shop.Tests/ArchitectureTest.cs", ".github/scripts/architecture.py"):
            self.assertIn(f"create {path}", described)
        self.assertTrue(any("dotnet add Shop.Tests/Shop.Tests.csproj package TngTech.ArchUnitNET" in n
                            and "architecture.py --write" in n
                            and n.index("architecture.py --write") < n.index("ARCHITECTURE_DIAGRAM=write")
                            for n in notes))
        diagram = self.read("docs/architecture.puml")
        self.assertIn("' root: Acme.Shop\n' exclude: Shop.Tests/\n", diagram)
        self.assertTrue(diagram.rstrip().endswith("@startuml\n@enduml"))
        test = self.read("Shop.Tests/ArchitectureTest.cs")
        self.assertIn('Root = "Acme.Shop"', test)
        self.assertIn('System.Reflection.Assembly.Load("AcmeShop")', test)
        self.assertIn("namespace Shop.Tests;", test)
        self.assertEqual(self.read(".github/scripts/architecture.py"),
                         (init_project.TEMPLATES / "github-scripts" / "architecture.py").read_text(encoding="utf-8"))
        check = "python3 -m unittest && python3 .github/scripts/architecture.py"
        self.assertIn(check, self.read(".githooks/pre-push"))
        self.assertIn(check, self.read(".github/workflows/verify.yml"))
        agents = self.read("AGENTS.md")
        self.assertIn("## Architecture\n", agents)
        self.assertIn("`docs/architecture.puml`", agents)
        self.assertIn("`Shop.Tests/ArchitectureTest.cs`", agents)
        self.assertIn("no cycle between components", agents)
        self.assertIn("approved by the user", agents)
        self.assertIn(check, agents)

    def test_single_project_with_tests_in_a_folder(self):
        answers = {**ANSWERS, "architecture": self.dotnet_project("gdUnit4.api", single=True)}
        self.apply(answers)
        self.assertIn("' root: Atelier\n' exclude: tests/ tools/\n", self.read("docs/architecture.puml"))
        test = self.read("tests/ArchitectureTest.cs")
        self.assertIn("namespace Atelier.Tests;", test)
        self.assertIn('System.Reflection.Assembly.Load("Atelier")', test)

    def test_test_attributes_follow_the_framework(self):
        for package, using, class_attribute, test_attribute in (
                ("xunit.v3", "using Xunit;", None, "[Fact]"),
                ("NUnit", "using NUnit.Framework;", "[TestFixture]", "[Test]"),
                ("MSTest.TestFramework", "using Microsoft.VisualStudio.TestTools.UnitTesting;", "[TestClass]",
                 "[TestMethod]"),
                ("gdUnit4.api", "using GdUnit4;", "[TestSuite]", "[TestCase]")):
            with self.subTest(package=package):
                self.setUp()
                self.apply({**ANSWERS, "architecture": self.dotnet_project(package)})
                test = self.read("Shop.Tests/ArchitectureTest.cs")
                self.assertIn(using, test)
                self.assertEqual(test.count(f"    {test_attribute}\n    public void"), 2)
                if class_attribute:
                    self.assertIn(f"{class_attribute}\npublic class ArchitectureTest", test)
                else:
                    self.assertIn("\npublic class ArchitectureTest", test)

    def test_no_known_test_framework_is_a_note_and_no_test(self):
        changes, notes = self.plan({**ANSWERS, "architecture": self.dotnet_project(None)})
        self.assertFalse(any("ArchitectureTest.cs" in c.description for c in changes))
        self.assertTrue(any("no known test framework in Shop.Tests/Shop.Tests.csproj" in n for n in notes))

    def test_existing_architecture_files_are_kept(self):
        answers = {**ANSWERS, "architecture": self.dotnet_project()}
        (self.project / "docs").mkdir()
        (self.project / "docs" / "architecture.puml").write_text("mine\n", encoding="utf-8")
        (self.project / "Shop.Tests" / "ArchitectureTest.cs").write_text("mine\n", encoding="utf-8")
        changes, _ = self.apply(answers)
        self.assertFalse(any("architecture.puml" in c.description or "ArchitectureTest.cs" in c.description
                             for c in changes))
        self.assertEqual(self.read("docs/architecture.puml"), "mine\n")
        self.assertEqual(self.read("Shop.Tests/ArchitectureTest.cs"), "mine\n")

    def test_existing_hook_without_the_check_is_a_note(self):
        answers = {**ANSWERS, "architecture": self.dotnet_project()}
        (self.project / ".githooks").mkdir()
        (self.project / ".githooks" / "pre-push").write_text("#!/bin/sh\nmake check\n", encoding="utf-8")
        _, notes = self.plan(answers)
        self.assertTrue(any("python3 .github/scripts/architecture.py" in n and ".githooks/pre-push" in n
                            for n in notes))

    def test_old_pre_commit_running_the_verification_is_still_replaced(self):
        answers = {**ANSWERS, "architecture": self.dotnet_project()}
        (self.project / ".githooks").mkdir()
        (self.project / ".githooks" / "pre-commit").write_text("#!/bin/sh\npython3 -m unittest\n", encoding="utf-8")
        changes, _ = self.plan(answers)
        self.assertTrue(any(c.description.startswith("update .githooks/pre-commit") for c in changes))

    def test_project_without_csproj_gets_no_architecture(self):
        changes, notes = self.apply({**ANSWERS, "architecture": {"project": "Shop.Tests/Shop.Tests.csproj"}})
        self.assertFalse(any("architecture" in c.description.lower() for c in changes))
        self.assertTrue(any("no .NET (*.csproj), Rust (Cargo workspace), Kotlin (Gradle), Python (pyproject.toml) or "
                            "JS/TS project" in n for n in notes))
        self.assertNotIn("## Architecture", self.read("AGENTS.md"))
        self.assertNotIn("architecture.py", self.read(".githooks/pre-push"))

    def test_no_architecture_answer_means_no_section(self):
        self.dotnet_project()
        changes, _ = self.apply()
        self.assertFalse(any("architecture" in c.description.lower() for c in changes))
        self.assertNotIn("## Architecture", self.read("AGENTS.md"))


    # Architecture (Python): .importlinter, its allowed contracts and the declaration check.

    def python_project(self, lock="uv.lock", flat=False, packages=("shop",)):
        """pyproject.toml, the given lock file and packages under src/ (or at the top), with a tests/ package."""
        (self.project / "pyproject.toml").write_text('[project]\nname = "shop"\n', encoding="utf-8")
        if lock:
            (self.project / lock).write_text("", encoding="utf-8")
        for package in (*packages, "tests"):
            folder = self.project / ("" if flat or package == "tests" else "src") / package
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "__init__.py").write_text("", encoding="utf-8")
        (self.project / ("" if flat else "src") / packages[0] / "orders.py").write_text("", encoding="utf-8")
        return {"stack": "python"}

    def test_python_project_gets_the_contracts_the_script_and_the_check(self):
        answers = {**ANSWERS, "architecture": self.python_project()}
        changes, notes = self.apply(answers)
        described = "\n".join(c.description for c in changes)
        self.assertIn("create .importlinter", described)
        self.assertIn("create .github/scripts/architecture.py", described)
        self.assertTrue(any(n.startswith("architecture, after apply: uv add --dev import-linter; then "
                                         "uv run python .github/scripts/architecture.py --write") for n in notes))
        contracts = self.read(".importlinter")
        self.assertTrue(contracts.startswith("; stack: python\n"))
        self.assertIn("[importlinter]\nroot_package = shop\n", contracts)
        check = "python3 -m unittest && uv run python .github/scripts/architecture.py"
        self.assertIn(check, self.read(".githooks/pre-push"))
        self.assertIn(check, self.read(".github/workflows/verify.yml"))
        agents = self.read("AGENTS.md")
        self.assertIn("`.importlinter`", agents)
        self.assertIn("package `shop`", agents)
        self.assertIn("`uv run python .github/scripts/architecture.py --write`", agents)
        self.assertIn("approved by the user", agents)
        self.assertNotIn("ArchUnitNET", agents)

    def test_written_contracts_header_is_read_by_the_script(self):
        self.apply({**ANSWERS, "architecture": self.python_project()})
        result = subprocess.run([sys.executable, ".github/scripts/architecture.py", "--write"], cwd=self.project,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        contracts = self.read(".importlinter")
        self.assertIn("; Rewrite the contracts from the code: uv run python .github/scripts/architecture.py --write",
                      contracts)
        self.assertIn("[importlinter:contract:orders]\nname = shop.orders\ntype = allowed\ncomponent = shop.orders\n",
                      contracts)

    def test_runner_and_install_command_follow_the_lock_file(self):
        for lock, runner, install in (("poetry.lock", "poetry run ", "poetry add --group dev import-linter"),
                                      (None, "", None)):
            with self.subTest(lock=lock):
                self.setUp()
                changes, notes = self.plan({**ANSWERS, "architecture": self.python_project(lock)})
                self.assertTrue(any(n.startswith(f"architecture, after apply: {install + '; then ' if install else ''}"
                                                 f"{runner}python .github/scripts/architecture.py --write")
                                    for n in notes), notes)
                self.assertEqual(any("add import-linter to the project's development dependencies" in n
                                     for n in notes), install is None)
        changes, notes = self.plan({**ANSWERS, "architecture": {"stack": "python", "runner": "hatch run"}})
        self.assertTrue(any("hatch run python .github/scripts/architecture.py --write" in n for n in notes))

    def test_stack_and_root_are_inferred_in_a_flat_layout(self):
        self.python_project(flat=True)
        self.apply({**ANSWERS, "architecture": {"runner": "uv run"}})
        self.assertIn("root_package = shop\n", self.read(".importlinter"))

    def test_existing_contracts_are_kept_and_nothing_is_set_up(self):
        for name, text in ((".importlinter", "[importlinter]\nroot_package = shop\n"),
                           ("pyproject.toml", '[project]\nname = "shop"\n[tool.importlinter]\nroot_package = "shop"\n')):
            with self.subTest(name=name):
                self.setUp()
                answers = {**ANSWERS, "architecture": self.python_project()}
                (self.project / name).write_text(text, encoding="utf-8")
                changes, notes = self.apply(answers)
                self.assertFalse(any("architecture" in c.description or "importlinter" in c.description
                                     for c in changes))
                self.assertTrue(any(f"{name} already holds import-linter contracts" in n for n in notes))
                self.assertEqual(self.read(name), text)
                self.assertNotIn("## Architecture", self.read("AGENTS.md"))
                self.assertNotIn("architecture.py", self.read(".githooks/pre-push"))

    def test_second_run_keeps_the_written_contracts(self):
        answers = {**ANSWERS, "architecture": self.python_project()}
        self.apply(answers)
        (self.project / ".importlinter").write_text("; stack: python\n[importlinter]\nroot_package = shop\n# mine\n",
                                                   encoding="utf-8")
        changes, notes = self.plan(answers)
        self.assertEqual([c.description for c in changes], [])
        self.assertFalse(any("already holds" in n for n in notes))

    def test_several_packages_are_all_covered_by_default(self):
        self.apply({**ANSWERS, "architecture": self.python_project(packages=("shop", "admin"))})
        self.assertIn("[importlinter]\nroot_packages =\n    admin\n    shop\n", self.read(".importlinter"))
        self.assertIn("packages `admin`, `shop`", self.read("AGENTS.md"))
        result = subprocess.run([sys.executable, ".github/scripts/architecture.py", "--write"], cwd=self.project,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("[importlinter:contract:shop.orders]\n", self.read(".importlinter"))
        self.assertIn("[importlinter:contract:admin]\n", self.read(".importlinter"))

    def test_roots_or_root_restrict_the_packages_covered(self):
        for given in ({"roots": ["admin"]}, {"root": "admin"}):
            with self.subTest(given=given):
                self.setUp()
                self.python_project(packages=("shop", "admin"))
                self.apply({**ANSWERS, "architecture": {"stack": "python", **given}})
                self.assertIn("[importlinter]\nroot_package = admin\n", self.read(".importlinter"))
                self.assertIn("package `admin`", self.read("AGENTS.md"))
        self.setUp()
        self.python_project(packages=("shop", "admin"))
        changes, notes = self.plan({**ANSWERS, "architecture": {"stack": "python", "roots": ["admin", "stock"]}})
        self.assertFalse(any("importlinter" in c.description for c in changes))
        self.assertTrue(any("package stock not found" in n for n in notes), notes)

    def test_no_package_means_nothing(self):
        (self.project / "pyproject.toml").write_text("", encoding="utf-8")
        changes, notes = self.plan({**ANSWERS, "architecture": {"stack": "python"}})
        self.assertFalse(any("architecture" in c.description or "importlinter" in c.description for c in changes))
        self.assertTrue(any("no Python package" in n for n in notes))

    def test_unsupported_stack_is_a_note(self):
        changes, notes = self.plan({**ANSWERS, "architecture": {"stack": "go"}})
        self.assertFalse(any("architecture" in c.description for c in changes))
        self.assertTrue(any("stack go not supported" in n for n in notes))


    # Architecture (Rust): docs/architecture.puml over the crates of the Cargo workspace.

    def rust_workspace(self, crates=("domain", "app")):
        """A Cargo workspace whose crates are under crates/; app depends on domain."""
        members = ", ".join(f'"crates/{c}"' for c in crates)
        (self.project / "Cargo.toml").write_text(f'[workspace]\nresolver = "2"\nmembers = [{members}]\n',
                                                 encoding="utf-8")
        for crate in crates:
            folder = self.project / "crates" / crate
            (folder / "src").mkdir(parents=True)
            (folder / "src" / "lib.rs").write_text("", encoding="utf-8")
            deps = 'domain = { path = "../domain" }\n' if crate == "app" else ""
            (folder / "Cargo.toml").write_text(f'[package]\nname = "{crate}"\nversion = "0.1.0"\n'
                                               f'edition = "2021"\n[dependencies]\n{deps}', encoding="utf-8")
        return {"stack": "rust"}

    def test_rust_workspace_gets_the_diagram_the_script_and_the_check(self):
        answers = {**ANSWERS, "architecture": {**self.rust_workspace(), "exclude": ["xtask"]}}
        changes, notes = self.apply(answers)
        described = "\n".join(c.description for c in changes)
        self.assertIn("create docs/architecture.puml", described)
        self.assertIn("create .github/scripts/architecture.py", described)
        self.assertTrue(any(n.startswith("architecture, after apply: python3 .github/scripts/architecture.py --write")
                            for n in notes), notes)
        diagram = self.read("docs/architecture.puml")
        self.assertTrue(diagram.startswith("' stack: rust\n"))
        self.assertIn("' exclude: xtask\n", diagram)
        check = "python3 -m unittest && python3 .github/scripts/architecture.py"
        self.assertIn(check, self.read(".githooks/pre-push"))
        self.assertIn(check, self.read(".github/workflows/verify.yml"))
        agents = self.read("AGENTS.md")
        self.assertIn("crates of the Cargo workspace", agents)
        self.assertIn("`<<restricted>>`", agents)
        self.assertIn("`python3 .github/scripts/architecture.py --write`", agents)
        self.assertIn("approved by the user", agents)
        self.assertNotIn("ArchUnitNET", agents)

    def test_stack_is_inferred_from_the_workspace_only(self):
        self.rust_workspace()
        (self.project / "pyproject.toml").write_text('[project]\nname = "shop"\n', encoding="utf-8")
        self.apply({**ANSWERS, "architecture": {"exclude": []}})
        self.assertTrue(self.read("docs/architecture.puml").startswith("' stack: rust\n"))
        self.setUp()
        python = self.python_project()
        (self.project / "Cargo.toml").write_text('[package]\nname = "ext"\n', encoding="utf-8")
        changes, _ = self.plan({**ANSWERS, "architecture": {"runner": "uv run"}})
        self.assertIn("create .importlinter", "\n".join(c.description for c in changes))
        self.assertEqual(python, {"stack": "python"})

    def test_single_crate_project_gets_a_note_and_nothing(self):
        for manifest in ('[package]\nname = "app"\n', None):
            with self.subTest(manifest=manifest):
                self.setUp()
                if manifest:
                    (self.project / "Cargo.toml").write_text(manifest, encoding="utf-8")
                changes, notes = self.plan({**ANSWERS, "architecture": {"stack": "rust"}})
                self.assertFalse(any("architecture" in c.description for c in changes))
                expected = "single crate" if manifest else "no Cargo.toml"
                self.assertTrue(any(expected in n and "nothing set up" in n for n in notes), notes)

    def test_existing_diagram_of_another_stack_is_kept(self):
        self.rust_workspace()
        (self.project / "docs").mkdir()
        (self.project / "docs" / "architecture.puml").write_text("@startuml\n[mine]\n@enduml\n", encoding="utf-8")
        changes, notes = self.plan({**ANSWERS, "architecture": {"stack": "rust"}})
        self.assertFalse(any("architecture" in c.description for c in changes))
        self.assertTrue(any("docs/architecture.puml already exists" in n for n in notes), notes)
        (self.project / "docs" / "architecture.puml").write_text("' stack: rust\n@startuml\n[domain]\n@enduml\n",
                                                                 encoding="utf-8")
        changes, notes = self.plan({**ANSWERS, "architecture": {"stack": "rust"}})
        self.assertNotIn("create docs/architecture.puml", "\n".join(c.description for c in changes))
        self.assertIn("create .github/scripts/architecture.py", "\n".join(c.description for c in changes))

    @unittest.skipUnless(shutil.which("cargo"), "cargo not installed")
    def test_written_diagram_header_is_read_by_the_script(self):
        self.apply({**ANSWERS, "architecture": self.rust_workspace()})
        result = subprocess.run([sys.executable, ".github/scripts/architecture.py", "--write"], cwd=self.project,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        diagram = self.read("docs/architecture.puml")
        self.assertIn("' stack: rust\n", diagram)
        self.assertIn("@startuml\n[app]\n[domain]\n[app] --> [domain]\n@enduml\n", diagram)
        result = subprocess.run([sys.executable, ".github/scripts/architecture.py"], cwd=self.project,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)


    # Architecture (Kotlin): docs/architecture.puml, ArchitectureTest.kt (ArchUnit) and the declaration check.

    ANDROID_BUILD = ('plugins {\n    id("com.android.application")\n}\n\nandroid {\n    namespace = "com.meteo.app"\n}\n\n'
                     'dependencies {\n    implementation("androidx.core:core-ktx:1.18.0")\n'
                     '    testImplementation("junit:junit:4.13.2")\n}\n')

    def kotlin_project(self, build=ANDROID_BUILD, build_name="build.gradle.kts", module="app",
                       files=("com/meteo/app/MainActivity.kt", "com/meteo/app/data/api/Api.kt",
                              "com/meteo/app/ui/Screen.java")):
        """A Gradle project like meteo: settings.gradle.kts, gradlew and one module with sources in src/main/java."""
        (self.project / "settings.gradle.kts").write_text('rootProject.name = "Meteo"\ninclude(":app")\n',
                                                          encoding="utf-8")
        (self.project / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
        folder = self.project / module
        folder.mkdir(parents=True, exist_ok=True)
        (folder / build_name).write_text(build, encoding="utf-8")
        for path in files:
            source = folder / "src" / "main" / "java" / path
            source.parent.mkdir(parents=True, exist_ok=True)
            package = ".".join(Path(path).parent.parts)
            source.write_text(f"package {package}{';' if path.endswith('.java') else ''}\n", encoding="utf-8")
        (folder / "src" / "test" / "java").mkdir(parents=True)
        return {"stack": "kotlin"}

    def test_kotlin_module_gets_the_diagram_its_test_archunit_and_the_check(self):
        changes, notes = self.apply({**ANSWERS, "architecture": self.kotlin_project()})
        described = "\n".join(c.description for c in changes)
        test = "app/src/test/java/com/meteo/app/ArchitectureTest.kt"
        for created in ("docs/architecture.puml", test, ".github/scripts/architecture.py"):
            self.assertIn(f"create {created}", described)
        self.assertIn("update app/build.gradle.kts (ArchUnit 1.5.1 test dependency, diagram as test input)", described)
        self.assertTrue(any(n.startswith("architecture, after apply: python3 .github/scripts/architecture.py --write")
                            and "ARCHITECTURE_DIAGRAM=write ./gradlew :app:testDebugUnitTest" in n for n in notes),
                        notes)
        diagram = self.read("docs/architecture.puml")
        self.assertTrue(diagram.startswith("' stack: kotlin\n"))
        self.assertIn("' root: com.meteo.app\n' sources: app/src/main/\n@startuml\n@enduml\n", diagram)
        kotlin_test = self.read(test)
        self.assertTrue(kotlin_test.startswith("package com.meteo.app\n"))
        self.assertIn("\nimport org.junit.Test\n", kotlin_test)
        self.assertIn('const val ROOT = "com.meteo.app"', kotlin_test)
        self.assertEqual(kotlin_test.count("    @Test\n    fun "), 2)
        build = self.read("app/build.gradle.kts")
        self.assertIn('dependencies {\n    testImplementation("com.tngtech.archunit:archunit:1.5.1")\n'
                      '    implementation("androidx.core:core-ktx:1.18.0")\n', build)
        self.assertIn('tasks.withType<Test>().configureEach {\n'
                      '    inputs.file(rootProject.file("docs/architecture.puml"))\n'
                      '    inputs.property("architectureDiagram", '
                      'providers.environmentVariable("ARCHITECTURE_DIAGRAM").orElse(""))\n}\n', build)
        check = "python3 -m unittest && python3 .github/scripts/architecture.py"
        self.assertIn(check, self.read(".githooks/pre-push"))
        agents = self.read("AGENTS.md")
        self.assertIn("Components (each package right under `com.meteo.app`)", agents)
        self.assertIn(f"`{test}` (ArchUnit, with the unit tests: `./gradlew :app:testDebugUnitTest`)", agents)
        self.assertIn("- Declare dependencies in the version catalog `gradle/libs.versions.toml`", agents)
        self.assertIn("approved by the user", agents)
        _, again = self.plan({**ANSWERS, "architecture": {"stack": "kotlin"}})
        self.assertFalse(any("architecture" in c.description or "gradle" in c.description for c in _), _)

    def test_kotlin_stack_is_inferred_and_jvm_groovy_junit5_project_is_supported(self):
        build = ("plugins {\n    id 'org.jetbrains.kotlin.jvm'\n}\n\n"
                 "dependencies {\n    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'\n}\n")
        self.kotlin_project(build, "build.gradle", ".", files=("com/shop/orders/Order.kt", "com/shop/billing/Bill.kt"))
        (self.project / "src" / "test" / "kotlin").mkdir(parents=True)
        self.apply({**ANSWERS, "architecture": {"module": "."}})
        self.assertIn("' root: com.shop\n' sources: src/main/\n", self.read("docs/architecture.puml"))
        kotlin_test = self.read("src/test/kotlin/com/shop/ArchitectureTest.kt")
        self.assertIn("\nimport org.junit.jupiter.api.Test\n", kotlin_test)
        build = self.read("build.gradle")
        self.assertIn("dependencies {\n    testImplementation 'com.tngtech.archunit:archunit:1.5.1'\n", build)
        self.assertIn("tasks.withType(Test).configureEach {\n    inputs.file(rootProject.file('docs/architecture.puml'))",
                      build)
        self.assertIn("`./gradlew test`", self.read("AGENTS.md"))

    def test_junit_from_the_version_catalog_and_archunit_already_there(self):
        build = ('plugins {\n    alias(libs.plugins.kotlin.jvm)\n}\n'
                 'dependencies {\n    testImplementation(libs.junit)\n    testImplementation(libs.archunit)\n}\n')
        answer = self.kotlin_project(build)
        (self.project / "gradle").mkdir()
        (self.project / "gradle" / "libs.versions.toml").write_text(
            '[libraries]\njunit = { group = "junit", name = "junit", version = "4.13.2" }\n', encoding="utf-8")
        changes, _ = self.apply({**ANSWERS, "architecture": answer})
        self.assertIn("update app/build.gradle.kts (diagram as test input)", "\n".join(c.description for c in changes))
        self.assertNotIn("com.tngtech.archunit", self.read("app/build.gradle.kts"))
        self.assertIn("\nimport org.junit.Test\n", self.read("app/src/test/java/com/meteo/app/ArchitectureTest.kt"))

    def test_build_file_without_dependencies_block_gets_one(self):
        self.assertEqual(init_project.gradle_test_setup("plugins {}\n", False, False).split("\n\n")[1],
                         'dependencies {\n    testImplementation("com.tngtech.archunit:archunit:1.5.1")\n}')

    def test_kotlin_without_junit_is_a_note_and_no_test(self):
        changes, notes = self.plan({**ANSWERS, "architecture": self.kotlin_project('plugins {}\n')})
        self.assertFalse(any("ArchitectureTest.kt" in c.description for c in changes))
        self.assertTrue(any("no JUnit 4 or 5 dependency in app/build.gradle.kts" in n for n in notes), notes)

    def test_kotlin_project_that_cannot_be_set_up_gets_a_note_and_nothing(self):
        def two_modules():
            self.kotlin_project()
            self.kotlin_project(module="wear")
        cases = [(lambda: None, {"stack": "kotlin"}, "no Gradle build"),
                 (two_modules, {"stack": "kotlin"}, "several Gradle modules with sources (app, wear)"),
                 (lambda: self.kotlin_project(files=()), {"stack": "kotlin"}, "no Gradle module with Kotlin or Java"),
                 (self.kotlin_project, {"stack": "kotlin", "module": "lib"}, "module lib not found"),
                 (lambda: self.kotlin_project(files=("Main.kt",)), {"stack": "kotlin"}, "no common package")]
        for prepare, answer, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                prepare()
                changes, notes = self.plan({**ANSWERS, "architecture": answer})
                self.assertFalse(any("architecture" in c.description or "gradle" in c.description for c in changes))
                self.assertTrue(any(expected in n and "nothing set up" in n or expected in n and "not covered yet" in n
                                    for n in notes), notes)

    def test_several_modules_with_a_chosen_one(self):
        self.kotlin_project()
        self.kotlin_project(module="wear")
        self.apply({**ANSWERS, "architecture": {"stack": "kotlin", "module": "wear", "root": "com.meteo"}})
        self.assertIn("' root: com.meteo\n' sources: wear/src/main/\n", self.read("docs/architecture.puml"))
        self.assertIn("ARCHITECTURE_DIAGRAM=write ./gradlew :wear:testDebugUnitTest", self.read("AGENTS.md"))

    def test_existing_diagram_of_another_stack_is_kept_for_kotlin(self):
        answer = self.kotlin_project()
        (self.project / "docs").mkdir()
        (self.project / "docs" / "architecture.puml").write_text("@startuml\n[mine]\n@enduml\n", encoding="utf-8")
        changes, notes = self.plan({**ANSWERS, "architecture": answer})
        self.assertFalse(any("architecture" in c.description for c in changes))
        self.assertTrue(any("without `' stack: kotlin`" in n for n in notes), notes)

    def test_written_kotlin_diagram_header_is_read_by_the_script(self):
        self.apply({**ANSWERS, "architecture": self.kotlin_project()})
        for args in (["--write"], []):
            result = subprocess.run([sys.executable, ".github/scripts/architecture.py", *args], cwd=self.project,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("@startuml\n[com.meteo.app] <<com.meteo.app>>\n[com.meteo.app.data] <<com.meteo.app.data..>>\n"
                      "[com.meteo.app.ui] <<com.meteo.app.ui..>>\n@enduml\n", self.read("docs/architecture.puml"))

    # Architecture (JS/TS): docs/architecture.json, the imports read by dependency-cruiser.

    def js_project(self, package=True, files=("src/hooks/useTimer.ts", "src/lib/clock.ts", "app/index.tsx")):
        """A package.json (or none) and the given sources."""
        if package:
            (self.project / "package.json").write_text(json.dumps(
                package if isinstance(package, dict) else {"name": "sample"}), encoding="utf-8")
        for path in files:
            (self.project / path).parent.mkdir(parents=True, exist_ok=True)
            (self.project / path).write_text("", encoding="utf-8")
        return {"stack": "js"}

    def test_js_project_gets_the_architecture_file_the_config_and_the_checks(self):
        changes, notes = self.apply({**ANSWERS, "architecture": self.js_project()})
        described = "\n".join(c.description for c in changes)
        for created in ("docs/architecture.json", ".dependency-cruiser.cjs", ".github/scripts/architecture.py"):
            self.assertIn(f"create {created}", described)
        self.assertNotIn("create package.json", described)
        content = json.loads(self.read("docs/architecture.json"))
        self.assertEqual({k: v for k, v in content.items() if k != "comment"},
                         {"stack": "js", "roots": ["src", "app"], "exclude": [], "components": {}})
        self.assertTrue(any(n.startswith("architecture, after apply: npm install --save-dev dependency-cruiser; then "
                                         "python3 .github/scripts/architecture.py --write") for n in notes), notes)
        check = "python3 -m unittest && python3 .github/scripts/architecture.py"
        self.assertIn(check, self.read(".githooks/pre-push"))
        self.assertIn("      - uses: actions/checkout@v4\n      - run: npm ci\n      - run: " + check,
                      self.read(".github/workflows/verify.yml"))
        self.assertIn("node_modules/", self.read(".gitignore").splitlines())
        agents = self.read("AGENTS.md")
        self.assertIn("`docs/architecture.json`, checked with dependency-cruiser", agents)
        self.assertIn("`python3 .github/scripts/architecture.py --write`", agents)
        self.assertIn("approved by the user", agents)

    def test_js_sources_without_package_json_get_one_and_the_stack_is_inferred(self):
        self.js_project(package=False, files=("src/content.js", "options/options.js", "test/parser.test.js"))
        changes, _ = self.apply({**ANSWERS, "name": "Jak Tube", "architecture": {"roots": ["."], "exclude": ["icons/"]}})
        self.assertIn("create package.json", "\n".join(c.description for c in changes))
        self.assertEqual(json.loads(self.read("package.json")), {"name": "jak-tube", "private": True})
        content = json.loads(self.read("docs/architecture.json"))
        self.assertEqual((content["stack"], content["roots"], content["exclude"]), ("js", ["."], ["icons/"]))

    def test_installed_dependency_cruiser_is_not_installed_again(self):
        answer = self.js_project({"name": "sample", "devDependencies": {"dependency-cruiser": "^18.0.0"}})
        _, notes = self.plan({**ANSWERS, "architecture": answer})
        self.assertTrue(any(n.startswith("architecture, after apply: python3 .github/scripts/architecture.py --write")
                            for n in notes), notes)

    def test_monorepo_missing_root_or_no_js_gets_a_note_and_nothing(self):
        cases = [(lambda: self.js_project(package=False, files=("backend/package.json", "backend/src/a.ts")),
                  {"stack": "js"}, "backend/package.json but no package.json at the root"),
                 (lambda: None, {"stack": "js"}, "no package.json nor JS/TS source"),
                 (lambda: self.js_project(), {"stack": "js", "roots": ["lib"]}, "root lib not found")]
        for prepare, answer, expected in cases:
            with self.subTest(expected=expected):
                self.setUp()
                prepare()
                changes, notes = self.plan({**ANSWERS, "architecture": answer})
                self.assertFalse(any("architecture" in c.description or "cruiser" in c.description for c in changes))
                self.assertTrue(any(expected in n and "nothing set up" in n for n in notes), notes)

    def test_existing_architecture_file_or_dependency_cruiser_config_is_kept(self):
        for path, text, expected in (
                ("docs/architecture.json", '{"layers": []}', "docs/architecture.json already exists"),
                (".dependency-cruiser.js", "module.exports = {};", ".dependency-cruiser.js already exists")):
            with self.subTest(path=path):
                self.setUp()
                answer = self.js_project()
                (self.project / path).parent.mkdir(parents=True, exist_ok=True)
                (self.project / path).write_text(text, encoding="utf-8")
                changes, notes = self.plan({**ANSWERS, "architecture": answer})
                self.assertFalse(any("architecture" in c.description or "cruiser" in c.description for c in changes))
                self.assertTrue(any(expected in n for n in notes), notes)
        self.setUp()
        answer = self.js_project()
        (self.project / "docs").mkdir()
        (self.project / "docs" / "architecture.json").write_text('{"stack": "js", "roots": ["src"]}', encoding="utf-8")
        described = "\n".join(c.description for c in self.plan({**ANSWERS, "architecture": answer})[0])
        self.assertNotIn("create docs/architecture.json", described)
        self.assertIn("create .dependency-cruiser.cjs", described)

    def test_existing_verify_workflow_gets_a_note_for_npm_ci(self):
        answer = self.js_project()
        (self.project / ".github" / "workflows").mkdir(parents=True)
        (self.project / ".github" / "workflows" / "verify.yml").write_text("steps:\n", encoding="utf-8")
        _, notes = self.plan({**ANSWERS, "architecture": answer})
        self.assertIn("architecture: add `- run: npm ci` before the verification in .github/workflows/verify.yml",
                      notes)

    def test_other_stacks_get_no_npm_step_nor_node_modules(self):
        self.apply({**ANSWERS, "architecture": self.rust_workspace()})
        self.assertNotIn("npm ci", self.read(".github/workflows/verify.yml"))
        self.assertNotIn("node_modules/", self.read(".gitignore"))
        self.assertNotIn("__pycache__/", self.read(".gitignore"))

    def test_python_project_gitignore_covers_builds_caches_and_venv(self):
        for architecture in (self.python_project(), None):  # with the Python architecture, or a pyproject.toml alone
            with self.subTest(architecture=architecture):
                self.apply({**ANSWERS, "architecture": architecture})
                lines = self.read(".gitignore").splitlines()
                for pattern in ("*.egg-info/", "__pycache__/", ".venv/"):
                    self.assertIn(pattern, lines)
                (self.project / ".gitignore").unlink()

    @unittest.skipUnless(shutil.which("depcruise"), "dependency-cruiser not installed")
    def test_written_architecture_file_is_read_by_the_script(self):
        answer = self.js_project(files=())
        (self.project / "src" / "lib").mkdir(parents=True)
        (self.project / "src" / "lib" / "clock.js").write_text("export const now = 1;\n", encoding="utf-8")
        (self.project / "src" / "index.js").write_text("import { now } from './lib/clock.js';\n", encoding="utf-8")
        self.apply({**ANSWERS, "architecture": answer})
        for args in (["--write"], []):
            result = subprocess.run([sys.executable, ".github/scripts/architecture.py", *args], cwd=self.project,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(self.read("docs/architecture.json"))["components"],
                         {"src": ["src/lib"], "src/lib": []})


    def test_every_stack_has_a_resolver_a_planner_and_its_agents_text(self):
        self.assertEqual(set(init_project.RESOLVERS), set(init_project.STACKS))
        self.assertEqual(set(init_project.PLANNERS), set(init_project.STACKS.values()))
        self.assertEqual(set(init_project.INSTRUCTIONS["architecture"]), set(init_project.STACKS))

    def test_generated_instructions_stay_within_their_budget(self):
        """With every optional section, the longest wiki line and each stack's architecture."""
        projects = {"none": lambda: None, "dotnet": self.dotnet_project, "python": self.python_project,
                    "rust": self.rust_workspace, "kotlin": self.kotlin_project,
                    "js": self.js_project}
        self.assertEqual(set(projects) - {"none"}, set(init_project.STACKS))
        for stack, project in projects.items():
            for language in ("en", "fr"):
                with self.subTest(stack=stack, language=language):
                    self.setUp()
                    (self.tmp / "sample-wiki").mkdir()
                    self.apply({**ANSWERS, "docs": "wiki-github", "languages": {"docs": language, "wiki": language},
                                "architecture": project()})
                    for name in ("AGENTS.md", "CLAUDE.md"):
                        size = len(self.read(name).encode("utf-8"))
                        self.assertLessEqual(size, doc_budget.DEFAULTS[name], name)


if __name__ == "__main__":
    unittest.main()
