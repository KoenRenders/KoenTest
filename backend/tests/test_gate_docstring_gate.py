"""Refuses a gate file whose docstring does not open with the one sentence of the fixed shape · hard · since #1952.

Part C2 of the architecture document is a table of the gates of the test suite,
and the table is derived from the code: the first line of the docstring of every
gate is one English sentence in one shape,

    Refuses <what> · <hard|ratchet> · since #<issue>.

— what the gate refuses, whether it is a hard gate or a ratchet (a baseline that
may only shrink), and the issue that brought it. The rest of the docstring stays
free text. Before #1952 all 53 gates had a docstring, in two languages and five
shapes, so the table of 13 October 2026 was written by hand; this gate keeps the
one shape, so the next table needs no hand.

**The set** is `GATE_BESTANDEN` of `test_gate_niet_leeg.py`: every file found by
name (`test_*gate*.py`, `*ratchet*.py`, under `tests/` and under
`app/domains/*/tests/`) and the four named files, 58 on 13 October 2026, this
gate included. It is read through the helper of that file, so an empty or a too
small set is red. **The regex** is `GATE_SENTENCE` below, with the groups
`refuses`, `kind` and `issue`; the documentation build reads both.

**Hard or ratchet:** `ratchet` is a gate whose baseline may only shrink and is
read by the gate itself (`ui_baseline.py`, `public_baseline.py`, the ceiling of
`test_list_table_gate.py`); a hard gate with a list of reasoned exemptions in its
own file that may only shrink is `hard`, as is `test_rules_gate.py`, which holds
two ratchets among its rules.

Proven red, additively: a scratch file in the set whose docstring lacks the
sentence is named by the message (`test_a_scratch_gate_without_the_sentence_is_named`,
on the real set plus the scratch file), and each defect — no docstring, another
opening, a missing kind, a missing issue, a missing full stop — is named in its
own words. The same on the real tree is a scratch `tests/test_zz_scratch_gate.py`
with a plain docstring, put in and taken out again.
"""

import ast
import re
from pathlib import Path

import pytest

from tests.test_gate_niet_leeg import BACKEND, GATE_BESTANDEN

#: The one sentence every gate opens with (#1952). Read by the documentation build.
GATE_SENTENCE = re.compile(
    r"^Refuses (?P<refuses>.+) · (?P<kind>hard|ratchet) · since #(?P<issue>\d+)\.$"
)

SHAPE = "Refuses <what> · <hard|ratchet> · since #<issue>."


def first_line(path: Path) -> str | None:
    """The first line of the module docstring of this file, or None."""
    doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
    return doc.splitlines()[0] if doc else None


def sentence_problem(line: str | None) -> str | None:
    """What is wrong with a first line, in words that say what to write; None when
    it is the sentence."""
    if line is None:
        return f"has no docstring: open it with `{SHAPE}`"
    if GATE_SENTENCE.match(line):
        return None
    if not line.startswith("Refuses "):
        return f'opens with "{line[:70]}": open it with `{SHAPE}`'
    if not line.endswith("."):
        return f"the sentence does not end with a full stop: `{SHAPE}`"
    parts = line.split(" · ")
    if len(parts) != 3:
        return f"has {len(parts)} part(s) split by ` · `, the shape has three: `{SHAPE}`"
    if parts[1] not in ("hard", "ratchet"):
        return f'the second part is "{parts[1]}": it is `hard` or `ratchet`'
    return f'the third part is "{parts[2]}": it is `since #<issue>.`, a number'


def _name(path: Path) -> str:
    try:
        return path.relative_to(BACKEND).as_posix()
    except ValueError:
        return str(path)


def problems(paths: list[Path]) -> dict[str, str]:
    """Per file (under `backend/`) what is missing from its first sentence."""
    found = {}
    for path in paths:
        problem = sentence_problem(first_line(path))
        if problem:
            found[_name(path)] = problem
    return found


def _message(found: dict[str, str]) -> str:
    return "Every gate opens with one sentence (#1952):\n" + "\n".join(
        f"  {name}: {problem}" for name, problem in sorted(found.items())
    )


def test_every_gate_opens_with_the_sentence():
    paths = [BACKEND / name for name in GATE_BESTANDEN]
    assert len(paths) >= 58, "the set of gates is smaller than it was: the gate walks too little"
    found = problems(paths)
    assert not found, _message(found)


def test_a_scratch_gate_without_the_sentence_is_named(tmp_path):
    """The additive violation: a file in the set with a plain docstring is red, and
    the message names it. Removed (here: not part of the real list), green."""
    scratch = tmp_path / "test_zz_scratch_gate.py"
    scratch.write_text('"""A gate with a docstring that is no sentence of the shape."""\n')
    real = [BACKEND / name for name in GATE_BESTANDEN]

    assert problems(real) == {}, "the real set must be green for this proof to mean anything"
    found = problems([*real, scratch])
    assert list(found) == [str(scratch)], found
    assert "test_zz_scratch_gate.py" in _message(found)


@pytest.mark.parametrize(
    ("docstring", "says"),
    [
        (None, "has no docstring"),
        ("Gate on something · hard · since #1.", "opens with"),
        ("Refuses a thing · hard · since #12", "full stop"),
        ("Refuses a thing since #12.", "has 1 part"),
        ("Refuses a thing · soft · since #12.", '"soft"'),
        ("Refuses a thing · hard · since the start.", "a number"),
        ("Refuses a thing · hard · since #1 · extra.", "has 4 part"),
    ],
)
def test_each_defect_is_named_in_its_own_words(docstring, says):
    assert says in (sentence_problem(docstring) or "")


def test_the_sentence_parses_into_its_three_parts():
    """What the documentation build reads."""
    line = "Refuses a loose string compared where a code exists · ratchet · since #1177."
    match = GATE_SENTENCE.match(line)
    assert match and match.groupdict() == {
        "refuses": "a loose string compared where a code exists",
        "kind": "ratchet",
        "issue": "1177",
    }
    assert sentence_problem(line) is None
