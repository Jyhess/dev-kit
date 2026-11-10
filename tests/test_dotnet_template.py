"""End-to-end test of the .NET architecture set up by project-init: ArchitectureTest.cs (ArchUnitNET) and
architecture.py on a throwaway NUnit solution. Needs the .NET SDK and nuget.org, about a minute: runs only with
DEV_KIT_DOTNET_TEMPLATE=1, in the dotnet-template job of .github/workflows/verify.yml."""

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
sys.path.insert(0, str(SCRIPT.parent))
import architecture  # noqa: E402
import init_project  # noqa: E402

ENABLED = os.environ.get("DEV_KIT_DOTNET_TEMPLATE") == "1"
TARGET_FRAMEWORK = "net8.0"
TEST_PACKAGES = {"Microsoft.NET.Test.Sdk": "17.8.0", "NUnit": "3.14.0", "NUnit3TestAdapter": "4.5.0",
                 "TngTech.ArchUnitNET": "0.13.5"}
NUGET_CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
</configuration>
"""
# A root class with field initialisers depends on itself; Billing depends on Orders.
SOURCES = {
    "Shop/Shop.cs": "namespace Acme.Shop;\n\npublic class Shop\n{\n    private static readonly Shop Instance = new();\n"
                    "    private readonly int count = 1;\n    public int Count => count;\n}\n",
    "Shop/Orders/Order.cs": "namespace Acme.Shop.Orders;\n\npublic class Order\n{\n    public decimal Total { get; } = 1m;\n}\n",
    "Shop/Billing/Invoice.cs": "namespace Acme.Shop.Billing;\n\npublic class Invoice\n{\n"
                               "    public Acme.Shop.Orders.Order Order { get; } = new();\n}\n",
}
ORDER_USING_BILLING = ("namespace Acme.Shop.Orders;\n\npublic class Order\n{\n"
                       "    public object Invoice { get; } = new Acme.Shop.Billing.Invoice();\n}\n")


def csproj(properties: str, items: str) -> str:
    return (f'<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <TargetFramework>{TARGET_FRAMEWORK}</TargetFramework>\n'
            f"    <Nullable>enable</Nullable>\n    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>\n{properties}"
            f"  </PropertyGroup>\n  <ItemGroup>\n{items}  </ItemGroup>\n</Project>\n")


@unittest.skipUnless(ENABLED, "DEV_KIT_DOTNET_TEMPLATE=1 not set")
class DotnetTemplateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.assertIsNotNone(shutil.which("dotnet"), "dotnet not found")
        self.write("nuget.config", NUGET_CONFIG)
        self.write("Shop/Shop.csproj", csproj("    <RootNamespace>Acme.Shop</RootNamespace>\n"
                                              "    <AssemblyName>AcmeShop</AssemblyName>\n", ""))
        packages = "".join(f'    <PackageReference Include="{n}" Version="{v}" />\n' for n, v in TEST_PACKAGES.items())
        self.write("Shop.Tests/Shop.Tests.csproj", csproj(
            "    <IsPackable>false</IsPackable>\n",
            packages + '    <ProjectReference Include="../Shop/Shop.csproj" />\n'))
        for path, text in SOURCES.items():
            self.write(path, text)
        found, notes = init_project.resolve_dotnet(
            self.repo, {"project": "Shop.Tests/Shop.Tests.csproj", "main": "Shop/Shop.csproj"})
        self.assertIsNotNone(found, notes)
        changes, _ = init_project.plan_dotnet(self.repo, {"name": "Shop"}, found)
        for change in changes:
            change.apply()

    def write(self, path, text):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def run_command(self, *command, env=None):
        return subprocess.run(command, cwd=self.repo, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env={**os.environ, "DOTNET_NOLOGO": "1",
                                                     "DOTNET_CLI_TELEMETRY_OPTOUT": "1", **(env or {})})

    def check(self, *command, env=None):
        result = self.run_command(*command, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_written_diagram_passes_and_an_undrawn_dependency_fails(self):
        self.check(sys.executable, str(SCRIPT), "--write", ".")
        diagram = (self.repo / "docs/architecture.puml").read_text(encoding="utf-8")
        components = ["Acme.Shop", "Acme.Shop.Billing", "Acme.Shop.Orders"]
        for component in components:
            self.assertIn(f"[{component}] <<{architecture.stereotype(component, 'Acme.Shop', components)}>>\n",
                          diagram)
        self.check("dotnet", "test", "Shop.Tests", env={"ARCHITECTURE_DIAGRAM": "write"})
        diagram = (self.repo / "docs/architecture.puml").read_text(encoding="utf-8")
        self.assertTrue(diagram.endswith("[Acme.Shop.Billing] --> [Acme.Shop.Orders]\n@enduml\n"), diagram)
        self.check("dotnet", "test", "Shop.Tests")
        self.check(sys.executable, str(SCRIPT), ".")
        self.write("Shop/Orders/Order.cs", ORDER_USING_BILLING)
        result = self.run_command("dotnet", "test", "Shop.Tests")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Acme.Shop.Orders.Order does depend on Acme.Shop.Billing.Invoice", result.stdout)


if __name__ == "__main__":
    unittest.main()
