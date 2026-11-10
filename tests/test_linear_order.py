"""Tests of plugins/tracking-linear/scripts/linear_order.py against a fake Linear API."""

import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "tracking-linear" / "scripts"))
import linear_order  # noqa: E402


class FakeLinear:
    """Answers the script's queries from dicts identifier -> sortOrder and
    identifier -> prioritySortOrder (by default, ten times the sortOrder)."""

    def __init__(self, orders, priority=None, team="team-kat", page=2, nudge=None):
        priority = priority or {i: o * 10 for i, o in orders.items()}
        self.issues = {}
        for i, o in orders.items():
            self.add(i, o, priority[i], team)
        self.page = page
        self.nudge = nudge
        self.updates = []

    def add(self, identifier, sort_order, priority_sort_order, team="team-kat"):
        self.issues[identifier] = {"id": f"id-{identifier}", "identifier": identifier, "sortOrder": sort_order,
                                   "prioritySortOrder": priority_sort_order, "team": team}

    def __call__(self, query, variables):
        if query == linear_order.ISSUE:
            issue = self.issues.get(variables["id"])
            return {"issue": issue and {**issue, "team": {"id": issue["team"], "key": "ABC"}}}
        if query == linear_order.TEAM_ISSUES:
            nodes = [{k: i[k] for k in ("id", "identifier", *linear_order.FIELDS)}
                     for i in self.issues.values() if i["team"] == variables["team"]]
            start = int(variables["after"] or 0)
            end = start + self.page
            return {"team": {"issues": {"nodes": nodes[start:end], "pageInfo": {
                "hasNextPage": end < len(nodes), "endCursor": str(end)}}}}
        if query == linear_order.UPDATE:
            issue = next(i for i in self.issues.values() if i["id"] == variables["id"])
            for field, value in variables["input"].items():
                self.assertIn(field, linear_order.FIELDS)
                if issue["identifier"] == self.nudge:
                    value -= 1000  # like Linear, which may move a value that collides with another
                issue[field] = value
            self.updates.append(issue["identifier"])
            return {"issueUpdate": {"success": True, "issue": issue}}
        raise AssertionError(f"unexpected query {query}")

    @staticmethod
    def assertIn(member, container):
        if member not in container:
            raise AssertionError(f"{member} not in {container}")

    def order(self, field="sortOrder"):
        return [i for i, _ in sorted(self.issues.items(), key=lambda kv: kv[1][field])]


