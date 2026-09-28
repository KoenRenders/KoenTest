"""#1280 — a code-list enum is its code in every string context, not `Klasse.LID`.

A member of a plain `Enum` turns into `Klasse.LID` in an f-string, `str()`,
`.format()` and a log line. CR-12 made dozens of strings into enums, and three
times a member landed silently where a string was expected (#1268 a template
comparison, #1279 a webhook URL ending in `PaymentProvider.MOLLIE`, and a member
in a template's output). No gate sees an f-string or a URL. So the class is closed
by construction: every enum of a `CodeList`, and every `ExternalVocabulary`,
inherits from `CodeEnum`, whose `__str__` and `__format__` give the code.

Two tests, both walking the REGISTRY rather than a list kept here, so a list
declared tomorrow is covered without editing this file:
  - the gate: every registered enum is a `CodeEnum` — names the one that is not;
  - the behaviour, per member of every registered enum: `f"{m}"`, `str(m)` and
    `"{}".format(m)` equal `m.value`; `repr(m)` does not; and a comparison with
    the code stays false, because `CodeEnum` is not a `str` (the text gates of
    CR-12 phase 5 rely on that).

Each test first asserts it found enums at all (#678).

Broken on purpose to check these tests can go red (run, then restored):
`class MeetingStatus(CodeEnum)` put back to `class MeetingStatus(Enum)` (with its
import) → the gate fails with "meetings.models.MeetingStatus is a plain Enum",
and the behaviour test with "meetings.models.MeetingStatus.AGENDA: f-string gives
'MeetingStatus.AGENDA', not 'agenda'".
"""
from __future__ import annotations

from enum import Enum

import pytest

from app.domains.registry import load_all_models
from app.kernel.codes import CodeEnum, ExternalVocabulary, registry


def _registered_enums() -> list[type[Enum]]:
    load_all_models()
    enums = {lst.enum for lst in registry().values() if lst.enum is not None}
    return sorted(enums, key=lambda e: f"{e.__module__}.{e.__name__}")


def _external_vocabularies() -> list[type[Enum]]:
    """Every loaded `ExternalVocabulary` subclass (the adapter enums, e.g. Mollie)."""
    load_all_models()
    import app.domains.payment.providers.mollie  # noqa: F401  the adapter lives outside the models

    found, todo = [], list(ExternalVocabulary.__subclasses__())
    while todo:
        cls = todo.pop()
        found.append(cls)
        todo.extend(cls.__subclasses__())
    return found


def _name(e: type[Enum]) -> str:
    return f"{e.__module__.removeprefix('app.domains.')}.{e.__name__}"


def test_every_code_list_enum_is_a_code_enum():
    enums = _registered_enums()
    assert len(enums) > 10, f"the registry yielded only {len(enums)} enums — the walk is blind"
    plain = [_name(e) for e in enums if not issubclass(e, CodeEnum)]
    assert not plain, "\n".join(
        f"{n} is a plain Enum — inherit from app.kernel.codes.CodeEnum, so a member is "
        f"its code in an f-string, str(), .format() and a log line (#1280)" for n in plain)


def test_every_member_is_its_code_in_a_string_context():
    enums = _registered_enums() + _external_vocabularies()
    members = [m for e in enums for m in e]
    assert len(members) > 50, f"only {len(members)} members found — the walk is blind"
    wrong = []
    for m in members:
        code = str(m.value)
        seen = {"f-string": f"{m}", "str()": str(m), ".format()": "{}".format(m),
                "%s": "%s" % m}
        wrong += [f"{_name(type(m))}.{m.name}: {how} gives {got!r}, not {code!r}"
                  for how, got in seen.items() if got != code]
        if repr(m) == code:
            wrong.append(f"{_name(type(m))}.{m.name}: repr() lost the member name")
        if not isinstance(m, str) and m == m.value:
            wrong.append(f"{_name(type(m))}.{m.name}: equals its code — CodeEnum must not be a str")
    assert not wrong, "\n".join(wrong[:20]) + (f"\n… {len(wrong) - 20} more" if len(wrong) > 20 else "")


def test_the_adapter_enum_is_a_code_enum_too():
    """Mollie's statuses end up in URLs and log lines like our own codes do."""
    adapters = _external_vocabularies()
    assert adapters, "no ExternalVocabulary subclass found — the walk is blind"
    assert all(issubclass(a, CodeEnum) for a in adapters)
