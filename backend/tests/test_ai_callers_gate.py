"""Refuses a module that formats a stored value into a prompt itself, or reads a `none` datum without a named exception · hard · since #2007.

CR-33 phase 2 (F7, T12): a module that talks to a model through `GuardedProvider` hands the
stored values it sends as `fields` — `(attribute key, value)` — and the port classifies and renders
them (`chatbot/fields.py`). What it must not do is what it did before: write `f"Naam: {activity.name}"`
into the prompt itself, where no classification looks at the value.

The callers are not typed here: they are the files outside the chatbot that build a
`GuardedProvider`. In them, an f-string is refused when it is a label and a value in the shapes of
the known idioms: `f"<Label>: {…}"` with a word the fiche or the sources used to carry, and
`f"- {…id…}: {…}"`, the line that listed the coming activities. The limit is stated, not hidden: a
value formatted with a new idiom slips this check; the pattern guard on the payload is the second net
and the reviewer of an AI caller reads the prompt builder for the rest.

**The one named exception** (Koen, 15 October 2026, Q&A nr. 12, "a"): the newsletter's writer reads
the minutes, which are `nooit` in the register, with the names removed. It stands in
`chatbot.fields.NAMED_EXCEPTIONS` with its reader and its reason; the reader says so where it reads
(`use_named_exception`), and this gate keeps the list honest: every exception names a datum that IS
`none`, a reader that really calls it, and nobody else calls it.

Proven red with an ADDITIVE violation (15 October 2026): the line `x = f"Naam: {activity.name}"` added
to `activities/proposer.py` fails the idiom test naming the file and the line; a call
`use_named_exception("meetings.meeting_item.notes_document", by="media.extraction")` added to
`media/extraction.py` fails the exception test.
"""

import ast
import re
from pathlib import Path

from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"

LABEL = re.compile(r"^\s*(Naam|Locatie|Omschrijving|Datums|Onderdeel|Activiteit|Product):\s*$")


def _rel(path: Path) -> str:
    return path.relative_to(APP).as_posix()


def _python():
    return bestanden(APP.rglob("*.py"), wat="alle Python-modules onder app/", minstens=100)


def ai_callers() -> list[Path]:
    """The files outside the chatbot that build a `GuardedProvider`."""
    return [
        p
        for p in _python()
        if not _rel(p).startswith("domains/chatbot/")
        and "GuardedProvider(" in p.read_text(encoding="utf-8")
    ]


def idioms(source: str) -> list[tuple[int, str]]:
    """The lines of `source` that format a stored value into text the known ways."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.JoinedStr):
            continue
        parts = node.values
        first = parts[0] if parts else None
        if (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and LABEL.match(first.value)
            and len(parts) > 1
            and isinstance(parts[1], ast.FormattedValue)
        ):
            found.append((node.lineno, f"a label and a value: {first.value.strip()}"))
        if (
            len(parts) == 4
            and isinstance(parts[0], ast.Constant)
            and parts[0].value == "- "
            and isinstance(parts[1], ast.FormattedValue)
            and isinstance(parts[2], ast.Constant)
            and str(parts[2].value).startswith(":")
            and isinstance(parts[3], ast.FormattedValue)
        ):
            found.append((node.lineno, "a line `- {id}: {name}`"))
    return found


def test_the_gate_finds_the_ai_callers():
    callers = {_rel(p) for p in ai_callers()}
    assert {
        "domains/activities/proposer.py",
        "domains/newsletter/drafting.py",
    } <= callers, sorted(callers)


def test_no_ai_caller_formats_a_stored_value_into_its_prompt():
    problems = [
        f"{_rel(p)}:{line}: {what}"
        for p in ai_callers()
        for line, what in idioms(p.read_text(encoding="utf-8"))
    ]
    assert not problems, (
        "a stored value is formatted into a prompt; hand it as a field of the register "
        "(`chatbot.api.Field`) and let the port render it:\n  " + "\n  ".join(problems)
    )


def test_the_idioms_are_recognised():
    """The gate can go red: the two shapes, written the old way."""
    old = 'a = f"Naam: {x.name}"\nb = f"- {s.activity.id}: {s.activity.name}"\nc = f"Naam is {x}"\n'
    assert [what for _line, what in idioms(old)] == [
        "a label and a value: Naam:",
        "a line `- {id}: {name}`",
    ]


def test_every_named_exception_is_honest():
    from app.domains.chatbot.api import NAMED_EXCEPTIONS
    from app.domains.registry import load_all_models
    from app.kernel.attributes import AiExposure, attribute

    load_all_models()
    assert NAMED_EXCEPTIONS, "no exception named — is the list still read?"
    for key, exception in NAMED_EXCEPTIONS.items():
        assert attribute(key).ai_exposure is AiExposure.NONE, (
            f"{key} is no longer `none`: the exception is an exception to nothing"
        )
        reader = APP / ("domains/" + exception.by.replace(".", "/") + ".py")
        assert f'use_named_exception("{key}", by="{exception.by}")' in reader.read_text(
            encoding="utf-8"
        ), f"{exception.by} does not say, where it reads, that it is the exception for {key}"
        others = [
            _rel(p)
            for p in _python()
            if _rel(p) != _rel(reader)
            and not _rel(p).startswith("domains/chatbot/")
            and f'use_named_exception("{key}"' in p.read_text(encoding="utf-8")
        ]
        assert not others, f"{key} is read as an exception by more than its named reader: {others}"