class ReorderTest(unittest.TestCase):
    def reorder(self, api, *identifiers, dry_run=False):
        return linear_order.reorder(api, list(identifiers), dry_run, out=io.StringIO())

    def test_puts_issues_at_the_place_of_the_first(self):
        api = FakeLinear({"ABC-1": 1.0, "ABC-12": 2.0, "ABC-3": 3.0, "ABC-9": 4.0, "ABC-5": 5.0, "ABC-15": 6.0})
        self.reorder(api, "ABC-12", "ABC-9", "ABC-15")
        for field in linear_order.FIELDS:
            self.assertEqual(api.order(field), ["ABC-1", "ABC-12", "ABC-9", "ABC-15", "ABC-3", "ABC-5"])

    def test_each_order_field_is_planned_on_its_own(self):
        api = FakeLinear({"ABC-1": 1.0, "ABC-2": 2.0, "ABC-3": 3.0},
                         priority={"ABC-1": 30.0, "ABC-2": 20.0, "ABC-3": 10.0})
        self.reorder(api, "ABC-2", "ABC-1")
        self.assertEqual(api.order("sortOrder"), ["ABC-2", "ABC-1", "ABC-3"])
        self.assertEqual(api.order("prioritySortOrder"), ["ABC-3", "ABC-2", "ABC-1"])
        self.assertEqual(api.issues["ABC-1"]["prioritySortOrder"], 21.0)

    def test_order_changed_by_linear_is_reported(self):
        api = FakeLinear({"ABC-1": 1.0, "ABC-2": 5.0, "ABC-3": 3.0}, nudge="ABC-2")
        with self.assertRaisesRegex(linear_order.LinearError, "adjusted sortOrder"):
            self.reorder(api, "ABC-1", "ABC-2")

    def test_issues_above_the_first_come_down(self):
        api = FakeLinear({"ABC-9": 1.0, "ABC-1": 2.0, "ABC-12": 3.0, "ABC-3": 4.0})
        self.reorder(api, "ABC-12", "ABC-9")
        self.assertEqual(api.order(), ["ABC-1", "ABC-12", "ABC-9", "ABC-3"])

    def test_other_issues_keep_their_sort_order(self):
        orders = {"ABC-1": -50.5, "ABC-12": 10.0, "ABC-3": 30.0, "ABC-9": -100.0, "ABC-5": 70.0}
        api = FakeLinear(orders)
        self.reorder(api, "ABC-12", "ABC-9")
        for other in ("ABC-1", "ABC-3", "ABC-5"):
            self.assertEqual(api.issues[other]["sortOrder"], orders[other])
            self.assertEqual(api.issues[other]["prioritySortOrder"], orders[other] * 10)
        self.assertEqual(api.updates, ["ABC-9"])

    def test_first_at_the_bottom(self):
        api = FakeLinear({"ABC-9": 1.0, "ABC-1": 2.0, "ABC-12": 3.0})
        self.reorder(api, "ABC-12", "ABC-9")
        self.assertEqual(api.order(), ["ABC-1", "ABC-12", "ABC-9"])

    def test_reads_every_page_of_the_team(self):
        api = FakeLinear({f"ABC-{n}": float(n) for n in range(1, 8)}, page=2)
        self.reorder(api, "ABC-2", "ABC-7")
        self.assertEqual(api.order(), ["ABC-1", "ABC-2", "ABC-7", "ABC-3", "ABC-4", "ABC-5", "ABC-6"])

    def test_issues_of_other_teams_are_ignored(self):
        api = FakeLinear({"ABC-1": 1.0, "ABC-2": 3.0})
        api.add("OPS-1", 1.5, 15.0, team="team-ops")
        self.reorder(api, "ABC-1", "ABC-2")
        self.assertEqual(api.issues["ABC-2"]["sortOrder"], 2.0)

    def test_lower_case_identifiers(self):
        api = FakeLinear({"ABC-1": 1.0, "ABC-2": 2.0, "ABC-3": 3.0})
        self.reorder(api, "abc-3", "abc-1")
        self.assertEqual(api.order(), ["ABC-2", "ABC-3", "ABC-1"])

    def test_dry_run_changes_nothing(self):
        api = FakeLinear({"ABC-1": 1.0, "ABC-2": 2.0, "ABC-3": 3.0})
        out = io.StringIO()
        linear_order.reorder(api, ["ABC-3", "ABC-1"], True, out=out)
        self.assertEqual(api.updates, [])
        self.assertIn("ABC-1: sortOrder 1.0 -> 4.0, prioritySortOrder 10.0 -> 31.0", out.getvalue())

    def test_errors(self):
        api = FakeLinear({"ABC-1": 1.0, "ABC-2": 2.0})
        api.add("OPS-1", 1.5, 15.0, team="team-ops")
        for identifiers, message in ((["ABC-1", "ABC-404"], "not found"),
                                     (["ABC-1", "abc-1"], "twice"),
                                     (["ABC-1", "OPS-1"], "several teams")):
            with self.subTest(identifiers), self.assertRaisesRegex(linear_order.LinearError, message):
                self.reorder(api, *identifiers)
        self.assertEqual(api.updates, [])

    def test_no_room_left(self):
        api = FakeLinear({"ABC-1": 1.0, "ABC-2": 1.0 + 2.2e-16, "ABC-3": 5.0})
        with self.assertRaisesRegex(linear_order.LinearError, "no room"):
            self.reorder(api, "ABC-1", "ABC-3")


class MainTest(unittest.TestCase):
    def test_missing_key_explains_how_to_set_it(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(linear_order, "api_key", return_value=None), \
                mock.patch("sys.stderr", err):
            self.assertEqual(linear_order.main(["reorder", "ABC-1", "ABC-2"]), 2)
        for expected in ("linear.app/settings/account/security", "PowerShell", "zsh", "LINEAR_API_KEY"):
            self.assertIn(expected, err.getvalue())

    def test_key_from_the_environment(self):
        with mock.patch.dict(os.environ, {"LINEAR_API_KEY": "lin_api_test"}):
            self.assertEqual(linear_order.api_key(), "lin_api_test")

    def test_api_errors_are_reported(self):
        def post(query, variables):
            raise linear_order.LinearError("Linear API: Authentication required")
        err = io.StringIO()
        with mock.patch.object(linear_order, "api_key", return_value="k"), \
                mock.patch.object(linear_order, "client", return_value=post), mock.patch("sys.stderr", err):
            self.assertEqual(linear_order.main(["reorder", "ABC-1", "ABC-2"]), 1)
        self.assertIn("Authentication required", err.getvalue())

    def test_client_sends_the_key_and_reads_graphql_errors(self):
        sent = {}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def urlopen(request, timeout):
            sent["auth"] = request.get_header("Authorization")
            return Response(b'{"errors": [{"message": "Entity not found"}]}')

        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaisesRegex(linear_order.LinearError, "Entity not found"):
                linear_order.client("lin_api_test")(linear_order.ISSUE, {"id": "ABC-1"})
        self.assertEqual(sent["auth"], "lin_api_test")


if __name__ == "__main__":
    unittest.main()
