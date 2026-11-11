#!/usr/bin/env python3
"""Validate a question form and print it as the HTML of one `show_widget` call (core skill `ask`).

    python3 ask_form.py < questions.json    # or: python3 ask_form.py questions.json

The input is {"questions": [...], "intro"?: str, "lang"?: "fr" | "en"}; each question is
{"id", "title", "options": [{"label", "description"?, "icon"?}], "multi"?,
"freeTextPlaceholder"?, "required"?}. Options whose label ends with a recommended marker start
selected; a single-choice question has at most one. Valid: prints ask_form.html with the form's data, exits 0. Invalid: prints
one line per error on stderr, exits 1. The answers come back as one `sendPrompt` message.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

TEMPLATE = Path(__file__).resolve().with_name("ask_form.html")
DATA_SLOT = "/*DATA*/null"
# Limits of a form: beyond, the questions are split into rounds.
MAX_QUESTIONS = 10
MIN_OPTIONS = 2
MAX_OPTIONS = 8
LANGS = ("fr", "en")
FORM_KEYS = {"questions", "intro", "lang"}
QUESTION_KEYS = {"id", "title", "multi", "options", "freeTextPlaceholder", "required"}
OPTION_KEYS = {"label", "description", "icon"}
# Must match RECOMMENDED in ask_form.html.
RECOMMENDED = re.compile(r"\((Recommandé|Recommended)\)$")
# A Tabler outline icon class; the pattern also keeps the value safe inside a class attribute.
ICON = re.compile(r"ti-[a-z0-9]+(-[a-z0-9]+)*")


class Kind(Enum):
    NOT_AN_OBJECT = "not an object"
    UNKNOWN_KEY = "unknown key"
    MISSING = "missing"
    WRONG_TYPE = "wrong type"
    EMPTY = "empty"
    TOO_FEW_QUESTIONS = "too few questions"
    TOO_MANY_QUESTIONS = "too many questions"
    TOO_FEW_OPTIONS = "too few options"
    TOO_MANY_OPTIONS = "too many options"
    DUPLICATE = "duplicate"
    UNKNOWN_LANG = "unknown lang"
    SEVERAL_RECOMMENDED = "several recommended"
    UNKNOWN_ICON = "unknown icon"


@dataclass(frozen=True)
class Error:
    kind: Kind
    path: str


MESSAGES = {
    Kind.NOT_AN_OBJECT: "{path}: must be a JSON object",
    Kind.UNKNOWN_KEY: "{path}: unknown key",
    Kind.MISSING: "{path}: missing",
    Kind.WRONG_TYPE: "{path}: wrong type",
    Kind.EMPTY: "{path}: must not be empty",
    Kind.TOO_FEW_QUESTIONS: "{path}: at least 1 question",
    Kind.TOO_MANY_QUESTIONS: f"{{path}}: at most {MAX_QUESTIONS} questions; split them into rounds",
    Kind.TOO_FEW_OPTIONS: f"{{path}}: at least {MIN_OPTIONS} options",
    Kind.TOO_MANY_OPTIONS: f"{{path}}: at most {MAX_OPTIONS} options",
    Kind.DUPLICATE: "{path}: duplicate value",
    Kind.UNKNOWN_LANG: f"{{path}}: one of {', '.join(LANGS)}",
    Kind.SEVERAL_RECOMMENDED: "{path}: at most one recommended option in a single-choice question; make it multi",
    Kind.UNKNOWN_ICON: "{path}: a Tabler icon name such as ti-lock",
}


def _text(value: object, path: str, errors: list[Error], required: bool = True) -> None:
    if value is None:
        if required:
            errors.append(Error(Kind.MISSING, path))
    elif not isinstance(value, str):
        errors.append(Error(Kind.WRONG_TYPE, path))
    elif required and not value.strip():
        errors.append(Error(Kind.EMPTY, path))


def _keys(item: dict, allowed: set[str], path: str, errors: list[Error]) -> None:
    errors.extend(Error(Kind.UNKNOWN_KEY, f"{path}.{key}") for key in sorted(set(item) - allowed))


def _options(options: object, multi: bool, path: str, errors: list[Error]) -> None:
    if options is None:
        errors.append(Error(Kind.MISSING, path))
        return
    if not isinstance(options, list):
        errors.append(Error(Kind.WRONG_TYPE, path))
        return
    if len(options) < MIN_OPTIONS:
        errors.append(Error(Kind.TOO_FEW_OPTIONS, path))
    if len(options) > MAX_OPTIONS:
        errors.append(Error(Kind.TOO_MANY_OPTIONS, path))
    labels = set()
    for j, option in enumerate(options):
        where = f"{path}[{j}]"
        if not isinstance(option, dict):
            errors.append(Error(Kind.NOT_AN_OBJECT, where))
            continue
        _keys(option, OPTION_KEYS, where, errors)
        label = option.get("label")
        _text(label, f"{where}.label", errors)
        _text(option.get("description"), f"{where}.description", errors, required=False)
        icon = option.get("icon")
        if icon is not None and not isinstance(icon, str):
            errors.append(Error(Kind.WRONG_TYPE, f"{where}.icon"))
        elif icon is not None and not ICON.fullmatch(icon):
            errors.append(Error(Kind.UNKNOWN_ICON, f"{where}.icon"))
        if isinstance(label, str):
            if label in labels:
                errors.append(Error(Kind.DUPLICATE, f"{where}.label"))
            labels.add(label)
    recommended = [o for o in options if isinstance(o, dict) and isinstance(o.get("label"), str)
                   and RECOMMENDED.search(o["label"])]
    if not multi and len(recommended) > 1:
        errors.append(Error(Kind.SEVERAL_RECOMMENDED, path))


def validate(form: object) -> list[Error]:
    """Every error of the form, in reading order; empty when the form is valid."""
    if not isinstance(form, dict):
        return [Error(Kind.NOT_AN_OBJECT, "form")]
    errors: list[Error] = []
    _keys(form, FORM_KEYS, "form", errors)
    _text(form.get("intro"), "intro", errors, required=False)
    if "lang" in form and form["lang"] not in LANGS:
        errors.append(Error(Kind.UNKNOWN_LANG, "lang"))
    questions = form.get("questions")
    if questions is None:
        return errors + [Error(Kind.MISSING, "questions")]
    if not isinstance(questions, list):
        return errors + [Error(Kind.WRONG_TYPE, "questions")]
    if not questions:
        errors.append(Error(Kind.TOO_FEW_QUESTIONS, "questions"))
    if len(questions) > MAX_QUESTIONS:
        errors.append(Error(Kind.TOO_MANY_QUESTIONS, "questions"))
    ids = set()
    for i, question in enumerate(questions):
        path = f"questions[{i}]"
        if not isinstance(question, dict):
            errors.append(Error(Kind.NOT_AN_OBJECT, path))
            continue
        _keys(question, QUESTION_KEYS, path, errors)
        qid = question.get("id")
        _text(qid, f"{path}.id", errors)
        if isinstance(qid, str):
            if qid in ids:
                errors.append(Error(Kind.DUPLICATE, f"{path}.id"))
            ids.add(qid)
        _text(question.get("title"), f"{path}.title", errors)
        _text(question.get("freeTextPlaceholder"), f"{path}.freeTextPlaceholder", errors, required=False)
        for flag in ("multi", "required"):
            if flag in question and not isinstance(question[flag], bool):
                errors.append(Error(Kind.WRONG_TYPE, f"{path}.{flag}"))
        _options(question.get("options"), question.get("multi") is True, f"{path}.options", errors)
    return errors


def render(form: dict) -> str:
    """The widget HTML of a valid form; `</` escaped so that no text closes the script."""
    data = json.dumps(form, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace(DATA_SLOT, data, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", nargs="?", help="questions JSON (default: stdin)")
    args = parser.parse_args(argv)
    source = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.buffer.read().decode("utf-8")
    try:
        form = json.loads(source)
    except json.JSONDecodeError as error:
        print(f"invalid JSON: {error}", file=sys.stderr)
        return 1
    errors = validate(form)
    for error in errors:
        print(MESSAGES[error.kind].format(path=error.path), file=sys.stderr)
    if errors:
        return 1
    sys.stdout.buffer.write(render(form).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
