---
name: wiki-github
description: Conventions of a project wiki kept as a GitHub repository and read in GitHub's interface — one README.md per folder, file names, page content, relative links, Mermaid, index page — and the link checker. Use before creating, moving or renaming a page or a folder of the wiki, or changing links between pages.
---

# Wiki in a GitHub repository

The wiki is an ordinary GitHub repository, read in GitHub's interface. Apply these rules to every page created, moved or renamed.

## Project settings

Read them in the project's `AGENTS.md`: the wiki repository and its local folder, the wiki's language (French unless stated otherwise), the name of the index page (`Index.md` by default). When one is missing, ask the user and propose to add it to `AGENTS.md`.

Write pages in the wiki's language; the labels below are given in French and English.

## Folders

The home page of a folder `X/` is **`X/README.md`**: GitHub shows it under the folder's file list. The wiki's home page is the root `README.md`, and the index page lists every page.

```
README.md              ← wiki home page
Index.md               ← list of every page
POC/
  README.md            ← home page of the folder
  Gameplay-loop.md
  Steps/
    README.md
    Step-01-….md
```

Every folder has its `README.md`. A page without sub-pages stays a plain file: no folder next to it.

## File names

- Spaces become hyphens: `Damage-handling.md`. Accents are kept.
- No `&` nor ` — ` in names: write `and` and `-`.
- Ordered pages take a two-digit prefix (`Step-01-…`, `Step-10-…`): GitHub sorts files alphabetically.

## Page content

- No front matter (`---` at the top): GitHub would show it as a table.
- The page starts with a **`# …` title**: GitHub shows only the file name in the navigation.
- Then a line `Document parent : [Parent](relative-path.md)` (`Parent document: …` in English), followed if needed by `Documents associés : …` (`Related documents: …`).
- Tracking information (date, status) goes in the body, under the title: `> Date : 2026-10-14 — Statut : Hypothèse à valider`.
- Diagrams are ` ```mermaid ` blocks, which GitHub renders.

## Links

- Never Obsidian links `[[…]]`, nor absolute links starting with `/` (GitHub would point them outside the repository).
- Links **relative to the current file, with the `.md` extension**: from `POC/Gameplay-loop.md`, write `[Damage handling](Damage-handling.md)` or `[Index](../Index.md)`.
- To link a folder's home page, target its `README.md`: `[POC](POC/README.md)`.
- Anchors follow the heading in lower case, spaces replaced by hyphens: `[Schedule](#schedule-and-decision-points)`.
- Add every new page to the index page, and to the `README.md` of its folder.
- Move a file with `git mv`, then update the links that targeted its old path.

## Check

After any change of structure, run the checker from the wiki's root (the script is `<dev-kit>/plugins/docs-wiki-github/scripts/check_md_links.py`; `<dev-kit>` is the dev-kit clone, the `root` of `~/.dev-kit/config.json` (in Claude Code, the plugin's base directory `<dev-kit>/plugins/<plugin>` works too)):

```bash
python3 "<dev-kit>/plugins/docs-wiki-github/scripts/check_md_links.py" <wiki dir>
```

It reports broken relative links, absolute links, Obsidian links and folders without a `README.md`, outside code blocks and hidden folders. Fix every line it prints; it ends with `0 problem(s)`.
