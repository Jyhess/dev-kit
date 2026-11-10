"""Tests of the architecture checks (plugins/core/templates/github-scripts/architecture.py)."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "core" / "templates" / "github-scripts" / "architecture.py"
sys.path.insert(0, str(SCRIPT.parent))
import architecture  # noqa: E402
from architecture import Kind, Problem  # noqa: E402

HEADER = "' root: Shop\n' exclude: tests/ tools/\n"
# A root class with a field initialiser depends on itself.
ROOT_CLASS = "namespace Shop;\n\npublic class Shop\n{\n    private readonly int count = 1;\n}\n"


class DeclarationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)

    def diagram(self, *components, header=HEADER):
        lines = [f"[{c}] <<{architecture.stereotype(c, 'Shop', components)}>>" for c in components]
        self.write("docs/architecture.puml", header + "@startuml\n" + "\n".join(lines) + "\n[Shop.Orders] --> [Shop.Billing]\n@enduml\n")

    def write(self, path, text):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def problems(self):
        return architecture.problems(self.repo)

    def test_diagram_with_or_without_a_stack_line_is_dotnet(self):
        self.diagram("Shop.Orders")
        self.assertEqual(architecture.stack(self.repo), "dotnet")
        self.diagram("Shop.Orders", header="' stack: dotnet\n" + HEADER)
        self.assertEqual(architecture.stack(self.repo), "dotnet")

    def test_code_matching_the_diagram_passes(self):
        self.diagram("Shop.Orders", "Shop.Billing")
        self.write("src/Orders/Order.cs", "namespace Shop.Orders;\npublic class Order {}\n")
        self.write("src/Orders/Lines/Line.cs", "namespace Shop.Orders.Lines\n{\n    public class Line {}\n}\n")
        self.write("src/Billing/Invoice.cs", "using Shop.Orders;\n\nnamespace   Shop.Billing {\n}\n")
        self.assertEqual(self.problems(), [])

    def test_new_namespace_is_undeclared(self):
        self.diagram("Shop.Orders")
        self.write("Orders/Order.cs", "namespace Shop.Orders;\n")
        self.write("Stock/Item.cs", "namespace Shop.Stock.Items;\n")
        self.assertEqual(self.problems(), [Problem(Kind.UNDECLARED, "Shop.Stock", "Stock/Item.cs")])

    def test_component_without_code_is_absent(self):
        self.diagram("Shop.Orders", "Shop.Billing")
        self.write("Orders/Order.cs", "namespace Shop.Orders;\n")
        self.assertEqual(self.problems(), [Problem(Kind.ABSENT, "Shop.Billing", "docs/architecture.puml")])

    def test_types_in_the_root_namespace_are_the_root_component(self):
        self.diagram("Shop", "Shop.Orders")
        self.write("Main.cs", ROOT_CLASS)
        self.write("Orders/Order.cs", "namespace Shop.Orders;\n")
        self.assertEqual(self.problems(), [])
        self.diagram("Shop.Orders")
        self.assertEqual(self.problems(), [Problem(Kind.UNDECLARED, "Shop", "Main.cs")])

    def test_excluded_and_build_folders_are_ignored(self):
        self.diagram("Shop.Orders")
        self.write("Orders/Order.cs", "namespace Shop.Orders;\n")
        self.write("tests/OrderTest.cs", "namespace Shop.Tests;\n")
        self.write("tools/Gen.cs", "namespace Tools;\n")
        self.write("obj/Debug/Generated.cs", "namespace Shop.Generated;\n")
        self.write("bin/Gen.cs", "namespace Shop.Bin;\n")
        self.write(".godot/mono/Gen.cs", "namespace Shop.Godot;\n")
        self.assertEqual(self.problems(), [])

    def test_namespace_outside_the_root_and_file_without_namespace_are_reported(self):
        self.diagram("Shop.Orders")
        self.write("Orders/Order.cs", "namespace Shop.Orders;\n")
        self.write("Other/Thing.cs", "namespace Elsewhere.Things;\n")
        self.write("Script.cs", "// namespace Shop.Fake;\npublic class Script {}\n")
        self.assertEqual(self.problems(), [Problem(Kind.OUTSIDE_ROOT, "Elsewhere.Things", "Other/Thing.cs"),
                                           Problem(Kind.NO_NAMESPACE, "", "Script.cs")])

    def test_missing_diagram_or_root_is_reported(self):
        self.assertEqual(self.problems(), [Problem(Kind.NO_DIAGRAM, "", "docs/architecture.puml")])
        self.diagram("Shop.Orders", header="' exclude: tests/\n")
        self.assertEqual(self.problems(), [Problem(Kind.NO_ROOT, "", "docs/architecture.puml")])

    def test_stereotype_is_an_anchored_namespace_pattern(self):
        components = ["Shop", "Shop.Orders", "Shop.Billing"]
        self.assertEqual(architecture.stereotype("Shop.Orders", "Shop", components), r"^Shop\.Orders(\..+)?$")
        self.assertEqual(architecture.stereotype("Shop", "Shop", components), r"^Shop(\.(?!Billing$|Orders$)[^.]+)?$")
        self.assertEqual(architecture.stereotype("Shop", "Shop", ["Shop"]), r"^Shop(\.[^.]+)?$")

    def test_each_type_and_namespace_matches_only_its_component_stereotype(self):
        # ArchUnitNET matches each type and each dependency target by its full name against the stereotypes: none
        # fails AdheresToDiagram (a root class depending on itself, ROOT_CLASS), several throws.
        components = ["Shop", "Shop.Orders", "Shop.Billing"]
        patterns = {c: architecture.stereotype(c, "Shop", components) for c in components}
        # A root type cannot share a component's name (CS0101), except a generic one: Shop.Orders`1.
        for name, component in (("Shop", "Shop"), ("Shop.Shop", "Shop"), ("Shop.Shop+Line", "Shop"),
                                ("Shop.Orders`1", "Shop"),
                                ("Shop.Orders", "Shop.Orders"), ("Shop.Orders.Order", "Shop.Orders"),
                                ("Shop.Orders.Lines.Line", "Shop.Orders"), ("Shop.Billing.Invoice", "Shop.Billing")):
            with self.subTest(name=name):
                self.assertEqual([c for c, p in patterns.items() if re.match(p, name)], [component])

    def code(self):
        self.write("Main.cs", ROOT_CLASS)
        self.write("Orders/Order.cs", "namespace Shop.Orders;\n")
        self.write("Billing/Invoice.cs", "namespace Shop.Billing;\n")

    def test_stereotype_not_generated_is_stale(self):
        # A component added by hand without rewriting the root's stereotype: its namespace matches two components.
        self.code()
        self.write("docs/architecture.puml", HEADER + "@startuml\n"
                   r"[Shop] <<^Shop(\.(?!Orders$)[^.]+)?$>>" "\n"
                   r"[Shop.Orders] <<^Shop\.Orders(\..+)?$>>" "\n"
                   r"[Shop.Billing] <<^Shop\.Billing(\..+)?$>>" "\n@enduml\n")
        self.assertEqual(self.problems(), [Problem(Kind.STALE_STEREOTYPE, "Shop", "docs/architecture.puml")])

    def test_write_rewrites_the_components_and_keeps_the_other_lines(self):
        self.code()
        self.write("docs/architecture.puml", HEADER + "@startuml\nskinparam componentStyle rectangle\n"
                   "[Shop.Orders] <<old>>\n[Shop.Gone] <<^Shop\\.Gone(\\..+)?$>>\n"
                   "[Shop.Billing] --> [Shop.Orders]\n[Shop.Orders] --> [Shop.Gone]\n@enduml\n")
        result = subprocess.run([sys.executable, str(SCRIPT), "--write", str(self.repo)], capture_output=True,
                                text=True)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual((self.repo / "docs/architecture.puml").read_text(encoding="utf-8"), HEADER + "@startuml\n"
                         r"[Shop] <<^Shop(\.(?!Billing$|Orders$)[^.]+)?$>>" "\n"
                         r"[Shop.Billing] <<^Shop\.Billing(\..+)?$>>" "\n"
                         r"[Shop.Orders] <<^Shop\.Orders(\..+)?$>>" "\n"
                         "skinparam componentStyle rectangle\n[Shop.Billing] --> [Shop.Orders]\n@enduml\n")
        self.assertEqual(self.problems(), [])

    def test_write_needs_a_startuml_line(self):
        self.code()
        self.write("docs/architecture.puml", HEADER)
        self.assertEqual(architecture.write_dotnet_diagram(self.repo),
                         [Problem(Kind.NO_STARTUML, "", "docs/architecture.puml")])

    def test_command_exits_1_and_names_each_problem(self):
        self.diagram("Shop.Orders")
        self.write("Stock/Item.cs", "namespace Shop.Stock;\n")
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.repo)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Stock/Item.cs: Shop.Stock: namespace not declared in docs/architecture.puml", result.stdout)
        self.assertIn("docs/architecture.puml: Shop.Orders: component declared but no code in it", result.stdout)


KT_HEADER = "' stack: kotlin\n' root: com.shop\n' sources: app/src/main/\n"
KT_MAIN = "app/src/main/java/com/shop/"


class KotlinDeclarationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)

    def write(self, path, text):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def diagram(self, *lines, header=KT_HEADER):
        self.write("docs/architecture.puml", header + "@startuml\n" + "".join(line + "\n" for line in lines)
                   + "@enduml\n")

    def code(self):
        self.write(KT_MAIN + "MainActivity.kt", "@file:JvmName(\"Main\")\n\npackage com.shop\n\nclass MainActivity\n")
        self.write(KT_MAIN + "data/api/Api.kt", "package com.shop.data.api\n\ninterface Api\n")
        self.write(KT_MAIN + "ui/Screen.java", "package com.shop.ui;\n\npublic class Screen {}\n")

    def problems(self):
        return architecture.problems(self.repo)

    def test_stack_line_selects_kotlin(self):
        self.diagram()
        self.assertEqual(architecture.stack(self.repo), "kotlin")

    def test_code_matching_the_diagram_passes(self):
        self.code()
        self.diagram("[com.shop] <<com.shop>>", "[com.shop.data] <<com.shop.data..>>", "[com.shop.ui] <<com.shop.ui..>>",
                     "[com.shop.ui] --> [com.shop.data]")
        self.assertEqual(self.problems(), [])

    def test_stereotype_is_an_archunit_package_identifier(self):
        # The root holds only its own types; ArchUnit matches `com.shop` to that package alone, `x..` to x and below.
        self.assertEqual(architecture.kotlin_stereotype("com.shop", "com.shop", ["com.shop", "com.shop.ui"]), "com.shop")
        self.assertEqual(architecture.kotlin_stereotype("com.shop.ui", "com.shop", ["com.shop"]), "com.shop.ui..")

    def test_new_package_absent_component_and_stale_stereotype_are_reported(self):
        self.code()
        self.diagram("[com.shop] <<com.shop..>>", "[com.shop.data] <<com.shop.data..>>",
                     "[com.shop.gone] <<com.shop.gone..>>")
        self.assertEqual(self.problems(), [
            Problem(Kind.UNDECLARED_PACKAGE, "com.shop.ui", KT_MAIN + "ui/Screen.java"),
            Problem(Kind.ABSENT, "com.shop.gone", "docs/architecture.puml"),
            Problem(Kind.STALE_STEREOTYPE, "com.shop", "docs/architecture.puml")])

    def test_file_without_package_and_package_outside_the_root_are_reported(self):
        self.diagram("[com.shop] <<com.shop>>")
        self.write(KT_MAIN + "Main.kt", "package com.shop\n")
        self.write(KT_MAIN + "Tools.kt", "// package com.shop.fake\nfun main() {}\n")
        self.write(KT_MAIN + "other/Thing.kt", "package org.other\n")
        self.assertEqual(self.problems(), [Problem(Kind.NO_PACKAGE_LINE, "", KT_MAIN + "Tools.kt"),
                                           Problem(Kind.OUTSIDE_ROOT_PACKAGE, "org.other", KT_MAIN + "other/Thing.kt")])

    def test_only_the_sources_folders_are_scanned(self):
        self.diagram("[com.shop] <<com.shop>>")
        self.write(KT_MAIN + "Main.kt", "package com.shop\n")
        self.write("app/src/test/java/com/shop/MainTest.kt", "package com.shop.tests\n")
        self.write("app/src/main/build/Gen.kt", "package com.shop.generated\n")
        self.write("app/src/main/.hidden/Gen.kt", "package com.shop.hidden\n")
        self.write("app/build/tmp/Gen.kt", "package com.shop.build\n")
        self.write("buildSrc/src/main/kotlin/Plugin.kt", "package plugins\n")
        self.assertEqual(self.problems(), [])

    def test_missing_sources_line_is_reported(self):
        self.diagram("[com.shop] <<com.shop>>", header="' stack: kotlin\n' root: com.shop\n")
        self.assertEqual(self.problems(), [Problem(Kind.NO_SOURCES, "", "docs/architecture.puml")])

    def test_write_rewrites_the_components_and_keeps_the_other_lines(self):
        self.code()
        self.diagram("skinparam componentStyle rectangle", "[com.shop.gone] <<com.shop.gone..>>",
                     "[com.shop.ui] --> [com.shop.data]", "[com.shop.ui] --> [com.shop.gone]")
        result = subprocess.run([sys.executable, str(SCRIPT), "--write", str(self.repo)], capture_output=True,
                                text=True)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual((self.repo / "docs/architecture.puml").read_text(encoding="utf-8"), KT_HEADER + "@startuml\n"
                         "[com.shop] <<com.shop>>\n[com.shop.data] <<com.shop.data..>>\n[com.shop.ui] <<com.shop.ui..>>\n"
                         "skinparam componentStyle rectangle\n[com.shop.ui] --> [com.shop.data]\n@enduml\n")

    def test_command_names_each_problem(self):
        self.diagram()
        self.write(KT_MAIN + "ui/Screen.kt", "package com.shop.ui\n")
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.repo)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{KT_MAIN}ui/Screen.kt: com.shop.ui: package not declared in docs/architecture.puml",
                      result.stdout)


PY_HEADER ="; stack: python\n; Components of Shop.\n"
# The cycle of PythonTest.shop: shop -> shop.billing -> shop.util -> shop.orders -> shop.
PY_CYCLE = "; allowed cycle: shop shop.billing shop.util shop.orders\n"
HAS_IMPORT_LINTER = importlib.util.find_spec("importlinter") is not None


class FakeGraph:
    """The part of grimp's ImportGraph that AllowedContract reads, from (importer, imported, line) triples."""

    def __init__(self, *imports, squashed=()):
        self.imports = imports
        self.modules = {m for i in imports for m in i[:2]}
        self.squashed = set(squashed)

    def is_module_squashed(self, module):
        return module in self.squashed

    def find_descendants(self, module):
        return {m for m in self.modules if m.startswith(module + ".")}

    def find_modules_directly_imported_by(self, module):
        return {imported for importer, imported, _ in self.imports if importer == module}

    def get_import_details(self, importer, imported):
        return [{"line_number": line} for i, m, line in self.imports if (i, m) == (importer, imported)]


class PythonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)

    def write(self, path, text=""):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def contracts(self, *components, root="shop"):
        text = PY_HEADER + f"[importlinter]\nroot_package = {root}\n"
        for c in components:
            text += f"\n[importlinter:contract:{c}]\nname = {c}\ntype = allowed\ncomponent = {c}\n"
        self.write(".importlinter", text)

    def shop(self, base="src/"):
        """A package with its __init__, a sub-package (orders, with a sub-module) and a module (util) as components."""
        self.write(f"{base}shop/__init__.py", "from .billing import invoice\nVERSION = 1\n")
        self.write(f"{base}shop/orders/__init__.py", "from . import lines\nfrom shop import VERSION\n")
        self.write(f"{base}shop/orders/lines.py", "def total():\n    from ..billing import invoice\n")
        self.write(f"{base}shop/billing/__init__.py")
        self.write(f"{base}shop/billing/invoice.py", "from shop import util\n")
        self.write(f"{base}shop/util.py", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
                                          "    import shop.orders.lines\nimport json\nimport shop\n")
        self.write(f"{base}shop/__pycache__/x.py")

    def test_stack_comes_from_the_header_of_importlinter(self):
        self.contracts()
        self.assertEqual(architecture.stack(self.repo), "python")

    def test_declared_children_pass_in_src_and_flat_layouts(self):
        for base in ("src/", ""):
            with self.subTest(base=base):
                self.setUp()
                self.shop(base)
                self.contracts("shop", "shop.orders", "shop.billing", "shop.util")
                self.assertEqual(architecture.problems(self.repo), [])

    def test_new_child_is_undeclared(self):
        self.shop()
        self.write("src/shop/new.py")
        self.write("src/shop/stock/__init__.py")
        self.write("src/shop/notes/readme.txt")
        self.contracts("shop", "shop.orders", "shop.billing", "shop.util")
        self.assertEqual(architecture.problems(self.repo),
                         [Problem(Kind.UNDECLARED_MODULE, "shop.new", "src/shop/new.py"),
                          Problem(Kind.UNDECLARED_MODULE, "shop.stock", "src/shop/stock")])

    def test_folder_with_code_but_no_init_is_reported(self):
        # grimp, so import-linter, skips such a folder and everything under it: its code is not checked.
        self.shop()
        self.write("src/shop/tools/cli.py", "import shop.orders\n")
        self.write("src/shop/jobs/nightly/run.py")
        self.write("src/shop/jobs/nightly/sub/__init__.py")
        self.write("src/shop/billing/rates/vat.py")
        self.write("src/shop/notes/readme.txt")
        self.contracts("shop", "shop.orders", "shop.billing", "shop.util")
        self.assertEqual(architecture.problems(self.repo),
                         [Problem(Kind.NO_INIT, "shop.billing.rates", "src/shop/billing/rates"),
                          Problem(Kind.NO_INIT, "shop.jobs", "src/shop/jobs"),
                          Problem(Kind.NO_INIT, "shop.tools", "src/shop/tools")])

    def test_undeclared_root_init_is_undeclared(self):
        self.shop()
        self.contracts("shop.orders", "shop.billing", "shop.util")
        self.assertEqual(architecture.problems(self.repo),
                         [Problem(Kind.UNDECLARED_MODULE, "shop", "src/shop/__init__.py")])

    def test_component_without_code_is_absent(self):
        self.shop()
        self.contracts("shop", "shop.orders", "shop.billing", "shop.util", "shop.stock")
        self.assertEqual(architecture.problems(self.repo), [Problem(Kind.ABSENT, "shop.stock", ".importlinter")])

    def test_missing_root_package_is_reported(self):
        self.contracts(root="shop")
        self.assertEqual(architecture.problems(self.repo), [Problem(Kind.NO_PACKAGE, "shop", ".importlinter")])
        self.write(".importlinter", PY_HEADER + "[importlinter]\n")
        self.assertEqual(architecture.problems(self.repo), [Problem(Kind.NO_ROOT_PACKAGE, "", ".importlinter")])

    def test_write_lists_the_imports_found_today_and_keeps_the_header(self):
        self.shop()
        self.write(".importlinter", PY_HEADER + PY_CYCLE + "[importlinter]\nroot_package = shop\n")
        self.assertEqual(architecture.write_contracts(self.repo), [])
        self.assertEqual((self.repo / ".importlinter").read_text(encoding="utf-8"), PY_HEADER + PY_CYCLE + (
            "[importlinter]\nroot_package = shop\ncontract_types =\n    allowed: architecture.AllowedContract\n"
            "\n[importlinter:contract:__init__]\nname = shop\ntype = allowed\ncomponent = shop\n"
            "allowed =\n    shop.billing\n"
            "\n[importlinter:contract:billing]\nname = shop.billing\ntype = allowed\ncomponent = shop.billing\n"
            "allowed =\n    shop.util\n"
            "\n[importlinter:contract:orders]\nname = shop.orders\ntype = allowed\ncomponent = shop.orders\n"
            "allowed =\n    shop\n    shop.billing\n"
            "\n[importlinter:contract:util]\nname = shop.util\ntype = allowed\ncomponent = shop.util\n"
            "allowed =\n    shop\n    shop.orders\n"))
        self.assertEqual(architecture.problems(self.repo), [])

    def test_write_keeps_the_other_options_and_the_contracts_of_other_types(self):
        self.shop()
        layers = "[importlinter:contract:layers]\nname = Layers\ntype = layers\nlayers =\n    shop.orders\n    shop.util\n"
        self.write(".importlinter", PY_HEADER + PY_CYCLE + (
            "[importlinter]\nroot_package = shop\ninclude_external_packages = True\n"
            "contract_types =\n    allowed: architecture.AllowedContract\n    mine: shop.contracts.Mine\n"
            "\n[importlinter:contract:util]\nname = old\ntype = allowed\ncomponent = shop.util\n"
            "\n" + layers))
        self.assertEqual(architecture.write_contracts(self.repo), [])
        text = (self.repo / ".importlinter").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(PY_HEADER + PY_CYCLE + (
            "[importlinter]\nroot_package = shop\ncontract_types =\n    allowed: architecture.AllowedContract\n"
            "    mine: shop.contracts.Mine\ninclude_external_packages = True\n\n" + layers
            + "\n[importlinter:contract:__init__]\n")), text)
        self.assertEqual(text.count("[importlinter:contract:util]"), 1)
        self.assertNotIn("name = old", text)
        self.assertEqual(architecture.problems(self.repo), [])

    def test_import_of_a_component_not_allowed_is_illegal(self):
        graph = FakeGraph(("shop.orders.lines", "shop.billing.invoice", 2), ("shop.orders", "shop.util", 5),
                          ("shop.orders", "shop.orders.lines", 1), ("shop.orders", "shop", 3),
                          ("shop.orders", "json", 4), squashed=("json",))
        self.assertEqual(architecture.illegal_imports(graph, "shop.orders", {"shop.billing"}),
                         [("shop.orders", "shop", (3,)), ("shop.orders", "shop.util", (5,))])
        self.assertEqual(architecture.illegal_imports(graph, "shop.orders", {"shop", "shop.billing", "shop.util"}), [])

    def test_import_from_the_root_init_not_allowed_is_illegal(self):
        graph = FakeGraph(("shop", "shop.billing.invoice", 1), ("shop", "shop.orders", 2),
                          ("shop.orders", "shop.util", 5), ("shop", "json", 3), squashed=("json",))
        self.assertEqual(architecture.illegal_imports(graph, "shop", {"shop.billing"}), [("shop", "shop.orders", (2,))])
        self.assertEqual(architecture.illegal_imports(graph, "shop", {"shop.billing", "shop.orders"}), [])

    def lib(self, base="src/"):
        """A second root package: its __init__ and a module (db); shop.orders imports lib.db."""
        self.write(f"{base}lib/__init__.py")
        self.write(f"{base}lib/db.py", "import json\n")
        self.write("src/shop/orders/lines.py", "def total():\n    from ..billing import invoice\nimport lib.db\n")

    def two_roots(self, *components):
        text = PY_HEADER + "[importlinter]\nroot_packages =\n    shop\n    lib\n"
        for c in components:
            text += f"\n[importlinter:contract:{c}]\nname = {c}\ntype = allowed\ncomponent = {c}\n"
        self.write(".importlinter", text)

    def test_children_of_every_root_package_are_declared(self):
        self.shop()
        self.lib(base="")
        self.write("lib/new.py")
        self.write("lib/jobs/run.py")
        self.two_roots("shop", "shop.orders", "shop.billing", "shop.util", "lib", "lib.db", "lib.gone")
        self.assertEqual(architecture.problems(self.repo),
                         [Problem(Kind.UNDECLARED_MODULE, "lib.new", "lib/new.py"),
                          Problem(Kind.NO_INIT, "lib.jobs", "lib/jobs"),
                          Problem(Kind.ABSENT, "lib.gone", ".importlinter")])

    def test_missing_one_of_the_root_packages_is_reported(self):
        self.shop()
        self.two_roots("shop", "shop.orders", "shop.billing", "shop.util")
        self.assertEqual(architecture.problems(self.repo), [Problem(Kind.NO_PACKAGE, "lib", ".importlinter")])

    def test_write_with_several_root_packages_names_sections_after_the_component(self):
        self.shop()
        self.lib()
        self.write(".importlinter", PY_HEADER + PY_CYCLE + "[importlinter]\nroot_packages =\n    shop\n    lib\n")
        self.assertEqual(architecture.write_contracts(self.repo), [])
        text = (self.repo / ".importlinter").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(PY_HEADER + PY_CYCLE + (
            "[importlinter]\nroot_packages =\n    shop\n    lib\ncontract_types =\n"
            "    allowed: architecture.AllowedContract\n"
            "\n[importlinter:contract:shop]\nname = shop\n")), text)
        self.assertTrue(text.endswith(
            "\n[importlinter:contract:lib]\nname = lib\ntype = allowed\ncomponent = lib\n"
            "\n[importlinter:contract:lib.db]\nname = lib.db\ntype = allowed\ncomponent = lib.db\n"), text)
        self.assertIn("\n[importlinter:contract:shop.orders]\nname = shop.orders\ntype = allowed\n"
                      "component = shop.orders\nallowed =\n    lib.db\n    shop\n    shop.billing\n", text)
        self.assertNotIn("root_package =", text)
        self.assertEqual(architecture.problems(self.repo), [])

    def test_import_of_another_root_package_not_allowed_is_illegal(self):
        graph = FakeGraph(("shop.orders.lines", "lib.db", 3), ("shop.orders", "lib", 4), ("shop.orders", "django", 5),
                          ("lib.db", "shop.util", 1), squashed=("django",))
        self.assertEqual(architecture.illegal_imports(graph, "shop.orders", {"lib"}),
                         [("shop.orders.lines", "lib.db", (3,))])
        self.assertEqual(architecture.illegal_imports(graph, "shop.orders", {"lib", "lib.db"}), [])

    @unittest.skipUnless(HAS_IMPORT_LINTER, "import-linter not installed")
    def test_command_with_several_root_packages_fails_on_an_import_between_them(self):
        self.shop()
        self.lib(base="")
        self.write(".importlinter", PY_HEADER + PY_CYCLE + "[importlinter]\nroot_packages =\n    shop\n    lib\n")
        self.write(".github/scripts/architecture.py", SCRIPT.read_text(encoding="utf-8"))
        command = [sys.executable, ".github/scripts/architecture.py"]
        run = lambda *args: subprocess.run(command + list(args), cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(run("--write").returncode, 0)
        self.assertEqual(run().returncode, 0, run().stdout)
        self.write("lib/db.py", "import shop.util\n")
        result = run()
        self.assertEqual(result.returncode, 1)
        self.assertIn("- lib.db -> shop.util (l.1)", result.stdout)

    @unittest.skipUnless(HAS_IMPORT_LINTER, "import-linter not installed")
    def test_command_writes_then_passes_then_fails_with_the_import_chain(self):
        self.shop()
        self.write(".importlinter", PY_HEADER + PY_CYCLE + "[importlinter]\nroot_package = shop\n")
        self.write(".github/scripts/architecture.py", SCRIPT.read_text(encoding="utf-8"))
        command = [sys.executable, ".github/scripts/architecture.py"]
        run = lambda *args: subprocess.run(command + list(args), cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(run("--write").returncode, 0)
        self.assertEqual(run().returncode, 0, run().stdout)
        self.write("src/shop/billing/tax.py", "import shop.orders\n")
        self.write("src/shop/__init__.py", "from shop import util\n")
        self.write("src/shop/new.py")
        self.write("src/shop/tools/cli.py", "import shop.orders\n")
        result = run()
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/shop/new.py: shop.new: component not declared in .importlinter", result.stdout)
        self.assertIn("- shop.billing.tax -> shop.orders (l.1)", result.stdout)
        self.assertIn("- shop -> shop.util (l.1)", result.stdout)
        self.assertIn("src/shop/tools: shop.tools: folder without __init__.py", result.stdout)

    @unittest.skipIf(HAS_IMPORT_LINTER, "import-linter installed")
    def test_command_without_import_linter_fails(self):
        self.shop()
        self.contracts("shop", "shop.orders", "shop.billing", "shop.util")
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.repo)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("import-linter is not installed", result.stdout)


RS_HEADER = "' stack: rust\n' exclude: xtask\n"
HAS_CARGO = shutil.which("cargo") is not None
NORMAL, BUILD, DEV = None, "build", "dev"


class RustTest(unittest.TestCase):
    """A workspace: domain (restricted: glam only), app (domain, eframe), xtask (excluded)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.crates = {"domain": [("glam", NORMAL), ("proptest", DEV)],
                       "app": [("domain", NORMAL), ("eframe", NORMAL), ("cc", BUILD), ("domain-tests", DEV)],
                       "xtask": [("app", NORMAL), ("clap", NORMAL)]}

    def metadata(self):
        """The fields of `cargo metadata --no-deps --format-version 1` the check reads."""
        root = self.repo / "ws"
        packages = [{"name": name, "id": f"path+file:///{(root / 'crates' / name).as_posix()}#0.1.0",
                     "manifest_path": str(root / "crates" / name / "Cargo.toml"),
                     "dependencies": [{"name": dep, "kind": kind, "rename": None, "target": None}
                                      for dep, kind in deps]}
                    for name, deps in self.crates.items()]
        return {"packages": packages, "workspace_members": [p["id"] for p in packages], "workspace_root": str(root)}

    def diagram(self, *lines, header=RS_HEADER):
        file = self.repo / "ws" / "docs" / "architecture.puml"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(header + "@startuml\n" + "".join(l + "\n" for l in lines) + "@enduml\n", encoding="utf-8")

    def problems(self):
        return architecture.rust_problems(self.repo / "ws", self.metadata())

    def allowed(self, *extra):
        self.diagram("[domain] <<restricted>>", "[app]", "[glam] <<external>>",
                     "[app] --> [domain]", "[domain] --> [glam]", *extra)

    def test_stack_comes_from_the_header_of_the_diagram(self):
        self.allowed()
        self.assertEqual(architecture.stack(self.repo / "ws"), "rust")

    def test_drawn_workspace_passes(self):
        self.allowed()
        self.assertEqual(self.problems(), [])

    def test_undrawn_dependency_between_crates_fails(self):
        self.crates["domain"].append(("app", NORMAL))
        self.allowed()
        self.assertEqual(self.problems(),
                         [Problem(Kind.UNDRAWN_DEPENDENCY, "domain -> app", "crates/domain/Cargo.toml")])

    def test_build_dependency_counts_and_dev_dependency_does_not(self):
        self.crates["domain"] += [("app", BUILD), ("app", DEV)]
        self.allowed()
        self.assertEqual(self.problems(),
                         [Problem(Kind.UNDRAWN_DEPENDENCY, "domain -> app", "crates/domain/Cargo.toml")])

    def test_arrow_drawn_but_unused_passes(self):
        self.allowed("[app] ..> [glam]")
        self.assertEqual(self.problems(), [])

    def test_undeclared_crate_and_component_without_crate_fail(self):
        self.crates["stock"] = []
        self.allowed("[billing]")
        self.assertEqual(self.problems(), [Problem(Kind.UNDECLARED_CRATE, "stock", "crates/stock/Cargo.toml"),
                                           Problem(Kind.ABSENT, "billing", "docs/architecture.puml")])

    def test_external_of_a_restricted_crate_must_be_drawn(self):
        self.crates["domain"] += [("winit", NORMAL), ("cc", BUILD)]
        self.crates["app"].append(("winit", NORMAL))
        self.allowed()
        self.assertEqual(self.problems(), [
            Problem(Kind.UNDRAWN_EXTERNAL, "domain -> winit", "crates/domain/Cargo.toml"),
            Problem(Kind.UNDRAWN_EXTERNAL, "domain -> cc", "crates/domain/Cargo.toml")])

    def test_arrow_to_or_from_an_undeclared_component_fails(self):
        self.allowed("[app] -up-> [domian]", "[serde] --> [glam]")
        self.assertEqual(self.problems(), [Problem(Kind.UNKNOWN_ARROW, "app -> domian", "docs/architecture.puml"),
                                           Problem(Kind.UNKNOWN_ARROW, "serde -> glam", "docs/architecture.puml")])

    def test_missing_diagram_is_reported(self):
        self.assertEqual(self.problems(), [Problem(Kind.NO_DIAGRAM, "", "docs/architecture.puml")])

    def test_write_draws_the_crates_arrows_and_externals_of_restricted_crates(self):
        self.diagram("skinparam componentStyle rectangle", "[domain] <<restricted>>", "[old]", "[old] --> [domain]")
        self.assertEqual(architecture.write_diagram(self.repo / "ws", self.metadata()), [])
        self.assertEqual((self.repo / "ws" / "docs" / "architecture.puml").read_text(encoding="utf-8"), RS_HEADER + (
            "@startuml\nskinparam componentStyle rectangle\n"
            "[app]\n[domain] <<restricted>>\n[glam] <<external>>\n"
            "[app] --> [domain]\n[domain] --> [glam]\n@enduml\n"))
        self.assertEqual(self.problems(), [])

    def test_cargo_failure_is_reported_with_its_message(self):
        self.allowed()
        found = architecture.rust_problems(self.repo / "ws", architecture.ToolFailure("error: no Cargo.toml"))
        self.assertEqual(found, [Problem(Kind.CARGO_FAILED, "error: no Cargo.toml", "")])

    @unittest.skipUnless(HAS_CARGO, "cargo not installed")
    def test_command_writes_then_passes_then_fails_on_a_new_dependency(self):
        def crate(name, deps=""):
            (self.repo / name / "src").mkdir(parents=True)
            (self.repo / name / "src" / "lib.rs").write_text("", encoding="utf-8")
            (self.repo / name / "Cargo.toml").write_text(
                f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n[dependencies]\n{deps}',
                encoding="utf-8")
        (self.repo / "Cargo.toml").write_text('[workspace]\nresolver = "2"\nmembers = ["domain", "app"]\n',
                                              encoding="utf-8")
        crate("domain")
        crate("app", 'domain = { path = "../domain" }\n')
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "architecture.puml").write_text(RS_HEADER, encoding="utf-8")
        run = lambda *args: subprocess.run([sys.executable, str(SCRIPT), *args, str(self.repo)],
                                           capture_output=True, text=True)
        self.assertEqual(run("--write").returncode, 0, run("--write").stdout)
        self.assertEqual(run().returncode, 0, run().stdout)
        (self.repo / "domain" / "Cargo.toml").write_text(
            (self.repo / "domain" / "Cargo.toml").read_text(encoding="utf-8") + 'app = { path = "../app" }\n',
            encoding="utf-8")
        result = run()
        self.assertEqual(result.returncode, 1)
        self.assertIn("domain/Cargo.toml: domain -> app: dependency not drawn in docs/architecture.puml",
                      result.stdout)


class JsTest(unittest.TestCase):
    """src/index.ts (component src), src/hooks/useTimer.ts imports src/lib/clock.ts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.imports = [("src/index.ts", "src/hooks/useTimer.ts"), ("src/hooks/useTimer.ts", "src/lib/clock.ts"),
                        ("src/hooks/useTimer.ts", "node_modules/react/index.js"), ("src/lib/clock.ts", "fs")]
        for path in ("src/index.ts", "src/hooks/useTimer.ts", "src/lib/clock.ts"):
            self.write(path, "")

    def write(self, path, text):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def declare(self, components=None, roots=("src",), exclude=()):
        components = components if components is not None else {
            "src": ["src/hooks"], "src/hooks": ["src/lib"], "src/lib": []}
        self.write("docs/architecture.json", json.dumps({"stack": "js", "comment": "Components of Shop.",
                                                         "roots": list(roots), "exclude": list(exclude),
                                                         "components": components}, indent=2))

    def cruise(self, unread=()):
        """What dependency-cruiser would return: every file on disk read, but `unread`, and self.imports."""
        read = {p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*") if p.is_file()} - set(unread)
        return architecture.Cruise(frozenset(read), tuple(self.imports))

    def problems(self):
        return architecture.js_problems(self.repo, self.cruise())

    def test_stack_comes_from_the_stack_key(self):
        self.declare()
        self.assertEqual(architecture.stack(self.repo), "js")

    def test_declared_components_pass(self):
        self.declare()
        self.assertEqual(self.problems(), [])

    def test_new_folder_is_undeclared(self):
        self.declare()
        self.write("src/new/feature.tsx", "")
        self.assertEqual(self.problems(), [Problem(Kind.UNDECLARED_FOLDER, "src/new", "src/new/feature.tsx")])

    def test_component_without_code_is_absent(self):
        self.declare({"src": ["src/hooks"], "src/hooks": ["src/lib"], "src/lib": [], "src/old": []})
        self.assertEqual(self.problems(), [Problem(Kind.ABSENT, "src/old", "docs/architecture.json")])

    def test_import_not_allowed_names_the_importing_file(self):
        self.declare()
        self.imports.append(("src/lib/clock.ts", "src/hooks/useTimer.ts"))
        self.assertEqual(self.problems(), [Problem(Kind.IMPORT_NOT_ALLOWED, "src/lib -> src/hooks (src/hooks/useTimer.ts)",
                                                   "src/lib/clock.ts")])

    def test_allowed_component_must_be_declared(self):
        self.declare({"src": ["src/hooks"], "src/hooks": ["src/lib", "src/libs"], "src/lib": []})
        self.assertEqual(self.problems(), [Problem(Kind.UNKNOWN_ALLOWED, "src/hooks -> src/libs", "docs/architecture.json")])

    def test_tests_node_modules_hidden_excluded_and_other_files_are_not_components(self):
        self.declare(exclude=["src/legacy/"])
        for path in ("src/__tests__/timer.ts", "src/test/helpers.js", "src/hooks/useTimer.test.tsx",
                     "src/lib/clock.spec.mjs", "src/node_modules/pkg/index.js", "src/.cache/a.js",
                     "src/legacy/old.js", "src/locales/fr.json"):
            self.write(path, "")
        self.imports += [("src/__tests__/timer.ts", "src/lib/clock.ts"), ("src/legacy/old.js", "src/hooks/useTimer.ts"),
                         ("src/lib/clock.ts", "src/legacy/old.js")]
        self.assertEqual(self.problems(), [])

    def test_repository_root_holds_the_top_folders_and_its_own_files(self):
        self.write("options/options.js", "")
        self.write("test/parser.test.js", "")
        self.write("babel.config.js", "")
        self.write(".dependency-cruiser.cjs", "")
        self.declare({".": [], "options": [], "src": []}, roots=["."])
        self.imports = [("options/options.js", "src/lib/clock.ts")]
        self.assertEqual(self.problems(), [Problem(Kind.IMPORT_NOT_ALLOWED, "options -> src (src/lib/clock.ts)",
                                                   "options/options.js")])

    def test_missing_unreadable_or_rootless_file_is_reported(self):
        self.assertEqual(self.problems(), [Problem(Kind.NO_DIAGRAM, "", "docs/architecture.json")])
        self.declare(roots=())
        self.assertEqual(self.problems(), [Problem(Kind.NO_ROOTS, "", "docs/architecture.json")])
        self.write("docs/architecture.json", '{"stack": "js", "roots": ["src"],')
        self.assertEqual([p.kind for p in self.problems()], [Kind.INVALID_FILE])

    def test_write_lists_the_imports_found_today_and_keeps_the_other_keys(self):
        self.declare({"src/old": ["src"]}, exclude=["src/legacy/"])
        self.assertEqual(architecture.write_js(self.repo, self.cruise()), [])
        content = json.loads((self.repo / "docs" / "architecture.json").read_text(encoding="utf-8"))
        self.assertEqual(content, {"stack": "js", "comment": "Components of Shop.", "roots": ["src"],
                                   "exclude": ["src/legacy/"],
                                   "components": {"src": ["src/hooks"], "src/hooks": ["src/lib"], "src/lib": []}})
        self.assertEqual(self.problems(), [])

    def test_source_not_read_by_dependency_cruiser_fails_and_is_not_written(self):
        self.declare()
        self.write("src/hooks/useClock.ts", "")
        cruise = self.cruise(unread=("src/hooks/useTimer.ts", "src/hooks/useClock.ts", "src/lib/clock.ts"))
        expected = [Problem(Kind.NOT_READ, "", "src/hooks/useClock.ts"), Problem(Kind.NOT_READ, "", "src/lib/clock.ts")]
        self.assertEqual(architecture.js_problems(self.repo, cruise), expected)
        before = (self.repo / "docs" / "architecture.json").read_text(encoding="utf-8")
        self.assertEqual(architecture.write_js(self.repo, cruise), expected)
        self.assertEqual((self.repo / "docs" / "architecture.json").read_text(encoding="utf-8"), before)

    def test_dependency_cruiser_failure_is_reported_with_its_message(self):
        self.declare()
        self.write("src/new/feature.ts", "")
        found = architecture.js_problems(self.repo, architecture.ToolFailure("npx canceled due to missing packages"))
        self.assertEqual(found, [Problem(Kind.UNDECLARED_FOLDER, "src/new", "src/new/feature.ts"),
                                 Problem(Kind.DEPCRUISE_FAILED, "npx canceled due to missing packages", "")])
        self.assertEqual(architecture.write_js(self.repo, architecture.ToolFailure("")), [Problem(Kind.NO_DEPCRUISE, "", "")])

    @unittest.skipUnless(shutil.which("depcruise"), "dependency-cruiser not installed")
    def test_command_writes_then_passes_then_fails_on_a_new_import(self):
        # JavaScript: dependency-cruiser needs the project's typescript package to read .ts files.
        for path in ("src/index.ts", "src/hooks/useTimer.ts", "src/lib/clock.ts"):
            (self.repo / path).unlink()
        self.write("src/hooks/useTimer.js", "import { now } from '../lib/clock.js';\nexport const t = now;\n")
        self.write("src/lib/clock.js", "export const now = 1;\n")
        self.write("src/index.js", "import { t } from './hooks/useTimer.js';\n")
        self.write("src/__tests__/clock.test.js", "import { t } from '../hooks/useTimer.js';\n")
        shutil.copy(SCRIPT.parents[1] / "dependency-cruiser.cjs", self.repo / ".dependency-cruiser.cjs")
        self.declare({})
        run = lambda *args: subprocess.run([sys.executable, str(SCRIPT), *args, str(self.repo)],
                                           capture_output=True, text=True, cwd=self.repo)
        result = run("--write")
        self.assertEqual(result.returncode, 0, result.stdout)
        content = json.loads((self.repo / "docs" / "architecture.json").read_text(encoding="utf-8"))
        self.assertEqual(content["components"], {"src": ["src/hooks"], "src/hooks": ["src/lib"], "src/lib": []})
        result = run()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.write("src/lib/clock.js", "import { t } from '../hooks/useTimer.js';\nexport const now = 1;\n")
        result = run()
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/lib/clock.js: src/lib -> src/hooks (src/hooks/useTimer.js): import not allowed in "
                      "docs/architecture.json", result.stdout)


class CycleTest(unittest.TestCase):
    """The allowed dependencies between components must not form a cycle not admitted, in every stack."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)

    def write(self, path, text):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def test_cycle_is_shown_as_a_path_through_all_its_components(self):
        edges = {"a": {"b", "d"}, "b": {"c"}, "c": {"a", "b"}, "d": {"a"}, "e": {"a"}}
        self.assertEqual(architecture.cycle_problems(edges, [], "f"),
                         [Problem(Kind.CYCLE, "a -> b -> c -> a -> d -> a", "f")])

    def test_admitted_cycle_passes_only_with_exactly_its_components(self):
        edges = {"a": {"b"}, "b": {"a"}, "c": {"d"}, "d": {"c"}}
        self.assertEqual(architecture.cycle_problems(edges, [("b", "a"), ("d", "c")], "f"), [])
        edges["b"].add("c")
        edges["d"].add("a")
        self.assertEqual(architecture.cycle_problems(edges, [("b", "a"), ("d", "c")], "f"),
                         [Problem(Kind.CYCLE, "a -> b -> c -> d -> a", "f"),
                          Problem(Kind.STALE_CYCLE, "a b", "f"), Problem(Kind.STALE_CYCLE, "c d", "f")])

    def test_dotnet_and_kotlin_diagram_arrows(self):
        cases = {"Shop": ("", "Shop.", "src/{}.cs", "namespace Shop.{};\n", architecture.stereotype),
                 "com.shop": (KT_HEADER, "com.shop.", "app/src/main/{}.kt", "package com.shop.{}\n",
                              architecture.kotlin_stereotype)}
        for root, (header, prefix, path, code, stereotype) in cases.items():
            with self.subTest(root=root):
                self.setUp()
                a, b = prefix + "Orders", prefix + "Billing"
                for name in ("Orders", "Billing"):
                    self.write(path.format(name), code.format(name))
                body = "".join(f"[{c}] <<{stereotype(c, root, (a, b))}>>\n" for c in (a, b))
                diagram = f"' root: {root}\n@startuml\n{body}[{a}] --> [{b}]\n[{b}] -up-> [{a}]\n@enduml\n"
                self.write("docs/architecture.puml", header + diagram)
                self.assertEqual(architecture.problems(self.repo),
                                 [Problem(Kind.CYCLE, f"{b} -> {a} -> {b}", "docs/architecture.puml")])
                self.write("docs/architecture.puml", header + f"' allowed cycle: {a} {b}\n" + diagram)
                self.assertEqual(architecture.problems(self.repo), [])

    def test_python_allowed_contracts(self):
        for name in ("orders", "billing"):
            self.write(f"shop/{name}.py", "")
        self.write("shop/__init__.py", "")
        contracts = ("[importlinter]\nroot_package = shop\n"
                     "[importlinter:contract:__init__]\nname = shop\ntype = allowed\ncomponent = shop\n"
                     "[importlinter:contract:orders]\nname = o\ntype = allowed\ncomponent = shop.orders\n"
                     "allowed =\n    shop.billing\n    shop.orders\n"
                     "[importlinter:contract:billing]\nname = b\ntype = allowed\ncomponent = shop.billing\n"
                     "allowed = shop.orders\n")
        self.write(".importlinter", PY_HEADER + contracts)
        self.assertEqual(architecture.problems(self.repo),
                         [Problem(Kind.CYCLE, "shop.billing -> shop.orders -> shop.billing", ".importlinter")])
        self.write(".importlinter", PY_HEADER + "# allowed cycle: shop.orders shop.billing\n" + contracts)
        self.assertEqual(architecture.problems(self.repo), [])

    def test_rust_diagram_arrows(self):
        metadata = {"workspace_root": str(self.repo), "packages": [
            {"name": name, "id": name, "manifest_path": str(self.repo / name / "Cargo.toml"), "dependencies": []}
            for name in ("app", "domain")], "workspace_members": ["app", "domain"]}
        diagram = "@startuml\n[app]\n[domain]\n[app] --> [domain]\n[domain] ..> [app]\n@enduml\n"
        self.write("docs/architecture.puml", RS_HEADER + diagram)
        self.assertEqual(architecture.rust_problems(self.repo, metadata),
                         [Problem(Kind.CYCLE, "app -> domain -> app", "docs/architecture.puml")])
        self.write("docs/architecture.puml", RS_HEADER + "' allowed cycle: app domain\n' allowed cycle: x y\n"
                   + diagram)
        self.assertEqual(architecture.rust_problems(self.repo, metadata),
                         [Problem(Kind.STALE_CYCLE, "x y", "docs/architecture.puml")])

    def test_js_components(self):
        self.write("src/a/x.ts", "")
        self.write("src/b/y.ts", "")
        content = {"stack": "js", "roots": ["src"], "components": {"src/a": ["src/b"], "src/b": ["src/a"]}}
        cruise = architecture.Cruise(frozenset({"src/a/x.ts", "src/b/y.ts"}), ())
        self.write("docs/architecture.json", json.dumps(content))
        self.assertEqual(architecture.js_problems(self.repo, cruise),
                         [Problem(Kind.CYCLE, "src/a -> src/b -> src/a", "docs/architecture.json")])
        self.write("docs/architecture.json", json.dumps({**content, "allowed_cycles": [["src/b", "src/a"]]}))
        self.assertEqual(architecture.js_problems(self.repo, cruise), [])
        self.write("docs/architecture.json", json.dumps({**content, "allowed_cycles": ["src/b src/a"]}))
        self.assertEqual([p.kind for p in architecture.js_problems(self.repo, cruise)], [Kind.INVALID_FILE])


if __name__ == "__main__":
    unittest.main()
