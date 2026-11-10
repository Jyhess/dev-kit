#!/usr/bin/env python3
"""Reorder Linear issues in the manual order, which the Linear MCP cannot do.

    python3 linear_order.py reorder ABC-12 ABC-9 ABC-15 [--dry-run]

Puts the issues in this order, at the place of the first of them: ABC-12 keeps
its place, ABC-9 and ABC-15 come right after it. Every other issue of the team
keeps its place, in every view sorted by manual order. The issues must belong
to the same team.

Linear keeps the manual order in two fields, ascending from the top:
`sortOrder`, and `prioritySortOrder` used by views ordered or grouped by
priority. For each field, the script reads the values of every issue of the
team, gives the moved issues values between the first one and the next issue
of the team, and sets them with the GraphQL mutation `issueUpdate`. Linear may
nudge a value that collides with another; the script then checks that the
values it stored still give the order asked for.

The personal API key is read from the `LINEAR_API_KEY` environment variable
(on Windows, also from the user environment, so that a key set after Claude
Code started is found). Nothing is stored in a repository.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.linear.app/graphql"
PAGE = 250

KEY_HELP = """LINEAR_API_KEY is not set.

Create a personal API key in Linear: Settings > Account > Security & access >
Personal API keys (https://linear.app/settings/account/security), then set it
without writing it in a repository or in your shell history:

  PowerShell (Windows):
    [Environment]::SetEnvironmentVariable('LINEAR_API_KEY', (Read-Host 'Linear API key' -MaskInput), 'User')

  zsh (macOS), then open a new terminal:
    read -s 'k?Linear API key: ' && echo "export LINEAR_API_KEY='$k'" >> ~/.zshrc && unset k
"""

# Linear keeps two manual orders: `sortOrder`, and `prioritySortOrder` used by
# views ordered or grouped by priority (the default Backlog view).
FIELDS = ("sortOrder", "prioritySortOrder")

ISSUE = """query($id: String!) {
  issue(id: $id) { id identifier sortOrder prioritySortOrder team { id key } }
}"""

TEAM_ISSUES = """query($team: String!, $after: String) {
  team(id: $team) {
    issues(first: %d, after: $after) {
      nodes { id identifier sortOrder prioritySortOrder }
      pageInfo { hasNextPage endCursor }
    }
  }
}""" % PAGE

UPDATE = """mutation($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { identifier sortOrder prioritySortOrder }
  }
}"""


class LinearError(Exception):
    pass


def api_key() -> str | None:
    """The key from the environment, or on Windows from the user environment."""
    key = os.environ.get("LINEAR_API_KEY")
    if key or sys.platform != "win32":
        return key or None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env:
            return winreg.QueryValueEx(env, "LINEAR_API_KEY")[0] or None
    except OSError:
        return None


def client(key: str):
    """A function that sends a GraphQL query to Linear and returns its data."""
    def post(query: str, variables: dict) -> dict:
        body = json.dumps({"query": query, "variables": variables}).encode()
        request = urllib.request.Request(API, data=body, headers={
            "Content-Type": "application/json", "Authorization": key,
            "User-Agent": "dev-kit-linear-order"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            try:
                payload = json.load(error)
            except ValueError:
                raise LinearError(f"Linear API: HTTP {error.code}") from None
        except urllib.error.URLError as error:
            raise LinearError(f"Linear API unreachable: {error.reason}") from None
        if payload.get("errors"):
            raise LinearError("Linear API: " + "; ".join(e.get("message", "?") for e in payload["errors"]))
        return payload["data"]
    return post


def fetch_issue(post, identifier: str) -> dict:
    issue = post(ISSUE, {"id": identifier}).get("issue")
    if not issue:
        raise LinearError(f"{identifier}: issue not found")
    return issue


def fetch_team_issues(post, team_id: str) -> list[dict]:
    issues, after = [], None
    while True:
        page = post(TEAM_ISSUES, {"team": team_id, "after": after})["team"]["issues"]
        issues += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return issues
        after = page["pageInfo"]["endCursor"]


def plan(moved: list[dict], others: list[dict], field: str) -> list[float]:
    """New values of the field for the moved issues: the first keeps its value,
    the others are spread between it and the next of the other issues."""
    start = moved[0][field]
    above = [o[field] for o in others if o[field] > start]
    step = (min(above) - start) / len(moved) if above else 1.0
    values = [start + i * step for i in range(len(moved))]
    if len(set(values)) != len(values):
        raise LinearError(f"no room left in {field} after {moved[0]['identifier']}")
    return values


def reorder(post, identifiers: list[str], dry_run: bool = False, out=sys.stdout) -> dict[str, list[float]]:
    wanted = [i.upper() for i in identifiers]
    if len(set(wanted)) != len(wanted):
        raise LinearError("an issue is given twice")
    moved = [fetch_issue(post, i) for i in wanted]
    teams = {m["team"]["id"] for m in moved}
    if len(teams) > 1:
        raise LinearError("the issues belong to several teams")
    ids = {m["id"] for m in moved}
    others = [i for i in fetch_team_issues(post, teams.pop()) if i["id"] not in ids]
    planned = {field: plan(moved, others, field) for field in FIELDS}
    stored = {field: [] for field in FIELDS}
    for n, issue in enumerate(moved):
        changes = {f: planned[f][n] for f in FIELDS if planned[f][n] != issue[f]}
        result = issue
        if changes and not dry_run:
            update = post(UPDATE, {"id": issue["id"], "input": changes})["issueUpdate"]
            if not update["success"]:
                raise LinearError(f"{issue['identifier']}: update refused")
            result = update["issue"]
        for field in FIELDS:
            stored[field].append(planned[field][n] if dry_run else result[field])
        detail = ", ".join(f"{f} {issue[f]!r} -> {planned[f][n]!r}" for f in changes) or "unchanged"
        print(f"{issue['identifier']}: {detail}", file=out)
    if dry_run:
        print("dry run: nothing changed in Linear", file=out)
    for field, values in stored.items():
        if values != sorted(set(values)):
            raise LinearError(f"Linear adjusted {field} and the order is not the one asked for; "
                              f"check it in Linear: {dict(zip(wanted, values))}")
    return stored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("reorder", help="put issues in this order, at the place of the first")
    command.add_argument("issues", nargs="+", metavar="ISSUE", help="issue identifiers, e.g. ABC-12")
    command.add_argument("--dry-run", action="store_true", help="print the new values without changing them")
    args = parser.parse_args(argv)
    if len(args.issues) < 2:
        parser.error("give at least two issues")
    key = api_key()
    if not key:
        print(KEY_HELP, file=sys.stderr)
        return 2
    try:
        reorder(client(key), args.issues, args.dry_run)
    except LinearError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
