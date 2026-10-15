"""A kit field names its datum, not its words: a ratchet on typed labels, and a hard gate on the keys · since CR-33 phase 1.

Every `ui.field(…)` call of the templates is read. Four checks:

- **a field has a label or an attribute**, and never both: `label` became optional when
  `attribute=` came, so the old error of a missing label is gone and this is where it lives now;
- **an `attribute=` key that is a literal resolves in the register** and that entry has a
  label, so a wrong key fails in CI and never as a 500 on a screen (the register's lookup
  raises everywhere, PROD included);
- **typed labels may only shrink** (CR-33 T10): a call that types its label as `_("…")` is
  frozen in `tests/field_labels_baseline.py`, per template and per word, and a new one fails
  with the file and the hint to give the field an `attribute=`. A field that is no datum — a
  search box, a filter — keeps its typed label and stays on the list, with its reason in
  `REASONS` where it is not obvious. An entry that no longer exists must leave the list;
- **the scan looks somewhere**: it asserts it found more than a hundred calls before it
  judges.

Proven red, each with an ADDITIVE violation (15 October 2026): a call
`ui.field("x", _("Nieuw woord"))` added to a template → "types a label"; `attribute="mdm.person.nope"`
→ the register's LookupError names the known keys; both `label=` and `attribute=` → "both".
"""

from __future__ import annotations

import pathlib
import re
from collections import Counter

import pytest

from tests.field_labels_baseline import TYPED_LABELS

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
CALL = re.compile(r"\bui\.field\(")
TYPED = re.compile(r"""^_\(\s*(["'])(.*)\1\s*\)$""", re.DOTALL)


def _balanced(text: str, start: int) -> str:
    """The text between the parentheses that open at `start - 1`, strings respected."""
    depth, i, quote = 1, start, None
    while i < len(text) and depth:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        i += 1
    return text[start : i - 1]


def _arguments(body: str) -> list[str]:
    """The top-level, comma-separated arguments of a call."""
    args, depth, quote, current = [], 0, None, []
    i = 0
    while i < len(body):
        ch = body[i]
        if quote:
            current.append(ch)
            if ch == "\\":
                i += 1
                current.append(body[i])
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch in "([{":
            depth += 1
            current.append(ch)
        elif ch in ")]}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        args.append(tail)
    return args


def field_calls(text: str) -> list[dict]:
    """Every `ui.field(` call of a template: its label, its attribute, its line."""
    calls = []
    for match in CALL.finditer(text):
        args = _arguments(_balanced(text, match.end()))
        positional = [a for a in args if not re.match(r"^[A-Za-z_]\w*\s*=(?!=)", a)]
        keywords = {
            m.group(1): a.split("=", 1)[1].strip()
            for a in args
            if (m := re.match(r"^([A-Za-z_]\w*)\s*=(?!=)", a))
        }
        label = keywords.get("label") or (positional[1] if len(positional) > 1 else None)
        calls.append(
            {
                "line": text.count("\n", 0, match.start()) + 1,
                "label": label,
                "attribute": keywords.get("attribute"),
            }
        )
    return calls


def _templates() -> list[pathlib.Path]:
    return sorted(p for p in APP.rglob("*.html") if "tests" not in p.relative_to(APP).parts)


def _scan() -> list[tuple[str, dict]]:
    return [
        (path.relative_to(APP).as_posix(), call)
        for path in _templates()
        for call in field_calls(path.read_text())
    ]


def _typed_word(label: str | None) -> str | None:
    match = TYPED.match(label) if label else None
    return match.group(2) if match else None


def test_the_scan_reads_the_templates():
    calls = _scan()
    assert len(calls) > 100, f"found only {len(calls)} kit field calls"
    assert any(call["attribute"] for _, call in calls), "no field reads the register yet"


def test_every_field_has_a_label_or_an_attribute_and_never_both():
    problems = []
    for name, call in _scan():
        if call["label"] is None and call["attribute"] is None:
            problems.append(f"{name}:{call['line']} has neither a label nor an attribute=")
        if call["label"] is not None and call["attribute"] is not None:
            problems.append(f"{name}:{call['line']} has both a label and an attribute= (both)")
    assert not problems, "\n".join(problems)


def test_every_attribute_key_resolves_and_has_a_label():
    from app.domains.registry import load_all_models
    from app.kernel.attributes import attribute

    load_all_models()
    problems = []
    for name, call in _scan():
        raw = call["attribute"]
        if raw is None:
            continue
        literal = re.match(r"""^(["'])([\w.]+)\1$""", raw)
        if not literal:
            continue  # a computed key: the macro's global raises when it runs
        try:
            entry = attribute(literal.group(2))
        except LookupError as error:
            problems.append(f"{name}:{call['line']}: {error}")
            continue
        if not entry.label:
            problems.append(f"{name}:{call['line']}: {entry.key} has no label")
    assert not problems, "\n".join(problems)


def test_typed_labels_may_only_shrink():
    found: Counter[tuple[str, str]] = Counter()
    for name, call in _scan():
        word = _typed_word(call["label"])
        if word is not None:
            found[(name, word)] += 1
    frozen = Counter(
        {(name, word): n for name, words in TYPED_LABELS.items() for word, n in words.items()}
    )
    new = sorted((found - frozen).items())
    gone = sorted((frozen - found).items())
    assert not new, (
        "these fields type their label: give each an `attribute=` (a datum) or, if it is no "
        "datum, add it to tests/field_labels_baseline.py with its reason:\n  "
        + "\n  ".join(f"{name}: _({word!r}) × {n}" for (name, word), n in new)
    )
    assert not gone, (
        "these typed labels are gone: remove them from tests/field_labels_baseline.py so the "
        "list only shrinks:\n  "
        + "\n  ".join(f"{name}: _({word!r}) × {n}" for (name, word), n in gone)
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{{ ui.field("x", _("Nieuw woord"), kind="text") }}', "Nieuw woord"),
        ('{{ ui.field("x", label=_("Zoek"), kind="text") }}', "Zoek"),
        ('{{ ui.field("x", attribute="mdm.person.first_name") }}', None),
        ('{{ ui.field("x", some_variable, kind="text") }}', None),
        (
            '{{ ui.field("a" ~ k, _("Met (haakjes), en komma"), value=f(1, 2)) }}',
            "Met (haakjes), en komma",
        ),
    ],
)
def test_the_parser_reads_a_call(text, expected):
    """The gate can go red: it sees a typed label in each shape, and no label in the others."""
    (call,) = field_calls(text)
    assert _typed_word(call["label"]) == expected
