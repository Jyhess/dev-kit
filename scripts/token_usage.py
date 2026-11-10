#!/usr/bin/env python3
"""Measure where Claude Code tokens go, from the local session transcripts.

    python3 scripts/token_usage.py [--since 2026-11-01] [--root DIR] [--top 15] [--json | --save]

Reads every `<root>/*/*.jsonl` transcript (default root: `~/.claude/projects`,
worktree folders included) and sums the `usage` of each assistant message
(input, output, cache read, cache creation tokens) per session, project, model,
kind of session and day. Also reports the context size of each call, what a
session loads before its first answer (system prompt, tool definitions,
attachments, instruction files), the cache rebuilds, the tool results and the
skills that cost most.

Prints aggregates only: prompt text is read to classify sessions, never
printed. `--save` writes the report to `history/token-usage/<today>.md` of the
main dev-kit clone (git-ignored, found from worktrees too) instead, to compare
analyses over time without publishing a machine's figures.

Quota units weight each token type like the API price list (input 1, output 5,
cache read 0.1, cache write 1.25 for the 5-minute cache and 2 for the 1-hour
cache). The plan limits are not published; the weighting is an estimate of
what drains them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "core" / "scripts"))
import git_paths  # noqa: E402
WEIGHTS = {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write_5m": 1.25, "cache_write_1h": 2.0}
# A cache write at least this large after the first call, bigger than the cache read, re-sends the context.
REBUILD_MIN_TOKENS = 20_000
CHARS_PER_TOKEN = 4
BUCKETS = (50_000, 100_000, 150_000, 200_000, 300_000, 400_000)
WORKTREE = re.compile(r"[\\/]\.claude[\\/]worktrees[\\/][^\\/]+$")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
REVIEW = re.compile(r"\breview\b|\brelis\b|\brevue\b|\brelecture\b")


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    calls: int = 0

    @property
    def cache_write(self) -> int:
        return self.cache_write_5m + self.cache_write_1h

    @property
    def context(self) -> int:
        return self.input + self.cache_read + self.cache_write

    @property
    def units(self) -> float:
        return sum(getattr(self, k) * w for k, w in WEIGHTS.items())

    def add(self, other: "Usage") -> None:
        for k in ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h", "calls"):
            setattr(self, k, getattr(self, k) + getattr(other, k))


def usage_of(raw: dict) -> Usage:
    write = raw.get("cache_creation_input_tokens") or 0
    split = raw.get("cache_creation") or {}
    w1h = split.get("ephemeral_1h_input_tokens")
    w5m = split.get("ephemeral_5m_input_tokens")
    if w1h is None and w5m is None:
        w5m, w1h = write, 0
    return Usage(
        input=raw.get("input_tokens") or 0,
        output=raw.get("output_tokens") or 0,
        cache_read=raw.get("cache_read_input_tokens") or 0,
        cache_write_5m=w5m or 0,
        cache_write_1h=w1h or 0,
        calls=1,
    )


@dataclass
class Session:
    id: str
    project: str = "?"
    kind: str = "question"
    first: str = ""
    last: str = ""
    usage: Usage = field(default_factory=Usage)
    by_model: dict = field(default_factory=lambda: defaultdict(Usage))
    by_context: dict = field(default_factory=lambda: defaultdict(Usage))
    start_context: int = 0
    max_context: int = 0
    rebuilds: int = 0
    rebuild_tokens: int = 0
    startup_chars: Counter = field(default_factory=Counter)
    instruction_chars: Counter = field(default_factory=Counter)
    prefix_chars: Counter = field(default_factory=Counter)
    tool_result_chars: Counter = field(default_factory=Counter)
    tools: Counter = field(default_factory=Counter)
    skills: Counter = field(default_factory=Counter)
    skill_units: Counter = field(default_factory=Counter)


def project_of(cwd: str) -> str:
    """`C:\\dev\\shop\\.claude\\worktrees\\x` and `C:\\dev\\shop` are both `shop`."""
    cwd = WORKTREE.sub("", cwd.rstrip("\\/"))
    return re.split(r"[\\/]", cwd)[-1] or "?"


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def size_of(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(size_of(b.get("text", "") if isinstance(b, dict) else b) for b in content)
    return len(json.dumps(content)) if content else 0


def attachment_label(att: dict) -> str:
    kind = att.get("type", "?")
    if kind.startswith("hook_"):
        return f"hook:{att.get('hookEvent') or att.get('hookName') or '?'}"
    return kind


def bucket(context: int) -> str:
    """Context size class of one call, e.g. `100k-150k`."""
    low = 0
    for high in BUCKETS:
        if context < high:
            return f"{low // 1000}k-{high // 1000}k"
        low = high
    return f"{low // 1000}k+"


def classify(prompt: str, scheduled: bool, tools: Counter, skills: Counter) -> str:
    """Kind of session, from its first prompt and the tools it used."""
    head = prompt.lstrip()[:500].lower()
    if "[dev-journal]" in head:
        return "journal"
    if scheduled:
        return "scheduled"
    if any("review" in s for s in skills) or REVIEW.search(head):
        return "review"
    if sum(tools[t] for t in EDIT_TOOLS):
        return "implementation"
    if any(s.endswith("clarify") for s in skills) or tools["AskUserQuestion"]:
        return "clarification"
    return "question"


def parse_time(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def read_session(path: Path, since: datetime | None = None) -> Session | None:
    s = Session(id=path.stem)
    messages: dict[str, tuple[dict, str]] = {}
    order: list[str] = []
    tool_names: dict[str, str] = {}
    skill_of: dict[str, str] = {}  # message id -> skill running when it was sent
    running = ""
    prompt = ""
    scheduled = False
    answered = False
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = rec.get("type")
            if s.project == "?" and rec.get("cwd"):
                s.project = project_of(rec["cwd"])
            if kind == "api-request-shape" and not s.prefix_chars:
                shape = rec.get("shape") or {}
                s.prefix_chars["system prompt"] = len(json.dumps(shape.get("system") or ""))
                for tool in shape.get("tools") or []:
                    s.prefix_chars[f"tool:{tool.get('name', '?')}"] = len(json.dumps(tool))
            elif kind == "attachment" and not answered:
                att = rec.get("attachment") or {}
                s.startup_chars[attachment_label(att)] += len(json.dumps(rec.get("rendered") or att.get("content") or ""))
                if att.get("type") == "instructions":
                    for f_ in att.get("files") or []:
                        name = re.split(r"[\\/]", str(f_.get("path", "?")))[-1]
                        s.instruction_chars[name] += len(f_.get("content") or "")
            elif kind == "user":
                content = (rec.get("message") or {}).get("content")
                if not rec.get("isMeta") and text_of(content).strip():
                    if not prompt:
                        prompt = text_of(content)
                        scheduled = (rec.get("origin") or {}).get("subkind") == "scheduled-trigger"
                    running = ""  # a new prompt ends the skill that was running
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            name = tool_names.get(b.get("tool_use_id"), "?")
                            s.tool_result_chars[name] += size_of(b.get("content"))
            elif kind == "assistant":
                msg = rec.get("message") or {}
                if msg.get("model") == "<synthetic>":
                    continue
                answered = True
                key = msg.get("id") or rec.get("requestId") or rec.get("uuid")
                if key not in messages:
                    order.append(key)
                    skill_of[key] = running
                # Streamed messages repeat with the same usage, one record per content block.
                messages[key] = (msg, rec.get("timestamp", ""))
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        name = b.get("name", "?")
                        tool_names[b.get("id")] = name
                        s.tools[name] += 1
                        if name == "Skill":
                            running = str((b.get("input") or {}).get("skill", "?")).split(":")[-1]
                            s.skills[running] += 1
    for key in order:
        msg, stamp = messages[key]
        when = parse_time(stamp)
        if since and when and when < since:
            continue
        u = usage_of(msg.get("usage") or {})
        if s.usage.calls == 0:
            s.start_context = u.context
            s.first = stamp
        elif u.cache_write >= REBUILD_MIN_TOKENS and u.cache_read < u.cache_write:
            s.rebuilds += 1
            s.rebuild_tokens += u.cache_write
        s.max_context = max(s.max_context, u.context)
        s.usage.add(u)
        s.by_model[msg.get("model", "?")].add(u)
        s.by_context[bucket(u.context)].add(u)
        if skill_of.get(key):
            s.skill_units[skill_of[key]] += u.units
        s.last = stamp
    if s.usage.calls == 0:
        return None
    s.kind = classify(prompt, scheduled, s.tools, s.skills)
    return s


def read_all(root: Path, since: datetime | None) -> list[Session]:
    sessions = []
    for path in sorted(root.glob("*/*.jsonl")):
        if since and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < since:
            continue
        s = read_session(path, since)
        if s:
            sessions.append(s)
    return sessions


def human(n: float) -> str:
    for unit, size in (("G", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(n) >= size:
            return f"{n / size:.1f}{unit}"
    return f"{n:.0f}"


def pct(part: float, total: float) -> str:
    return f"{100 * part / total:.0f}%" if total else "0%"


def usage_table(title: str, column: str, rows: dict[str, tuple[Usage, int]], total: float, top: int) -> list[str]:
    lines = [f"## {title}", "", f"| {column} | sessions | calls | output | cache read | cache write | quota units | share |",
             "|---|---|---|---|---|---|---|---|"]
    for label, (u, n) in sorted(rows.items(), key=lambda kv: -kv[1][0].units)[:top]:
        lines.append(f"| {label} | {n} | {u.calls} | {human(u.output)} | {human(u.cache_read)} | {human(u.cache_write)} "
                     f"| {human(u.units)} | {pct(u.units, total)} |")
    return lines + [""]


def group(sessions: list[Session], key) -> dict[str, tuple[Usage, int]]:
    out: dict[str, tuple[Usage, int]] = {}
    for s in sessions:
        u, n = out.get(key(s), (Usage(), 0))
        u.add(s.usage)
        out[key(s)] = (u, n + 1)
    return out


def summed(sessions: list[Session], attr: str) -> Counter:
    out: Counter = Counter()
    for s in sessions:
        out.update(getattr(s, attr))
    return out


def report(sessions: list[Session], top: int = 15) -> str:
    total = Usage()
    for s in sessions:
        total.add(s.usage)
    t = total.units
    n = len(sessions)
    lines = ["# Token usage", "", f"{n} sessions, {total.calls} API calls, {human(t)} quota units.", "",
             "| token type | tokens | quota units | share |", "|---|---|---|---|"]
    for k, w in WEIGHTS.items():
        lines.append(f"| {k} | {human(getattr(total, k))} | {human(getattr(total, k) * w)} | {pct(getattr(total, k) * w, t)} |")
    lines.append("")

    by_model: dict[str, tuple[Usage, int]] = {}
    for s in sessions:
        for m, u in s.by_model.items():
            acc, k = by_model.get(m, (Usage(), 0))
            acc.add(u)
            by_model[m] = (acc, k + 1)
    lines += usage_table("Usage per project", "project", group(sessions, lambda s: s.project), t, top)
    lines += usage_table("Usage per kind of session", "kind", group(sessions, lambda s: s.kind), t, top)
    lines += usage_table("Usage per model", "model", by_model, t, top)
    lines += usage_table("Usage per day (UTC, session start)", "day", group(sessions, lambda s: s.first[:10]), t, top)

    lines += ["## Biggest sessions", "", "| session | project | kind | calls | start context | max context "
              "| cache rebuilds | quota units | share |", "|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(sessions, key=lambda s: -s.usage.units)[:top]:
        lines.append(f"| {s.id[:8]} | {s.project} | {s.kind} | {s.usage.calls} | {human(s.start_context)} "
                     f"| {human(s.max_context)} | {s.rebuilds} | {human(s.usage.units)} | {pct(s.usage.units, t)} |")
    lines.append("")

    calls = sorted(s.usage.calls for s in sessions)
    starts = sorted(s.start_context for s in sessions)
    start_tokens = sum(starts)
    prefix_read = sum(s.start_context * (s.usage.calls - 1) for s in sessions)
    rebuild_tokens = sum(s.rebuild_tokens for s in sessions)
    lines += ["## Context", "",
              f"- Calls per session: median {calls[n // 2]}, max {calls[-1]}.",
              f"- Context sent per call: mean {human(total.context / total.calls)} tokens.",
              f"- Context at the first call: median {human(starts[n // 2])}, max {human(starts[-1])} tokens. Writing it "
              f"to the cache: about {human(start_tokens * WEIGHTS['cache_write_1h'])} quota units "
              f"({pct(start_tokens * WEIGHTS['cache_write_1h'], t)}); reading it again at every later call: about "
              f"{human(prefix_read * WEIGHTS['cache_read'])} ({pct(prefix_read * WEIGHTS['cache_read'], t)}).",
              f"- Cache rebuilds (cache write of at least {human(REBUILD_MIN_TOKENS)} after the first call): "
              f"{sum(s.rebuilds for s in sessions)}, {human(rebuild_tokens)} tokens, about "
              f"{human(rebuild_tokens * WEIGHTS['cache_write_1h'])} quota units "
              f"({pct(rebuild_tokens * WEIGHTS['cache_write_1h'], t)}).", ""]

    buckets: dict[str, Usage] = defaultdict(Usage)
    for s in sessions:
        for b, u in s.by_context.items():
            buckets[b].add(u)
    lines += ["## Calls per context size", "", "| context of the call | calls | quota units | share |", "|---|---|---|---|"]
    for b in sorted(buckets, key=lambda b: int(b.split("k")[0])):
        lines.append(f"| {b} | {buckets[b].calls} | {human(buckets[b].units)} | {pct(buckets[b].units, t)} |")
    lines.append("")

    shaped = [s for s in sessions if s.prefix_chars]
    if shaped:
        prefix = summed(shaped, "prefix_chars")
        groups: Counter = Counter()
        for k, v in prefix.items():
            if k.startswith("tool:"):
                name = k[5:]
                groups["mcp:" + name.split("__")[1] if name.startswith("mcp__") else name] += v
        per = len(shaped) * CHARS_PER_TOKEN
        lines += ["## Fixed prefix of the first request", "",
                  f"Mean over {len(shaped)} sessions: system prompt {human(prefix['system prompt'] / per)} tokens, "
                  f"tool definitions {human(sum(groups.values()) / per)} tokens (chars / 4).", "",
                  "| tool or MCP server | mean tokens per session |", "|---|---|"]
        lines += [f"| {k} | {human(v / per)} |" for k, v in groups.most_common(top)] + [""]

    startup = summed(sessions, "startup_chars")
    lines += ["## Attachments before the first answer", "", "| attachment | mean tokens per session (chars / 4) |",
              "|---|---|"]
    lines += [f"| {k} | {human(v / CHARS_PER_TOKEN / n)} |" for k, v in startup.most_common(top)] + [""]

    instructions: Counter = Counter()
    for s in sessions:
        for name, chars in s.instruction_chars.items():
            instructions[(s.project, name)] = max(instructions[(s.project, name)], chars)
    if instructions:
        lines += ["## Instruction files loaded at start (largest copy)", "", "| project | file | tokens (chars / 4) |",
                  "|---|---|---|"]
        lines += [f"| {p} | {f} | {human(c / CHARS_PER_TOKEN)} |" for (p, f), c in instructions.most_common(top)] + [""]

    results = summed(sessions, "tool_result_chars")
    lines += ["## Tool results (tokens added to the context, chars / 4)", "", "| tool | tokens |", "|---|---|"]
    lines += [f"| {k} | {human(v / CHARS_PER_TOKEN)} |" for k, v in results.most_common(top)] + [""]

    skills = summed(sessions, "skills")
    if skills:
        spent = summed(sessions, "skill_units")
        lines += ["## Skills (quota units from the invocation to the next prompt)", "",
                  "| skill | invocations | quota units | share |", "|---|---|---|---|"]
        lines += [f"| {k} | {c} | {human(spent[k])} | {pct(spent[k], t)} |" for k, c in skills.most_common(top)] + [""]
    return "\n".join(lines)


def as_json(sessions: list[Session]) -> str:
    rows = []
    for s in sessions:
        u = s.usage
        rows.append({"session": s.id, "project": s.project, "kind": s.kind, "first": s.first, "last": s.last,
                     "calls": u.calls, "input": u.input, "output": u.output, "cache_read": u.cache_read,
                     "cache_write": u.cache_write, "units": round(u.units), "start_context": s.start_context,
                     "max_context": s.max_context, "rebuilds": s.rebuilds, "rebuild_tokens": s.rebuild_tokens,
                     "skills": dict(s.skills), "skill_units": {k: round(v) for k, v in s.skill_units.items()},
                     "tool_result_chars": dict(s.tool_result_chars)})
    return json.dumps(rows, indent=1)


def history_dir() -> Path:
    """`history/token-usage` of the main clone, also when run from a worktree."""
    return (git_paths.main_clone(ROOT) or ROOT) / "history" / "token-usage"


def save(text: str, folder: Path, today: date, since: str | None) -> Path:
    """Write the report as `<folder>/<today>.md`, with the measured period under its title."""
    path = folder / f"{today.isoformat()}.md"
    title, rest = text.split("\n", 1)
    period = f"since {since}" if since else "all transcripts"
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{title}\n\nMeasured on {today.isoformat()}, {period}.\n{rest}", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--since", help="first day, YYYY-MM-DD (UTC)")
    parser.add_argument("--top", type=int, default=15)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="one row per session instead of the report")
    output.add_argument("--save", action="store_true", help="write the report to history/token-usage/<today>.md")
    parser.add_argument("--history", type=Path, help=argparse.SUPPRESS)  # tests: folder of --save
    args = parser.parse_args(argv)
    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else None
    sessions = read_all(args.root, since)
    if not sessions:
        sys.exit(f"no session in {args.root}")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.save:
        path = save(report(sessions, args.top), args.history or history_dir(), date.today(), args.since)
        print(f"saved {path}")
        return
    print(as_json(sessions) if args.json else report(sessions, args.top))


if __name__ == "__main__":
    main()
