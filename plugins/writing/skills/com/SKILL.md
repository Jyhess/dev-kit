---
name: com
description: Draft the user's professional communications (LinkedIn post, announcement, professional mail, project page) in their own voice, and tell whether a text was reworked by AI. Use when the user asks to write, rewrite or review a "com", a post, an announcement or a professional message, or asks "est-ce que ce texte a été retravaillé par l'IA ?". Not for mails to friends, which they write themselves.
---

# Professional communications in the user's voice

The communications themselves are in French unless they ask for another language. They sign with the first name `voice.md` gives.

Their voice is described in `voice.md`: traits, phrases they never write, and anonymized excerpts of their own prose. Read it before writing anything. It quotes their mails, so it lives in their private work journal repository, the dev-journal clone next to the dev-kit clone that holds this skill (`<dev folder>/dev-journal/voice.md`, `<dev folder>` being the parent of `<dev-kit>`; `<dev-kit>` is the dev-kit clone, the `root` of `~/.dev-kit/config.json` (in Claude Code, the plugin's base directory `<dev-kit>/plugins/<plugin>` works too)).

When `voice.md` is missing, write nothing: tell the user the path where it is expected, that `python3 scripts/install.py` in dev-kit clones dev-journal, and that [voice.example.md](voice.example.md) shows its layout.

## Write a communication

1. **Gather.** Ask in one round what is missing: the channel (LinkedIn, mail, site), the readers, what the user wants to say. Take their notes or findings as they come; they are the content. Never add a fact, figure, name or opinion they did not give; ask for it instead.
2. **Draft.** Write the text from their notes, following the traits of `voice.md`: start with the subject, short factual sentences, one concrete image rather than a general statement, their opinion stated plainly. Keep their own sentences when they work; reorder and correct them rather than replace them.
3. **Refine the voice.** In Claude Code, run the `humanizer:humanizer` skill on the draft, giving it excerpts of `voice.md` as the writing sample and the "Never writes" list as extra patterns. In Codex, make a second pass against `voice.md`: replace generic phrasing with the user's direct style, keep their concrete details, and remove patterns from "Never writes" without adding facts or changing their intent.
4. **Check.** Go through the "Never writes" list and the typography of `voice.md` once more, then fix spelling and grammar: their mails have typos, a published text must not.
5. **Show.** Give them the final text, then in a few lines what changed in their notes and why. Never publish, post or send anything: they do it themselves.

## Tell whether a text was reworked by AI

Compare the text with `voice.md`, part by part. Give a verdict per part (the user, AI, unsure) with the phrases that show it, and say that no detector can prove it either way. Signs that a part is theirs: the traits of `voice.md`, typos and editing slips. Signs of AI: the "Never writes" list, the humanizer's patterns, curly apostrophes (’) in a text otherwise typed by hand.

## Keep the voice profile up to date

When the user gives a text they wrote themselves and like, propose to add an excerpt to `voice.md`, anonymized as that file says, and commit it in the dev-journal clone (its hourly sync pushes it). Never add a text that was drafted or reworked by AI, even partly: the profile would then learn the AI's style instead of their.
