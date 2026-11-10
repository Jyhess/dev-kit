# ${name} — shared project instructions

${purpose}

Audience: ${audience}. Stack: ${stack}.

## Communication and languages

- Talk to the user in ${chat}.
- Documentation and skills are in ${docs}; code, comments and commit messages are in ${code}.${wiki_line}

## Shared rules

- Shared rules: `~/.dev-kit/rules/shared-rules.md`; Claude Code gets them from the core plugin, other agents read the file at session start; a section of this file that contradicts them wins.

## Commands

${commands}

## Documentation and tracking

- ${docs_where}
- ${tracking_where}
- Time spent is recorded in the work journal (plugin `dev-journal`).

## Vocabulary

- The domain glossary is at `${glossary}`: read it before a task involving domain concepts, and follow its definitions and forbidden synonyms.

## Design

- Before designing or changing code, read `${principles}` (errors, robustness by design).

## Architecture

${architecture}
- Changing these components or their checks is an architecture change, approved by the user beforehand.

## Verification

${verification}
