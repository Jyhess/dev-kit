---
name: hourly
description: Write the work journal entries of the finished hours from this machine's local activity, then push the journal. Run by the hourly scheduled task of each machine, whose prompt starts with [dev-journal]; also when the user asks to fill in the journal.
---

# Hourly journal entries

You usually run unattended, from a scheduled task: ask no question. The journal format and its rules are in `<dev-kit>/docs/dev-journal.md`; read it when in doubt.

The script is `<dev-kit>/plugins/dev-journal/scripts/dev_journal.py`, called `journal` below. Run it as `python3 "<script path>" …`. `<dev-kit>` is the dev-kit clone, the `root` of `~/.dev-kit/config.json` (in Claude Code, the plugin's base directory `<dev-kit>/plugins/<plugin>` works too).

1. `journal collect` returns, as JSON, the finished one-hour slots that have activity on this machine and no entry yet: Claude Code sessions (with the user's requests and the session's `project`) and the commits made on this machine (with their `project`). Codex session transcripts are not collected: in Codex, the entries come from commits only. Commits pulled from the other machine and the journal's sync commits are already left out. If `slots` is empty, stop there.
2. For each slot, write one entry:
   `journal add <day> <hour> <category> "<text>" --project <project>`
   - **Category**, the one that dominates the hour: `dev` (code), `cadrage` (preparing, specifying, splitting, being challenged), `organisation` (tracking, wiki, tooling, planning), `marketing` (communication, social networks, content), `admin`, `autre`.
   - **Project**: the `project` of the sessions and commits of the slot (the GitHub repository's name, or the folder's name). When several projects share the hour, take the one with the most activity. Work on the journal itself is `dev-kit`.
   - **Thin slot** (`"thin": true`): category `❓`, and one line on what was seen (for example « Session de 4 min sur ABC-18, trop courte pour conclure »). The user will complete it.
   - **Text**: 1 to 4 lines in French. What was done, what was decided or learnt (paths tried, dead ends), with the ticket identifiers cited (ABC-…, #12). Add a line « Angle com : … » only when a topic would really make a good post. Invent nothing: if the trace does not say why, do not guess. Summarise the requests, do not copy them.
3. `journal sync` commits and pushes the journal.

End with one line: the slots written, or « rien à noter ».
