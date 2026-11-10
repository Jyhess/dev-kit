---
name: note
description: Add a note to the work journal (dev-journal) and push it right away. Use when the user says "note dans le journal : …", "ajoute au journal …", or runs /dev-journal:note with a text.
---

# Journal note

A note is one line the user wants to keep: why something was done, a dead end, an idea for a post. It does not count as time and never replaces an hourly entry. Format and rules: `<dev-kit>/docs/dev-journal.md`.

The script is `<dev-kit>/plugins/dev-journal/scripts/dev_journal.py`. `<dev-kit>` is the dev-kit clone, the `root` of `~/.dev-kit/config.json` (in Claude Code, the plugin's base directory `<dev-kit>/plugins/<plugin>` works too). Run:

```bash
python3 "<script path>" note "<text>" [--project <project>] [--day YYYY-MM-DD] [--time HH:MM]
```

- **Text**: The user's words as they said them, typos fixed only. Rephrase only when they ask.
- **Project**: leave it out to use the current folder's (its GitHub repository name); pass it when the user names another project.
- **Day and time**: leave them out for now; pass them when the note is about an earlier moment (« note pour hier 15h : … »).

The command writes the note and pushes the journal. Answer with one line: the note as written.
