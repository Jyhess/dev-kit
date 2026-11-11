"""Tests of the question form (plugins/core/scripts/ask_form.py and its ask_form.html logic)."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "core" / "scripts"))
import ask_form  # noqa: E402
from ask_form import Error, Kind  # noqa: E402

SCRIPT = ROOT / "plugins" / "core" / "scripts" / "ask_form.py"


def question(qid="q", **extra):
    return {"id": qid, "title": "Which?", "options": [{"label": "A"}, {"label": "B"}], **extra}


def form(count=1, **extra):
    return {"questions": [question(f"q{i}") for i in range(count)], **extra}


class ValidateTest(unittest.TestCase):
    def test_question_counts(self):
        self.assertEqual(ask_form.validate(form(0)), [Error(Kind.TOO_FEW_QUESTIONS, "questions")])
        self.assertEqual(ask_form.validate(form(1)), [])
        self.assertEqual(ask_form.validate(form(ask_form.MAX_QUESTIONS)), [])
        self.assertEqual(ask_form.validate(form(ask_form.MAX_QUESTIONS + 1)),
                         [Error(Kind.TOO_MANY_QUESTIONS, "questions")])

    def test_options_missing_too_few_too_many(self):
        q = question()
        del q["options"]
        self.assertEqual(ask_form.validate({"questions": [q]}), [Error(Kind.MISSING, "questions[0].options")])
        few = question(options=[{"label": "A"}])
        many = question(options=[{"label": str(i)} for i in range(ask_form.MAX_OPTIONS + 1)])
        self.assertEqual(ask_form.validate({"questions": [few]}), [Error(Kind.TOO_FEW_OPTIONS, "questions[0].options")])
        self.assertEqual(ask_form.validate({"questions": [many]}),
                         [Error(Kind.TOO_MANY_OPTIONS, "questions[0].options")])
        full = question(options=[{"label": str(i), "description": "Line 1\nLine 2"} for i in range(ask_form.MAX_OPTIONS)])
        self.assertEqual(ask_form.validate({"questions": [full]}), [])

    def test_fields(self):
        bad = {"id": "", "title": 3, "multi": "yes", "required": 1, "freeTextPlaceholder": 2, "extra": True,
               "options": [{"label": "A", "detail": "x"}, {"label": "A"}, "C"]}
        self.assertEqual(ask_form.validate({"questions": [bad], "lang": "de", "intro": 1, "other": 0}), [
            Error(Kind.UNKNOWN_KEY, "form.other"), Error(Kind.WRONG_TYPE, "intro"), Error(Kind.UNKNOWN_LANG, "lang"),
            Error(Kind.UNKNOWN_KEY, "questions[0].extra"), Error(Kind.EMPTY, "questions[0].id"),
            Error(Kind.WRONG_TYPE, "questions[0].title"), Error(Kind.WRONG_TYPE, "questions[0].freeTextPlaceholder"),
            Error(Kind.WRONG_TYPE, "questions[0].multi"), Error(Kind.WRONG_TYPE, "questions[0].required"),
            Error(Kind.UNKNOWN_KEY, "questions[0].options[0].detail"),
            Error(Kind.DUPLICATE, "questions[0].options[1].label"), Error(Kind.NOT_AN_OBJECT, "questions[0].options[2]")])

    def test_duplicate_ids_and_shapes(self):
        self.assertEqual(ask_form.validate({"questions": [question("a"), question("a")]}),
                         [Error(Kind.DUPLICATE, "questions[1].id")])
        self.assertEqual(ask_form.validate([]), [Error(Kind.NOT_AN_OBJECT, "form")])
        self.assertEqual(ask_form.validate({}), [Error(Kind.MISSING, "questions")])
        self.assertEqual(ask_form.validate({"questions": {}}), [Error(Kind.WRONG_TYPE, "questions")])

    def test_every_kind_has_a_message(self):
        self.assertEqual(set(ask_form.MESSAGES), set(Kind))


class RenderTest(unittest.TestCase):
    def test_data_is_embedded_and_cannot_close_the_script(self):
        html = ask_form.render(form(intro="Avant </script><b>"))
        self.assertNotIn(ask_form.DATA_SLOT, html)
        self.assertIn('"intro": "Avant <\\/script><b>"', html)
        self.assertEqual(html.count("</script>"), 1)

    def test_template_languages_match(self):
        template = ask_form.TEMPLATE.read_text(encoding="utf-8")
        labels = re.search(r"const LABELS = \{(.*?)\n\};", template, re.S).group(1)
        self.assertEqual(tuple(re.findall(r"^  (\w+): \{", labels, re.M)), ask_form.LANGS)

    def test_cli(self):
        ok = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(form()).encode(), capture_output=True)
        self.assertEqual(ok.returncode, 0)
        self.assertIn(b'"id": "q0"', ok.stdout)
        bad = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(form(11)).encode(), capture_output=True)
        self.assertEqual((bad.returncode, bad.stdout), (1, b""))
        self.assertIn(b"at most 10 questions", bad.stderr)
        broken = subprocess.run([sys.executable, str(SCRIPT)], input=b"{", capture_output=True)
        self.assertIn(b"invalid JSON", broken.stderr)


LOGIC_TEST = r"""
const assert = require("assert");
const qs = [
  {id: "one", title: "Un", options: [{label: "A"}, {label: "B"}]},
  {id: "many", title: "Plusieurs", multi: true, options: [{label: "A"}, {label: "B"}, {label: "C"}]},
  {id: "opt", title: "Facultative", required: false, options: [{label: "A"}, {label: "B"}]},
];
const st = newState(qs);
assert.strictEqual(canSend(qs, st), false);
toggle(qs[0], st[0], "A"); toggle(qs[0], st[0], "B");
assert.deepStrictEqual(st[0].selected, ["B"]);
toggle(qs[0], st[0], "B");
assert.deepStrictEqual(st[0].selected, []);
toggle(qs[0], st[0], "A");
toggle(qs[1], st[1], "C"); toggle(qs[1], st[1], "A");
assert.deepStrictEqual(st[1].selected, ["A", "C"]);
assert.strictEqual(canSend(qs, st), true);
toggle(qs[1], st[1], "A"); toggle(qs[1], st[1], "C");
assert.strictEqual(answered(st[1]), false);
st[1].open = true; st[1].free = "   ";
assert.strictEqual(answered(st[1]), false);
st[1].free = " Autre chose ";
assert.strictEqual(answered(st[1]), true);
toggle(qs[1], st[1], "B");
const res = result(qs, st, "submitted");
assert.deepStrictEqual(res, {status: "submitted", answers: [
  {id: "one", selected: ["A"], freeText: null},
  {id: "many", selected: ["B"], freeText: "Autre chose"},
  {id: "opt", selected: [], freeText: null}]});
