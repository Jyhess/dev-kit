#!/usr/bin/env python3
"""Warn when a Claude Code session's context grows past the size where calls get costly.

Run by the core plugin on `UserPromptSubmit`, `PostToolUse` and `SessionStart`
(resume); about 35 ms a run, Python's start included, whatever the transcript's
size: kept on `PostToolUse`, as `UserPromptSubmit` alone would warn a long
autonomous turn only after it ends. The context of the last call is read from
the end of the session transcript (`transcript_path` of the hook input):
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens` of the
last main-thread assistant entry. Calls above 200k tokens weighed 47% of quota
units (docs/token-usage.md).

- Past WARN tokens, then past LIMIT tokens, Claude is told once per level to
  ask the user, when the turn ends, whether to hand over to a new session; it
  never stops its work for it. The user gets a one-line system message.
  Both levels are re-armed once the context is back under WARN (after a
  compaction). The level already warned is kept per session in a small file
  of the system's temporary folder.
- On resume, when the last call is older than the cache lifetime and the
  context is over RESUME_MIN tokens, Claude is told to propose a hand-over.

Never blocks the session: it always exits 0 and prints nothing or one JSON object.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

WARN = 400_000
LIMIT = 500_000
RESUME_MIN = 100_000
CACHE_LIFETIME = timedelta(hours=1)
TAIL = 1 << 20  # bytes read from the end of the transcript before reading it all
STATE_DIR = Path(tempfile.gettempdir()) / "dev-kit-context-size"

HAND_OVER = (
    "To hand over: in a sub-session working on one ticket, comment the ticket (done, left, branch or PR), "
    "then hand the work over to a new session on the same branch (the app's hand-off tool when available, "
    "else give the user a short brief to paste into a new session). In a pilot session that steers a theme "
    "through sub-sessions, close the pilot with the core:pilot skill: comment the theme's parent ticket "
    "(state, open sub-sessions, next steps), then propose a new pilot session.")
MESSAGES = {
    1: ("Context size: this session's context is {k}k tokens, past the {warn}k warning level "
        "(calls above {limit}k cost about half of the quota). Do not stop the current work for it: when you give the turn back to the user, say so and ask them whether to "
        "hand over now. " + HAND_OVER,
        "contexte : {k}k tokens, Claude te demandera en fin de tour s'il passe la main."),
    2: ("Context size: this session's context is {k}k tokens, past the {limit}k limit. "
        "Do not stop the current work for it: when you give the turn back to the user, ask them what to do, "
        "recommending to hand over before any other work. " + HAND_OVER,
        "contexte : {k}k tokens, au-delà de {limit}k : Claude te demandera en fin de tour quoi faire."),
    "resume": ("Context size: this session was resumed {hours} after its last call, with {k}k tokens of context; "
               "its cache has expired, so going on rewrites the whole context. Propose to the user to hand over "
               "instead of going on, unless what is left is a few calls. " + HAND_OVER,
               "contexte : reprise après {hours} avec {k}k tokens, Claude propose de passer la main."),
}


def last_call(transcript: Path) -> tuple[int, datetime | None] | None:
    """Context size and time of the last main-thread call, or None when unknown or before a compaction."""
    size = transcript.stat().st_size
    with transcript.open("rb") as file:
        file.seek(max(0, size - TAIL))
        lines = file.read().splitlines()
    if size > TAIL:
        found = _scan(lines[1:])  # the first line may be cut
        if found is not False:
            return found
        lines = transcript.read_bytes().splitlines()
    found = _scan(lines)
    return None if found is False else found


def _scan(lines: list[bytes]):
    """Scan from the end; False when no call nor compaction is found in these lines."""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        if entry.get("subtype") == "compact_boundary":
            return None
        usage = (entry.get("message") or {}).get("usage") if entry.get("type") == "assistant" else None
        if isinstance(usage, dict):
            tokens = sum(int(usage.get(key) or 0) for key in
                         ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            return tokens, _time(entry.get("timestamp"))
    return False


def _time(value) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def level(tokens: int) -> int:
    return 2 if tokens >= LIMIT else 1 if tokens >= WARN else 0


def _duration(delta: timedelta) -> str:
    hours = delta.total_seconds() / 3600
    return f"{hours:.0f}h" if hours < 48 else f"{hours / 24:.0f} days"


def warning(event: str, source: str | None, tokens: int, when: datetime | None, warned: int,
            now: datetime) -> tuple[str | None, int]:
    """The message key to send (or None) and the level to remember."""
    current = level(tokens)
    if event == "SessionStart":
        stale = when is not None and now - when > CACHE_LIFETIME
        return ("resume" if source == "resume" and stale and tokens > RESUME_MIN else None), current
    if current > warned:
        return current, current
    return None, current if current == 0 else warned


def _state_file(state_dir: Path, session: str) -> Path:
    return state_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", session) + ".json")


def run(hook_input: dict, state_dir: Path = STATE_DIR, now: datetime | None = None) -> dict | None:
    event = hook_input.get("hook_event_name", "")
    transcript = hook_input.get("transcript_path")
    if not transcript or not Path(transcript).is_file():
        return None
    found = last_call(Path(transcript))
    if found is None:
        return None
    tokens, when = found
    state = _state_file(state_dir, str(hook_input.get("session_id") or Path(transcript).stem))
    try:
        warned = int(json.loads(state.read_text(encoding="utf-8")).get("level", 0))
    except (OSError, ValueError, AttributeError):
        warned = 0
    now = now or datetime.now(timezone.utc)
    key, remembered = warning(event, hook_input.get("source"), tokens, when, warned, now)
    if remembered != warned:
        state_dir.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"level": remembered}), encoding="utf-8")
    if key is None:
        return None
    values = {"k": round(tokens / 1000), "warn": WARN // 1000, "limit": LIMIT // 1000,
              "hours": _duration(now - when) if when else ""}
    for_claude, for_user = MESSAGES[key]
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": for_claude.format(**values)},
            "systemMessage": for_user.format(**values)}


def main() -> None:
    try:
        result = run(json.loads(sys.stdin.buffer.read() or b"{}"))
    except (OSError, ValueError, TypeError, AttributeError):
        result = None
    if result:
        print(json.dumps(result))  # ASCII escapes: safe whatever the console encoding
    sys.exit(0)


if __name__ == "__main__":
    main()
