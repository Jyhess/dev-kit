#!/usr/bin/env python3
"""Expose dev-kit skills and shared rules to Codex from the shared clone, and record where the clone is.

The shared rules are linked as ~/.dev-kit/rules, the path that the Shared rules section of
a project's AGENTS.md names.

Skills name their files as `<dev-kit>/plugins/<plugin>/...`, `<dev-kit>` being the `root`
of ~/.dev-kit/config.json: a path relative to the skill's folder would break on Windows,
which collapses `..` before following the junction under the Codex skills directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = Path.home() / ".dev-kit" / "config.json"
RULES_LINK = Path.home() / ".dev-kit" / "rules"
# Prefix of the Codex link names, `dev-kit-<plugin>-<skill>`,
# so generic skill names (docs, note, com…) cannot collide with other Codex skills.
LINK_PREFIX = "dev-kit-"


def windows() -> bool:
    return os.name == "nt"


def record_root(root: Path = ROOT, config: Path = LOCAL_CONFIG) -> list[str]:
    """Set `root` in the local config, keeping its other entries; an unreadable config raises ValueError."""
    data = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    if not isinstance(data, dict):
        raise ValueError(f"{config} is not a JSON object")
    wanted = str(root.resolve())
    if data.get("root") == wanted:
        return []
    data["root"] = wanted
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return [f"dev-kit root recorded in {config}"]


def codex_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return (Path(codex_home).expanduser() if codex_home else Path.home() / ".codex") / "skills"


def skills(root: Path = ROOT) -> list[Path]:
    return sorted(path.parent for path in root.glob("plugins/*/skills/*/SKILL.md"))


def link_name(skill: Path) -> str:
    return f"{LINK_PREFIX}{skill.parents[1].name}-{skill.name}"


def link_target(entry: Path) -> Path | None:
    """Where a symlink or junction points, or None for anything else."""
    try:
        target = os.readlink(entry)
    except (OSError, ValueError):
        return None
    if target.startswith("\\\\?\\"):
        target = target[4:]
    return Path(os.path.abspath(entry.parent / target))


def inside(path: Path, root: Path) -> bool:
    base = os.path.normcase(os.path.abspath(root))
    return os.path.normcase(str(path)).startswith(base + os.sep)


def remove_link(entry: Path) -> None:
    # A directory symlink or a junction is removed with rmdir on Windows.
    if windows():
        os.rmdir(entry)
    else:
        os.unlink(entry)


def same_target(link: Path, target: Path) -> bool:
    try:
        return link.resolve(strict=True) == target.resolve(strict=True)
    except (OSError, RuntimeError):
        return False


def create_link(link: Path, target: Path) -> None:
    if windows():
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            # Junctions do not require the symlink privilege on Windows.
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                           check=True, capture_output=True, text=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def install(root: Path = ROOT, destination: Path | None = None) -> list[str]:
    """Create user-level links and drop stale ones into the clone; never touch an unrelated entry."""
    target_dir = destination or codex_skills_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    sources = {link_name(source): source for source in skills(root)}
    messages = remove_stale_links(root, target_dir, set(sources))
    for name, source in sources.items():
        link = target_dir / name
        if os.path.lexists(link):
            if same_target(link, source):
                continue
            messages.append(f"warning: kept existing Codex skill {link}; it does not point to {source}")
            continue
        try:
            create_link(link, source.resolve())
        except subprocess.CalledProcessError as exc:
            messages.append(f"warning: could not link Codex skill {name} to {link}: {exc}: {(exc.stderr or '').strip()}")
        except OSError as exc:
            messages.append(f"warning: could not link Codex skill {name} to {link}: {exc}")
        else:
            messages.append(f"Codex skill {name} linked to the dev-kit clone")
    return messages


def remove_stale_links(root: Path, target_dir: Path, wanted: set[str]) -> list[str]:
    """Remove the links into the clone that no current skill uses (renamed, removed, former names)."""
    messages = []
    for entry in sorted(target_dir.iterdir()):
        target = link_target(entry)
        if entry.name in wanted or target is None or not inside(target, root.resolve()):
            continue
        try:
            remove_link(entry)
        except OSError as exc:
            messages.append(f"warning: could not remove stale Codex skill link {entry}: {exc}")
        else:
            messages.append(f"stale Codex skill link {entry.name} removed")
    return messages


def link_rules(root: Path = ROOT, link: Path = RULES_LINK) -> list[str]:
    """Link ~/.dev-kit/rules to the clone's shared rules, which AGENTS.md's Shared rules section points to.

    A link elsewhere (a former clone) is replaced; anything else is kept with a warning.
    """
    target = root / "plugins" / "core" / "rules"
    if os.path.lexists(link):
        if same_target(link, target):
            return []
        if link_target(link) is None:
            return [f"warning: kept {link}; it is not a link to {target}, Codex will not get the shared rules"]
        remove_link(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        create_link(link, target.resolve())
    except subprocess.CalledProcessError as exc:
        return [f"warning: could not link {link} to {target}: {exc}: {(exc.stderr or '').strip()}"]
    except OSError as exc:
        return [f"warning: could not link {link} to {target}: {exc}"]
    return [f"shared rules linked: {link} -> {target}"]


def main() -> None:
    try:
        messages = record_root() + install() + link_rules()
    except (ValueError, OSError) as exc:
        sys.exit(f"Codex installation failed: {exc}")
    for message in messages:
        print(message)


if __name__ == "__main__":
    main()
