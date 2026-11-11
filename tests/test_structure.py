"""Tests of the structural change detection (plugins/core/templates/github-scripts/structure.py)."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "core" / "templates" / "github-scripts"))
import structure  # noqa: E402
from structure import Kind, Signal  # noqa: E402


def signals(*changes, base=(), head=(), config=None):
    return structure.signals(list(changes), set(base), set(head), config or {})


class SignalsTest(unittest.TestCase):
    def test_source_and_doc_changes_are_not_structural(self):
        self.assertEqual(signals(("M", "src/app.py"), ("A", "docs/guide.md"), ("D", "src/old.py"),
                                 ("M", "package-lock.json"), ("M", "poetry.lock"), base=("src",), head=("src",)), [])

    def test_architecture_files(self):
        for path in ("docs/architecture.puml", "docs/architecture.md", "tests/ArchitectureTest.cs",
                     ".importlinter", "web/.dependency-cruiser.js", ".github/scripts/architecture.py"):
            with self.subTest(path=path):
                self.assertEqual(signals(("M", path)), [Signal(Kind.ARCHITECTURE_FILE, path)])

    def test_manifests_by_status(self):
        for status, kind in (("A", Kind.MANIFEST_ADDED), ("D", Kind.MANIFEST_REMOVED), ("M", Kind.MANIFEST_CHANGED),
                             ("T", Kind.MANIFEST_CHANGED)):
            with self.subTest(status=status):
                self.assertEqual(signals((status, "tools/Atelier.csproj")), [Signal(kind, "tools/Atelier.csproj")])
        for path in ("Atelier.sln", "web/package.json", "pyproject.toml", "requirements-dev.txt", "Cargo.toml",
                     "go.mod", "project.godot", "kit.gemspec", "Gemfile"):
            with self.subTest(path=path):
                self.assertEqual(signals(("M", path)), [Signal(Kind.MANIFEST_CHANGED, path)])

    def test_config_extends_the_defaults(self):
        config = {"architecture_patterns": [".claude-plugin/marketplace.json"], "manifest_patterns": ["deps.edn"]}
        self.assertEqual(signals(("M", ".claude-plugin/marketplace.json"), ("M", "deps.edn"), ("M", "go.mod"),
                                 config=config),
                         [Signal(Kind.ARCHITECTURE_FILE, ".claude-plugin/marketplace.json"),
                          Signal(Kind.MANIFEST_CHANGED, "deps.edn"), Signal(Kind.MANIFEST_CHANGED, "go.mod")])

    def test_top_level_folders_added_or_removed_hidden_ones_included(self):
        self.assertEqual(signals(base=("src", "old"), head=("src", "server", ".vscode")),
                         [Signal(Kind.FOLDER_ADDED, ".vscode/"), Signal(Kind.FOLDER_ADDED, "server/"),
                          Signal(Kind.FOLDER_REMOVED, "old/")])

    def test_signal_text_for_logs(self):
        self.assertEqual(str(Signal(Kind.FOLDER_ADDED, "server/")), "server/: top-level folder added")


CSPROJ = """<Project Sdk="Godot.NET.Sdk/4.3.0">
  <!-- The game. -->
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <Compile Remove="tools/**" />
    <PackageReference Include="gdUnit4.api" Version="4.3.0" />
    <ProjectReference Include="tools/TestRunTools/TestRunTools.csproj" />
  </ItemGroup>
  <Target Name="Lock" BeforeTargets="VSTest"><Message Text="lock" /></Target>
</Project>
"""
PYPROJECT = """[project]
name = "kit"
dependencies = ["requests>=2", "Rich[jupyter]==13.0"]
[project.optional-dependencies]
docs = ["mkdocs"]
[build-system]
requires = ["setuptools"]
[tool.ruff]
line-length = 120
"""


GODOT = """; Engine configuration file.
config_version=5

[application]

config/name="Atelier"
run/main_scene="res://scenes/garage.tscn"
config/features=PackedStringArray("4.7", "C#", "Forward Plus")

[autoload]

Game="*res://game.gd"

[dotnet]

project/assembly_name="Atelier"

[editor_plugins]

enabled=PackedStringArray("res://addons/gdUnit4/plugin.cfg")

[input]

fire={
"deadzone": 0.2,
"events": [Object(InputEventMouseButton,"button_index":1,"pressed":false)
]
}

[physics]

