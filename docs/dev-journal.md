# Work journal (dev-journal)

An hour-by-hour work journal, filled in by every machine (Mac and Windows). It serves two purposes: knowing where time goes (dev, cadrage, organisation, marketing…) per project, and keeping raw material for communication.

- **Code**: the `dev-journal` plugin of dev-kit (`plugins/dev-journal/`): `scripts/dev_journal.py`, the `UserPromptSubmit` hook and the `/dev-journal:hourly` and `/dev-journal:note` skills.
- **Data**: a private Git repository of the user's own, cloned as `dev-journal` next to dev-kit in the dev folder (`~/dvp` on the Mac, `~/dev` on Windows). It holds `journal/`, `repos.json`, `voice.md`, the user's voice profile read by `writing:com` (kept private because it quotes their mails), and `private-words`, the words every project's pre-push refuses (`plugins/core/scripts/private_words.py`; one per line, `#` starts a comment), except in the project a word names: the folder of its main clone or its `origin` repository, without case; a push to a private GitHub repository is not checked.
- **Local configuration**: `~/.dev-journal/config.json` (`machine`: `mac` or `windows`, the suffix of the journal files; `start`: no gap is claimed before this date; `journal_url`: the journal repository, used to clone it) and `state.json` (slots already asked, last pull, and a cache of each recent transcript's per-hour summary, keyed by path, size and mtime, and of the project names by folder).

## How it works

1. **Every working hour**, a scheduled task on each machine runs `/dev-journal:hourly`. It reads the local activity (Claude Code sessions, commits of the watched repositories), writes one entry per hour in the machine's file, then pushes the journal. It also catches up the hours missed (machine asleep, work outside working hours) over the last 72 hours. When the material is too thin (fewer than 3 exchanges or less than 10 minutes, no commit), the entry is marked `❓`.
2. **At each message sent to Claude Code**, the hook (`dev_journal.py check`) starts a background pull of the journal at most every 10 minutes (its result is seen by the next message) and looks for the working slots (`WORK_DAYS` and `WORK_HOURS` of `dev_journal.py`, Monday–Friday 9h–19h by default) that no machine has filled in. Claude then asks the user what they did in these slots, once per slot.

Work outside working hours is not claimed. Claude sessions in those hours are logged automatically; for the rest, the user mentions it and Claude adds it.

Sessions whose prompt contains `[dev-journal]` (the scheduled task) are not activity, and the hook stays silent for them.

### Local activity only

- **Sessions**: the transcripts of `~/.claude/projects/` of this machine.
- **Commits**: read from the reflogs of the watched repositories (`git log --walk-reflogs --all`), keeping the actions that create a commit here (`commit`, `commit (amend)`, `commit (merge)`, `cherry-pick`, `revert`, a local `merge`). Commits pulled from the other machine appear in the reflogs as pulls, fetches or rebases and are left out. The journal's own sync commits (`Journal <machine> <date>`) are left out too.

### Projects

The project of a session or a commit is the name of its folder's GitHub repository (the `origin` remote), or the folder's name when there is none: `dev-kit`, `stellar`, `atelier`… Work on the journal itself is `dev-kit`. A slot shared by several projects takes the one with the most activity.

### Watched repositories

`repos.json` in dev-journal lists the repositories whose commits are read, by their path relative to the dev folder, so that one list serves both machines. Names are compared without case (Windows does not care, the Mac does: keep the Mac's case). `/core:project-init` adds a new project and pushes the list; by hand:

```bash
python3 plugins/dev-journal/scripts/dev_journal.py register <project folder>
```

## Layout

```
dev-journal/
  repos.json
  journal/
    2026-S45/
      2026-11-02-mac.md
      2026-11-02-windows.md
```

Each machine writes only in its own files: no Git conflict between machines. A slot counts as filled in as soon as one machine has an entry other than `❓`.

## Entry format

```markdown
## 2026-11-02 · windows

### 14:00–15:00 · dev · atelier
Branchement de l'import CSV sur le modèle de commandes (ABC-21).
Impasse sur les fichiers en Latin-1, contournée en détectant l'encodage.
Angle com : « ce que j'ai appris en lisant des exports CSV ».

### 15:00–16:00 · ❓ · atelier
Session de 4 min sur ABC-18, trop courte pour conclure.

### 16:00–17:00 · marketing · atelier · déclaré
Rédaction d'un post LinkedIn sur le POC.
```

- Heading: `### HH:00–HH:00 · <category> · <project>[ · déclaré]`.
- Categories: `dev`, `cadrage`, `organisation`, `marketing`, `admin`, `autre`. When the user was not working: category `autre`, project `off`, text « off ».
- `déclaré`: an entry dictated by the user, not deduced from traces.
- Text, in French: 1 to 4 lines. What was done, what was decided or learnt, and a line « Angle com : … » when a topic lends itself to it. Nothing invented.

## Notes

The user keeps what the traces do not say (why, a dead end, an idea for a post) as notes: « note dans le journal : … » or `/dev-journal:note …`. They go in a `## Notes` section at the bottom of the machine's day file, one line each, sorted by time, and the journal is pushed right away:

```markdown
## Notes

- 14:32 · atelier · Les exports CSV mettent les dates en jj/mm/aaaa, pas en ISO.
```

- Project: the current folder's by default; time: now, or `--day` / `--time` for an earlier moment. The text is kept as said, on one line.
- A note is not time spent: it never fills a slot. `add` keeps the notes, and `collect` does not read them.

## Commands

```bash
python3 plugins/dev-journal/scripts/dev_journal.py collect     # local activity of the hours not logged yet (JSON)
python3 plugins/dev-journal/scripts/dev_journal.py add 2026-11-02 14 dev "texte" --project atelier [--declared]
python3 plugins/dev-journal/scripts/dev_journal.py note "texte" [--project atelier] [--day 2026-11-02] [--time 14:32]   # + push
python3 plugins/dev-journal/scripts/dev_journal.py sync        # commit + push
python3 plugins/dev-journal/scripts/dev_journal.py status      # gaps and hours to write
python3 plugins/dev-journal/scripts/dev_journal.py register <folder>
```

## Install on a machine

1. Create a private Git repository for the journal, with a first commit (a README), once for all your machines.
2. `git pull` dev-kit, then `python3 scripts/install.py --journal-url <URL of the journal repository>`. It installs the plugin (which brings the hook), clones the journal as `dev-journal` next to dev-kit if missing, and writes `~/.dev-journal/config.json` with the URL; later runs need no option. An existing `dev-journal` clone is used as it is. Without a URL and without a clone, the installer skips the journal with a `note:`, and the hook stays silent.
3. In the Claude desktop app, create the scheduled task « Journal — entrée horaire »: prompt `[dev-journal] Lance le skill /dev-journal:hourly et suis-le, sans poser de question.`, schedule `5 10-19 * * 1-5` (5 minutes past each hour, 10:05 to 19:05, Monday to Friday), no notification. `install.py` prints a `note:` while it is missing.
4. Check: `python3 plugins/dev-journal/scripts/dev_journal.py status` shows the gaps and the hours to write.
