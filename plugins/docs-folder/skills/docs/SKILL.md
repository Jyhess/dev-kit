---
name: docs
description: Conventions of a project documented in a `docs/` folder of its repository, in English — page layout, links, and the project's update table `docs/update-table.md` (which change requires which file to be updated). Use before creating, moving or renaming a page of `docs/`, and before committing a change to the code or the docs.
---

# Documentation in `docs/`

The documentation lives in the `docs/` folder of the project's repository, next to the code, in English unless the project's `AGENTS.md` says otherwise. There is no wiki.

## Project settings

The documentation's language is in the project's `AGENTS.md`, which also points to the **update table**, `docs/update-table.md`: it maps each kind of change to the files to update, for example:

| Change | Files to update |
|---|---|
| Change of the deploy steps | `skills/deploy/SKILL.md`, `docs/deploy.md` |
| New decision on the scope | `docs/scoping.md` |

It lists only the links that the index of `docs/` does not make obvious (a skill, a config or a script to keep in step with a page); a change whose page the index names needs no line. When the table is missing, propose one to the user from the existing files; once they agree, write it and add to the Documentation section of `AGENTS.md`: "Before committing, check `docs/update-table.md`." The table never goes into `AGENTS.md`, which stays small.

## Pages

- `README.md` at the repository's root: what the project is, the few commands to install and run it, and links to the pages of `docs/`; everything else goes in `docs/`.
- One page per topic in `docs/`, with lower-case hyphenated names (`scoping.md`, `architecture.md`). A sub-folder only when a topic needs several pages.
- Each page starts with a `# …` title. No front matter.
- Diagrams are ` ```mermaid ` blocks.
- Links are relative to the current file, with the `.md` extension; never absolute links starting with `/`.
- Documentation describes the why and the what; tasks and their progress stay in the tracker (GitHub issues or Linear), not in `docs/`.

## Keep it up to date

1. Before committing a change, find its kind in the update table, or its page in the index of `docs/`, and update the files in the same commit.
2. When a change has no page and no line of the table, say so to the user and propose a page or a line.
3. After moving or renaming a page (`git mv`), update the links that targeted its old path.