assert.strictEqual(recap(qs, res, LABELS.fr),
  "Réponses :\n1. Un : A\n2. Plusieurs : B ; « Autre chose »\n3. Facultative : sans réponse");
const skipped = result(qs, st, "skipped");
assert.deepStrictEqual(skipped.answers[1], {id: "many", selected: [], freeText: null});
assert.strictEqual(recap(qs, skipped, LABELS.en), "Questions skipped, no answer.");
assert.deepStrictEqual(segments("See [#6 Form](https://github.com/o/r/issues/6) and [bad](javascript:x)."), [
  {text: "See "}, {text: "#6 Form", url: "https://github.com/o/r/issues/6"}, {text: " and [bad](javascript:x)."}]);
assert.deepStrictEqual(segments("Plain"), [{text: "Plain"}]);
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class LogicTest(unittest.TestCase):
    def test_answered_toggle_and_serialization(self):
        template = ask_form.TEMPLATE.read_text(encoding="utf-8")
        logic = template.split("// logic:start", 1)[1].split("// logic:end", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "logic_test.js"
            script.write_text(logic + LOGIC_TEST, encoding="utf-8")
            run = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_rendered_script_parses(self):
        html = ask_form.render(form(3, intro="Intro"))
        code = html.split("<script>", 1)[1].split("</script>", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "form.js"
            script.write_text(code, encoding="utf-8")
            run = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
