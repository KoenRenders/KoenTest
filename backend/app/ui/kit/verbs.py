"""The kit's vocabulary of verbs and glyphs, readable from Python (#2106).

One meaning per glyph (§1.4 of `docs/design-system.md`, #698, CR-11 block 1): a
text button carries the lead glyph its verb has here, and a glyph of this table
stands only on a button of its own verb. The table lives HERE and nowhere else
as data: the design-system page renders it (`/admin/design-system`, section
3), and the UI gate (`tests/test_ui_conventions_gate.py`) reads it. The prose
table of §1.4 is the same words for a reader of the document; a test ties the
two (`tests/test_verb_table_one_source_2106.py`), so neither can drift alone.

A verb is the FIRST WORD of a button's label — a leading "+" reads as "add",
and punctuation around the word does not count. "Toevoegen aan de kring" is
the verb *toevoegen*; "Annuleren" and "Openen" are in no row, so they have no
glyph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: What a leading "+" in a label stands for. The glyph is `plus`, never a typed "+".
PLUS_VERB = "toevoegen"


@dataclass(frozen=True)
class Verb:
    """One row of the table."""

    glyph: str
    #: What the glyph means, in the words of the design-system page.
    meaning: str
    #: The Dutch words a label begins with (lower case). Empty: the row is
    #: documentation only — a reference, a group, the "more" menu — and the
    #: gate has no label to read for it.
    words: tuple[str, ...] = ()
    #: The kit style the verb always has (`btn_danger` for delete).
    variant: str | None = None
    #: A note beside the row on the page.
    note: str = ""


VERBS: tuple[Verb, ...] = (
    Verb("plus", "toevoegen / nieuw", ("toevoegen", "nieuw", "nieuwe")),
    Verb("upload", "uploaden / importeren", ("uploaden", "importeren")),
    Verb("pencil", "bewerken", ("bewerken", "wijzigen"), note="niet het tandwiel"),
    Verb("trash-2", "verwijderen", ("verwijderen",), variant="danger", note="altijd rood"),
    Verb("copy", "kopiëren", ("kopiëren",)),
    Verb("printer", "afdrukken", ("afdrukken", "printen")),
    Verb("send", "versturen", ("versturen", "verstuur", "stuur", "verzenden")),
    Verb("filter", "filteren", ("filteren",)),
    Verb("settings", "instellingen", ("instellingen",), note="het tandwiel, en niets anders"),
    Verb("download", "downloaden / exporteren", ("downloaden", "download", "exporteren", "export")),
    Verb("x", "sluiten", ("sluiten",), note="een toast, een modal, een paneel — nooit verwijderen"),
    Verb("chevron-left", "de weg terug", ("terug",)),
    Verb("sparkles", "de assistent", ("assistent",)),
    Verb("arrow-up-right", "elders openen (een verwijzing)", note="geen vast label"),
    Verb("ellipsis", "meer acties", note="geen vast label"),
    Verb("chevron-down", "een groep die opent of sluit", note="nooit het tandwiel"),
    Verb("chevron-right", "een groep die opent of sluit", note="de dichte stand"),
)

#: The glyphs of the verbs that make something new: the create button of a list's
#: header is one of these (it was a label with a typed "+" until #2106). Two list
#: screens create by uploading.
CREATE_GLYPHS = ("plus", "upload")

_BY_WORD: dict[str, Verb] = {w: v for v in VERBS for w in v.words}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def glyphs() -> tuple[str, ...]:
    """Every glyph of the table."""
    return tuple(v.glyph for v in VERBS)


def gated_glyphs() -> tuple[str, ...]:
    """The glyphs the gate checks: the rows that have words to read a label by."""
    return tuple(v.glyph for v in VERBS if v.words)


def verb_of(label: str) -> Verb | None:
    """The verb a label begins with, or None. A leading "+" is *toevoegen*."""
    text = label.strip()
    if text.startswith("+"):
        return _BY_WORD[PLUS_VERB]
    first = _WORD.search(text)
    return _BY_WORD.get(first.group(0).lower()) if first else None


def verbs_in(label: str) -> set[str]:
    """The glyphs of every verb that stands anywhere in a label — the "other
    verb" a glyph must not sit on."""
    found = {_BY_WORD[w.lower()].glyph for w in _WORD.findall(label) if w.lower() in _BY_WORD}
    if label.strip().startswith("+"):
        found.add(_BY_WORD[PLUS_VERB].glyph)
    return found
