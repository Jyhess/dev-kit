"""Tests of scripts/install_terminal.py with a temporary HOME."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install_terminal  # noqa: E402

LINE = 'source "/dev-kit/terminal/zsh/dev-kit.zsh"'


class InstallTerminalTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.zshrc = self.home / ".zshrc"

    def test_source_line_is_added_once_after_the_local_lines(self):
        self.zshrc.write_text("export PATH=$PATH:~/.local/bin\n", encoding="utf-8")
        self.assertTrue(install_terminal.add_source_line(self.zshrc, LINE))
        self.assertFalse(install_terminal.add_source_line(self.zshrc, LINE))
        text = self.zshrc.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("export PATH=$PATH:~/.local/bin\n\n# dev-kit"))
        self.assertEqual(text.count(LINE), 1)

    def test_missing_zshrc_is_created(self):
        self.assertTrue(install_terminal.add_source_line(self.zshrc, LINE))
        self.assertTrue(self.zshrc.read_text(encoding="utf-8").startswith("# dev-kit"))

    def test_source_line_points_at_the_clone(self):
        self.assertEqual(install_terminal.source_line(),
                         f'source "{(ROOT / "terminal" / "zsh" / "dev-kit.zsh").as_posix()}"')

    def test_every_missing_dependency_is_reported_with_its_command(self):
        deps = install_terminal.missing(self.home, {}, which=lambda tool: None)
        self.assertEqual([d.split(":")[0] for d in deps],
                         ["oh-my-zsh", "zsh-autosuggestions", "zsh-syntax-highlighting", "starship", "direnv"])
        self.assertIn("brew install starship", deps[3])

    def test_nothing_missing(self):
        zsh = self.home / ".oh-my-zsh"
        (zsh / "oh-my-zsh.sh").parent.mkdir()
        (zsh / "oh-my-zsh.sh").write_text("", encoding="utf-8")
        for plugin in ("zsh-autosuggestions", "zsh-syntax-highlighting"):
            (zsh / "custom" / "plugins" / plugin).mkdir(parents=True)
        self.assertEqual(install_terminal.missing(self.home, {}, which=lambda tool: "/bin/" + tool), [])


class FakePowerShell:
    """Answers the pwsh commands of install_windows like a machine with the given modules."""

    def __init__(self, profile: Path, modules=()):
        self.profile, self.modules, self.installed = profile, set(modules), []

    def __call__(self, cmd, **kwargs):
        command = cmd[-1]
        out = ""
        if command.startswith("(Get-Module"):
            out = "\n".join(sorted(self.modules))
        elif command.startswith("Install-Module"):
            name = command.split("'")[1]
            self.modules.add(name)
            self.installed.append(name)
        elif command.startswith("$PROFILE"):
            out = str(self.profile)
        return subprocess.CompletedProcess(cmd, 0, out, "")


class InstallWindowsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.profile = Path(tmp.name) / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"

    def test_fresh_machine_gets_modules_and_profile_line(self):
        shell = FakePowerShell(self.profile, modules={"posh-git"})
        report = install_terminal.install_windows(run=shell, which=lambda tool: None)
        self.assertEqual(shell.installed, [m for m in install_terminal.POWERSHELL_MODULES if m != "posh-git"])
        self.assertIn("missing: starship: winget install --id Starship.Starship -e", report)
        self.assertIn(install_terminal.profile_line(), self.profile.read_text(encoding="utf-8").splitlines())

    def test_second_run_changes_nothing_and_keeps_local_lines(self):
        self.profile.parent.mkdir(parents=True)
        self.profile.write_text("$env:LOCAL = 1\n", encoding="utf-8")
        shell = FakePowerShell(self.profile)
        install_terminal.install_windows(run=shell, which=lambda tool: "starship")
        first = self.profile.read_text(encoding="utf-8")
        shell.installed.clear()
        report = install_terminal.install_windows(run=shell, which=lambda tool: "starship")
        self.assertEqual(shell.installed, [])
        self.assertEqual(self.profile.read_text(encoding="utf-8"), first)
        self.assertTrue(first.startswith("$env:LOCAL = 1\n\n# dev-kit"))
        self.assertTrue(any("already loads" in line for line in report))

    def test_module_names_are_compared_without_case(self):
        self.assertEqual(install_terminal.missing_modules({m.lower() for m in install_terminal.POWERSHELL_MODULES}), [])

    def test_profile_line_points_at_the_clone(self):
        self.assertEqual(install_terminal.profile_line(),
                         f'. "{ROOT / "terminal" / "powershell" / "dev-kit.ps1"}"')


if __name__ == "__main__":
    unittest.main()
