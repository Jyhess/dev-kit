---
name: ask
description: Ask the user questions with choices in one inline form — 1 to 10 questions visible together, 2 to 8 options each (single or multiple choice, optional descriptions), a free answer per question, Skip and Send — whose answers come back in one message. Use for every question to the user that has choices, alone or several at once (clarification rounds, setup questions, decisions before acting).
---

# Ask questions in one form

Every question to the user that has choices goes in this form, even a single one. An open question that needs a long written answer (a goal statement, an example) stays in chat text.

## Build the form

1. Write the questions as JSON:

```json
{
  "lang": "fr",
  "intro": "Optional sentence shown above the questions.",
  "questions": [
    {
      "id": "storage",
      "title": "Where are the drafts kept?",
      "multi": false,
      "required": true,
      "freeTextPlaceholder": "Another place…",
      "options": [
        {"label": "Local files (Recommandé)", "description": "No account needed.\nLost with the machine.", "icon": "ti-device-laptop"},
        {"label": "Private Git repository"}
      ]
    }
  ]
}
```

   - `lang`: the language of the project's communication with the user, `fr` (default) or `en`.
   - `multi`: `true` when several options can hold together; `required`: `false` for a question that may stay unanswered.
   - `icon`: optional, a Tabler outline icon name (`ti-lock`, `ti-brand-git`), when an icon helps tell the options apart.
2. Validate and render it, with the JSON on stdin (`<dev-kit>` is the dev-kit clone, the `root` of `~/.dev-kit/config.json`; in Claude Code, the plugin's base directory `<dev-kit>/plugins/core` works too):

```sh
python3 "<dev-kit>/plugins/core/scripts/ask_form.py" < questions.json
```

   On errors (stderr, exit 1), fix the JSON and run it again.
3. Pass its whole stdout, unchanged, as `widget_code` to `show_widget`; before the form, give in one or two lines the context the options do not carry. Then end the turn: the answers arrive as the user's next message, one line per question (`<n>. <title> : <choices> ; « <free answer> »`), or a line saying the questions were skipped.

## Write good questions

- **One decision per question**; a question that depends on another one's answer waits for the next round.
- **Mutually exclusive options** for a single choice: each option a whole answer, none containing another, no "both" option (make it `multi` instead). Cover the realistic answers; the free answer catches the rest, so no "Other" option.
- **The recommended option first**, its label ending in "(Recommandé)" (or "(Recommended)"), its reason in its description; recommended options start selected, at most one per single-choice question.
- **Labels short** (one to five words); the **description** carries what the label cannot: the consequence, the cost, the trade-off. Use descriptions, even of several lines, when the options differ by their effects rather than by their names; leave them out when the labels speak for themselves: the form then shows compact chips.
- **Links** (tickets, PRs, pages): Markdown links `[title](https://…)` in `intro` and `title`, opened in a new tab and kept in the answers; labels and descriptions are plain text.
- **At most 10 questions** per form: beyond, split into rounds, the most blocking first.

## Without the form

Without `show_widget` (a terminal session), use the agent's interactive question tool: at most four questions and four options per call, so split into consecutive calls and merge the options beyond four into the free answer. Without either, show concise numbered options in chat and wait for the reply.

Known limitations: no timeout, the form does not block (the answers are the next message); Send only fills the chat input and the user presses Enter, since the app's widgets cannot send a message themselves; the rendering in the app, including the action bar kept visible on a long form, is checked by hand; without node, the tests skip the JavaScript logic.
