"""End-to-end test of the Kotlin architecture set up by project-init: ArchitectureTest.kt (ArchUnit) and
architecture.py on a throwaway one-module Gradle project. Needs a JDK, Gradle on the PATH and Maven Central, a few
minutes: runs only with DEV_KIT_KOTLIN_TEMPLATE=1, in the kotlin-template job of .github/workflows/verify.yml."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "core" / "templates" / "github-scripts" / "architecture.py"
sys.path.insert(0, str(ROOT / "plugins" / "core" / "scripts"))
import init_project  # noqa: E402

ENABLED = os.environ.get("DEV_KIT_KOTLIN_TEMPLATE") == "1"
KOTLIN_VERSION = "2.3.21"
SETTINGS = """pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
rootProject.name = "shop"
include(":app")
"""
BUILD = f"""plugins {{
    kotlin("jvm") version "{KOTLIN_VERSION}"
}}

dependencies {{
    testImplementation("junit:junit:4.13.2")
}}
"""
MAIN = "app/src/main/kotlin/com/shop/"
# A root class depending on itself and a top-level function (class ShopKt) in the root; Billing depends on Orders.
SOURCES = {
    MAIN + "Shop.kt": "package com.shop\n\nclass Shop {\n    private val count = 1\n    fun copy() = Shop()\n}\n\n"
                      "fun main() {}\n",
    MAIN + "orders/Order.kt": "package com.shop.orders\n\ndata class Order(val total: Int = 1)\n",
    MAIN + "billing/Invoice.kt": "package com.shop.billing\n\nimport com.shop.orders.Order\n\n"
                                 "class Invoice {\n    val order = Order()\n}\n",
}
ORDER_USING_BILLING = ("package com.shop.orders\n\nimport com.shop.billing.Invoice\n\n"
                       "data class Order(val total: Int = 1) {\n    fun invoice() = Invoice()\n}\n")


@unittest.skipUnless(ENABLED, "DEV_KIT_KOTLIN_TEMPLATE=1 not set")
class KotlinTemplateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.gradle = shutil.which("gradle")
        self.assertIsNotNone(self.gradle, "gradle not found")
        self.write("settings.gradle.kts", SETTINGS)
        self.write("app/build.gradle.kts", BUILD)
        for path, text in SOURCES.items():
            self.write(path, text)
        found, notes = init_project.resolve_kotlin(self.repo, {})
        self.assertIsNotNone(found, notes)
        self.architecture = found
        changes, _ = init_project.plan_kotlin(self.repo, {"name": "Shop"}, found)
        for change in changes:
            change.apply()

    def write(self, path, text):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def run_command(self, *command, env=None):
        return subprocess.run(command, cwd=self.repo, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env={**os.environ, **(env or {})})

    def check(self, *command, env=None):
        result = self.run_command(*command, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def gradle_test(self, env=None):
        """The command project-init gives for the unit tests, with this machine's Gradle."""
        _, *args = self.architecture.gradle_test.split()
        return self.run_command(self.gradle, *args, "--console=plain", env=env)

    def test_written_diagram_passes_and_an_undrawn_dependency_fails(self):
        self.assertEqual(self.architecture.gradle_test, "gradle :app:test")
        self.check(sys.executable, str(SCRIPT), "--write", ".")
        diagram = (self.repo / "docs/architecture.puml").read_text(encoding="utf-8")
        self.assertIn("@startuml\n[com.shop] <<com.shop>>\n[com.shop.billing] <<com.shop.billing..>>\n"
                      "[com.shop.orders] <<com.shop.orders..>>\n@enduml\n", diagram)
        result = self.gradle_test({"ARCHITECTURE_DIAGRAM": "write"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        diagram = (self.repo / "docs/architecture.puml").read_text(encoding="utf-8")
        self.assertTrue(diagram.endswith("[com.shop.billing] --> [com.shop.orders]\n@enduml\n"), diagram)
        result = self.gradle_test()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.check(sys.executable, str(SCRIPT), ".")
        # The diagram is a test input: without its arrow, the tests run again although the code did not change.
        arrow = "[com.shop.billing] --> [com.shop.orders]\n"
        self.write("docs/architecture.puml", diagram.replace(arrow, ""))
        result = self.gradle_test()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.write("docs/architecture.puml", diagram)
        self.write(MAIN + "orders/Order.kt", ORDER_USING_BILLING)
        result = self.gradle_test()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        report = "".join(p.read_text(encoding="utf-8") for p in (self.repo / "app/build/test-results").rglob("*.xml"))
        self.assertIn("com.shop.orders.Order", report)
        self.assertIn("com.shop.billing.Invoice", report)


if __name__ == "__main__":
    unittest.main()