common/physics_interpolation=true
"""
GODOT_ACTION = 'aim_next={\n"deadzone": 0.2,\n"events": []\n}\n'


def manifest_signals(path, base, head):
    return structure.signals([("M", path)], set(), set(), {}, {path: (base, head)})


class ManifestDependenciesTest(unittest.TestCase):
    def test_changes_outside_the_dependencies_are_not_structural(self):
        for path, base, head in (
                ("Atelier.csproj", CSPROJ, CSPROJ.replace("The game.", "The game, built by Godot.")
                 .replace('Version="4.3.0"', 'Version="4.4.0"').replace('<Message Text="lock" />', "")
                 .replace("<Nullable>enable</Nullable>", "")),
                ("web/package.json", '{"version": "1.0.0", "dependencies": {"react": "^18"}}',
                 '{"version": "1.1.0", "scripts": {"t": "jest"}, "dependencies": {"react": "^19"}}'),
                ("pyproject.toml", PYPROJECT, PYPROJECT.replace("120", "100").replace(">=2", ">=2.31")),
                ("requirements-dev.txt", "# tools\nrequests>=2\n-r requirements.txt\n",
                 "requests==2.31  # pinned\n-r  requirements.txt\n"),
                ("project.godot", GODOT, GODOT.replace("fire={", GODOT_ACTION + "fire={")
                 .replace('"Atelier"\nrun', '"Atelier 2"\nrun').replace("interpolation=true", "interpolation=false")
                 .replace("garage", "menu")
                 + '\n[layer_names]\n\n3d_physics/layer_1="ships"\n')):
            with self.subTest(path=path):
                self.assertEqual(manifest_signals(path, base, head), [])

    def test_dependencies_added_or_removed_are_structural(self):
        for path, base, head, detail in (
                ("Atelier.csproj", CSPROJ, CSPROJ.replace("gdUnit4.api", "Moq"), "+PackageReference Moq, "
                 "-PackageReference gdUnit4.api"),
                ("Atelier.csproj", CSPROJ, CSPROJ.replace("net8.0", "net9.0"),
                 "+TargetFramework net9.0, -TargetFramework net8.0"),
                ("Atelier.csproj", CSPROJ, CSPROJ.replace("4.3.0\">", "4.4.0\">"),
                 "+Sdk Godot.NET.Sdk/4.4.0, -Sdk Godot.NET.Sdk/4.3.0"),
                ("Atelier.csproj", CSPROJ, CSPROJ.replace('    <ProjectReference Include="tools/TestRunTools/'
                                                          'TestRunTools.csproj" />\n', ""),
                 "-ProjectReference tools/TestRunTools/TestRunTools.csproj"),
                ("package.json", '{"dependencies": {"react": "1"}}',
                 '{"dependencies": {"react": "1"}, "devDependencies": {"jest": "1"}, "workspaces": ["app"]}',
                 "+devDependencies jest, +workspace app"),
                ("pyproject.toml", PYPROJECT, PYPROJECT.replace('"Rich[jupyter]==13.0"', '"httpx"'),
                 "+dependencies httpx, -dependencies rich"),
                ("requirements.txt", "requests\n", "requests\nPy_Yaml\n", "+py-yaml"),
                ("project.godot", GODOT, GODOT.replace('"4.7"', '"4.8"'),
                 "+application config/features 4.8, -application config/features 4.7"),
                ("project.godot", GODOT, GODOT.replace("[dotnet]", 'Audio="*res://audio.gd"\n\n[dotnet]'),
                 '+autoload Audio "*res://audio.gd"'),
                ("project.godot", GODOT, GODOT.replace('PackedStringArray("res://addons/gdUnit4/plugin.cfg")',
                                                       "PackedStringArray()"),
                 "-editor_plugins enabled res://addons/gdUnit4/plugin.cfg"),
                ("project.godot", GODOT, GODOT.replace("config_version=5", "config_version=6"),
                 "+project config_version 6, -project config_version 5")):
            with self.subTest(path=path, detail=detail):
                self.assertEqual(manifest_signals(path, base, head), [Signal(Kind.MANIFEST_CHANGED, path, detail)])

    def test_unreadable_or_unknown_manifests_count(self):
        for path, base, head in (("Atelier.csproj", CSPROJ, "<Project"), ("package.json", "{}", "{"),
                                 ("package.json", "{}", '{"dependencies": 3}'), ("package.json", "{}", "[]"),
                                 ("pyproject.toml", PYPROJECT, "[project"), ("Cargo.toml", "a", "b")):
            with self.subTest(path=path, head=head):
                self.assertEqual(manifest_signals(path, base, head), [Signal(Kind.MANIFEST_CHANGED, path)])


PILOT = """using Godot;

namespace Atelier.Controls;

