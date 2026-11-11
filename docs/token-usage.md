# Token usage

Where Claude Code tokens go, and what dev-kit does about it. Measured with:

```
python3 scripts/token_usage.py --since 2026-11-01          # print the report
python3 scripts/token_usage.py --since 2026-11-01 --save   # write it to history/token-usage/<today>.md
```

The script reads `~/.claude/projects/*/*.jsonl` (worktrees included) and prints aggregates only, never prompt text. `--json` gives one row per session. A machine's figures stay out of the repository: `--save` writes them to the git-ignored `history/` folder of the main clone, one dated page per analysis, to compare the effect of new rules.

**Quota units** weight each token type like the API price list: input 1, output 5, cache read 0.1, cache write 1.25 (5-minute cache) or 2 (1-hour cache). Plan limits are not published, so the units estimate what drains them; they are not the plan's own count.

## Findings

From a first analysis of four days of daily use, with Opus at medium effort.

- **Context size drives the cost.** Each call re-sends the whole conversation; the cache makes it cheaper but not free. Cache reads and writes are about 85% of the quota units, output about 14%, uncached input nothing. Calls past 200k tokens of context weigh about half of the total, and a long session resumed after the 1-hour cache expired pays a full cache rebuild.
- **The prefix a session loads before its first answer is large** (about 74k tokens): it is written to the cache once and read again at every call, about a third of the total. Each 1k tokens removed from it saves about 0.5%. Tool definitions are the biggest part (about 32k: `Artifact` 9.4k, the built-in browser 5.6k, `PowerShell` and `Bash` 3.1k…), then the system prompt, the skills listing and the deferred tools listing of the connectors.
- **Tool results grow the context**: shell commands reading whole files and MCP tools returning whole objects make most of them; their cost shows up in the long-session figures.
- **Instruction files weigh little** (0.5k–2.5k tokens): halving them saves under 0.5%. Their size budget is worth it for readability, not for tokens.
- **The journal costs little**: a few % for the hourly scheduled tasks and the skill run inside interactive sessions.

## Leads

| action | estimated gain |
|---|---|
| Keep sessions short: one ticket per session; past a context threshold, or when resuming after the cache expired, hand over to a new session with a short summary (`plugins/core/scripts/context_size.py`). | 10–15% |
| Remove unused tools from the prefix with `permissions.deny`: `project-init` writes `DENIED_TOOLS` of `init_project.py` (`Artifact`, built-in browser, `Workflow`, `ScheduleWakeup`…) into the project's settings, and removes `REQUIRED_TOOLS` (`visualize`, for the `ask` form) from them, and the claude.ai connectors of the local `~/.dev-kit/config.json` into its `settings.local.json`; a project keeps what it uses with `keep_tools`. See below. | ~11% (~22k tokens) |
| Disable the `anthropic-skills` plugin (docx, pptx, xlsx, pdf…) in coding projects: `"enabledPlugins": {"anthropic-skills@inline": false}` in the project's `.claude/settings.json` (the desktop app loads it as an `@inline` plugin); `project-init` writes it. | ~1% (1.7k tokens of skills listing per session) |
| Read file ranges instead of whole files and trim command outputs (`head`, `--stat`); do not fetch an object an MCP tool just returned. | a few % (part of the long-context cost) |

### Denied tools leave the prompt

Checked by capturing the API request of the bundled CLI (2.1.317) against a local fake server, with and without `--settings` deny rules:

- a bare tool name (`Artifact`) or an MCP server prefix (`mcp__Claude_Browser`, `mcp__<connector id>`) removes the definitions from the request, and from the deferred tools listing: `Artifact` alone takes 9.4k tokens off; a rule with a pattern (`Bash(rm:*)`) keeps the definition;
- the instructions of a fully denied MCP server stay in the prompt;
- never deny every MCP tool: with nothing left to defer, tool search turns off and all deferred tools are sent in full (the app's `mcp__ccd_*` tools always remain);
- connector prefixes (`mcp__<id>`) belong to the claude.ai account: read them in a session transcript and write them in `~/.dev-kit/config.json` as `{"connectors": {"<name>": "mcp__<id>"}}`.

Not worth acting on: the journal, effort (already medium), Markdown budgets for cost.

The findings come from one machine and a few days. Rerun the script with `--save` after a change to measure it.
