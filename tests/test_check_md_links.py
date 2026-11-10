"""Tests of plugins/docs-wiki-github/scripts/check_md_links.py on a throwaway wiki."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "docs-wiki-github" / "scripts"))
import check_md_links  # noqa: E402

PAGES = {
    "README.md": "# Wiki\n\n[Index](Index.md) · [POC](POC/README.md) · [Site](https://example.com)\n",
    "Index.md": "# Index\n\n- [Gestion des dégâts](POC/Gestion-des-dégâts.md#calendrier)\n- [Encoded](POC/Gestion-des-d%C3%A9g%C3%A2ts.md)\n",
    "POC/README.md": "# POC\n\nDocument parent : [Wiki](../README.md)\n\n[Section](#section)\n",
    "POC/Gestion-des-dégâts.md": (
        "# Dégâts\n\n```markdown\n[example](Missing.md) and [[Obsidian]]\n```\n\n"
        "Inline `[code](Nowhere.md)` is ignored.\n"),
}


class CheckMdLinksTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.wiki = Path(tmp.name)
        for name, text in PAGES.items():
            (self.wiki / name).parent.mkdir(parents=True, exist_ok=True)
            (self.wiki / name).write_text(text, encoding="utf-8")
        hidden = self.wiki / ".claude" / "skills"
        hidden.mkdir(parents=True)
        (hidden / "SKILL.md").write_text("[broken](Nope.md)\n", encoding="utf-8")

    def write(self, name, text):
        (self.wiki / name).parent.mkdir(parents=True, exist_ok=True)
        (self.wiki / name).write_text(text, encoding="utf-8")

    def test_clean_wiki_passes(self):
        self.assertEqual(check_md_links.check(self.wiki), [])

    def test_broken_relative_link(self):
        self.write("POC/Page.md", "# Page\n\n[Lost](Lost.md) and [Up](../../Outside.md)\n")
        self.assertEqual(check_md_links.check(self.wiki), [
            "POC/Page.md:3: broken link Lost.md",
            "POC/Page.md:3: broken link ../../Outside.md"])

    def test_absolute_link(self):
        self.write("Index.md", "# Index\n\n[POC](/POC/README.md)\n")
        self.assertEqual(check_md_links.check(self.wiki), ["Index.md:3: absolute link /POC/README.md"])

    def test_obsidian_link(self):
        self.write("Index.md", "# Index\n\nSee [[POC]].\n")
        self.assertEqual(check_md_links.check(self.wiki), ["Index.md:3: Obsidian link [[POC]]"])

    def test_missing_readme(self):
        self.write("Étude/Concurrence.md", "# Concurrence\n")
        self.assertEqual(check_md_links.check(self.wiki), ["Étude/: no README.md"])

    def test_main_exit_code(self):
        self.write("Index.md", "# Index\n\n[Lost](Lost.md)\n")
        sys.argv = ["check_md_links.py", str(self.wiki)]
        with self.assertRaises(SystemExit) as raised, open(self.wiki / ".out", "w", encoding="utf-8") as out:
            sys.stdout, saved = out, sys.stdout
            try:
                check_md_links.main()
            finally:
                sys.stdout = saved
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
