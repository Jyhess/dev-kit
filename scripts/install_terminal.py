#!/usr/bin/env python3
"""Install dev-kit's terminal configuration on this machine. Idempotent: run it again at will.

    python3 scripts/install_terminal.py

macOS: adds one line to ~/.zshrc that sources terminal/zsh/dev-kit.zsh
(oh-my-zsh, aliases, .NET aliases, background fetch, starship prompt from
terminal/starship.toml), and lists the missing dependencies with the command
that installs each; it installs nothing itself. The lines of ~/.zshrc that
dev-kit.zsh takes over are to be removed by hand.

Windows: installs the missing PowerShell modules for the current user, lists
starship with its winget command when it is missing, and adds one line to the
PowerShell 7 profile ($PROFILE) that dot-sources terminal/powershell/dev-kit.ps1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZSH_CONFIG = ROOT / "terminal" / "zsh" / "dev-kit.zsh"
POWERSHELL_CONFIG = ROOT / "terminal" / "powershell" / "dev-kit.ps1"
POWERSHELL_MODULES = ("posh-dotnet", "posh-git", "PSKubectlCompletion", "DockerCompletion", "npm-completion",
                      "WslInterop")
STARSHIP_WINGET = "winget install --id Starship.Starship -e"
OH_MY_ZSH = 'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"'


def source_line(config: Path = ZSH_CONFIG) -> str:
    return f'source "{config.as_posix()}"'


def missing(home: Path, env: dict, which=shutil.which) -> list[str]:
    """Missing dependencies, each with the command that installs it."""
    zsh = Path(env.get("ZSH") or home / ".oh-my-zsh")
    custom = Path(env.get("ZSH_CUSTOM") or zsh / "custom")
    found = []
    if not (zsh / "oh-my-zsh.sh").exists():
        found.append(f"oh-my-zsh: {OH_MY_ZSH}")
    for plugin in ("zsh-autosuggestions", "zsh-syntax-highlighting"):
        if not (custom / "plugins" / plugin).is_dir():
            found.append(f"{plugin}: git clone https://github.com/zsh-users/{plugin} {custom / 'plugins' / plugin}")
    for tool in ("starship", "direnv"):
        if not which(tool):
            found.append(f"{tool}: brew install {tool}")
    return found


def add_source_line(rc_file: Path, line: str) -> bool:
    """Append the line to the shell's startup file unless it is there; return True when added."""
    current = rc_file.read_text(encoding="utf-8") if rc_file.exists() else ""
    if line in (existing.strip() for existing in current.splitlines()):
        return False
    block = "# dev-kit terminal configuration (github.com/Jyhess/dev-kit)\n" + line + "\n"
    rc_file.parent.mkdir(parents=True, exist_ok=True)
    rc_file.write_text(current.rstrip("\n") + ("\n\n" if current.strip() else "") + block, encoding="utf-8")
    return True


def profile_line(config: Path = POWERSHELL_CONFIG) -> str:
    return f'. "{config}"'


def pwsh(command: str, run=subprocess.run) -> subprocess.CompletedProcess:
    return run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True,
               encoding="utf-8")


def missing_modules(available: set[str]) -> list[str]:
    lowered = {name.lower() for name in available}
    return [m for m in POWERSHELL_MODULES if m.lower() not in lowered]


def install_windows(run=subprocess.run, which=shutil.which) -> list[str]:
    """Install the PowerShell configuration; return what was done and what is missing."""
    report = []
    names = ",".join(f"'{m}'" for m in POWERSHELL_MODULES)
    listed = pwsh(f"(Get-Module -ListAvailable -Name {names}).Name", run)
    for module in missing_modules(set(listed.stdout.split())):
        result = pwsh(f"Install-Module -Name '{module}' -Scope CurrentUser -Repository PSGallery -Force -AllowClobber",
                      run)
        report.append(f"module {module} installed" if result.returncode == 0
                      else f"module {module} not installed: {(result.stderr or result.stdout).strip()}")
    if not which("starship"):
        report.append(f"missing: starship: {STARSHIP_WINGET}")
    profile = Path(pwsh("$PROFILE.CurrentUserCurrentHost", run).stdout.strip())
    added = add_source_line(profile, profile_line())
    report.append(f"{profile}: dev-kit.ps1 loaded" if added else f"{profile} already loads dev-kit.ps1")
    return report


def main() -> None:
    if sys.platform == "win32":
        if not shutil.which("pwsh"):
            sys.exit("PowerShell 7 (pwsh) is not on PATH: winget install --id Microsoft.PowerShell -e")
        print("\n".join(install_windows()))
        print("Open a new PowerShell to load it.")
        return
    if sys.platform != "darwin":
        sys.exit("Only macOS and Windows are supported.")
    home = Path.home()
    added = add_source_line(home / ".zshrc", source_line())
    print("~/.zshrc: dev-kit.zsh sourced" if added else "~/.zshrc already sources dev-kit.zsh")
    deps = missing(home, dict(os.environ))
    for dep in deps:
        print("missing: " + dep)
    print("Open a new shell to load it." if not deps else "Install what is missing, then open a new shell.")


if __name__ == "__main__":
    main()
