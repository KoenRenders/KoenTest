"""#1216 — the words of an export's filter header go through `_()`.

The header of sheet 1 says which filters were active: "Datum ligt tussen … en
…", "Jaar is dit jaar (2026)". Its operator words, the " en " between two
values and the symbolic values (`SYMBOLIC_LABELS`) were written as plain Dutch
strings, so they could never be translated. Koen's decision (27 September
2026): they go through `_()` and into the catalogue now; an English interface
is a decision of its own, and nothing changes on the screen today. The object
names (`obj.name`, from the universe) stay outside this issue.

So these tests do not check that an English export is English — there is no
English catalogue. They check the two things this issue makes true: every word
is in `messages.pot` and in the `nl_BE` catalogue, and every word reaches the
header through `_()` (a marking `_` swapped in shows on each of them).

Broken on purpose to check that these tests can go red: `"ne": _("is niet")`
written back as `"ne": "is niet"` in `filter_summary` → the routing test falls
over on the `ne` line; `N_(` taken off "dit jaar" in `SYMBOLIC_LABELS` → the
catalogue test falls over after `scripts/i18n.sh`, because the word is no
longer extracted.
"""

from pathlib import Path

import pytest

from app.domains.reporting import exports
from app.domains.reporting.engine import (
    SYMBOLIC_LABELS,
    SYMBOLIC_THIS_YEAR,
    Filter,
    Operator,
    Selection,
)

pytestmark = pytest.mark.ui_agnostisch

LOCALES = Path(__file__).resolve().parents[1] / "app" / "locales"
OPERATOR_WORDS = [
    "is",
    "is niet",
    "is een van",
    "is kleiner dan",
    "is hoogstens",
    "is groter dan",
    "is minstens",
    "ligt tussen",
    "bevat",
]


def _msgids(path: Path) -> set[str]:
    return {
        line[len('msgid "') : -1]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith('msgid "')
    }


@pytest.mark.parametrize("catalogue", ["messages.pot", "nl_BE/LC_MESSAGES/messages.po"])
def test_every_header_word_is_in_the_catalogue(catalogue):
    msgids = _msgids(LOCALES / catalogue)
    assert len(msgids) > 100, f"{catalogue} looks empty — is this test still looking?"
    words = OPERATOR_WORDS + ["en"] + list(SYMBOLIC_LABELS.values())
    missing = [w for w in words if w not in msgids]
    assert not missing, f"not in {catalogue}: {missing} — run scripts/i18n.sh"


def test_every_header_word_reaches_the_header_through_underscore(monkeypatch):
    """A `_` that marks what it translates: every word must come out marked."""
    monkeypatch.setattr(exports, "_", lambda text: f"«{text}»")
    object_key = next(iter(exports.BY_KEY))
    filters = [Filter(object_key=object_key, operator=op, values=("1", "2")) for op in Operator]
    filters.append(
        Filter(
            object_key=object_key,
            operator=Operator.EQ,
            values=("2026",),
            symbolic=SYMBOLIC_THIS_YEAR,
        )
    )
    lines = exports.filter_summary(Selection(object_keys=(object_key,), filters=tuple(filters)))

    for op, line in zip(Operator, lines):
        assert "«" in line.split("1", 1)[0], f"{op.value}: the operator word is plain: {line!r}"
    between = lines[list(Operator).index(Operator.BETWEEN)]
    assert "«en»" in between, between
    assert f"«{SYMBOLIC_LABELS[SYMBOLIC_THIS_YEAR]}»" in lines[-1], lines[-1]
