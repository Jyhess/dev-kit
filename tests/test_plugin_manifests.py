import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class PluginManifestsTest(unittest.TestCase):
    def test_marketplace_and_plugin_descriptions_are_equal(self):
        """One description per plugin: the marketplace entry and the plugin's own manifest say the same."""
        for entry in load(ROOT / ".claude-plugin" / "marketplace.json")["plugins"]:
            with self.subTest(plugin=entry["name"]):
                manifest = load(ROOT / entry["source"] / ".claude-plugin" / "plugin.json")
                self.assertEqual(manifest["name"], entry["name"])
                self.assertEqual(manifest["description"], entry["description"])


if __name__ == "__main__":
    unittest.main()
