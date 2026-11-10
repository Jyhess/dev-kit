#!/usr/bin/env python3
"""Hourly work journal shared by the user's machines.

Subcommands:
  collect   local activity of the finished hours not logged yet (JSON)
  add       write (or replace) an entry in this machine's file
  note      add a note to this machine's day file, then commit and push
  check     UserPromptSubmit hook: tell Claude about the journal's gaps
  pull      pull the journal (run in the background by `check`)
  sync      commit and push the journal
  status    show the gaps and the hours to write, marking nothing
  register  add a project folder to the watched repositories, commit and push

The entries live in a journal repository of the user's own, cloned as
`dev-journal` next to dev-kit in the dev folder by `scripts/install.py
--journal-url URL`. Its `repos.json` lists the watched repositories by their
path relative to the dev folder, for every machine. Local configuration:
~/.dev-journal/config.json (`machine`, `start`, `journal_url`).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import functools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEV_KIT = Path(__file__).resolve().parents[3]
JOURNAL_REPO = DEV_KIT.parent / "dev-journal"
STATE_DIR = Path.home() / ".dev-journal"
CONFIG = STATE_DIR / "config.json"
STATE = STATE_DIR / "state.json"
TRANSCRIPTS = Path.home() / ".claude" / "projects"
SCRIPT = Path(__file__).resolve()

MARKER = "[dev-journal]"
CATEGORIES = ["dev", "cadrage", "organisation", "marketing", "admin", "autre"]
WORK_HOURS = range(9, 19)  # slots 9h–10h … 18h–19h
WORK_DAYS = range(0, 5)  # Monday–Friday
THIN_PROMPTS = 3
THIN_MINUTES = 10
COLLECT_LOOKBACK_H = 72
GAP_LOOKBACK_DAYS = 7
GRACE_MIN = 20  # time left to the hourly task before a slot counts as a gap
PULL_EVERY_MIN = 10
PULL_TIMEOUT_S = 60  # background pull of `check`

REPOS_FILE = "repos.json"
REPOS_HEADER = {"format": "dev-journal watched repositories", "format_version": 1,
                "program": "dev-kit dev-journal plugin"}

HEADING = re.compile(r"^### (\d{2}):00–(\d{2}):00 · (.+)$")
NOTES_HEADING = "## Notes"
NOTE_TIME = re.compile(r"^\d{2}:\d{2}$")
# Reflog actions that create a commit on this machine; pulls, fetches and rebases are left out.
LOCAL_ACTION = re.compile(r"^(commit( \([a-z]+\))?|cherry-pick|revert|merge [^:]+: Merge made)")
SYNC_SUBJECT = re.compile(r"^Journal \S+ \d{4}-\d{2}-\d{2}")


# ---------------------------------------------------------------- configuration and state

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_text(path, text):
    """Write a file with LF line ends on every system (the journal is shared by Windows and macOS)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def save_json(path, data):
    """Write through a temporary file, so that a concurrent hook never reads half a file."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    write_text(tmp, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def config(journal: Path = JOURNAL_REPO) -> dict:
    cfg = load_json(CONFIG, None)
    if not cfg:
        sys.exit(f"Configuration absente : {CONFIG} (lance `python3 scripts/install.py --journal-url <URL>` dans dev-kit)")
    if not (journal / ".git").exists():
        url = cfg.get("journal_url", "<URL du dépôt du journal>")
        sys.exit(f"Dépôt du journal absent : git clone {url} {journal}")
    return {**cfg, "journal": journal}


def now():
    return dt.datetime.now().astimezone()


def git(repo: Path, *args: str, timeout: float = 20) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout, env=env)


# ---------------------------------------------------------------- watched repositories

def watched_names(journal: Path) -> list[str]:
    return load_json(journal / REPOS_FILE, {}).get("repos", [])


def watched_repos(journal: Path) -> list[Path]:
    """Watched repositories of this machine: names relative to the dev folder."""
    return [journal.parent / name for name in watched_names(journal)]


def add_watched(journal: Path, names: list[str]) -> list[str]:
    """Add the names not watched yet (case-insensitive) to repos.json; return the added ones."""
    data = load_json(journal / REPOS_FILE, {})
    repos = data.get("repos", [])
    added = []
    for name in names:
        if name.casefold() not in {r.casefold() for r in repos + added}:
            added.append(name)
    if added:
        data = {**REPOS_HEADER, "created": data.get("created", dt.date.today().isoformat()),
                "repos": sorted(repos + added, key=str.casefold)}
        save_json(journal / REPOS_FILE, data)
    return added


def relative_name(journal: Path, target: Path) -> str:
    """Path of a project folder relative to the dev folder; ValueError when it is outside."""
    dev_dir = journal.parent.resolve()
    try:
        return target.resolve().relative_to(dev_dir).as_posix()
    except ValueError:
        raise ValueError(f"{target} n'est pas dans le dossier dev {dev_dir}") from None


def register(journal: Path, targets: list[Path]) -> list[str]:
    """Watch the project folders on every machine: update repos.json, commit and push."""
    added = add_watched(journal, [relative_name(journal, t) for t in targets])
    if added:
        commit_and_push(journal, [REPOS_FILE], f"Watch {', '.join(added)}")
    return added


@functools.lru_cache(maxsize=None)
def project_name(path: str) -> str:
    """Name of the GitHub repository of a folder (its origin), or the folder's name."""
    try:
        url = git(Path(path), "remote", "get-url", "origin", timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        url = ""
    if url:
        name = re.split(r"[/:\\]", url.rstrip("/"))[-1]
        return name[:-4] if name.endswith(".git") else name
    return Path(path).name


# ---------------------------------------------------------------- journal files

def day_dir(journal, day):
    year, week, _ = day.isocalendar()
    return journal / "journal" / f"{year}-S{week:02d}"


def day_file(journal, day, machine):
    return day_dir(journal, day) / f"{day.isoformat()}-{machine}.md"


def parse_entries(path):
    """{hour: (fields, text)} for a journal file; the notes section is left out."""
    entries, current = {}, None
    if not path.exists():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == NOTES_HEADING:
            break
        m = HEADING.match(line)
        if m:
            current = int(m.group(1))
            entries[current] = ([f.strip() for f in m.group(3).split("·")], [])
        elif current is not None:
            entries[current][1].append(line)
    return {h: (f, "\n".join(t).strip()) for h, (f, t) in entries.items()}


def is_unknown(fields):
    return fields[0].startswith("❓")


def parse_notes(path):
    """Lines of the notes section of a journal file (`- HH:MM · project · text`), as written."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = [l.strip() for l in lines].index(NOTES_HEADING) + 1
    except ValueError:
        return []
    return [l.rstrip() for l in lines[start:] if l.strip()]


def note_line(time, project, text):
    """One-line note: newlines and repeated spaces of the text become single spaces."""
    return f"- {time} · {project} · {' '.join(text.split())}"


def write_entries(path, day, machine, entries, notes=None):
    """Write a day file; notes=None keeps the notes already in the file."""
    if notes is None:
        notes = parse_notes(path)
    lines = [f"## {day.isoformat()} · {machine}", ""]
    for hour in sorted(entries):
        fields, text = entries[hour]
        lines.append(f"### {hour:02d}:00–{hour + 1:02d}:00 · {' · '.join(fields)}")
        if text:
            lines.append(text)
        lines.append("")
    if notes:
        lines += [NOTES_HEADING, "", *sorted(notes), ""]
    write_text(path, "\n".join(lines))


def add_note(path, day, machine, time, project, text):
    """Add a note to a day file, keeping its entries and its other notes."""
    if not NOTE_TIME.match(time) or not (0 <= int(time[:2]) < 24 and 0 <= int(time[3:]) < 60):
        raise ValueError(f"Heure invalide : {time} (attendu : HH:MM)")
    if not text.strip():
        raise ValueError("Note vide.")
    notes = parse_notes(path) + [note_line(time, project, text)]
    write_entries(path, day, machine, parse_entries(path), notes)


def all_entries(journal, day):
    """Entries of every machine for a day: {hour: [(machine, fields, text)]}."""
    merged = {}
    for path in sorted(day_dir(journal, day).glob(f"{day.isoformat()}-*.md")):
        machine = path.stem[len(day.isoformat()) + 1:]
        for hour, (fields, text) in parse_entries(path).items():
            merged.setdefault(hour, []).append((machine, fields, text))
    return merged


# ---------------------------------------------------------------- local activity

def text_of(content):
    if isinstance(content, str):
        return content
    parts = [b.get("text", "") for b in content or [] if b.get("type") == "text"]
    return "\n".join(parts)


def is_prompt(rec):
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
        return False
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list) and any(b.get("type") == "tool_result" for b in content):
        return False
    return bool(text_of(content).strip())


def summarize_transcript(path):
    """Per-hour summary of a whole transcript, as stored in the cache of state.json.

    {"journal": bool, "hours": {"YYYY-MM-DDTHH": {"first", "last", "cwd", "prompts"}}}, local hours;
    `journal` marks a session started by the journal itself.
    """
    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if any(MARKER in text_of(r["message"]["content"]) for r in records if is_prompt(r)):
        return {"journal": True, "hours": {}}
    hours = {}
    for r in records:
        if r.get("type") not in ("user", "assistant") or r.get("isSidechain") or not r.get("timestamp"):
            continue
        ts = dt.datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).astimezone()
        h = hours.setdefault(f"{ts.date().isoformat()}T{ts.hour:02d}",
                             {"first": ts, "last": ts, "cwd": None, "prompts": []})
        h["first"], h["last"] = min(h["first"], ts), max(h["last"], ts)
        h["cwd"] = r.get("cwd") or h["cwd"]
        if is_prompt(r):
            h["prompts"].append(text_of(r["message"]["content"]).strip()[:400])
    for h in hours.values():
        h["first"], h["last"] = h["first"].isoformat(), h["last"].isoformat()
    return {"journal": False, "hours": hours}


def scan_sessions(start, end, transcripts=TRANSCRIPTS, cache=None):
    """Claude Code exchanges between start and end, grouped by session then by local hour.

    `cache` (from state.json) maps a transcript's path to its size, mtime and summary: an
    unchanged transcript is not read again. It is updated in place and keeps only the
    transcripts of the period.
    """
    sessions, kept = [], {}
    cache = {} if cache is None else cache
    if not transcripts.exists():
        cache.clear()
        return sessions
    for path in sorted(transcripts.glob("*/*.jsonl")):
        try:
            stat = path.stat()
            if dt.datetime.fromtimestamp(stat.st_mtime).astimezone() < start:
                continue
            entry = cache.get(str(path))
            if not entry or [entry.get("mtime"), entry.get("size")] != [stat.st_mtime_ns, stat.st_size]:
                entry = {"mtime": stat.st_mtime_ns, "size": stat.st_size, "summary": summarize_transcript(path)}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        kept[str(path)] = entry
        hours, cwd = {}, None
        for key, h in sorted(entry["summary"]["hours"].items()):
            day, hour = dt.date.fromisoformat(key[:10]), int(key[11:])
            slot_start = dt.datetime.combine(day, dt.time(hour)).astimezone()
            if not (slot_start < end and slot_start + dt.timedelta(hours=1) > start):
                continue
            cwd = h["cwd"] or cwd
            hours[(day, hour)] = {"first": dt.datetime.fromisoformat(h["first"]),
                                  "last": dt.datetime.fromisoformat(h["last"]), "prompts": list(h["prompts"])}
        if hours:
            sessions.append({"session": path.stem, "cwd": cwd, "hours": hours})
    cache.clear()
    cache.update(kept)
    return sessions


def scan_commits(repos, start, end):
    """Commits made on this machine between start and end, read from the reflogs.

    The reflogs only record what happened in this clone: commits pulled from the
    other machine show up as pulls or fetches and are left out, like the
    journal's own sync commits.
    """
    def reflog(repo):
        if not Path(repo).is_dir():
            return ""
        try:
            return git(Path(repo), "log", "--walk-reflogs", "--all",
                       "--format=%H%x1f%h%x1f%cI%x1f%gs%x1f%s").stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    commits, seen = [], set()
    with concurrent.futures.ThreadPoolExecutor() as pool:  # one git process per repository, side by side
        logs = list(pool.map(reflog, repos))
    for repo, out in zip(repos, logs):
        for line in out.splitlines():
            full, sha, when, action, subject = line.split("\x1f", 4)
            if full in seen or not LOCAL_ACTION.match(action) or SYNC_SUBJECT.match(subject):
                continue
            ts = dt.datetime.fromisoformat(when).astimezone()
            if start <= ts < end:
                seen.add(full)
                commits.append({"repo": str(repo), "ts": ts, "sha": sha, "subject": subject})
    return commits


def local_activity(repos, start, end, transcripts=TRANSCRIPTS, state=None):
    """{(day, hour): activity} for the hours with a local trace.

    `state` (state.json) holds the caches of the transcript summaries and of the project
    names by folder; it is updated in place.
    """
    state = {} if state is None else state
    names, used = state.get("projects", {}), {}

    def project(folder):
        used[folder] = names.get(folder) or project_name(folder)
        return used[folder]

    slots = {}
    for s in scan_sessions(start, end, transcripts, state.setdefault("transcripts", {})):
        for key, h in s["hours"].items():
            slot = slots.setdefault(key, {"sessions": [], "commits": []})
            slot["sessions"].append({
                "session": s["session"], "cwd": s["cwd"],
                "project": project(s["cwd"]) if s["cwd"] else None,
                "start": h["first"].strftime("%H:%M"), "end": h["last"].strftime("%H:%M"),
                "minutes": round((h["last"] - h["first"]).total_seconds() / 60),
                "prompt_count": len(h["prompts"]), "prompts": h["prompts"],
            })
    for c in scan_commits(repos, start, end):
        slot = slots.setdefault((c["ts"].date(), c["ts"].hour), {"sessions": [], "commits": []})
        slot["commits"].append({"project": project(c["repo"]), "time": c["ts"].strftime("%H:%M"),
                                "sha": c["sha"], "message": c["subject"]})
    for slot in slots.values():
        prompts = sum(s["prompt_count"] for s in slot["sessions"])
        minutes = sum(s["minutes"] for s in slot["sessions"])
        slot["thin"] = not slot["commits"] and (prompts < THIN_PROMPTS or minutes < THIN_MINUTES)
    state["projects"] = used
    return slots


def pending_slots(cfg, transcripts=TRANSCRIPTS, state=None):
    """Finished hours with local activity but no entry from this machine."""
    journal = cfg["journal"]
    end = now().replace(minute=0, second=0, microsecond=0)
    start = end - dt.timedelta(hours=COLLECT_LOOKBACK_H)
    since = dt.date.fromisoformat(cfg.get("start", "1970-01-01"))
    slots = local_activity(watched_repos(journal), start, end, transcripts, state)
    pending = {}
    for (day, hour), slot in sorted(slots.items()):
        if day >= since and hour not in parse_entries(day_file(journal, day, cfg["machine"])):
            pending[(day, hour)] = slot
    return pending


# ---------------------------------------------------------------- gaps

def gaps(cfg):
    """Finished working slots that no machine has filled in (❓ included)."""
    current = now()
    since = dt.date.fromisoformat(cfg.get("start", "1970-01-01"))
    result = []
    for back in range(GAP_LOOKBACK_DAYS, -1, -1):
        day = current.date() - dt.timedelta(days=back)
        if day < since or day.weekday() not in WORK_DAYS:
            continue
        merged = all_entries(cfg["journal"], day)
        for hour in WORK_HOURS:
            slot_end = dt.datetime.combine(day, dt.time(hour + 1), current.tzinfo)
            if slot_end + dt.timedelta(minutes=GRACE_MIN) > current:
                continue
            found = merged.get(hour, [])
            if any(not is_unknown(f) for _, f, _ in found):
                continue
            hint = "; ".join(t.splitlines()[0] for _, f, t in found if t)
            result.append((day, hour, hint))
    return result


def detach(command):
    """Start a command that outlives this process, without a window and without its output."""
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    subprocess.Popen(command, **options)


def pull_now(journal):
    try:
        git(journal, "pull", "--rebase", "--autostash", "--quiet", timeout=PULL_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        pass


def pull(journal, force=False):
    """Pull the journal at most every PULL_EVERY_MIN minutes, in the background; force: now, waiting for it.

    The background pull's result is seen by the next `check`.
    """
    state = load_json(STATE, {})
    last = state.get("last_pull")
    if not force and last and (now() - dt.datetime.fromisoformat(last)).total_seconds() < PULL_EVERY_MIN * 60:
        return
    if force:
        pull_now(journal)
    else:
        detach([sys.executable, str(SCRIPT), "pull", "--journal", str(journal)])
    state["last_pull"] = now().isoformat()
    save_json(STATE, state)


def commit_and_push(journal, paths, message) -> bool:
    """Commit the paths and push; False when there was nothing to commit."""
    if git(journal, "add", *paths).returncode != 0:
        sys.exit("git add a échoué dans le dépôt du journal.")
    if git(journal, "diff", "--cached", "--quiet").returncode == 0:
        return False
    if git(journal, "commit", "--quiet", "-m", message).returncode != 0:
        sys.exit("git commit a échoué dans le dépôt du journal.")
    for _ in range(2):
        git(journal, "pull", "--rebase", "--autostash", "--quiet", timeout=30)
        if git(journal, "push", "--quiet", timeout=30).returncode == 0:
            return True
    sys.exit("Échec du push du journal.")


def slot_label(day, hour):
    return f"{day.isoformat()} {hour:02d}h–{hour + 1:02d}h"


# ---------------------------------------------------------------- commands

def cmd_collect(args):
    cfg = config()
    state = load_json(STATE, {})
    out = []
    pending = pending_slots(cfg, state=state)
    save_json(STATE, state)
    for (day, hour), slot in pending.items():
        path = day_file(cfg["journal"], day, cfg["machine"]).relative_to(cfg["journal"])
        out.append({"day": day.isoformat(), "hour": hour, "file": path.as_posix(), **slot})
    print(json.dumps({"machine": cfg["machine"], "slots": out}, indent=2, ensure_ascii=False))


def cmd_add(args):
    cfg = config()
    day = dt.date.fromisoformat(args.day)
    if args.category != "❓" and args.category not in CATEGORIES:
        sys.exit(f"Catégorie inconnue : {args.category} (attendu : {', '.join(CATEGORIES)} ou ❓)")
    fields = [args.category, args.project] + (["déclaré"] if args.declared else [])
    path = day_file(cfg["journal"], day, cfg["machine"])
    entries = parse_entries(path)
    entries[args.hour] = (fields, args.text.strip())
    write_entries(path, day, cfg["machine"], entries)
    print(path.relative_to(cfg["journal"]).as_posix())


def cmd_note(args):
    cfg = config()
    current = now()
    day = dt.date.fromisoformat(args.day) if args.day else current.date()
    project = args.project or project_name(os.getcwd())
    path = day_file(cfg["journal"], day, cfg["machine"])
    try:
        add_note(path, day, cfg["machine"], args.time or current.strftime("%H:%M"), project, args.text)
    except ValueError as exc:
        sys.exit(str(exc))
    print(path.relative_to(cfg["journal"]).as_posix())
    cmd_sync(args)


def cmd_sync(args):
    cfg = config()
    if commit_and_push(cfg["journal"], ["journal"], f"Journal {cfg['machine']} {now():%Y-%m-%d %H:%M}"):
        print("Journal poussé.")
    else:
        print("Rien à synchroniser.")


def cmd_register(args):
    cfg = config()
    try:
        added = register(cfg["journal"], args.folders)
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"Surveillé(s) : {', '.join(added)}" if added else "Déjà surveillé(s).")


def report(cfg, mark, transcripts=TRANSCRIPTS):
    state = load_json(STATE, {})
    asked = set(state.get("asked", []))
    to_write = pending_slots(cfg, transcripts, state)
    command = f'python3 "{SCRIPT.as_posix()}"'
    lines = []
    if to_write:
        lines.append("Heures avec de l'activité sur cette machine, pas encore notées : "
                     + ", ".join(slot_label(d, h) for d, h in to_write)
                     + f". Suis le skill /dev-journal:hourly (ou lance `{command} collect`,"
                     " rédige-les avec `add`, puis `sync`).")
    new_gaps = [(d, h, hint) for d, h, hint in gaps(cfg)
                if (d, h) not in to_write and f"{d.isoformat()}T{h:02d}" not in asked]
    if new_gaps:
        detail = "\n".join(f"- {slot_label(d, h)}" + (f" (vu : {hint})" if hint else "") for d, h, hint in new_gaps)
        lines.append("Créneaux sans trace dans le journal, sur aucune machine :\n" + detail
                     + "\nAvant de traiter la demande, demande à l'utilisateur en une phrase ce qu'il a fait sur ces"
                     f" créneaux (ou s'il était off). Note ensuite chaque réponse avec `{command} add <jour>"
                     " <heure> <catégorie> \"texte\" --project <projet> --declared` (catégorie `autre`, projet"
                     " `off` et texte « off » s'il ne travaillait pas), puis `sync`.")
        if mark:
            asked.update(f"{d.isoformat()}T{h:02d}" for d, h, _ in new_gaps)
            state["asked"] = sorted(asked)[-500:]
    save_json(STATE, state)
    return lines


def cmd_check(args):
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if MARKER in (payload.get("prompt") or ""):
        return
    cfg = config()
    pull(cfg["journal"])
    lines = report(cfg, mark=True)
    if lines:
        context = "Journal de travail (dev-journal) :\n" + "\n\n".join(lines)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": context}}, ensure_ascii=False))


def cmd_pull(args):
    pull_now(args.journal)


def cmd_status(args):
    cfg = config()
    pull(cfg["journal"], force=True)
    print("\n\n".join(report(cfg, mark=False)) or "Journal à jour.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect").set_defaults(func=cmd_collect)
    add = sub.add_parser("add")
    add.add_argument("day", help="YYYY-MM-DD")
    add.add_argument("hour", type=int, help="start hour of the slot (14 for 14h–15h)")
    add.add_argument("category", help=" | ".join(CATEGORIES) + " | ❓")
    add.add_argument("text")
    add.add_argument("--project", required=True, help="GitHub repository name, or folder name")
    add.add_argument("--declared", action="store_true", help="entry dictated by the user")
    add.set_defaults(func=cmd_add)
    note = sub.add_parser("note")
    note.add_argument("text")
    note.add_argument("--project", help="default: GitHub repository name, or name, of the current folder")
    note.add_argument("--day", help="YYYY-MM-DD, default today")
    note.add_argument("--time", help="HH:MM, default now")
    note.set_defaults(func=cmd_note)
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("sync").set_defaults(func=cmd_sync)
    bg_pull = sub.add_parser("pull")
    bg_pull.add_argument("--journal", type=Path, default=JOURNAL_REPO)
    bg_pull.set_defaults(func=cmd_pull)
    sub.add_parser("status").set_defaults(func=cmd_status)
    reg = sub.add_parser("register")
    reg.add_argument("folders", type=Path, nargs="+")
    reg.set_defaults(func=cmd_register)
    args = parser.parse_args()
    if args.cmd == "check":
        try:
            args.func(args)
        except BaseException:  # a hook must never block the conversation
            pass
        return
    args.func(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