/// <summary>Drives a ship.</summary>
public interface IPilot
{
    // Called every physics frame.
    Vector2 Steer(double delta);
    [Obsolete("use Steer")] void Turn(float angle);
    string Name { get; }
    event System.Action Crashed;
}
"""


def interface_signals(base, head):
    """Interface signals between two sets of {path: C# text}."""
    return structure.interface_signals(base, head)


class CSharpInterfacesTest(unittest.TestCase):
    def test_members_header_and_namespace(self):
        found = structure.csharp_interfaces(PILOT)
        self.assertEqual(list(found), ["Atelier.Controls.IPilot"])
        header, members = found["Atelier.Controls.IPilot"]
        self.assertEqual(header, "public interface IPilot")
        self.assertEqual(members, {"Vector2 Steer(double delta);", '[Obsolete("")]void Turn(float angle);',
                                   "string Name{get;}", "event System.Action Crashed;"})

    def test_block_scoped_and_nested_namespaces(self):
        text = "namespace A { namespace B { public interface IX { void M(); } } public interface IY {} }"
        self.assertEqual(sorted(structure.csharp_interfaces(text)), ["A.B.IX", "A.IY"])

    def test_only_public_interfaces(self):
        text = ("namespace N; internal interface IHidden { void M(); } interface IDefault { void M(); }"
                " public class Pilot { public void M() {} } public partial interface IShown<T> : IBase where T : class"
                " { T Get(); }")
        found = structure.csharp_interfaces(text)
        self.assertEqual(list(found), ["N.IShown"])
        self.assertEqual(found["N.IShown"][0], "public partial interface IShown<T>:IBase where T:class")

    def test_interface_without_body(self):
        self.assertEqual(structure.csharp_interfaces("namespace N; public interface IMarker; public interface IX { void M(); }"),
                         {"N.IMarker": ("public interface IMarker", frozenset()),
                          "N.IX": ("public interface IX", frozenset({"void M();"}))})


class InterfaceSignalsTest(unittest.TestCase):
    def test_removed_or_modified_member(self):
        for old, new in (("    Vector2 Steer(double delta);\n", ""),
                         ("Vector2 Steer(double delta);", "Vector2 Steer(float delta);"),
                         ('[Obsolete("use Steer")] void', "void"),
                         ("string Name { get; }", "string Name { get; set; }")):
            with self.subTest(old=old, new=new):
                self.assertEqual(interface_signals({"IPilot.cs": PILOT}, {"IPilot.cs": PILOT.replace(old, new)}),
                                 [Signal(Kind.INTERFACE_CHANGED, "IPilot.cs", "Atelier.Controls.IPilot")])

    def test_changed_header(self):
        for new in ("public interface IPilot<T>", "public interface IPilot : IDisposable", "[Tool] public interface IPilot"):
            with self.subTest(new=new):
                self.assertEqual(interface_signals({"IPilot.cs": PILOT},
                                                   {"IPilot.cs": PILOT.replace("public interface IPilot", new)}),
                                 [Signal(Kind.INTERFACE_CHANGED, "IPilot.cs", "Atelier.Controls.IPilot")])

    def test_deleted_renamed_or_no_longer_public(self):
        for head in ({}, {"IPilot.cs": PILOT.replace("IPilot", "IDriver")},
                     {"IPilot.cs": PILOT.replace("public interface", "internal interface")},
                     {"IPilot.cs": PILOT.replace("Atelier.Controls", "Atelier.Ships")}):
            with self.subTest(head=head):
                self.assertEqual(interface_signals({"IPilot.cs": PILOT}, head),
                                 [Signal(Kind.INTERFACE_REMOVED, "IPilot.cs", "Atelier.Controls.IPilot")])

    def test_additions_are_not_structural(self):
        added = PILOT.replace("    string Name", "    void Land();\n    string Name")
        added += "public interface IAutopilot { void Engage(); }\n"
        self.assertEqual(interface_signals({"IPilot.cs": PILOT}, {"IPilot.cs": added, "IHud.cs": "public interface IHud {}"}),
                         [])
        self.assertEqual(interface_signals({}, {"IPilot.cs": PILOT}), [])

    def test_comments_formatting_and_moves_are_not_structural(self):
        reformatted = (PILOT.replace("// Called every physics frame.", "/* Called once per frame. */")
                       .replace("Vector2 Steer(double delta);", "Vector2 Steer(\n        double delta\n    );")
                       .replace("string Name { get; }", "string Name{get;}"))
        self.assertEqual(interface_signals({"IPilot.cs": PILOT}, {"IPilot.cs": reformatted}), [])
        self.assertEqual(interface_signals({"IPilot.cs": PILOT, "Ship.cs": "class Ship {}"},
                                           {"Ship.cs": "class Ship {}\n" + PILOT}), [])

    def test_non_interface_changes_are_not_structural(self):
        self.assertEqual(interface_signals({"Pilot.cs": "public class Pilot { public void M() {} }",
                                            "IHidden.cs": "internal interface IHidden { void M(); }"},
                                           {"Pilot.cs": "public class Pilot { }", "IHidden.cs": ""}), [])

    def test_signal_text_for_logs(self):
        self.assertEqual(str(Signal(Kind.INTERFACE_CHANGED, "IPilot.cs", "Atelier.Controls.IPilot")),
                         "IPilot.cs: public interface changed (Atelier.Controls.IPilot)")


JOURNAL = '''"""Work journal."""
import json

ROOT = "journal"
_CACHE = {}


@cached
def collect(day: str, *, limit: int = 10) -> list[str]:
    """Activity of a day."""
    return [day] * limit


class Entry(Base):
    def __init__(self, text):
        self.text = text

    def render(self, width=80):
        return self.text[:width]

    def _wrap(self):
        return self.text


def _helper():
    return 1


def unused(x):
    return x
'''

INSTALL = "import journal\nfrom journal import ROOT, Entry, _helper\n\njournal.collect('today')\n"


def python_signals(base_journal, head_journal, importer=INSTALL, head_importer=None):
    """Interface signals of journal.py, imported by install.py, between two versions."""
    head = {"install.py": importer if head_importer is None else head_importer}
    if head_journal is not None:
        head["lib/journal.py"] = head_journal
    return structure.interface_signals({"lib/journal.py": base_journal, "install.py": importer}, head)


def changed(name):
    return [Signal(Kind.INTERFACE_CHANGED, "lib/journal.py", f"journal.{name}")]


def removed(name):
    return [Signal(Kind.INTERFACE_REMOVED, "lib/journal.py", f"journal.{name}")]


class PythonInterfacesTest(unittest.TestCase):
    def test_imported_names_are_exposed(self):
        found = structure.python_interfaces({"lib/journal.py": JOURNAL, "install.py": INSTALL}).interfaces
        self.assertEqual({d.name for d in found.values() if d.exposed},
                         {"journal.ROOT", "journal.Entry", "journal._helper", "journal.collect"})
        entry = found["lib/journal.py:Entry"]
        self.assertEqual(entry.interface, ("class Entry(Base):\n    pass", frozenset(
            {"def __init__(self, text):\n    pass", "def render(self, width=80):\n    pass"})))
        self.assertEqual(found["lib/journal.py:collect"].interface[0],
                         "@cached\ndef collect(day: str, *, limit: int=10) -> list[str]:\n    pass")

    def test_import_forms(self):
        for importer, exposed in (("from journal import *", {"journal.ROOT", "journal.collect", "journal.Entry",
                                                              "journal.unused"}),
                                  ("import lib.journal as j\nj.unused(1)", {"journal.unused"}),
                                  ("import lib.journal\nlib.journal.unused(1)", {"journal.unused"}),
                                  ("from .journal import unused", {"journal.unused"}),
                                  ("import json\njson.unused", set())):
            with self.subTest(importer=importer):
                found = structure.python_interfaces({"lib/journal.py": JOURNAL, "app.py": importer}).interfaces
                self.assertEqual({d.name for d in found.values() if d.exposed}, exposed)

    def test_star_import_follows_all_and_package_init(self):
        found = structure.python_interfaces({"lib/__init__.py": "__all__ = ['a']\na = 1\nb = 2\n",
                                             "app.py": "from lib import *\n"}).interfaces
        self.assertEqual({d.name for d in found.values() if d.exposed}, {"lib.a"})

    def test_a_file_importing_itself_exposes_nothing(self):
        found = structure.python_interfaces({"journal.py": "import journal\ndef f():\n    journal.f()\n"}).interfaces
        self.assertFalse(found["journal.py:f"].exposed)


class PythonInterfaceSignalsTest(unittest.TestCase):
    def test_changed_signature_bases_decorators_or_public_method(self):  # P1
        for old, new, name in (("limit: int = 10", "limit: int = 20", "collect"),
                               ("day: str, *", "day: str, verbose: bool, *", "collect"),
                               ("-> list[str]", "-> tuple[str]", "collect"),
                               ("@cached\n", "", "collect"),
                               ("class Entry(Base)", "class Entry", "Entry"),
                               ("def render(self, width=80)", "def render(self, width=100)", "Entry"),
                               ("    def render(self, width=80):\n        return self.text[:width]\n", "", "Entry"),
                               ("def __init__(self, text)", "def __init__(self, text, author)", "Entry"),
                               ("def _helper()", "def _helper(x)", "_helper")):
            with self.subTest(old=old, new=new):
                self.assertEqual(python_signals(JOURNAL, JOURNAL.replace(old, new)), changed(name))

    def test_removed_renamed_or_moved(self):  # P2
        self.assertEqual(python_signals(JOURNAL, JOURNAL.replace('ROOT = "journal"', "")), removed("ROOT"))
        self.assertEqual(python_signals(JOURNAL, JOURNAL.replace("class Entry", "class Record")), removed("Entry"))
        self.assertEqual(python_signals(JOURNAL, None, head_importer="from other import ROOT, Entry, _helper, collect"),
                         removed("ROOT") + removed("collect") + removed("Entry") + removed("_helper"))
        self.assertEqual(python_signals(JOURNAL, JOURNAL.replace("def _helper", "def _assist"), head_importer=""),
                         removed("_helper"))

    def test_additions_are_not_structural(self):  # P3
        added = JOURNAL.replace("    def _wrap", "    def close(self):\n        pass\n\n    def _wrap") + "\nNEW = 1\n"
        self.assertEqual(python_signals(JOURNAL, added), [])
        self.assertEqual(python_signals(JOURNAL, JOURNAL.replace("def unused(x)", "def unused(x, y)"),
                                        head_importer=INSTALL + "from journal import unused\n"), [])

    def test_body_comments_docstrings_formatting_and_values_are_not_structural(self):  # P4
        edited = (JOURNAL.replace("return [day] * limit", "# Repeat.\n    return [day for _ in range(limit)]")
                  .replace('"""Activity of a day."""', '"""What happened that day."""')
                  .replace("def collect(day: str, *, limit: int = 10)", "def collect(\n    day: str, *, limit: int=10\n)")
                  .replace('ROOT = "journal"', 'ROOT = "journals"')
                  .replace("return self.text\n\n\ndef _helper", "return self.text.strip()\n\n\ndef _helper"))
        self.assertEqual(python_signals(JOURNAL, edited), [])

    def test_names_no_other_file_imports_are_not_structural(self):  # P5
        self.assertEqual(python_signals(JOURNAL, JOURNAL.replace("def unused(x)", "def unused()")
                                        .replace("    def _wrap(self)", "    def _wrap(self, width)")), [])

    def test_unparsable_file_changes_its_exposed_names(self):
        self.assertEqual(python_signals(JOURNAL, JOURNAL + "\ndef broken(:\n"),
                         changed("ROOT") + changed("collect") + changed("Entry") + changed("_helper"))


FACADE = "from journal import collect, Entry as Record\nfrom os import path\nfrom . import journal\nfrom journal import *\n"
FACADE_USER = "from api import collect, Record, path, journal, ROOT\n"


def facade_signals(head_facade, importer=FACADE_USER, head_journal=JOURNAL):
    """Interface signals of api.py, which re-exports journal.py, imported by app.py, between two versions."""
    files = {"lib/journal.py": JOURNAL, "api.py": FACADE, "app.py": importer}
    return [s for s in structure.interface_signals(files, {**files, "api.py": head_facade,
                                                           "lib/journal.py": head_journal}) if s.path == "api.py"]


class PythonReExportSignalsTest(unittest.TestCase):
    def test_removed_reexport_imported_elsewhere(self):  # R1, R2: the bound name, any origin
        for new, name in (("Entry as Record", "collect"), ("collect", "Record"), ("collect, Entry", "Record")):
            with self.subTest(new=new):
                self.assertEqual(facade_signals(FACADE.replace("collect, Entry as Record", new)),
                                 [Signal(Kind.INTERFACE_REMOVED, "api.py", f"api.{name}")])
        self.assertEqual(facade_signals(FACADE.replace("from os import path\n", "")),
                         [Signal(Kind.INTERFACE_REMOVED, "api.py", "api.path")])

    def test_reexport_nobody_imports_is_not_structural(self):  # R3; test files never reach the extractor
        self.assertEqual(facade_signals("from journal import *\n", importer=""), [])

    def test_changed_definition_is_reported_on_its_module_only(self):  # R4
        signals = structure.interface_signals(
            {"lib/journal.py": JOURNAL, "api.py": FACADE, "app.py": FACADE_USER},
            {"lib/journal.py": JOURNAL.replace("limit: int = 10", "limit: int = 20"), "api.py": FACADE,
             "app.py": FACADE_USER})
        self.assertEqual(signals, changed("collect"))

    def test_switch_between_definition_and_reexport_is_a_change(self):  # R5
        defined = FACADE.replace("collect, ", "") + "\ndef collect(day):\n    return []\n"
        self.assertEqual(facade_signals(defined), [Signal(Kind.INTERFACE_CHANGED, "api.py", "api.collect")])
        files = {"lib/journal.py": JOURNAL, "api.py": defined, "app.py": FACADE_USER}
        self.assertEqual([s for s in structure.interface_signals(files, {**files, "api.py": FACADE})
                          if s.path == "api.py"], [Signal(Kind.INTERFACE_CHANGED, "api.py", "api.collect")])

    def test_last_binding_wins_and_constants_match_reexports(self):
        self.assertEqual(facade_signals(FACADE + "path = 'here'\n"), [])
        self.assertEqual(facade_signals(FACADE + "def path():\n    pass\n"),
                         [Signal(Kind.INTERFACE_CHANGED, "api.py", "api.path")])
        self.assertEqual(facade_signals("def path():\n    pass\n" + FACADE), [])

    def test_reexported_modules_and_star_are_not_tracked(self):  # documented out of scope
        self.assertEqual(facade_signals(FACADE.replace("from . import journal\n", "")
                                        .replace("from journal import *\n", "")), [])


MODELS = '''from dataclasses import dataclass
from enum import Enum


@dataclass
class Hour:
    day: str
    hour: int = 0
    tags: list[str] = None
    _cache: dict = None
    LIMIT = 24
    FIRST, LAST = 0, 23

    def __post_init__(self):
        self.seen = True


class Color(Enum):
    RED = 1
    GREEN = 2
'''


def attribute_signals(head_models):
    """Interface signals of models.py, imported by app.py, between MODELS and a head version."""
    importer = {"app.py": "from models import Hour, Color\n"}
    return structure.interface_signals({"models.py": MODELS, **importer}, {"models.py": head_models, **importer})


def attribute_changed(name):
    return [Signal(Kind.INTERFACE_CHANGED, "models.py", f"models.{name}")]


class PythonClassAttributeSignalsTest(unittest.TestCase):
    def test_removed_attribute_is_a_change(self):  # A1, A4
        for line, name in (("    day: str\n", "Hour"), ("    hour: int = 0\n", "Hour"), ("    LIMIT = 24\n", "Hour"),
                           ("    FIRST, LAST = 0, 23\n", "Hour"), ("    GREEN = 2\n", "Color")):
            with self.subTest(line=line):
                self.assertEqual(attribute_signals(MODELS.replace(line, "")), attribute_changed(name))

    def test_changed_or_added_annotation_is_a_change(self):  # A2, A4
        for old, new in (("day: str", "day: int"), ("tags: list[str]", "tags: list[int]"),
                         ("LIMIT = 24", "LIMIT: int = 24")):
            with self.subTest(old=old, new=new):
                self.assertEqual(attribute_signals(MODELS.replace(old, new)), attribute_changed("Hour"))

    def test_values_defaults_and_order_are_not_structural(self):  # A3, A4, A5
        for old, new in (("hour: int = 0", "hour: int = 1"), ("hour: int = 0", "hour: int"),
                         ("day: str", "day: str = ''"), ("LIMIT = 24", "LIMIT = 48"), ("RED = 1", "RED = 10"),
                         ("    day: str\n    hour: int = 0\n", "    hour: int = 0\n    day: str\n")):
            with self.subTest(old=old, new=new):
                self.assertEqual(attribute_signals(MODELS.replace(old, new)), [])

    def test_private_instance_and_added_attributes_are_not_structural(self):  # A5
        self.assertEqual(attribute_signals(MODELS.replace("    _cache: dict = None\n", "")
                                           .replace("self.seen = True", "self.seen: bool = False")
                                           .replace("    LIMIT = 24\n", "    LIMIT = 24\n    STEP: int = 1\n")), [])


FORECAST = '''package com.meteo.app.data.api

import retrofit2.http.GET
import retrofit2.http.Query

/** Talks to MET Norway. */
interface ForecastService {
    // Compact forecast, see https://api.met.no.
    @GET("weatherapi/locationforecast/2.0/compact")
    suspend fun compactForecast(
        @Query("lat") lat: Double,
        @Query("lon") lon: Double = 0.0,
        @Header("User-Agent") userAgent: String = "MeteoApp/1.0 (https://github.com/meteo/meteo)"
    ): ForecastResponse

    val priority: Int

    val label: String
        get() = "MET {Norway"

    fun describe(): String = """forecast
        $label"""

    fun clear() {
        println('}')
    }

    private fun log(message: String) {
        println(message)
    }
}
'''
FORECAST_NAME = "com.meteo.app.data.api.ForecastService"


class KotlinInterfacesTest(unittest.TestCase):
    def test_members_header_and_package(self):
        found = structure.kotlin_interfaces(FORECAST)
        self.assertEqual(list(found), [FORECAST_NAME])
        header, members = found[FORECAST_NAME]
        self.assertEqual(header, "interface ForecastService")
        self.assertEqual(members, {
            '@GET("weatherapi/locationforecast/2.0/compact")suspend fun compactForecast(@Query("lat")lat:Double,'
            '@Query("lon")lon:Double=0.0,@Header("User-Agent")userAgent:String='
            '"MeteoApp/1.0 (https://github.com/meteo/meteo)"):ForecastResponse',
            "val priority:Int", "val label:String", "fun describe():String", "fun clear()"})

    def test_only_public_interfaces(self):
        text = ("package p\ninternal interface Hidden { fun m() }\nprivate interface Secret\n"
                "protected interface Guarded\nclass Pilot { fun m() {} }\nabstract class Base { abstract fun m() }\n"
                "sealed class State\npublic interface Shown<T> : Base,\n    Other where T : Any {\n    fun get(): T\n}\n"
                "@Stable fun interface Action { fun run() }\nsealed interface Event\n")
        found = structure.kotlin_interfaces(text)
        self.assertEqual(sorted(found), ["p.Action", "p.Event", "p.Shown"])
        self.assertEqual(found["p.Shown"][0], "interface Shown<T>:Base,Other where T:Any")
        self.assertEqual(found["p.Action"], ("@Stable fun interface Action", frozenset({"fun run()"})))
        self.assertEqual(found["p.Event"], ("sealed interface Event", frozenset()))

    def test_nested_types(self):
        text = ("class Outer {\n    interface Inner { fun m() }\n    companion object { val x = 1 }\n}\n"
                "interface Host {\n    fun m()\n    interface Child { fun n() }\n"
                "    class Impl(val y: Int) : Host { override fun m() {} }\n    object Default\n    val z: Int\n}\n")
        self.assertEqual(structure.kotlin_interfaces(text),
                         {"Outer.Inner": ("interface Inner", frozenset({"fun m()"})),
                          "Host": ("interface Host", frozenset({"fun m()", "val z:Int"})),
                          "Host.Child": ("interface Child", frozenset({"fun n()"}))})

    def test_public_modifier_is_the_default(self):
        self.assertEqual(structure.kotlin_interfaces("public interface X { public fun m() }"),
                         structure.kotlin_interfaces("interface X { fun m() }"))


def replace_once(text, old, new):
    assert old in text, old
    return text.replace(old, new)


class KotlinInterfaceSignalsTest(unittest.TestCase):
    CHANGED = [Signal(Kind.INTERFACE_CHANGED, "ForecastService.kt", FORECAST_NAME)]

    def signals(self, head, base=None):
        return interface_signals(base or {"ForecastService.kt": FORECAST}, head)

    def test_removed_or_modified_member(self):
        for old, new in (("    val priority: Int\n", ""), ("val priority: Int", "val priority: Long"),
                         ("val priority", "var priority"), ("2.0/compact", "2.0/complete"),
                         ("lon: Double = 0.0", "lon: Double"), ('@Query("lat") ', ""),
                         ("suspend fun compactForecast", "fun compactForecast")):
            with self.subTest(old=old, new=new):
                self.assertEqual(self.signals({"ForecastService.kt": replace_once(FORECAST, old, new)}), self.CHANGED)

    def test_changed_header(self):
        for new in ("interface ForecastService<T>", "interface ForecastService : Service",
                    "@Deprecated(\"x\")\ninterface ForecastService", "sealed interface ForecastService"):
            with self.subTest(new=new):
                head = replace_once(FORECAST, "interface ForecastService", new)
                self.assertEqual(self.signals({"ForecastService.kt": head}), self.CHANGED)

    def test_deleted_renamed_or_no_longer_public(self):
        for head in ({}, {"ForecastService.kt": FORECAST.replace("ForecastService", "WeatherService")},
                     {"ForecastService.kt": FORECAST.replace("interface Forecast", "internal interface Forecast")},
                     {"ForecastService.kt": FORECAST.replace("data.api", "data.remote")}):
            with self.subTest(head=head):
                self.assertEqual(self.signals(head),
                                 [Signal(Kind.INTERFACE_REMOVED, "ForecastService.kt", FORECAST_NAME)])

    def test_additions_are_not_structural(self):
        added = replace_once(FORECAST, "    val priority", "    fun refresh()\n    val priority") + "interface Cache\n"
        self.assertEqual(self.signals({"ForecastService.kt": added, "Hud.kt": "interface Hud"}), [])
        self.assertEqual(self.signals({"ForecastService.kt": FORECAST}, base={"Other.kt": ""}), [])

    def test_comments_formatting_bodies_private_members_and_moves_are_not_structural(self):
        changed = (FORECAST.replace("/** Talks to MET Norway. */", "// Talks to MET Norway.")
                   .replace("val priority: Int", "val priority:Int")
                   .replace('meteo/meteo)"\n', 'meteo/meteo)",\n')
                   .replace('get() = "MET {Norway"', 'get() = "met.no"')
                   .replace('"""forecast\n        $label"""', '"forecast"')
                   .replace("println('}')", "cache.clear()")
                   .replace("private fun log(message: String)", "private fun log(text: String, level: Int)"))
        self.assertEqual(self.signals({"ForecastService.kt": changed}), [])
        self.assertEqual(self.signals({"api/Forecast.kt": "class Forecast\n" + FORECAST}), [])

    def test_non_interface_changes_are_not_structural(self):
        self.assertEqual(interface_signals({"Pilot.kt": "class Pilot { fun m() {} }",
                                            "Hidden.kt": "internal interface Hidden { fun m() }"},
                                           {"Pilot.kt": "class Pilot", "Hidden.kt": ""}), [])

    def test_gradle_scripts_are_not_read(self):
        self.assertEqual(interface_signals({"build.gradle.kts": "interface X { fun m() }"}, {}), [])


ENGINE_PATH = "crates/stellar-domain/src/engine.rs"
ENGINE = """//! Physics engines.
use crate::state::State;

/// Advances a simulation.
pub trait PhysicsEngine: Send {
    /// Engine id.
    const ID: &'static str;
    type Error: std::error::Error;
    // One step.
    fn step(&mut self, state: &mut State, dt: f64) -> Result<(), Self::Error>;
    #[must_use]
    fn name(&self) -> String {
        format!("{}", "engine {")
    }
}
"""
ENGINE_KEY = "stellar-domain::engine::PhysicsEngine"


class RustTraitsTest(unittest.TestCase):
    def test_members_header_and_key(self):
        found = structure.rust_traits(ENGINE_PATH, ENGINE)
        self.assertEqual(list(found), [ENGINE_KEY])
        header, members = found[ENGINE_KEY]
        self.assertEqual(header, "pub trait PhysicsEngine:Send")
        self.assertEqual(members, {"const ID:&'static str", "type Error:std::error::Error",
                                   "fn step(&mut self,state:&mut State,dt:f64)->Result<(),Self::Error>",
                                   "#[must_use]fn name(&self)->String"})

    def test_module_path_from_file_path(self):
        for path, key in (("crates/x/src/lib.rs", "x::T"), ("crates/x/src/main.rs", "x::T"),
                          ("crates/x/src/a/mod.rs", "x::a::T"), ("crates/x/src/a/b.rs", "x::a::b::T"),
                          ("src/lib.rs", "crate::T")):
            with self.subTest(path=path):
                self.assertEqual(list(structure.rust_traits(path, "pub trait T {}")), [key])

    def test_files_outside_src_are_ignored(self):
        for path in ("crates/x/tests/engine.rs", "crates/x/build.rs", "examples/demo.rs", "crates/x/benches/b.rs"):
            with self.subTest(path=path):
                self.assertEqual(structure.rust_traits(path, "pub trait T {}"), {})

    def test_inline_modules_are_in_the_path(self):
        text = "mod a { pub mod b { pub trait T { fn m(&self); } } } pub trait U {}"
        self.assertEqual(sorted(structure.rust_traits("crates/x/src/lib.rs", text)), ["x::U", "x::a::b::T"])

    def test_only_pub_traits(self):
        text = ("pub(crate) trait A {} pub(super) trait B {} pub (in crate::a) trait C {} trait D {}"
                " pub struct S { pub f: u8 } pub fn f() {} pub enum E { V } impl D for S {}"
                ' #[cfg(feature = "x")] pub unsafe trait Shown<T>: Clone where T: Send { fn g(&self) -> T; }')
        found = structure.rust_traits("crates/x/src/lib.rs", text)
        self.assertEqual(list(found), ["x::Shown"])
        self.assertEqual(found["x::Shown"][0], '#[cfg(feature="")]pub unsafe trait Shown<T>:Clone where T:Send')

    def test_raw_strings_and_chars_are_not_code(self):
        text = """pub trait T { const S: &'static str = r#"a "} b;"#; const C: char = '}'; fn m(); }"""
        self.assertEqual(structure.rust_traits("crates/x/src/lib.rs", text)["x::T"][1],
                         {"const S:&'static str=\"\"", "const C:char=\"\"", "fn m()"})

    def test_trait_alias_without_body(self):
        self.assertEqual(structure.rust_traits("crates/x/src/lib.rs", "pub trait Alias = Send + Sync;"),
                         {"x::Alias": ("pub trait Alias=Send + Sync", frozenset())})


class RustInterfaceSignalsTest(unittest.TestCase):
    def signals(self, head, base=None):
        return interface_signals(base or {ENGINE_PATH: ENGINE}, head)

    def test_removed_or_modified_member(self):
        for old, new in (("    type Error: std::error::Error;\n", ""),
                         ("dt: f64", "dt: f32"),
                         ("    #[must_use]\n", ""),
                         ("&'static str", "&'static [u8]")):
            with self.subTest(old=old, new=new):
                self.assertEqual(self.signals({ENGINE_PATH: ENGINE.replace(old, new)}),
                                 [Signal(Kind.INTERFACE_CHANGED, ENGINE_PATH, ENGINE_KEY)])

    def test_changed_header(self):
        for new in ("pub trait PhysicsEngine<T>: Send", "pub trait PhysicsEngine: Send + Sync",
                    "pub trait PhysicsEngine: Send where Self: Sized", "pub unsafe trait PhysicsEngine: Send"):
            with self.subTest(new=new):
                self.assertEqual(self.signals({ENGINE_PATH: ENGINE.replace("pub trait PhysicsEngine: Send", new)}),
                                 [Signal(Kind.INTERFACE_CHANGED, ENGINE_PATH, ENGINE_KEY)])

    def test_deleted_renamed_restricted_or_moved_to_another_module(self):
        for head in ({}, {ENGINE_PATH: ENGINE.replace("PhysicsEngine", "Engine")},
                     {ENGINE_PATH: ENGINE.replace("pub trait", "pub(crate) trait")},
                     {ENGINE_PATH: "", "crates/stellar-domain/src/physics.rs": ENGINE}):
            with self.subTest(head=head):
                self.assertEqual(self.signals(head), [Signal(Kind.INTERFACE_REMOVED, ENGINE_PATH, ENGINE_KEY)])

    def test_additions_are_not_structural(self):
        added = ENGINE.replace("    #[must_use]", "    fn reset(&mut self);\n    #[must_use]")
        added += "pub trait EngineFactory { fn create(&self) -> Box<dyn PhysicsEngine<Error = ()>>; }\n"
        self.assertEqual(self.signals({ENGINE_PATH: added}), [])

    def test_comments_formatting_default_bodies_and_same_module_moves_are_not_structural(self):
        reformatted = (ENGINE.replace("// One step.", "/* A single step. */")
                       .replace("/// Engine id.", "/// The engine id.")
                       .replace("dt: f64) -> Result", "dt: f64,\n    ) -> Result")
                       .replace('format!("{}", "engine {")', "String::from(\"cpu\")"))
        self.assertEqual(self.signals({ENGINE_PATH: reformatted.replace("dt: f64,", "dt: f64")}), [])
        module = "crates/stellar-domain/src/engine/mod.rs"
        self.assertEqual(self.signals({module: ENGINE}, base={module: ENGINE}), [])
        self.assertEqual(self.signals({ENGINE_PATH: ENGINE}, base={module: ENGINE}), [])

    def test_non_trait_changes_are_not_structural(self):
        lib = "crates/x/src/lib.rs"
        self.assertEqual(interface_signals({lib: "pub struct S; pub fn f(a: u8) {} pub(crate) trait H { fn m(); }"},
                                           {lib: "pub struct S(u8); pub fn f() {}"}), [])


class DiffSignalsTest(unittest.TestCase):
    """diff_signals on a real repository."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def write(self, name, text="x\n"):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")
        return self.git("rev-parse", "HEAD")

    def test_changes_since_the_merge_base(self):
        self.write("src/app.py")
        self.write("old/tool.py")
        self.write("package.json", "{}\n")
        base = self.commit()
        self.git("checkout", "-q", "-b", "feature")
        self.write("src/app.py", "y\n")
        (self.repo / "old" / "tool.py").unlink()
        self.write("server/main.py")
        self.write("package.json", '{"dependencies": {"a": "1"}}\n')
        head = self.commit()
        self.git("checkout", "-q", "main")
        self.write("main_only/file.py")
        main = self.commit()
        self.assertEqual(structure.diff_signals(main, head, {}, cwd=self.repo),
                         [Signal(Kind.MANIFEST_CHANGED, "package.json", "+dependencies a"),
                          Signal(Kind.FOLDER_ADDED, "server/"),
                          Signal(Kind.FOLDER_REMOVED, "old/")])
        self.assertEqual(structure.diff_signals(base, base, {}, cwd=self.repo), [])

    def test_public_interface_removed_or_changed_member(self):
        self.write("scripts/Controls/IPilot.cs", PILOT)
        self.write("scripts/Hud/Hud.cs", "namespace Atelier.Hud { public interface IHudSource { int Score(); } }\n")
        self.write("scripts/Ship.cs", "public class Ship {}\n")
        base = self.commit()
        self.write("scripts/Controls/IPilot.cs", PILOT.replace("    string Name { get; }\n", ""))
        (self.repo / "scripts" / "Hud" / "Hud.cs").unlink()
        self.write("scripts/Ship.cs", "public class Ship { public void Fly() {} }\n")
        self.write("scripts/IAutopilot.cs", "public interface IAutopilot { void Engage(); }\n")
        head = self.commit()
        self.assertEqual(structure.diff_signals(base, head, {}, cwd=self.repo),
                         [Signal(Kind.INTERFACE_CHANGED, "scripts/Controls/IPilot.cs", "Atelier.Controls.IPilot"),
                          Signal(Kind.INTERFACE_REMOVED, "scripts/Hud/Hud.cs", "Atelier.Hud.IHudSource")])

    def test_added_member_is_not_structural(self):
        self.write("scripts/Controls/IPilot.cs", PILOT)
        base = self.commit()
        self.write("scripts/Controls/IPilot.cs", PILOT.replace("    string Name", "    void Land();\n    string Name"))
        head = self.commit()
        self.assertEqual(structure.diff_signals(base, head, {}, cwd=self.repo), [])

    def test_python_imported_signature_changed_body_changed_or_test_import(self):
        self.write("plugins/journal/scripts/journal.py", JOURNAL)
        self.write("scripts/install.py", INSTALL)
        self.write("tests/test_journal.py", "from journal import unused\n")
        base = self.commit()
        self.write("plugins/journal/scripts/journal.py",
                   JOURNAL.replace("limit: int = 10", "limit: int = 20").replace("return x", "return -x")
                   .replace("def unused(x)", "def unused(x, y)"))
        head = self.commit()
        self.assertEqual(structure.diff_signals(base, head, {}, cwd=self.repo),
                         [Signal(Kind.INTERFACE_CHANGED, "plugins/journal/scripts/journal.py", "journal.collect")])
        self.write("plugins/journal/scripts/journal.py", JOURNAL.replace("return [day] * limit", "return []"))
        self.assertEqual(structure.diff_signals(base, self.commit(), {}, cwd=self.repo), [])

    def test_rust_trait_member_removed_or_added(self):
        self.write(ENGINE_PATH, ENGINE)
        base = self.commit()
        self.write(ENGINE_PATH, ENGINE.replace("    fn step", "    fn reset(&mut self);\n    fn step"))
        added = self.commit()
        self.write(ENGINE_PATH, ENGINE.replace("    const ID: &'static str;\n", ""))
        removed = self.commit()
        self.assertEqual(structure.diff_signals(base, added, {}, cwd=self.repo), [])
        self.assertEqual(structure.diff_signals(added, removed, {}, cwd=self.repo),
                         [Signal(Kind.INTERFACE_CHANGED, ENGINE_PATH, ENGINE_KEY)])

    def test_kotlin_interface_changed_member(self):
        self.write("app/src/ForecastService.kt", FORECAST)
        base = self.commit()
        self.write("app/src/ForecastService.kt", FORECAST.replace("    val priority: Int\n", ""))
        head = self.commit()
        self.assertEqual(structure.diff_signals(base, head, {}, cwd=self.repo),
                         [Signal(Kind.INTERFACE_CHANGED, "app/src/ForecastService.kt", FORECAST_NAME)])

    def test_kotlin_added_member_is_not_structural(self):
        self.write("app/src/ForecastService.kt", FORECAST)
        base = self.commit()
        self.write("app/src/ForecastService.kt", FORECAST.replace("    val priority", "    fun refresh()\n    val priority"))
        head = self.commit()
        self.assertEqual(structure.diff_signals(base, head, {}, cwd=self.repo), [])


if __name__ == "__main__":
    unittest.main()
