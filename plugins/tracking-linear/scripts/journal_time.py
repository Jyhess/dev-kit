#!/usr/bin/env python3
"""Hours of the work journal spent on a project over a period, for a step review.

    python3 journal_time.py <journal dir> <project> --since 2026-11-02 [--until 2026-11-13]

Each journal entry is one hour (`### HH:00–HH:00 · <category> · <project>`, in
`journal/<week>/<day>-<machine>.md`). An entry counts when its project is the one
requested and its day is in the period, both bounds included (`--until` defaults
to today). An hour logged by both machines counts once. Prints JSON: the total
hours, the hours per category, and the entries marked `❓` of the hours no
machine has filled in otherwise, which are listed but not counted. The files
are read with the parser of the dev-journal plugin.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dev-journal" / "scripts"))
import dev_journal  # noqa: E402

FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")


def entries(journal: Path):
    """Yield (day, machine, hour, fields, text) for every entry of the journal."""
    for path in sorted(journal.rglob("*.md")):
        m = FILE.match(path.name)
        if not m:
            continue
        day, machine = m.groups()
        for hour, (fields, text) in sorted(dev_journal.parse_entries(path).items()):
            yield day, machine, hour, fields, text


def time_for(journal: Path, project: str, since: datetime.date, until: datetime.date) -> dict:
    slots: dict[tuple[str, int], list] = {}
    for day, machine, hour, fields, text in entries(journal):
        if len(fields) < 2 or fields[1].casefold() != project.casefold():
            continue
        if since <= datetime.date.fromisoformat(day) <= until:
            slots.setdefault((day, hour), []).append((machine, fields, text))
    hours: Counter[str] = Counter()
    unknown = []
    for (day, hour), found in sorted(slots.items()):
        known = [fields for _, fields, _ in found if not dev_journal.is_unknown(fields)]
        if known:
            hours[known[0][0]] += 1
            continue
        machine, _, text = found[0]
        unknown.append({"day": day, "hour": f"{hour:02d}:00", "machine": machine,
                        "text": text.splitlines()[0] if text else ""})
    return {"project": project, "since": since.isoformat(), "until": until.isoformat(),
            "hours": sum(hours.values()), "by_category": dict(sorted(hours.items())),
            "unknown": unknown}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("journal", type=Path, help="the journal repository, or its journal/ folder")
    parser.add_argument("project", help="the project name used in the journal entries")
    parser.add_argument("--since", type=datetime.date.fromisoformat, required=True, help="first day, YYYY-MM-DD")
    parser.add_argument("--until", type=datetime.date.fromisoformat, default=datetime.date.today(),
                        help="last day, YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    print(json.dumps(time_for(args.journal, args.project, args.since, args.until), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
